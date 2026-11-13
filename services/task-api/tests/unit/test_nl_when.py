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


# ======================= Faz 11a =======================
import time as _time  # noqa: E402

NOW11 = datetime(2026, 11, 13, 10, 0, tzinfo=TZ)  # Cuma

_C = L(2026, 11, 14, 15, 0)
# (id, metin, due, has_time, dk, clean_title, strong)
FAZ11_POSITIVE = [
    ("F1", "yarın 15.00 da çalışacam", _C, True, None, "çalışacam", True),
    ("F2", "yarın 15.00 çalışacam", _C, True, None, "çalışacam", True),
    ("F3", "yarın 15:00 da çalışacam", _C, True, None, "çalışacam", True),
    ("F4", "yarın 15 te çalışacam", _C, True, None, "çalışacam", True),
    ("F5", "yarın 15 de çalışacam", _C, True, None, "çalışacam", True),
    ("F6", "yarın saat 15 de çalışacam", _C, True, None, "çalışacam", True),
    ("F7", "yarın 9.30 da dişçi", L(2026, 11, 14, 9, 30), True, None, "dişçi", True),
    ("F8", "yarın 10.05 te ders", L(2026, 11, 14, 10, 5), True, None, "ders", True),
    ("F9", "pazartesi 10 da toplantı", L(2026, 11, 16, 10, 0), True, None, "toplantı", True),
    ("F10", "sabah 9 da koş", L(2026, 11, 14, 9, 0), True, None, "koş", True),
    ("F11", "yarın 3 te gel", _C, True, None, "gel", True),
    ("F12", "saat 3 te gel", L(2026, 11, 13, 15, 0), True, None, "gel", True),
    ("F13", "yarın saat üçte gel", _C, True, None, "gel", True),
    ("F14", "sabah dokuzda koş", L(2026, 11, 14, 9, 0), True, None, "koş", True),
    ("F15", "cuma ya rapor", L(2026, 11, 13), False, None, "rapor", True),
    ("F16", "yarin aksam 8 de annemi ara", L(2026, 11, 14, 20, 0), True, None, "annemi ara", True),
    ("F17", "YARIN 15:00 TOPLANTI", _C, True, None, "TOPLANTI", True),
    ("F18", "carsamba 14.30 da sunum", L(2026, 11, 18, 14, 30), True, None, "sunum", True),
    ("F19", "yarın gidicem markete 10 da", L(2026, 11, 14, 10, 0), True, None, "gidicem markete", True),
    ("F20", "yarın 10.05 dişçi", L(2026, 11, 14, 10, 5), True, None, "dişçi", True),
    ("F21", "Toplantı 15'te", L(2026, 11, 13, 15, 0), True, None, "Toplantı", True),
    ("F22", "kendime spor yapacam yarın 8 gibi", L(2026, 11, 14, 8, 0), True, None, "kendime spor yapacam", True),
    ("F23", "cumartesi ye kadar bitir", L(2026, 11, 14), False, None, "bitir", True),
    ("R1", "toplantı 15.00-17.00", L(2026, 11, 13, 15, 0), True, 120, "toplantı", True),
    ("R2", "toplantı saat 3 ile 5 arası", L(2026, 11, 13, 15, 0), True, 120, "toplantı", True),
    ("R3", "toplantı 14:00'ten 16:00'ya kadar", L(2026, 11, 13, 14, 0), True, 120, "toplantı", True),
    ("R4", "toplantı öğleden sonra 2 ile 4 arasında", L(2026, 11, 13, 14, 0), True, 120, "toplantı", True),
    ("R5", "toplantı sabah 9 dan 11 e", L(2026, 11, 14, 9, 0), True, 120, "toplantı", True),
    ("R6", "toplantı sabah 9'dan 11'e", L(2026, 11, 14, 9, 0), True, 120, "toplantı", True),
    ("R7", "toplantı 15 ile 17 arasında", L(2026, 11, 13, 15, 0), True, 120, "toplantı", False),
    ("R8", "ders yarın 15-17", _C, True, 120, "ders", True),
    ("R9", "toplantı 15:00 ile 17:00 arası", L(2026, 11, 13, 15, 0), True, 120, "toplantı", True),
    ("R10", "yemek akşam 7-9 arası", L(2026, 11, 13, 19, 0), True, 120, "yemek", True),
    ("R11", "nöbet gece 11 ile 1 arası", L(2026, 11, 13, 23, 0), True, 120, "nöbet", True),
    ("R12", "toplantı 11-1 arası", L(2026, 11, 13, 11, 0), True, 120, "toplantı", False),
    ("R13", "yarın 15 ten 17 ye kadar ders", _C, True, 120, "ders", True),
    ("R14", "toplantı yarın 15-17 arası", _C, True, 120, "toplantı", True),
    ("R15", "ders 10.30-12.30", L(2026, 11, 13, 10, 30), True, 120, "ders", True),
    ("A1", "yarın akşam 8 gibi annemi ara", L(2026, 11, 14, 20, 0), True, None, "annemi ara", True),
    ("A2", "akşam 8 gibi annemi ara", L(2026, 11, 13, 20, 0), True, None, "annemi ara", True),
    ("A3", "15 civarı ara", L(2026, 11, 13, 15, 0), True, None, "ara", False),
    ("A4", "saat 8 gibi ara", L(2026, 11, 14, 8, 0), True, None, "ara", True),
    ("A5", "15.00 gibi ara", L(2026, 11, 13, 15, 0), True, None, "ara", True),
    ("A6", "3 sularında uğra", L(2026, 11, 13, 15, 0), True, None, "uğra", False),
    ("A7", "yarın 15 falan gel", _C, True, None, "gel", True),
    ("A8", "8 civarında kalk", L(2026, 11, 14, 8, 0), True, None, "kalk", False),
    ("G1", "öğlene doğru bitir", L(2026, 11, 13, 12, 0), True, None, "bitir", False),
    ("G2", "akşamüstü koş", L(2026, 11, 13, 17, 0), True, None, "koş", False),
    ("G3", "gece yarısı yedekle", L(2026, 11, 14, 0, 0), True, None, "yedekle", False),
    ("G4", "öğle arası yemek", L(2026, 11, 13, 12, 0), True, None, "yemek", False),
    ("G5", "akşama ara", L(2026, 11, 13, 19, 0), True, None, "ara", False),
    ("G6", "sabaha bitir", L(2026, 11, 14, 9, 0), True, None, "bitir", False),
    ("G7", "yarın öğlen yemek", L(2026, 11, 14, 12, 0), True, None, "yemek", True),
    ("G8", "aksamustu kos", L(2026, 11, 13, 17, 0), True, None, "kos", False),
    ("G9", "yarın akşamüstü spor", L(2026, 11, 14, 17, 0), True, None, "spor", True),
    ("G10", "yarın gece yarısı yedekle", L(2026, 11, 15, 0, 0), True, None, "yedekle", True),
    ("G11", "akşama kadar bitir", L(2026, 11, 13, 19, 0), True, None, "bitir", False),
    # K1, K2: bilerek kabul edilen yanlis pozitifler (web'de x ile reddedilir, asistanda zayif)
    ("K1", "Oyun 2 ile 3 arası puan", L(2026, 11, 13, 14, 0), True, 60, "Oyun puan", False),
    ("K2", "Gece yarısı kitabını oku", L(2026, 11, 14, 0, 0), True, None, "Kitabını oku", False),
]  # fmt: skip


@pytest.mark.parametrize(
    "pid,text,due,has_time,minutes,clean,strong",
    FAZ11_POSITIVE,
    ids=[p[0] for p in FAZ11_POSITIVE],
)
def test_faz11_positive(pid, text, due, has_time, minutes, clean, strong):
    m = parse_when(text, NOW11, TZ, 0)
    assert m is not None, text
    assert m.due_date == due, (m.due_date, due)
    assert m.has_time is has_time
    assert m.estimated_minutes == minutes
    assert m.clean_title == clean
    assert m.strong is strong


FAZ11_NEGATIVE = [
    "Bölüm 3 te kaldım", "10 da 1 indirim", "Kat 3 te", "3-5 kişilik masa",
    "sayfa 15-17 oku", "2-3 elma ye", "toplantı 9-11", "toplantı 15den 17ye kadar",
    "3'ten 5'e kadar say", "Bölüm 2'den 5'e oku", "1.5 litre su iç",
    "Fiyat 1.50-2.50", "Sürüm 15.00 notları", "Pazar da ekmek al", "Bir de süt al",
    "Onda kalsın", "4 gibi örnek yaz", "8 gibi annemi ara", "akşam bir film izle",
    "sabah bir de koşu", "Akşam yemeği hazırla", "iPhone 15 kılıf",
]  # fmt: skip


@pytest.mark.parametrize("text", FAZ11_NEGATIVE)
def test_faz11_negative(text):
    assert parse_when(text, NOW11, TZ, 0) is None


FAZ11_STRENGTH = [
    ("S1", "Pazartesi toplantısı notları", False),
    ("S2", "Perşembe pazarı alışverişi", False),
    ("S3", "Kat 2de toplantı", False),
    ("S4", "Sınav 1 saat önce gel", False),
    ("S5", "2 saat pil testi", False),
    ("S6", "Rapor 2 saat", True),
    ("S7", "Oda 12'de toplantı", False),
    ("S8", "Pazar günü yürüyüş", True),
    ("S9", "Ödev cumaya", True),
    ("S10", "Fatura öde cuma", False),
    ("S11", "3 saatlik çalışma", False),
    ("S12", "Market perşembe 9'da", True),
    ("S13", "yarın 15.00 da diş hekimi", True),
    ("S14", "toplantı yarın 15-17 arası", True),
    ("S15", "Kira 1.12", True),
]


@pytest.mark.parametrize("pid,text,strong", FAZ11_STRENGTH, ids=[p[0] for p in FAZ11_STRENGTH])
def test_faz11_strength(pid, text, strong):
    m = parse_when(text, NOW11, TZ, 0)
    assert m is not None, text
    assert m.strong is strong


@pytest.mark.parametrize(
    "text",
    [
        "15 da " * 33, "1 ile " * 40, "9 dan " * 30, "akşam " * 33, "15.00 " * 33,
        "yarın 3 te " * 18, "gece yarısı " * 16, "cuma ya " * 25, "8 gibi " * 28,
    ],
)  # fmt: skip
def test_faz11_redos(text):
    t0 = _time.perf_counter()
    parse_when(text, NOW11, TZ, 0)
    assert _time.perf_counter() - t0 < 0.02


def test_faz11_wordhour_map():
    from app.services.nl_when import _HW

    assert _HW["onbir"] == 11
    assert _HW["oniki"] == 12
    assert _HW["uc"] == 3


# ---- Faz 11 denetim duzeltmeleri (D1, D2, D3, D5, D8) ----
AUDIT11_NONE = [  # saat uretmemeli, eslesme olmamali
    "saat on beşte gel", "saat on üçte gel", "saat yedi buçukta gel",  # D1
    "her saat bir bardak su iç", "saat iki kere kontrol et",  # D2
    "toplantı 15.00-17.10",  # D5
]  # fmt: skip


@pytest.mark.parametrize("text", AUDIT11_NONE)
def test_audit11_none(text):
    assert parse_when(text, NOW11, TZ, 0) is None


AUDIT11_DAY_ONLY = [  # yalniz gun (14 Kas), saat yok, baslik bozulmaz
    ("yarın 15,00 da çalış", "15,00 da çalış"),  # D3
    ("yarın 10,00 da toplantı", "10,00 da toplantı"),  # D3
]  # fmt: skip


@pytest.mark.parametrize("text,rest", AUDIT11_DAY_ONLY)
def test_audit11_day_only(text, rest):
    m = parse_when(text, NOW11, TZ, 0)
    assert m is not None
    assert m.has_time is False
    assert (m.due_date.month, m.due_date.day) == (11, 14)
    assert rest in m.clean_title


@pytest.mark.parametrize(
    "text,due,clean",
    [
        ("yarın 3.05 de çalış", L(2026, 11, 14, 15, 5), "çalış"),  # D8
        ("yarın 2.10 da toplantı", L(2026, 11, 14, 14, 10), "toplantı"),  # D8
        ("yarın saat üçte gel", L(2026, 11, 14, 15, 0), "gel"),  # D2 korunur
        ("toplantı saat üç", L(2026, 11, 13, 15, 0), "toplantı"),  # D2: baslik sonu serbest
    ],
)
def test_audit11_positive(text, due, clean):
    m = parse_when(text, NOW11, TZ, 0)
    assert m is not None, text
    assert m.due_date == due
    assert m.has_time is True
    assert m.clean_title == clean
