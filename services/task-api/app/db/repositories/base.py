from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.entities.base import Base


class BaseRepository[T: Base]:
    def __init__(self, session: AsyncSession, model: type[T]):
        self.session = session
        self.model = model

    async def get_by_id(self, id: int) -> T | None:
        query = select(self.model).where(getattr(self.model, "id") == id)
        result = await self.session.execute(query)

        return result.scalar_one_or_none()

    async def get_all(self) -> list[T]:
        query = select(self.model)
        result = await self.session.execute(query)

        return list(result.scalars().all())

    async def create(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)

        return entity

    async def update(self, entity: T) -> T:
        await self.session.commit()
        await self.session.refresh(entity)

        return entity

    async def delete(self, entity: T) -> None:
        await self.session.delete(entity)
        await self.session.commit()
