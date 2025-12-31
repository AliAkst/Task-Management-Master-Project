from fastapi import FastAPI

from app.api.v1.tasks import tasks_router as tasks_router
from app.config import settings
from contextlib import asynccontextmanager
from app.db.database import engine
from app.db.entities import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.include_router(tasks_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy", "app_name": settings.app_name}


@app.get("/")
def read_root():
    return {"message": "Welcome to Task API"}
