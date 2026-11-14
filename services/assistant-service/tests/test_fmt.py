"""Faz 13e — fmt_day_long."""

from datetime import date

from app.agent.fmt import fmt_day_long


def test_fmt_day_long_known_dates():
    assert fmt_day_long(date(2026, 11, 14)) == "Cumartesi 14 Kasım"
    assert fmt_day_long(date(2026, 11, 15)) == "Pazar 15 Kasım"


def test_fmt_day_long_covers_every_month_and_weekday():
    names = {fmt_day_long(date(2026, m, 1)).split()[2] for m in range(1, 13)}
    assert len(names) == 12
    days = {fmt_day_long(date(2026, 11, d)).split()[0] for d in range(2, 9)}
    assert len(days) == 7
