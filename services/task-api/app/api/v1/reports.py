"""Raporlar: iş özeti (Faz 13h1)."""

from datetime import date as date_type

from fastapi import APIRouter

from app.api.dependencies import CurrentUserDep, UnitOfWorkDep
from app.core.exceptions import ValidationException
from app.models.common import ApiResponse
from app.models.reports import WorkSummary
from app.services.reports import ReportService

reports_router = APIRouter(tags=["Reports"])


@reports_router.get("/reports/work-summary", response_model=ApiResponse[WorkSummary])
async def work_summary(
    uow: UnitOfWorkDep,
    user: CurrentUserDep,
    date: date_type,
    board_ids: str | None = None,
):
    """Bir günün Markdown iş özeti. `board_ids` (virgüllü) yoksa tüm board'lar;
    başkasının/olmayan board 404."""
    ids: list[int] | None = None
    if board_ids is not None and board_ids.strip():
        try:
            ids = [int(p) for p in board_ids.split(",") if p.strip()]
        except ValueError:
            raise ValidationException("board_ids virgülle ayrılmış sayılar olmalı")
    return ApiResponse(
        success=True, data=await ReportService(uow).work_summary(user.id, date, ids)
    )
