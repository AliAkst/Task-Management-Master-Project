import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth import auth_router as auth_router
from app.api.v1.tasks import tasks_router as tasks_router
from app.api.v1.boards import boards_router
from app.api.v1.cards import cards_router
from app.api.v1.day_plans import day_plans_router
from app.api.v1.events import events_router
from app.api.v1.goals import goals_router
from app.api.v1.integrations import integrations_router
from app.api.v1.time_sessions import sessions_router
from app.api.v1.user_settings import settings_router
from app.config import settings
from app.core.cache import redis_cache
from app.core.exceptions import AppException
from app.core.handlers import app_exception_handler, generic_exception_handler
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RateLimitMiddleware
from app.api.v1.health import router as health_router
from app.core.correlation import CorrelationIdMiddleware
from app.core.messaging import rabbitmq_client
from app.integrations.scheduler import sync_loop

setup_logging()

logger = get_logger(__name__)
logger.info("Starting my little tiny app...(finally i made it)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_cache.connect()
    # RabbitMQ opsiyonel: baglanamazsa event'ler atlanir, uygulama calismaya devam eder
    try:
        await rabbitmq_client.connect()
    except Exception as e:
        logger.warning(f"RabbitMQ unavailable, domain events disabled: {e}")

    sync_task = asyncio.create_task(sync_loop())

    yield

    #Shutdown
    logger.info("Shutting down application...")
    sync_task.cancel()
    await rabbitmq_client.disconnect()
    await redis_cache.disconnect()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# ------- MIDDLEWARE KAYDI BASLATILIYOR... -------- #
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(RateLimitMiddleware)
# CORS en son eklenir -> en dista calisir (preflight istekleri rate limit'e takilmaz)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID"],
)

# --- Exception Handler Kaydi baslatiliyor --- #
app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_exception_handler)

# ------------------------- ROUTERLAR EKLENIYOR ------------------- #
app.include_router(tasks_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(settings_router, prefix=settings.api_v1_prefix)
app.include_router(boards_router, prefix=settings.api_v1_prefix)
app.include_router(cards_router, prefix=settings.api_v1_prefix)
app.include_router(events_router, prefix=settings.api_v1_prefix)
app.include_router(goals_router, prefix=settings.api_v1_prefix)
app.include_router(integrations_router, prefix=settings.api_v1_prefix)
app.include_router(sessions_router, prefix=settings.api_v1_prefix)
app.include_router(day_plans_router, prefix=settings.api_v1_prefix)
app.include_router(health_router)



@app.get("/")
def read_root():
    return {"message": "Welcome to Task API"}
