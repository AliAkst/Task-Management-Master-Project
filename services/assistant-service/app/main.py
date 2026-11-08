from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.actions import router as actions_router
from app.api.chat import router as chat_router
from app.api.facts import router as facts_router
from app.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    """task-api ile ayni hata sarmali (frontend tek bir yardimci kullaniyor)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)},
        },
    )


app.include_router(chat_router, prefix="/api/v1/assistant")
app.include_router(actions_router, prefix="/api/v1/assistant")
app.include_router(facts_router, prefix="/api/v1/assistant")


@app.get("/health")
async def health():
    return {"status": "ok"}
