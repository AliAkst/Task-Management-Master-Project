"""
İş özeti (Faz 13h1): bir günün tamamlanan / çalışılan / yapılamayan / yarın
işlerini Trello'ya yapıştırılabilir Markdown'a çevirir. Yalnız okur.
"""

from datetime import date, timedelta

from app.core.exceptions import NotFoundException
from app.db.entities.day_plan import DayPlanItemEntity, ItemOutcome
from app.db.unit_of_work import TaskUnitOfWork
from app.models.reports import (
    NotDoneLine,
    TomorrowLine,
    WorkLine,
    WorkSections,
    WorkSummary,
)
from app.services.timeutil import day_bounds, session_span, user_tz

WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]  # fmt: skip

Key = tuple[str, int | str]


def fmt_minutes(minutes: int) -> str:
    """90 -> '1 sa 30 dk', 45 -> '45 dk', 120 -> '2 sa', 0 -> ''."""
    if minutes <= 0:
        return ""
    hours, rest = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} sa")
    if rest:
        parts.append(f"{rest} dk")
    return " ".join(parts)


def short_date(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}"


def render_text(day: date, s: WorkSections) -> str:
    head = f"**İş özeti — {short_date(day)} {day.year}, {WEEKDAYS[day.weekday()]}**"
    blocks: list[str] = []

    def timed(line: WorkLine) -> str:
        t = fmt_minutes(line.minutes)
        return f"- {line.title} ({t})" if t else f"- {line.title}"

    if s.completed:
        blocks.append("**Tamamlananlar**\n" + "\n".join(timed(x) for x in s.completed))
    if s.worked:
        blocks.append(
            "**Üzerinde çalışılanlar**\n" + "\n".join(timed(x) for x in s.worked)
        )
    if s.not_done:
        rows = []
        for n in s.not_done:
            row = f"- {n.title}"
            if n.reason:
                row += f" — neden: {n.reason}"
            if n.postponed_to:
                row += f" (→ {short_date(n.postponed_to)})"
            rows.append(row)
        blocks.append("**Yapılamayanlar**\n" + "\n".join(rows))
    if s.tomorrow:
        blocks.append("**Yarın**\n" + "\n".join(f"- {x.title}" for x in s.tomorrow))
    if not blocks:
        return f"{head}\n\nBu gün için kayıtlı iş yok."
    return head + "\n\n" + "\n\n".join(blocks)


class ReportService:
    def __init__(self, uow: TaskUnitOfWork):
        self.uow = uow

    async def _owned_boards(self, user_id: int, ids: list[int] | None) -> set[int] | None:
        if ids is None:
            return None
        for board_id in ids:
            if await self.uow.boards.get_owned(board_id, user_id) is None:
                raise NotFoundException("Board", board_id)
        return set(ids)

    async def work_summary(
        self, user_id: int, day: date, board_ids: list[int] | None
    ) -> WorkSummary:
        boards = await self._owned_boards(user_id, board_ids)

        def ok(board_id: int | None) -> bool:
            return boards is None or board_id in boards

        tz = await user_tz(self.uow, user_id)
        start, end = day_bounds(day, tz)

        plan = await self.uow.day_plans.for_date(user_id, day)
        items: list[DayPlanItemEntity] = (
            await self.uow.day_plan_items.for_plans([plan.id]) if plan else []
        )
        nxt = await self.uow.day_plans.for_date(user_id, day + timedelta(days=1))
        next_items = await self.uow.day_plan_items.for_plans([nxt.id]) if nxt else []

        # ---- o günün oturumları -> (anahtar -> saniye) ----
        sessions = await self.uow.time_sessions.list_for_user(
            user_id, start, end, limit=5000
        )
        item_cache: dict[int, DayPlanItemEntity | None] = {i.id: i for i in items}
        card_cache: dict[int, object] = {}
        seconds: dict[Key, int] = {}
        titles: dict[Key, str] = {}
        boards_of: dict[Key, int | None] = {}

        for s in sessions:
            span = session_span(s, start, end)
            if span is None:
                continue
            sec = int((span[1] - span[0]).total_seconds())
            key: Key
            title: str
            board: int | None
            if s.card_id is not None:
                key = ("c", s.card_id)
                card = card_cache.get(s.card_id)
                if card is None:
                    card = await self.uow.tasks.get_by_id(s.card_id)
                    card_cache[s.card_id] = card
                title = getattr(card, "title", None) or s.card_title or "(adsız)"
                board = s.board_id
            elif s.day_plan_item_id is not None:
                if s.day_plan_item_id not in item_cache:
                    item_cache[s.day_plan_item_id] = await self.uow.day_plan_items.get_by_id(
                        s.day_plan_item_id
                    )
                it = item_cache[s.day_plan_item_id]
                if it is not None and it.card_id is not None:
                    key, title, board = ("c", it.card_id), it.title, it.board_id
                elif it is not None:
                    key, title, board = ("i", it.id), it.title, it.board_id
                else:
                    key = ("t", s.card_title or "(adsız)")
                    title, board = s.card_title or "(adsız)", s.board_id
            else:
                title = s.card_title or "(adsız)"
                key, board = ("t", title), s.board_id
            seconds[key] = seconds.get(key, 0) + sec
            titles.setdefault(key, title)
            boards_of.setdefault(key, board)

        def minutes(key: Key, fallback: int = 0) -> int:
            return round((seconds.get(key) or fallback) / 60)

        def item_key(it: DayPlanItemEntity) -> Key:
            return ("c", it.card_id) if it.card_id is not None else ("i", it.id)

        # ---- tamamlananlar ----
        completed: list[WorkLine] = []
        done_keys: set[Key] = set()
        for card in await self.uow.analytics.completed_cards(user_id, start, end):
            if not ok(card.board_id):
                continue
            key = ("c", card.id)
            done_keys.add(key)
            completed.append(WorkLine(title=card.title, minutes=minutes(key)))
        for it in items:
            if it.outcome != ItemOutcome.DONE or not ok(it.board_id):
                continue
            key = item_key(it)
            if key in done_keys:
                continue
            done_keys.add(key)
            completed.append(
                WorkLine(title=it.title, minutes=minutes(key, it.tracked_sec))
            )

        # ---- üzerinde çalışılanlar (oturumlu ya da kısmen yapılmış) ----
        worked_map: dict[Key, WorkLine] = {}
        for key, sec in seconds.items():
            if key in done_keys or not ok(boards_of.get(key)):
                continue
            worked_map[key] = WorkLine(title=titles[key], minutes=minutes(key))
        for it in items:
            if it.outcome != ItemOutcome.PARTIAL or not ok(it.board_id):
                continue
            key = item_key(it)
            if key in done_keys or key in worked_map:
                continue
            worked_map[key] = WorkLine(
                title=it.title, minutes=minutes(key, it.tracked_sec)
            )
        worked = sorted(worked_map.values(), key=lambda w: (-w.minutes, w.title))

        # ---- yapılamayanlar ----
        not_done = [
            NotDoneLine(
                title=it.title,
                reason=it.reason or None,
                postponed_to=it.postponed_to
                if it.outcome == ItemOutcome.POSTPONED
                else None,
            )
            for it in items
            if it.outcome in (ItemOutcome.NOT_DONE, ItemOutcome.POSTPONED)
            and ok(it.board_id)
        ]

        tomorrow = [TomorrowLine(title=it.title) for it in next_items if ok(it.board_id)]

        sections = WorkSections(
            completed=completed, worked=worked, not_done=not_done, tomorrow=tomorrow
        )
        return WorkSummary(date=day, sections=sections, text=render_text(day, sections))
