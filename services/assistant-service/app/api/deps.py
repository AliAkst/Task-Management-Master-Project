"""Kimlik: gelen JWT task-api'ye sorulur (kendi kullanici tablosu yok)."""

import base64
import json
import time
from typing import Any

import httpx
from fastapi import Header, HTTPException

from app.config import settings

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_SECONDS = 60
PAT_PREFIX = "pat_"


def _cache_ttl(token: str) -> float:
    """JWT'nin kendi `exp`'ini asmayan onbellek suresi (imza dogrulanmaz; yalniz sure)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:
        return CACHE_SECONDS
    return min(CACHE_SECONDS, exp - time.time())


async def current_user(authorization: str | None = Header(None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Kimlik doğrulama gerekli")
    token = authorization.split(" ", 1)[1].strip()
    if token.startswith(PAT_PREFIX):
        # Erisim anahtari (PAT) bu serviste kullanilamaz: izin/onay/hafiza/saglayici
        # uclari yalniz kullanici oturumuyla (Faz 13b denetim D2)
        raise HTTPException(403, "Erişim anahtarı bu serviste kullanılamaz")
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
    ttl = _cache_ttl(token)
    if ttl > 0:
        _CACHE[token] = (time.monotonic() + ttl, user)
    return user


def ok(data: Any) -> dict[str, Any]:
    """task-api ile ayni yanit sarmali."""
    return {"success": True, "data": data, "error": None}
