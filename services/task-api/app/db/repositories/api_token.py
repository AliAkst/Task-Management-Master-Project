from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities.api_token import ApiTokenEntity

from .base import BaseRepository


class ApiTokenRepository(BaseRepository[ApiTokenEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ApiTokenEntity)

    @with_db_retry
    async def get_by_hash(self, token_hash: str) -> ApiTokenEntity | None:
        q = select(ApiTokenEntity).where(ApiTokenEntity.token_hash == token_hash)
        return (await self.session.execute(q)).scalar_one_or_none()

    @with_db_retry
    async def list_active(self, user_id: int) -> list[ApiTokenEntity]:
        q = (
            select(ApiTokenEntity)
            .where(
                ApiTokenEntity.user_id == user_id,
                ApiTokenEntity.revoked_at.is_(None),
            )
            .order_by(ApiTokenEntity.id)
        )
        return list((await self.session.execute(q)).scalars().all())

    @with_db_retry
    async def count_active(self, user_id: int) -> int:
        q = select(func.count(ApiTokenEntity.id)).where(
            ApiTokenEntity.user_id == user_id, ApiTokenEntity.revoked_at.is_(None)
        )
        return int((await self.session.execute(q)).scalar_one())
