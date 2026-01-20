from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.entities import TaskEntity

from .base import BaseRepository


class TaskRepository(BaseRepository[TaskEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, TaskEntity)

    async def get_all_by_users(self, user_id: int) -> list[TaskEntity]:
        """Sadece Belirli bir kullaniciya ait tasklari getirir."""
        query = select(TaskEntity).where(TaskEntity.user_id == user_id)
        result = await self.session.execute(query)

        return list(result.scalars().all())