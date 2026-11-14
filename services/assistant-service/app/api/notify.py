"""
Bildirim ayarlari (Faz 13f): sunucu bildirimlerini ac/kapat, Telegram eslestirme,
Windows bildirimi, is turu tercihleri, deneme. Yalniz kullanici oturumuyla (JWT).

Bot token ve zamanlayici PAT'i hicbir yanitta ve log satirinda gorunmez.
"""

import json
import logging
import secrets
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.chat as chat_module
from app.api.deps import current_user, ok
from app.db.models import (
    DEFAULT_NOTIFY_KINDS,
    NotificationChannelEntity,
    NotificationSettingsEntity,
    ServiceCredentialEntity,
    get_session,
)
from app.notify.base import Notification, Notifier, channel_config
from app.notify.telegram import TelegramClient, TelegramError, latest_start_chat
from app.security import SecretError, encrypt
from app.tools.task_api import TaskApiAuthError, TaskApiError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/notify")

# Testlerde sahte Telegram tasiyicisi (httpx.MockTransport); uretimde None
TRANSPORT: httpx.AsyncBaseTransport | None = None
SERVICE_TOKEN_NAME = "Ajanda zamanlayıcı"


def fail(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "success": False,
            "data": None,
            "error": {"code": code, "message": message},
        },
    )


class TelegramToken(BaseModel):
    bot_token: str = Field(..., min_length=10, max_length=200)


class ToastToggle(BaseModel):
    enabled: bool


class SettingsIn(BaseModel):
    kinds: dict[str, bool] | None = None
    browser_reminders_off: bool | None = None


async def _channel(
    session: AsyncSession, user_id: int, kind: str
) -> NotificationChannelEntity | None:
    return await session.scalar(
        select(NotificationChannelEntity).where(
            NotificationChannelEntity.user_id == user_id,
            NotificationChannelEntity.kind == kind,
        )
    )


async def _settings_row(
    session: AsyncSession, user_id: int
) -> NotificationSettingsEntity:
    row = await session.scalar(
        select(NotificationSettingsEntity).where(
            NotificationSettingsEntity.user_id == user_id
        )
    )
    if row is None:
        row = NotificationSettingsEntity(
            user_id=user_id, kinds=dict(DEFAULT_NOTIFY_KINDS)
        )
        session.add(row)
        await session.flush()
    return row


async def _credential(
    session: AsyncSession, user_id: int
) -> ServiceCredentialEntity | None:
    return await session.scalar(
        select(ServiceCredentialEntity).where(
            ServiceCredentialEntity.user_id == user_id
        )
    )


def _settings_payload(row: NotificationSettingsEntity | None) -> dict[str, Any]:
    return {
        "kinds": {**DEFAULT_NOTIFY_KINDS, **((row.kinds if row else None) or {})},
        "browser_reminders_off": row.browser_reminders_off if row else True,
    }


PAIR_CODE_TTL = 600  # sn


def _new_pair_code(cfg: dict[str, Any]) -> str:
    code = f"{secrets.randbelow(10**6):06d}"
    cfg["pair_code"] = code
    cfg["pair_expires"] = time.time() + PAIR_CODE_TTL
    return code


def _code_valid(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("pair_code")) and time.time() < float(
        cfg.get("pair_expires") or 0
    )


def _channel_payload(row: NotificationChannelEntity) -> dict[str, Any]:
    """Token ASLA donmez; Telegram icin yalniz bot kullanici adi + eslesme durumu."""
    out: dict[str, Any] = {
        "kind": row.kind,
        "is_enabled": row.is_enabled,
        "last_error": row.last_error,
        "last_sent_at": row.last_sent_at,
    }
    if row.kind == "telegram":
        try:
            cfg = channel_config(row)
        except (SecretError, ValueError):
            cfg = {}
        out["bot_username"] = cfg.get("bot_username")
        out["paired"] = cfg.get("chat_id") is not None
        if not out["paired"] and _code_valid(cfg):
            out["pair_code"] = cfg["pair_code"]
    return out


@router.get("")
async def get_notify(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    rows = list(
        await session.scalars(
            select(NotificationChannelEntity).where(
                NotificationChannelEntity.user_id == user["id"]
            )
        )
    )
    settings_row = await session.scalar(
        select(NotificationSettingsEntity).where(
            NotificationSettingsEntity.user_id == user["id"]
        )
    )
    return ok(
        {
            "enabled": await _credential(session, user["id"]) is not None,
            "channels": [_channel_payload(r) for r in rows],
            "settings": _settings_payload(settings_row),
        }
    )


@router.post("/enable")
async def enable(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    if await _credential(session, user["id"]) is None:
        api = chat_module.TaskApiClient(user["token"])
        try:
            created = await api.post_read(
                "/auth/tokens", {"name": SERVICE_TOKEN_NAME, "scopes": ["read"]}
            )
        except TaskApiAuthError:
            return fail(401, "AUTH_EXPIRED", "Oturum süresi doldu")
        except TaskApiError as e:
            return fail(
                502, "TOKEN_CREATE_FAILED", e.message or "Anahtar oluşturulamadı"
            )
        finally:
            await api.close()
        session.add(
            ServiceCredentialEntity(
                user_id=user["id"],
                token_encrypted=encrypt(created["token"]),
                token_id=int(created["id"]),
            )
        )
    await _settings_row(session, user["id"])
    await session.commit()
    return ok({"enabled": True})


@router.post("/disable")
async def disable(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    cred = await _credential(session, user["id"])
    if cred is not None:
        api = chat_module.TaskApiClient(user["token"])
        try:
            # Iptal basarisiz olsa da yerel kayit silinir (anahtar Ayarlar'dan da iptal edilebilir)
            await api._send("DELETE", f"/auth/tokens/{cred.token_id}")
        except (TaskApiError, TaskApiAuthError):
            log.warning("notify disable: task-api token revoke failed")
        finally:
            await api.close()
        await session.delete(cred)
        await session.commit()
    return ok({"enabled": False})


@router.put("/telegram")
async def put_telegram(
    body: TelegramToken,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    token = body.bot_token.strip()
    try:
        me = await TelegramClient(token, TRANSPORT).get_me()
    except TelegramError:
        return fail(
            422,
            "TELEGRAM_TOKEN_INVALID",
            "Bot anahtarı geçersiz ya da Telegram'a ulaşılamadı",
        )
    username = (me or {}).get("username")
    row = await _channel(session, user["id"], "telegram")
    if row is None:
        row = NotificationChannelEntity(user_id=user["id"], kind="telegram")
        session.add(row)
    cfg: dict[str, Any] = {"bot_token": token, "bot_username": username}
    code = _new_pair_code(cfg)
    row.config_encrypted = encrypt(json.dumps(cfg))
    row.is_enabled = False
    row.last_error = None
    await session.commit()
    return ok({"bot_username": username, "pair_code": code})


@router.post("/telegram/code")
async def new_telegram_code(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    row = await _channel(session, user["id"], "telegram")
    if row is None or not row.config_encrypted:
        return fail(409, "TELEGRAM_NO_TOKEN", "Önce bot anahtarını kaydet")
    cfg = channel_config(row)
    code = _new_pair_code(cfg)
    row.config_encrypted = encrypt(json.dumps(cfg))
    await session.commit()
    return ok({"pair_code": code})


@router.post("/telegram/pair")
async def pair_telegram(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    row = await _channel(session, user["id"], "telegram")
    if row is None or not row.config_encrypted:
        return fail(409, "TELEGRAM_NO_TOKEN", "Önce bot anahtarını kaydet")
    cfg = channel_config(row)
    if not cfg.get("pair_code"):
        return fail(409, "TELEGRAM_NO_START", "Eşleştirme kodu al, sonra tekrar dene")
    if not _code_valid(cfg):
        return fail(
            409, "TELEGRAM_CODE_EXPIRED", "Kodun süresi doldu; yeni kod al"
        )
    client = TelegramClient(cfg["bot_token"], TRANSPORT)
    try:
        found = latest_start_chat(await client.get_updates(), cfg["pair_code"])
    except TelegramError as e:
        return fail(422, "TELEGRAM_ERROR", str(e))
    if found is None:
        return fail(
            409,
            "TELEGRAM_NO_START",
            f"Bota /start {cfg['pair_code']} yaz, sonra tekrar dene",
        )
    chat_id, chat_name = found
    try:
        await client.send_message(chat_id, "Ajanda bağlandı ✅")
    except TelegramError as e:
        row.last_error = str(e)[:300]  # kod korunur: tekrar denenebilir
        await session.commit()
        return fail(422, "TELEGRAM_ERROR", str(e))
    cfg["chat_id"] = chat_id
    cfg.pop("pair_code", None)  # tek kullanimlik
    cfg.pop("pair_expires", None)
    row.config_encrypted = encrypt(json.dumps(cfg))
    row.is_enabled = True
    row.last_error = None
    await session.commit()
    return ok({**_channel_payload(row), "chat_name": chat_name})


@router.delete("/telegram")
async def delete_telegram(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    row = await _channel(session, user["id"], "telegram")
    if row is not None:
        await session.delete(row)
        await session.commit()
    return ok(None)


@router.put("/toast")
async def put_toast(
    body: ToastToggle,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _channel(session, user["id"], "toast")
    if row is None:
        row = NotificationChannelEntity(user_id=user["id"], kind="toast")
        session.add(row)
    row.is_enabled = body.enabled
    await session.commit()
    return ok(_channel_payload(row))


@router.put("/settings")
async def put_settings(
    body: SettingsIn,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _settings_row(session, user["id"])
    if body.kinds is not None:
        unknown = set(body.kinds) - set(DEFAULT_NOTIFY_KINDS)
        if unknown:
            return fail(422, "UNKNOWN_KIND", "Bilinmeyen bildirim türü")
        row.kinds = {**DEFAULT_NOTIFY_KINDS, **(row.kinds or {}), **body.kinds}
    if body.browser_reminders_off is not None:
        row.browser_reminders_off = body.browser_reminders_off
    await session.commit()
    return ok(_settings_payload(row))


@router.post("/test")
async def send_test(user: dict = Depends(current_user)):
    notifier = Notifier(chat_module.session_maker, TRANSPORT)
    results = await notifier.send(
        user["id"], Notification("test", "Ajanda", "Deneme bildirimi")
    )
    return ok({"results": results})
