"""Faz 13h2 (G1): hafiza yakin tekrar eslestirici - dusman girdi tablosu."""

from types import SimpleNamespace

import pytest

from app.tools.fact_similarity import hours, near_duplicate, tokens


def fact(category: str, content: str):
    return SimpleNamespace(category=category, content=content)


R = "routine"
CASES = [
    (R, "Sabah 7-9 işe gider, akşam 18-20 döner", R, "Ofis günlerinde ~07:00 çıkar ~20:00 eve döner", True),
    (R, "09:00–18:00 arasına iş dışı plan yapılmamalı", R, "Evden çalışınca 09:00-18:00 mesai, 12:00-13:00 öğle", False),
    (R, "Spor salonuna haftada 3 gün gider", R, "Haftada 3 gün spor salonuna gidiyor", True),
    (R, "Kahveyi şekersiz içer", R, "Çayı şekersiz içer", False),
    (R, "Saat 9'da kalkar", R, "Saat 9'da yatar", False),
    (R, "Salı ve perşembe ofiste", R, "Salı ve perşembe ofiste çalışır", True),
    (R, "Pazartesi 18:00-19:00 İngilizce kursu", R, "Cuma 18:00-19:00 yüzme", False),
    (R, "Uykuya 00:00-01:00 arası yatar", R, "Gece 00:00-01:00 arası telefona bakmaz", True),
    ("relationship", "Annesinin doğum günü 12 Mart", R, "Annesinin doğum günü 12 Mart", False),
    (R, "Öğle arası 12-13", R, "Öğle yemeğini 12:30'da yer", False),
    (R, "Hafta sonu geç kalkar", R, "Hafta içi erken kalkar", False),
    (R, "", R, "Herhangi", False),
]  # fmt: skip


@pytest.mark.parametrize("ca,a,cb,b,expected", CASES)
def test_near_duplicate_table(ca, a, cb, b, expected):
    assert near_duplicate(fact(ca, a), fact(cb, b)) is expected
    assert near_duplicate(fact(cb, b), fact(ca, a)) is expected  # simetrik


def test_hours_only_hour_part_and_no_minute_range_leak():
    assert hours("Ofis ~07:30 çıkar") == {7}
    assert hours("12:00-13:00 öğle") == {12, 13}  # "00-13" dakika sızıntısı yok
    assert hours("Sabah 7-9 işe gider") == {7, 9}
    assert hours("Saat 99:00 ve 30-40") == set()  # 0-24 dışı atılır


def test_tokens_fold_and_stopwords():
    assert tokens("İşe gider, her gün bir kez ve ile için") == {"ise", "gider", "gun", "kez"}
    assert tokens("07:00 18") == set()  # rakamlar < 3 harf: sayılmaz
