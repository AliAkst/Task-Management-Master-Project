from fastapi import FastAPI

from app.api.v1.tasks import router as tasks_router
from app.config import settings

app = FastAPI(
    title=settings.app_name, version=settings.app_version, debug=settings.debug
)

app.include_router(tasks_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy", "app_name": settings.app_name}


@app.get("/")
def read_root():
    return {"message": "Welcome to Task API"}
