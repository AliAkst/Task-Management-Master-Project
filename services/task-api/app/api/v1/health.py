"""
Health Check API Endpoints.

Kubernetes liveness/readiness probe'lari icin kullanilir.

"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from app.core.health import health_checker, HealthStatus
from app.models.common import ApiResponse

router = APIRouter(prefix="/health", tags=["Health"])

@router.get(
    "/live",
    response_model=ApiResponse[dict],
    summary="Liveness Probe",
    description="Uygulama ayakta mi kontrol eder."
)
async def liveness():
    """
    Liveness endpoint - Container olu mu kontrol eder.

    Returns:
        dict: {"status": "alive"}
    """
    is_live = await health_checker.is_live()

    if is_live:
        return ApiResponse(success= True,data={"status":"alive"})
    
    return JSONResponse(
        content=ApiResponse(success= False, data={"status":"dead"}).model_dump(mode="json"),
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE
    )

@router.get(
    "/ready",
    response_model=ApiResponse[dict],
    summary="Readiness Probe",
    description="Uygulama trafik almaya hazir mi kontrol eder."
)
async def readiness():
    """
    Readiness Endpoint - Trafik alabilir mi kontrol eder.
    
    Returns:
        ApiResponse: {"success":True,"data":{"status":"ready"}}
    
    """
    is_ready= await health_checker.is_ready()

    if is_ready:
        return ApiResponse(success=True, data = {"status":"ready"})
    
    return JSONResponse(
        content= ApiResponse(success=False, data={"status":"not_ready"}).model_dump(mode="json"),
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE
    )
@router.get(
    "/detailed",
    response_model=ApiResponse[dict],
    summary="Detailed Health Check",
    description ="Tum bilesenlerin detayli saglik durumunu dondurur."
)
async def detailed_health():
    """
    Detayli health check - Tum bilesenlerin durumu.

    Returns:
        ApiResponse: Tum check sonuclarini iceren rapor
    """
    result = await health_checker.check_all()

    if result["status"] == HealthStatus.UNHEALTHY.value:
        return JSONResponse(
            content=ApiResponse(success=False, data= result).model_dump(mode="json"),
            status_code= status.HTTP_503_SERVICE_UNAVAILABLE
        )
    return ApiResponse(success=True,data=result)