from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities import CardSeriesEntity, TaskEntity
from app.models.task import TaskStatus

from .base import BaseRepository


class SeriesRepository(BaseRepository[CardSeriesEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, CardSeriesEntity)

    @with_db_retry
    async def get_many(self, ids: list[int]) -> list[CardSeriesEntity]:
        if not ids:
            return []
        result = await self.session.execute(
            select(CardSeriesEntity).where(CardSeriesEntity.id.in_(ids))
        )
        return list(result.scalars().all())

    @with_db_retry
    async def done_counts(self, ids: list[int]) -> dict[int, int]:
        """Seri basina tamamlanmis kart sayisi ("Kosu: 14. tamamlama")."""
        if not ids:
            return {}
        result = await self.session.execute(
            select(TaskEntity.series_id, func.count())
            .where(
                TaskEntity.series_id.in_(ids),
                TaskEntity.status == TaskStatus.COMPLETED,
            )
            .group_by(TaskEntity.series_id)
        )
        return {sid: n for sid, n in result.all()}

    @with_db_retry
    async def has_index(self, series_id: int, index: int) -> bool:
        result = await self.session.execute(
            select(TaskEntity.id)
            .where(TaskEntity.series_id == series_id, TaskEntity.series_index == index)
            .limit(1)
        )
        return result.first() is not None
