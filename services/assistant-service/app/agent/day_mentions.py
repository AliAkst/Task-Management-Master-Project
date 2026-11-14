"""
Metinden gun ipucu (Faz 13d): kullanicinin mesajinda gecen gunleri KOD bulur.
Modelin 'day' alani guvenilmez (gercek vaka: "Cumartesi planlayalim. Yarin spor"
-> yanlis gun). 0 gun -> model day'i kullanilir; 1 -> kod zorlar; >=2 -> soru.
Genel/tekrarlayan ifadeler ("her sali", "salilari") ve bugunku anlami olmayanlar
("pazara gideceğim" = alisveris, "cumaya kadar") sayilmaz.
"""

import re
from datetime import date, datetime, time

from app.tools.schedule_day import resolve_day_ex

_MONTHS = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
}  # fmt: skip
_WEEKDAYS = (
    "pazartesi|salı|sali|çarşamba|carsamba|perşembe|persembe|cumartesi|cuma|pazar"
)
_TOKEN = re.compile(
    r"(?P<iso>\d{4}-\d{2}-\d{2})"
    r"|(?P<dm>\b\d{1,2})\s+(?P<month>ocak|şubat|mart|nisan|mayıs|haziran|temmuz|"
    r"ağustos|eylül|ekim|kasım|aralık)\w*"
    r"|(?P<rel>\bbug[uü]n|\byar[ıi]n\w*|\böbür gün|\bobur gun|\bertesi gün)"
    rf"|(?P<wd>\b(?:{_WEEKDAYS}))(?P<suf>\w*)"
)
_BLOCK_BEFORE = {
    "her", "geçen", "gecen", "önceki", "onceki", "haftaya", "gelecek", "önümüzdeki",
}  # fmt: skip
_PLURAL = ("lar", "ler")


def _prev_word(text: str, pos: int) -> str:
    m = re.search(r"(\w+)\W*$", text[:pos])
    return m.group(1) if m else ""


def _ok_context(text: str, m: re.Match[str]) -> bool:
    if _prev_word(text, m.start()) in _BLOCK_BEFORE:
        return False
    return not re.match(r"\W*kadar\b", text[m.end() :])


def day_mentions(text: str, now_local: datetime, rollover: time | None) -> list[date]:
    """Metinde gecen gunler (tekil, tarih sirali)."""
    t = (text or "").casefold()
    out: set[date] = set()
    today = now_local.date()
    for m in _TOKEN.finditer(t):
        if not _ok_context(t, m):
            continue
        try:
            if m.group("iso"):
                out.add(date.fromisoformat(m.group("iso")))
            elif m.group("dm"):
                d = date(today.year, _MONTHS[m.group("month")], int(m.group("dm")))
                if d < today:
                    d = date(today.year + 1, d.month, d.day)
                out.add(d)
            elif m.group("rel"):
                word = m.group("rel")
                key = (
                    "bugün" if word.startswith("bug")
                    else "yarın" if word.startswith("yar")
                    else "öbür gün"
                )  # fmt: skip
                out.add(resolve_day_ex(key, today, now_local=now_local, rollover=rollover)[0])
            elif m.group("wd"):
                name, suf = m.group("wd"), m.group("suf")
                if suf.startswith(_PLURAL):  # "salıları": genel ifade
                    continue
                if name == "pazar" and suf:
                    continue  # pazara/pazarı/pazarda: alisveris
                out.add(resolve_day_ex(name, today, now_local=now_local, rollover=rollover)[0])
        except ValueError:
            continue
    return sorted(out)
