"""
Yazma araclari (Faz 5). Her arac iki asamali:

1. prepare(): argumanlari DOGRULAR ve COZER (board -> liste id'si, "2026-11-09"
   -> yerel gun sonu ISO, gizlilik kontrolu) ve kullaniciya gosterilecek Turkce
   ozeti uretir. Hata -> ValueError: model hemen duzeltebilsin diye aciklayici.
2. execute(): onceden cozulmus argumanlarla task-api'ye yazar (X-Actor: ai).

Boylece onay kartinda gordugun sey, onaylayinca yapilan seyin TA KENDISIDIR.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.llm.types import ToolSpec
from app.tools.card_content import (
    CONTENT_ACTION_TYPES,
    CONTENT_SPECS,
    CONTENT_TOOL_TO_ACTION,
    apply_labels,
    clean_texts,
    execute_checklist,
    execute_delete_items,
    label_line,
    names_list,
    split_known,
)
from app.tools.delete_tools import (
    DELETE_ACTION_TYPES,
    DELETE_SPECS,
    execute_delete,
    prepare_cancel_day,
    prepare_delete_cards,
)
from app.tools.memory_tools import (
    MEMORY_ACTION_TYPES,
    MEMORY_SPECS,
    TOOL_TO_ACTION,
    MemoryTools,
    validate_goal_args,
)
from app.tools.privacy import HIDDEN_MESSAGE, PrivacyFilter
from app.tools.schedule_day import (
    SCHEDULE_SPEC,
    build_timeline,
    find_board,
    find_conflict,
    hhmm,
    resolve_day,
    to_datetime,
)
from app.tools.task_api import TaskApiClient, TaskApiError

# Islem turleri (izin ayarlari bu anahtarlarla tutulur)
ACTION_TYPES: dict[str, str] = {
    "create_card": "Kart oluşturma",
    "update_card": "Kart güncelleme / taşıma / tamamlama",
    "add_note": "Karta not ekleme",
    "create_event": "Takvime etkinlik / zaman bloğu ekleme",
    "split_card": "Kartı parçalara bölme",
    "link_cards": "Kartları ön koşulla bağlama",
    "plan_day": "Gün planına madde ekleme",
    "schedule_day": "Günü saat saat planlama (kartlar + takvim blokları)",
    "triage_inbox": "Gelen Kutusu'ndaki kartları board'lara dağıtma",
    **CONTENT_ACTION_TYPES,
    **DELETE_ACTION_TYPES,
    **MEMORY_ACTION_TYPES,
}

PRIORITIES = ("low", "medium", "high")
STATUSES = ("pending", "in_progress", "completed")
_DAY = {"type": "string", "description": "YYYY-MM-DD"}
_DT = {
    "type": "string",
    "description": "ISO 8601, kullanıcının saat dilimi ofsetiyle (örn. 2026-11-09T18:00:00+03:00)",
}

WRITE_SPECS: list[ToolSpec] = [
    ToolSpec(
        "create_card",
        "Yeni kart oluşturur. Board id'si gerekir (list_boards). Liste verilmezse board'un ilk listesine eklenir. parent_id verilirse alt kart olur. labels (etiket adları) ve checklist (madde metinleri, en fazla 20) ile birlikte oluşturulabilir.",
        {
            "type": "object",
            "properties": {
                "board_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "list_name": {"type": "string"},
                "due_date": _DAY,
                "estimated_minutes": {"type": "integer"},
                "priority": {"type": "string", "enum": list(PRIORITIES)},
                "parent_id": {"type": "integer"},
                "labels": {"type": "array", "items": {"type": "string"}},
                "checklist": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["board_id", "title"],
        },
    ),
    ToolSpec(
        "update_card",
        "Kartı günceller: başlık, açıklama, son tarih, tahmini süre, öncelik, durum (completed = tamamla) ya da başka listeye taşıma (list_name). Sadece değişecek alanları gönder. Etiket için set_card_labels, checklist için add_checklist_items / update_checklist_items kullan.",
        {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "due_date": _DAY,
                "estimated_minutes": {"type": "integer"},
                "priority": {"type": "string", "enum": list(PRIORITIES)},
                "status": {"type": "string", "enum": list(STATUSES)},
                "list_name": {"type": "string"},
            },
            "required": ["card_id"],
        },
    ),
    ToolSpec(
        "add_note",
        "Karta not ekler (markdown).",
        {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer"},
                "content": {"type": "string"},
            },
            "required": ["card_id", "content"],
        },
    ),
    ToolSpec(
        "create_event",
        "Takvime etkinlik ekler. card_id verilirse o kart için ayrılmış zaman bloğu olur (başlık ve board karttan gelir).",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_at": _DT,
                "end_at": _DT,
                "card_id": {"type": "integer"},
                "board_id": {"type": "integer"},
                "location": {"type": "string"},
            },
            "required": ["start_at", "end_at"],
        },
    ),
    ToolSpec(
        "split_card",
        "Kartı alt kartlara böler: 'parts' (eşit parça sayısı) ya da 'titles' (parça başlıkları). total_minutes parçalara dağıtılır; chain=true ise parçalar sırayla birbirine bağlanır.",
        {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer"},
                "parts": {"type": "integer"},
                "titles": {"type": "array", "items": {"type": "string"}},
                "total_minutes": {"type": "integer"},
                "chain": {"type": "boolean"},
            },
            "required": ["card_id"],
        },
    ),
    ToolSpec(
        "link_cards",
        "Ön koşul bağlar: card_id, depends_on_id bitmeden başlayamaz.",
        {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer"},
                "depends_on_id": {"type": "integer"},
            },
            "required": ["card_id", "depends_on_id"],
        },
    ),
    ToolSpec(
        "plan_day",
        "Bir günün planına madde ekler (mevcut maddeler korunur). Her madde card_id ya da title içerir; planned_minutes opsiyonel.",
        {
            "type": "object",
            "properties": {
                "date": _DAY,
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "card_id": {"type": "integer"},
                            "title": {"type": "string"},
                            "planned_minutes": {"type": "integer"},
                        },
                    },
                },
            },
            "required": ["date", "items"],
        },
    ),
]

WRITE_SPECS += [SCHEDULE_SPEC, *CONTENT_SPECS, *DELETE_SPECS, *MEMORY_SPECS]
WRITE_TOOL_NAMES = {s.name for s in WRITE_SPECS}


def action_type_of(tool_name: str) -> str:
    """Arac adi -> izin turu (orn. save_goal -> manage_goal)."""
    return CONTENT_TOOL_TO_ACTION.get(tool_name) or TOOL_TO_ACTION.get(
        tool_name, tool_name
    )


_DAY_FMT = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_MONTHS = [
    "Oca",
    "Şub",
    "Mar",
    "Nis",
    "May",
    "Haz",
    "Tem",
    "Ağu",
    "Eyl",
    "Eki",
    "Kas",
    "Ara",
]


def _fmt_day(d: date) -> str:
    return f"{_DAY_FMT[d.weekday()]} {d.day} {_MONTHS[d.month - 1]}"


def _fmt_dt(dt: datetime) -> str:
    return f"{_fmt_day(dt.date())} {dt:%H:%M}"


def _parse_day(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as e:
        raise ValueError(f"{field} YYYY-MM-DD olmalı (gelen: {value})") from e


def _due_iso(value: Any, tz: ZoneInfo) -> str:
    """Son tarih: o gunun yerel 23:59'u (kanban'daki tarih secici ile ayni mantik)."""
    d = _parse_day(value, "due_date")
    return datetime.combine(d, time(23, 59), tzinfo=tz).isoformat()


def _parse_dt(value: Any, field: str, tz: ZoneInfo) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError as e:
        raise ValueError(f"{field} ISO 8601 tarih-saat olmalı (gelen: {value})") from e
    if len(str(value)) <= 10:
        raise ValueError(f"{field} saat de içermeli (örn. 2026-11-09T18:00:00+03:00)")
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def _int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field} tam sayı olmalı (gelen: {value})") from e


def _clip(text: str, n: int = 60) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def triage_summary(moves: list[dict[str, Any]]) -> str:
    """Gelen Kutusu dagitiminin onay karti metni (cikarilan maddelerden sonra yeniden kurulur)."""
    lines = [
        f"• {_clip(m['title'], 50)} → {m['board']} / {m['list']}"
        + (f" — {_clip(m['reason'], 80)}" if m.get("reason") else "")
        for m in moves
    ]
    return f"📥 Gelen Kutusu'ndan {len(moves)} kart taşınır:\n" + "\n".join(lines)


def without_cards(args: dict[str, Any], card_ids: set[int]) -> dict[str, Any]:
    """Dagitim isleminden kullanicinin cikardigi kartlar (onaydan once)."""
    return {**args, "moves": [m for m in args["moves"] if m["card_id"] not in card_ids]}


@dataclass
class PreparedAction:
    action_type: str
    args: dict[str, Any]  # execute() icin cozulmus argumanlar
    summary: str  # onay kartinda gorunen metin


class WriteTools:
    def __init__(
        self,
        api: TaskApiClient,
        privacy: PrivacyFilter,
        tz: ZoneInfo,
        memory: MemoryTools | None = None,
    ):
        self.api = api
        self.privacy = privacy
        self.tz = tz
        # Hafiza islemleri (asistan DB'si); yoksa hafiza araclari kapali
        self.memory = memory

    # ---------------- yardimcilar ----------------
    async def _card(self, card_id: Any) -> dict[str, Any]:
        cid = _int(card_id, "card_id")
        if self.privacy.card_hidden(cid):
            raise ValueError(HIDDEN_MESSAGE)
        card = await self.api.get(f"/cards/{cid}")
        if self.privacy.board_hidden(card.get("board_id")):
            raise ValueError(HIDDEN_MESSAGE)
        return card

    async def _board(self, board_id: Any) -> dict[str, Any]:
        bid = _int(board_id, "board_id")
        if self.privacy.board_hidden(bid):
            raise ValueError(HIDDEN_MESSAGE)
        return await self.api.get(f"/boards/{bid}")

    @staticmethod
    def _find_list(board: dict[str, Any], name: str | None) -> dict[str, Any]:
        lists = board["lists"]
        if not lists:
            raise ValueError(f"'{board['board']['name']}' board'unda liste yok")
        if name:
            match = [x for x in lists if x["name"].casefold() == name.casefold()]
            if not match:
                names = ", ".join(x["name"] for x in lists)
                raise ValueError(f"'{name}' listesi yok. Mevcut listeler: {names}")
            return match[0]
        return next((x for x in lists if not x["is_done_list"]), lists[0])

    # ---------------- hazirlik ----------------
    async def prepare(self, name: str, args: dict[str, Any]) -> PreparedAction:
        if name == "delete_cards":
            body, summary = await prepare_delete_cards(self.api, self.privacy, **args)
            return PreparedAction(name, body, summary)
        if name == "cancel_day":
            body, summary = await prepare_cancel_day(
                self.api, self.privacy, self.tz, **args
            )
            return PreparedAction(name, body, summary)
        if name == "tidy_facts":
            if self.memory is None:
                raise ValueError("Hafıza şu an kullanılamıyor")
            body, summary = await self.memory.prepare_tidy(**args)
            return PreparedAction(action_type_of(name), body, summary)
        if name in ("remember_fact", "forget_fact"):
            if self.memory is None:
                raise ValueError("Hafıza şu an kullanılamıyor")
            if name == "remember_fact":
                body, summary = await self.memory.prepare_remember(**args)
            else:
                body, summary = await self.memory.prepare_forget(**args)
            return PreparedAction(action_type_of(name), body, summary)
        handler = getattr(self, f"_prepare_{name}", None)
        if handler is None:
            raise ValueError(f"Bilinmeyen araç: {name}")
        return await handler(**args)

    async def _prepare_create_card(
        self,
        board_id: Any,
        title: str,
        description: str | None = None,
        list_name: str | None = None,
        due_date: Any = None,
        estimated_minutes: Any = None,
        priority: str | None = None,
        parent_id: Any = None,
        labels: list[str] | None = None,
        checklist: list[str] | None = None,
    ) -> PreparedAction:
        if not str(title).strip():
            raise ValueError("Başlık boş olamaz")
        board = await self._board(board_id)
        lst = self._find_list(board, list_name)
        body: dict[str, Any] = {"list_id": lst["id"], "title": str(title).strip()[:200]}
        extra = []
        if description:
            body["description"] = description
        if due_date:
            body["due_date"] = _due_iso(due_date, self.tz)
            extra.append(f"son tarih {_fmt_day(_parse_day(due_date, 'due_date'))}")
        if estimated_minutes is not None:
            body["estimated_minutes"] = _int(estimated_minutes, "estimated_minutes")
            extra.append(f"⏱ {body['estimated_minutes']} dk")
        if priority:
            if priority not in PRIORITIES:
                raise ValueError(
                    f"priority şunlardan biri olmalı: {', '.join(PRIORITIES)}"
                )
            body["priority"] = priority
        if parent_id is not None:
            parent = await self._card(parent_id)
            body["parent_id"] = parent["id"]
            extra.append(f"'{_clip(parent['title'], 40)}' kartının alt kartı")
        summary = f"🗂 Yeni kart: '{_clip(body['title'])}' → {board['board']['name']} / {lst['name']}"
        if extra:
            summary += " (" + ", ".join(extra) + ")"
        names = names_list(labels, "labels")
        if names:
            found, missing = split_known(names, board.get("labels", []))
            if found or missing:
                body["_labels"] = {
                    "board_id": board["board"]["id"],
                    "add_ids": [lb["id"] for lb in found],
                    "add_new": missing,
                }
                summary += "\n🏷 " + label_line(found, missing, board.get("labels", []))
        if checklist:
            items = clean_texts(checklist, "checklist")
            body["_checklist"] = items
            summary += (
                f"\n☑️ {len(items)} madde: "
                + ", ".join(f"«{_clip(i, 40)}»" for i in items)
            )
        return PreparedAction("create_card", body, summary)

    # ---------------- checklist / etiket (Faz 8a) ----------------
    async def _prepare_add_checklist_items(
        self, card_id: Any, items: Any
    ) -> PreparedAction:
        card = await self._card(card_id)
        wanted = clean_texts(items)
        have = {i["text"].casefold() for i in card.get("checklist", [])}
        new = [t for t in wanted if t.casefold() not in have]
        dupes = [t for t in wanted if t.casefold() in have]
        if not new:
            raise ValueError(
                "Bu maddelerin hepsi kartta zaten var: " + ", ".join(dupes)
            )
        summary = (
            f"☑️ '{_clip(card['title'], 40)}' kartına {len(new)} madde: "
            + ", ".join(f"«{_clip(t, 40)}»" for t in new)
        )
        if dupes:
            summary += " (zaten var: " + ", ".join(_clip(t, 30) for t in dupes) + ")"
        return PreparedAction(
            "edit_checklist",
            {"card_id": card["id"], "add": new, "changes": []},
            summary,
        )

    async def _prepare_update_checklist_items(
        self, card_id: Any, changes: Any
    ) -> PreparedAction:
        card = await self._card(card_id)
        if not isinstance(changes, list) or not changes:
            raise ValueError("changes en az bir değişiklik içermeli")
        items = {i["id"]: i for i in card.get("checklist", [])}
        out: list[dict[str, Any]] = []
        lines = []
        for ch in changes:
            iid = _int(ch.get("item_id"), "item_id")
            item = items.get(iid)
            if item is None:
                raise ValueError(
                    f"{iid} numaralı madde kartta yok; get_card ile id'leri al"
                )
            entry: dict[str, Any] = {"item_id": iid}
            what = []
            if ch.get("is_done") is not None:
                entry["is_done"] = bool(ch["is_done"])
                what.append("✓ tamamlandı" if entry["is_done"] else "□ yeniden açılır")
            if ch.get("text") is not None:
                text = str(ch["text"]).strip()[:500]
                if not text:
                    raise ValueError("Madde metni boş olamaz")
                entry["text"] = text
                what.append(f"→ «{_clip(text, 40)}»")
            if not what:
                raise ValueError("Her değişiklikte is_done ya da text olmalı")
            lines.append(f"«{_clip(item['text'], 40)}» " + " ".join(what))
            out.append(entry)
        summary = f"☑️ '{_clip(card['title'], 40)}': " + "; ".join(lines)
        return PreparedAction(
            "edit_checklist",
            {"card_id": card["id"], "add": [], "changes": out},
            summary,
        )

    async def _prepare_delete_checklist_items(
        self, card_id: Any, item_ids: Any
    ) -> PreparedAction:
        card = await self._card(card_id)
        if not isinstance(item_ids, list) or not item_ids:
            raise ValueError("item_ids en az bir id içermeli")
        items = {i["id"]: i for i in card.get("checklist", [])}
        ids = list(dict.fromkeys(_int(i, "item_id") for i in item_ids))
        for iid in ids:
            if iid not in items:
                raise ValueError(
                    f"{iid} numaralı madde kartta yok; get_card ile id'leri al"
                )
        listing = "\n".join(f"- {_clip(items[i]['text'], 60)}" for i in ids)
        summary = (
            f"🗑 '{_clip(card['title'], 40)}' checklist'inden "
            f"{len(ids)} madde silinir:\n{listing}"
        )
        return PreparedAction(
            "delete_checklist_items", {"card_id": card["id"], "item_ids": ids}, summary
        )

    async def _prepare_set_card_labels(
        self, card_id: Any, add: Any = None, remove: Any = None
    ) -> PreparedAction:
        card = await self._card(card_id)
        add_names, remove_names = names_list(add, "add"), names_list(remove, "remove")
        if not add_names and not remove_names:
            raise ValueError("add ya da remove ile en az bir etiket adı ver")
        board = await self._board(card["board_id"])
        board_labels = board.get("labels", [])
        on_card = set(card.get("label_ids", []))
        found, missing = split_known(add_names, board_labels)
        found = [lb for lb in found if lb["id"] not in on_card]  # zaten takili
        gone, unknown = split_known(remove_names, board_labels)
        gone = [lb for lb in gone if lb["id"] in on_card]
        if not found and not missing and not gone:
            raise ValueError("Değişiklik yok: etiketler kartta zaten istenen durumda")
        line = label_line(found, missing, board_labels, gone)
        if unknown:
            line += f" (yok sayıldı: {', '.join(unknown)} etiketi board'da yok)"
        return PreparedAction(
            "manage_labels",
            {
                "card_id": card["id"],
                "board_id": card["board_id"],
                "add_ids": [lb["id"] for lb in found],
                "add_new": missing,
                "remove_ids": [lb["id"] for lb in gone],
            },
            f"🏷 '{_clip(card['title'], 40)}': {line}",
        )

    async def _prepare_update_card(
        self,
        card_id: Any,
        title: str | None = None,
        description: str | None = None,
        due_date: Any = None,
        estimated_minutes: Any = None,
        priority: str | None = None,
        status: str | None = None,
        list_name: str | None = None,
    ) -> PreparedAction:
        card = await self._card(card_id)
        patch: dict[str, Any] = {}
        changes = []
        if title:
            patch["title"] = str(title).strip()[:200]
            changes.append(f"başlık → '{_clip(patch['title'], 40)}'")
        if description is not None:
            patch["description"] = description
            changes.append("açıklama güncellenir")
        if due_date:
            patch["due_date"] = _due_iso(due_date, self.tz)
            changes.append(f"son tarih → {_fmt_day(_parse_day(due_date, 'due_date'))}")
        if estimated_minutes is not None:
            patch["estimated_minutes"] = _int(estimated_minutes, "estimated_minutes")
            changes.append(f"tahmin → {patch['estimated_minutes']} dk")
        if priority:
            if priority not in PRIORITIES:
                raise ValueError(
                    f"priority şunlardan biri olmalı: {', '.join(PRIORITIES)}"
                )
            patch["priority"] = priority
            changes.append(f"öncelik → {priority}")
        if status:
            if status not in STATUSES:
                raise ValueError(f"status şunlardan biri olmalı: {', '.join(STATUSES)}")
            patch["status"] = status
            changes.append(
                {
                    "completed": "tamamlandı olarak işaretlenir",
                    "in_progress": "'devam ediyor' yapılır",
                    "pending": "yeniden açılır",
                }[status]
            )
        move_to = None
        if list_name:
            board = await self._board(card["board_id"])
            lst = self._find_list(board, list_name)
            move_to = lst["id"]
            changes.append(f"'{lst['name']}' listesine taşınır")
        if not patch and move_to is None:
            raise ValueError("Değişecek bir alan verilmedi")
        summary = f"✏️ '{_clip(card['title'])}': " + ", ".join(changes)
        return PreparedAction(
            "update_card",
            {"card_id": card["id"], "patch": patch, "move_to": move_to},
            summary,
        )

    async def _prepare_add_note(self, card_id: Any, content: str) -> PreparedAction:
        if not str(content).strip():
            raise ValueError("Not boş olamaz")
        card = await self._card(card_id)
        return PreparedAction(
            "add_note",
            {"card_id": card["id"], "content": str(content).strip()},
            f"📝 '{_clip(card['title'], 40)}' kartına not: «{_clip(str(content).strip(), 80)}»",
        )

    async def _prepare_create_event(
        self,
        start_at: Any,
        end_at: Any,
        title: str | None = None,
        card_id: Any = None,
        board_id: Any = None,
        location: str | None = None,
    ) -> PreparedAction:
        start = _parse_dt(start_at, "start_at", self.tz)
        end = _parse_dt(end_at, "end_at", self.tz)
        if end <= start:
            raise ValueError("end_at, start_at'ten sonra olmalı")
        body: dict[str, Any] = {
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        }
        where = ""
        if card_id is not None:
            card = await self._card(card_id)
            body["card_id"] = card["id"]
            label = title or card["title"]
            board = (
                await self.api.get(f"/boards/{card['board_id']}")
                if card.get("board_id")
                else None
            )
            where = (
                f" ({board['board']['name']}, karta zaman bloğu)"
                if board
                else " (karta zaman bloğu)"
            )
        else:
            if not title:
                raise ValueError("Karta bağlı değilse title gerekli")
            label = title
            if board_id is not None:
                board = await self._board(board_id)
                body["board_id"] = board["board"]["id"]
                where = f" ({board['board']['name']})"
        if title:
            body["title"] = str(title)[:200]
        if location:
            body["location"] = location
        local_start, local_end = start.astimezone(self.tz), end.astimezone(self.tz)
        span = (
            f"{_fmt_dt(local_start)}–{local_end:%H:%M}"
            if local_start.date() == local_end.date()
            else f"{_fmt_dt(local_start)} – {_fmt_dt(local_end)}"
        )
        return PreparedAction(
            "create_event", body, f"📅 '{_clip(label)}' — {span}{where}"
        )

    async def _prepare_split_card(
        self,
        card_id: Any,
        parts: Any = None,
        titles: list[str] | None = None,
        total_minutes: Any = None,
        chain: bool = True,
    ) -> PreparedAction:
        card = await self._card(card_id)
        body: dict[str, Any] = {"chain": bool(chain)}
        if titles:
            body["titles"] = [str(t) for t in titles if str(t).strip()][:50]
            n = len(body["titles"])
        elif parts is not None:
            n = _int(parts, "parts")
            if not 1 <= n <= 50:
                raise ValueError("parts 1-50 arası olmalı")
            body["parts"] = n
        else:
            raise ValueError("'parts' ya da 'titles' gerekli")
        if total_minutes is not None:
            body["total_minutes"] = _int(total_minutes, "total_minutes")
        hours = (body.get("total_minutes") or card.get("estimated_minutes") or 0) / 60
        summary = f"✂️ '{_clip(card['title'])}' → {n} alt kart"
        if hours:
            summary += f", toplam {hours:g} saat"
        if body["chain"]:
            summary += ", sırayla birbirine bağlı"
        return PreparedAction("split_card", {"card_id": card["id"], **body}, summary)

    async def _prepare_link_cards(
        self, card_id: Any, depends_on_id: Any
    ) -> PreparedAction:
        card = await self._card(card_id)
        dep = await self._card(depends_on_id)
        if card["id"] == dep["id"]:
            raise ValueError("Kart kendisine bağlanamaz")
        return PreparedAction(
            "link_cards",
            {"card_id": card["id"], "depends_on_id": dep["id"]},
            f"⛓ '{_clip(card['title'], 40)}', '{_clip(dep['title'], 40)}' bitmeden başlamayacak",
        )

    async def _prepare_plan_day(
        self, date: Any, items: list[dict[str, Any]]
    ) -> PreparedAction:  # noqa: A002
        day = _parse_day(date, "date")
        if not items:
            raise ValueError("En az bir madde gerekli")
        plan = await self.api.get(f"/day-plans/{day.isoformat()}")
        if plan.get("status") == "reviewed":
            raise ValueError("Bu gün değerlendirildi; planı değiştirilemez")
        new: list[dict[str, Any]] = []
        titles = []
        for it in items:
            entry: dict[str, Any] = {}
            if it.get("card_id") is not None:
                card = await self._card(it["card_id"])
                entry["card_id"] = card["id"]
                titles.append(card["title"])
            elif it.get("event_id") is not None:
                eid = _int(it["event_id"], "event_id")
                event = await self.api.get(f"/events/{eid}")
                if self.privacy.board_hidden(event.get("board_id")):
                    raise ValueError(HIDDEN_MESSAGE)
                entry["event_id"] = eid
                titles.append(event["title"])
            elif it.get("title"):
                entry["title"] = str(it["title"])[:200]
                titles.append(entry["title"])
            else:
                raise ValueError("Her madde card_id, event_id ya da title içermeli")
            if it.get("planned_minutes") is not None:
                entry["planned_minutes"] = _int(
                    it["planned_minutes"], "planned_minutes"
                )
            new.append(entry)
        summary = f"🗓 {_fmt_day(day)} planına {len(new)} madde: " + ", ".join(
            _clip(t, 30) for t in titles
        )
        return PreparedAction(
            "plan_day", {"date": day.isoformat(), "items": new}, summary
        )

    async def _prepare_triage_inbox(
        self, moves: list[dict[str, Any]]
    ) -> PreparedAction:
        """Gelen Kutusu kartlarini board listelerine tasima onerisi (id'ler cozulur)."""
        if not moves:
            raise ValueError("En az bir kart gerekli")
        resolved: list[dict[str, Any]] = []
        boards: dict[int, dict[str, Any]] = {}
        seen: set[int] = set()
        for m in moves:
            card = await self._card(m.get("card_id"))
            if card["id"] in seen:
                continue
            seen.add(card["id"])
            bid = _int(m.get("board_id"), "board_id")
            if bid not in boards:
                boards[bid] = await self._board(bid)
            board = boards[bid]
            if board["board"].get("system_kind"):
                raise ValueError("Kart Gelen Kutusu'nun kendisine taşınamaz")
            if card["board_id"] == bid:
                continue  # zaten orada
            wanted = m.get("list_id")
            lst = next((x for x in board["lists"] if x["id"] == wanted), None)
            lst = lst or self._find_list(board, None)
            resolved.append(
                {
                    "card_id": card["id"],
                    "title": card["title"],
                    "from_board_id": card["board_id"],
                    "board_id": bid,
                    "board": board["board"]["name"],
                    "list_id": lst["id"],
                    "list": lst["name"],
                    "reason": str(m["reason"])[:300] if m.get("reason") else None,
                }
            )
        if not resolved:
            raise ValueError("Taşınacak kart kalmadı")
        return PreparedAction(
            "triage_inbox", {"moves": resolved}, triage_summary(resolved)
        )

    async def _check_calendar_conflicts(self, target: date, timeline: list) -> None:
        """Yeni bloklar o gunun saatli etkinlikleriyle (Teams toplantisi...) cakismasin."""
        start = datetime.combine(target, time(0), tzinfo=self.tz)
        # Bloklar gece yarisini gecebilir: ertesi gunun sonuna kadar bak
        cal = await self.api.get(
            "/calendar",
            start=start.isoformat(),
            end=(start + timedelta(days=2)).isoformat(),
        )
        events = [
            i if self.privacy.keep(i) else {**i, "title": "Başka bir etkinlik"}
            for i in cal.get("items", [])
        ]
        conflict = find_conflict(timeline, target, self.tz, events)
        if conflict:
            raise ValueError(conflict)

    async def _prepare_schedule_day(
        self, day: Any, blocks: list[dict[str, Any]]
    ) -> PreparedAction:
        target = resolve_day(day, datetime.now(self.tz).date())
        if target < datetime.now(self.tz).date():
            raise ValueError(f"{_fmt_day(target)} geçmişte kaldı; ileri bir gün ver")
        timeline = build_timeline(blocks if isinstance(blocks, list) else [])
        await self._check_calendar_conflicts(target, timeline)
        boards = [
            b
            for b in await self.api.get("/boards")
            if not self.privacy.board_hidden(b["id"])
        ]
        default = boards[0] if boards else None
        out: list[dict[str, Any]] = []
        lines = []
        lists: dict[int, dict[str, Any]] = {}
        for blk in timeline:
            item: dict[str, Any] = {
                "title": blk.title,
                "start_at": to_datetime(target, blk.start, self.tz).isoformat(),
                "end_at": to_datetime(target, blk.end, self.tz).isoformat(),
                "minutes": blk.end - blk.start,
                "card": blk.card,
            }
            board = find_board(boards, blk.board)
            if blk.board not in (None, "") and board is None:
                names = ", ".join(b["name"] for b in boards)
                raise ValueError(
                    f"'{blk.title}' için board '{blk.board}' bulunamadı. Mevcut: {names}"
                )
            if blk.card:
                board = board or default
                if board is None:
                    raise ValueError("Kart için önce bir board oluşturulmalı")
                if board["id"] not in lists:
                    lists[board["id"]] = self._find_list(
                        await self._board(board["id"]), None
                    )
                item["list_id"] = lists[board["id"]]["id"]
            if board is not None:
                item["board_id"] = board["id"]
            kind = f"kart, {board['name']}" if blk.card and board else "etkinlik"
            lines.append(f"{hhmm(blk.start)}–{hhmm(blk.end)} {blk.title} ({kind})")
            out.append(item)
        cards = sum(1 for i in out if i["card"])
        summary = (
            f"🗓 {_fmt_day(target)} planı: {cards} kart, "
            f"{len(out) - cards} sabit etkinlik, hepsi takvime\n" + "\n".join(lines)
        )
        return PreparedAction(
            "schedule_day", {"date": target.isoformat(), "blocks": out}, summary
        )

    async def _prepare_save_goal(
        self, goal_id: Any = None, **fields: Any
    ) -> PreparedAction:
        body = validate_goal_args({"goal_id": goal_id, **fields})
        if body.get("board_id") is not None:
            board = await self._board(body["board_id"])
            board_name = board["board"]["name"]
        else:
            board_name = None
        details = []
        if body.get("target_date"):
            details.append(
                f"hedef tarih {_fmt_day(date.fromisoformat(body['target_date']))}"
            )
        if board_name:
            details.append(board_name)
        if goal_id is not None:
            goals = {g["id"]: g for g in await self.api.get("/goals")}
            gid = _int(goal_id, "goal_id")
            if gid not in goals:
                raise ValueError(f"{gid} numaralı hedef bulunamadı")
            if self.privacy.board_hidden(goals[gid].get("board_id")):
                raise ValueError(HIDDEN_MESSAGE)
            status = {
                "achieved": "ulaşıldı olarak işaretlenir",
                "dropped": "bırakıldı olarak işaretlenir",
                "active": "yeniden aktif",
            }
            if "status" in body:
                details.insert(0, status[body["status"]])
            summary = f"🎯 Hedef güncellenir: '{_clip(goals[gid]['title'])}'"
            return PreparedAction(
                "manage_goal",
                {"goal_id": gid, "body": body},
                summary + (" (" + ", ".join(details) + ")" if details else ""),
            )
        summary = f"🎯 Yeni hedef: '{_clip(body['title'])}'" + (
            " (" + ", ".join(details) + ")" if details else ""
        )
        if body.get("why"):
            summary += f" — neden: «{_clip(body['why'], 60)}»"
        return PreparedAction("manage_goal", {"goal_id": None, "body": body}, summary)

    # ---------------- calistirma ----------------
    async def execute(self, action_type: str, args: dict[str, Any]) -> dict[str, Any]:
        api = self.api
        if action_type in ("remember_fact", "forget_fact"):
            if self.memory is None:
                raise ValueError("Hafıza şu an kullanılamıyor")
            return await self.memory.execute(action_type, args)
        if action_type == "manage_goal":
            if args.get("goal_id") is None:
                g = await api.write("POST", "/goals", args["body"])
            else:
                g = await api.write("PATCH", f"/goals/{args['goal_id']}", args["body"])
            return {"goal_id": g["id"], "title": g["title"], "status": g["status"]}
        if action_type == "create_card":
            return await self._execute_create_card(api, args)
        if action_type == "edit_checklist":
            return await execute_checklist(api, args)
        if action_type == "delete_checklist_items":
            return await execute_delete_items(api, args)
        if action_type == "manage_labels":
            return await apply_labels(
                api,
                args["card_id"],
                args["board_id"],
                args["add_ids"],
                args["add_new"],
                args["remove_ids"],
            )
        if action_type == "update_card":
            if args["patch"]:
                await api.write("PATCH", f"/cards/{args['card_id']}", args["patch"])
            if args.get("move_to") is not None:
                # index sona kirpilir -> listenin sonuna tasi
                await api.write(
                    "POST",
                    f"/cards/{args['card_id']}/move",
                    {"list_id": args["move_to"], "index": 100000},
                )
            c = await api.get(f"/cards/{args['card_id']}")
            return {"card_id": c["id"], "title": c["title"], "status": c["status"]}
        if action_type == "add_note":
            n = await api.write(
                "POST", f"/cards/{args['card_id']}/notes", {"content": args["content"]}
            )
            return {"note_id": n["id"]}
        if action_type == "create_event":
            e = await api.write("POST", "/events", args)
            return {"event_id": e["id"], "title": e["title"], "start_at": e["start_at"]}
        if action_type == "split_card":
            body = {k: v for k, v in args.items() if k != "card_id"}
            c = await api.write("POST", f"/cards/{args['card_id']}/split", body)
            return {
                "subtasks": [
                    {"id": s["id"], "title": s["title"]} for s in c["subtasks"]
                ]
            }
        if action_type == "link_cards":
            await api.write(
                "POST",
                f"/cards/{args['card_id']}/dependencies",
                {"depends_on_id": args["depends_on_id"]},
            )
            return {"linked": True}
        if action_type == "schedule_day":
            return await self._execute_schedule(api, args)
        if action_type == "triage_inbox":
            return await self._execute_triage(api, args)
        if action_type in ("delete_cards", "cancel_day"):
            return await execute_delete(api, action_type, args)
        if action_type == "plan_day":
            # Onay aninda mevcut planla yeniden birlestir (arada elle degismis olabilir)
            plan = await api.get(f"/day-plans/{args['date']}")
            existing = [
                {
                    k: i[k]
                    for k in ("card_id", "event_id", "planned_minutes")
                    if i.get(k) is not None
                }
                | (
                    {}
                    if i.get("card_id") or i.get("event_id")
                    else {"title": i["title"]}
                )
                for i in plan.get("items", [])
                if i["was_planned"]
            ]
            have = {i.get("card_id") for i in existing if i.get("card_id")}
            have_ev = {i.get("event_id") for i in existing if i.get("event_id")}
            merged = existing + [
                i
                for i in args["items"]
                if not (i.get("card_id") and i["card_id"] in have)
                and not (i.get("event_id") and i["event_id"] in have_ev)
            ]
            p = await api.write("PUT", f"/day-plans/{args['date']}", {"items": merged})
            return {"date": p["date"], "items": len(p["items"])}
        raise ValueError(f"Bilinmeyen işlem: {action_type}")

    async def _execute_create_card(
        self, api: TaskApiClient, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Karti olusturur; etiket/checklist adimlari kartin kendisini bozmaz: biri
        hata verirse kart yine de olusmustur, sonuc neyin eksik kaldigini soyler."""
        body = {k: v for k, v in args.items() if not k.startswith("_")}
        c = await api.write("POST", "/cards", body)
        out: dict[str, Any] = {"card_id": c["id"], "title": c["title"]}
        warnings: list[str] = []
        if args.get("_labels"):
            lb = args["_labels"]
            try:
                await apply_labels(
                    api, c["id"], lb["board_id"], lb["add_ids"], lb["add_new"], []
                )
            except TaskApiError as e:
                warnings.append(f"etiket eklenemedi: {e.message}")
        if args.get("_checklist"):
            try:
                await execute_checklist(
                    api, {"card_id": c["id"], "add": args["_checklist"]}
                )
            except TaskApiError as e:
                warnings.append(f"checklist eklenemedi: {e.message}")
        if warnings:
            out["note"] = "Kart oluşturuldu; " + "; ".join(warnings)
        return out

    async def _execute_triage(
        self, api: TaskApiClient, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Kartlari tasir (X-Actor: ai). Arada baska yere tasinmis karta dokunulmaz;
        bir kartin hatasi digerlerini durdurmaz."""
        moved: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for m in args["moves"]:
            try:
                card = await api.get(f"/cards/{m['card_id']}")
                if card.get("board_id") != m["from_board_id"]:
                    skipped.append({"card_id": m["card_id"], "title": m["title"]})
                    continue
                # index sona kirpilir -> listenin sonuna tasi
                await api.write(
                    "POST",
                    f"/cards/{m['card_id']}/move",
                    {"list_id": m["list_id"], "index": 100000},
                )
                moved.append(
                    {"card_id": m["card_id"], "title": m["title"], "board": m["board"]}
                )
            except TaskApiError as err:
                failed.append({"title": m["title"], "error": err.message})
        if not moved and failed:
            raise TaskApiError(422, failed[0]["error"])
        return {"moved": moved, "skipped": skipped, "failed": failed}

    async def _execute_schedule(
        self, api: TaskApiClient, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Kartlar + takvim bloklari; kartlar gun planina eklenir. Bir blok
        basarisiz olsa da digerleri yazilir, sonuc neyin yapildigini soyler."""
        day = args["date"]
        due = _due_iso(day, self.tz)
        done: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        card_ids: list[int] = []
        for b in args["blocks"]:
            try:
                event: dict[str, Any] = {
                    "start_at": b["start_at"],
                    "end_at": b["end_at"],
                }
                if b["card"]:
                    c = await api.write(
                        "POST",
                        "/cards",
                        {
                            "list_id": b["list_id"],
                            "title": b["title"],
                            "due_date": due,
                            "estimated_minutes": b["minutes"],
                        },
                    )
                    card_ids.append(c["id"])
                    event["card_id"] = c["id"]
                else:
                    event["title"] = b["title"]
                    if b.get("board_id"):
                        event["board_id"] = b["board_id"]
                e = await api.write("POST", "/events", event)
                done.append(
                    {
                        "title": b["title"],
                        "event_id": e["id"],
                        "card_id": event.get("card_id"),
                    }
                )
            except TaskApiError as err:
                failed.append({"title": b["title"], "error": err.message})
        if not done:
            raise TaskApiError(
                422, failed[0]["error"] if failed else "Hiçbir blok yazılamadı"
            )
        planned = False
        if card_ids:
            try:
                await self.execute(
                    "plan_day",
                    {"date": day, "items": [{"card_id": c} for c in card_ids]},
                )
                planned = True
            except TaskApiError:
                planned = False  # gun degerlendirilmis olabilir; takvim yine de yazildi
        return {
            "date": day,
            "created": done,
            "failed": failed,
            "added_to_plan": planned,
        }
