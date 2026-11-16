"""
Yerel Ingilizce kocu uclari (Faz 13j2). Yalniz kullanici oturumu (PAT yok - deps).

Gizlilik: pratik metni YALNIZ yerel modele gider; bulut model hicbir kosulda kurulmaz.
Kayitlar izin kapisindan (`log_english`) gecer: auto -> yazilir, ask -> oneri, never -> yazilmaz.
"""

import secrets
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.actions import ActionGate, load_modes
from app.agent.english_coach import (
    MAX_HISTORY,
    MAX_SENTENCE_CHARS,
    MAX_SENTENCES,
    correct_sentences,
    dialog_turn,
    example_prompt,
)
from app.api.deps import current_user, ok
from app.api.providers import user_background_model, user_default_model
from app.config import settings
from app.db.models import get_session, session_maker
from app.llm.registry import build_provider, is_local_model, list_local_models
from app.llm.types import LLMError, ToolCall
from app.tools.english_tools import ENGLISH_ACTION, mistakes_summary
from app.tools.privacy import PrivacyFilter
from app.tools.task_api import TaskApiAuthError, TaskApiClient, TaskApiError
from app.tools.write_tools import PreparedAction, WriteTools

router = APIRouter()
DEFAULT_TZ = "Europe/Istanbul"
DAILY_MINUTES = 5


def today_fn(tz: ZoneInfo) -> date:
    """Yerel bugun; testler bunu ezer (duvar saatine bagimsizlik)."""
    return datetime.now(tz).date()


class CorrectIn(BaseModel):
    sentences: list[str] = Field(min_length=1, max_length=MAX_SENTENCES)

    @field_validator("sentences")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        out = []
        for s in v:
            s = s.strip()
            if not 1 <= len(s) <= MAX_SENTENCE_CHARS:
                raise ValueError(f"Her cümle 1-{MAX_SENTENCE_CHARS} karakter olmalı")
            out.append(s)
        return out


class Turn(BaseModel):
    role: Literal["user", "coach"]
    text: str = Field(min_length=1, max_length=1000)


class DialogIn(BaseModel):
    history: list[Turn] = Field(default_factory=list, max_length=MAX_HISTORY)
    user_text: str = Field(min_length=1, max_length=MAX_SENTENCE_CHARS)


class ExampleIn(BaseModel):
    vocab_ids: list[int] = Field(min_length=1, max_length=5)


async def _local_model_id(session: AsyncSession, user_id: int) -> str:
    """Arka plan modeli yerelse o, degilse sohbet varsayilani; hicbiri yerel degilse kurulu
    ilk yerel model. Yerel model yoksa 503 - bulut ASLA."""
    installed = [m.id for m in await list_local_models()]
    if not installed:
        raise HTTPException(503, "Yerel model yok: Ollama'yı başlatıp bir model kur.")
    for mid in (
        await user_background_model(session, user_id, set(installed)),
        await user_default_model(session, user_id),
    ):
        if is_local_model(mid) and mid in installed:
            return mid
    return installed[0]


async def _tz(api: TaskApiClient) -> ZoneInfo:
    try:
        data = await api.get("/settings/")
        return ZoneInfo((data or {}).get("timezone") or DEFAULT_TZ)
    except TaskApiError:
        return ZoneInfo(DEFAULT_TZ)
    except Exception:  # gecersiz saat dilimi adi
        return ZoneInfo(DEFAULT_TZ)


def _is_today(started_at: Any, tz: ZoneInfo, today: date) -> bool:
    try:
        dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(tz).date() == today


async def _daily_done(api: TaskApiClient, tz: ZoneInfo) -> bool:
    sessions = await api.get("/english/sessions", limit=30) or []
    today = today_fn(tz)
    return any(
        s.get("kind") == "daily" and _is_today(s.get("started_at"), tz, today)
        for s in sessions
    )


async def _save(
    session: AsyncSession,
    api: TaskApiClient,
    user_id: int,
    model_id: str,
    tz: ZoneInfo,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Hatalari (+ gunluk seans) izin kapisindan gecirerek kaydeder."""
    out: dict[str, Any] = {"saved": 0}
    modes = await load_modes(session, user_id)
    if not items or modes.get(ENGLISH_ACTION) == "never":
        return out
    body: dict[str, Any] = {"kind": "mistakes", "items": items}
    if not await _daily_done(api, tz):
        body["session"] = {
            "kind": "daily",
            "minutes": DAILY_MINUTES,
            "mistakes_count": len(items),
            "source": "local",
        }
    prepared = PreparedAction(ENGLISH_ACTION, body, mistakes_summary(items))
    gate = ActionGate(
        session_maker,
        WriteTools(api, PrivacyFilter(active=False), tz),
        user_id=user_id,
        conversation_id=None,
        model_id=model_id,
        modes=modes,
    )
    call = ToolCall(id="english-" + secrets.token_hex(4), name="correct", arguments={})
    result = await gate.handle(call, prepared)
    action = result.action or {}
    status = action.get("status")
    if status == "executed":
        out["saved"] = len(items)
    elif status == "proposed":
        out["pending_action_id"] = action.get("id")
    else:
        out["save_error"] = (action.get("result") or {}).get("error") or "kaydedilemedi"
    return out


def _local_items(results: list[Any]) -> list[dict[str, Any]]:
    items = []
    for r in results:
        for m in r.mistakes:
            row = {k: m[k] for k in ("original", "corrected", "category")}
            if m.get("explanation_tr"):
                row["explanation_tr"] = m["explanation_tr"]
            items.append({**row, "source": "local"})
    return items


@router.post("/english/correct")
async def correct(
    data: CorrectIn,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    model_id = await _local_model_id(session, user["id"])
    provider = build_provider(model_id, None, timeout=settings.background_timeout_seconds)
    try:
        results = await correct_sentences(provider, data.sentences)
    except LLMError as e:
        raise HTTPException(502, f"Yerel model yanıt vermedi: {e}") from e
    if results is None:
        raise HTTPException(502, "Model geçerli yanıt vermedi")
    api = TaskApiClient(user["token"])
    try:
        tz = await _tz(api)
        saved = await _save(
            session, api, user["id"], model_id, tz, _local_items(results)
        )
    except TaskApiAuthError as e:
        raise HTTPException(401, "Oturum süresi doldu") from e
    except TaskApiError as e:
        raise HTTPException(502, e.message) from e
    finally:
        await api.close()
    return ok({"results": [r.as_dict() for r in results], **saved, "model": model_id})


@router.post("/english/dialog")
async def dialog(
    data: DialogIn,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    model_id = await _local_model_id(session, user["id"])
    provider = build_provider(model_id, None, timeout=settings.background_timeout_seconds)
    try:
        turn = await dialog_turn(
            provider, [t.model_dump() for t in data.history], data.user_text
        )
    except LLMError as e:
        raise HTTPException(502, f"Yerel model yanıt vermedi: {e}") from e
    if turn is None:
        raise HTTPException(502, "Model geçerli yanıt vermedi")
    reply, corrections = turn
    return ok({"reply": reply, "corrections": corrections, "model": model_id})


@router.post("/english/example")
async def example(data: ExampleIn, user: dict = Depends(current_user)):
    """Model YOK: secili kelimelerle 'su kelimelerle 2 cumle kur' metnini kod uretir."""
    api = TaskApiClient(user["token"])
    try:
        vocab = await api.get("/english/vocab", limit=200) or []
    except TaskApiAuthError as e:
        raise HTTPException(401, "Oturum süresi doldu") from e
    except TaskApiError as e:
        raise HTTPException(502, e.message) from e
    finally:
        await api.close()
    by_id = {v["id"]: v["term"] for v in vocab}
    terms = [by_id[i] for i in dict.fromkeys(data.vocab_ids) if i in by_id]
    if not terms:
        raise HTTPException(404, "Kelime bulunamadı")
    return ok({"prompt": example_prompt(terms)})
