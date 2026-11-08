"""
Silme araclari: kart silme (isimle / board'la / hepsi) ve bir gunun planini
iptal etme. Hangi kayitlarin gidecegini KOD bulur; model sadece neyi istedigini
soyler. Silme geri alinamaz: bu islemler izin "otomatik" olsa bile her zaman
onay karti olarak gelir (bkz. ActionGate.ALWAYS_ASK).
"""

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.llm.types import ToolSpec
from app.tools.privacy import PrivacyFilter
from app.tools.schedule_day import find_board, resolve_day
from app.tools.task_api import TaskApiClient, TaskApiError

LIST_LIMIT = 15  # onay kartinda gosterilen en fazla baslik

DELETE_SPECS = [
    ToolSpec(
        "delete_cards",
        "Kartları siler. Şunlardan birini ver: 'titles' (kart adları ya da "
        "adlarının bir parçası), 'board' (o board'daki kartlar) "
        "ya da all=true (bütün kartlar). "
        "include_completed=false ise tamamlanmış kartlar kalır. Kullanıcı onaylamadan "
        "hiçbir şey silinmez.",
        {
            "type": "object",
            "properties": {
                "titles": {"type": "array", "items": {"type": "string"}},
                "board": {"type": "string", "description": "board adı"},
                "all": {"type": "boolean"},
                "include_completed": {"type": "boolean"},
            },
        },
    ),
    ToolSpec(
        "cancel_day",
        "Bir günün planını iptal eder: gün planını boşaltır ve o günün takvim "
        "etkinliklerini kaldırır. delete_cards=true ise o günün planındaki kartları da "
        "siler. Gün: 'bugün', 'yarın', 'salı' ya da YYYY-MM-DD.",
        {
            "type": "object",
            "properties": {
                "day": {"type": "string"},
                "delete_cards": {"type": "boolean"},
            },
            "required": ["day"],
        },
    ),
]
DELETE_ACTION_TYPES = {
    "delete_cards": "Kart silme (her zaman onay ister)",
    "cancel_day": "Gün planını iptal etme (her zaman onay ister)",
}


def _list(titles: list[str]) -> str:
    shown = [f"- {t}" for t in titles[:LIST_LIMIT]]
    if len(titles) > LIST_LIMIT:
        shown.append(f"- … ve {len(titles) - LIST_LIMIT} kart daha")
    return "\n".join(shown)


async def _visible_boards(
    api: TaskApiClient, privacy: PrivacyFilter
) -> list[dict[str, Any]]:
    return [b for b in await api.get("/boards") if not privacy.board_hidden(b["id"])]


async def prepare_delete_cards(
    api: TaskApiClient,
    privacy: PrivacyFilter,
    titles: list[str] | None = None,
    board: Any = None,
    all: bool = False,  # noqa: A002
    include_completed: bool = True,
) -> tuple[dict[str, Any], str]:
    boards = await _visible_boards(api, privacy)
    names = [str(t).strip().casefold() for t in titles or [] if str(t).strip()]
    if not names and board in (None, "") and not all:
        raise ValueError("Neyi sileceğimi söyle: titles, board ya da all=true")
    scope = boards
    if board not in (None, ""):
        b = find_board(boards, board)
        if b is None:
            raise ValueError(
                f"'{board}' board'u bulunamadı. Mevcut: "
                + ", ".join(x["name"] for x in boards)
            )
        scope = [b]
    cards: list[dict[str, Any]] = []
    for b in scope:
        detail = await api.get(f"/boards/{b['id']}")
        for c in detail["cards"]:
            if privacy.card_hidden(c["id"]):
                continue
            if not include_completed and c["status"] == "completed":
                continue
            if names and not any(n in c["title"].casefold() for n in names):
                continue
            cards.append({"id": c["id"], "title": c["title"], "board": b["name"]})
    if not cards:
        raise ValueError("Bu tarife uyan kart bulunamadı; kart adını kontrol et")
    where = (
        f"'{scope[0]['name']}' board'undaki"
        if board not in (None, "")
        else "bütün board'lardaki"
    )
    what = "adı eşleşen" if names else "tüm"
    summary = (
        f"🗑 {where} {what} {len(cards)} kart kalıcı olarak silinir "
        f"(alt kartlar bağımsız kart olarak kalır)\n"
        + _list([f"{c['title']} ({c['board']})" for c in cards])
    )
    return {"card_ids": [c["id"] for c in cards]}, summary


async def prepare_cancel_day(
    api: TaskApiClient,
    privacy: PrivacyFilter,
    tz: ZoneInfo,
    day: Any,
    delete_cards: bool = False,
) -> tuple[dict[str, Any], str]:
    target: date = resolve_day(day, datetime.now(tz).date())
    plan = await api.get(f"/day-plans/{target.isoformat()}")
    if plan.get("status") == "reviewed":
        raise ValueError("Bu gün değerlendirildi; planı iptal edilemez")
    start = datetime.combine(target, time(0), tzinfo=tz)
    cal = await api.get(
        "/calendar",
        start=start.isoformat(),
        end=(start + timedelta(days=1)).isoformat(),
    )
    events = [
        i
        for i in cal["items"]
        if i["kind"] == "event"
        and not i.get("recurrence_rule")  # tekrarlayan seri bu gun icin silinmez
        and privacy.keep(i)
    ]
    items = [i for i in plan.get("items", []) if i.get("was_planned")]
    card_ids: list[int] = []
    if delete_cards:
        card_ids = sorted(
            {i["card_id"] for i in items if i.get("card_id")}
            | {e["card_id"] for e in events if e.get("card_id")}
        )
    if not items and not events:
        raise ValueError(f"{target.isoformat()} için plan ya da etkinlik yok")
    lines = [f"Plan maddeleri: {len(items)} madde kaldırılır"]
    if events:
        lines.append(f"Takvimden {len(events)} etkinlik kaldırılır:")
        lines.append(_list([e["title"] for e in events]))
    if card_ids:
        lines.append(f"Plandaki {len(card_ids)} kart da kalıcı olarak silinir")
    return (
        {
            "date": target.isoformat(),
            "event_ids": sorted({e["event_id"] for e in events if e.get("event_id")}),
            "card_ids": card_ids,
        },
        f"↩️ {target.isoformat()} planı iptal edilir\n" + "\n".join(lines),
    )


async def execute_delete(
    api: TaskApiClient, action_type: str, args: dict[str, Any]
) -> dict[str, Any]:
    deleted_cards, deleted_events, failed = [], [], []
    if action_type == "cancel_day":
        try:
            await api.write("PUT", f"/day-plans/{args['date']}", {"items": []})
        except TaskApiError as e:
            failed.append({"plan": args["date"], "error": e.message})
        for eid in args.get("event_ids", []):
            try:
                await api.write("DELETE", f"/events/{eid}")
                deleted_events.append(eid)
            except TaskApiError as e:
                failed.append({"event_id": eid, "error": e.message})
    for cid in args.get("card_ids", []):
        try:
            await api.write("DELETE", f"/cards/{cid}")
            deleted_cards.append(cid)
        except TaskApiError as e:
            if e.status != 404:  # zaten silinmis
                failed.append({"card_id": cid, "error": e.message})
    return {
        "deleted_cards": deleted_cards,
        "deleted_events": deleted_events,
        "failed": failed,
    }
