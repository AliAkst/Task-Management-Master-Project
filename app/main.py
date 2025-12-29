from fastapi import FastAPI
from app.config import settings
from app.api.v1.tasks import router as tasks_router


app = FastAPI(
    title=settings.app_name, version=settings.app_version, debug=settings.debug
)

app.include_router(tasks_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
    }


# Rooting


@app.get("/")
def read_root() -> dict:
    return {"message": "Task Management API", "status": "Running"}
