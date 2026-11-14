"""Ogrenme koçu endpoint'leri: kurs ilerleme / ETA (Faz 13g)."""

from typing import Literal

from fastapi import APIRouter, status

from app.api.dependencies import CurrentUserDep, LearningServiceDep
from app.models.common import ApiResponse
from app.models.learning import CourseCreate, CourseResponse

learning_router = APIRouter(prefix="/learning", tags=["Learning"])


@learning_router.get("/courses", response_model=ApiResponse[list[CourseResponse]])
async def list_courses(
    service: LearningServiceDep,
    user: CurrentUserDep,
    include: Literal["active", "all"] = "active",
):
    """Kurslar: ilerleme, siradaki parca, haftalik hiz, tahmini bitis."""
    return ApiResponse(success=True, data=await service.list_courses(user.id, include))


@learning_router.post(
    "/courses",
    response_model=ApiResponse[CourseResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_course(
    data: CourseCreate, service: LearningServiceDep, user: CurrentUserDep
):
    """Alt parcalari olan bir karti kurs olarak takibe alir."""
    return ApiResponse(success=True, data=await service.create(user.id, data))
