"""
Docstring for services.task-api.app.core.middleware

FastAPI middleware'lerini barindirir.

Calisma prensibi:
- Request -> Middleware -> Endpoint -> Middleware -> Response
"""
from fastapi import Request,status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.rate_limiter import rate_limiter
from app.core.logging import get_logger

logger = get_logger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Docstring for RateLimitMiddleware
    
    Rate Limiting middleware sinifi

    Her istekte:
    1-Kullanici identifier'ini belirle
    2-Rate limiter'dan izin kontrol et.
    3-Izin varsa: istegi gecir $ Header'lara bilgi ekle
    4-Izin yoksa: 429 To Many Requests don
    """
    EXCLUDED_PATHS={
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json"
    }
    async def dispatch(self,request: Request, call_next):
        """Her istek bu metoddan gecer."""

        # Excluded path kontrolu
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)
        
        #identifieri belirle(JWT USER ID OLARAK GUNCELLENECEK)
        client_ip = request.client.host if request.client else "unkown"
        identifier = f"ip:{client_ip}"

        #Rate limit kontrolu
        allowed, info = await rate_limiter.is_allowed(identifier)

        #response header'lari
        headers={
            "X-RateLimit-Limit":str(info["limit"]),
            "X-RateLimit-Remaining":str(info["remaining"]),
            "X-RateLimit-Reset-After":str(info["reset_after"])
        }
        if not allowed:
            logger.warning(f"Rate limit exceeded for {identifier} on {request.url.path}")
            return JSONResponse(
                status_code = status.HTTP_429_TOO_MANY_REQUESTS,
                content ={
                    "success": False,
                    "error":{
                        "code":"RATE_LIMIT_EXCEEDED",
                        "message":"Too many requests.Please try again later.",
                        "retry_after":info["reset_after"]
                    }
                },headers=headers
            )
        #istegi gecir ve response a header ekle
        response = await call_next(request)
        #headerlari responsa ekledigimiz kisim
        for key,value in headers.items():
            response.headers[key]=value
        
        return response