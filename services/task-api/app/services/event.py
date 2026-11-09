"""
Takvim: etkinlik CRUD + birlesik takvim gorunumu.

Kart = ne, etkinlik = ne zaman. Karta bagli etkinlik o kart icin ayrilmis
zaman blogudur; planlanan zaman bloklari activity_log'a yazilir (Faz 3b
"planlanan vs gerceklesen" analizi bunlari kullanir).
"""

from datetime import datetime, timedelta

from app.core.events import domain_event_publisher
from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.db.entities import BoardEntity, EventEntity, TaskEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.models.event import (
    CalendarItem,
    CalendarResponse,
    EventCreate,
    EventResponse,
    EventUpdate,
    ExternalRef,
)
from app.services.activity import ActivityLogger, diff
from app.services.board import BoardService
from app.services.recurrence import events_in_range, normalize_rule
from app.services.timeutil import user_tz

DEFAULT_COLOR = "#64748b"
MAX_RANGE = timedelta(days=400)


class EventService:
    def __init__(self, uow: TaskUnitOfWork, actor: str = "user"):
        self.uow = uow
        self.actor = actor
        self.activity = ActivityLogger(uow, actor)
        self.boards = BoardService(uow)

    async def _owned(self, event_id: int, user_id: int) -> EventEntity:
        event = await self.uow.events.get_owned(event_id, user_id)
        if event is None:
            raise NotFoundException("Event", event_id)
        return event

    async def _owned_card(self, card_id: int, user_id: int) -> TaskEntity:
        card = await self.uow.tasks.get_owned(card_id, user_id)
        if card is None:
            raise NotFoundException("Card", card_id)
        return card

    async def _externals(self, event_ids: list[int]) -> dict[int, ExternalRef]:
        """Dis takvimden gelen etkinliklerin kaynagi (event_id -> kaynak)."""
        links = await self.uow.external_links.for_entities(None, "event", event_ids)
        return {
            eid: ExternalRef(provider=link.provider, url=link.url)
            for eid, link in links.items()
        }

    async def _response(self, event: EventEntity) -> EventResponse:
        response = EventResponse.model_validate(event)
        response.external = (await self._externals([event.id])).get(event.id)
        return response

    async def _assert_editable(self, event: EventEntity) -> None:
        external = (await self._externals([event.id])).get(event.id)
        if external is not None:
            source = (
                "Outlook/Teams takviminden"
                if external.provider == "microsoft"
                else "Google Takvim'den"
            )
            raise ConflictException(
                "EVENT_READ_ONLY", f"Bu etkinlik {source} geliyor; orada düzenleyin."
            )

    @staticmethod
    def _changes(event: EventEntity) -> dict:
        return {
            "title": event.title,
            "start_at": event.start_at,
            "end_at": event.end_at,
            "all_day": event.all_day,
        }

    async def _publish(self, name: str, user_id: int, event: EventEntity) -> None:
        await domain_event_publisher.publish(
            name,
            {
                "event_id": event.id,
                "user_id": user_id,
                "card_id": event.card_id,
                "board_id": event.board_id,
                "start_at": event.start_at.isoformat(),
                "end_at": event.end_at.isoformat(),
                "actor": self.actor,
            },
        )

    # ---------------- CRUD ----------------
    async def create(self, user_id: int, data: EventCreate) -> EventResponse:
        board_id = data.board_id
        title = data.title
        if data.card_id is not None:
            card = await self._owned_card(data.card_id, user_id)
            board_id = card.board_id  # zaman blogu kartin board'una aittir
            title = title or card.title
        elif board_id is not None:
            await self.boards.get_owned_board(board_id, user_id)

        event = EventEntity(
            user_id=user_id,
            board_id=board_id,
            card_id=data.card_id,
            title=title,
            start_at=data.start_at,
            end_at=data.end_at,
            all_day=data.all_day,
            location=data.location,
            notes=data.notes,
            recurrence_rule=normalize_rule(data.recurrence_rule),
            created_by=self.actor,
        )
        await self.uow.events.create(event)
        await self.uow.flush()
        await self.activity.log(
            user_id,
            "event",
            event.id,
            "scheduled",
            board_id=board_id,
            card_id=event.card_id,
            changes=self._changes(event),
        )
        await self.uow.commit()
        await self._publish("event.created", user_id, event)
        return EventResponse.model_validate(event)

    async def get(self, event_id: int, user_id: int) -> EventResponse:
        return await self._response(await self._owned(event_id, user_id))

    async def list_for_card(self, card_id: int, user_id: int) -> list[EventResponse]:
        card = await self._owned_card(card_id, user_id)
        return [
            EventResponse.model_validate(e)
            for e in await self.uow.events.for_card(card.id)
        ]

    async def update(
        self, event_id: int, user_id: int, data: EventUpdate
    ) -> EventResponse:
        event = await self._owned(event_id, user_id)
        await self._assert_editable(event)
        update = data.model_dump(exclude_unset=True)
        if "recurrence_rule" in update:
            update["recurrence_rule"] = normalize_rule(update["recurrence_rule"])

        if "board_id" in update and update["board_id"] != event.board_id:
            if event.card_id is not None:
                raise ValidationException(
                    "Karta bağlı etkinliğin board'u kartın board'udur"
                )
            if update["board_id"] is not None:
                await self.boards.get_owned_board(update["board_id"], user_id)

        start = update.get("start_at", event.start_at)
        end = update.get("end_at", event.end_at)
        if end <= start:
            raise ValidationException("Bitiş zamanı başlangıçtan sonra olmalı")

        changes = diff(event, update)
        for key, value in update.items():
            setattr(event, key, value)
        if changes:
            moved = {"start_at", "end_at", "all_day"} & changes.keys()
            await self.activity.log(
                user_id,
                "event",
                event.id,
                "rescheduled" if moved else "updated",
                board_id=event.board_id,
                card_id=event.card_id,
                changes=changes,
            )
        await self.uow.commit()
        await self._publish("event.updated", user_id, event)
        return EventResponse.model_validate(event)

    async def delete(self, event_id: int, user_id: int) -> None:
        event = await self._owned(event_id, user_id)
        await self._assert_editable(event)
        await self.activity.log(
            user_id,
            "event",
            event.id,
            "unscheduled",
            board_id=event.board_id,
            card_id=event.card_id,
            changes=self._changes(event),
        )
        await self.uow.day_plan_items.detach_event(event.id)
        await self.uow.events.delete(event)
        await self.uow.commit()
        await domain_event_publisher.publish(
            "event.deleted",
            {"event_id": event_id, "user_id": user_id, "actor": self.actor},
        )

    # ---------------- birlesik takvim ----------------
    async def calendar(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
        board_ids: list[int] | None = None,
    ) -> CalendarResponse:
        if end <= start:
            raise ValidationException("end, start'tan sonra olmalı")
        if end - start > MAX_RANGE:
            raise ValidationException("Takvim aralığı en fazla 400 gün olabilir")

        boards: dict[int, BoardEntity] = {
            b.id: b
            for b in await self.uow.boards.list_for_user(user_id, include_archived=True)
        }
        wanted = set(board_ids) if board_ids else None

        def visible(board_id: int | None) -> bool:
            if board_id is not None and boards.get(board_id) is not None:
                if boards[board_id].is_archived:
                    return False
            if wanted is None:
                return True
            return board_id in wanted

        def color(board_id: int | None) -> str:
            board = boards.get(board_id) if board_id is not None else None
            return board.color if board else DEFAULT_COLOR

        tz = await user_tz(self.uow, user_id)
        expanded = await events_in_range(self.uow, user_id, start, end, tz)
        externals = await self._externals([e.id for e, _, _ in expanded])
        linked = {
            c.id: c
            for c in await self.uow.tasks.get_many(
                [e.card_id for e, _, _ in expanded if e.card_id is not None]
            )
        }

        items: list[CalendarItem] = []
        for e, occ_start, occ_end in expanded:
            card = linked.get(e.card_id) if e.card_id is not None else None
            # Karta bagli blogun board'u (ve rengi) her zaman kartin guncel board'u
            board_id = card.board_id if card is not None else e.board_id
            if not visible(board_id):
                continue
            items.append(
                CalendarItem(
                    kind="event",
                    # Tekrarlarin takvimde benzersiz kimligi: etkinlik + tekrar zamani
                    id=f"event-{e.id}-{int(occ_start.timestamp())}"
                    if e.recurrence_rule
                    else f"event-{e.id}",
                    title=e.title,
                    start=occ_start,
                    end=occ_end,
                    all_day=e.all_day,
                    board_id=board_id,
                    color=color(board_id),
                    event_id=e.id,
                    card_id=e.card_id,
                    card_status=card.status if card is not None else None,
                    location=e.location,
                    meeting_url=e.meeting_url,
                    recurrence_rule=e.recurrence_rule,
                    external=externals.get(e.id),
                )
            )

        for c in await self.uow.events.deadlines_in_range(user_id, start, end):
            if not visible(c.board_id):
                continue
            items.append(
                CalendarItem(
                    kind="deadline",
                    id=f"deadline-{c.id}",
                    title=c.title,
                    start=c.due_date,  # type: ignore[arg-type]
                    end=None,
                    all_day=True,
                    board_id=c.board_id,
                    color=color(c.board_id),
                    card_id=c.id,
                    card_status=c.status,
                )
            )
        return CalendarResponse(items=items)
