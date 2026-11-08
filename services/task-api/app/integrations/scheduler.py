"""
Arka plan senkron dongusu (Faz 7b): RabbitMQ/APScheduler yok; `lifespan`'da
bir asyncio gorevi her 15 dakikada aktif hesaplari senkronlar.
Ilk tur acilistan 30 sn sonra (uygulama hazir olsun diye).
"""

import asyncio

from app.core.logging import get_logger

logger = get_logger(__name__)

FIRST_DELAY_SEC = 30
INTERVAL_SEC = 15 * 60


async def run_once() -> None:
    """Tum entegrasyonlari bir kez senkronlar (biri hata verirse digerleri surer)."""
    from app.integrations import google_calendar, microsoft_todo

    for name, job in (
        ("google", google_calendar.sync_all_accounts),
        ("microsoft", microsoft_todo.sync_all_accounts),
    ):
        try:
            await job()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{name} senkron turu basarisiz: {e}")


async def sync_loop(
    first_delay: float = FIRST_DELAY_SEC, interval: float = INTERVAL_SEC
) -> None:
    await asyncio.sleep(first_delay)
    while True:
        await run_once()
        await asyncio.sleep(interval)
