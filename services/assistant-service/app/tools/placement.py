"""
Yerlestirme motoru (Faz 13d): saf kod, I/O yok.

Model yalniz SIRAYI, saati belli olanlari (capa) ve surelerini (esnek) verir; bos
zamana yerlestirmeyi, cakisma/sigmama tespitini ve tek numarali soruyu KOD yapar.
Kural tablosu P1-P12 ve soru metinleri planlar/faz13/13d-yerlesim-motoru.md'dedir.
`build_timeline` (schedule_day.py) degismez; kutsal testler onu dogrudan cagirir.
"""

import copy
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.tools.schedule_day import DEFAULT_MINUTES, MAX_BLOCKS, hhmm, parse_clock

DEFAULT_DAY_START = 8 * 60
DEFAULT_DAY_END = 23 * 60
DAY = 24 * 60

# P10: pencere adi -> (baslangic, bitis) dakika
WINDOWS: dict[str, tuple[int, int]] = {
    "sabah": (360, 720),
    "öğle": (720, 840),
    "öğleden sonra": (840, 1080),
    "akşam": (1080, 1320),
    "gece": (1320, 1440),
}

WEEKDAY_LONG = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
MONTH_LONG = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]  # fmt: skip


def day_label(d: date) -> str:
    """'Cumartesi 14 Kasım'."""
    return f"{WEEKDAY_LONG[d.weekday()]} {d.day} {MONTH_LONG[d.month - 1]}"


def fold(text: str) -> str:
    return " ".join(str(text).casefold().split())


@dataclass
class Busy:
    title: str
    start: int
    end: int
    kind: str = "event"  # "template" | "event"


@dataclass
class TemplateInfo:
    name: str
    blocks: list[Busy]
    day_start: int = DEFAULT_DAY_START
    day_end: int = DEFAULT_DAY_END
    buffer: int = 0


@dataclass
class Row:
    title: str
    start: int | None
    end: int | None
    card: bool = True
    board: Any = None
    defaulted: bool = False
    moved: bool = False


@dataclass
class Placement:
    rows: list[Row] = field(default_factory=list)
    untimed: list[Row] = field(default_factory=list)
    carry: list[Row] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Option:
    label: str
    patch: dict[str, Any]


@dataclass
class Question:
    kind: str  # q1 | q2 | q3 | q4 | q5
    text: str
    options: list[Option]


# ---------------------------------------------------------------- iç yapı
@dataclass
class _Item:
    idx: int  # girdi listesindeki sira (patch'ler buna gore)
    title: str
    card: bool
    board: Any
    start: int | None = None
    end: int | None = None
    minutes: int | None = None
    window: str | None = None
    overlap_ok: bool = False
    defaulted: bool = False
    kind: str = "untimed"  # anchor | flex | untimed
    moved: bool = False

    @property
    def dur(self) -> int:
        if self.start is not None and self.end is not None:
            return self.end - self.start
        return self.minutes or 0


def _blank(v: Any) -> bool:
    return v in (None, "")


def _normalize(
    raw: list[dict[str, Any]], notes: list[str], rollover_min: int
) -> list[_Item]:
    """P1 + P2 + P3: dogrulama, sinif, gece yarisi."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("En az bir blok gerekli")
    if len(raw) > MAX_BLOCKS:
        raise ValueError(f"En fazla {MAX_BLOCKS} blok verilebilir")
    items: list[_Item] = []
    for i, b in enumerate(raw):
        if not isinstance(b, dict) or not str(b.get("title") or "").strip():
            raise ValueError(f"{i + 1}. bloğun başlığı (title) yok")
        title = str(b["title"]).strip()[:200]
        card = b.get("card")
        it = _Item(
            i, title, card if isinstance(card, bool) else True, b.get("board"),
            overlap_ok=bool(b.get("overlap_ok")),
        )  # fmt: skip
        if not _blank(b.get("window")):
            key = fold(b["window"])
            if key in WINDOWS:
                it.window = key
            else:
                notes.append(f"'{title}' için pencere anlaşılmadı")
        minutes = None
        if not _blank(b.get("minutes")):
            try:
                minutes = int(b["minutes"])
            except (TypeError, ValueError) as e:
                raise ValueError(f"'{title}' minutes tam sayı olmalı") from e
            if not 1 <= minutes <= DAY:
                raise ValueError(f"'{title}' süresi 1–1440 dakika olmalı")
        start = None if _blank(b.get("start")) else parse_clock(b["start"], f"'{title}' start")
        end = None if _blank(b.get("end")) else parse_clock(b["end"], f"'{title}' end")
        if start is None and end is None and minutes is None:
            items.append(it)  # saatsiz (window tek basina saatsizdir)
            continue
        if start is None and end is not None:
            if minutes is None:
                raise ValueError(f"'{title}' için start ya da minutes ver")
            start = end - minutes  # P1: bitisi verilen esnek -> capa
            if start < 0:
                raise ValueError(f"'{title}' için start geçersiz (gün başından önce)")
        elif start is not None and end is not None and end % DAY == start % DAY:
            raise ValueError(f"'{title}' başladığı saatte bitiyor; süreyi düzelt")
        if start is None:
            it.kind, it.minutes = "flex", minutes
            items.append(it)
            continue
        it.kind = "anchor"
        if end is None:
            if minutes is not None:
                end = start + minutes
            else:
                end, it.defaulted = start + DEFAULT_MINUTES, True  # M4
        while end <= start:
            end += DAY
        if end - start > DAY:
            raise ValueError(f"'{title}' 24 saatten uzun olamaz")
        it.start, it.end = start, end
        items.append(it)
    # P3: ogleden sonra bir sey varken rollover'dan once baslayan capa ertesi gune tasar
    late = False
    for it in items:
        if it.kind == "flex":
            late = True
        elif it.kind == "anchor":
            if it.start < rollover_min and late:
                it.start += DAY
                it.end += DAY
            if it.start >= 720:
                late = True
    return items


def _fits(start: int, end: int, obstacles: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [o for o in obstacles if o[0] < end and start < o[1]]


def _gap_text(items: list[_Item]) -> str:
    return ", ".join(f"«{i.title}» ({i.dur} dk)" for i in items)


def _numbered(head: str, options: list[Option]) -> str:
    lines = [head] + [f"{n}) {o.label}" for n, o in enumerate(options, 1)]
    lines.append('Numarayla cevap ver (ör. 1) ya da "vazgeç" yaz.')
    return "\n".join(lines)


def _q(kind: str, head: str, options: list[Option]) -> Question:
    return Question(kind, _numbered(head, options), options)


def day_question(days: list[date]) -> Question:
    """Q5: metinde birden cok gun gecti."""
    options = [Option(day_label(d), {"day": d.isoformat()}) for d in sorted(set(days))]
    return _q("q5", "Hangi gün için planlayayım?", options)


def _span(a: int, b: int) -> str:
    return f"{hhmm(a)}–{hhmm(b)}"


def _to_flex(it: _Item) -> dict[str, Any]:
    """Capayi esnege cevirir (start/end silinir, sure minutes olarak korunur)."""
    return {"start": None, "end": None, "minutes": it.dur or DEFAULT_MINUTES}


def place_day(
    items: list[dict[str, Any]],
    *,
    day: date,
    now_local: datetime,
    template: TemplateInfo | None,
    busy: list[Busy],
    rollover_min: int = 240,
    unfit: str | None = None,
) -> Placement | Question:
    notes: list[str] = []
    its = _normalize(items, notes, rollover_min)

    # P4: sablon tekrari
    tpl_blocks = template.blocks if template else []
    tpl_titles = {fold(b.title) for b in tpl_blocks}
    kept: list[_Item] = []
    for it in its:
        dup = fold(it.title) in tpl_titles or (
            it.kind == "anchor"
            and any(b.start == it.start and b.end == it.end for b in tpl_blocks)
        )
        if dup:
            notes.append(f"'{it.title}' şablonda zaten var")
        else:
            kept.append(it)
    its = kept

    # P5: engeller
    titles = {fold(i.title) for i in its}
    events = [b for b in busy if fold(b.title) not in titles]
    obstacles_b: list[Busy] = list(tpl_blocks) + events

    # P6: gun penceresi
    day_start = template.day_start if template else DEFAULT_DAY_START
    day_end = template.day_end if template else DEFAULT_DAY_END
    buffer = template.buffer if template else 0
    earliest = day_start
    is_today = day == now_local.date()
    now_min = now_local.hour * 60 + now_local.minute
    if is_today:
        earliest = max(day_start, -(-now_min // 5) * 5)

    anchors = sorted((i for i in its if i.kind == "anchor"), key=lambda i: i.start)

    # P7: capa cakismalari
    if is_today:
        for a in anchors:
            if a.end <= now_min and not a.overlap_ok:
                raise ValueError(f"'{a.title}' saati geçti")
    for n, x in enumerate(anchors):
        if x.overlap_ok:
            continue
        for a in anchors[:n]:  # a: daha once baslayan
            if a.start < x.end and x.start < a.end:
                opts = [
                    Option(f"«{x.title}» → {hhmm(a.end)} sonrasına", {"item": x.idx, "set": {"start": hhmm(a.end), "end": None, "minutes": x.dur}}),
                    Option(f"«{x.title}» → ilk boş saate", {"item": x.idx, "set": _to_flex(x)}),
                    Option("İkisi de bu saatlerde kalsın", {"item": x.idx, "set": {"overlap_ok": True}}),
                ]  # fmt: skip
                return _q(
                    "q1",
                    f"«{x.title}» {_span(x.start, x.end)}, «{a.title}» {_span(a.start, a.end)} ile çakışıyor.",
                    opts,
                )
        for e in events:
            if e.start < x.end and x.start < e.end:
                opts = [
                    Option(f"«{x.title}» → {hhmm(e.end + buffer)} sonrasına", {"item": x.idx, "set": {"start": hhmm(e.end + buffer), "end": None, "minutes": x.dur}}),
                    Option(f"«{x.title}» → ilk boş saate", {"item": x.idx, "set": _to_flex(x)}),
                    Option("Çakışsın, bu saatte kalsın", {"item": x.idx, "set": {"overlap_ok": True}}),
                ]  # fmt: skip
                return _q(
                    "q2",
                    f"«{x.title}» {_span(x.start, x.end)}, takvimdeki «{e.title}» {_span(e.start, e.end)} ile çakışıyor.",
                    opts,
                )
        for t in tpl_blocks:
            if t.start < x.end and x.start < t.end:
                opts = [
                    Option(f"«{x.title}» → {hhmm(t.end)} sonrasına", {"item": x.idx, "set": {"start": hhmm(t.end), "end": None, "minutes": x.dur}}),
                    Option("Şablon bloğunun içinde kalsın", {"item": x.idx, "set": {"overlap_ok": True}}),
                    Option("Bu gün şablonu kullanma", {"template_off": True}),
                ]  # fmt: skip
                name = template.name if template else ""
                return _q(
                    "q3",
                    f"«{x.title}» {_span(x.start, x.end)}, «{name}» şablonundaki «{t.title}» {_span(t.start, t.end)} ile çakışıyor.",
                    opts,
                )

    # P8 + P9: yerlestirme
    placed: list[tuple[int, int]] = []  # yerlesmis esnekler

    def all_obst() -> list[tuple[int, int]]:
        return (
            [(b.start, b.end) for b in obstacles_b]
            + [(a.start, a.end) for a in anchors]
            + placed
        )

    rows: dict[int, Row] = {}
    unfit_items: list[_Item] = []
    first_anchor_pos = next((n for n, i in enumerate(its) if i.kind == "anchor"), None)
    lead: list[_Item] = []
    if first_anchor_pos is not None:
        lead = [i for i in its[:first_anchor_pos] if i.kind == "flex"]
        if any(i.window for i in lead):
            lead = []
    if lead:
        fa = its[first_anchor_pos]
        total = sum(i.minutes for i in lead)
        begin = fa.start - total
        others = [(b.start, b.end) for b in obstacles_b] + [
            (a.start, a.end) for a in anchors
        ]
        if begin >= 0 and not _fits(begin, fa.start, others):
            t = begin
            for i in lead:
                rows[i.idx] = Row(i.title, t, t + i.minutes, i.card, i.board)
                placed.append((t, t + i.minutes))
                t += i.minutes
        else:
            lead = []
    lead_ids = {i.idx for i in lead}
    last_anchor_end = max((a.end for a in anchors), default=0)
    cursor: int | None = None
    for it in its:
        if it.kind == "untimed":
            continue
        if it.kind == "anchor":
            rows[it.idx] = Row(it.title, it.start, it.end, it.card, it.board, it.defaulted)
            cursor = it.end
            continue
        if it.idx in lead_ids:
            cursor = rows[it.idx].end
            continue
        m = it.minutes
        limit = max(day_end, last_anchor_end)
        t = max(cursor if cursor is not None else earliest, earliest)
        if it.window:
            ws, we = WINDOWS[it.window]
            ws = max(ws, day_start)
            if it.window != "gece":
                we = min(we, day_end)
            t = max(ws, earliest)
            limit = we
        moved = False
        found = None
        while True:
            if t + m > limit:
                break
            hit = _fits(t, t + m, all_obst())
            if not hit:
                found = t
                break
            t = max(h[1] for h in hit) + buffer
            moved = True
        if found is None:
            unfit_items.append(it)
            continue
        rows[it.idx] = Row(it.title, found, found + m, it.card, it.board, False, moved)
        placed.append((found, found + m))
        cursor = max(cursor or 0, found + m) if it.window else found + m

    # P11
    untimed = [Row(i.title, None, None, i.card, i.board) for i in its if i.kind == "untimed"]
    carry: list[Row] = []
    if unfit_items:
        if unfit is None:
            return _unfit_question(unfit_items, day, earliest, day_end, all_obst(), buffer)
        rest = [Row(i.title, None, None, i.card, i.board) for i in unfit_items]
        if unfit == "untimed":
            untimed += rest
        elif unfit == "carry":
            carry = rest
        elif unfit == "drop":
            notes += [f"çıkarıldı: {r.title}" for r in rest]
    ordered = sorted(rows.values(), key=lambda r: r.start)  # P12
    return Placement(ordered, untimed, carry, notes)


def _unfit_question(
    unfit_items: list[_Item], day: date, earliest: int, day_end: int,
    obst: list[tuple[int, int]], buffer: int,
) -> Question:  # fmt: skip
    from datetime import timedelta

    head = f"Şunlar {day_label(day)} için boş zamana sığmadı: {_gap_text(unfit_items)}."
    nxt = day + timedelta(days=1)
    opts = [
        Option("Saatsiz olarak bu günün planına ekle", {"unfit": "untimed"}),
        Option(f"Yarının ({day_label(nxt)}) planına aktar", {"unfit": "carry"}),
        Option("Plandan çıkar", {"unfit": "drop"}),
    ]
    if len(unfit_items) == 1:
        gap = _largest_gap(earliest, day_end, obst)
        n = (gap - buffer) // 5 * 5
        if gap >= 15 and 0 < n < unfit_items[0].dur:
            a = unfit_items[0]
            opts.append(Option(f"«{a.title}» → {n} dk'ya kısalt", {"item": a.idx, "set": {"minutes": n}}))
    return _q("q4", head, opts)


def _largest_gap(lo: int, hi: int, obst: list[tuple[int, int]]) -> int:
    cur, best = lo, 0
    for s, e in sorted(obst):
        if s > cur:
            best = max(best, min(s, hi) - cur)
        cur = max(cur, e)
    return max(best, hi - cur) if hi > cur else best


# ---------------------------------------------------------------- patch
def apply_patch(state: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Secilen secenegin patch'ini soru durumuna isler (kopya dondurur).

    state: {"items": [...], "template_off": bool, "unfit": str|None, "day": iso}
    patch: {"item": idx, "set": {alan: deger|None}} | {"template_off": True}
           | {"unfit": "..."} | {"day": iso}
    """
    new = copy.deepcopy(state)
    if "item" in patch:
        target = new["items"][patch["item"]]
        for k, v in patch["set"].items():
            if v is None:
                target.pop(k, None)
            else:
                target[k] = v
    if patch.get("template_off"):
        new["template_off"] = True
    if "unfit" in patch:
        new["unfit"] = patch["unfit"]
    if "day" in patch:
        new["day"] = patch["day"]
    return new



class NeedsAnswer(Exception):  # noqa: N818 — ValueError alt sinifi DEGIL (yeniden denenmez)
    """prepare() kullaniciya tek numarali soru sormali; modele hata gitmez."""

    def __init__(self, question: Question, state: dict[str, Any]):
        super().__init__(question.text)
        self.question = question
        self.state = state
