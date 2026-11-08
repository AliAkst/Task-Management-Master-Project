"""Kimlik: gelen JWT task-api'ye sorulur (kendi kullanici tablosu yok)."""

import time
from typing import Any

import httpx
from fastapi import Header, HTTPException

from app.config import settings

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_SECONDS = 60


async def current_user(authorization: str | None = Header(None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Kimlik doğrulama gerekli")
    token = authorization.split(" ", 1)[1].strip()
    hit = _CACHE.get(token)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                f"{settings.task_api_url}/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as e:
        raise HTTPException(503, "Görev servisine ulaşılamadı") from e
    if res.status_code != 200:
        raise HTTPException(401, "Geçersiz ya da süresi dolmuş oturum")
    user = {**res.json()["data"], "token": token}
    _CACHE[token] = (time.monotonic() + CACHE_SECONDS, user)
    return user


def ok(data: Any) -> dict[str, Any]:
    """task-api ile ayni yanit sarmali."""
    return {"success": True, "data": data, "error": None}
