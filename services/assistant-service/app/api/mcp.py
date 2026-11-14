"""Claude baglantisi: yapilandirma kod bloklari icin yerel yollar (sir yok)."""

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends

import app as app_package
from app.api.deps import current_user, ok

router = APIRouter()


@router.get("/mcp/config")
async def mcp_config(_: dict = Depends(current_user)):
    return ok(
        {
            "uv": shutil.which("uv") or "uv",
            "assistant_dir": str(Path(app_package.__file__).resolve().parents[1]),
        }
    )
