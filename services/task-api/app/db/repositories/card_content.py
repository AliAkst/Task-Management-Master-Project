from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities import ActivityLogEntity, CardNoteEntity, ChecklistItemEntity

from .base import BaseRepository


class CardNoteRepository(BaseRepository[CardNoteEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, CardNoteEntity)

    @with_db_retry
    async def list_for_card(self, card_id: int) -> list[CardNoteEntity]:
        result = await self.session.execute(
            select(CardNoteEntity)
            .where(CardNoteEntity.card_id == card_id)
            .order_by(CardNoteEntity.created_at.desc(), CardNoteEntity.id.desc())
        )
        return list(result.scalars().all())

    @with_db_retry
    async def counts_for_cards(self, card_ids: list[int]) -> dict[int, int]:
        if not card_ids:
            return {}
        result = await self.session.execute(
            select(CardNoteEntity.card_id, func.count())
            .where(CardNoteEntity.card_id.in_(card_ids))
            .group_by(CardNoteEntity.card_id)
        )
        return dict(result.all())

    async def delete_for_card(self, card_id: int) -> None:
        await self.session.execute(
            delete(CardNoteEntity).where(CardNoteEntity.card_id == card_id)
        )


class ChecklistRepository(BaseRepository[ChecklistItemEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ChecklistItemEntity)

    @with_db_retry
    async def list_for_card(self, card_id: int) -> list[ChecklistItemEntity]:
        result = await self.session.execute(
            select(ChecklistItemEntity)
            .where(ChecklistItemEntity.card_id == card_id)
            .order_by(ChecklistItemEntity.position, ChecklistItemEntity.id)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def progress_for_cards(
        self, card_ids: list[int]
    ) -> dict[int, tuple[int, int]]:
        """card_id -> (toplam, tamamlanan)"""
        if not card_ids:
            return {}
        done = func.sum(case((ChecklistItemEntity.is_done.is_(True), 1), else_=0))
        result = await self.session.execute(
            select(ChecklistItemEntity.card_id, func.count(), done)
            .where(ChecklistItemEntity.card_id.in_(card_ids))
            .group_by(ChecklistItemEntity.card_id)
        )
        return {card_id: (total, int(d or 0)) for card_id, total, d in result.all()}

    @with_db_retry
    async def max_position(self, card_id: int) -> float:
        result = await self.session.execute(
            select(func.max(ChecklistItemEntity.position)).where(
                ChecklistItemEntity.card_id == card_id
            )
        )
        return result.scalar() or 0.0

    async def delete_for_card(self, card_id: int) -> None:
        await self.session.execute(
            delete(ChecklistItemEntity).where(ChecklistItemEntity.card_id == card_id)
        )


class ActivityRepository(BaseRepository[ActivityLogEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ActivityLogEntity)

    @with_db_retry
    async def for_card(self, user_id: int, card_id: int, limit: int = 100):
        result = await self.session.execute(
            select(ActivityLogEntity)
            .where(
                ActivityLogEntity.user_id == user_id,
                ActivityLogEntity.card_id == card_id,
            )
            .order_by(ActivityLogEntity.occurred_at.desc(), ActivityLogEntity.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
