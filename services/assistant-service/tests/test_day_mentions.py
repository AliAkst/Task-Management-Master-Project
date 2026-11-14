"""Faz 13d — metinden gün ipucu (G1 düşman girdileri) ve gün dönümlü gün çözümü."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.agent.day_mentions import day_mentions
from app.tools.schedule_day import resolve_day, resolve_day_ex

TZ = ZoneInfo("Europe/Istanbul")
ROLLOVER = time(4, 0)
FRI_2324 = datetime(2026, 11, 13, 23, 24, tzinfo=TZ)  # Cuma
SAT_0030 = datetime(2026, 11, 14, 0, 30, tzinfo=TZ)  # Cumartesi, gün dönümünden önce
FRI_1000 = datetime(2026, 11, 13, 10, 0, tzinfo=TZ)


def nov(*days: int) -> list[date]:
    return [date(2026, 11, d) for d in days]


@pytest.mark.parametrize(
    ("text", "at_2324", "at_0030"),
    [
        ("Cumartesi planlayalım. Yarın spor", [14], [14]),
        ("yarın planla", [14], [14]),
        ("bugün ve yarın", [13, 14], [14]),  # ikisi de 14 -> tek
        ("Yarın pazara gideceğim", [14], [14]),
        ("pazar günü kahvaltı", [15], [15]),
        ("her salı spor yaparım, yarını planla", [14], [14]),
        ("salıları ofisteyim", [], []),
        ("cumaya kadar bitir, yarını planla", [14], [14]),
        ("geçen cuma çok yoruldum", [], []),
        ("haftaya salı toplantı", [], []),
        ("14 Kasım'da kuyumcu", [14], [14]),
        ("2026-11-20 için plan", [20], [20]),
        ("dün spor yaptım bugün dinleneceğim", [13], [14]),
        ("saat 10'da toplantı", [], []),
        ("3 gün sonra", [], []),
        ("cumartesiye kuyumcu, pazara market", [14], [14]),
        ("Salı ofisteyim, çarşamba evden", [17, 18], [17, 18]),
        ("akşam 7'de spor", [], []),
        ("Yarin sabah", [14], [14]),
    ],
)
def test_day_mentions_table(text, at_2324, at_0030):
    assert day_mentions(text, FRI_2324, ROLLOVER) == nov(*at_2324)
    assert day_mentions(text, SAT_0030, ROLLOVER) == nov(*at_0030)


def test_day_mentions_friday_prayer_on_friday_morning():
    assert day_mentions("cuma namazından sonra", FRI_1000, ROLLOVER) == nov(13)


def test_day_mentions_empty_and_garbage():
    assert day_mentions("", FRI_2324, ROLLOVER) == []
    assert day_mentions("31 Şubat", FRI_2324, ROLLOVER) == []  # geçersiz tarih


def test_day_mentions_is_sorted_and_unique():
    out = day_mentions("çarşamba, salı ve tekrar salı", FRI_2324, ROLLOVER)
    assert out == nov(17, 18)


# ---- resolve_day_ex (T4)
def test_resolve_day_ex_before_rollover_uses_yesterday_as_base():
    d, rolled = resolve_day_ex(
        "yarın", SAT_0030.date(), now_local=SAT_0030, rollover=ROLLOVER
    )
    assert d == date(2026, 11, 14) and rolled is True
    # bugün: dünü değil takvimsel bugünü verir
    d, _ = resolve_day_ex("bugün", SAT_0030.date(), now_local=SAT_0030, rollover=ROLLOVER)
    assert d == date(2026, 11, 14)
    # geçmişe düşen hafta günü bugün baz alınarak yeniden çözülür
    d, _ = resolve_day_ex("cuma", SAT_0030.date(), now_local=SAT_0030, rollover=ROLLOVER)
    assert d == date(2026, 11, 20)


def test_resolve_day_ex_after_rollover_is_plain_and_iso_unaffected():
    noon = datetime(2026, 11, 14, 12, 0, tzinfo=TZ)
    assert resolve_day_ex("yarın", noon.date(), now_local=noon, rollover=ROLLOVER) == (
        date(2026, 11, 15),
        False,
    )
    d, rolled = resolve_day_ex(
        "2026-11-20", SAT_0030.date(), now_local=SAT_0030, rollover=ROLLOVER
    )
    assert d == date(2026, 11, 20) and rolled is False


def test_resolve_day_signature_and_behavior_unchanged():
    assert resolve_day("yarın", date(2026, 11, 8)) == date(2026, 11, 9)
    assert resolve_day_ex("yarın", date(2026, 11, 8)) == (date(2026, 11, 9), False)
