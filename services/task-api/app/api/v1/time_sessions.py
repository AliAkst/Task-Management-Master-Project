"""Zaman takibi endpoint'leri (kronometre + elle giris)."""

from datetime import datetime

from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUserDep, TimeSessionServiceDep
from app.models.common import ApiResponse
from app.models.time_session import (
    ActiveSession,
    SessionManualCreate,
    SessionResponse,
    SessionStart,
    SessionStop,
    SessionUpdate,
)

sessions_router = APIRouter(prefix="/sessions", tags=["Time tracking"])


@sessions_router.get("/active", response_model=ApiResponse[ActiveSession])
async def active_session(service: TimeSessionServiceDep, user: CurrentUserDep):
    """Calisan kronometre (yoksa session: null)."""
    return ApiResponse(success=True, data=await service.active(user.id))


@sessions_router.post("/start", response_model=ApiResponse[SessionResponse])
async def start_session(
    data: SessionStart, service: TimeSessionServiceDep, user: CurrentUserDep
):
    """Kronometreyi baslatir. Calisan varsa once onu durdurur."""
    return ApiResponse(success=True, data=await service.start(user.id, data))


@sessions_router.post("/stop", response_model=ApiResponse[SessionResponse])
async def stop_session(
    data: SessionStop, service: TimeSessionServiceDep, user: CurrentUserDep
):
    """Calisan kronometreyi durdurur (yoksa 409 NO_ACTIVE_SESSION)."""
    return ApiResponse(success=True, data=await service.stop(user.id, data.note))


@sessions_router.get("", response_model=ApiResponse[list[SessionResponse]])
async def list_sessions(
    service: TimeSessionServiceDep,
    user: CurrentUserDep,
    start: datetime | None = None,
    end: datetime | None = None,
    card_id: int | None = None,
):
    """Oturumlar (en yeni once). start/end araligiyla kesisenler; card_id filtresi."""
    return ApiResponse(
        success=True, data=await service.list(user.id, start, end, card_id)
    )


@sessions_router.post(
    "",
    response_model=ApiResponse[SessionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_session(
    data: SessionManualCreate, service: TimeSessionServiceDep, user: CurrentUserDep
):
    """Sonradan calisma suresi girer (cakisma 409 SESSION_OVERLAP)."""
    return ApiResponse(success=True, data=await service.create_manual(user.id, data))


@sessions_router.patch("/{session_id}", response_model=ApiResponse[SessionResponse])
async def update_session(
    session_id: int,
    data: SessionUpdate,
    service: TimeSessionServiceDep,
    user: CurrentUserDep,
):
    return ApiResponse(
        success=True, data=await service.update(session_id, user.id, data)
    )


@sessions_router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int, service: TimeSessionServiceDep, user: CurrentUserDep
):
    await service.delete(session_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
