"""
Kullanicinin saat dilimine gore "gun" hesaplari.

Veritabaninda her sey UTC; "bugun", "gece yarisi", "saat 9-10 arasi" ise
kullanicinin yerel saatine gore. Gece yarisini asan calisma oturumlari
gunlere (ve saatlere) bolunerek sayilir.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.db.entities import TimeSessionEntity
from app.db.unit_of_work import TaskUnitOfWork

DEFAULT_TZ = "Europe/Istanbul"


async def user_tz(uow: TaskUnitOfWork, user_id: int) -> ZoneInfo:
    settings = await uow.user_settings.get_by_user_id(user_id)
    return ZoneInfo(settings.timezone if settings else DEFAULT_TZ)


def day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Yerel gunun [00:00, ertesi 00:00) araliginin UTC karsiligi."""
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def range_bounds(first: date, last: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[first, last] (dahil) gunlerinin UTC araligi."""
    return day_bounds(first, tz)[0], day_bounds(last, tz)[1]


def local_today(tz: ZoneInfo, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(tz).date()


def split_by_hour(
    start: datetime, end: datetime, tz: ZoneInfo
) -> Iterator[tuple[date, int, float]]:
    """[start, end) araligini yerel (gun, saat) parcalarina boler -> saniye."""
    cur = start
    while cur < end:
        local = cur.astimezone(tz)
        hour_start = local.replace(minute=0, second=0, microsecond=0)
        next_hour = (hour_start + timedelta(hours=1)).astimezone(UTC)
        step = min(end, next_hour)
        yield local.date(), local.hour, (step - cur).total_seconds()
        cur = step


def session_span(
    s: TimeSessionEntity,
    clip_start: datetime | None = None,
    clip_end: datetime | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime] | None:
    """Oturumun (calisiyorsa 'simdi'ye kadar) araliga kirpilmis hali."""
    start = s.started_at
    end = s.ended_at or (now or datetime.now(UTC))
    if clip_start is not None:
        start = max(start, clip_start)
    if clip_end is not None:
        end = min(end, clip_end)
    return (start, end) if end > start else None
