from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException
from app.core.logging import get_logger
from app.models.common import ApiResponse, ErrorDetail

logger = get_logger(__name__)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Uygulama icinde firlatilan hatalari yakalar"""
    error_detail = ErrorDetail(code=exc.error_code, message=exc.message)

    logger.warning(f"App exception: {exc.error_code} - {exc.message}")

    response: ApiResponse = ApiResponse(success=False, error=error_detail)
    return JSONResponse(
        status_code=exc.status_code, content=response.model_dump(mode="json")
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Beklenmeyen, sistem kaynakli hatalari yakalar(500 ERROR)"""
    error_detail = ErrorDetail(
        code="INTERNAL_SERVER_ERROR", message="An unexpected error occurred"
    )
    logger.exception(f"Unexpected error: {exc}")
    response: ApiResponse = ApiResponse(success=False, error=error_detail)
    return JSONResponse(status_code=500, content=response.model_dump(mode="json"))
