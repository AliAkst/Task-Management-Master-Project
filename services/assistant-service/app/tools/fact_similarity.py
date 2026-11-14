"""
Hafiza yakin tekrar tespiti (Faz 13h2) - saf fonksiyonlar, G/C yok.

Kural (plan 13h2): ayni kategori VE (sozcuk Jaccard >= 0.6 YA DA
(ortak saat >= 2 VE Jaccard >= 0.1)). Birlestirme her zaman kullanici onayli
oldugu icin kabul edilen yanlis pozitifler zararsizdir.
"""

import re
from typing import Any, Protocol

from app.tools.card_lookup import fold

JACCARD_HIGH = 0.6
JACCARD_LOW = 0.1
MIN_SHARED_HOURS = 2

# katlanmis (fold) hâlleriyle
STOP_WORDS = {
    "ile", "icin", "gibi", "daha", "cok", "bir", "olan", "olarak",
    "kullanici", "genelde", "genellikle", "her",
}  # fmt: skip

_WORD = re.compile(r"[a-z0-9]+")
# 07:30 / 7.30 -> yalniz saat
_CLOCK = re.compile(r"(?<![\d:.])(\d{1,2})[:.](\d{2})(?![\d])")
# 7-9 / 18 – 20 (dakikali yazimin parcasi olan "00-13" sayilmaz)
_RANGE = re.compile(r"(?<![\d:.])(\d{1,2})\s*[-–]\s*(\d{1,2})(?![\d]|[:.]\d)")


class _FactLike(Protocol):
    category: str
    content: str


def tokens(text: Any) -> set[str]:
    words = _WORD.findall(fold(text))
    return {w for w in words if len(w) >= 3 and w not in STOP_WORDS}


def hours(text: Any) -> set[int]:
    s = str(text)
    found: set[int] = set()
    for m in _CLOCK.finditer(s):
        found.add(int(m.group(1)))
    for m in _RANGE.finditer(s):
        found.add(int(m.group(1)))
        found.add(int(m.group(2)))
    return {h for h in found if 0 <= h <= 24}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def near_duplicate_text(a: str, b: str) -> bool:
    j = jaccard(tokens(a), tokens(b))
    if j >= JACCARD_HIGH:
        return True
    return len(hours(a) & hours(b)) >= MIN_SHARED_HOURS and j >= JACCARD_LOW


def near_duplicate(a: _FactLike, b: _FactLike) -> bool:
    return a.category == b.category and near_duplicate_text(a.content, b.content)
