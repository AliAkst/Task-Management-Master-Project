"""
Zaman takibi: kronometre (start/stop) ve elle girilen sureler.

Kurallar:
- Kullanici basina tek calisan oturum; yeni baslatmak calisani durdurur.
- Bitmis oturumlar birbiriyle cakisamaz (yoksa sure iki kez sayilir).
- Gelecege oturum girilemez; tek oturum en fazla 24 saat.
- Oturum karti silinse de kalir (board_id / card_title snapshot'lari).
"""

from datetime import UTC, datetime, timedelta

from app.core.events import domain_event_publisher
from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.db.entities import TaskEntity, TimeSessionEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.models.time_session import (
    MAX_SESSION_HOURS,
    ActiveSession,
    SessionManualCreate,
    SessionResponse,
    SessionStart,
    SessionUpdate,
)

FUTURE_TOLERANCE = timedelta(minutes=1)


def _now() -> datetime:
    return datetime.now(UTC)


def to_response(s: TimeSessionEntity) -> SessionResponse:
    return SessionResponse.model_validate(s).model_copy(
        update={"is_running": s.ended_at is None}
    )


class TimeSessionService:
    def __init__(self, uow: TaskUnitOfWork, actor: str = "user"):
        self.uow = uow
        self.actor = actor

    # ---------------- yardimcilar ----------------
    async def _owned(self, session_id: int, user_id: int) -> TimeSessionEntity:
        s = await self.uow.time_sessions.get_owned(session_id, user_id)
        if s is None:
            raise NotFoundException("Session", session_id)
        return s

    async def _card(self, card_id: int | None, user_id: int) -> TaskEntity | None:
        if card_id is None:
            return None
        card = await self.uow.tasks.get_owned(card_id, user_id)
        if card is None:
            raise NotFoundException("Card", card_id)
        return card

    @staticmethod
    def _attach(s: TimeSessionEntity, card: TaskEntity | None) -> None:
        s.card_id = card.id if card else None
        s.board_id = card.board_id if card else None
        s.card_title = card.title if card else None

    @staticmethod
    def _close(s: TimeSessionEntity, at: datetime) -> None:
        s.ended_at = at
        s.duration_sec = max(0, int((at - s.started_at).total_seconds()))

    async def _check_range(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
        exclude_id: int | None = None,
    ) -> None:
        if end <= start:
            raise ValidationException("Bitiş zamanı başlangıçtan sonra olmalı")
        if end > _now() + FUTURE_TOLERANCE:
            raise ValidationException("Gelecek bir zamana çalışma süresi girilemez")
        if (end - start) > timedelta(hours=MAX_SESSION_HOURS):
            raise ValidationException(
                f"Tek oturum en fazla {MAX_SESSION_HOURS} saat olabilir"
            )
        if await self.uow.time_sessions.overlapping(user_id, start, end, exclude_id):
            raise ConflictException(
                "SESSION_OVERLAP", "Bu zaman aralığında başka bir çalışma kaydı var"
            )

    async def _publish(self, name: str, user_id: int, s: TimeSessionEntity) -> None:
        await domain_event_publisher.publish(
            name,
            {
                "session_id": s.id,
                "user_id": user_id,
                "card_id": s.card_id,
                "board_id": s.board_id,
                "started_at": s.started_at.isoformat(),
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "duration_sec": s.duration_sec,
                "source": s.source,
                "actor": self.actor,
            },
        )

    # ---------------- kronometre ----------------
    async def active(self, user_id: int) -> ActiveSession:
        s = await self.uow.time_sessions.active_for_user(user_id)
        return ActiveSession(session=to_response(s) if s else None)

    async def start(self, user_id: int, data: SessionStart) -> SessionResponse:
        card = await self._card(data.card_id, user_id)
        now = _now()

        stopped = await self.uow.time_sessions.active_for_user(user_id)
        if stopped is not None:
            self._close(stopped, now)
            # Yeni satir eklenmeden once kapat (tek-aktif unique index'i)
            await self.uow.flush()

        s = TimeSessionEntity(
            user_id=user_id, started_at=now, note=data.note, source="timer"
        )
        self._attach(s, card)
        await self.uow.time_sessions.create(s)
        await self.uow.commit()

        if stopped is not None:
            await self._publish("session.stopped", user_id, stopped)
        await self._publish("session.started", user_id, s)
        return to_response(s)

    async def stop(self, user_id: int, note: str | None = None) -> SessionResponse:
        s = await self.uow.time_sessions.active_for_user(user_id)
        if s is None:
            raise ConflictException("NO_ACTIVE_SESSION", "Çalışan bir kronometre yok")
        self._close(s, _now())
        if note:
            s.note = f"{s.note}\n{note}" if s.note else note
        await self.uow.commit()
        await self._publish("session.stopped", user_id, s)
        return to_response(s)

    # ---------------- elle giris / duzeltme ----------------
    async def create_manual(
        self, user_id: int, data: SessionManualCreate
    ) -> SessionResponse:
        card = await self._card(data.card_id, user_id)
        await self._check_range(user_id, data.started_at, data.ended_at)
        s = TimeSessionEntity(
            user_id=user_id, started_at=data.started_at, note=data.note, source="manual"
        )
        self._attach(s, card)
        self._close(s, data.ended_at)
        await self.uow.time_sessions.create(s)
        await self.uow.commit()
        await self._publish("session.stopped", user_id, s)
        return to_response(s)

    async def update(
        self, session_id: int, user_id: int, data: SessionUpdate
    ) -> SessionResponse:
        s = await self._owned(session_id, user_id)
        update = data.model_dump(exclude_unset=True)

        if "card_id" in update:
            self._attach(s, await self._card(update["card_id"], user_id))
        if "note" in update:
            s.note = update["note"]

        if "started_at" in update or "ended_at" in update:
            if s.ended_at is None:
                raise ValidationException(
                    "Çalışan kronometrenin zamanı değiştirilemez; önce durdur"
                )
            start = update.get("started_at") or s.started_at
            end = update.get("ended_at") or s.ended_at
            await self._check_range(user_id, start, end, exclude_id=s.id)
            s.started_at = start
            self._close(s, end)

        await self.uow.commit()
        return to_response(s)

    async def delete(self, session_id: int, user_id: int) -> None:
        s = await self._owned(session_id, user_id)
        await self.uow.time_sessions.delete(s)
        await self.uow.commit()

    async def list(
        self,
        user_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
        card_id: int | None = None,
    ) -> list[SessionResponse]:
        if card_id is not None:
            await self._card(card_id, user_id)
        rows = await self.uow.time_sessions.list_for_user(user_id, start, end, card_id)
        return [to_response(s) for s in rows]
