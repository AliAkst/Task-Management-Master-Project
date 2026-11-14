"""Faz 13d — match_answer (G1 düşman girdileri, n=3)."""

import pytest

from app.agent.answers import match_answer


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1", 1),
        ("1.", 1),
        ("2)", 2),
        (" 3 ", 3),
        ("2'yi", 2),
        ("ikincisi", 2),
        ("seçenek 2", 2),
        ("2 olsun", 2),
        ("birinci olsun", 1),
        ("ilk", 1),
        ("üçüncü", 3),
        ("4", None),  # aralık dışı
        ("12", None),
        ("0", None),
        ("1 saat sonra", None),
        ("2 saat spor yapacağım", None),
        ("yarın 1'de", None),
        ("1,5 saat", None),
        ("1.5", None),
        ("bir", None),  # sayı sözcüğü kabul edilmez
        ("ilk önce markete gideyim", None),
        ("vazgeç", "cancel"),
        ("iptal et", "cancel"),
        ("hiçbiri", "cancel"),
        ("Vazgeç.", "cancel"),
        ("iptal edilen toplantıyı ekle", None),
        ("vazgeçtim, yarın spor ekle", None),
        ("", None),
        ("   ", None),
    ],
)
def test_match_answer(text, expected):
    assert match_answer(text, 3) == expected


def test_match_answer_respects_option_count():
    assert match_answer("3", 2) is None
    assert match_answer("ikinci", 1) is None
    assert match_answer("4", 4) == 4
    assert match_answer("dördüncüsü", 4) == 4


def test_match_answer_long_text_is_never_an_answer():
    assert match_answer("1 " + "x" * 40, 3) is None
    assert match_answer("vazgeç " + "x" * 40, 3) is None
