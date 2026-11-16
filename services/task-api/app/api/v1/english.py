"""Ingilizce kocu (Faz 13j1): profil, kelime (SRS), hata gunlugu, seanslar, bugun, ilerleme."""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import CurrentUserDep, EnglishServiceDep
from app.models.common import ApiResponse
from app.models.english import (
    MistakeBatch,
    MistakeCategory,
    MistakeItem,
    MistakeResponse,
    ProfileInput,
    ProfileResponse,
    ProgressResponse,
    SessionCreate,
    SessionResponse,
    TodayResponse,
    VocabBatch,
    VocabItem,
    VocabResponse,
    VocabReview,
    VocabUpdate,
)

english_router = APIRouter(prefix="/english", tags=["English"])


# ---------------- profil ----------------
@english_router.get("/profile", response_model=ApiResponse[ProfileResponse])
async def get_profile(service: EnglishServiceDep, user: CurrentUserDep):
    return ApiResponse(success=True, data=await service.get_profile(user.id))


@english_router.put("/profile", response_model=ApiResponse[ProfileResponse])
async def put_profile(
    data: ProfileInput, service: EnglishServiceDep, user: CurrentUserDep
):
    return ApiResponse(success=True, data=await service.put_profile(user.id, data))


# ---------------- kelime ----------------
@english_router.get("/vocab", response_model=ApiResponse[list[VocabResponse]])
async def list_vocab(
    service: EnglishServiceDep,
    user: CurrentUserDep,
    due: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return ApiResponse(success=True, data=await service.list_vocab(user.id, due, limit))


@english_router.post(
    "/vocab",
    response_model=ApiResponse[VocabResponse | list[VocabResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def create_vocab(
    body: VocabItem | VocabBatch,
    response: Response,
    service: EnglishServiceDep,
    user: CurrentUserDep,
):
    """Tek kelime ya da {items: [...]} (en cok 20). Var olan terim `existing: true` doner."""
    batch = isinstance(body, VocabBatch)
    out = await service.add_vocab(user.id, body.items if batch else [body])
    if all(v.existing for v in out):
        response.status_code = status.HTTP_200_OK
    return ApiResponse(success=True, data=out if batch else out[0])


@english_router.patch("/vocab/{vocab_id}", response_model=ApiResponse[VocabResponse])
async def update_vocab(
    vocab_id: int,
    data: VocabUpdate,
    service: EnglishServiceDep,
    user: CurrentUserDep,
):
    return ApiResponse(
        success=True, data=await service.update_vocab(vocab_id, user.id, data)
    )


@english_router.delete("/vocab/{vocab_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vocab(vocab_id: int, service: EnglishServiceDep, user: CurrentUserDep):
    await service.delete_vocab(vocab_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@english_router.post(
    "/vocab/{vocab_id}/review", response_model=ApiResponse[VocabResponse]
)
async def review_vocab(
    vocab_id: int,
    data: VocabReview,
    service: EnglishServiceDep,
    user: CurrentUserDep,
):
    """SM-2 tekrar notu (0-5)."""
    return ApiResponse(
        success=True, data=await service.review_vocab(vocab_id, user.id, data.grade)
    )


# ---------------- hata gunlugu ----------------
@english_router.get("/mistakes", response_model=ApiResponse[list[MistakeResponse]])
async def list_mistakes(
    service: EnglishServiceDep,
    user: CurrentUserDep,
    category: MistakeCategory | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    rows = await service.list_mistakes(user.id, category, limit)
    return ApiResponse(
        success=True, data=[MistakeResponse.model_validate(r) for r in rows]
    )


@english_router.post(
    "/mistakes",
    response_model=ApiResponse[MistakeResponse | list[MistakeResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def create_mistakes(
    body: MistakeItem | MistakeBatch, service: EnglishServiceDep, user: CurrentUserDep
):
    """Tek hata ya da {items: [...]} (en cok 20)."""
    batch = isinstance(body, MistakeBatch)
    rows = await service.add_mistakes(user.id, body.items if batch else [body])
    out = [MistakeResponse.model_validate(r) for r in rows]
    return ApiResponse(success=True, data=out if batch else out[0])


@english_router.delete("/mistakes/{mistake_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mistake(
    mistake_id: int, service: EnglishServiceDep, user: CurrentUserDep
):
    await service.delete_mistake(mistake_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- seanslar ----------------
@english_router.get("/sessions", response_model=ApiResponse[list[SessionResponse]])
async def list_sessions(
    service: EnglishServiceDep,
    user: CurrentUserDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
):
    rows = await service.list_sessions(user.id, limit)
    return ApiResponse(
        success=True, data=[SessionResponse.model_validate(r) for r in rows]
    )


@english_router.post(
    "/sessions",
    response_model=ApiResponse[SessionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    data: SessionCreate, service: EnglishServiceDep, user: CurrentUserDep
):
    row = await service.add_session(user.id, data)
    return ApiResponse(success=True, data=SessionResponse.model_validate(row))


# ---------------- bugun / ilerleme ----------------
@english_router.get("/today", response_model=ApiResponse[TodayResponse])
async def today(service: EnglishServiceDep, user: CurrentUserDep):
    return ApiResponse(success=True, data=await service.today(user.id))


@english_router.get("/progress", response_model=ApiResponse[ProgressResponse])
async def progress(
    service: EnglishServiceDep,
    user: CurrentUserDep,
    weeks: Annotated[int, Query(ge=1, le=52)] = 8,
):
    return ApiResponse(success=True, data=await service.progress(user.id, weeks))
