"""Kullanici ayarlari (saat dilimi, planlama / degerlendirme saatleri)."""

from fastapi import APIRouter

from app.api.dependencies import CurrentUserDep, UserSettingsServiceDep
from app.models.common import ApiResponse
from app.models.user_settings import UserSettingsResponse, UserSettingsUpdate

settings_router = APIRouter(prefix="/settings", tags=["Settings"])


@settings_router.get("/", response_model=ApiResponse[UserSettingsResponse])
async def get_settings(current_user: CurrentUserDep, service: UserSettingsServiceDep):
    """Giris yapmis kullanicinin ayarlarini doner (yoksa varsayilanlarla olusturur)."""
    return ApiResponse(success=True, data=await service.get(current_user.id))


@settings_router.put("/", response_model=ApiResponse[UserSettingsResponse])
async def update_settings(
    settings_in: UserSettingsUpdate,
    current_user: CurrentUserDep,
    service: UserSettingsServiceDep,
):
    """Ayarlari kismi olarak gunceller."""
    return ApiResponse(
        success=True, data=await service.update(current_user.id, settings_in)
    )
