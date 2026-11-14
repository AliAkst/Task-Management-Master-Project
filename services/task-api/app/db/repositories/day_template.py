from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities import DayTemplateEntity

from .base import BaseRepository


class DayTemplateRepository(BaseRepository[DayTemplateEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, DayTemplateEntity)

    @with_db_retry
    async def list_for_user(self, user_id: int) -> list[DayTemplateEntity]:
        result = await self.session.execute(
            select(DayTemplateEntity)
            .where(DayTemplateEntity.user_id == user_id)
            .order_by(DayTemplateEntity.id)
        )
        return list(result.scalars().all())
