"""Bildirim kanallarina gonderim (Faz 13f). Hata last_error'a, basari last_sent_at'e."""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import NotificationChannelEntity
from app.notify.telegram import TelegramClient, TelegramError
from app.notify.toast import ToastError, send_toast
from app.security import SecretError, decrypt

log = logging.getLogger(__name__)


@dataclass
class Notification:
    kind: str
    title: str
    body: str


def channel_config(row: NotificationChannelEntity) -> dict:
    if not row.config_encrypted:
        return {}
    return json.loads(decrypt(row.config_encrypted))


class Notifier:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.session_maker = session_maker
        self.transport = transport

    async def _deliver(self, row: NotificationChannelEntity, n: Notification) -> None:
        if row.kind == "toast":
            await send_toast(n.title, n.body)
        elif row.kind == "telegram":
            cfg = channel_config(row)
            if not cfg.get("bot_token") or cfg.get("chat_id") is None:
                raise TelegramError("Telegram eşleştirilmemiş")
            await TelegramClient(cfg["bot_token"], self.transport).send_message(
                cfg["chat_id"], f"{n.title}\n{n.body}"
            )

    async def send(self, user_id: int, n: Notification) -> dict[str, str]:
        """Etkin her kanala gonderir: {kind: "ok" | "hata"}."""
        result: dict[str, str] = {}
        async with self.session_maker() as session:
            rows = list(
                await session.scalars(
                    select(NotificationChannelEntity).where(
                        NotificationChannelEntity.user_id == user_id,
                        NotificationChannelEntity.is_enabled.is_(True),
                    )
                )
            )
            for row in rows:
                try:
                    await self._deliver(row, n)
                    row.last_sent_at = datetime.now(UTC)
                    row.last_error = None
                    result[row.kind] = "ok"
                except (TelegramError, ToastError, SecretError) as e:
                    row.last_error = str(e)[:300]
                    result[row.kind] = "hata"
                except Exception:  # kanal hatasi dongu/isi dusurmesin
                    log.exception("notify %s failed", row.kind)
                    row.last_error = "Beklenmeyen bildirim hatası"
                    result[row.kind] = "hata"
            await session.commit()
        return result


async def record_error(session: AsyncSession, user_id: int, message: str) -> None:
    """Zamanlayici hatasini kullaniciya gostermek icin etkin kanallara yazar."""
    rows = await session.scalars(
        select(NotificationChannelEntity).where(
            NotificationChannelEntity.user_id == user_id
        )
    )
    for row in rows:
        row.last_error = message
    await session.commit()
