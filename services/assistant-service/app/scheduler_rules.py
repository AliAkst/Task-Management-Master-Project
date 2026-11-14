"""
Zamanlama kurallari (Faz 13f) - saf fonksiyon, G/C yok.

due_jobs(now_local, cfg, runs): simdi calismasi gereken (kind, period_key) listesi.
Pencere disinda kacirilan is atlanir (gec gelen "gece plani" hatirlatmasi anlamsiz).
Kayit olan periyot tekrar etmez.
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

NIGHT_PLAN = "night_plan"
MORNING = "morning"
OVERDUE = "overdue"
WEEKLY = "weekly"
FACTS_PURGE = "facts_purge"  # Faz 13h2: bildirim gondermez, kind ayari yok (hep acik)
ALL_KINDS = (NIGHT_PLAN, MORNING, OVERDUE, WEEKLY)

DEFAULT_PLANNING = time(22, 30)
DEFAULT_MORNING = time(7, 30)
DEFAULT_REVIEW = time(20, 0)
NIGHT_WINDOW = timedelta(hours=3)
MORNING_END = time(12, 0)
OVERDUE_START = time(12, 30)
OVERDUE_END = time(23, 0)


@dataclass
class SchedCfg:
    planning_time: time | None = None
    morning_time: time | None = None
    review_time: time | None = None
    rollover: time = time(0, 0)
    template_first_start: time | None = None
    kinds: dict[str, bool] = field(default_factory=lambda: {k: True for k in ALL_KINDS})


def week_key(day) -> str:
    iso = day.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _at(day, t: time, now: datetime) -> datetime:
    return datetime.combine(day, t, tzinfo=now.tzinfo)


def _night_plan(now: datetime, cfg: SchedCfg) -> str | None:
    t = cfg.planning_time or DEFAULT_PLANNING
    for back in (0, 1):  # pencere gece yarisini gecebilir
        base = now.date() - timedelta(days=back)
        start = _at(base, t, now)
        if start <= now < start + NIGHT_WINDOW:
            # T, gun donumunden onceyse mantiksal gun hala "dun": hedef takvim bugunu
            target = base if t < cfg.rollover else base + timedelta(days=1)
            return target.isoformat()
    return None


def _morning_time(cfg: SchedCfg) -> time:
    t = cfg.morning_time or DEFAULT_MORNING
    if cfg.template_first_start is not None:
        lead = cfg.template_first_start.hour * 60 + cfg.template_first_start.minute - 15
        lead = max(lead, 0)  # gece yarisinin oncesine tasmaz
        t = min(t, time(lead // 60, lead % 60))
    return t


def _in_morning(now: datetime, cfg: SchedCfg) -> bool:
    start = _at(now.date(), _morning_time(cfg), now)
    return start <= now < _at(now.date(), MORNING_END, now)


def _in_overdue(now: datetime) -> bool:
    day = now.date()
    return _at(day, OVERDUE_START, now) <= now < _at(day, OVERDUE_END, now)


def _weekly(now: datetime, cfg: SchedCfg) -> str | None:
    t = cfg.review_time or DEFAULT_REVIEW
    today = now.date()
    if today.weekday() == 6 and now >= _at(today, t, now):
        return week_key(today)
    if today.weekday() == 0 and now < _at(today, MORNING_END, now):
        return week_key(today - timedelta(days=1))
    return None


PURGE_START = time(3, 0)


def _facts_purge(now: datetime) -> str | None:
    """Pazar 03:00-23:59: pasif + 30 gunden eski hafiza kayitlarinin haftalik silinmesi."""
    today = now.date()
    if today.weekday() == 6 and now >= _at(today, PURGE_START, now):
        return week_key(today)
    return None


def due_jobs(
    now_local: datetime, cfg: SchedCfg, runs: set[tuple[str, str]]
) -> list[tuple[str, str]]:
    found: list[tuple[str, str | None]] = []
    if cfg.kinds.get(NIGHT_PLAN, True):
        found.append((NIGHT_PLAN, _night_plan(now_local, cfg)))
    if cfg.kinds.get(MORNING, True) and _in_morning(now_local, cfg):
        found.append((MORNING, now_local.date().isoformat()))
    if cfg.kinds.get(OVERDUE, True) and _in_overdue(now_local):
        found.append((OVERDUE, now_local.date().isoformat()))
    if cfg.kinds.get(WEEKLY, True):
        found.append((WEEKLY, _weekly(now_local, cfg)))
    found.append((FACTS_PURGE, _facts_purge(now_local)))
    return [(k, p) for k, p in found if p is not None and (k, p) not in runs]
