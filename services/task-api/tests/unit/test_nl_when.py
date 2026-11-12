"""Turkce zaman ifadesi ayristiricisi (app/services/nl_when.py) tablo testleri."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.nl_when import fold, parse_when

TZ = ZoneInfo("Europe/Istanbul")
NOW = datetime(2026, 11, 12, 10, 0, tzinfo=TZ)  # Persembe


def L(y, m, d, h=23, mi=59):
    return datetime(y, m, d, h, mi, tzinfo=TZ)


# (id, metin, week_start, due, has_time, dk, clean_title, label|None)
POSITIVE = [
    ("P1", "Fatura öde yarın 15'te", 0, L(2026, 11, 13, 15, 0), True, None, "Fatura öde", "📅 Cum 13 Kas 15:00"),
    ("P2", "Rapor yaz yarın", 0, L(2026, 11, 13), False, None, "Rapor yaz", "📅 Cum 13 Kas"),
    ("P3", "Toplantı bugün saat 14:30", 0, L(2026, 11, 12, 14, 30), True, None, "Toplantı", "📅 Per 12 Kas 14:30"),
    ("P4", "Spor öbür gün", 0, L(2026, 11, 14), False, None, "Spor", "📅 Cmt 14 Kas"),
    ("P5", "Ödev cumaya", 0, L(2026, 11, 13), False, None, "Ödev", None),
    ("P6", "Market perşembe", 0, L(2026, 11, 12), False, None, "Market", None),
    ("P7", "Market perşembe 9'da", 0, L(2026, 11, 19, 9, 0), True, None, "Market", None),
    ("P8", "Sunum önümüzdeki perşembe", 0, L(2026, 11, 19), False, None, "Sunum", None),
    ("P9", "Sunum önümüzdeki cuma", 0, L(2026, 11, 13), False, None, "Sunum", None),
    ("P10", "Sunum haftaya cuma", 0, L(2026, 11, 20), False, None, "Sunum", None),
    ("P10b", "Sunum haftaya cuma", 6, L(2026, 11, 20), False, None, "Sunum", None),
    ("P11", "Yürüyüş haftaya pazar", 0, L(2026, 11, 22), False, None, "Yürüyüş", None),
    ("P12", "Yürüyüş haftaya pazar", 6, L(2026, 11, 15), False, None, "Yürüyüş", None),
    ("P13", "Diş hekimi haftaya salı 10:00 1,5 saat", 0, L(2026, 11, 17, 10, 0), True, 90, "Diş hekimi", "📅 Sal 17 Kas 10:00 · ⏱ 1 sa 30 dk"),
    ("P14", "Okuma bu cumartesi", 0, L(2026, 11, 14), False, None, "Okuma", None),
    ("P15", "Planlama bu pazartesi", 0, L(2026, 11, 16), False, None, "Planlama", None),
    ("P16", "Raporu bitir bu hafta", 0, L(2026, 11, 15), False, None, "Raporu bitir", None),
    ("P17", "Raporu bitir bu hafta", 6, L(2026, 11, 14), False, None, "Raporu bitir", None),
    ("P18", "Temizlik hafta sonu", 0, L(2026, 11, 14), False, None, "Temizlik", None),
    ("P19", "Proje haftaya", 0, L(2026, 11, 16), False, None, "Proje", None),
    ("P20", "Proje haftaya", 6, L(2026, 11, 15), False, None, "Proje", None),
    ("P21", "Vergi 14 kasım", 0, L(2026, 11, 14), False, None, "Vergi", "📅 Cmt 14 Kas"),
    ("P22", "Vergi 5 ocak", 0, L(2027, 1, 5), False, None, "Vergi", "📅 Sal 5 Oca 2027"),
    ("P23", "Telefon 10 Kasım'da", 0, L(2027, 11, 10), False, None, "Telefon", "📅 Çar 10 Kas 2027"),
    ("P24", "Kira 1.12", 0, L(2026, 12, 1), False, None, "Kira", "📅 Sal 1 Ara"),
    ("P25", "Kira 01/12/2026", 0, L(2026, 12, 1), False, None, "Kira", None),
    ("P26", "Kira 2026-12-01", 0, L(2026, 12, 1), False, None, "Kira", None),
    ("P27", "Sınav 3 gün sonra", 0, L(2026, 11, 15), False, None, "Sınav", None),
    ("P28", "Kontrol iki hafta sonra", 0, L(2026, 11, 26), False, None, "Kontrol", None),
    ("P29", "Ara ver saat 3", 0, L(2026, 11, 12, 15, 0), True, None, "Ara ver", None),
    ("P30", "Uyan sabah 7", 0, L(2026, 11, 13, 7, 0), True, None, "Uyan", None),
    ("P31", "Film akşam 8'de", 0, L(2026, 11, 12, 20, 0), True, None, "Film", None),
    ("P32", "Ders yarın akşam", 0, L(2026, 11, 13, 19, 0), True, None, "Ders", None),
    ("P33", "Yürüyüş bu akşam", 0, L(2026, 11, 12, 19, 0), True, None, "Yürüyüş", None),
    ("P34", "Rapor 2 saat", 0, None, False, 120, "Rapor", "⏱ 2 sa"),
    ("P35", "Okuma 30 dk", 0, None, False, 30, "Okuma", "⏱ 30 dk"),
    ("P36", "Okuma yarım saat", 0, None, False, 30, "Okuma", None),
    ("P37", "Kodlama 1 saat 30 dk", 0, None, False, 90, "Kodlama", "⏱ 1 sa 30 dk"),
    ("P38", "Kodlama bir buçuk saat", 0, None, False, 90, "Kodlama", None),
    ("P39", "Kodlama 1.5 saat", 0, None, False, 90, "Kodlama", None),
    ("P40", "3 saatlik çalışma", 0, None, False, 180, "çalışma", None),
    ("P41", "Toplantı yarın 15-17 arası", 0, L(2026, 11, 13, 15, 0), True, 120, "Toplantı", "📅 Cum 13 Kas 15:00 · ⏱ 2 sa"),
    ("P42", "Toplantı 14:00-15:30", 0, L(2026, 11, 12, 14, 0), True, 90, "Toplantı", None),
    ("P43", "Fatura ayın 20'si", 0, L(2026, 11, 20), False, None, "Fatura", None),
    ("P44", "yarın 15'te", 0, L(2026, 11, 13, 15, 0), True, None, "yarın 15'te", None),
    ("P45", "Yayın 00:30", 0, L(2026, 11, 13, 0, 30), True, None, "Yayın", None),
    ("P46", "Pazar günü yürüyüş", 0, L(2026, 11, 15), False, None, "Yürüyüş", None),
    ("P47", "Fatura öde cuma", 0, L(2026, 11, 13), False, None, "Fatura öde", None),
    ("P48", "Cuma 15'te toplantı", 0, L(2026, 11, 13, 15, 0), True, None, "Toplantı", None),
    ("P49", "YARIN 15:00 Rapor", 0, L(2026, 11, 13, 15, 0), True, None, "Rapor", None),
    ("P50", "Rapor yarin 15te", 0, L(2026, 11, 13, 15, 0), True, None, "Rapor", None),
    ("P51", "Yarın fatura öde 15'te", 0, L(2026, 11, 13, 15, 0), True, None, "Fatura öde", None),
    ("P52", "Rapor için yarın", 0, L(2026, 11, 13), False, None, "Rapor", None),
    ("P53", "2 saat pil testi", 0, None, False, 120, "pil testi", None),
    ("P54", "Yarın kitabını oku", 0, L(2026, 11, 13), False, None, "Kitabını oku", None),
]


@pytest.mark.parametrize(
    "pid,text,ws,due,has_time,minutes,clean,label",
    POSITIVE,
    ids=[p[0] for p in POSITIVE],
)
def test_positive(pid, text, ws, due, has_time, minutes, clean, label):
    m = parse_when(text, NOW, TZ, ws)
    assert m is not None, text
    if due is None:
        assert m.due_date is None
    else:
        assert m.due_date is not None
        assert m.due_date == due
        assert m.due_date.astimezone(TZ).hour == due.hour
    assert m.has_time is has_time
    assert m.estimated_minutes == minutes
    assert m.clean_title == clean
    if label is not None:
        assert m.label == label


NEGATIVE = [
    "Pazar araştırması",
    "Cuma namazı",
    "iPhone 15 kılıf",
    "Akşam yemeği hazırla",
    "Sabah koşusu",
    "Kitap 3-4 sayfa oku",
    "Bölüm 2.5'i oku",
    "Ekim ayı raporu",
    "Ara toplantı",
    "Saat tamiri",
    "Mayıs bütçesi",
    "Tez 15 sayfa",
    "Sürüm v2.10 yayınla",
    "Bugünlük notlar",
    "Saat 25'te",
    "31.02 kontrol",
    "",
    "Fatura",
]


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative(text):
    assert parse_when(text, NOW, TZ, 0) is None


def test_fold_keeps_length():
    s = "İstanbul IŞIK"
    assert len(fold(s)) == len(s)
    assert fold("İĞNE Işık") == "igne isik"


def test_p51_spans_two_ascending():
    m = parse_when("Yarın fatura öde 15'te", NOW, TZ, 0)
    assert len(m.spans) == 2
    assert m.spans[0][1] <= m.spans[1][0]
    assert m.spans[0] < m.spans[1]


def test_phrase_p13():
    m = parse_when("Diş hekimi haftaya salı 10:00 1,5 saat", NOW, TZ, 0)
    assert m.phrase == "haftaya salı 10:00 1,5 saat"


def test_naive_now_is_utc():
    naive = datetime(2026, 11, 12, 22, 30)  # UTC -> Istanbul 13 Kas 01:30
    m = parse_when("Rapor yarın", naive, TZ, 0)
    assert m.due_date == L(2026, 11, 14)


def test_long_text_no_error():
    parse_when("a " * 300 + "yarın", NOW, TZ, 0)
    parse_when("x" * 5000, NOW, TZ, 0)


def test_year_rollover_month_name():
    now = datetime(2026, 12, 20, 10, 0, tzinfo=TZ)
    m = parse_when("Vergi 5 ocak", now, TZ, 0)
    assert m.due_date == L(2027, 1, 5)


def test_ayin_past_day_goes_next_month():
    now = datetime(2026, 11, 25, 10, 0, tzinfo=TZ)
    m = parse_when("Fatura ayın 20'si", now, TZ, 0)
    assert m.due_date == L(2026, 12, 20)


def test_ayin_missing_day_clamps_to_last():
    now = datetime(2027, 2, 1, 10, 0, tzinfo=TZ)
    m = parse_when("Fatura ayın 31'i", now, TZ, 0)
    assert m.due_date == L(2027, 2, 28)


def test_timezone_utc_vs_istanbul():
    now = datetime(2026, 11, 12, 22, 30, tzinfo=UTC)
    m = parse_when("Rapor yarın", now, ZoneInfo("UTC"), 0)
    assert m.due_date == datetime(2026, 11, 13, 23, 59, tzinfo=ZoneInfo("UTC"))
    m = parse_when("Rapor yarın", now, TZ, 0)
    assert m.due_date == L(2026, 11, 14)


# Faz 10 denetim duzeltmesi (D1, D4)
D1_D4 = [
    ("D1a", "Ders 10.05'te", L(2026, 11, 12, 10, 5), True, None, "Ders"),
    ("D1b", "Ders 10.10'da", L(2026, 11, 12, 10, 10), True, None, "Ders"),
    ("D1c", "Görüşme 1.12'de", L(2026, 12, 1), False, None, "Görüşme"),
    ("D1d", "Ödev 3.10'a kadar", L(2026, 10, 3).replace(year=2027), False, None, "Ödev"),
    ("D1e", "Proje 10 Kasım 2026'da", L(2026, 11, 10), False, None, "Proje"),
    ("D4c", "ders 11-2 arası", L(2026, 11, 12, 11, 0), True, 180, "ders"),
]


@pytest.mark.parametrize("text", ["toplantı 10:30-09:00", "toplantı 18:00-18:00"])
def test_audit_invalid_range_not_split(text):
    assert parse_when(text, NOW, TZ, 0) is None


@pytest.mark.parametrize(
    "pid,text,due,has_time,minutes,clean", D1_D4, ids=[p[0] for p in D1_D4]
)
def test_audit_fixes(pid, text, due, has_time, minutes, clean):
    m = parse_when(text, NOW, TZ, 0)
    assert m is not None, text
    assert m.due_date == due
    assert m.has_time is has_time
    assert m.estimated_minutes == minutes
    assert m.clean_title == clean


def test_known_false_positive_oda_12de():
    """K10'da bilerek kabul edilen yanlis pozitif (belge amacli, davranis kilidi)."""
    m = parse_when("Oda 12'de toplantı", NOW, TZ, 0)
    assert m is not None
    assert m.due_date == L(2026, 11, 12, 12, 0)
    assert m.clean_title == "Oda toplantı"
