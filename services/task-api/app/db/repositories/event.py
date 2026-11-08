from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities import EventEntity, TaskEntity

from .base import BaseRepository


class EventRepository(BaseRepository[EventEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, EventEntity)

    @with_db_retry
    async def in_range(
        self, user_id: int, start: datetime, end: datetime
    ) -> list[EventEntity]:
        """[start, end) araligiyla kesisen etkinlikler."""
        result = await self.session.execute(
            select(EventEntity)
            .where(
                EventEntity.user_id == user_id,
                EventEntity.start_at < end,
                EventEntity.end_at > start,
            )
            .order_by(EventEntity.start_at, EventEntity.id)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def for_card(self, card_id: int) -> list[EventEntity]:
        result = await self.session.execute(
            select(EventEntity)
            .where(EventEntity.card_id == card_id)
            .order_by(EventEntity.start_at)
        )
        return list(result.scalars().all())

    async def delete_for_card(self, card_id: int) -> None:
        await self.session.execute(
            delete(EventEntity).where(EventEntity.card_id == card_id)
        )

    async def delete_for_board(self, board_id: int) -> None:
        """Board'a ait ya da board'daki bir karta bagli etkinlikler."""
        card_ids = select(TaskEntity.id).where(TaskEntity.board_id == board_id)
        await self.session.execute(
            delete(EventEntity).where(
                (EventEntity.board_id == board_id) | EventEntity.card_id.in_(card_ids)
            )
        )

    @with_db_retry
    async def deadlines_in_range(
        self, user_id: int, start: datetime, end: datetime
    ) -> list[TaskEntity]:
        """Son tarihi araliga dusen, arsivlenmemis kartlar."""
        result = await self.session.execute(
            select(TaskEntity)
            .where(
                TaskEntity.user_id == user_id,
                TaskEntity.due_date.is_not(None),
                TaskEntity.due_date >= start,
                TaskEntity.due_date < end,
                TaskEntity.is_archived.is_(False),
            )
            .order_by(TaskEntity.due_date)
        )
        return list(result.scalars().all())
