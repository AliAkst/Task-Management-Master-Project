"""
Telegram Bot API istemcisi (Faz 13f). Duz metin gonderir (parse_mode yok).

Bot token URL'nin icindedir: httpx hata/log mesajlari URL tasiyabilir, bu yuzden
tum httpx hatalari tokensiz genel bir TelegramError'a cevrilir ve httpx
kaydedicisi WARNING'e cekilir (istek satirlari token sizdirmasin).
"""

import hmac
import logging
from typing import Any

import httpx

logging.getLogger("httpx").setLevel(logging.WARNING)

API = "https://api.telegram.org"
MAX_TEXT = 4000
TIMEOUT = 10.0


class TelegramError(Exception):
    """Mesaj token icermez."""


class TelegramClient:
    def __init__(self, token: str, transport: httpx.AsyncBaseTransport | None = None):
        self._token = token
        self._transport = transport

    async def _call(self, method: str, **params: Any) -> Any:
        url = f"{API}/bot{self._token}/{method}"
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT, transport=self._transport
            ) as client:
                if method == "sendMessage":
                    res = await client.post(url, json=params)
                else:
                    res = await client.get(url, params=params)
        except httpx.HTTPError as e:
            raise TelegramError(
                f"Telegram'a ulaşılamadı ({type(e).__name__})"
            ) from None
        try:
            body = res.json()
        except ValueError:
            body = {}
        if res.status_code != 200 or not body.get("ok"):
            desc = str(body.get("description") or f"HTTP {res.status_code}")
            raise TelegramError(
                f"Telegram reddetti: {desc.replace(self._token, '***')}"
            )
        return body.get("result")

    async def get_me(self) -> dict[str, Any]:
        return await self._call("getMe")

    async def get_updates(self) -> list[dict[str, Any]]:
        return await self._call("getUpdates", limit=20) or []

    async def send_message(self, chat_id: int | str, text: str) -> None:
        await self._call(
            "sendMessage",
            chat_id=chat_id,
            text=text[:MAX_TEXT],
            disable_web_page_preview=True,
        )


def latest_start_chat(
    updates: list[dict[str, Any]], code: str
) -> tuple[int, str | None] | None:
    """`/start <kod>` metni tasiyan EN YENI mesajin (chat.id, gorunen ad)'i.

    Kodsuz ya da yanlis kodlu /start kabul edilmez (sahiplik kaniti)."""
    if not code:
        return None
    want = f"/start {code}"
    best: tuple[int, int, str | None] | None = None
    for u in updates:
        msg = u.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat = msg.get("chat") or {}
        if chat.get("id") is None or not hmac.compare_digest(
            text.encode(), want.encode()
        ):
            continue
        uid = int(u.get("update_id") or 0)
        if best is None or uid >= best[0]:
            name = chat.get("first_name") or chat.get("username")
            best = (uid, int(chat["id"]), name)
    return (best[1], best[2]) if best else None
