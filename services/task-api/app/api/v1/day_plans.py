"""Gunluk planlama, gun sonu degerlendirmesi ve istatistik endpoint'leri."""

from datetime import date

from fastapi import APIRouter, Response, status

from app.api.dependencies import (
    AnalyticsServiceDep,
    CurrentUserDep,
    DayPlanServiceDep,
    DayTemplateServiceDep,
)
from app.models.analytics import AnalyticsSummary
from app.models.common import ApiResponse
from app.models.day_plan import (
    AiSummaryInput,
    DayPlanItemPatch,
    DayPlanResponse,
    DayPlanSave,
    DayReview,
    DaySuggestions,
    ItemMove,
    ItemToCard,
)
from app.models.day_template import (
    ApplyTemplateInput,
    ApplyTemplateResult,
    DayTemplateForDay,
    TemplateModeInput,
)

day_plans_router = APIRouter(tags=["Day planning"])


@day_plans_router.get("/day-plans/{day}", response_model=ApiResponse[DayPlanResponse])
async def get_day_plan(day: date, service: DayPlanServiceDep, user: CurrentUserDep):
    """Gunun plani (yoksa exists=false) + o gun harcanan sureler."""
    return ApiResponse(success=True, data=await service.get(user.id, day))


@day_plans_router.get(
    "/day-plans/{day}/suggestions", response_model=ApiResponse[DaySuggestions]
)
async def get_suggestions(day: date, service: DayPlanServiceDep, user: CurrentUserDep):
    """Plan onerileri: takvim, ertelenen, son tarih, devam eden, calisilan."""
    return ApiResponse(success=True, data=await service.suggestions(user.id, day))


@day_plans_router.get(
    "/day-plans/{day}/template", response_model=ApiResponse[DayTemplateForDay]
)
async def get_day_template(
    day: date, service: DayTemplateServiceDep, user: CurrentUserDep
):
    """Gunun cozumlenen sablonu (off > gun bazli secim > hafta gunu)."""
    return ApiResponse(success=True, data=await service.for_day(user.id, day))


@day_plans_router.put(
    "/day-plans/{day}/template", response_model=ApiResponse[DayTemplateForDay]
)
async def set_day_template(
    day: date,
    data: TemplateModeInput,
    service: DayTemplateServiceDep,
    user: CurrentUserDep,
):
    """Gunun sablon modu: auto | off | template. Degerlendirilmis gunde 409."""
    return ApiResponse(success=True, data=await service.set_mode(user.id, day, data))


@day_plans_router.post(
    "/day-plans/{day}/apply-template", response_model=ApiResponse[ApplyTemplateResult]
)
async def apply_day_template(
    day: date,
    data: ApplyTemplateInput,
    service: DayTemplateServiceDep,
    user: CurrentUserDep,
):
    """Cozumlenen sablonun bloklarini plana ekler (bir kez; force ile tekrar)."""
    return ApiResponse(
        success=True, data=await service.apply(user.id, day, data.force)
    )


@day_plans_router.put("/day-plans/{day}", response_model=ApiResponse[DayPlanResponse])
async def save_day_plan(
    day: date, data: DayPlanSave, service: DayPlanServiceDep, user: CurrentUserDep
):
    """Planli maddeleri (yeniden) yazar. Degerlendirilmis gunde 409."""
    return ApiResponse(success=True, data=await service.save_plan(user.id, day, data))


@day_plans_router.post(
    "/day-plans/{day}/review", response_model=ApiResponse[DayPlanResponse]
)
async def review_day(
    day: date, data: DayReview, service: DayPlanServiceDep, user: CurrentUserDep
):
    """Gun sonu degerlendirmesi; tekrar gonderilebilir (guncelleme)."""
    return ApiResponse(success=True, data=await service.review(user.id, day, data))


@day_plans_router.put(
    "/day-plans/{day}/ai-summary", response_model=ApiResponse[DayPlanResponse]
)
async def set_ai_summary(
    day: date, data: AiSummaryInput, service: DayPlanServiceDep, user: CurrentUserDep
):
    """Asistanin gun ozetini yazar (ya da None ile siler)."""
    return ApiResponse(
        success=True, data=await service.set_ai_summary(user.id, day, data)
    )


@day_plans_router.delete(
    "/day-plan-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_plan_item(
    item_id: int, service: DayPlanServiceDep, user: CurrentUserDep
):
    await service.delete_item(item_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@day_plans_router.patch(
    "/day-plan-items/{item_id}", response_model=ApiResponse[DayPlanResponse]
)
async def patch_plan_item(
    item_id: int,
    data: DayPlanItemPatch,
    service: DayPlanServiceDep,
    user: CurrentUserDep,
):
    """Tek maddeyi gunceller: tamamla, baslik, sure, saat."""
    return ApiResponse(
        success=True, data=await service.patch_item(item_id, user.id, data)
    )


@day_plans_router.post(
    "/day-plan-items/{item_id}/to-card", response_model=ApiResponse[DayPlanResponse]
)
async def plan_item_to_card(
    item_id: int, data: ItemToCard, service: DayPlanServiceDep, user: CurrentUserDep
):
    """Kartsiz plan maddesini karta donusturur."""
    return ApiResponse(
        success=True, data=await service.item_to_card(item_id, user.id, data)
    )


@day_plans_router.post(
    "/day-plan-items/{item_id}/move", response_model=ApiResponse[DayPlanResponse]
)
async def move_plan_item(
    item_id: int, data: ItemMove, service: DayPlanServiceDep, user: CurrentUserDep
):
    """Plan maddesini baska bir gune tasir (bos ise ertesi gun)."""
    return ApiResponse(
        success=True, data=await service.move_item(item_id, user.id, data)
    )


@day_plans_router.get(
    "/analytics/summary", response_model=ApiResponse[AnalyticsSummary]
)
async def analytics_summary(
    start: date, end: date, service: AnalyticsServiceDep, user: CurrentUserDep
):
    """[start, end] (dahil, yerel gunler) icin istatistik ozeti."""
    return ApiResponse(success=True, data=await service.summary(user.id, start, end))
