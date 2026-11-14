"""Gun donumu (Faz 13c, T4): gece rollover saatine kadar 'yarin' uyandigin gundur. Saf."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.services.nl_when import WhenMatch, parse_when


def utc_now() -> datetime:
    """Saat kaynagi (testlerde monkeypatch edilir)."""
    return datetime.now(UTC)


def planning_now(now_local: datetime, rollover: time) -> tuple[datetime, bool]:
    """Saat < rollover ise bir onceki gunun 23:59'u ve True; degilse (now, False)."""
    if now_local.time() < rollover:
        prev = now_local.date() - timedelta(days=1)
        return (
            datetime.combine(prev, time(23, 59), tzinfo=now_local.tzinfo),
            True,
        )
    return now_local, False


def parse_with_rollover(
    text: str, now: datetime, tz: ZoneInfo, week_start: int, rollover: time
) -> WhenMatch | None:
    """parse_when + gun donumu kurali: sonuc takvimsel bugunden onceyse gercek saatle coz."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    local = now.astimezone(tz)
    shifted, rolled = planning_now(local, rollover)
    m = parse_when(text, shifted, tz, week_start)
    if (
        rolled
        and m is not None
        and m.due_date is not None
        and m.due_date.astimezone(tz).date() < local.date()
    ):
        m = parse_when(text, now, tz, week_start)
    return m
