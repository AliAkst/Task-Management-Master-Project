from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities import (
    BoardEntity,
    BoardListEntity,
    CardLabelEntity,
    LabelEntity,
    TaskEntity,
)

from .base import BaseRepository


class BoardRepository(BaseRepository[BoardEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, BoardEntity)

    @with_db_retry
    async def list_for_user(
        self, user_id: int, include_archived: bool = False
    ) -> list[BoardEntity]:
        query = select(BoardEntity).where(BoardEntity.user_id == user_id)
        if not include_archived:
            query = query.where(BoardEntity.is_archived.is_(False))
        result = await self.session.execute(
            query.order_by(BoardEntity.position, BoardEntity.id)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def open_card_counts(self, user_id: int) -> dict[int, int]:
        """Board basina tamamlanmamis, arsivlenmemis kart sayisi."""
        query = (
            select(TaskEntity.board_id, func.count())
            .where(
                TaskEntity.user_id == user_id,
                TaskEntity.board_id.is_not(None),
                TaskEntity.is_archived.is_(False),
                TaskEntity.completed_at.is_(None),
            )
            .group_by(TaskEntity.board_id)
        )
        result = await self.session.execute(query)
        return {board_id: count for board_id, count in result.all()}

    @with_db_retry
    async def max_position(self, user_id: int) -> float:
        result = await self.session.execute(
            select(func.max(BoardEntity.position)).where(BoardEntity.user_id == user_id)
        )
        return result.scalar() or 0.0

    @with_db_retry
    async def find_by_name(self, user_id: int, name: str) -> BoardEntity | None:
        result = await self.session.execute(
            select(BoardEntity)
            .where(BoardEntity.user_id == user_id, BoardEntity.name == name)
            .order_by(BoardEntity.id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    @with_db_retry
    async def find_inbox(self, user_id: int) -> BoardEntity | None:
        result = await self.session.execute(
            select(BoardEntity)
            .where(BoardEntity.user_id == user_id, BoardEntity.system_kind == "inbox")
            .order_by(BoardEntity.id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def delete_cascade(self, board: BoardEntity) -> None:
        """
        Board'u ve icerigini siler. SQLite FK cascade'i varsayilan olarak kapali
        oldugu icin cocuk kayitlari acikca siliyoruz (Postgres'te zararsiz).
        """
        from app.db.entities import CardNoteEntity, ChecklistItemEntity

        card_ids = select(TaskEntity.id).where(TaskEntity.board_id == board.id)
        label_ids = select(LabelEntity.id).where(LabelEntity.board_id == board.id)
        await self.session.execute(
            delete(CardLabelEntity).where(
                CardLabelEntity.card_id.in_(card_ids)
                | CardLabelEntity.label_id.in_(label_ids)
            )
        )
        await self.session.execute(
            delete(CardNoteEntity).where(CardNoteEntity.card_id.in_(card_ids))
        )
        await self.session.execute(
            delete(ChecklistItemEntity).where(ChecklistItemEntity.card_id.in_(card_ids))
        )
        await self.session.execute(
            delete(TaskEntity).where(TaskEntity.board_id == board.id)
        )
        await self.session.execute(
            delete(LabelEntity).where(LabelEntity.board_id == board.id)
        )
        await self.session.execute(
            delete(BoardListEntity).where(BoardListEntity.board_id == board.id)
        )
        await self.session.delete(board)


class BoardListRepository(BaseRepository[BoardListEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, BoardListEntity)

    @with_db_retry
    async def list_for_board(self, board_id: int) -> list[BoardListEntity]:
        result = await self.session.execute(
            select(BoardListEntity)
            .where(BoardListEntity.board_id == board_id)
            .order_by(BoardListEntity.position, BoardListEntity.id)
        )
        return list(result.scalars().all())


class LabelRepository(BaseRepository[LabelEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, LabelEntity)

    @with_db_retry
    async def list_for_board(self, board_id: int) -> list[LabelEntity]:
        result = await self.session.execute(
            select(LabelEntity)
            .where(LabelEntity.board_id == board_id)
            .order_by(LabelEntity.id)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def get_many(self, ids: list[int]) -> list[LabelEntity]:
        if not ids:
            return []
        result = await self.session.execute(
            select(LabelEntity).where(LabelEntity.id.in_(ids))
        )
        return list(result.scalars().all())


class CardLabelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    @with_db_retry
    async def label_ids_for_cards(self, card_ids: list[int]) -> dict[int, list[int]]:
        if not card_ids:
            return {}
        result = await self.session.execute(
            select(CardLabelEntity.card_id, CardLabelEntity.label_id)
            .where(CardLabelEntity.card_id.in_(card_ids))
            .order_by(CardLabelEntity.label_id)
        )
        mapping: dict[int, list[int]] = {}
        for card_id, label_id in result.all():
            mapping.setdefault(card_id, []).append(label_id)
        return mapping

    async def set_for_card(self, card_id: int, label_ids: list[int]) -> None:
        await self.session.execute(
            delete(CardLabelEntity).where(CardLabelEntity.card_id == card_id)
        )
        for label_id in dict.fromkeys(label_ids):  # tekrarlari at, sirayi koru
            self.session.add(CardLabelEntity(card_id=card_id, label_id=label_id))

    async def delete_for_label(self, label_id: int) -> None:
        await self.session.execute(
            delete(CardLabelEntity).where(CardLabelEntity.label_id == label_id)
        )
