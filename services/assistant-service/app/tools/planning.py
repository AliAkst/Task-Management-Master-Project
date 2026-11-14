"""Planlama baglami (Faz 13d): kullanicinin yerel saati ve gun donumu (day_rollover)."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.tools.task_api import TaskApiClient, TaskApiError

DEFAULT_ROLLOVER = time(4, 0)


def parse_rollover(value: object) -> time:
    """'04:00' / '04:00:00' -> time; bos ya da bozuk -> 04:00."""
    try:
        h, m = str(value).split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, TypeError):
        return DEFAULT_ROLLOVER


async def planning_context(
    api: TaskApiClient,
    tz: ZoneInfo,
    now: datetime | None = None,
    rollover: time | None = None,
) -> tuple[datetime, time]:
    """-> (simdi yerel, rollover). `rollover` onbellekten gelirse ayar okunmaz;
    ayar okunamazsa 04:00."""
    if rollover is None:
        rollover = DEFAULT_ROLLOVER
        try:
            data = await api.get("/settings/")
            if data.get("day_rollover"):
                rollover = parse_rollover(data["day_rollover"])
        except TaskApiError:
            pass
    return (now.astimezone(tz) if now else datetime.now(tz)), rollover
