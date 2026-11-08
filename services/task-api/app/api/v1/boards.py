"""Board, liste ve etiket endpoint'leri."""

from fastapi import APIRouter, Response, status

from app.api.dependencies import BoardServiceDep, CurrentUserDep
from app.models.board import (
    BoardCreate,
    BoardDetail,
    BoardResponse,
    BoardUpdate,
    BoardWithCounts,
    LabelCreate,
    LabelResponse,
    LabelUpdate,
    ListCreate,
    ListMove,
    ListResponse,
    ListUpdate,
)
from app.models.common import ApiResponse

boards_router = APIRouter(tags=["Boards"])


# ---------------- board ----------------
@boards_router.get("/boards", response_model=ApiResponse[list[BoardWithCounts]])
async def list_boards(
    service: BoardServiceDep, user: CurrentUserDep, include_archived: bool = False
):
    """Kullanicinin board'lari (acik kart sayilariyla)."""
    return ApiResponse(
        success=True, data=await service.list_boards(user.id, include_archived)
    )


@boards_router.post(
    "/boards",
    response_model=ApiResponse[BoardResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_board(
    data: BoardCreate, service: BoardServiceDep, user: CurrentUserDep
):
    """Board olusturur. `lists` verilmezse Yapilacak/Yapiliyor/Tamamlandi eklenir."""
    return ApiResponse(success=True, data=await service.create_board(user.id, data))


@boards_router.get("/boards/{board_id}", response_model=ApiResponse[BoardDetail])
async def get_board(board_id: int, service: BoardServiceDep, user: CurrentUserDep):
    """Kanban ekrani: board + listeler + kartlar + etiketler tek istekte."""
    return ApiResponse(success=True, data=await service.get_detail(board_id, user.id))


@boards_router.patch("/boards/{board_id}", response_model=ApiResponse[BoardResponse])
async def update_board(
    board_id: int, data: BoardUpdate, service: BoardServiceDep, user: CurrentUserDep
):
    return ApiResponse(
        success=True, data=await service.update_board(board_id, user.id, data)
    )


@boards_router.delete("/boards/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board(board_id: int, service: BoardServiceDep, user: CurrentUserDep):
    """Board'u tum liste ve kartlariyla siler (gecmis activity_log'da kalir)."""
    await service.delete_board(board_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- liste ----------------
@boards_router.post(
    "/boards/{board_id}/lists",
    response_model=ApiResponse[ListResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_list(
    board_id: int, data: ListCreate, service: BoardServiceDep, user: CurrentUserDep
):
    return ApiResponse(
        success=True, data=await service.create_list(board_id, user.id, data)
    )


@boards_router.patch("/lists/{list_id}", response_model=ApiResponse[ListResponse])
async def update_list(
    list_id: int, data: ListUpdate, service: BoardServiceDep, user: CurrentUserDep
):
    return ApiResponse(
        success=True, data=await service.update_list(list_id, user.id, data)
    )


@boards_router.post("/lists/{list_id}/move", response_model=ApiResponse[ListResponse])
async def move_list(
    list_id: int, data: ListMove, service: BoardServiceDep, user: CurrentUserDep
):
    return ApiResponse(
        success=True, data=await service.move_list(list_id, user.id, data.index)
    )


@boards_router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_list(list_id: int, service: BoardServiceDep, user: CurrentUserDep):
    """Sadece bos liste silinebilir (409 LIST_NOT_EMPTY)."""
    await service.delete_list(list_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- etiket ----------------
@boards_router.post(
    "/boards/{board_id}/labels",
    response_model=ApiResponse[LabelResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_label(
    board_id: int, data: LabelCreate, service: BoardServiceDep, user: CurrentUserDep
):
    return ApiResponse(
        success=True, data=await service.create_label(board_id, user.id, data)
    )


@boards_router.patch("/labels/{label_id}", response_model=ApiResponse[LabelResponse])
async def update_label(
    label_id: int, data: LabelUpdate, service: BoardServiceDep, user: CurrentUserDep
):
    return ApiResponse(
        success=True, data=await service.update_label(label_id, user.id, data)
    )


@boards_router.delete("/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_label(label_id: int, service: BoardServiceDep, user: CurrentUserDep):
    await service.delete_label(label_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
