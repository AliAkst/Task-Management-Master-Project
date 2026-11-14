from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import with_db_retry
from app.db.entities import TaskEntity
from app.db.entities.day_plan import (
    DayPlanEntity,
    DayPlanItemEntity,
    DayPlanStatus,
    ItemOutcome,
)
from app.models.task import TaskStatus

from .base import BaseRepository


class DayPlanRepository(BaseRepository[DayPlanEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, DayPlanEntity)

    @with_db_retry
    async def for_date(self, user_id: int, day: date) -> DayPlanEntity | None:
        result = await self.session.execute(
            select(DayPlanEntity).where(
                DayPlanEntity.user_id == user_id, DayPlanEntity.date == day
            )
        )
        return result.scalar_one_or_none()

    @with_db_retry
    async def in_range(
        self, user_id: int, start: date, end: date
    ) -> list[DayPlanEntity]:
        """[start, end] (dahil) arasindaki planlar."""
        result = await self.session.execute(
            select(DayPlanEntity)
            .where(
                DayPlanEntity.user_id == user_id,
                DayPlanEntity.date >= start,
                DayPlanEntity.date <= end,
            )
            .order_by(DayPlanEntity.date)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def reviewed_dates(self, user_id: int, limit: int = 400) -> list[date]:
        result = await self.session.execute(
            select(DayPlanEntity.date)
            .where(
                DayPlanEntity.user_id == user_id,
                DayPlanEntity.status == DayPlanStatus.REVIEWED,
            )
            .order_by(DayPlanEntity.date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class DayPlanItemRepository(BaseRepository[DayPlanItemEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, DayPlanItemEntity)

    @with_db_retry
    async def for_plans(self, plan_ids: list[int]) -> list[DayPlanItemEntity]:
        if not plan_ids:
            return []
        result = await self.session.execute(
            select(DayPlanItemEntity)
            .where(DayPlanItemEntity.day_plan_id.in_(plan_ids))
            .order_by(DayPlanItemEntity.position, DayPlanItemEntity.id)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def for_event(self, event_id: int) -> list[DayPlanItemEntity]:
        result = await self.session.execute(
            select(DayPlanItemEntity).where(DayPlanItemEntity.event_id == event_id)
        )
        return list(result.scalars().all())

    @with_db_retry
    async def carried_to(self, user_id: int, day: date) -> list[DayPlanItemEntity]:
        """Bu gune ertelenmis maddeler."""
        result = await self.session.execute(
            select(DayPlanItemEntity).where(
                DayPlanItemEntity.user_id == user_id,
                DayPlanItemEntity.outcome == ItemOutcome.POSTPONED,
                DayPlanItemEntity.postponed_to == day,
            )
        )
        return list(result.scalars().all())

    async def detach_card(self, card_id: int) -> None:
        from app.db.entities import EventEntity

        events = select(EventEntity.id).where(EventEntity.card_id == card_id)
        await detach_from_plans(self.session, [card_id], events)

    async def detach_event(self, event_id: int) -> None:
        await detach_from_plans(self.session, None, [event_id])

    async def detach_board(self, board_id: int) -> None:
        from app.db.entities import EventEntity

        cards = select(TaskEntity.id).where(TaskEntity.board_id == board_id)
        events = select(EventEntity.id).where(
            (EventEntity.board_id == board_id) | EventEntity.card_id.in_(cards)
        )
        await detach_from_plans(self.session, cards, events)


class AnalyticsRepository:
    """Istatistik sorgulari (salt okunur)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @with_db_retry
    async def completed_cards(
        self, user_id: int, start: datetime, end: datetime
    ) -> list[TaskEntity]:
        result = await self.session.execute(
            select(TaskEntity).where(
                TaskEntity.user_id == user_id,
                TaskEntity.status == TaskStatus.COMPLETED,
                TaskEntity.completed_at >= start,
                TaskEntity.completed_at < end,
            )
        )
        return list(result.scalars().all())

    @with_db_retry
    async def postpone_counts(
        self, user_id: int, first: date, last: date, limit: int = 5
    ) -> list[tuple[int, int]]:
        """
        (card_id, erteleme sayisi) en cok ertelenenler. Plan maddelerinden
        sayilir: erteleme, degerlendirmenin yapildigi ana degil, degerlendirilen
        gune aittir (activity_log zamani buna uymaz).
        """
        count = func.count().label("n")
        result = await self.session.execute(
            select(DayPlanItemEntity.card_id, count)
            .join(DayPlanEntity, DayPlanEntity.id == DayPlanItemEntity.day_plan_id)
            .where(
                DayPlanItemEntity.user_id == user_id,
                DayPlanItemEntity.outcome == ItemOutcome.POSTPONED,
                DayPlanItemEntity.card_id.is_not(None),
                DayPlanEntity.date >= first,
                DayPlanEntity.date <= last,
            )
            .group_by(DayPlanItemEntity.card_id)
            .order_by(count.desc())
            .limit(limit)
        )
        return [(card_id, n) for card_id, n in result.all()]


async def detach_from_plans(
    session: AsyncSession,
    card_ids_query=None,
    event_ids_query=None,
) -> None:
    """Kart/etkinlik silinirken plan maddelerini koru, baglantiyi kopar
    (SQLite'ta FK kapali oldugu icin ON DELETE SET NULL calismaz)."""
    from sqlalchemy import update

    if card_ids_query is not None:
        await session.execute(
            update(DayPlanItemEntity)
            .where(DayPlanItemEntity.card_id.in_(card_ids_query))
            .values(card_id=None)
        )
    if event_ids_query is not None:
        await session.execute(
            update(DayPlanItemEntity)
            .where(DayPlanItemEntity.event_id.in_(event_ids_query))
            .values(event_id=None)
        )
