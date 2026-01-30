"""
Dapr Service Invocation client.
Diger servisleri Dapr uzerinden cagirmak icin kullanilir.
"""
import http
from math import log
from multiprocessing import reduction
from multiprocessing.connection import Client
import stat
from statistics import correlation
from turtle import heading
from venv import logger
import httpx
from typing import Any
from app.core.logging import get_logger
from app.core.correlation import get_correlation_id
from app.config import settings

logger= get_logger(__name__)

# Dapr sidecar URL
DAPR_HTTP_PORT = 3500
DAPR_BASE_URL = f"http://localhost:{DAPR_HTTP_PORT}"

class DaprClient:
    """
    Dapr Service Invocation client.

    Diger mikroservisleri Dapr sidecar uzerinden cagirmak icin kullanilir.

    Sebep ne ?:
    - Service discovery otomatik
    - Retry/timeout Dapr tarafindan yonetilir.
    - mTLS otomatik (production'da)
    """

    def __init__(self,timeout: float= 30.0):
        """
        DaprClient instance'i olusturur.

        Args:
            timeout: HTTP istekleri icin timeout
        """
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """
        Lazy initialization ile HTTP client dondurur.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url = DAPR_BASE_URL,
                timeout = self._timeout
            )
        return self._client
    
    async def close(self) -> None:
        """
        HTTP client'i kapatir.
        """
        if self._client:
            await self._client.aclose()
            self._client =None
    
    async def invoke(
        self,
        app_id: str,
        method: str,
        data: dict | None = None,
        http_method: str = "GET",
        headers: dict | None = None
    )->dict[str,Any]:
        """
        Baska bir servisi Dapr uzerinden cagir.

        Args:
            app_id: Hedef servisin Dapr app_id si
            method: Cagrilacak endpoint (orn: "users/1")
            data: POST/PUT icin gonderilecek veri
            http_method: HTTP metodu (GET, POST , PUT, DELETE)
            headers: ek HTTP headerlari (correlation id, middleware vs)
        
        Returns:
            dict: Servis yaniti
        
        Raises:
            DaprInvocationError: Cagri basarisiz olursa
        """
        client= await self._get_client()

        url = f"/v1.0/invoke/{app_id}/method/{method}"

        # Correlation ID'yi header'a ekliyoruz
        request_headers=headers or {}
        correlation_id = get_correlation_id
        if correlation_id:
            request_headers["X-Correlation-ID"]= correlation_id
        
        logger.info(
            f"Dapr invoke: {http_method} {app_id}/{method}",
            extra={"correlation_id":correlation_id}
        )
        try:
            if http_method.upper() == "GET":
                response = await client.get(url, headers=request_headers)
            elif http_method.upper() == "POST":
                response = await client.post(url,json=data, headers=request_headers)
            elif http_method.upper() == "PUT":
                response = await client.put(url,json=data, headers=request_headers)
            elif http_method.upper() == "DELETE":
                response = await client.delete(url, headers=request_headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {http_method}")
            
            response.raise_for_status()

            logger.debug(
                f"Dapr Invoke success: {app_id}/{method}",
                extra={"correlation_id":correlation_id}
            )

            return response.json if response.content else {}
        
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Dapr Invoke failed: {app_id}/{method} -> {e.response.status_code}",
                extra={"correlation_id":correlation_id}
            )
            raise DaprInvocationError(
                app_id=app_id,
                method=method,
                status_code=e.status_code,
                detail = str(e)
            )
        except httpx.RequestError as e:
            logger.error(
                f"Dapr Invoke error: {app_id}/{method} -> {e}",
                extra={"correlation_id":correlation_id} 
            )

            raise DaprInvocationError(
                app_id=app_id,
                method=method,
                status_code=503,
                detail=f"Service unavailable: {e}"
            )
    
# ----- CONVENIENCE METHODS ----- #

async def get(self, app_id: str, method: str, headers:dict | None = None)->dict:
    """GET istegi gonderir."""
    return await self.invoke(app_id, method, http_method="GET", headers=headers)

async def post(self, app_id: str, data: dict, method: str, headers: dict | None = None)->dict:
    """POST istegi gonderir."""
    return await self.invoke(app_id,method,data=data,http_method="POST",headers=headers)

async def put(self, app_id: str, data: dict, method: str, headers: dict | None = None)->dict:
    """PUT istegi gonderir."""
    return await self.invoke(app_id, method, data=data, http_method="PUT", headers=headers)

async def delete(self, app_id: str, method: str, headers: dict | None = None)->dict:
    """DELETE istegi gonderir."""
    return await self.invoke(app_id, method, http_method="DELETE", headers=headers)

class DaprInvocationError(Exception):
    """Dapr service invocation hatasi."""

    def __init__(self,app_id: str,method: str,status_code: int,detail: str):
        self.app_id = app_id
        self.method = method
        self.status_code = status_code
        self.detail=detail
        super().__init__(f"Failed to invoke {app_id}/{method}: {status_code}-{detail}")

#Global instance
dapr_client = DaprClient()