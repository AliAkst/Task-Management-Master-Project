from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.resilience import with_db_retry
from app.db.entities.base import Base
from app.db.repositories.specifications import PaginationSpecification, Specification


class BaseRepository[T: Base]:
    def __init__(self, session: AsyncSession, model: type[T]):
        self.session = session
        self.model = model

    @with_db_retry
    async def get_by_id(self, id: int) -> T | None:
        """Id ye gore Tasklari listeler"""
        query = select(self.model).where(getattr(self.model, "id") == id)
        result = await self.session.execute(query)

        return result.scalar_one_or_none()
    
    @with_db_retry
    async def get_all(self) -> list[T]:
        """Tum tasklari getirir"""
        query = select(self.model)
        result = await self.session.execute(query)

        return list(result.scalars().all())
    
    async def create(self, entity: T) -> T:
        """Yeni task olusturur."""
        self.session.add(entity)

        return entity
    
    async def update(self, entity: T) -> T:
        """Id si iletilen taski gunceller."""

        return entity
    
    async def delete(self, entity: T) -> None:
        """Id si verilen taski siler"""
        await self.session.delete(entity)

    @with_db_retry
    async def find(self, *specifications: Specification[T])->list[T]:
        """Sepecification'lara gore filtrelenmis sonuclari doner"""
        query = select(self.model)

        for spec in specifications:
            query = spec.apply(query)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    @with_db_retry
    async def find_one(self,*specifications: Specification[T])->T | None:
        """Specification'lara gore tek sonuc doner"""
        query = select(self.model)

        for spec in specifications:
            query = spec.apply(query)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    @with_db_retry
    async def count(self,*specifications:Specification[T]) -> int:
        """Specification'lara gore kayit sayisini doner. 
        Yani a harfi ile baslayan 5 kayit var gibi"""
        query= select(func.count()).select_from(self.model)

        for spec in specifications:
            if not isinstance(spec, PaginationSpecification): # pagination count'u etkilemesin diye
                query=spec.apply(query)
        
        result = await self.session.execute(query)
        return result.scalar() or 0