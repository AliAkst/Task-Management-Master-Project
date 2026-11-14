"""Faz 13h1 (G1): süpürme eşleştiricileri - düşman girdi tablosu."""

import pytest

from app.services.sweep import is_done_list_hint, is_duplicate, is_old_list


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Old Todos", True),
        ("OLD JIRA TASKS", True),
        ("Golden tasks", False),
        ("Holder", False),
        ("Eski işler", True),
        ("Eskişehir gezisi", False),
        ("Arşiv", True),
        ("Archived", True),
        ("Completed(Same Week)", False),
    ],
)
def test_old_list(name, expected):
    assert is_old_list(name) is expected


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("P2", "P2 — Veri kalitesi", True),
        ("P2", "P12 — Modelleme", False),
        ("P2", "P2", True),
        ("Market", "market.", True),
        ("Market", "Market alışverişi", False),
        ("Eğitimlere bakma (P2, P3)", "P2", False),
        ("F1", "P1", False),
        ("  Kuyumcu  ", "kuyumcu", True),
        ("🛒 Market", "market", True),
        ("", "", False),
    ],
)
def test_duplicate(a, b, expected):
    assert is_duplicate(a, b) is expected
    assert is_duplicate(b, a) is expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Completed(Same Week)", True),
        ("Incomplete", False),
        ("Done-ish ideas", True),
        ("Tamamlanan", True),
        ("Bitti", True),
        ("Undone", False),
        ("Yapılacak", False),
    ],
)
def test_done_list_hint(name, expected):
    assert is_done_list_hint(name) is expected
