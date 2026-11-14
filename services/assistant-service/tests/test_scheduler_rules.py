"""Faz 13f: zamanlama tablosu (saf kural) - pencere ici/disi, kacirilan, tekrar."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.scheduler_rules import SchedCfg, due_jobs

TZ = ZoneInfo("Europe/Istanbul")


def at(y, m, d, hh, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def kinds(now, cfg=None, runs=None):
    return dict(due_jobs(now, cfg or SchedCfg(), runs or set()))


# 2026-11-10 Sali, 2026-11-15 Pazar, 2026-11-16 Pazartesi
def test_night_plan_window_and_target_day():
    assert kinds(at(2026, 11, 10, 22, 29)).get("night_plan") is None
    assert kinds(at(2026, 11, 10, 22, 30))["night_plan"] == "2026-11-11"
    assert (
        kinds(at(2026, 11, 11, 1, 29))["night_plan"] == "2026-11-11"
    )  # gece yarisini gecer
    assert "night_plan" not in kinds(at(2026, 11, 11, 1, 30))  # pencere (3 sa) bitti


def test_night_plan_crossing_midnight_2330_to_0010():
    cfg = SchedCfg(planning_time=time(23, 30))
    assert kinds(at(2026, 11, 10, 23, 45), cfg)["night_plan"] == "2026-11-11"
    # 00:10'da hedef gun degismez: dunun "yarin"i = takvim bugunu
    assert kinds(at(2026, 11, 11, 0, 10), cfg)["night_plan"] == "2026-11-11"


def test_night_plan_target_with_rollover():
    # planlama 02:00, gun donumu 04:00: mantiksal gun dun, hedef takvim bugunu
    cfg = SchedCfg(planning_time=time(2, 0), rollover=time(4, 0))
    assert kinds(at(2026, 11, 11, 2, 15), cfg)["night_plan"] == "2026-11-11"
    cfg2 = SchedCfg(planning_time=time(22, 30), rollover=time(4, 0))
    assert kinds(at(2026, 11, 10, 22, 40), cfg2)["night_plan"] == "2026-11-11"


def test_morning_window_default_and_missed():
    assert "morning" not in kinds(at(2026, 11, 10, 7, 29))
    assert kinds(at(2026, 11, 10, 7, 30))["morning"] == "2026-11-10"
    assert kinds(at(2026, 11, 10, 11, 59))["morning"] == "2026-11-10"
    assert "morning" not in kinds(at(2026, 11, 10, 12, 0))  # kacirildi: atla


def test_morning_earlier_with_template():
    cfg = SchedCfg(template_first_start=time(7, 0))  # 07:00 - 15 dk = 06:45
    assert kinds(at(2026, 11, 10, 6, 44), cfg).get("morning") is None
    assert kinds(at(2026, 11, 10, 6, 45), cfg)["morning"] == "2026-11-10"
    late = SchedCfg(template_first_start=time(9, 0))  # sabah saatinden gec: 07:30 kalir
    assert "morning" not in kinds(at(2026, 11, 10, 7, 29), late)
    assert kinds(at(2026, 11, 10, 7, 30), late)["morning"] == "2026-11-10"
    early = SchedCfg(template_first_start=time(0, 5))  # 00:00'in oncesine tasmaz
    assert kinds(at(2026, 11, 10, 0, 0), early)["morning"] == "2026-11-10"


def test_overdue_window():
    assert "overdue" not in kinds(at(2026, 11, 10, 12, 29))
    assert kinds(at(2026, 11, 10, 12, 30))["overdue"] == "2026-11-10"
    assert kinds(at(2026, 11, 10, 22, 59))["overdue"] == "2026-11-10"
    assert "overdue" not in kinds(at(2026, 11, 10, 23, 0))


def test_weekly_sunday_and_monday_window():
    assert "weekly" not in kinds(at(2026, 11, 15, 19, 59))
    assert kinds(at(2026, 11, 15, 20, 0))["weekly"] == "2026-W46"
    assert kinds(at(2026, 11, 15, 23, 59))["weekly"] == "2026-W46"
    # Pazartesi 11:59 hala gonderir, 12:01 atlar; anahtar PAZAR'in haftasi
    assert kinds(at(2026, 11, 16, 11, 59))["weekly"] == "2026-W46"
    assert "weekly" not in kinds(at(2026, 11, 16, 12, 1))
    assert "weekly" not in kinds(at(2026, 11, 14, 21, 0))  # Cumartesi


def test_weekly_custom_review_time():
    cfg = SchedCfg(review_time=time(18, 0))
    assert kinds(at(2026, 11, 15, 18, 0), cfg)["weekly"] == "2026-W46"


def test_recorded_period_does_not_repeat():
    now = at(2026, 11, 10, 22, 40)
    assert kinds(now, runs={("night_plan", "2026-11-11")}).get("night_plan") is None
    # baska periyot kaydi engellemez
    assert kinds(now, runs={("night_plan", "2026-11-10")})["night_plan"] == "2026-11-11"
    # baska turun kaydi engellemez
    assert kinds(now, runs={("morning", "2026-11-11")})["night_plan"] == "2026-11-11"


def test_disabled_kinds_never_due():
    cfg = SchedCfg(
        kinds={"night_plan": False, "morning": False, "overdue": False, "weekly": False}
    )
    assert due_jobs(at(2026, 11, 15, 22, 40), cfg, set()) == []
    only = SchedCfg(
        kinds={"night_plan": False, "morning": True, "overdue": True, "weekly": True}
    )
    assert "night_plan" not in dict(due_jobs(at(2026, 11, 10, 22, 40), only, set()))
