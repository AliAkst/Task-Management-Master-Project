from abc import ABC, abstractmethod
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Self
from app.db.repositories.task import TaskRepository
from app.db.repositories.user import UserRepository

class BaseUnitOfWork(ABC):
    """
    Tum unit of Work siniflari icin temel(Abstract) sinif.
    Transection yonetimini(commit,rollback) ve context manager mantigini saglar.
    """
    def __init__(self,session:AsyncSession):
        self.session=session
    
    async def commit(self):
        """Degisiklikleri veritabanina kalici olarak kaydeder"""
        await self.session.commit()
        pass
    
    async def rollback(self):
        """Hata Durumunda yapilan degisiklikleri geri alir."""
        await self.session.rollback()
        pass
    
    async def __aenter__(self) -> Self:
        """'async with' blogu basladiginda calisir."""
        return self
        pass
    
    async def __aexit__(self,exc_type,exc_val,exc_tb) -> Self:
        """
        'async with'blogu bittiginde calisir.
        eger blok icinde bir exception olustuysa otomatik rollback yapar.
        """
        if exc_type is not None:
            await self.rollback()
        pass

class TaskUnitOfWork(BaseUnitOfWork):
    """Task ve User islemlerini tek bir transaction altinda yoneten sinif"""
    def __init__(self,session:AsyncSession):
        super().__init__(session)
        self.tasks = TaskRepository(session)
        self.users = UserRepository(session)
    
    async def commit(self):
        """
        Degisiklikleri kaydeder ve veritabanindan gelen guncel bilgileri(ID vb.)
        nesnelere geri yukler(refresh).
        """
        await super().commit()
        
        for obj in self.session.identity_map.values():
            try:
                await self.session.refresh(obj)
            except Exception:
                #Bazi nesneler(silinenler vs.) refresh edilemez onlari atlamaliyiz.
                continue