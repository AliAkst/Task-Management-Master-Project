"""
Kimlik dogrulama (Authentication) uc noktalarini iceren router.
Kayit,Giris,Token yenileme ve profil bilgilerine erisim islemlerini yonetir.
"""

from fastapi import APIRouter, Request, status
from pydantic import BaseModel

from app.api.dependencies import AuthServiceDep, CurrentUserDep, UnitOfWorkDep
from app.models.api_token import ApiTokenCreate, ApiTokenCreated, ApiTokenResponse
from app.models.common import ApiResponse
from app.models.user import (
    MeResponse,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.services.api_token import ApiTokenService

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


@auth_router.get("/registration", response_model=ApiResponse[dict])
async def registration_status(service: AuthServiceDep):
    """Kayit acik mi? Kimlik istemez (giris sayfasi buna bakar)."""
    return ApiResponse(success=True, data={"open": await service.registration_open()})


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


@auth_router.get("/me", response_model=ApiResponse[MeResponse])
async def get_me(request: Request, current_user: CurrentUserDep):
    """
    O an giris yapmis olan kullanicinin bilgilerinin doner.
    bu endpoint Bearer Token (Autharization basligi) gerektirir.
    """
    # CurrentUserDep zaten token'i cozup kullaniciyi DB'den bulup getiriyor.
    me = MeResponse.model_validate(current_user)
    me.token_scopes = getattr(request.state, "pat_scopes", None)
    return ApiResponse(success=True, data=me)


@auth_router.post(
    "/tokens",
    response_model=ApiResponse[ApiTokenCreated],
    status_code=status.HTTP_201_CREATED,
)
async def create_api_token(
    data: ApiTokenCreate, current_user: CurrentUserDep, uow: UnitOfWorkDep
):
    """Kisisel erisim jetonu olusturur; duz metin yalniz bu yanitta doner (PAT ile cagrilamaz)."""
    entity, token = await ApiTokenService(uow).create(current_user.id, data)
    return ApiResponse(
        success=True,
        data=ApiTokenCreated(
            id=entity.id,
            name=entity.name,
            token=token,
            token_hint=entity.token_hint,
            scopes=list(entity.scopes),
            created_at=entity.created_at,
            expires_at=entity.expires_at,
        ),
    )


@auth_router.get("/tokens", response_model=ApiResponse[list[ApiTokenResponse]])
async def list_api_tokens(current_user: CurrentUserDep, uow: UnitOfWorkDep):
    """Iptal edilmemis jetonlar (hash/duz metin asla)."""
    items = await ApiTokenService(uow).list(current_user.id)
    return ApiResponse(
        success=True, data=[ApiTokenResponse.model_validate(i) for i in items]
    )


@auth_router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_token(
    token_id: int, current_user: CurrentUserDep, uow: UnitOfWorkDep
):
    await ApiTokenService(uow).revoke(current_user.id, token_id)
