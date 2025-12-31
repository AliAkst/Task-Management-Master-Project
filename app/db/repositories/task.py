from sqlalchemy.ext.asyncio import AsyncSession

from app.db.entities import TaskEntity

from .base import BaseRepository


class TaskRepository(BaseRepository[TaskEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, TaskEntity)
