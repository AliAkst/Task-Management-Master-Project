from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.services.planning_day import parse_with_rollover, planning_now

TZ = ZoneInfo("Europe/Istanbul")


def _at(h: int, m: int) -> datetime:
    return datetime(2026, 11, 14, h, m, tzinfo=TZ)  # Cumartesi


class TestPlanningNow:
    def test_midnight_is_rolled(self):
        shifted, rolled = planning_now(_at(0, 0), time(4, 0))
        assert rolled is True
        assert shifted == datetime(2026, 11, 13, 23, 59, tzinfo=TZ)

    def test_before_rollover_is_rolled(self):
        assert planning_now(_at(3, 59), time(4, 0))[1] is True

    def test_at_rollover_is_not_rolled(self):
        now = _at(4, 0)
        assert planning_now(now, time(4, 0)) == (now, False)

    def test_end_of_day_is_not_rolled(self):
        now = _at(23, 59)
        assert planning_now(now, time(4, 0)) == (now, False)

    def test_custom_rollover(self):
        assert planning_now(_at(2, 15), time(2, 30))[1] is True
        assert planning_now(_at(2, 30), time(2, 30))[1] is False

    def test_zero_rollover_never_rolls(self):
        assert planning_now(_at(0, 0), time(0, 0))[1] is False


class TestParseWithRollover:
    def test_afternoon_unchanged(self):
        m = parse_with_rollover("yarın", _at(14, 0), TZ, 0, time(4, 0))
        assert m.due_date.date().isoformat() == "2026-11-15"

    def test_after_midnight_tomorrow_is_same_calendar_day(self):
        m = parse_with_rollover("yarın", _at(0, 30), TZ, 0, time(4, 0))
        assert m.due_date.date().isoformat() == "2026-11-14"

    def test_fallback_keeps_today_evening(self):
        m = parse_with_rollover("bu akşam film", _at(0, 30), TZ, 0, time(4, 0))
        assert m.due_date.isoformat() == "2026-11-14T19:00:00+03:00"

    def test_absolute_date_unaffected(self):
        m = parse_with_rollover("14 kasım fatura", _at(0, 30), TZ, 0, time(4, 0))
        assert m.due_date.date().isoformat() == "2026-11-14"
