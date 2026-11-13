"""
Var olan karti BASLIKLA bulma + kartla ilgili yeni araclar (Faz 9d).

Kucuk local modeller kart id'sini bulup ikinci adimda kullanmakta zorlaniyor ve
"X kartini takvime koy" isteginde yeni kart aciyordu. Burada eslestirme KOD'da:
model yalnizca karttan soz ettigi metni verir (`card`), kod tek karta cozer ya da
aciklayici hata dondurur. Gizlilik: bulut modelde local_only board'larin kart/board
adlari ne eslesmede ne hata metninde gecer.
"""

import re
import unicodedata
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.llm.types import ToolSpec
from app.tools.privacy import HIDDEN_MESSAGE, PrivacyFilter
from app.tools.task_api import TaskApiClient

# Yeni arac adi -> izin turu (yeni islem turu yok: izin modeli sade kalsin)
CARD_TOOL_TO_ACTION = {
    "schedule_card": "create_event",
    "reschedule_card": "update_card",
    "move_card": "update_card",
}

_CARD_REF = {
    "type": "string",
    "description": 'Kartın id\'si (örn. "42") ya da başlığı',
}

CARD_TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        "schedule_card",
        "Var olan bir kartı takvime koyar (karta bağlı zaman bloğu). Saat verilmezse boş saat önerir. Yeni kart AÇMAZ.",
        {
            "type": "object",
            "properties": {
                "card": _CARD_REF,
                "day": {
                    "type": "string",
                    "description": "yarın / salı / 2026-11-10",
                },
                "start": {"type": "string", "description": "HH:MM (opsiyonel)"},
                "minutes": {"type": "integer", "description": "süre (opsiyonel)"},
            },
            "required": ["card", "day"],
        },
    ),
    ToolSpec(
        "reschedule_card",
        "Var olan kartın gününü değiştirir: son tarihi ve gelecekteki takvim bloğunu yeni güne taşır.",
        {
            "type": "object",
            "properties": {
                "card": _CARD_REF,
                "day": {
                    "type": "string",
                    "description": "yarın / cuma / 2026-11-14",
                },
                "start": {"type": "string", "description": "HH:MM (opsiyonel)"},
            },
            "required": ["card", "day"],
        },
    ),
    ToolSpec(
        "move_card",
        "Var olan kartı başka bir board'a ve/veya listeye taşır.",
        {
            "type": "object",
            "properties": {
                "card": _CARD_REF,
                "board": {"type": "string", "description": "Hedef board'un adı ya da id'si"},
                "list_name": {"type": "string", "description": "Hedef liste adı (opsiyonel)"},
            },
            "required": ["card", "board"],
        },
    ),
]

# Katlanmis dolgu kelimeleri (sorgudan atilir)
FILLER = {
    "kart", "karti", "kartini", "kartin", "kartim", "kartimi",
    "is", "isi", "isini", "isim", "gorev", "gorevi", "gorevini",
    "bu", "su", "o", "bunu", "sunu", "ve", "ile", "icin", "de", "da",
}  # fmt: skip

# "bu kart" gibi: odak kartina isaret eden ifadeler (katlanmis)
THIS_CARD = {"bu", "bu kart", "bu karti", "bu is", "bu isi", "bunu", "bu gorev"}


def fold(text: Any) -> str:
    """Turkce katlama: 'Eğitim' -> 'egitim', 'İngilizce' -> 'ingilizce', 'IŞIK' -> 'isik'."""
    s = str(text).replace("İ", "i").replace("I", "ı").lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.replace("ı", "i")


def tokens(text: Any) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def query_tokens(query: Any) -> list[str]:
    raw = tokens(query)
    kept = [t for t in raw if t not in FILLER]
    return kept or raw


def token_match(q: str, t: str) -> bool:
    if t == q:
        return True
    if len(q) < 3:
        return False
    return t.startswith(q) or (len(t) >= 3 and q.startswith(t))


def score(query: Any, title: Any) -> tuple[bool, bool, int]:
    """(tam aday: tum sorgu tokenlari basliktaki bir tokenla eslesiyor,
    kesin esit: token dizileri birebir ayni, eslesen sorgu token sayisi)."""
    raw = tokens(query)
    qt = query_tokens(query)
    tt = tokens(title)
    matched = sum(1 for q in qt if any(token_match(q, t) for t in tt))
    full = bool(qt) and matched == len(qt)
    exact = bool(tt) and (tt == raw or tt == qt)
    return full, exact, matched


# ---------------- veri ----------------
async def visible_boards(api: TaskApiClient, privacy: PrivacyFilter) -> list[dict[str, Any]]:
    boards = await api.get("/boards", include_archived=False)
    return [b for b in boards if not privacy.board_hidden(b["id"])]


async def visible_cards(
    api: TaskApiClient, privacy: PrivacyFilter, *, include_completed: bool
) -> list[dict[str, Any]]:
    """Gorunur board'lardaki kartlar (board_id, board_name, list_name eklenmis)."""
    out: list[dict[str, Any]] = []
    for b in await visible_boards(api, privacy):
        detail = await api.get(f"/boards/{b['id']}")
        lists = {lst["id"]: lst["name"] for lst in detail["lists"]}
        for c in detail["cards"]:
            if privacy.card_hidden(c["id"]):
                continue
            if not include_completed and c["status"] == "completed":
                continue
            out.append(
                {
                    **c,
                    "board_id": b["id"],
                    "board_name": b["name"],
                    "list_name": lists.get(c.get("list_id")),
                }
            )
    return out


def _label(c: dict[str, Any]) -> str:
    return f"#{c['id']} «{c['title']}» ({c['board_name']})"


async def find_exact_open(
    api: TaskApiClient,
    privacy: PrivacyFilter,
    title: str,
    cards: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Gorunur board'larda ayni basligi (katlanmis token dizisi birebir) tasiyan acik kart."""
    want = tokens(title)
    if not want:
        return None
    if cards is None:
        cards = await visible_cards(api, privacy, include_completed=False)
    for c in cards:
        if c["status"] != "completed" and tokens(c["title"]) == want:
            return c
    return None


# "board'ındaki" kesmede bolununce kalan ek parcalari
_LOCATIVE = {"indaki", "inda", "inde", "ndaki", "ndeki", "daki", "deki", "nda", "nde"}


def find_open_for_block(
    cards: list[dict[str, Any]],
    title: str,
    board: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """schedule_day blogu icin var olan ACIK kart. Once verilen board'daki kartlara, sonra
    tum gorunur kartlara bakar. Eslesme: baslik token dizisi birebir ya da dolgu kelimeleri
    ("kart"), board adi ve "board..." sozcukleri atildiktan sonra token KUMESI birebir
    ("P2 kartı", "Eğitim board'ındaki P2" -> "P2"). Belirsizse None (yeni kart)."""
    want = tokens(title)
    if not want:
        return None
    drop = {t for t in tokens(board["name"])} if board else set()
    core = {
        t
        for t in query_tokens(title)
        if t not in drop and not t.startswith("board") and t not in _LOCATIVE
    }
    open_cards = [c for c in cards if c["status"] != "completed"]
    pools = []
    if board:
        pools.append([c for c in open_cards if c.get("board_id") == board["id"]])
    pools.append(open_cards)
    for pool in pools:
        exact = [c for c in pool if tokens(c["title"]) == want]
        if exact:
            return exact[0]
        if core:
            loose = [c for c in pool if set(query_tokens(c["title"])) == core]
            if len(loose) == 1:
                return loose[0]
    return None


async def resolve_card(
    api: TaskApiClient,
    privacy: PrivacyFilter,
    ref: Any,
    *,
    focus_card_id: int | None = None,
    include_completed: bool = False,
) -> dict[str, Any]:
    """Karta gonderme (id ya da baslik) -> tek kart. Belirsizlik/bulunamama ValueError."""
    text = str(ref).strip() if ref is not None else ""
    if not text:
        raise ValueError("card gerekli: kartın id'si ya da başlığı")
    id_text = text.lstrip("#").strip()
    if id_text.isdigit():
        cid = int(id_text)
        if privacy.card_hidden(cid):
            raise ValueError(HIDDEN_MESSAGE)
        card = await api.get(f"/cards/{cid}")
        if privacy.board_hidden(card.get("board_id")):
            raise ValueError(HIDDEN_MESSAGE)
        detail = await api.get(f"/boards/{card['board_id']}")
        lists = {lst["id"]: lst["name"] for lst in detail["lists"]}
        return {
            **card,
            "board_name": detail["board"]["name"],
            "list_name": lists.get(card.get("list_id")),
        }
    if " ".join(tokens(text)) in THIS_CARD:
        if focus_card_id is None:
            raise ValueError("Hangi kart? Başlığını yaz.")
        return await resolve_card(
            api, privacy, focus_card_id, include_completed=include_completed
        )

    pool = await visible_cards(api, privacy, include_completed=True)
    scored = [(c, score(text, c["title"])) for c in pool]
    full = [(c, s) for c, s in scored if s[0]]
    open_full = [(c, s) for c, s in full if c["status"] != "completed"]
    # Acik kart varsa tamamlanmislar elenir (kullanici yeniden acmak istemiyordur)
    chosen = open_full or (full if include_completed else [])
    if len(chosen) == 1:
        return chosen[0][0]
    if len(chosen) > 1:
        exact = [c for c, s in chosen if s[1]]
        if len(exact) == 1:
            return exact[0]
        listing = ", ".join(_label(c) for c, _ in chosen[:5])
        raise ValueError(
            f"Birden çok kart eşleşti: {listing} — hangisi? "
            "Kartın id'siyle tekrar çağır."
        )
    if full:  # yalniz tamamlanmis tam adaylar
        c = full[0][0]
        raise ValueError(
            f"«{c['title']}» tamamlanmış (#{c['id']}). "
            "Yine de bu kartla işlem istiyorsan id'siyle çağır."
        )
    similar = [
        c
        for c, s in scored
        if s[2] > 0 and c["status"] != "completed"
    ]
    similar.sort(key=lambda c: -score(text, c["title"])[2])
    if similar:
        listing = ", ".join(_label(c) for c in similar[:5])
        raise ValueError(
            f"«{text}» adlı kart bulunamadı. Benzerler: {listing}. "
            "Doğru olan varsa id'siyle tekrar çağır."
        )
    raise ValueError(f"«{text}» adlı kart bulunamadı; search_cards ile ara.")


async def resolve_board(
    api: TaskApiClient, privacy: PrivacyFilter, ref: Any
) -> dict[str, Any]:
    """Board id'si ya da adi -> /boards satiri. Gizli board 'bulunamadi' gibi davranir."""
    boards = await visible_boards(api, privacy)
    text = str(ref).strip() if ref is not None else ""
    names = ", ".join(b["name"] for b in boards)
    found: list[dict[str, Any]] = []
    if text.isdigit():
        found = [b for b in boards if b["id"] == int(text)]
    if not found and text:
        key = fold(text)
        found = [b for b in boards if fold(b["name"]) == key]
        if not found:
            found = [b for b in boards if score(text, b["name"])[0]]
    if len(found) != 1:
        raise ValueError(f"Board bulunamadı/belirsiz. Mevcut: {names}")
    return found[0]


def free_slot(
    busy: list[tuple[datetime, datetime]],
    day: date,
    minutes: int,
    tz: ZoneInfo,
    now: datetime,
) -> datetime | None:
    """O gunun 09:00-21:00 araligindaki ilk bos aralik (15 dk adim); bugunse simdiden sonra."""
    start = datetime.combine(day, time(9), tzinfo=tz)
    limit = datetime.combine(day, time(21), tzinfo=tz)
    now = now.astimezone(tz)
    if now.date() == day and now > start:
        rounded = now.replace(second=0, microsecond=0)
        extra = (-rounded.minute) % 15
        if now.second or now.microsecond or extra:
            rounded += timedelta(minutes=extra or 15)
        start = max(start, rounded)
    cur = start
    length = timedelta(minutes=minutes)
    while cur + length <= limit:
        end = cur + length
        if not any(cur < be and bs < end for bs, be in busy):
            return cur
        cur += timedelta(minutes=15)
    return None
