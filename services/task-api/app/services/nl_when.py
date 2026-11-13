"""Kart basligindaki Turkce dogal dil tarih/saat/sure ifadelerini ayiklar (Faz 10a).

Saf fonksiyon: DB/ag yok, yalniz stdlib. Kurallar `planlar/faz10/10a-ayristirici-uc.md`.
Faz 11a: kurallar `planlar/faz11/11a-ayristirici-genisleme.md`.
Katlanmis (ASCII'ye yakin, uzunlugu koruyan) metinde aranir; araliklar ozgun metne
birebir denk gelir.
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MAX_LEN = 200

_FOLD_MAP = {
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "â": "a", "î": "i", "û": "u",
    "’": "'", "‘": "'", "´": "'", "`": "'",
    "–": "-", "—": "-",
}  # fmt: skip


def fold(text: str) -> str:
    """Uzunlugu koruyan katlama (ozgun metne araliklar birebir denk gelir)."""
    out: list[str] = []
    for ch in text:
        if ch == "İ" or ch == "I":
            c = "i"
        else:
            c = ch.lower()
            if len(c) != 1:
                c = ch
        out.append(_FOLD_MAP.get(c, c))
    return "".join(out)


@dataclass(frozen=True)
class WhenMatch:
    spans: list[tuple[int, int]]
    phrase: str
    due_date: datetime | None
    has_time: bool
    estimated_minutes: int | None
    label: str
    clean_title: str
    strong: bool = True


@dataclass
class Piece:
    kind: str  # day | time | duration | range
    start: int
    end: int
    value: object
    bare: bool = False  # W-BARE: bugun + gecmis saat -> +7
    strong: bool = True  # Faz 11a: parca gucu (L10)
    plus_day: bool = False  # gece yarisi: gun + 1


# ---------------- sabitler ----------------
NUM = {
    "bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5,
    "alti": 6, "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10,
}  # fmt: skip
_NUM_RE = "(?:dokuz|dort|sekiz|yedi|alti|iki|bir|bes|uc|on)"
_GUN_RE = "(?:cumartesi|cuma|pazartesi|pazar|sali|carsamba|persembe)"
_GUN = {
    "pazartesi": 0, "sali": 1, "carsamba": 2, "persembe": 3,
    "cuma": 4, "cumartesi": 5, "pazar": 6,
}  # fmt: skip
_AY_TAM = [
    "ocak", "subat", "mart", "nisan", "mayis", "haziran",
    "temmuz", "agustos", "eylul", "ekim", "kasim", "aralik",
]  # fmt: skip
_AY_KISA = [
    "oca", "sub", "mar", "nis", "may", "haz",
    "tem", "agu", "eyl", "eki", "kas", "ara",
]  # fmt: skip
_AY_RE = "|".join(_AY_TAM) + "|(?:" + "|".join(_AY_KISA) + r")\.?"
_DP_RE = "ogleden sonra|oglen|ogle|sabah|aksam|gece"

_SUFT = "ya kadar|ye kadar|a kadar|e kadar|ten|tan|den|dan|te|ta|de|da"
_SUF_DAY = (
    r"(?:'?(?:ya kadar|ye kadar|a kadar|e kadar|ya|ye|yi|dan|den|da|de|a|e|i|u)"
    r"| (?:ya kadar|ye kadar|ya|ye)(?! d[ae](?![a-z0-9])))?"
    r"(?: gunune| gunu| gune)?"
)
_SUF_TIME = "'?(?:" + _SUFT + ")"
_SUF_TIME_SP = "(?:'| )?(?:" + _SUFT + ")"  # bitisik, kesmeli ya da tek bosluklu
_SUF_MONTH = r"(?:'?(?:ya|ye|ta|te|da|de|nin|in|a|e))?"
_SUF_NUMDAY = r"(?:'?(?:sinde|unda|inde|sine|si|ine|i|u))?"
_APX = "gibi|falan|civarinda|civari|sularinda|dolaylarinda"
_APPROX_FREE = {"civari", "civarinda", "sularinda", "dolaylarinda"}
_HW_RE = "on ?bir|on ?iki|dokuz|sekiz|yedi|alti|dort|bes|uc|iki|bir|on"
_HW = {
    "onbir": 11, "oniki": 12, "dokuz": 9, "sekiz": 8, "yedi": 7, "alti": 6,
    "dort": 4, "bes": 5, "uc": 3, "iki": 2, "bir": 1, "on": 10,
}  # fmt: skip

_TOKENS = {
    "@GUN@": _GUN_RE,
    "@NUM@": _NUM_RE,
    "@AY@": _AY_RE,
    "@DP@": _DP_RE,
    "@SUFDAY@": _SUF_DAY,
    "@SUFTIME@": _SUF_TIME,
    "@SUFTSP@": _SUF_TIME_SP,
    "@SUFT@": _SUFT,
    "@APX@": _APX,
    "@HW@": _HW_RE,
    "@SUFMON@": _SUF_MONTH,
    "@SUFNUMDAY@": _SUF_NUMDAY,
}

# Baglam sozcukleri (L3): ayrik ek / noktali saat / yaklasik sozcuk yalniz bunlardan sonra
_CTX_WORDS = frozenset({
    "pazartesi", "sali", "carsamba", "persembe", "cuma", "cumartesi", "pazar",
    "yarin", "bugun", "gun", "gunu", "oburgun", "sonra", "haftaya", "saat",
    "sabah", "ogle", "oglen", "aksam", "gece", "aksamustu", "ikindi",
    "sabahleyin", "aksamleyin",
    *_AY_TAM,
})  # fmt: skip


def _c(pattern: str) -> re.Pattern[str]:
    for k, v in _TOKENS.items():
        pattern = pattern.replace(k, v)
    return re.compile(r"(?<![a-z0-9])(?:" + pattern + r")(?![a-z0-9])")


_R_ISO = _c(r"(\d{4})-(\d{2})-(\d{2})")
_PRE = r"(?:(?P<pre>saat|@DP@)(?:i|si)? (?:saat )?)?"
_E1 = r"(?P<h1>\d{1,2})(?:(?P<s1>[:.])(?P<m1>\d{2}))?"
_E2 = r"(?P<h2>\d{1,2})(?:(?P<s2>[:.])(?P<m2>\d{2}))?"
_R_RANGE_TIRE = _c(_PRE + _E1 + r" ?- ?" + _E2 + r"(?P<tail> arasi(?:nda)?|@SUFTSP@)?")
_R_RANGE_ILE = _c(_PRE + _E1 + r" ile " + _E2 + r" arasi(?:nda|na)?")
_R_RANGE_DANE = _c(
    _PRE + _E1 + r"(?:'| )?(?:dan|den|tan|ten) " + _E2 + r"(?:'| )?(?:ya|ye|a|e)(?: kadar)?"
)
_R_DUR2 = _c(
    r"(\d{1,3}|@NUM@) ?(?:saat|sa\.?) (\d{1,3}|@NUM@) ?(?:dakika|dk\.?|dak\.?)"
)
_R_DUR1 = _c(
    r"(\d{1,3}(?:[.,]\d{1,2})?|@NUM@ bucuk|\d{1,2} bucuk|@NUM@|yarim|ceyrek)"
    r" ?(saatlik|saat|sa\.?|dakikalik|dakika|dk\.?|dak\.?)"
)
_R_MON = _c(
    r"(\d{1,2})@SUFNUMDAY@ (@AY@)@SUFMON@(?: (\d{4})@SUFMON@)?"
)
_R_NUMDATE = _c(
    r"(\d{1,2})[./](\d{2})(?:[./](\d{4}|\d{2}))?(@SUFTSP@)?"
    r"(?! ?(?:saat|sa|dakika|dk))"
)
_R_AYIN = _c(r"ayin (\d{1,2})(?:'?(?:si|i|u|unda|inde|sinde|ine|sine|ne))?")
_R_NEXTWEEK_DAY = _c(
    r"(?:haftaya|gelecek hafta(?:nin)?|onumuzdeki hafta(?:nin)?|sonraki hafta(?:nin)?)"
    r" (@GUN@)@SUFDAY@"
)
_R_NEXT_DAY = _c(r"(?:onumuzdeki|gelecek|sonraki) (@GUN@)@SUFDAY@")
_R_THIS_DAY = _c(r"bu (@GUN@)@SUFDAY@")
_R_WK_NEXT = _c(
    r"(?:haftaya|gelecek hafta|onumuzdeki hafta|sonraki hafta)(?:ya|ye)?"
)
_R_WK_END = _c(r"(?:bu )?hafta ?sonu(?:na|nda|ya)?")
_R_WK_THIS = _c(r"bu hafta(?: sonuna|nin sonuna|sonuna|icinde|ya|ye)?")
_R_REL = _c(r"(bugun(?:e|de|den|ku)?)|(yarin(?:a|da|dan|ki)?)|(obur ?gun(?:e|u)?)")
_R_AFTER = _c(r"(\d{1,2}|@NUM@) (gun|hafta) sonra(?:ya|sina)?")
_R_DP_TODAY = _c(r"bu (sabah|ogleden sonra|oglen|ogle|aksam|gece)")
_R_T_DP = _c(
    r"(@DP@)(?:i|si)? (?:saat )?(\d{1,2})(?:[:.](\d{2}))?(?:@SUFTSP@)?(?: (?:@APX@))?"
)
_R_T_SAAT = _c(r"saat (\d{1,2})(?:[:.](\d{2}))?(?:@SUFTSP@)?(?: (?:@APX@))?")
_R_T_WORD = _c(
    r"(?:(?P<saat>saat)|(?P<dp>@DP@)(?:i|si)?) (?P<hw>@HW@)(?P<suf>'?(?:@SUFT@))?"
    r"(?P<apx> (?:@APX@))?"
    r"(?! (?:bir|iki|uc|dort|bes|alti|yedi|sekiz|dokuz|bucuk))"  # D1: "on beste", "yedi bucukta"
)
_R_T_COLON = _c(r"(\d{1,2}):(\d{2})(?:@SUFTSP@)?(?: (?:@APX@))?")
_R_T_DOT = _c(r"(\d{1,2})\.(\d{2})(@SUFTSP@)?( (?:@APX@))?")
_R_T_SUF = _c(r"(?<!\d[,.:])(\d{1,2})@SUFTIME@(?: (?:@APX@))?")
_R_T_SUF_SP = _c(r"(?<!\d[,.:])(\d{1,2}) (?:@SUFT@)(?: (?:@APX@))?")
_R_T_APPROX = _c(r"(?<!\d[,.:])(\d{1,2})(?:[:.](\d{2}))? (@APX@)")
_NODIGIT = r"(?! (?:saat )?\d)"
_R_DP_FREE = [
    (_c(r"aksam ?ustu(?:nde|ne)?" + _NODIGIT), (17, 0), False),
    (_c(r"ikindi(?:ye|de|leyin)?(?: dogru)?" + _NODIGIT), (17, 0), False),
    (_c(r"oglen? arasi(?:nda|na)?" + _NODIGIT), (12, 0), False),
    (_c(r"gece ?yarisi(?:nda|na)?" + _NODIGIT), (0, 0), True),
    (_c(r"(?:ogleye|oglene)(?: dogru| kadar)?" + _NODIGIT), (12, 0), False),
    (_c(r"aksama(?: dogru| kadar)?" + _NODIGIT), (19, 0), False),
    (_c(r"aksamleyin" + _NODIGIT), (19, 0), False),
    (_c(r"sabaha(?: dogru| kadar)?" + _NODIGIT), (9, 0), False),
    (_c(r"sabahleyin" + _NODIGIT), (9, 0), False),
    (_c(r"geceye(?: dogru| kadar)?" + _NODIGIT), (22, 0), False),
]
_R_DP_ALONE = _c(r"(@DP@)(?:i|si|leyin)?")
_R_W_BARE = _c(r"(@GUN@)@SUFDAY@")
_DP_AFTER = re.compile(r"\s+(?:sabah|ogle|aksam|gece)")

_DP_DEFAULT = {"sabah": 9, "ogle": 12, "ogleden": 15, "aksam": 19, "gece": 22}
_FILLERS = ["en gec", "en son", "icin", "saat", "tarihinde", "itibaren"]
_GUN_AD = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_AY_AD = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]


# ---------------- yardimcilar ----------------
def _num(tok: str) -> int | None:
    if tok.isdigit():
        return int(tok)
    return NUM.get(tok)


def _dp_kind(word: str) -> str:
    if word.startswith("ogleden"):
        return "ogleden"
    if word.startswith("ogle"):
        return "ogle"
    return word.split()[0]


def _dp_hour(kind: str, h: int) -> int | None:
    if kind == "sabah":
        return h if 1 <= h <= 12 else None
    if kind == "ogle":
        if 1 <= h <= 5:
            return h + 12
        return h if 11 <= h <= 12 else None
    if kind in ("ogleden", "aksam"):
        if h > 23:
            return None
        return h + 12 if h < 12 else h
    if kind == "gece":
        if 1 <= h <= 5:
            return h
        if 6 <= h <= 11:
            return h + 12
        if h == 12 or h == 0:
            return 0
        return h if h <= 23 else None
    return None


def _k5(hs: str) -> int | None:
    """Gun bolumu yokken yalin saat (K5)."""
    h = int(hs)
    if h > 23:
        return None
    if 1 <= h <= 6 and not hs.startswith("0"):
        return h + 12
    return h


def _hm(h: int | None, mi: str | None) -> tuple[int, int] | None:
    if h is None:
        return None
    m = int(mi) if mi else 0
    if m > 59 or h > 23:
        return None
    return h, m


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _week_start_of(today: date, ws: int) -> date:
    return today - timedelta(days=(today.weekday() - ws) % 7)


def _fmt_dur(m: int) -> str:
    if m < 60:
        return f"{m} dk"
    if m % 60 == 0:
        return f"{m // 60} sa"
    return f"{m // 60} sa {m % 60} dk"


def _prev_word(f: str, start: int) -> str | None:
    """start'tan onceki sozcuk (arada en az bir bosluk olmali)."""
    i = start
    while i > 0 and f[i - 1] == " ":
        i -= 1
    if i == start or i == 0:
        return None
    j = i
    while j > 0 and "a" <= f[j - 1] <= "z":
        j -= 1
    return f[j:i] if j < i else None


def _ctx_word(f: str, start: int) -> bool:
    return _prev_word(f, start) in _CTX_WORDS


def _ctx(f: str, start: int, pieces: "list[Piece]") -> bool:
    return _ctx_word(f, start) or any(p.kind == "day" and not p.bare for p in pieces)


def _range_value(
    pre: str | None, h1: str, m1: str | None, h2: str, m2: str | None
) -> tuple[tuple[int, int], int] | None:
    kind = _dp_kind(pre) if pre and pre != "saat" else None
    sh = _dp_hour(kind, int(h1)) if kind else _k5(h1)
    if sh is None:
        return None
    sm = int(m1) if m1 else 0
    h2i = int(h2)
    eh = h2i
    if kind:
        v = _dp_hour(kind, h2i)
        eh = v if v is not None else h2i
    em = int(m2) if m2 else 0
    if sm > 59 or em > 59 or eh > 23:
        return None
    s_min, e_min = sh * 60 + sm, eh * 60 + em
    if e_min <= s_min:
        if kind == "gece":
            e_min += 1440
        elif not m2 and h2i < 12:
            e_min += 720
    if e_min <= s_min:
        return None
    return (sh, sm), e_min - s_min


def _overlaps(taken: list[tuple[int, int]], s: int, e: int) -> bool:
    return any(s < te and ts < e for ts, te in taken)


# ---------------- ayristirma ----------------
def _scan(f: str, today: date, ws: int) -> list[Piece]:  # noqa: C901
    pieces: list[Piece] = []
    taken: list[tuple[int, int]] = []

    def add(
        kind: str,
        m: re.Match[str],
        value: object,
        bare: bool = False,
        strong: bool = True,
        plus_day: bool = False,
    ) -> None:
        pieces.append(Piece(kind, m.start(), m.end(), value, bare, strong, plus_day))
        taken.append((m.start(), m.end()))

    def free(m: re.Match[str]) -> bool:
        return not _overlaps(taken, m.start(), m.end())

    # 1 D-ISO
    for m in _R_ISO.finditer(f):
        d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d and free(m):
            add("day", m, d)

    # 2 R1a tire, 2b R1b ile..arasi, 2c R1c -dan..-e
    def range_hit(m: re.Match[str], strong: bool) -> None:
        val = _range_value(
            m.group("pre"), m.group("h1"), m.group("m1"), m.group("h2"), m.group("m2")
        )
        if val is None:
            taken.append((m.start(), m.end()))  # gecersiz aralik: parcalari tek saat sayma
            return
        add("range", m, val, strong=strong)

    for m in _R_RANGE_TIRE.finditer(f):
        if not free(m):
            continue
        tail = m.group("tail") or ""
        minutes = bool(m.group("m1") or m.group("m2"))
        colon = m.group("s1") == ":" or m.group("s2") == ":"
        ok_min = bool(
            m.group("m1")
            and m.group("m2")
            and m.group("m1") in ("00", "15", "30", "45")
            and m.group("m2") in ("00", "15", "30", "45")
        )
        has_ctx = _ctx_word(f, m.start())
        if not (m.group("pre") or "arasi" in tail or colon or has_ctx or ok_min):
            if m.group("m1") and m.group("m2"):
                taken.append((m.start(), m.end()))  # D5: reddedilen H.MM-H.MM parcalari serbest kalmasin
            continue
        range_hit(m, bool(m.group("pre") or minutes or has_ctx))
    for m in _R_RANGE_ILE.finditer(f):
        if not free(m):
            continue
        minutes = bool(m.group("m1") or m.group("m2"))
        range_hit(m, bool(m.group("pre") or minutes or _ctx_word(f, m.start())))
    for m in _R_RANGE_DANE.finditer(f):
        if not free(m):
            continue
        minutes = bool(m.group("m1") or m.group("m2"))
        if m.group("pre") or minutes or _ctx_word(f, m.start()):
            range_hit(m, True)
        else:
            taken.append((m.start(), m.end()))  # L5: parcalari tek saat sayma

    # 3 DUR2
    for m in _R_DUR2.finditer(f):
        h, mi = _num(m.group(1)), _num(m.group(2))
        if h is None or mi is None or not free(m):
            continue
        total = h * 60 + mi
        if 1 <= total <= 100000:
            add("duration", m, total)

    # 4 DUR1
    for m in _R_DUR1.finditer(f):
        g, unit = m.group(1), m.group(2)
        hour_unit = unit.startswith("sa")
        if g in ("yarim", "ceyrek"):
            if not hour_unit:
                continue
            val = 0.5 if g == "yarim" else 0.25
        elif g.endswith(" bucuk"):
            base = _num(g[: -len(" bucuk")])
            if base is None:
                continue
            val = base + 0.5
        elif g.isdigit() or g[0].isdigit():
            val = float(g.replace(",", "."))
        else:
            n = _num(g)
            if n is None:
                continue
            val = float(n)
        total = int(round(val * 60)) if hour_unit else int(round(val))
        if 1 <= total <= 100000 and free(m):
            at_end = f[m.end() :].strip(" .,;:!?") == ""
            add("duration", m, total, strong=at_end)

    # 5 D-MON
    for m in _R_MON.finditer(f):
        if not free(m):
            continue
        name = m.group(2).rstrip(".")
        mon = (_AY_TAM.index(name) if name in _AY_TAM else _AY_KISA.index(name)) + 1
        dd = int(m.group(1))
        if m.group(3):
            d = _safe_date(int(m.group(3)), mon, dd)
        else:
            d = _safe_date(today.year, mon, dd)
            if d and d < today:
                d = _safe_date(today.year + 1, mon, dd)
        if d:
            add("day", m, d)

    # 6 D-NUM
    for m in _R_NUMDATE.finditer(f):
        if not free(m):
            continue
        dd, mon = int(m.group(1)), int(m.group(2))
        suf = (m.group(4) or "").lstrip("' ")
        if suf and not m.group(3) and (suf.startswith("t") or dd >= 7):
            continue  # "10.05'te" saat yazimi: T-DOT alsin
        if not m.group(3):
            pw = _prev_word(f, m.start())
            if pw in _CTX_WORDS and pw not in _AY_TAM and _hm(dd, m.group(2)):
                continue  # "yarin 10.05": baglamli saat, T-DOT alsin
        if m.group(3):
            y = int(m.group(3))
            d = _safe_date(y + 2000 if y < 100 else y, mon, dd)
        else:
            d = _safe_date(today.year, mon, dd)
            if d and d < today:
                d = _safe_date(today.year + 1, mon, dd)
        if d:
            add("day", m, d)

    # 7 D-AYIN
    for m in _R_AYIN.finditer(f):
        if not free(m):
            continue
        dd = int(m.group(1))
        if not 1 <= dd <= 31:
            continue
        y, mon = today.year, today.month
        if dd < today.day:
            mon += 1
            if mon > 12:
                mon, y = 1, y + 1
        dd = min(dd, calendar.monthrange(y, mon)[1])
        add("day", m, date(y, mon, dd))

    # 8-10 haftanin gunleri
    this_ws = _week_start_of(today, ws)
    for m in _R_NEXTWEEK_DAY.finditer(f):
        if free(m):
            w = _GUN[m.group(1)]
            add("day", m, this_ws + timedelta(days=7 + (w - ws) % 7))
    for m in _R_NEXT_DAY.finditer(f):
        if free(m):
            w = _GUN[m.group(1)]
            add("day", m, today + timedelta(days=(w - today.weekday()) % 7 or 7))
    for m in _R_THIS_DAY.finditer(f):
        if free(m):
            w = _GUN[m.group(1)]
            d = this_ws + timedelta(days=(w - ws) % 7)
            if d < today:
                d += timedelta(days=7)
            add("day", m, d)

    # 11 WK-NEXT, 12 WK-END, 13 WK-THIS
    for m in _R_WK_NEXT.finditer(f):
        if free(m):
            add("day", m, this_ws + timedelta(days=7))
    for m in _R_WK_END.finditer(f):
        if free(m):
            wd = today.weekday()
            add("day", m, today if wd >= 5 else today + timedelta(days=5 - wd))
    for m in _R_WK_THIS.finditer(f):
        if free(m):
            add("day", m, this_ws + timedelta(days=6))

    # 14 D-REL
    for m in _R_REL.finditer(f):
        if not free(m):
            continue
        n = 0 if m.group(1) else 1 if m.group(2) else 2
        add("day", m, today + timedelta(days=n))

    # 15 D-AFTER
    for m in _R_AFTER.finditer(f):
        n = _num(m.group(1))
        if n is None or not free(m):
            continue
        if m.group(2) == "gun":
            ok, days = 1 <= n <= 60, n
        else:
            ok, days = 1 <= n <= 12, 7 * n
        if ok:
            add("day", m, today + timedelta(days=days))

    # 16 DP-TODAY
    for m in _R_DP_TODAY.finditer(f):
        if free(m):
            kind = _dp_kind(m.group(1))
            pieces.append(Piece("day", m.start(), m.end(), today))
            pieces.append(Piece("time", m.start(), m.end(), (_DP_DEFAULT[kind], 0)))
            taken.append((m.start(), m.end()))

    # 16b G-DP-FREE (ekli/bilesik gun bolumu sozcukleri)
    for rx, (hh, mm), plus in _R_DP_FREE:
        for m in rx.finditer(f):
            if free(m):
                add("time", m, (hh, mm), strong=_ctx_word(f, m.start()), plus_day=plus)

    # 17 T-DP
    for m in _R_T_DP.finditer(f):
        if not free(m):
            continue
        hm = _hm(_dp_hour(_dp_kind(m.group(1)), int(m.group(2))), m.group(3))
        if hm:
            add("time", m, hm)

    # 18 T-SAAT
    for m in _R_T_SAAT.finditer(f):
        if not free(m):
            continue
        hm = _hm(_k5(m.group(1)), m.group(2))
        if hm:
            add("time", m, hm)

    # 18b T-WORD (sayi sozcugu saat)
    for m in _R_T_WORD.finditer(f):
        if not free(m):
            continue
        n = _HW[m.group("hw").replace(" ", "")]
        if m.group("saat"):
            if not (m.group("suf") or m.group("apx") or not f[m.end() :].strip(" .,;:!?")):
                continue  # D2: "her saat bir bardak su ic": ek/yaklasik/baslik sonu sart
            h: int | None = n + 12 if 1 <= n <= 6 else n
        else:
            if not m.group("suf"):
                continue  # "aksam bir film", "sabah bir de": ek zorunlu ve bitisik
            h = _dp_hour(_dp_kind(m.group("dp")), n)
        hm = _hm(h, None)
        if hm:
            add("time", m, hm)

    # 19 T-COLON
    for m in _R_T_COLON.finditer(f):
        if not free(m):
            continue
        hm = _hm(_k5(m.group(1)), m.group(2))
        if hm:
            add("time", m, hm)

    # 20 T-DOT
    for m in _R_T_DOT.finditer(f):
        if not free(m):
            continue
        if not (m.group(3) or m.group(4) or _ctx(f, m.start(), pieces)):
            continue
        hm = _hm(_k5(m.group(1)), m.group(2))
        if hm:
            add("time", m, hm)

    # 21 T-SUF
    for m in _R_T_SUF.finditer(f):
        if not free(m):
            continue
        hm = _hm(_k5(m.group(1)), None)
        if hm:
            add("time", m, hm, strong=_ctx_word(f, m.start()) or int(m.group(1)) >= 13)

    # 21b T-SUF-SP (ayrik ek; yalniz baglamla)
    for m in _R_T_SUF_SP.finditer(f):
        if not free(m) or not _ctx(f, m.start(), pieces):
            continue
        hm = _hm(_k5(m.group(1)), None)
        if hm:
            add("time", m, hm)

    # 21c T-APPROX (N gibi / civari ...)
    for m in _R_T_APPROX.finditer(f):
        if not free(m):
            continue
        ctx = _ctx(f, m.start(), pieces)
        if not (m.group(3) in _APPROX_FREE or ctx):
            continue
        hm = _hm(_k5(m.group(1)), m.group(2))
        if hm:
            add("time", m, hm, strong=ctx)

    # 23 W-BARE (pazar/cuma yalin ise kisitli: W5)
    time_starts = {p.start for p in pieces if p.kind in ("time", "range")}
    for m in _R_W_BARE.finditer(f):
        if not free(m):
            continue
        name = m.group(1)
        if name in ("pazar", "cuma") and m.group(0) == name:
            rest = f[m.end() :]
            last_word = rest.strip(" .,;:!?") == ""
            nxt = m.end() + (len(rest) - len(rest.lstrip(" ")))
            before_time = rest.startswith(" ") and nxt in time_starts
            before_dp = bool(_DP_AFTER.match(rest))
            if not (last_word or before_time or before_dp):
                continue
        w = _GUN[name]
        tail = m.group(0)[len(name) :].lstrip("' ")
        core = tail.split(" ")[0] if tail else ""
        strong = core in ("a", "e", "ya", "ye") or "gun" in tail
        add(
            "day", m, today + timedelta(days=(w - today.weekday()) % 7),
            bare=True, strong=strong,
        )  # fmt: skip

    # 22 DP-ALONE (hemen onunde day parcasi olmali)
    for m in _R_DP_ALONE.finditer(f):
        if not free(m):
            continue
        before = f[: m.start()]
        stripped = before.rstrip(" ")
        if stripped == before or not stripped:
            continue
        if not any(p.kind == "day" and p.end == len(stripped) for p in pieces):
            continue
        add("time", m, (_DP_DEFAULT[_dp_kind(m.group(1))], 0))

    return pieces


def _clean(text: str, f: str, spans: list[tuple[int, int]]) -> str:
    cut = [list(s) for s in spans]
    changed = True
    while changed:
        changed = False
        for c in cut:
            left = f[: c[0]].rstrip(" ")
            for fill in _FILLERS:
                if left.endswith(fill):
                    st = len(left) - len(fill)
                    if (st == 0 or not f[st - 1].isalnum()) and st < c[0]:
                        c[0] = st
                        changed = True
                        break
            right_start = c[1] + (len(f[c[1] :]) - len(f[c[1] :].lstrip(" ")))
            for fill in _FILLERS:
                if f.startswith(fill, right_start):
                    en = right_start + len(fill)
                    if (en == len(f) or not f[en].isalnum()) and en > c[1]:
                        c[1] = en
                        changed = True
                        break
    cut.sort()
    out: list[str] = []
    pos = 0
    for s, e in cut:
        if s < pos:
            s = pos
        if e <= s:
            continue
        out.append(text[pos:s])
        out.append(" ")
        pos = e
    out.append(text[pos:])
    res = re.sub(r" {2,}", " ", "".join(out)).replace(" ,", ",")
    res = res.strip(" ,;:-·")
    if len(res) < 2:
        return text.strip()
    first = next((ch for ch in text if not ch.isspace()), "")
    if first.isupper() and res[0].islower():
        res = ({"i": "İ", "ı": "I"}.get(res[0]) or res[0].upper()) + res[1:]
    return res


def parse_when(
    text: str, now: datetime, tz: ZoneInfo, week_start: int = 0
) -> WhenMatch | None:
    text = text[:MAX_LEN]
    if not text.strip():
        return None
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("UTC"))
    local_now = now.astimezone(tz)
    today = local_now.date()
    f = fold(text)
    pieces = _scan(f, today, week_start)
    if not pieces:
        return None

    def first(kind: str) -> Piece | None:
        c = [p for p in pieces if p.kind == kind]
        return min(c, key=lambda p: p.start) if c else None

    day_p, time_p, dur_p, range_p = (
        first("day"), first("time"), first("duration"), first("range"),
    )  # fmt: skip
    used: list[Piece] = []
    minutes: int | None = None
    hm: tuple[int, int] | None = None
    if day_p:
        used.append(day_p)
    if range_p:
        used.append(range_p)
        hm, minutes = range_p.value  # type: ignore[misc]
    else:
        if time_p:
            used.append(time_p)
            hm = time_p.value  # type: ignore[assignment]
        if dur_p:
            used.append(dur_p)
            minutes = dur_p.value  # type: ignore[assignment]
    if not used:
        return None

    due: datetime | None = None
    has_time = hm is not None
    if day_p or hm:
        if day_p:
            d: date = day_p.value  # type: ignore[assignment]
        else:
            d = today
        if time_p and time_p.plus_day and not range_p:
            d += timedelta(days=1)
        t = time(hm[0], hm[1]) if hm else time(23, 59)
        due = datetime.combine(d, t, tzinfo=tz)
        if hm and not day_p and due <= local_now:
            due += timedelta(days=1)
        elif hm and day_p and day_p.bare and due <= local_now:
            due += timedelta(days=7)

    # ayni aralik iki parca olabilir (DP-TODAY); araliklari tekille
    uniq = sorted({(p.start, p.end) for p in used})
    spans = [(s, e) for s, e in uniq]
    phrase = " ".join(text[s:e] for s, e in spans)

    parts: list[str] = []
    if due is not None:
        lbl = f"📅 {_GUN_AD[due.weekday()]} {due.day} {_AY_AD[due.month - 1]}"
        if due.year != today.year:
            lbl += f" {due.year}"
        if has_time:
            lbl += f" {due.hour:02d}:{due.minute:02d}"
        parts.append(lbl)
    if minutes is not None:
        parts.append(f"⏱ {_fmt_dur(minutes)}")

    return WhenMatch(
        spans=spans,
        phrase=phrase,
        due_date=due,
        has_time=has_time,
        estimated_minutes=minutes,
        label=" · ".join(parts),
        clean_title=_clean(text, f, spans),
        strong=any(p.strong for p in used),
    )
