"""
Yazma araclari (Faz 5). Her arac iki asamali:

1. prepare(): argumanlari DOGRULAR ve COZER (board -> liste id'si, "2026-11-09"
   -> yerel gun sonu ISO, gizlilik kontrolu) ve kullaniciya gosterilecek Turkce
   ozeti uretir. Hata -> ValueError: model hemen duzeltebilsin diye aciklayici.
2. execute(): onceden cozulmus argumanlarla task-api'ye yazar (X-Actor: ai).

Boylece onay kartinda gordugun sey, onaylayinca yapilan seyin TA KENDISIDIR.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from app.llm.types import ToolSpec
from app.tools.memory_tools import (
    MEMORY_ACTION_TYPES,
    MEMORY_SPECS,
    TOOL_TO_ACTION,
    MemoryTools,
    validate_goal_args,
)
from app.tools.privacy import HIDDEN_MESSAGE, PrivacyFilter
from app.tools.task_api import TaskApiClient

# Islem turleri (izin ayarlari bu anahtarlarla tutulur)
ACTION_TYPES: dict[str, str] = {
    "create_card": "Kart oluşturma",
    "update_card": "Kart güncelleme / taşıma / tamamlama",
    "add_note": "Karta not ekleme",
    "create_event": "Takvime etkinlik / zaman bloğu ekleme",
    "split_card": "Kartı parçalara bölme",
    "link_cards": "Kartları ön koşulla bağlama",
    "plan_day": "Gün planına madde ekleme",
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
        "Yeni kart oluşturur. Board id'si gerekir (list_boards). Liste verilmezse board'un ilk listesine eklenir. parent_id verilirse alt kart olur.",
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
            },
            "required": ["board_id", "title"],
        },
    ),
    ToolSpec(
        "update_card",
        "Kartı günceller: başlık, açıklama, son tarih, tahmini süre, öncelik, durum (completed = tamamla) ya da başka listeye taşıma (list_name). Sadece değişecek alanları gönder.",
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

WRITE_SPECS += MEMORY_SPECS
WRITE_TOOL_NAMES = {s.name for s in WRITE_SPECS}


def action_type_of(tool_name: str) -> str:
    """Arac adi -> izin turu (orn. save_goal -> manage_goal)."""
    return TOOL_TO_ACTION.get(tool_name, tool_name)


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
        return PreparedAction("create_card", body, summary)

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
            elif it.get("title"):
                entry["title"] = str(it["title"])[:200]
                titles.append(entry["title"])
            else:
                raise ValueError("Her madde card_id ya da title içermeli")
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
            c = await api.write("POST", "/cards", args)
            return {"card_id": c["id"], "title": c["title"]}
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
            merged = existing + [
                i
                for i in args["items"]
                if i.get("card_id") not in have or i.get("card_id") is None
            ]
            p = await api.write("PUT", f"/day-plans/{args['date']}", {"items": merged})
            return {"date": p["date"], "items": len(p["items"])}
        raise ValueError(f"Bilinmeyen işlem: {action_type}")
