"""Takvim ve etkinlik endpoint'leri."""

from datetime import datetime

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import CurrentUserDep, EventServiceDep
from app.models.common import ApiResponse
from app.models.event import (
    CalendarResponse,
    EventCreate,
    EventResponse,
    EventUpdate,
)

events_router = APIRouter(tags=["Calendar"])


@events_router.get("/calendar", response_model=ApiResponse[CalendarResponse])
async def calendar(
    service: EventServiceDep,
    user: CurrentUserDep,
    start: datetime,
    end: datetime,
    board_id: list[int] | None = Query(None),
):
    """
    Tum board'lardaki etkinlikler + kart son tarihleri, [start, end) araliginda.
    `board_id` tekrarlanarak filtrelenebilir (?board_id=1&board_id=3).
    Arsivlenmis board'larin ogeleri gosterilmez.
    """
    return ApiResponse(
        success=True, data=await service.calendar(user.id, start, end, board_id)
    )


@events_router.post(
    "/events",
    response_model=ApiResponse[EventResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_event(
    data: EventCreate, service: EventServiceDep, user: CurrentUserDep
):
    """Etkinlik ya da (card_id ile) karta zaman blogu olusturur."""
    return ApiResponse(success=True, data=await service.create(user.id, data))


@events_router.get("/events/{event_id}", response_model=ApiResponse[EventResponse])
async def get_event(event_id: int, service: EventServiceDep, user: CurrentUserDep):
    return ApiResponse(success=True, data=await service.get(event_id, user.id))


@events_router.patch("/events/{event_id}", response_model=ApiResponse[EventResponse])
async def update_event(
    event_id: int, data: EventUpdate, service: EventServiceDep, user: CurrentUserDep
):
    return ApiResponse(success=True, data=await service.update(event_id, user.id, data))


@events_router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: int, service: EventServiceDep, user: CurrentUserDep):
    await service.delete(event_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@events_router.get(
    "/cards/{card_id}/events", response_model=ApiResponse[list[EventResponse]]
)
async def card_events(card_id: int, service: EventServiceDep, user: CurrentUserDep):
    """Karta ayrilmis zaman bloklari."""
    return ApiResponse(success=True, data=await service.list_for_card(card_id, user.id))
