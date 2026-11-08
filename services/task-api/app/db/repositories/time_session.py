from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities import TimeSessionEntity

from .base import BaseRepository


class TimeSessionRepository(BaseRepository[TimeSessionEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, TimeSessionEntity)

    @with_db_retry
    async def active_for_user(self, user_id: int) -> TimeSessionEntity | None:
        result = await self.session.execute(
            select(TimeSessionEntity).where(
                TimeSessionEntity.user_id == user_id,
                TimeSessionEntity.ended_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @with_db_retry
    async def overlapping(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
        exclude_id: int | None = None,
    ) -> list[TimeSessionEntity]:
        """[start, end) ile kesisen bitmis oturumlar ve calisan oturum."""
        query = select(TimeSessionEntity).where(
            TimeSessionEntity.user_id == user_id,
            TimeSessionEntity.started_at < end,
            (TimeSessionEntity.ended_at.is_(None))
            | (TimeSessionEntity.ended_at > start),
        )
        if exclude_id is not None:
            query = query.where(TimeSessionEntity.id != exclude_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    @with_db_retry
    async def list_for_user(
        self,
        user_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
        card_id: int | None = None,
        limit: int = 200,
    ) -> list[TimeSessionEntity]:
        query = select(TimeSessionEntity).where(TimeSessionEntity.user_id == user_id)
        if start is not None:
            query = query.where(
                (TimeSessionEntity.ended_at.is_(None))
                | (TimeSessionEntity.ended_at > start)
            )
        if end is not None:
            query = query.where(TimeSessionEntity.started_at < end)
        if card_id is not None:
            query = query.where(TimeSessionEntity.card_id == card_id)
        result = await self.session.execute(
            query.order_by(TimeSessionEntity.started_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def totals_for_cards(self, card_ids: list[int]) -> dict[int, int]:
        """card_id -> bitmis oturumlarin toplam saniyesi."""
        if not card_ids:
            return {}
        result = await self.session.execute(
            select(TimeSessionEntity.card_id, func.sum(TimeSessionEntity.duration_sec))
            .where(
                TimeSessionEntity.card_id.in_(card_ids),
                TimeSessionEntity.ended_at.is_not(None),
            )
            .group_by(TimeSessionEntity.card_id)
        )
        return {card_id: int(total or 0) for card_id, total in result.all()}

    async def detach_card(self, card_id: int) -> None:
        """Kart silinirken oturumlari koru, baglantiyi kopar (SQLite FK kapali)."""
        from sqlalchemy import update

        await self.session.execute(
            update(TimeSessionEntity)
            .where(TimeSessionEntity.card_id == card_id)
            .values(card_id=None)
        )

    async def detach_board_cards(self, board_id: int) -> None:
        """Board silinirken o board'daki kartlarin oturumlarini bagimsiz yap."""
        from sqlalchemy import update

        from app.db.entities import TaskEntity

        card_ids = select(TaskEntity.id).where(TaskEntity.board_id == board_id)
        await self.session.execute(
            update(TimeSessionEntity)
            .where(TimeSessionEntity.card_id.in_(card_ids))
            .values(card_id=None)
        )
