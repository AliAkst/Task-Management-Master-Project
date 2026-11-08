from abc import ABC
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.board import (
    BoardListRepository,
    BoardRepository,
    CardLabelRepository,
    LabelRepository,
)
from app.db.repositories.card_content import (
    ActivityRepository,
    CardNoteRepository,
    ChecklistRepository,
    DependencyRepository,
)
from app.db.repositories.day_plan import (
    AnalyticsRepository,
    DayPlanItemRepository,
    DayPlanRepository,
)
from app.db.repositories.event import EventRepository
from app.db.repositories.integration import (
    ExternalLinkRepository,
    IntegrationAccountRepository,
)
from app.db.repositories.series import SeriesRepository
from app.db.repositories.task import TaskRepository
from app.db.repositories.time_session import TimeSessionRepository
from app.db.repositories.user import UserRepository
from app.db.repositories.user_settings import UserSettingsRepository
from app.core.resilience import with_db_retry

class BaseUnitOfWork(ABC):
    """
    Tum unit of Work siniflari icin temel(Abstract) sinif.
    Transection yonetimini(commit,rollback) ve context manager mantigini saglar.
    """
    def __init__(self,session:AsyncSession):
        self.session=session
    
    @with_db_retry
    async def commit(self):
        """Degisiklikleri veritabanina kalici olarak kaydeder"""
        await self.session.commit()
        pass
    
    async def flush(self):
        """Commit etmeden SQL'i gonderir (yeni kayitlarin ID'lerini almak icin)."""
        await self.session.flush()

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
        self.user_settings = UserSettingsRepository(session)
        self.boards = BoardRepository(session)
        self.lists = BoardListRepository(session)
        self.labels = LabelRepository(session)
        self.card_labels = CardLabelRepository(session)
        self.notes = CardNoteRepository(session)
        self.checklist = ChecklistRepository(session)
        self.activity = ActivityRepository(session)
        self.events = EventRepository(session)
        self.time_sessions = TimeSessionRepository(session)
        self.day_plans = DayPlanRepository(session)
        self.day_plan_items = DayPlanItemRepository(session)
        self.analytics = AnalyticsRepository(session)
        self.dependencies = DependencyRepository(session)
        self.series = SeriesRepository(session)
        self.integration_accounts = IntegrationAccountRepository(session)
        self.external_links = ExternalLinkRepository(session)
    
    @with_db_retry
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