from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.entities import UserEntity

from .base import BaseRepository


class UserRepository(BaseRepository[UserEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, UserEntity)

    async def get_by_email(self, email: str) -> UserEntity | None:
        query = select(UserEntity).where(UserEntity.email == email)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
