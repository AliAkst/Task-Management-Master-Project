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

from datetime import UTC, date, datetime, timedelta

from app.core.events import domain_event_publisher
from app.core.exceptions import ConflictException, NotFoundException
from app.db.entities import EventEntity, TaskEntity
from app.db.entities.day_plan import (
    DayPlanEntity,
    DayPlanItemEntity,
    DayPlanStatus,
    ItemOutcome,
)
from app.db.unit_of_work import TaskUnitOfWork
from app.models.day_plan import (
    AiSummaryInput,
    DayPlanItemResponse,
    DayPlanResponse,
    DayPlanSave,
    DayReview,
    DaySuggestions,
    PlanSuggestion,
)
from app.models.task import TaskStatus
from app.services.activity import ActivityLogger
from app.services.ordering import STEP
from app.services.timeutil import day_bounds, local_today, session_span, user_tz

OUTCOME_ACTION = {
    ItemOutcome.DONE: "completed",
    ItemOutcome.POSTPONED: "postponed",
    ItemOutcome.NOT_DONE: "skipped",
    ItemOutcome.PARTIAL: "partially_done",
}


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

        result: list[PlanSuggestion] = []
        seen_cards: set[int] = set()

        def add(s: PlanSuggestion) -> None:
            if s.card_id is not None:
                if s.card_id in seen_cards:
                    return
                seen_cards.add(s.card_id)
            s.already_planned = (s.card_id in planned_cards) or (
                s.event_id is not None and s.event_id in planned_events
            )
            result.append(s)

        # 1) O gunun takvim bloklari / etkinlikleri
        events = await self.uow.events.in_range(user_id, start, end)
        event_cards = {
            c.id: c
            for c in await self.uow.tasks.get_many(
                [e.card_id for e in events if e.card_id is not None]
            )
        }
        for e in events:
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
                    planned_start=None if e.all_day else e.start_at,
                    planned_minutes=None
                    if e.all_day
                    else int((e.end_at - e.start_at).total_seconds() // 60),
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
        for c in sorted(open_cards, key=lambda c: c.due_date or end):
            if c.due_date is not None and start <= c.due_date < end:
                kind = "due"
            elif c.due_date is not None and c.due_date < start and is_past_or_today:
                kind = "overdue"
            elif c.status == TaskStatus.IN_PROGRESS:
                kind = "in_progress"
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
    async def save_plan(
        self, user_id: int, day: date, data: DayPlanSave
    ) -> DayPlanResponse:
        # Once dogrula (sahiplik), sonra yaz: gecersiz istek yan etki birakmasin
        resolved: list[tuple[TaskEntity | None, EventEntity | None]] = []
        for it in data.items:
            card = await self._owned_card(it.card_id, user_id) if it.card_id else None
            event = (
                await self._owned_event(it.event_id, user_id) if it.event_id else None
            )
            if card is None and event is not None and event.card_id is not None:
                card = await self.uow.tasks.get_by_id(event.card_id)
            resolved.append((card, event))

        plan = await self._get_or_create(user_id, day)
        if plan.status == DayPlanStatus.REVIEWED:
            raise ConflictException(
                "PLAN_ALREADY_REVIEWED",
                "Bu gün değerlendirildi; planı değil değerlendirmeyi güncelle",
            )
        existing = await self.uow.day_plan_items.for_plans([plan.id])
        previously_planned = {i.card_id for i in existing if i.card_id is not None}
        for item in existing:
            if item.was_planned:
                await self.uow.day_plan_items.delete(item)

        newly_planned: list[TaskEntity] = []
        for idx, (it, (card, event)) in enumerate(
            zip(data.items, resolved, strict=True), start=1
        ):
            minutes = it.planned_minutes
            if minutes is None and event is not None and not event.all_day:
                minutes = int((event.end_at - event.start_at).total_seconds() // 60)
            if minutes is None and card is not None:
                minutes = card.estimated_minutes

            await self.uow.day_plan_items.create(
                DayPlanItemEntity(
                    user_id=user_id,
                    day_plan_id=plan.id,
                    card_id=card.id if card else None,
                    event_id=event.id if event else None,
                    title=(it.title or (card.title if card else None) or event.title)[
                        :200
                    ],  # type: ignore[union-attr]
                    board_id=card.board_id
                    if card
                    else (event.board_id if event else None),
                    was_planned=True,
                    planned_start=event.start_at
                    if event and not event.all_day
                    else None,
                    planned_minutes=minutes,
                    position=idx * STEP,
                )
            )
            if card is not None and card.id not in previously_planned:
                newly_planned.append(card)

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
