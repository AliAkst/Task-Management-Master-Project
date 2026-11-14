"""Faz 13g (G1): kurs parcasi dogal siralama ayristiricisi - dusman girdiler."""

import pytest

from app.services.learning import course_sort_key

# (baslik, beklenen grup, beklenen anahtar; grup 0 disinda anahtar kontrol edilmez)
CASES = [
    ("P1 — Giriş", 0, ("p", 1)),
    ("P10 Modelleme", 0, ("p", 10)),
    ("p2: veri kalitesi", 0, ("p", 2)),
    ("F 3 Lakehouse", 0, ("f", 3)),
    ("F-12", 0, ("f", 12)),
    ("P2 (Opsiyonel) ek okuma", 2, None),
    ("Opsiyonel: proje", 2, None),
    ("2024 güncellemesi", 1, None),
    ("Power BI temelleri", 1, None),
    ("PBI101 ders", 0, ("pbi", 101)),
    ("P1000 uzun", 1, None),
    ("ABCD1 test", 1, None),
    ("Bölüm 3", 1, None),
    ("P3a", 0, ("p", 3)),
    ("  P4  ", 0, ("p", 4)),
]


@pytest.mark.parametrize(("title", "group", "key"), CASES)
def test_course_sort_key(title, group, key):
    got = course_sort_key(title, 5.0)
    assert got[0] == group
    if key is not None:
        assert got[1] == key
    assert got[2] == 5.0


def test_p10_sorts_after_p2():
    titles = ["P10 Modelleme", "P2 Veri", "P1 Giriş", "Ek not", "P3 (OPSİYONEL) ek"]
    ordered = sorted(titles, key=lambda t: course_sort_key(t, titles.index(t)))
    assert ordered == ["P1 Giriş", "P2 Veri", "P10 Modelleme", "Ek not", "P3 (OPSİYONEL) ek"]


def test_ungrouped_titles_keep_position_order():
    a = course_sort_key("Power BI temelleri", 2.0)
    b = course_sort_key("Veri modelleme", 1.0)
    assert sorted([a, b]) == [b, a]
