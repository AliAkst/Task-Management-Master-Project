"""
Gunluk planlama ve gun sonu degerlendirmesi.

Akis:
1. Planlama (sabah ya da onceki aksam): oneriler (takvim bloklari, ertelenenler,
   son tarihi gelen/gecmis kartlar, devam edenler) -> secilen maddeler kaydedilir.
2. Degerlendirme (aksam): her madde done/partial/not_done/postponed; o gun
   harcanan sure snapshot'lanir; plansiz yapilan isler eklenir.
   - done -> kart tamamlanir (kanban senkron, bagimlilar acilir)
   - postponed -> ertesi gunun onerilerine duser, kart gecmisine 'postponed'
   - not_done -> kart gecmisine 'skipped'
Bu veri, istatistiklerin ve AI'in "planladigin vs yaptigin" analizinin temelidir.
"""

from datetime import UTC, date, datetime, time, timedelta

from app.core.events import domain_event_publisher
from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.db.entities import EventEntity, TaskEntity
from app.db.entities.day_plan import (
    DayPlanEntity,
    DayPlanItemEntity,
    DayPlanStatus,
    ItemOutcome,
)
from app.db.unit_of_work import TaskUnitOfWork
from app.models.card import CardCreate, CardUpdate
from app.models.day_plan import (
    AiSummaryInput,
    DayPlanItemPatch,
    DayPlanItemResponse,
    DayPlanResponse,
    DayPlanSave,
    DayReview,
    DaySuggestions,
    ItemMove,
    ItemToCard,
    PlanItemInput,
    PlanSuggestion,
)
from app.models.task import TaskStatus
from app.services.activity import ActivityLogger
from app.services.ordering import STEP
from app.services.recurrence import events_in_range, occurrences
from app.services.timeutil import day_bounds, local_today, session_span, user_tz

OUTCOME_ACTION = {
    ItemOutcome.DONE: "completed",
    ItemOutcome.POSTPONED: "postponed",
    ItemOutcome.NOT_DONE: "skipped",
    ItemOutcome.PARTIAL: "partially_done",
}


UNBLOCK_WINDOW = timedelta(days=14)


def _now() -> datetime:
    return datetime.now(UTC)


class DayPlanService:
    def __init__(self, uow: TaskUnitOfWork, actor: str = "user"):
        self.uow = uow
        self.actor = actor
        self.activity = ActivityLogger(uow, actor)

    # ---------------- yardimcilar ----------------
    async def _tracked_for_day(
        self, user_id: int, start: datetime, end: datetime
    ) -> tuple[dict[int | None, int], dict[int, tuple[str | None, int | None]]]:
        """O gun karta harcanan saniyeler + oturum snapshot'lari (baslik, board)."""
        sessions = await self.uow.time_sessions.list_for_user(
            user_id, start, end, limit=1000
        )
        totals: dict[int | None, int] = {}
        meta: dict[int, tuple[str | None, int | None]] = {}
        now = _now()
        for s in sessions:
            span = session_span(s, start, end, now)
            if span is None:
                continue
            totals[s.card_id] = totals.get(s.card_id, 0) + int(
                (span[1] - span[0]).total_seconds()
            )
            if s.card_id is not None:
                meta[s.card_id] = (s.card_title, s.board_id)
        return totals, meta

    async def _owned_card(self, card_id: int, user_id: int) -> TaskEntity:
        card = await self.uow.tasks.get_owned(card_id, user_id)
        if card is None:
            raise NotFoundException("Card", card_id)
        return card

    async def _owned_event(self, event_id: int, user_id: int) -> EventEntity:
        event = await self.uow.events.get_owned(event_id, user_id)
        if event is None:
            raise NotFoundException("Event", event_id)
        return event

    async def _response(
        self, user_id: int, day: date, plan: DayPlanEntity | None
    ) -> DayPlanResponse:
        tz = await user_tz(self.uow, user_id)
        start, end = day_bounds(day, tz)
        tracked, _ = await self._tracked_for_day(user_id, start, end)
        total_today = sum(tracked.values())
        if plan is None:
            return DayPlanResponse(
                date=day, exists=False, tracked_today_sec=total_today
            )

        items = await self.uow.day_plan_items.for_plans([plan.id])
        cards = {
            c.id: c
            for c in await self.uow.tasks.get_many(
                [i.card_id for i in items if i.card_id is not None]
            )
        }
        return DayPlanResponse(
            date=day,
            exists=True,
            status=plan.status,
            mood=plan.mood,
            energy=plan.energy,
            reflection=plan.reflection,
            planned_at=plan.planned_at,
            reviewed_at=plan.reviewed_at,
            ai_summary=plan.ai_summary,
            tracked_today_sec=total_today,
            items=[
                DayPlanItemResponse.model_validate(i).model_copy(
                    update={
                        "card_status": cards[i.card_id].status
                        if i.card_id in cards
                        else None,
                        "tracked_today_sec": tracked.get(i.card_id, 0)
                        if i.card_id is not None
                        else 0,
                    }
                )
                for i in items
            ],
        )

    async def _get_or_create(self, user_id: int, day: date) -> DayPlanEntity:
        plan = await self.uow.day_plans.for_date(user_id, day)
        if plan is None:
            plan = DayPlanEntity(
                user_id=user_id, date=day, status=DayPlanStatus.PLANNED
            )
            await self.uow.day_plans.create(plan)
            await self.uow.flush()
        return plan

    # ---------------- okuma ----------------
    async def get(self, user_id: int, day: date) -> DayPlanResponse:
        plan = await self.uow.day_plans.for_date(user_id, day)
        return await self._response(user_id, day, plan)

    async def suggestions(self, user_id: int, day: date) -> DaySuggestions:
        tz = await user_tz(self.uow, user_id)
        start, end = day_bounds(day, tz)
        is_past_or_today = day <= local_today(tz)

        plan = await self.uow.day_plans.for_date(user_id, day)
        planned_items = (
            await self.uow.day_plan_items.for_plans([plan.id]) if plan else []
        )
        planned_cards = {i.card_id for i in planned_items if i.card_id is not None}
        planned_events = {i.event_id for i in planned_items if i.event_id is not None}
        planned_titles = {
            i.title.strip().casefold()
            for i in planned_items
            if i.was_planned and i.card_id is None and i.event_id is None
        }

        result: list[PlanSuggestion] = []
        seen_cards: set[int] = set()

        def add(s: PlanSuggestion) -> None:
            if s.card_id is not None:
                if s.card_id in seen_cards:
                    return
                seen_cards.add(s.card_id)
            s.already_planned = (
                (s.card_id in planned_cards)
                or (s.event_id is not None and s.event_id in planned_events)
                or (
                    s.card_id is None
                    and s.event_id is None
                    and s.title.strip().casefold() in planned_titles
                )
            )
            result.append(s)

        # 1) O gunun takvim bloklari / etkinlikleri
        events = await events_in_range(self.uow, user_id, start, end, tz)
        event_cards = {
            c.id: c
            for c in await self.uow.tasks.get_many(
                [e.card_id for e, _, _ in events if e.card_id is not None]
            )
        }
        for e, occ_start, occ_end in events:
            card = event_cards.get(e.card_id) if e.card_id is not None else None
            if card is not None and card.status == TaskStatus.COMPLETED:
                continue
            add(
                PlanSuggestion(
                    kind="event",
                    card_id=e.card_id,
                    event_id=e.id,
                    title=e.title,
                    board_id=card.board_id if card else e.board_id,
                    planned_start=None if e.all_day else occ_start,
                    planned_minutes=None
                    if e.all_day
                    else int((occ_end - occ_start).total_seconds() // 60),
                )
            )

        # 2) Bu gune ertelenenler
        carried = await self.uow.day_plan_items.carried_to(user_id, day)
        carried_cards = {
            c.id: c
            for c in await self.uow.tasks.get_many(
                [i.card_id for i in carried if i.card_id is not None]
            )
        }
        for i in carried:
            card = carried_cards.get(i.card_id) if i.card_id is not None else None
            if card is not None and (
                card.status == TaskStatus.COMPLETED or card.is_archived
            ):
                continue
            add(
                PlanSuggestion(
                    kind="carry_over",
                    card_id=i.card_id,
                    title=card.title if card else i.title,
                    board_id=card.board_id if card else i.board_id,
                    planned_minutes=i.planned_minutes,
                )
            )

        # 3) Son tarihi bu gun olan / (bugun icin) gecmis kartlar, 4) devam edenler
        cards = await self.uow.tasks.get_all_by_users(user_id)
        open_cards = [
            c
            for c in cards
            if not c.is_archived
            and c.status != TaskStatus.COMPLETED
            and not any(ch.parent_id == c.id for ch in cards)  # parcalanmis ana kart
        ]
        blocked = await self._blocked_ids([c.id for c in open_cards])
        recently_unblocked = await self._recently_unblocked(
            [c.id for c in open_cards if c.id not in blocked], start
        )
        for c in sorted(open_cards, key=lambda c: c.due_date or end):
            if c.due_date is not None and start <= c.due_date < end:
                kind = "due"
            elif c.due_date is not None and c.due_date < start and is_past_or_today:
                kind = "overdue"
            elif c.status == TaskStatus.IN_PROGRESS:
                kind = "in_progress"
            elif c.id in recently_unblocked:
                kind = "next_in_chain"  # zincirde onceki is bitti, sira bunda
            else:
                continue
            add(
                PlanSuggestion(
                    kind=kind,
                    card_id=c.id,
                    title=c.title,
                    board_id=c.board_id,
                    planned_minutes=c.estimated_minutes,
                    due_date=c.due_date,
                    blocked=c.id in blocked,
                )
            )

        # 5) O gun uzerinde calisilan kartlar (degerlendirmede "plansiz is")
        tracked, meta = await self._tracked_for_day(user_id, start, end)
        worked_cards = {
            c.id: c
            for c in await self.uow.tasks.get_many(
                [cid for cid in tracked if cid is not None]
            )
        }
        for card_id, sec in tracked.items():
            if card_id is None:
                continue
            card = worked_cards.get(card_id)
            title, board_id = meta.get(card_id, (None, None))
            add(
                PlanSuggestion(
                    kind="worked",
                    card_id=card_id,
                    title=card.title if card else (title or "Silinmiş kart"),
                    board_id=card.board_id if card else board_id,
                    planned_minutes=card.estimated_minutes if card else None,
                )
            )
        for s in result:
            if s.card_id is not None:
                s.tracked_sec = tracked.get(s.card_id, 0)
        return DaySuggestions(date=day, items=result)

    async def _recently_unblocked(
        self, card_ids: list[int], start: datetime
    ) -> set[int]:
        """
        On kosullarinin hepsi bitmis ve sonuncusu son UNBLOCK_WINDOW icinde
        bitmis kartlar: zincirde "siradaki" is (orn. 9 parcalik egitimin 2. parcasi).
        """
        edges = [
            (c, d)
            for c, d in await self.uow.dependencies.edges_touching(card_ids)
            if c in card_ids
        ]
        if not edges:
            return set()
        prereqs = {
            t.id: t for t in await self.uow.tasks.get_many(list({d for _, d in edges}))
        }
        latest: dict[int, datetime] = {}
        for c, d in edges:
            p = prereqs.get(d)
            if p is None or p.completed_at is None:
                continue
            if c not in latest or p.completed_at > latest[c]:
                latest[c] = p.completed_at
        return {c for c, t in latest.items() if t >= start - UNBLOCK_WINDOW}

    async def _blocked_ids(self, card_ids: list[int]) -> set[int]:
        edges = await self.uow.dependencies.edges_touching(card_ids)
        prereqs = {
            t.id: t.status
            for t in await self.uow.tasks.get_many(list({d for _, d in edges}))
        }
        return {
            c
            for c, d in edges
            if c in card_ids
            and prereqs.get(d, TaskStatus.COMPLETED) != TaskStatus.COMPLETED
        }

    # ---------------- planlama ----------------
    @staticmethod
    def _event_start(event, bounds, tz) -> datetime | None:
        """Etkinligin plandaki saati (tekrarlayanda o gunku tekrar)."""
        if event is None or event.all_day:
            return None
        planned_start = event.start_at
        if event.recurrence_rule:
            occ = occurrences(
                event.recurrence_rule,
                event.start_at,
                event.end_at - event.start_at,
                bounds,
                tz,
            )
            planned_start = occ[0][0] if occ else None
        return planned_start

    @staticmethod
    def _event_minutes(event) -> int | None:
        if event is None or event.all_day:
            return None
        return int((event.end_at - event.start_at).total_seconds() // 60)

    @staticmethod
    def _check_start(value: datetime | None, bounds, tz) -> datetime | None:
        """planned_start planin gunu icinde olmali (naive -> kullanici dilimi)."""
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        if not (bounds[0] <= value < bounds[1]):
            raise ValidationException("planned_start planın günü içinde olmalı")
        return value

    def _fill_item(
        self, item: DayPlanItemEntity, it, card, event, bounds, tz, start
    ) -> None:
        """Yeni plan maddesinin baslik/board/dakika/saat alanlari (tek yer)."""
        minutes = it.planned_minutes
        if minutes is None:
            minutes = self._event_minutes(event)
        if minutes is None and card is not None:
            minutes = card.estimated_minutes
        title = it.title or (card.title if card else None)
        if title is None and event is not None:
            title = event.title
        item.card_id = card.id if card else None
        item.event_id = event.id if event else None
        item.title = (title or "")[:200]
        item.board_id = card.board_id if card else (event.board_id if event else None)
        item.was_planned = True
        item.planned_minutes = minutes
        item.planned_start = (
            self._event_start(event, bounds, tz) if event is not None else start
        )

    async def save_plan(
        self, user_id: int, day: date, data: DayPlanSave
    ) -> DayPlanResponse:
        tz = await user_tz(self.uow, user_id)
        bounds = day_bounds(day, tz)
        plan = await self.uow.day_plans.for_date(user_id, day)
        existing = await self.uow.day_plan_items.for_plans([plan.id]) if plan else []
        planned_rows = [i for i in existing if i.was_planned]
        by_id = {i.id: i for i in planned_rows}

        async def resolve(it):
            card = await self._owned_card(it.card_id, user_id) if it.card_id else None
            event = (
                await self._owned_event(it.event_id, user_id) if it.event_id else None
            )
            if card is None and event is not None and event.card_id is not None:
                card = await self.uow.tasks.get_by_id(event.card_id)
            start = (
                self._check_start(it.planned_start, bounds, tz)
                if event is None
                else None
            )
            return card, event, start

        # 1) Once tumunu dogrula (sahiplik, 404, planned_start); sonra yaz
        resolved: list[tuple] = []  # (id ile bulunan satir | None, kart, etkinlik, saat)
        for it in data.items:
            row = by_id.get(it.id) if it.id is not None else None
            if row is not None:
                start = (
                    self._check_start(it.planned_start, bounds, tz)
                    if row.event_id is None and "planned_start" in it.model_fields_set
                    else None
                )
                resolved.append((row, None, None, start))
                continue
            if it.id is not None and (
                it.card_id is None and it.event_id is None and not it.title
            ):
                raise NotFoundException("DayPlanItem", it.id)
            resolved.append((None, *await resolve(it)))

        plan = await self._get_or_create(user_id, day)
        if plan.status == DayPlanStatus.REVIEWED:
            raise ConflictException(
                "PLAN_ALREADY_REVIEWED",
                "Bu gün değerlendirildi; planı değil değerlendirmeyi güncelle",
            )
        previously_planned = {i.card_id for i in existing if i.card_id is not None}

        # 2) Esle / guncelle / olustur
        used: set[int] = set()
        row_by_card: dict[int, DayPlanItemEntity] = {}
        row_by_event: dict[int, DayPlanItemEntity] = {}
        newly_planned: list[TaskEntity] = []
        position_idx = 0

        def register(row: DayPlanItemEntity) -> None:
            if row.card_id is not None:
                row_by_card[row.card_id] = row
            if row.event_id is not None:
                row_by_event[row.event_id] = row

        def find_unused(pred) -> DayPlanItemEntity | None:
            return next((r for r in planned_rows if r.id not in used and pred(r)), None)

        for it, (id_row, card, event, start) in zip(data.items, resolved, strict=True):
            row = id_row if id_row is not None and id_row.id not in used else None
            if row is None and id_row is not None:
                # ayni id ikinci kez: id'siz girdi gibi (referans yoksa yok sayilir)
                if it.card_id is None and it.event_id is None and not it.title:
                    continue
                card, event, start = await resolve(it)

            attach_event = None
            if row is None:
                # K-S6: bu istekte islenmis kart/etkinlik tekrar gelirse yeni satir yok
                dup = (event and row_by_event.get(event.id)) or (
                    card and row_by_card.get(card.id)
                )
                if dup:
                    if event is not None and dup.event_id is None:
                        dup.event_id = event.id
                        dup.planned_start = self._event_start(event, bounds, tz)
                        if dup.planned_minutes is None:
                            dup.planned_minutes = self._event_minutes(event)
                        row_by_event[event.id] = dup
                    continue
                if event is not None:
                    row = find_unused(lambda r: r.event_id == event.id)
                    if row is None and card is not None:
                        row = find_unused(
                            lambda r: r.card_id == card.id and r.event_id is None
                        )
                        attach_event = event if row is not None else None
                elif card is not None:
                    row = find_unused(lambda r: r.card_id == card.id)
                else:
                    key = (it.title or "").strip().casefold()
                    row = find_unused(
                        lambda r: r.card_id is None
                        and r.event_id is None
                        and r.title.strip().casefold() == key
                    )

            position_idx += 1
            if row is None:
                row = DayPlanItemEntity(
                    user_id=user_id,
                    day_plan_id=plan.id,
                    position=position_idx * STEP,
                )
                self._fill_item(row, it, card, event, bounds, tz, start)
                await self.uow.day_plan_items.create(row)
                if card is not None and card.id not in previously_planned:
                    newly_planned.append(card)
                    previously_planned.add(card.id)
                register(row)
                continue

            used.add(row.id)
            row.position = position_idx * STEP
            if attach_event is not None:
                row.event_id = attach_event.id
                row.planned_start = self._event_start(attach_event, bounds, tz)
                if row.planned_minutes is None:
                    row.planned_minutes = self._event_minutes(attach_event)
            if "planned_minutes" in it.model_fields_set:
                minutes = it.planned_minutes
                if minutes is None:
                    ev = (
                        await self.uow.events.get_by_id(row.event_id)
                        if row.event_id
                        else None
                    )
                    minutes = self._event_minutes(ev)
                    if minutes is None and row.card_id is not None:
                        c = await self.uow.tasks.get_by_id(row.card_id)
                        minutes = c.estimated_minutes if c else None
                row.planned_minutes = minutes
            if row.card_id is None and row.event_id is None and it.title:
                row.title = it.title[:200]
            if row.event_id is None and "planned_start" in it.model_fields_set:
                row.planned_start = start
            register(row)

        # 3) Hicbir girdiyle eslesmeyen planli satirlari sil
        for r in planned_rows:
            if r.id not in used:
                await self.uow.day_plan_items.delete(r)

        for card in newly_planned:
            await self.activity.log(
                user_id,
                "card",
                card.id,
                "planned",
                board_id=card.board_id,
                card_id=card.id,
                changes={"date": day.isoformat()},
            )
        plan.planned_at = _now()
        await self.uow.commit()
        await domain_event_publisher.publish(
            "plan.saved",
            {"user_id": user_id, "date": day.isoformat(), "items": len(data.items)},
        )
        return await self.get(user_id, day)

    async def add_event_item(self, user_id: int, event: EventEntity) -> bool:
        """Takvimde olusturulan etkinligi etkinligin gununun planina ekler (12d)."""
        tz = await user_tz(self.uow, user_id)
        day = event.start_at.astimezone(tz).date()
        bounds = day_bounds(day, tz)
        plan = await self.uow.day_plans.for_date(user_id, day)
        if plan is not None and plan.status == DayPlanStatus.REVIEWED:
            return False
        existing = await self.uow.day_plan_items.for_plans([plan.id]) if plan else []
        planned = [i for i in existing if i.was_planned]
        if any(i.event_id == event.id for i in planned):
            return False
        card = (
            await self.uow.tasks.get_by_id(event.card_id)
            if event.card_id is not None
            else None
        )
        if card is not None:
            row = next(
                (i for i in planned if i.card_id == card.id and i.event_id is None),
                None,
            )
            if row is not None:
                row.event_id = event.id
                row.planned_start = self._event_start(event, bounds, tz)
                if row.planned_minutes is None:
                    row.planned_minutes = self._event_minutes(event)
                await self.uow.commit()
                return True

        plan = await self._get_or_create(user_id, day)
        row = DayPlanItemEntity(
            user_id=user_id,
            day_plan_id=plan.id,
            position=max((i.position for i in existing), default=0) + STEP,
        )
        self._fill_item(
            row, PlanItemInput(event_id=event.id), card, event, bounds, tz, None
        )
        await self.uow.day_plan_items.create(row)
        if card is not None and not any(i.card_id == card.id for i in existing):
            await self.activity.log(
                user_id,
                "card",
                card.id,
                "planned",
                board_id=card.board_id,
                card_id=card.id,
                changes={"date": day.isoformat(), "via": "calendar"},
            )
        await self.uow.commit()
        return True

    async def refresh_event_items(self, user_id: int, event: EventEntity) -> None:
        """Etkinlik tasininca bagli plan maddelerinin saat/sure snapshot'i (commit'siz)."""
        rows = await self.uow.day_plan_items.for_event(event.id)
        if not rows:
            return
        tz = await user_tz(self.uow, user_id)
        new_day = event.start_at.astimezone(tz).date()
        for row in rows:
            if not row.was_planned:
                continue
            plan = await self.uow.day_plans.get_by_id(row.day_plan_id)
            if plan is None or plan.status == DayPlanStatus.REVIEWED:
                continue
            if plan.date == new_day:
                row.planned_start = None if event.all_day else event.start_at
                row.planned_minutes = self._event_minutes(event)
            else:
                row.planned_start = None

    async def patch_item(
        self, item_id: int, user_id: int, data: DayPlanItemPatch
    ) -> DayPlanResponse:
        from app.services.card import CardService

        item = await self.uow.day_plan_items.get_owned(item_id, user_id)
        if item is None:
            raise NotFoundException("DayPlanItem", item_id)
        plan = await self.uow.day_plans.get_by_id(item.day_plan_id)
        fields = data.model_fields_set
        if plan.status == DayPlanStatus.REVIEWED and fields - {"done"}:
            raise ConflictException(
                "PLAN_ALREADY_REVIEWED",
                "Bu gün değerlendirildi; yalnız tamamlandı işareti değiştirilebilir",
            )
        tz = await user_tz(self.uow, user_id)
        bounds = day_bounds(plan.date, tz)
        new_title = data.title if "title" in fields else None
        if new_title is not None and item.card_id is not None:
            raise ValidationException("Kartlı maddenin başlığı karttan gelir")
        if "planned_start" in fields and item.event_id is not None:
            raise ValidationException("Saat takvim etkinliğinden gelir")
        start = self._check_start(data.planned_start, bounds, tz)

        if new_title is not None:
            item.title = new_title.strip()[:200]
        if "planned_minutes" in fields:
            item.planned_minutes = data.planned_minutes
        if "planned_start" in fields:
            item.planned_start = start

        card = (
            await self.uow.tasks.get_by_id(item.card_id)
            if item.card_id is not None
            else None
        )
        new_status = None
        if data.done is True:
            item.outcome = ItemOutcome.DONE
            item.postponed_to = None
            if card is not None and card.status != TaskStatus.COMPLETED:
                new_status = TaskStatus.COMPLETED
        elif data.done is False:
            item.outcome = None
            item.reason = None
            item.postponed_to = None
            if card is not None and card.status == TaskStatus.COMPLETED:
                new_status = TaskStatus.PENDING
        if new_status is not None:
            # CardService.update durum degisimini gecmise yazmiyor; istatistik icin
            # burada yazilir (ayni transaction'da, update commit eder)
            await self.activity.log(
                user_id,
                "card",
                card.id,
                "completed" if new_status == TaskStatus.COMPLETED else "reopened",
                board_id=card.board_id,
                card_id=card.id,
                changes={"date": plan.date.isoformat(), "via": "day_plan"},
            )
            await CardService(self.uow, self.actor).update(
                card.id, user_id, CardUpdate(status=new_status)
            )
        else:
            await self.uow.commit()
        return await self.get(user_id, plan.date)

    async def item_to_card(
        self, item_id: int, user_id: int, data: ItemToCard
    ) -> DayPlanResponse:
        from app.services.board import BoardService
        from app.services.card import CardService
        from app.services.event import EventService

        item = await self.uow.day_plan_items.get_owned(item_id, user_id)
        if item is None:
            raise NotFoundException("DayPlanItem", item_id)
        if item.card_id is not None:
            raise ConflictException("ITEM_HAS_CARD", "Bu madde zaten bir karta bağlı")
        plan = await self.uow.day_plans.get_by_id(item.day_plan_id)

        list_id = data.list_id
        if list_id is None:
            board_id = data.board_id if data.board_id is not None else item.board_id
            if board_id is None:
                raise ValidationException("board_id ya da list_id gerekli")
            await BoardService(self.uow).get_owned_board(board_id, user_id)
            lists = await self.uow.lists.list_for_board(board_id)
            open_lists = [lst for lst in lists if not lst.is_done_list]
            if not open_lists:
                raise ValidationException("Board'da açık liste yok")
            list_id = open_lists[0].id

        tz = await user_tz(self.uow, user_id)
        card = await CardService(self.uow, self.actor).create(
            user_id,
            CardCreate(
                list_id=list_id,
                title=item.title,
                due_date=datetime.combine(plan.date, time(23, 59), tzinfo=tz),
                estimated_minutes=item.planned_minutes,
            ),
        )
        item.card_id = card.id
        item.board_id = card.board_id

        if item.event_id is not None:
            event = await self.uow.events.get_by_id(item.event_id)
            if event is not None:
                try:
                    await EventService(self.uow, self.actor)._assert_editable(event)
                except ConflictException:
                    pass  # dis takvim etkinligi baglanmaz
                else:
                    event.card_id = card.id
                    event.board_id = card.board_id
        await self.activity.log(
            user_id,
            "card",
            card.id,
            "planned",
            board_id=card.board_id,
            card_id=card.id,
            changes={"date": plan.date.isoformat(), "via": "to_card"},
        )
        if item.outcome == ItemOutcome.DONE:
            await CardService(self.uow, self.actor).update(
                card.id, user_id, CardUpdate(status=TaskStatus.COMPLETED)
            )
        else:
            await self.uow.commit()
        return await self.get(user_id, plan.date)

    async def move_item(
        self, item_id: int, user_id: int, data: ItemMove
    ) -> DayPlanResponse:
        item = await self.uow.day_plan_items.get_owned(item_id, user_id)
        if item is None:
            raise NotFoundException("DayPlanItem", item_id)
        if not item.was_planned:
            raise ValidationException("Yalnız planlanmış madde taşınabilir")
        if item.outcome == ItemOutcome.DONE:
            raise ValidationException("Tamamlanmış madde taşınamaz")
        source = await self.uow.day_plans.get_by_id(item.day_plan_id)
        if source.status == DayPlanStatus.REVIEWED:
            raise ConflictException(
                "PLAN_ALREADY_REVIEWED",
                "Bu gün değerlendirildi; değerlendirmede ertele seçeneğini kullan",
            )
        tz = await user_tz(self.uow, user_id)
        target = data.date or source.date + timedelta(days=1)
        if target == source.date:
            raise ValidationException("Hedef gün aynı")
        if target < local_today(tz):
            raise ValidationException("Geçmiş bir güne taşınamaz")
        target_plan = await self.uow.day_plans.for_date(user_id, target)
        if target_plan is not None and target_plan.status == DayPlanStatus.REVIEWED:
            raise ConflictException(
                "PLAN_ALREADY_REVIEWED", "Hedef gün değerlendirilmiş"
            )
        target_plan = await self._get_or_create(user_id, target)
        rows = [
            i
            for i in await self.uow.day_plan_items.for_plans([target_plan.id])
            if i.was_planned
        ]
        key = item.title.strip().casefold()
        duplicate = any(
            (item.card_id is not None and r.card_id == item.card_id)
            or (
                item.card_id is None
                and r.card_id is None
                and r.event_id is None
                and r.title.strip().casefold() == key
            )
            for r in rows
        )
        if not duplicate:
            await self.uow.day_plan_items.create(
                DayPlanItemEntity(
                    user_id=user_id,
                    day_plan_id=target_plan.id,
                    card_id=item.card_id,
                    event_id=None,
                    title=item.title,
                    board_id=item.board_id,
                    was_planned=True,
                    planned_start=None,
                    planned_minutes=item.planned_minutes,
                    position=max((r.position for r in rows), default=0.0) + STEP,
                )
            )
        if item.card_id is not None:
            card = await self.uow.tasks.get_by_id(item.card_id)
            if card is not None:
                await self.activity.log(
                    user_id,
                    "card",
                    card.id,
                    "planned",
                    board_id=card.board_id,
                    card_id=card.id,
                    changes={
                        "date": target.isoformat(),
                        "moved_from": source.date.isoformat(),
                    },
                )
        source_day = source.date
        await self.uow.day_plan_items.delete(item)
        await self.uow.commit()
        return await self.get(user_id, source_day)

    async def delete_item(self, item_id: int, user_id: int) -> None:
        item = await self.uow.day_plan_items.get_owned(item_id, user_id)
        if item is None:
            raise NotFoundException("DayPlanItem", item_id)
        await self.uow.day_plan_items.delete(item)
        await self.uow.commit()

    async def set_ai_summary(
        self, user_id: int, day: date, data: AiSummaryInput
    ) -> DayPlanResponse:
        """Asistanin gun ozeti. Plan maddelerine dokunmaz; degerlendirilmis
        gunde de yazilabilir (ozet zaten degerlendirmeden sonra uretilir)."""
        plan = await self._get_or_create(user_id, day)
        text = (data.ai_summary or "").strip()
        plan.ai_summary = text or None
        await self.uow.commit()
        return await self.get(user_id, day)

    # ---------------- degerlendirme ----------------
    async def review(self, user_id: int, day: date, data: DayReview) -> DayPlanResponse:
        from app.services.card import CardService

        cards_svc = CardService(self.uow, self.actor)
        tz = await user_tz(self.uow, user_id)
        start, end = day_bounds(day, tz)
        tracked, _ = await self._tracked_for_day(user_id, start, end)

        # Once dogrula, sonra yaz: gecersiz istek yan etki birakmasin
        plan = await self.uow.day_plans.for_date(user_id, day)
        items = (
            {i.id: i for i in await self.uow.day_plan_items.for_plans([plan.id])}
            if plan
            else {}
        )
        for r in data.items:
            if r.id not in items:
                raise NotFoundException("DayPlanItem", r.id)
        for u in data.unplanned:
            if u.card_id is not None:
                await self._owned_card(u.card_id, user_id)
        plan = plan or await self._get_or_create(user_id, day)
        # Gecmis bir gun degerlendiriliyorsa tamamlanma o gune yazilir
        completed_at = min(_now(), end - timedelta(seconds=1))
        completed: list[TaskEntity] = []

        async def apply(item: DayPlanItemEntity, outcome: ItemOutcome, reason, to):
            previous = item.outcome
            item.outcome = outcome
            item.reason = reason
            item.postponed_to = (
                (to or day + timedelta(days=1))
                if outcome == ItemOutcome.POSTPONED
                else None
            )
            if item.card_id is not None:
                item.tracked_sec = tracked.get(item.card_id, 0)
            if previous == outcome or item.card_id is None:
                return  # tekrar degerlendirmede yan etkiler bir kez
            card = await self.uow.tasks.get_by_id(item.card_id)
            if card is None:
                return
            if outcome == ItemOutcome.DONE and card.status != TaskStatus.COMPLETED:
                await cards_svc._apply_status(card, TaskStatus.COMPLETED)
                card.completed_at = completed_at
                completed.append(card)
            changes: dict = {"date": day.isoformat(), "via": "day_review"}
            if reason:
                changes["reason"] = reason
            if item.postponed_to:
                changes["postponed_to"] = item.postponed_to.isoformat()
            await self.activity.log(
                user_id,
                "card",
                card.id,
                OUTCOME_ACTION[outcome],
                board_id=card.board_id,
                card_id=card.id,
                changes=changes,
            )

        for r in data.items:
            await apply(items[r.id], r.outcome, r.reason, r.postponed_to)

        existing_cards = {i.card_id for i in items.values() if i.card_id is not None}
        position = max((i.position for i in items.values()), default=0.0)
        for u in data.unplanned:
            card = await self._owned_card(u.card_id, user_id) if u.card_id else None
            if card is not None and card.id in existing_cards:
                continue  # zaten planda
            position += STEP
            item = DayPlanItemEntity(
                user_id=user_id,
                day_plan_id=plan.id,
                card_id=card.id if card else None,
                title=(u.title or card.title)[:200],  # type: ignore[union-attr]
                board_id=card.board_id if card else None,
                was_planned=False,
                planned_minutes=card.estimated_minutes if card else None,
                position=position,
            )
            await self.uow.day_plan_items.create(item)
            await apply(item, u.outcome, u.reason, None)

        plan.status = DayPlanStatus.REVIEWED
        plan.reviewed_at = _now()
        for key in ("mood", "energy", "reflection"):
            if key in data.model_fields_set:
                setattr(plan, key, getattr(data, key))
        await self.uow.commit()

        # Commit sonrasi: kanban/eski API cache'i, card.completed + unblock
        for card in completed:
            await cards_svc._after_change(user_id, "card.completed", card)
        await domain_event_publisher.publish(
            "review.submitted",
            {"user_id": user_id, "date": day.isoformat(), "plan_id": plan.id},
        )
        return await self.get(user_id, day)
