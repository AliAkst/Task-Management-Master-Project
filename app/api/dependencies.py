"""
API katmaninda kullanilan bagimliliklari(Dependencies) icerir.
Servislerin olusturulmasi ve mevcut kullanicinin dogrulanmasi burada yapilir.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, InvalidTokenException
from app.core.security import decode_token
from app.db.database import get_db_session
from app.db.entities import UserEntity
from app.db.repositories.user import UserRepository
from app.services.auth import AuthService
from app.services.task import TaskService

# Bearer semasi, Swagger UI'da "Authorize" butonunu aktiflestirir ve token bekler.
bearer_scheme = HTTPBearer()


async def get_task_service(
    session: AsyncSession = Depends(get_db_session),
) -> TaskService:
    """Veritabani sessioni alir ve bu session ile calisan
    bir task service nesnesi uretir."""

    return TaskService(session)


async def get_auth_service(session: AsyncSession = Depends(get_db_session)):
    """Kimlik dogrulama islemlerini yuruten servisi hazirlar"""
    return AuthService(session)


async def get_current_user(
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


# --- TYPE ALIASES (KISAYOLLAR) ---

TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDep = Annotated[UserEntity, Depends(get_current_user)]


async def get_current_admin_user(current_user: CurrentUserDep) -> UserEntity:
    """Sadece admin kullanicilari gecirir,digerlerine 403 doner."""
    if not current_user.is_superuser:
        raise ForbiddenException("Admin access required")
    return current_user


# admin kisayolu
AdminUserDep = Annotated[UserEntity, Depends(get_current_admin_user)]
