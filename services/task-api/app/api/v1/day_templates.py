"""Gun sablonlari (Faz 13c): Ofis gunu / Ev gunu iskeletleri."""

from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUserDep, DayTemplateServiceDep
from app.models.common import ApiResponse
from app.models.day_template import (
    DayTemplateCreate,
    DayTemplateResponse,
    DayTemplateUpdate,
)

day_templates_router = APIRouter(prefix="/day-templates", tags=["Day templates"])


@day_templates_router.get("", response_model=ApiResponse[list[DayTemplateResponse]])
async def list_templates(service: DayTemplateServiceDep, user: CurrentUserDep):
    return ApiResponse(success=True, data=await service.list(user.id))


@day_templates_router.post(
    "",
    response_model=ApiResponse[DayTemplateResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    data: DayTemplateCreate, service: DayTemplateServiceDep, user: CurrentUserDep
):
    return ApiResponse(success=True, data=await service.create(user.id, data))


@day_templates_router.patch(
    "/{template_id}", response_model=ApiResponse[DayTemplateResponse]
)
async def update_template(
    template_id: int,
    data: DayTemplateUpdate,
    service: DayTemplateServiceDep,
    user: CurrentUserDep,
):
    return ApiResponse(
        success=True, data=await service.update(template_id, user.id, data)
    )


@day_templates_router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int, service: DayTemplateServiceDep, user: CurrentUserDep
):
    await service.delete(template_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
