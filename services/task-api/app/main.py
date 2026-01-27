from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.auth import auth_router as auth_router
from app.api.v1.tasks import tasks_router as tasks_router
from app.config import settings
from app.core.cache import redis_cache
from app.core.exceptions import AppException
from app.core.handlers import app_exception_handler, generic_exception_handler
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RateLimitMiddleware
from app.api.v1.health import router as health_router

setup_logging()

logger = get_logger(__name__)
logger.info("Starting my little tiny app...(finally i made it)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_cache.connect()
    logger.info("Database tables created")

    yield
    
    logger.info("Shutting down application...")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

#---MIDDLEWARE KAYDI BASLATILIYOR...---
app.add_middleware(RateLimitMiddleware)

# --- Exception Handler Kaydi baslatiliyor ---
app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_exception_handler)
# -------------------------
app.include_router(tasks_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(health_router)



@app.get("/")
def read_root():
    return {"message": "Welcome to Task API"}
