from datetime import date, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities import (
    EnglishMistakeEntity,
    EnglishProfileEntity,
    EnglishSessionEntity,
    EnglishVocabEntity,
)

from .base import BaseRepository


class EnglishProfileRepository(BaseRepository[EnglishProfileEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, EnglishProfileEntity)

    @with_db_retry
    async def for_user(self, user_id: int) -> EnglishProfileEntity | None:
        result = await self.session.execute(
            select(EnglishProfileEntity).where(EnglishProfileEntity.user_id == user_id)
        )
        return result.scalar_one_or_none()


class EnglishVocabRepository(BaseRepository[EnglishVocabEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, EnglishVocabEntity)

    @with_db_retry
    async def by_key(self, user_id: int, term_key: str) -> EnglishVocabEntity | None:
        result = await self.session.execute(
            select(EnglishVocabEntity).where(
                EnglishVocabEntity.user_id == user_id,
                EnglishVocabEntity.term_key == term_key,
            )
        )
        return result.scalar_one_or_none()

    @with_db_retry
    async def list_for_user(
        self, user_id: int, limit: int, due_on_or_before: date | None = None
    ) -> list[EnglishVocabEntity]:
        e = EnglishVocabEntity
        query = select(e).where(e.user_id == user_id)
        if due_on_or_before is not None:
            query = query.where(e.due_on <= due_on_or_before)
        query = query.order_by(e.due_on, e.id).limit(limit)
        return list((await self.session.execute(query)).scalars().all())

    @with_db_retry
    async def stats(self, user_id: int, today: date) -> tuple[int, int, int]:
        """(toplam, vadesi gelen, olgun: aralik >= 21 gun)."""
        e = EnglishVocabEntity
        row = (
            await self.session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(case((e.due_on <= today, 1), else_=0)), 0),
                    func.coalesce(
                        func.sum(case((e.interval_days >= 21, 1), else_=0)), 0
                    ),
                ).where(e.user_id == user_id)
            )
        ).one()
        return int(row[0]), int(row[1]), int(row[2])


class EnglishMistakeRepository(BaseRepository[EnglishMistakeEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, EnglishMistakeEntity)

    @with_db_retry
    async def list_for_user(
        self, user_id: int, limit: int, category: str | None = None
    ) -> list[EnglishMistakeEntity]:
        e = EnglishMistakeEntity
        query = select(e).where(e.user_id == user_id)
        if category:
            query = query.where(e.category == category)
        query = query.order_by(e.created_at.desc(), e.id.desc()).limit(limit)
        return list((await self.session.execute(query)).scalars().all())

    @with_db_retry
    async def since(self, user_id: int, start: datetime) -> list[EnglishMistakeEntity]:
        e = EnglishMistakeEntity
        result = await self.session.execute(
            select(e).where(e.user_id == user_id, e.created_at >= start)
        )
        return list(result.scalars().all())


class EnglishSessionRepository(BaseRepository[EnglishSessionEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, EnglishSessionEntity)

    @with_db_retry
    async def list_for_user(
        self, user_id: int, limit: int
    ) -> list[EnglishSessionEntity]:
        e = EnglishSessionEntity
        result = await self.session.execute(
            select(e)
            .where(e.user_id == user_id)
            .order_by(e.started_at.desc(), e.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def in_range(
        self, user_id: int, start: datetime, end: datetime | None = None
    ) -> list[EnglishSessionEntity]:
        e = EnglishSessionEntity
        query = select(e).where(e.user_id == user_id, e.started_at >= start)
        if end is not None:
            query = query.where(e.started_at < end)
        return list((await self.session.execute(query)).scalars().all())

    @with_db_retry
    async def all_starts(self, user_id: int) -> list[datetime]:
        e = EnglishSessionEntity
        result = await self.session.execute(
            select(e.started_at).where(e.user_id == user_id)
        )
        return list(result.scalars().all())
