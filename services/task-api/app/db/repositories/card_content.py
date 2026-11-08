from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities import (
    ActivityLogEntity,
    CardAttachmentEntity,
    CardDependencyEntity,
    CardNoteEntity,
    ChecklistItemEntity,
)

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


class DependencyRepository(BaseRepository[CardDependencyEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, CardDependencyEntity)

    @with_db_retry
    async def edges_for_user(self, user_id: int) -> list[tuple[int, int]]:
        """(card_id, depends_on_id) ciftleri - dongu kontrolu icin tum grafik."""
        result = await self.session.execute(
            select(
                CardDependencyEntity.card_id, CardDependencyEntity.depends_on_id
            ).where(CardDependencyEntity.user_id == user_id)
        )
        return [(a, b) for a, b in result.all()]

    @with_db_retry
    async def edges_touching(self, card_ids: list[int]) -> list[tuple[int, int]]:
        """Verilen kartlardan cikan VEYA onlara giren ipler."""
        if not card_ids:
            return []
        result = await self.session.execute(
            select(
                CardDependencyEntity.card_id, CardDependencyEntity.depends_on_id
            ).where(
                CardDependencyEntity.card_id.in_(card_ids)
                | CardDependencyEntity.depends_on_id.in_(card_ids)
            )
        )
        return [(a, b) for a, b in result.all()]

    @with_db_retry
    async def get_edge(
        self, card_id: int, depends_on_id: int
    ) -> CardDependencyEntity | None:
        result = await self.session.execute(
            select(CardDependencyEntity).where(
                CardDependencyEntity.card_id == card_id,
                CardDependencyEntity.depends_on_id == depends_on_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_for_card(self, card_id: int) -> None:
        await self.session.execute(
            delete(CardDependencyEntity).where(
                (CardDependencyEntity.card_id == card_id)
                | (CardDependencyEntity.depends_on_id == card_id)
            )
        )


class AttachmentRepository(BaseRepository[CardAttachmentEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, CardAttachmentEntity)

    @with_db_retry
    async def list_for_card(self, card_id: int) -> list[CardAttachmentEntity]:
        result = await self.session.execute(
            select(CardAttachmentEntity)
            .where(CardAttachmentEntity.card_id == card_id)
            .order_by(CardAttachmentEntity.created_at, CardAttachmentEntity.id)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def counts_for_cards(self, card_ids: list[int]) -> dict[int, int]:
        if not card_ids:
            return {}
        result = await self.session.execute(
            select(CardAttachmentEntity.card_id, func.count())
            .where(CardAttachmentEntity.card_id.in_(card_ids))
            .group_by(CardAttachmentEntity.card_id)
        )
        return dict(result.all())

    @with_db_retry
    async def all_storage_keys(self) -> set[str]:
        result = await self.session.execute(select(CardAttachmentEntity.storage_key))
        return set(result.scalars().all())

    @with_db_retry
    async def keys_for_card(self, card_id: int) -> list[str]:
        result = await self.session.execute(
            select(CardAttachmentEntity.storage_key).where(
                CardAttachmentEntity.card_id == card_id
            )
        )
        return list(result.scalars().all())

    @with_db_retry
    async def keys_for_board(self, board_id: int) -> list[str]:
        from app.db.entities import TaskEntity

        result = await self.session.execute(
            select(CardAttachmentEntity.storage_key).where(
                CardAttachmentEntity.card_id.in_(
                    select(TaskEntity.id).where(TaskEntity.board_id == board_id)
                )
            )
        )
        return list(result.scalars().all())

    async def delete_for_card(self, card_id: int) -> None:
        await self.session.execute(
            delete(CardAttachmentEntity).where(CardAttachmentEntity.card_id == card_id)
        )

    async def detach_note(self, note_id: int) -> None:
        """Not silinince ekler kalir, note_id bosalir (SQLite'ta FK kapali)."""
        await self.session.execute(
            update(CardAttachmentEntity)
            .where(CardAttachmentEntity.note_id == note_id)
            .values(note_id=None)
        )
