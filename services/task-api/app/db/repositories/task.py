from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities import TaskEntity

from .base import BaseRepository


class TaskRepository(BaseRepository[TaskEntity]):
    """Task / kart sorgulari (ayni tablo)."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, TaskEntity)

    async def get_all_by_users(self, user_id: int) -> list[TaskEntity]:
        """Sadece Belirli bir kullaniciya ait tasklari getirir."""
        query = select(TaskEntity).where(TaskEntity.user_id == user_id)
        result = await self.session.execute(query)

        return list(result.scalars().all())

    @with_db_retry
    async def list_for_board(
        self, board_id: int, include_archived: bool = False
    ) -> list[TaskEntity]:
        query = select(TaskEntity).where(TaskEntity.board_id == board_id)
        if not include_archived:
            query = query.where(TaskEntity.is_archived.is_(False))
        result = await self.session.execute(
            query.order_by(TaskEntity.position, TaskEntity.id)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def list_in_list(self, list_id: int) -> list[TaskEntity]:
        """Bir kanban listesindeki (arsivlenmemis) kartlar, sirali."""
        result = await self.session.execute(
            select(TaskEntity)
            .where(TaskEntity.list_id == list_id, TaskEntity.is_archived.is_(False))
            .order_by(TaskEntity.position, TaskEntity.id)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def max_position_in_list(self, list_id: int) -> float:
        result = await self.session.execute(
            select(func.max(TaskEntity.position)).where(TaskEntity.list_id == list_id)
        )
        return result.scalar() or 0.0

    @with_db_retry
    async def count_in_list(self, list_id: int) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(TaskEntity)
            .where(TaskEntity.list_id == list_id, TaskEntity.is_archived.is_(False))
        )
        return result.scalar() or 0
