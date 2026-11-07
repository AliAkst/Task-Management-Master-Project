from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities import UserSettingsEntity

from .base import BaseRepository


class UserSettingsRepository(BaseRepository[UserSettingsEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, UserSettingsEntity)

    @with_db_retry
    async def get_by_user_id(self, user_id: int) -> UserSettingsEntity | None:
        query = select(UserSettingsEntity).where(UserSettingsEntity.user_id == user_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
