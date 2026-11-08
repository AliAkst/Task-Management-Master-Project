"""
Model saglayicilari (Claude / GPT / Gemini) ve kullanicinin varsayilan modeli.

Guvenlik: API anahtari sifreli saklanir ve HICBIR yanitta geri donmez (sadece
son 4 karakteri). Varsayilan model her zaman local olmak zorunda: bulut modeller
ucretli oldugu icin sadece kullanici bilerek sectiginde kullanilir.
"""

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, ok
from app.config import settings
from app.db.models import ModelPrefEntity, ProviderConfigEntity, get_session
from app.llm.registry import (
    CLOUD_PROVIDERS,
    CloudConfig,
    is_local_model,
    parse_model_id,
    probe_provider,
)
from app.llm.types import LLMError
from app.security import SecretError, decrypt, encrypt, mask

router = APIRouter()
MODEL_NAME_RE = re.compile(r"^[\w.\-:/@]{1,100}$")


class ProviderUpsert(BaseModel):
    # Bos/None: kayitli anahtar korunur (sadece model listesi guncellenir)
    api_key: str | None = Field(None, max_length=500)
    models: list[str] = Field(default_factory=list, max_length=20)
    is_enabled: bool = True
    base_url: str | None = Field(None, max_length=300)


class ProbeRequest(BaseModel):
    api_key: str | None = Field(None, max_length=500)
    base_url: str | None = Field(None, max_length=300)


class PrefsUpdate(BaseModel):
    # Gonderilmeyen alan degismez; background_model_id=None -> onerilen buyuk local
    default_model_id: str | None = Field(None, min_length=3, max_length=200)
    background_model_id: str | None = Field(None, min_length=3, max_length=200)


# ---------------- yardimcilar (chat.py de kullanir) ----------------
def _known(provider: str) -> None:
    if provider not in CLOUD_PROVIDERS:
        raise HTTPException(404, "Bilinmeyen sağlayıcı")


async def _config(
    session: AsyncSession, user_id: int, provider: str
) -> ProviderConfigEntity | None:
    return await session.scalar(
        select(ProviderConfigEntity).where(
            ProviderConfigEntity.user_id == user_id,
            ProviderConfigEntity.provider == provider,
        )
    )


async def enabled_cloud_models(
    session: AsyncSession, user_id: int
) -> list[tuple[str, list[str]]]:
    rows = await session.scalars(
        select(ProviderConfigEntity).where(
            ProviderConfigEntity.user_id == user_id,
            ProviderConfigEntity.is_enabled.is_(True),
        )
    )
    return [(r.provider, list(r.models or [])) for r in rows]


async def load_cloud_config(
    session: AsyncSession, user_id: int, provider: str
) -> CloudConfig | None:
    row = await _config(session, user_id, provider)
    if row is None or not row.is_enabled:
        return None
    try:
        key = decrypt(row.api_key_encrypted)
    except SecretError as e:
        raise LLMError(str(e)) from e
    return CloudConfig(provider, key, list(row.models or []), row.base_url)


async def user_default_model(session: AsyncSession, user_id: int) -> str:
    pref = await session.get(ModelPrefEntity, user_id)
    return pref.default_model_id if pref else settings.default_model


async def user_background_model(
    session: AsyncSession, user_id: int, installed: set[str] | None = None
) -> str:
    """
    Arka plan isleri icin model: kullanicinin secimi > config'teki buyuk local
    model (kuruluysa) > sohbet varsayilani. `installed`: kurulu local modeller
    (None: kontrol etme).
    """
    pref = await session.get(ModelPrefEntity, user_id)
    if pref and pref.background_model_id:
        return pref.background_model_id
    if installed is None or settings.background_model in installed:
        return settings.background_model
    return await user_default_model(session, user_id)


def _clean_models(names: list[str]) -> list[str]:
    out: list[str] = []
    for n in (x.strip() for x in names):
        if not n:
            continue
        if not MODEL_NAME_RE.match(n):
            raise HTTPException(422, f"Geçersiz model adı: {n}")
        if n not in out:
            out.append(n)
    return out


def _payload(p: str, row: ProviderConfigEntity | None) -> dict:
    meta = CLOUD_PROVIDERS[p]
    return {
        "provider": p,
        "label": meta.label,
        "key_url": meta.key_url,
        "suggested_models": list(meta.suggested),
        "connected": row is not None,
        "key_hint": row.key_hint if row else None,
        "models": list(row.models or []) if row else [],
        "is_enabled": row.is_enabled if row else False,
        "base_url": row.base_url if row else None,
        "updated_at": row.updated_at if row else None,
    }


# ---------------- uc noktalar ----------------
@router.get("/providers")
async def list_providers(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    rows = {
        r.provider: r
        for r in await session.scalars(
            select(ProviderConfigEntity).where(
                ProviderConfigEntity.user_id == user["id"]
            )
        )
    }
    return ok([_payload(p, rows.get(p)) for p in CLOUD_PROVIDERS])


@router.put("/providers/{provider}")
async def upsert_provider(
    provider: str,
    data: ProviderUpsert,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    _known(provider)
    models = _clean_models(data.models)
    key = (data.api_key or "").strip()
    row = await _config(session, user["id"], provider)
    if row is None:
        if not key:
            raise HTTPException(422, "API anahtarı gerekli")
        row = ProviderConfigEntity(user_id=user["id"], provider=provider)
        session.add(row)
    if key:
        row.api_key_encrypted = encrypt(key)
        row.key_hint = mask(key)
    row.models = models
    row.is_enabled = data.is_enabled
    row.base_url = (data.base_url or "").strip() or None
    row.updated_at = datetime.now(UTC)
    await session.commit()
    return ok(_payload(provider, row))


@router.delete("/providers/{provider}", status_code=204)
async def delete_provider(
    provider: str,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    _known(provider)
    row = await _config(session, user["id"], provider)
    if row is not None:
        await session.delete(row)
        await session.commit()
    return Response(status_code=204)


@router.post("/providers/{provider}/test")
async def test_provider(
    provider: str,
    data: ProbeRequest,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    """Anahtari dogrular (ucretsiz model listesi cagrisi) ve modelleri doner."""
    _known(provider)
    key = (data.api_key or "").strip()
    base_url = (data.base_url or "").strip() or None
    if not key:
        row = await _config(session, user["id"], provider)
        if row is None:
            raise HTTPException(422, "API anahtarı gerekli")
        try:
            key = decrypt(row.api_key_encrypted)
        except SecretError as e:
            raise HTTPException(422, str(e)) from e
        base_url = base_url or row.base_url
    try:
        models = await probe_provider(provider, key, base_url)
    except LLMError as e:
        raise HTTPException(422, str(e)) from e
    return ok({"models": models})


@router.get("/preferences")
async def get_prefs(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    pref = await session.get(ModelPrefEntity, user["id"])
    return ok(
        {
            "default_model_id": await user_default_model(session, user["id"]),
            "background_model_id": pref.background_model_id if pref else None,
            "suggested_background_model": settings.background_model,
        }
    )


@router.put("/preferences")
async def put_prefs(
    data: PrefsUpdate,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    sent = data.model_fields_set
    if "default_model_id" in sent and (
        data.default_model_id is None or not is_local_model(data.default_model_id)
    ):
        raise HTTPException(
            422, "Varsayılan model local olmalı; bulut modeller sadece elle seçilir"
        )
    bg = data.background_model_id
    if "background_model_id" in sent and bg and not is_local_model(bg):
        # Bulut arka plan modeli: kullanici bilerek secer, saglayici bagli olmali
        try:
            provider, name = parse_model_id(bg)
            cloud = await load_cloud_config(session, user["id"], provider)
        except LLMError as e:
            raise HTTPException(422, str(e)) from e
        if cloud is None or name not in cloud.models:
            raise HTTPException(422, "Bu bulut modeli bağlı ya da etkin değil")
    pref = await session.get(ModelPrefEntity, user["id"])
    if pref is None:
        pref = ModelPrefEntity(
            user_id=user["id"],
            default_model_id=await user_default_model(session, user["id"]),
        )
        session.add(pref)
    if "default_model_id" in sent:
        pref.default_model_id = data.default_model_id  # type: ignore[assignment]
    if "background_model_id" in sent:
        pref.background_model_id = bg
    pref.updated_at = datetime.now(UTC)
    await session.commit()
    return ok(
        {
            "default_model_id": pref.default_model_id,
            "background_model_id": pref.background_model_id,
            "suggested_background_model": settings.background_model,
        }
    )
