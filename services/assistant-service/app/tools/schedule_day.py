"""
Gunu saat saat planlama araci (schedule_day).

Kucuk local modeller "her is icin kart olustur, sonra kartin id'siyle takvime
koy" zincirini yapamiyor: kart onaylanana kadar olusmadigi icin ikinci adimin
id'si yok, ustelik gun/saat aritmetiginde hata yapiyorlar. Bu aracta model
sadece SIRAYI ve SURELERI verir; gunu ("sali", "yarin"), baslangici
verilmeyen bloklarin saatini ve bitisleri KOD hesaplar, cakismalari yakalar.
Tek onay karti -> kartlar + takvim bloklari + gun plani birlikte yazilir.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.llm.types import ToolSpec

MAX_BLOCKS = 24

SCHEDULE_SPEC = ToolSpec(
    "schedule_day",
    "Bir günü saat saat planlar: TEK çağrıyla bütün blokları sırasıyla ver. "
    "Yapılacak işler (card=true) kart + takvim bloğu olur ve gün planına eklenir; "
    "yol, iş, yemek gibi sabit şeyler (card=false) sadece takvim etkinliği olur. "
    "Saat hesabı yapma: başlangıcı verilmeyen blok bir öncekinin bitişinde başlar; "
    "bitiş yerine 'minutes' (süre) verebilirsin. Gün: 'bugün', 'yarın', haftanın günü "
    "('salı') ya da YYYY-MM-DD.",
    {
        "type": "object",
        "properties": {
            "day": {"type": "string", "description": "salı / yarın / 2026-11-10"},
            "blocks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start": {
                            "type": "string",
                            "description": "HH:MM (sadece sabit saatli bloklarda)",
                        },
                        "minutes": {"type": "integer", "description": "süre (dakika)"},
                        "end": {"type": "string", "description": "HH:MM"},
                        "card": {
                            "type": "boolean",
                            "description": "true: yapılacak iş; false: sabit etkinlik",
                        },
                        "board": {
                            "type": "string",
                            "description": "kartın board'u (ad); card=true ise",
                        },
                    },
                    "required": ["title"],
                },
            },
        },
        "required": ["day", "blocks"],
    },
)

WEEKDAY_NAMES = {
    "pazartesi": 0,
    "salı": 1,
    "sali": 1,
    "çarşamba": 2,
    "carsamba": 2,
    "çarsamba": 2,
    "perşembe": 3,
    "persembe": 3,
    "cuma": 4,
    "cumartesi": 5,
    "pazar": 6,
}


def resolve_day(value: Any, today: date) -> date:
    """'salı' -> bugunden itibaren ilk sali (bugun saliysa bugun)."""
    text = str(value or "").strip().casefold()
    if not text:
        raise ValueError("day gerekli (örn. 'salı', 'yarın' ya da 2026-11-10)")
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    if text in ("bugün", "bugun"):
        return today
    if text in ("yarın", "yarin"):
        return today + timedelta(days=1)
    if text in ("öbür gün", "obur gun", "ertesi gün"):
        return today + timedelta(days=2)
    for name, wd in WEEKDAY_NAMES.items():
        if text.startswith(name) and (
            len(text) == len(name) or not text[len(name)].isalpha()
        ):
            return today + timedelta(days=(wd - today.weekday()) % 7)
    raise ValueError(
        f"Gün anlaşılamadı: '{value}'. 'bugün', 'yarın', 'salı' ya da YYYY-MM-DD yaz"
    )


def parse_clock(value: Any, field: str) -> int:
    """'07:30', '7.30', '7', '19' -> gece yarisindan itibaren dakika."""
    m = re.fullmatch(r"\s*(\d{1,2})(?:[:.](\d{2}))?\s*", str(value))
    if not m:
        raise ValueError(f"{field} HH:MM olmalı (gelen: {value})")
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 24 or mi > 59 or (h == 24 and mi):
        raise ValueError(f"{field} geçerli bir saat değil (gelen: {value})")
    return h * 60 + mi


def hhmm(minutes: int) -> str:
    m = minutes % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


@dataclass
class Block:
    title: str
    start: int  # gun basindan dakika (ertesi gune tasabilir)
    end: int
    card: bool
    board: Any


def _lead_in_start(blocks: list[dict[str, Any]]) -> int | None:
    """
    Ilk bloklarin saati yoksa ama sonraki bir blok sabit saatliyse ("ofise yol
    2 saat", "is 09:00") o bloklar sabit saate BITECEK sekilde geriye hesaplanir:
    yol 07:00-09:00. Kucuk modeller ilk bloga saat vermeyi sik unutuyor.
    """
    if not blocks or not isinstance(blocks[0], dict) or blocks[0].get("start"):
        return None
    lead = 0
    for b in blocks:
        if not isinstance(b, dict):
            return None
        if b.get("start") not in (None, ""):
            anchor = parse_clock(b["start"], "start")
            return anchor - lead if anchor - lead >= 0 else None
        try:
            lead += int(b.get("minutes"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None  # sure yok: geriye hesaplanamaz
    return None


def build_timeline(blocks: list[dict[str, Any]]) -> list[Block]:
    """Sirali bloklar -> saatler. Hata: modelin duzeltebilecegi Turkce aciklama."""
    if not blocks:
        raise ValueError("En az bir blok gerekli")
    if len(blocks) > MAX_BLOCKS:
        raise ValueError(f"En fazla {MAX_BLOCKS} blok verilebilir")
    out: list[Block] = []
    cursor = _lead_in_start(blocks)
    for i, b in enumerate(blocks, 1):
        if not isinstance(b, dict) or not str(b.get("title") or "").strip():
            raise ValueError(f"{i}. bloğun başlığı (title) yok")
        title = str(b["title"]).strip()[:200]
        if b.get("start") not in (None, ""):
            start = parse_clock(b["start"], f"'{title}' start")
            # Gece yarisini gecmis bir zaman cizelgesinde "01:00" ertesi gundur
            while cursor is not None and start + 12 * 60 <= cursor:
                start += 24 * 60
            if cursor is not None and start < cursor:
                prev = out[-1]
                raise ValueError(
                    f"'{title}' {hhmm(start)}'de başlıyor ama önceki blok "
                    f"'{prev.title}' {hhmm(prev.end)}'de bitiyor. Saati düzelt ya da "
                    f"start vermeden sıraya koy."
                )
        elif cursor is None:
            raise ValueError(f"İlk bloğun ('{title}') başlangıç saati (start) gerekli")
        else:
            start = cursor
        if b.get("end") not in (None, ""):
            end = parse_clock(b["end"], f"'{title}' end")
            if end % (24 * 60) == start % (24 * 60):
                raise ValueError(f"'{title}' başladığı saatte bitiyor; süreyi düzelt")
            while end <= start:
                end += 24 * 60
        elif b.get("minutes") not in (None, ""):
            try:
                minutes = int(b["minutes"])
            except (TypeError, ValueError) as e:
                raise ValueError(f"'{title}' minutes tam sayı olmalı") from e
            if not 1 <= minutes <= 24 * 60:
                raise ValueError(f"'{title}' süresi 1–1440 dakika olmalı")
            end = start + minutes
        else:
            raise ValueError(f"'{title}' için süre (minutes) ya da bitiş (end) gerekli")
        if end - start > 24 * 60:
            raise ValueError(f"'{title}' 24 saatten uzun olamaz")
        card = b.get("card")
        out.append(
            Block(
                title,
                start,
                end,
                card if isinstance(card, bool) else True,
                b.get("board"),
            )
        )
        cursor = end
    return out


def find_board(boards: list[dict[str, Any]], ref: Any) -> dict[str, Any] | None:
    """Board id'si ya da adi (buyuk/kucuk harf duyarsiz, kismi eslesme)."""
    if ref in (None, ""):
        return None
    if isinstance(ref, int) or str(ref).isdigit():
        return next((b for b in boards if b["id"] == int(ref)), None)
    key = str(ref).strip().casefold()
    exact = [b for b in boards if b["name"].casefold() == key]
    if exact:
        return exact[0]
    partial = [
        b for b in boards if key in b["name"].casefold() or b["name"].casefold() in key
    ]
    return partial[0] if len(partial) == 1 else None


def to_datetime(day: date, minutes: int, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time(0), tzinfo=tz) + timedelta(minutes=minutes)
