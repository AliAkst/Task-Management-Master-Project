"""
Correlation ID sistemi.

Amac:
    gonderilen requesti takibe almak ve hatayi kaynagiyla tespit etmek.

Her HTTP istegine benzersiz bir ID atar ve bu ID'yi
tum log'larda ve response header'larda tasir.
"""

import uuid
from contextvars import ContextVar
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
import logging

logger = logging.getLogger(__name__)

#Context variable - async-safe, her request icin ayri deger tutar.
correlation_id_ctx: ContextVar[Optional[str]] = ContextVar(
    "correlation_id",
    default=None
)
# Header isimleri
CORRELATION_ID_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request_ID"
def get_correlation_id() -> Optional[str]:
    """
    Mevcut request'in correlation ID'sini doldurur.

    Returns:
        Optional[str]: Correlation ID veya none    
    """
    return correlation_id_ctx.get()

def set_correlation_id(correlation_id: str) -> None:
    """
    Mevcut request icin correlation ID'yi ayarlar.

    Args:
        correlation_id Atanacak ID
    """
    correlation_id_ctx.set(correlation_id)

def generate_correlation_id() -> str:
    """
    Yeni bir correlation ID uretir.

    Returns:
        str UUID formatinda benzersin ID    
    """
    return str(uuid.uuid4())

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Her HTTP istegine correlation ID atar.

    - Gelen istekte X-Correlation-ID header'i varsa onu kullanir.
    - Yoksa yeni bir ID uretir.
    - Response header'ina ID'yi ekler.
    - Context variable'a ID'yi kaydeder.(log'lar icin)
    """
    async def dispatch(
        self,
        request:Request,
        call_next: RequestResponseEndpoint
    ) -> Response:
        """
        Request'i isler ve correlation ID yonetimini yapar.

        Args:
            request: Gelen HTTP istegi
            call_next: Sonraki middleware/endpoint

        Returns:
            Response: HTTP yaniti (correlation ID header'i ile gonderir.)
        """
        # Gelen header'dan ID al veya yeni uret
        correlation_id = request.headers.get(
            CORRELATION_ID_HEADER
        ) or request.headers.get(
            REQUEST_ID_HEADER
        ) or generate_correlation_id()
    
        # Context'e kaydet (loglar bu degeri kullanabilsin diye)
        set_correlation_id(correlation_id)

        # Debug log
        logger.debug(
            f"Request started: {request.method} {request.url.path}",
            extra = {"correlation_id": correlation_id}
        )

        # Request'e isle
        response = await call_next(request)

        # Response header'a ekle
        response.headers[CORRELATION_ID_HEADER] = correlation_id

        # Debug log
        logger.debug(
            f"Request Completed: {request.method} {request.url.path} "
            f"- Status: {response.status_code}",
            extra={"correlation_id": correlation_id}
        )
        
        return response