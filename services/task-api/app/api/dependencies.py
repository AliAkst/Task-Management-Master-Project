"""
API katmaninda kullanilan bagimliliklari(Dependencies) icerir.
Servislerin olusturulmasi ve mevcut kullanicinin dogrulanmasi burada yapilir.
"""

from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ForbiddenException,
    InvalidTokenException,
    PatForbiddenException,
    PatScopeException,
)
from app.core.pat_policy import is_forbidden, needs_write
from app.core.security import decode_token
from app.db.database import get_db_session
from app.db.entities import UserEntity
from app.db.repositories.user import UserRepository
from app.db.unit_of_work import TaskUnitOfWork
from app.services.api_token import PAT_PREFIX, ApiTokenService
from app.services.auth import AuthService
from app.services.board import BoardService
from app.services.attachment import AttachmentService
from app.services.card import CardService
from app.services.analytics import AnalyticsService
from app.services.day_plan import DayPlanService
from app.services.day_template import DayTemplateService
from app.services.event import EventService
from app.services.goal import GoalService
from app.services.time_session import TimeSessionService
from app.services.task import TaskService
from app.services.user_settings import UserSettingsService

# Bearer semasi, Swagger UI'da "Authorize" butonunu aktiflestirir ve token bekler.
bearer_scheme = HTTPBearer()

async def get_unit_of_work(
        session:AsyncSession=Depends(get_db_session)
) -> TaskUnitOfWork:
    """
    FastAPI her istek geldiginde bir veritabani session'i olusturur(get_db_session)
    biz de bu session'i alip TaskOfWork icine enjekte ediyoruz.
    """
    return TaskUnitOfWork(session)
    
    pass

async def get_task_service(
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
) -> TaskService:
    """Taskunitten gelen Session ile calisan
    bir task service nesnesi uretir."""

    return TaskService(uow)


async def get_user_settings_service(
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
) -> UserSettingsService:
    """Kullanici ayarlari servisini hazirlar"""
    return UserSettingsService(uow)


def get_actor(x_actor: str | None = Header(None)) -> str:
    """
    Islemi kimin yaptigi: asistan servisi `X-Actor: ai`, MCP sunucusu `X-Actor: mcp` gonderir.
    Sadece etiket (created_by / activity_log.actor); yetki vermez - kullanici
    zaten sadece kendi kayitlarina erisebilir.
    """
    value = (x_actor or "").lower()
    return value if value in ("ai", "mcp") else "user"


async def get_board_service(
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
) -> BoardService:
    return BoardService(uow)


def _is_pat(request: Request) -> bool:
    """Istek bir PAT ile mi geliyor (kimlik cozulmeden once de dogru: baslik onekine bakar)."""
    parts = request.headers.get("authorization", "").split(" ", 1)
    return len(parts) == 2 and parts[1].strip().startswith(PAT_PREFIX)


async def get_card_service(
    request: Request,
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
    actor: str = Depends(get_actor),
) -> CardService:
    return CardService(
        uow, actor, expose_urls=not _is_pat(request)
    )


async def get_attachment_service(
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
    actor: str = Depends(get_actor),
) -> AttachmentService:
    return AttachmentService(uow, actor)


async def get_event_service(
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
    actor: str = Depends(get_actor),
) -> EventService:
    return EventService(uow, actor)


async def get_time_session_service(
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
) -> TimeSessionService:
    return TimeSessionService(uow)


async def get_day_plan_service(
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
    actor: str = Depends(get_actor),
) -> DayPlanService:
    return DayPlanService(uow, actor)


async def get_day_template_service(
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
    actor: str = Depends(get_actor),
) -> DayTemplateService:
    return DayTemplateService(uow, actor)


async def get_analytics_service(
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
) -> AnalyticsService:
    return AnalyticsService(uow)


async def get_goal_service(
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
    actor: str = Depends(get_actor),
) -> GoalService:
    return GoalService(uow, actor)


async def get_auth_service(uow: TaskUnitOfWork = Depends(get_unit_of_work)):
    """Kimlik dogrulama islemlerini yuruten servisi hazirlar"""
    return AuthService(uow)


async def _authenticate_pat(
    request: Request, token: str, session: AsyncSession
) -> UserEntity:
    """Kisisel erisim jetonu yolu (Faz 13b): gecerlilik -> yasak yol -> kapsam."""
    service = ApiTokenService(TaskUnitOfWork(session))
    entity = await service.authenticate(token)
    if entity is None:
        raise InvalidTokenException()
    user = await UserRepository(session).get_by_id(entity.user_id)
    if not user:
        raise InvalidTokenException()
    method, path = request.method, request.url.path
    if is_forbidden(method, path):
        raise PatForbiddenException()
    if needs_write(method, path) and "write" not in (entity.scopes or []):
        raise PatScopeException()
    await service.touch(entity)
    request.state.auth_kind = "pat"
    return user


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> UserEntity:
    """
    Gelen istekteki token'i dogrular ve veritabanindan kullaniciyi getirir.

    Args:
        credentials: HTTP Bearer token bilgileri.
        session: Veritabani oturumu.
    Returns:
        UserEntity: Mevcut giris yapmis kullanici
    Raises:
        InvalidTokenException: Token gecersiz, suresi dolmus veya
        kullanici bulunamadiysa.
    """
    # token al ve decode et
    token = credentials.credentials
    if token.startswith(PAT_PREFIX):
        return await _authenticate_pat(request, token, session)
    request.state.auth_kind = "jwt"
    payload = decode_token(token)

    # Token gecerlilik ve tip kontrolu
    if not payload or payload.get("type") != "access" or payload.get("sub") is None:
        raise InvalidTokenException()

    # User id al ve kullaniciyi bul
    user_id = int(payload["sub"])
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)

    # Kullanici hala var mi kontrolu
    if not user:
        raise InvalidTokenException()
    return user



# User kisayolu(eger user kisayolu olmazsa admin user getiremeyiz diye burda tanimladik)
CurrentUserDep = Annotated[UserEntity, Depends(get_current_user)]

async def get_current_admin_user(current_user: CurrentUserDep) -> UserEntity:
    """Sadece admin kullanicilari gecirir,digerlerine 403 doner."""
    if not current_user.is_superuser:
        raise ForbiddenException("Admin access required")
    return current_user


# --- TYPE ALIASES (KISAYOLLAR) ---
AdminUserDep = Annotated[UserEntity, Depends(get_current_admin_user)]
UnitOfWorkDep = Annotated[TaskUnitOfWork, Depends(get_unit_of_work)]
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
UserSettingsServiceDep = Annotated[UserSettingsService, Depends(get_user_settings_service)]
BoardServiceDep = Annotated[BoardService, Depends(get_board_service)]
CardServiceDep = Annotated[CardService, Depends(get_card_service)]
AttachmentServiceDep = Annotated[AttachmentService, Depends(get_attachment_service)]
EventServiceDep = Annotated[EventService, Depends(get_event_service)]
TimeSessionServiceDep = Annotated[
    TimeSessionService, Depends(get_time_session_service)
]
DayPlanServiceDep = Annotated[DayPlanService, Depends(get_day_plan_service)]
DayTemplateServiceDep = Annotated[
    DayTemplateService, Depends(get_day_template_service)
]
AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]
GoalServiceDep = Annotated[GoalService, Depends(get_goal_service)]
