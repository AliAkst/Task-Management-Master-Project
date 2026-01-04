"""
Kimlik dogrulama (Authentication) uc noktalarini iceren router.
Kayit,Giris,Token yenileme ve profil bilgilerine erisim islemlerini yonetir.
"""

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.api.dependencies import AuthServiceDep, CurrentUserDep
from app.models.common import ApiResponse
from app.models.user import TokenResponse, UserCreate, UserLogin, UserResponse

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


class RefreshRequest(BaseModel):
    """Token yenileme istegi icin basit sema"""

    refresh_token: str


@auth_router.post(
    "/register",
    response_model=ApiResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register(user_in: UserCreate, service: AuthServiceDep):
    """
    Yeni bir kullanici olusturur.
    """
    user = await service.register(user_in)
    return ApiResponse(success=True, data=user)


@auth_router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(user_in: UserLogin, service: AuthServiceDep):
    """
    Kullanici bilgilerini dogrular ve Access/Refresh token ciftini doner.
    """
    tokens = await service.login(user_in)
    return ApiResponse(success=True, data=tokens)


@auth_router.post(
    "/refresh",
    response_model=ApiResponse[TokenResponse],
)
async def refresh_token(request: RefreshRequest, service: AuthServiceDep):
    """
    Gecerli bir refresh token ile yeni token'lar olusturur.
    """
    tokens = await service.refresh_token(request.refresh_token)
    return ApiResponse(success=True, data=tokens)


@auth_router.get("/me", response_model=ApiResponse[UserResponse])
async def get_me(current_user: CurrentUserDep):
    """
    O an giris yapmis olan kullanicinin bilgilerinin doner.
    bu endpoint Bearer Token (Autharization basligi) gerektirir.
    """
    # CurrentUserDep zaten token'i cozup kullaniciyi DB'den bulup getiriyor.
    return ApiResponse(success=True, data=UserResponse.model_validate(current_user))
