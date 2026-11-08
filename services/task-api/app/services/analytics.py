"""
Istatistikler: her istekte ham veriden (oturumlar, gunluk planlar, activity
log, kartlar) hesaplanir. Kisisel olcekte veri kucuk; hazir tutulan ozet
tablolari eskiyebilirdi, anlik hesap her zaman dogru.

Bu ozet hem istatistik sayfasini hem de (Faz 4) AI'in get_stats_summary
aracini besler; AI ham veri yerine bu hazir metrikleri okur.
"""

from datetime import UTC, date, datetime, timedelta
from statistics import median

from app.core.exceptions import ValidationException
from app.db.entities.day_plan import DayPlanStatus, ItemOutcome
from app.db.unit_of_work import TaskUnitOfWork
from app.models.analytics import (
    AnalyticsSummary,
    BoardStat,
    DayStat,
    EstimateAccuracy,
    EstimateSample,
    PostponedCard,
    Totals,
)
from app.services.timeutil import (
    local_today,
    range_bounds,
    session_span,
    split_by_hour,
    user_tz,
)

MAX_DAYS = 366
NO_BOARD_COLOR = "#94a3b8"


def _now() -> datetime:
    return datetime.now(UTC)


class AnalyticsService:
    def __init__(self, uow: TaskUnitOfWork):
        self.uow = uow

    async def summary(self, user_id: int, first: date, last: date) -> AnalyticsSummary:
        if last < first:
            raise ValidationException("end, start'tan önce olamaz")
        n_days = (last - first).days + 1
        if n_days > MAX_DAYS:
            raise ValidationException(
                f"En fazla {MAX_DAYS} günlük aralık sorgulanabilir"
            )

        tz = await user_tz(self.uow, user_id)
        start, end = range_bounds(first, last, tz)
        now = _now()

        days = {
            first + timedelta(days=i): DayStat(date=first + timedelta(days=i))
            for i in range(n_days)
        }
        hours = [0.0] * 24
        weekdays = [0.0] * 7
        board_sec: dict[int | None, float] = {}
        day_sec: dict[date, float] = {}

        # --- harcanan sure: oturumlari gun/saat/board'a bol ---
        sessions = await self.uow.time_sessions.list_for_user(
            user_id, start, end, limit=100_000
        )
        for s in sessions:
            span = session_span(s, start, end, now)
            if span is None:
                continue
            for day, hour, sec in split_by_hour(span[0], span[1], tz):
                hours[hour] += sec
                weekdays[day.weekday()] += sec
                board_sec[s.board_id] = board_sec.get(s.board_id, 0) + sec
                day_sec[day] = day_sec.get(day, 0) + sec
        for day, d in days.items():
            d.tracked_min = round(day_sec.get(day, 0) / 60)

        # --- gunluk planlar / degerlendirmeler ---
        plans = await self.uow.day_plans.in_range(user_id, first, last)
        items = await self.uow.day_plan_items.for_plans([p.id for p in plans])
        by_plan: dict[int, list] = {}
        for it in items:
            by_plan.setdefault(it.day_plan_id, []).append(it)
        planned_total = done_total = 0
        score = 0.0
        scored = 0
        for p in plans:
            d = days[p.date]
            d.reviewed = p.status == DayPlanStatus.REVIEWED
            d.mood, d.energy = p.mood, p.energy
            for it in by_plan.get(p.id, []):
                if not it.was_planned:
                    d.unplanned += 1
                    continue
                d.planned += 1
                planned_total += 1
                if it.outcome == ItemOutcome.DONE:
                    d.done += 1
                    done_total += 1
                elif it.outcome == ItemOutcome.PARTIAL:
                    d.partial += 1
                elif it.outcome == ItemOutcome.NOT_DONE:
                    d.not_done += 1
                elif it.outcome == ItemOutcome.POSTPONED:
                    d.postponed += 1
                if it.outcome is not None:
                    scored += 1
                    score += {ItemOutcome.DONE: 1, ItemOutcome.PARTIAL: 0.5}.get(
                        it.outcome, 0
                    )

        # --- board'lar ---
        boards = await self.uow.boards.list_for_user(user_id, include_archived=True)
        completed = await self.uow.analytics.completed_cards(user_id, start, end)
        completed_by_board: dict[int | None, int] = {}
        for c in completed:
            completed_by_board[c.board_id] = completed_by_board.get(c.board_id, 0) + 1
        board_stats = [
            BoardStat(
                board_id=b.id,
                name=b.name,
                color=b.color,
                tracked_min=round(board_sec.get(b.id, 0) / 60),
                completed_cards=completed_by_board.get(b.id, 0),
                budget_min=round(b.weekly_time_budget_min * n_days / 7)
                if b.weekly_time_budget_min
                else None,
            )
            for b in boards
            if not b.is_archived or b.id in board_sec or b.id in completed_by_board
        ]
        free = board_sec.get(None, 0)
        if free:
            board_stats.append(
                BoardStat(
                    board_id=None,
                    name="Board'suz / serbest",
                    color=NO_BOARD_COLOR,
                    tracked_min=round(free / 60),
                )
            )
        board_stats.sort(key=lambda b: b.tracked_min, reverse=True)

        # --- tahmin dogrulugu (tamamlanan kartlar, tum zamanlarin suresi) ---
        estimated = [c for c in completed if c.estimated_minutes]
        totals_sec = await self.uow.time_sessions.totals_for_cards(
            [c.id for c in estimated]
        )
        samples = [
            EstimateSample(
                card_id=c.id,
                title=c.title,
                estimated_min=c.estimated_minutes,  # type: ignore[arg-type]
                tracked_min=round(totals_sec[c.id] / 60),
                ratio=round(totals_sec[c.id] / 60 / c.estimated_minutes, 2),  # type: ignore[operator]
            )
            for c in estimated
            if totals_sec.get(c.id, 0) >= 60
        ]
        ratios = [s.ratio for s in samples]
        accuracy = EstimateAccuracy(
            sample_size=len(samples),
            mean_ratio=round(sum(ratios) / len(ratios), 2) if ratios else None,
            median_ratio=round(median(ratios), 2) if ratios else None,
            biggest_overruns=sorted(samples, key=lambda s: s.ratio, reverse=True)[:5],
        )

        # --- en cok ertelenenler ---
        postponed_rows = await self.uow.analytics.postpone_counts(user_id, first, last)
        titles = {
            c.id: c.title
            for c in await self.uow.tasks.get_many([cid for cid, _ in postponed_rows])
        }
        most_postponed = [
            PostponedCard(card_id=cid, title=titles.get(cid, "Silinmiş kart"), count=n)
            for cid, n in postponed_rows
        ]

        # --- seri: bugun ya da dun biten ardisik degerlendirilmis gunler ---
        reviewed = set(await self.uow.day_plans.reviewed_dates(user_id))
        today = local_today(tz, now)
        cursor = today if today in reviewed else today - timedelta(days=1)
        streak = 0
        while cursor in reviewed:
            streak += 1
            cursor -= timedelta(days=1)

        total_sec = sum(board_sec.values())
        return AnalyticsSummary(
            start=first,
            end=last,
            totals=Totals(
                days=n_days,
                tracked_min=round(total_sec / 60),
                planned_items=planned_total,
                done_items=done_total,
                completion_rate=round(score / scored, 2) if scored else None,
                reviewed_days=sum(1 for d in days.values() if d.reviewed),
                current_streak=streak,
                completed_cards=len(completed),
            ),
            days=list(days.values()),
            boards=board_stats,
            estimate_accuracy=accuracy,
            productive_hours=[round(h / 60) for h in hours],
            weekdays=[round(w / 60) for w in weekdays],
            most_postponed=most_postponed,
        )
