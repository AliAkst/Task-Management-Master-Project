"""
Soru cevabi eslestirici (Faz 13d): kullanici numarali bir soruya "2", "ikincisi",
"vazgec" gibi cevap verdi mi? Saf kod; asiri esnek eslesme YOK: "1 saat sonra"
ya da "2 saat spor yapacagim" yeni bir istektir, secenek sayilmaz.
"""

import re

_CANCEL = re.compile(r"(vazgeç|iptal|iptal et|hiçbiri|boşver|gerek yok)[.!]?")
_ORDINAL = re.compile(
    r"(ilk|ilki|birinci|birincisi|ikinci|ikincisi|üçüncü|üçüncüsü|dördüncü|dördüncüsü)"
    r"(?:\s+olsun)?[.!]?"
)
_ORDINAL_NUM = {
    "ilk": 1, "ilki": 1, "birinci": 1, "birincisi": 1,
    "ikinci": 2, "ikincisi": 2,
    "üçüncü": 3, "üçüncüsü": 3,
    "dördüncü": 4, "dördüncüsü": 4,
}  # fmt: skip
_NUMBER = re.compile(
    r"(?:(?:seçenek|şık)\s*)?([1-9])"
    r"\s*(?:[.)]|'?(?:yi|yı|i|ı|u|ü)|\s*(?:olsun|seç|seçiyorum|lütfen|tamam))*"
    r"\s*[.!]?"
)
MAX_LEN = 30


def match_answer(text: str, n_options: int) -> int | str | None:
    """-> 1..n (secenek) | "cancel" | None (cevap degil, normal akis)."""
    t = (text or "").strip().casefold()
    if not t or len(t) > MAX_LEN:
        return None
    if _CANCEL.fullmatch(t):
        return "cancel"
    m = _ORDINAL.fullmatch(t)
    k: int | None = _ORDINAL_NUM[m.group(1)] if m else None
    if k is None:
        m = _NUMBER.fullmatch(t)
        k = int(m.group(1)) if m else None
    if k is not None and 1 <= k <= n_options:
        return k
    return None
