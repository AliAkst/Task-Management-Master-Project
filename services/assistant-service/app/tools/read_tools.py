"""
Okuma araclari (Faz 4). Yazma araclari (kart/etkinlik olusturma, bolme...)
Faz 5'te izin/onay akisiyla eklenecek.

Ciktilar bilincli olarak KISA: local modelin baglami 16K token; ham API yanitlari
onu hemen doldurur. Her arac sadece gereken alanlari dondurur.
"""

import json
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from app.llm.types import ToolCall, ToolSpec
from app.tools.privacy import HIDDEN_MESSAGE, PrivacyFilter
from app.tools.task_api import TaskApiClient, TaskApiError
from app.tools.write_tools import (
    WRITE_SPECS,
    WRITE_TOOL_NAMES,
    WriteTools,
    action_type_of,
)

if TYPE_CHECKING:
    from app.agent.actions import ActionGate, ToolResult

MAX_RESULT_CHARS = 6000

_DATE = {"type": "string", "description": "YYYY-MM-DD"}


def _clip(text: str | None, n: int) -> str | None:
    if not text:
        return text
    return text if len(text) <= n else text[: n - 1] + "…"


def _card(
    c: dict[str, Any],
    lists: dict[int, str] | None = None,
    labels: dict[int, str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"id": c["id"], "title": c["title"], "status": c["status"]}
    if lists and c.get("list_id") in lists:
        out["list"] = lists[c["list_id"]]
    if labels:
        names = [labels[i] for i in c.get("label_ids") or [] if i in labels]
        if names:
            out["labels"] = names
    for key in ("priority", "due_date", "estimated_minutes"):
        if c.get(key) not in (None, "medium"):
            out[key] = c[key]
    tracked = (c.get("tracked_seconds") or 0) + (c.get("subtask_tracked_seconds") or 0)
    if tracked:
        out["tracked_min"] = round(tracked / 60)
    if c.get("blocked"):
        out["blocked"] = True
    if c.get("parent_id"):
        out["parent_id"] = c["parent_id"]
    if c.get("subtask_total"):
        out["subtasks"] = f"{c['subtask_done']}/{c['subtask_total']}"
    if c.get("checklist_total"):
        out["checklist"] = f"{c['checklist_done']}/{c['checklist_total']}"
    return out


class ToolBox:
    """Bir sohbet turu boyunca yasayan arac seti (kullanicinin token'i ile)."""

    def __init__(self, api: TaskApiClient, privacy: PrivacyFilter, tz: ZoneInfo):
        self.api = api
        self.privacy = privacy
        self.tz = tz
        self._boards: list[dict[str, Any]] | None = None
        self.writer = WriteTools(api, privacy, tz)
        # Yazma araclari sadece izin kapisi baglaninca acilir (Faz 5)
        self.gate: ActionGate | None = None
        # Bu turda modele gosterilmeyen araclar (orn. sohbette hafiza araclari:
        # onlari ayri, odakli hafiza adimi kullanir)
        self.hidden: set[str] = set()
        self._handlers: dict[str, Callable[..., Awaitable[Any]]] = {
            "list_boards": self.list_boards,
            "get_board": self.get_board,
            "search_cards": self.search_cards,
            "get_card": self.get_card,
            "get_calendar": self.get_calendar,
            "get_day_plan": self.get_day_plan,
            "get_stats_summary": self.get_stats_summary,
            "list_goals": self.list_goals,
        }

    # ---------------- kurulum ----------------
    @classmethod
    async def create(
        cls, api: TaskApiClient, *, cloud: bool, tz: ZoneInfo
    ) -> "ToolBox":
        """Cloud model icin gizli board'lari ve kartlarini onceden belirler."""
        box = cls(api, PrivacyFilter(active=cloud), tz)
        if cloud:
            for b in await box.boards():
                if b["privacy"] == "local_only":
                    box.privacy.hidden_boards.add(b["id"])
                    detail = await api.get(f"/boards/{b['id']}")
                    box.privacy.hidden_cards.update(c["id"] for c in detail["cards"])
        return box

    async def boards(self) -> list[dict[str, Any]]:
        if self._boards is None:
            self._boards = await self.api.get("/boards", include_archived=False)
        return self._boards

    # ---------------- arac tanimlari ----------------
    def specs(self) -> list[ToolSpec]:
        """Okuma araclari + (izin kapisi varsa) kullanicinin 'asla' demedigi yazma
        araclari; `hidden` (orn. sohbette hafiza araclari) haric."""
        return [
            s
            for s in self.read_specs() + self.write_specs()
            if s.name not in self.hidden
        ]

    def write_specs(self) -> list[ToolSpec]:
        if self.gate is None:
            return []
        return [s for s in WRITE_SPECS if self.gate.allowed(action_type_of(s.name))]

    @staticmethod
    def read_specs() -> list[ToolSpec]:
        return [
            ToolSpec(
                "list_boards",
                "Kullanıcının hayat alanlarını (board) listeler: ad, kapsam, açık kart sayısı, haftalık süre hedefi.",
            ),
            ToolSpec(
                "get_board",
                "Bir board'un listelerini ve kartlarını getirir (başlık, durum, liste, son tarih, tahmin, harcanan süre, bekleme).",
                {
                    "type": "object",
                    "properties": {"board_id": {"type": "integer"}},
                    "required": ["board_id"],
                },
            ),
            ToolSpec(
                "search_cards",
                "Tüm board'larda kart başlığı/açıklamasında arar. Kart id'sini bulmak için kullan.",
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "include_completed": {"type": "boolean"},
                    },
                    "required": ["query"],
                },
            ),
            ToolSpec(
                "get_card",
                "Kart detayı: açıklama, checklist (madde id'leri update/delete için), etiketler, son notlar, alt kartlar, ön koşullar, harcanan süre, takvim blokları.",
                {
                    "type": "object",
                    "properties": {"card_id": {"type": "integer"}},
                    "required": ["card_id"],
                },
            ),
            ToolSpec(
                "get_calendar",
                "Tarih aralığındaki takvim etkinlikleri ve kart son tarihleri (bitiş dahil).",
                {
                    "type": "object",
                    "properties": {"start_date": _DATE, "end_date": _DATE},
                    "required": ["start_date", "end_date"],
                },
            ),
            ToolSpec(
                "get_day_plan",
                "Bir günün planı ve gün sonu değerlendirmesi (yapıldı/yapılmadı/ertelendi, nedenler, ruh hâli), o gün çalışılan süre.",
                {"type": "object", "properties": {"date": _DATE}, "required": ["date"]},
            ),
            ToolSpec(
                "get_stats_summary",
                "İstatistik özeti: çalışılan süre, plana uyum, tahmin doğruluğu (gerçek/tahmin oranı), verimli saatler, board'lara göre süre, en çok ertelenenler. Varsayılan son 7 gün.",
                {
                    "type": "object",
                    "properties": {"start_date": _DATE, "end_date": _DATE},
                },
            ),
            ToolSpec(
                "list_goals",
                "Kullanıcının hayat hedefleri (aktif, ulaşılmış, bırakılmış): başlık, neden, hedef tarih, ilgili board.",
            ),
        ]

    # ---------------- calistirma ----------------
    async def execute(self, call: ToolCall) -> "ToolResult":
        """Araci calistirir -> modele gidecek JSON metni (+ yazmada islem karti)."""
        from app.agent.actions import ToolResult

        def fail(msg: str) -> ToolResult:
            return ToolResult(json.dumps({"error": msg}, ensure_ascii=False), False)

        if not call.valid:
            return fail("Argümanlar geçerli JSON değil")
        if call.name in WRITE_TOOL_NAMES:
            if self.gate is None or not self.gate.allowed(action_type_of(call.name)):
                return fail("Bu işlem şu an kapalı.")
            try:
                prepared = await self.writer.prepare(call.name, call.arguments)
            except TypeError as e:
                return fail(f"Geçersiz argümanlar: {e}")
            except (TaskApiError, ValueError) as e:
                return fail(getattr(e, "message", str(e)))
            return await self.gate.handle(call, prepared)

        handler = self._handlers.get(call.name)
        if handler is None:
            return fail(f"Bilinmeyen araç: {call.name}")
        try:
            result = await handler(**call.arguments)
            ok = not (isinstance(result, dict) and "error" in result)
        except TypeError as e:  # eksik / fazla arguman
            result, ok = {"error": f"Geçersiz argümanlar: {e}"}, False
        except (TaskApiError, ValueError) as e:
            result, ok = {"error": getattr(e, "message", str(e))}, False
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + '… (kısaltıldı)"'
        return ToolResult(text, ok)

    # ---------------- araclar ----------------
    async def list_boards(self) -> Any:
        return [
            {
                "id": b["id"],
                "name": b["name"],
                "scope": _clip(b.get("scope_description"), 200),
                "open_cards": b["open_card_count"],
                "weekly_budget_min": b.get("weekly_time_budget_min"),
            }
            for b in await self.boards()
            if not self.privacy.board_hidden(b["id"])
        ]

    async def get_board(self, board_id: int) -> Any:
        if self.privacy.board_hidden(board_id):
            return {"error": HIDDEN_MESSAGE}
        d = await self.api.get(f"/boards/{board_id}")
        lists = {lst["id"]: lst["name"] for lst in d["lists"]}
        labels = {lb["id"]: lb["name"] for lb in d.get("labels", [])}
        out: dict[str, Any] = {
            "board": {"id": d["board"]["id"], "name": d["board"]["name"]},
            "lists": [lst["name"] for lst in d["lists"]],
        }
        if labels:
            out["labels"] = list(labels.values())
        out["cards"] = [_card(c, lists, labels) for c in d["cards"]]
        return out

    async def search_cards(self, query: str, include_completed: bool = False) -> Any:
        q = query.casefold().strip()
        if not q:
            raise ValueError("Boş arama")
        found = []
        for b in await self.boards():
            if self.privacy.board_hidden(b["id"]):
                continue
            d = await self.api.get(f"/boards/{b['id']}")
            for c in d["cards"]:
                if not include_completed and c["status"] == "completed":
                    continue
                if q in c["title"].casefold():
                    found.append({**_card(c), "board": b["name"]})
        return found[:30] or {"result": "Eşleşen kart yok"}

    async def get_card(self, card_id: int) -> Any:
        if self.privacy.card_hidden(card_id):
            return {"error": HIDDEN_MESSAGE}
        c = await self.api.get(f"/cards/{card_id}")
        if self.privacy.board_hidden(c.get("board_id")):
            return {"error": HIDDEN_MESSAGE}
        events = await self.api.get(f"/cards/{card_id}/events")
        out = _card(c)
        out["description"] = _clip(c.get("description"), 1500)
        if c["checklist"]:
            out["checklist_items"] = [
                {"id": i["id"], "text": i["text"], "is_done": i["is_done"]}
                for i in c["checklist"]
            ]
        if c.get("label_ids"):
            board = await self.api.get(f"/boards/{c['board_id']}")
            names = {lb["id"]: lb["name"] for lb in board.get("labels", [])}
            out["labels"] = [
                {"id": i, "name": names[i]} for i in c["label_ids"] if i in names
            ]
        if c.get("attachments"):  # yalniz dosya adlari; icerik modele gitmez (Faz 8c)
            out["attachments"] = [a["filename"] for a in c["attachments"]]
        if c["notes"]:
            out["recent_notes"] = [_clip(n["content"], 300) for n in c["notes"][:5]]
        if c["subtasks"]:
            out["subtask_list"] = [_card(s) for s in c["subtasks"]]
        if c["depends_on"]:
            out["waits_for"] = [
                {"id": d["id"], "title": d["title"], "status": d["status"]}
                for d in c["depends_on"]
            ]
        if events:
            out["scheduled"] = [
                {"start": e["start_at"], "end": e["end_at"]} for e in events[-5:]
            ]
        return out

    def _bounds(self, start: str, end: str) -> tuple[str, str]:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
        if e < s:
            raise ValueError("end_date, start_date'ten önce olamaz")
        if (e - s).days > 62:
            raise ValueError("En fazla 62 günlük takvim sorgulanabilir")
        start_dt = datetime.combine(s, datetime.min.time(), tzinfo=self.tz)
        end_dt = datetime.combine(
            e + timedelta(days=1), datetime.min.time(), tzinfo=self.tz
        )
        return start_dt.isoformat(), end_dt.isoformat()

    async def get_calendar(self, start_date: str, end_date: str) -> Any:
        start, end = self._bounds(start_date, end_date)
        items = await self.api.get("/calendar", start=start, end=end)
        items = self.privacy.filter(items["items"])
        return [
            {
                "type": "deadline" if i["kind"] == "deadline" else "event",
                "title": i["title"],
                "start": i["start"],
                "end": i.get("end"),
                "all_day": i["all_day"],
                **({"card_id": i["card_id"]} if i.get("card_id") else {}),
                **({"card_status": i["card_status"]} if i.get("card_status") else {}),
            }
            for i in items
        ] or {"result": "Bu aralıkta etkinlik yok"}

    async def get_day_plan(self, date: str) -> Any:  # noqa: A002 - arac parametre adi
        p = await self.api.get(f"/day-plans/{date}")
        items = self.privacy.filter(p["items"])
        out: dict[str, Any] = {
            "date": p["date"],
            "planned": p["exists"],
            "tracked_today_min": round(p["tracked_today_sec"] / 60),
        }
        if p["exists"]:
            out.update(
                status=p["status"],
                mood=p["mood"],
                energy=p["energy"],
                reflection=_clip(p["reflection"], 500),
                items=[
                    {
                        "title": i["title"],
                        "planned": i["was_planned"],
                        "planned_min": i["planned_minutes"],
                        "outcome": i["outcome"],
                        "reason": i["reason"],
                        "tracked_min": round(
                            (i["tracked_today_sec"] or i["tracked_sec"]) / 60
                        ),
                    }
                    for i in items
                ],
            )
        return out

    async def get_stats_summary(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> Any:
        today = datetime.now(self.tz).date()
        end = date.fromisoformat(end_date) if end_date else today
        start = (
            date.fromisoformat(start_date) if start_date else end - timedelta(days=6)
        )
        s = await self.api.get(
            "/analytics/summary", start=start.isoformat(), end=end.isoformat()
        )
        acc = s["estimate_accuracy"]
        return {
            "range": f"{start} – {end}",
            "totals": s["totals"],
            "boards": [
                {
                    k: b[k]
                    for k in ("name", "tracked_min", "completed_cards", "budget_min")
                }
                for b in s["boards"]
                if not self.privacy.board_hidden(b["board_id"])
                and (b["tracked_min"] or b["completed_cards"] or b["budget_min"])
            ],
            "estimate_ratio": {
                "mean": acc["mean_ratio"],
                "median": acc["median_ratio"],
                "sample_size": acc["sample_size"],
                "biggest_overruns": [
                    {"title": o["title"], "ratio": o["ratio"]}
                    for o in acc["biggest_overruns"]
                    if not self.privacy.card_hidden(o["card_id"])
                ],
            },
            "busiest_hours": sorted(
                (
                    {"hour": h, "min": m}
                    for h, m in enumerate(s["productive_hours"])
                    if m > 0
                ),
                key=lambda x: -x["min"],
            )[:5],
            "weekday_min": dict(
                zip(
                    ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"],
                    s["weekdays"],
                    strict=True,
                )
            ),
            "most_postponed": [
                {"title": p["title"], "count": p["count"]}
                for p in s["most_postponed"]
                if not self.privacy.card_hidden(p["card_id"])
            ],
            "days": [
                {
                    k: d[k]
                    for k in (
                        "date",
                        "tracked_min",
                        "planned",
                        "done",
                        "not_done",
                        "postponed",
                        "mood",
                        "energy",
                    )
                }
                for d in s["days"]
                if d["tracked_min"] or d["planned"] or d["mood"]
            ],
        }

    async def list_goals(self) -> Any:
        goals = await self.api.get("/goals")
        names = {b["id"]: b["name"] for b in await self.boards()}
        return [
            {
                "id": g["id"],
                "title": g["title"],
                "why": _clip(g.get("why"), 300),
                "target_date": g.get("target_date"),
                "status": g["status"],
                "board": names.get(g.get("board_id")),
            }
            for g in goals
            if not self.privacy.board_hidden(g.get("board_id"))
        ] or {"result": "Henüz hedef yok"}
