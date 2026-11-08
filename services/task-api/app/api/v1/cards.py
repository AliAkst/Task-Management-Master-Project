"""Kart, not ve checklist endpoint'leri."""

from fastapi import APIRouter, Response, status

from app.api.dependencies import CardServiceDep, CurrentUserDep
from app.models.card import (
    ActivityResponse,
    BoardGraph,
    CardCreate,
    CardDetail,
    CardMove,
    CardRecurrence,
    CardSplit,
    CardUpdate,
    ChecklistItemCreate,
    ChecklistItemResponse,
    ChecklistItemUpdate,
    DependencyCreate,
    NoteCreate,
    NoteResponse,
    NoteUpdate,
)
from app.models.common import ApiResponse

cards_router = APIRouter(tags=["Cards"])


# ---------------- kart ----------------
@cards_router.post(
    "/cards",
    response_model=ApiResponse[CardDetail],
    status_code=status.HTTP_201_CREATED,
)
async def create_card(data: CardCreate, service: CardServiceDep, user: CurrentUserDep):
    """Karti verilen listenin sonuna ekler."""
    return ApiResponse(success=True, data=await service.create(user.id, data))


@cards_router.get("/cards/{card_id}", response_model=ApiResponse[CardDetail])
async def get_card(card_id: int, service: CardServiceDep, user: CurrentUserDep):
    """Kart detayi: aciklama, notlar, checklist."""
    return ApiResponse(success=True, data=await service.get_detail(card_id, user.id))


@cards_router.patch("/cards/{card_id}", response_model=ApiResponse[CardDetail])
async def update_card(
    card_id: int, data: CardUpdate, service: CardServiceDep, user: CurrentUserDep
):
    """Kismi guncelleme. status=completed karti 'tamamlandi' listesine tasir."""
    return ApiResponse(success=True, data=await service.update(card_id, user.id, data))


@cards_router.post("/cards/{card_id}/move", response_model=ApiResponse[CardDetail])
async def move_card(
    card_id: int, data: CardMove, service: CardServiceDep, user: CurrentUserDep
):
    """Karti hedef listede `index` sirasina tasir (0 tabanli)."""
    return ApiResponse(
        success=True,
        data=await service.move(card_id, user.id, data.list_id, data.index),
    )


@cards_router.delete("/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(card_id: int, service: CardServiceDep, user: CurrentUserDep):
    await service.delete(card_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@cards_router.get(
    "/cards/{card_id}/activity", response_model=ApiResponse[list[ActivityResponse]]
)
async def card_activity(card_id: int, service: CardServiceDep, user: CurrentUserDep):
    """Kartin degisiklik gecmisi (en yeni once)."""
    return ApiResponse(success=True, data=await service.activity_for(card_id, user.id))


# ---------------- not ----------------
@cards_router.post(
    "/cards/{card_id}/notes",
    response_model=ApiResponse[NoteResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_note(
    card_id: int, data: NoteCreate, service: CardServiceDep, user: CurrentUserDep
):
    return ApiResponse(
        success=True, data=await service.add_note(card_id, user.id, data)
    )


@cards_router.patch("/notes/{note_id}", response_model=ApiResponse[NoteResponse])
async def update_note(
    note_id: int, data: NoteUpdate, service: CardServiceDep, user: CurrentUserDep
):
    return ApiResponse(
        success=True, data=await service.update_note(note_id, user.id, data)
    )


@cards_router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: int, service: CardServiceDep, user: CurrentUserDep):
    await service.delete_note(note_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- checklist ----------------
@cards_router.post(
    "/cards/{card_id}/checklist",
    response_model=ApiResponse[ChecklistItemResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_checklist_item(
    card_id: int,
    data: ChecklistItemCreate,
    service: CardServiceDep,
    user: CurrentUserDep,
):
    return ApiResponse(
        success=True, data=await service.add_checklist_item(card_id, user.id, data)
    )


@cards_router.patch(
    "/checklist/{item_id}", response_model=ApiResponse[ChecklistItemResponse]
)
async def update_checklist_item(
    item_id: int,
    data: ChecklistItemUpdate,
    service: CardServiceDep,
    user: CurrentUserDep,
):
    return ApiResponse(
        success=True, data=await service.update_checklist_item(item_id, user.id, data)
    )


@cards_router.delete("/checklist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_checklist_item(
    item_id: int, service: CardServiceDep, user: CurrentUserDep
):
    await service.delete_checklist_item(item_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- hiyerarsi & bagimlilik (Faz 1b) ----------------
@cards_router.post(
    "/cards/{card_id}/dependencies", response_model=ApiResponse[CardDetail]
)
async def add_dependency(
    card_id: int, data: DependencyCreate, service: CardServiceDep, user: CurrentUserDep
):
    """`depends_on_id` bitmeden bu kart baslayamaz. Dongu -> 409 DEPENDENCY_CYCLE."""
    await service.graph.add_dependency(card_id, user.id, data.depends_on_id)
    return ApiResponse(success=True, data=await service.get_detail(card_id, user.id))


@cards_router.delete(
    "/cards/{card_id}/dependencies/{depends_on_id}",
    response_model=ApiResponse[CardDetail],
)
async def remove_dependency(
    card_id: int, depends_on_id: int, service: CardServiceDep, user: CurrentUserDep
):
    await service.graph.remove_dependency(card_id, user.id, depends_on_id)
    return ApiResponse(success=True, data=await service.get_detail(card_id, user.id))


@cards_router.put("/cards/{card_id}/recurrence", response_model=ApiResponse[CardDetail])
async def set_card_recurrence(
    card_id: int, data: CardRecurrence, service: CardServiceDep, user: CurrentUserDep
):
    """Karti tekrarlayan yapar (RRULE) ya da tekrari durdurur (rule=null).
    Tamamlaninca bir sonraki kart kuralin bir sonraki tarihiyle acilir."""
    return ApiResponse(
        success=True, data=await service.set_recurrence(card_id, user.id, data)
    )


@cards_router.post("/cards/{card_id}/split", response_model=ApiResponse[CardDetail])
async def split_card(
    card_id: int, data: CardSplit, service: CardServiceDep, user: CurrentUserDep
):
    """Karti alt kartlara boler; sureyi dagitir, `chain` ise sirali iple baglar."""
    await service.graph.split(card_id, user.id, data)
    return ApiResponse(success=True, data=await service.get_detail(card_id, user.id))


@cards_router.get("/boards/{board_id}/graph", response_model=ApiResponse[BoardGraph])
async def board_graph(board_id: int, service: CardServiceDep, user: CurrentUserDep):
    """Grafik gorunum: dugumler (kartlar) + kenarlar (bagimlilik / ust-alt)."""
    return ApiResponse(
        success=True, data=await service.graph.board_graph(board_id, user.id)
    )
