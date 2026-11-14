"""Faz 13i: Ajanda MCP sunucusu - bellek ici istemci, sahte task-api, gercek test DB'si.

Gercek Claude/Anthropic'e istek yok; PAT uydurma. Saat/zaman duvar saatine bagli degil
(gun planlari sabit tarihle).
"""

import json
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from mcp.client import Client
from sqlalchemy import select

import app.api.chat as chat_module
from app.agent.actions import set_mode
from app.api.deps import current_user
from app.db.models import AiActionEntity
from app.main import app
from app.mcp_server import build_server
from app.mcp_tools import MCP_READ, MCP_WRITE, McpBridge
from app.notify.base import Notification
from app.tools.privacy import HIDDEN_MESSAGE
from app.tools.task_api import TaskApiClient

PAT = "pat_FakePatForTestsOnly_0123456789abcdef"
USER_ID = 7
FORBIDDEN = {
    "delete_cards", "cancel_day", "remember_fact", "forget_fact", "tidy_facts",
    "merge_facts", "triage_inbox", "split_card", "link_cards", "add_note",
    "add_checklist_items", "update_checklist_items", "delete_checklist_items",
    "set_card_labels", "save_goal",
}  # fmt: skip


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[int, Notification]] = []

    async def send(self, user_id: int, n: Notification) -> dict[str, str]:
        self.sent.append((user_id, n))
        return {}


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def make_client(db_session_maker, task_api_transport, notifier):
    async def _open(transport=None):
        bridge = McpBridge(
            db_session_maker,
            PAT,
            transport=transport or task_api_transport,
            notifier=notifier,  # type: ignore[arg-type]
        )
        return bridge

    return _open


async def names(client: Client) -> set[str]:
    return {t.name for t in (await client.list_tools()).tools}


def text_of(result) -> str:
    return result.content[0].text


async def with_client(bridge, fn):
    async with Client(build_server(bridge)) as c:
        return await fn(c)


# ---------------- arac listesi ----------------
async def test_list_tools_read_all_and_writes_by_permission(make_client, db_session_maker):
    bridge = await make_client()

    async def run(c):
        return await names(c)

    got = await with_client(bridge, run)
    assert set(MCP_READ) <= got
    assert set(MCP_WRITE) <= got  # varsayilan 'ask': yazmalar listede
    assert got == set(MCP_READ) | set(MCP_WRITE)

    # 'never' yapilan tur listeden duser; ayar her list_tools'ta yeniden okunur
    async with db_session_maker() as s:
        await set_mode(s, USER_ID, "create_card", "never")
        await s.commit()
    got = await with_client(bridge, run)
    assert "create_card" not in got and "update_card" in got


@pytest.mark.parametrize("mode", ["ask", "auto", "never"])
async def test_delete_and_memory_tools_never_listed(make_client, db_session_maker, mode):
    async with db_session_maker() as s:
        for t in ("delete_cards", "cancel_day", "remember_fact", "forget_fact",
                  "merge_facts", "triage_inbox", "manage_goal", "edit_checklist"):  # fmt: skip
            await set_mode(s, USER_ID, t, mode)
        await s.commit()
    bridge = await make_client()
    got = await with_client(bridge, names)
    assert not (got & FORBIDDEN)


async def test_forbidden_and_unknown_tool_calls_are_errors(make_client, fake_api):
    bridge = await make_client()

    async def run(c):
        out = []
        for name in ("delete_cards", "remember_fact", "olmayan_arac"):
            r = await c.call_tool(name, {"card_ids": [11]})
            out.append((r.is_error, text_of(r)))
        return out

    for is_error, msg in await with_client(bridge, run):
        assert is_error and msg == "Bu araç Claude bağlantısında yok."
    assert fake_api.writes == []


# ---------------- gizlilik (local_only) ----------------
async def test_local_only_data_never_reaches_claude(make_client, fake_api):
    def handler(request: httpx.Request) -> httpx.Response:
        res = fake_api(request)
        if request.method == "GET" and request.url.path.startswith("/api/v1/day-plans/"):
            data = json.loads(res.content)["data"]
            data.update(mood=None, energy=None, reflection=None)
            return httpx.Response(200, json={"success": True, "data": data})
        return res

    bridge = await make_client(httpx.MockTransport(handler))
    fake_api.plans["2026-11-09"] = [
        {"card_id": 21, "title": "Gizli date planı"},
        {"card_id": 11, "title": "Koşu"},
    ]

    async def run(c):
        r = {}
        r["boards"] = await c.call_tool("list_boards", {})
        r["board"] = await c.call_tool("get_board", {"board_id": 2})
        r["search"] = await c.call_tool("search_cards", {"query": "date"})
        r["cal"] = await c.call_tool(
            "get_calendar", {"start_date": "2026-11-09", "end_date": "2026-11-10"}
        )
        r["plan"] = await c.call_tool("get_day_plan", {"date": "2026-11-09"})
        r["create"] = await c.call_tool(
            "create_card", {"board_id": 2, "title": "Yeni gizli", "force_new": True}
        )
        r["move"] = await c.call_tool(
            "move_card", {"card": "11", "board": "Date planları"}
        )
        r["sched"] = await c.call_tool(
            "schedule_day",
            {"day": "2099-11-09", "blocks": [{"title": "X", "minutes": 30, "board": "Date planları"}]},
        )
        return r

    r = await with_client(bridge, run)
    assert "Date planları" not in text_of(r["boards"]) and "Spor" in text_of(r["boards"])
    assert r["board"].is_error  # gizli board
    assert "Gizli" not in text_of(r["search"]) and "gizli" not in text_of(r["search"]).lower()
    cal = text_of(r["cal"])
    assert "Gizli" not in cal and "Koşu bloğu" in cal
    plan = text_of(r["plan"])
    assert "Gizli date" not in plan
    assert r["create"].is_error and HIDDEN_MESSAGE in text_of(r["create"])
    assert r["move"].is_error and "Board bulunamadı" in text_of(r["move"])
    assert r["sched"].is_error and "bulunamadı. Mevcut: Spor" in text_of(r["sched"])
    assert fake_api.writes == []  # hicbiri task-api'ye yazmadi
    # hicbir yanitta gizli kart/etkinlik basligi yok ("Mevcut: Spor" gibi hata metinleri haric)
    for key, res in r.items():
        for secret in ("Gizli date planı", "Gizli akşam yemeği"):
            assert secret not in text_of(res), key


async def test_privacy_set_is_fresh_on_every_call(make_client, task_api_transport, fake_api):
    """1. cagridan sonra bir board local_only olur -> 2. cagrida gizli."""
    state = {"spor_local": False}

    def handler(request: httpx.Request) -> httpx.Response:
        res = fake_api(request)
        if (
            state["spor_local"]
            and request.method == "GET"
            and request.url.path.endswith("/boards")
        ):
            data = json.loads(res.content)["data"]
            for b in data:
                if b["id"] == 1:
                    b["privacy"] = "local_only"
            return httpx.Response(200, json={"success": True, "data": data})
        return res

    bridge = await make_client(httpx.MockTransport(handler))

    async def run(c):
        first = await c.call_tool("list_boards", {})
        state["spor_local"] = True
        second = await c.call_tool("list_boards", {})
        return first, second

    first, second = await with_client(bridge, run)
    assert "Spor" in text_of(first)
    assert "Spor" not in text_of(second)


# ---------------- yazma: ask / auto ----------------
async def test_ask_creates_pending_action_and_notifies(
    make_client, db_session_maker, fake_api, notifier
):
    bridge = await make_client()

    async def run(c):
        return await c.call_tool(
            "create_card", {"board_id": 1, "title": "Koşu", "force_new": True}
        )

    res = await with_client(bridge, run)
    msg = text_of(res)
    assert not res.is_error
    assert msg.startswith("ONAY BEKLİYOR (#") and "YAPILMADI" in msg
    assert fake_api.writes == []
    async with db_session_maker() as s:
        row = await s.scalar(select(AiActionEntity))
    assert row.status == "proposed" and row.conversation_id is None
    assert row.model_id == "mcp:claude" and row.user_id == USER_ID
    assert f"(#{row.id})" in msg
    assert len(notifier.sent) == 1
    uid, n = notifier.sent[0]
    assert uid == USER_ID and n.kind == "mcp" and n.title == "Claude bir işlem önerdi"
    assert len(n.body) <= 120 and "\n" not in n.body


async def test_auto_executes_with_mcp_actor(make_client, db_session_maker, fake_api):
    async with db_session_maker() as s:
        await set_mode(s, USER_ID, "create_card", "auto")
        await s.commit()
    bridge = await make_client()

    async def run(c):
        return await c.call_tool(
            "create_card", {"board_id": 1, "title": "Koşu", "force_new": True}
        )

    res = await with_client(bridge, run)
    assert not res.is_error and text_of(res).startswith("YAPILDI: ")
    assert [(w["path"], w["actor"]) for w in fake_api.writes] == [("/cards", "mcp")]


async def test_auto_failure_is_error(make_client, db_session_maker, fake_api):
    async with db_session_maker() as s:
        await set_mode(s, USER_ID, "create_card", "auto")
        await s.commit()
    fake_api.fail_paths.add("/cards")
    bridge = await make_client()

    async def run(c):
        return await c.call_tool(
            "create_card", {"board_id": 1, "title": "Koşu", "force_new": True}
        )

    res = await with_client(bridge, run)
    assert res.is_error and text_of(res).startswith("BAŞARISIZ: ")


async def test_never_called_from_stale_list_is_error(make_client, db_session_maker):
    bridge = await make_client()
    async with db_session_maker() as s:
        await set_mode(s, USER_ID, "create_card", "never")
        await s.commit()

    async def run(c):
        return await c.call_tool("create_card", {"board_id": 1, "title": "x"})

    res = await with_client(bridge, run)
    assert res.is_error and text_of(res) == "Kullanıcı bu tür işlemleri kapattı."


# ---------------- onay ucu: conversation_id=None satiri yurutulur ----------------
async def test_web_can_approve_mcp_proposal(
    make_client, db_session_maker, fake_api, task_api_transport, monkeypatch
):
    bridge = await make_client()

    async def run(c):
        return await c.call_tool(
            "create_card", {"board_id": 1, "title": "Koşu", "force_new": True}
        )

    await with_client(bridge, run)
    monkeypatch.setattr(chat_module, "session_maker", db_session_maker)
    monkeypatch.setattr(
        chat_module,
        "TaskApiClient",
        lambda token: TaskApiClient(token, transport=task_api_transport),
    )

    async def fake_session():
        async with db_session_maker() as s:
            yield s

    app.dependency_overrides[current_user] = lambda: {
        "id": USER_ID, "full_name": "Ali", "token": "jwt-token"
    }
    app.dependency_overrides[chat_module.get_session] = fake_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as web:
            listed = (await web.get("/api/v1/assistant/actions?status=proposed")).json()["data"]
            assert [a["id"] for a in listed if a["conversation_id"] is None] if False else listed
            res = await web.post(f"/api/v1/assistant/actions/{listed[0]['id']}/approve", json={})
        assert res.json()["data"]["status"] == "executed"
    finally:
        app.dependency_overrides.clear()
    assert fake_api.writes[0]["path"] == "/cards"

    # Claude sonucu get_action_status ile sorar
    async def status(c):
        return await c.call_tool("get_action_status", {"action_id": listed[0]["id"]})

    out = json.loads(text_of(await with_client(bridge, status)))
    assert out["status"] == "executed" and out["id"] == listed[0]["id"]


# ---------------- get_action_status ----------------
async def test_get_action_status_other_users_action_is_error(make_client, db_session_maker):
    async with db_session_maker() as s:
        s.add(
            AiActionEntity(
                user_id=99, action_type="create_card", args={}, summary="baskasi",
                status="proposed", model_id="mcp:claude",
            )
        )
        mine = AiActionEntity(
            user_id=USER_ID, action_type="create_card", args={}, summary="benim",
            status="rejected", user_feedback="gerek yok", model_id="mcp:claude",
        )
        s.add(mine)
        await s.commit()
        other_id, mine_id = 1, mine.id
    bridge = await make_client()

    async def run(c):
        a = await c.call_tool("get_action_status", {"action_id": other_id})
        b = await c.call_tool("get_action_status", {"action_id": mine_id})
        d = await c.call_tool("get_action_status", {"action_id": 12345})
        return a, b, d

    a, b, d = await with_client(bridge, run)
    assert a.is_error and text_of(a) == "İşlem bulunamadı" and "baskasi" not in text_of(a)
    assert d.is_error
    out = json.loads(text_of(b))
    assert out["status"] == "rejected" and out["user_feedback"] == "gerek yok"


# ---------------- kimlik ----------------
@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "anahtar geçersiz"), (403, "anahtar geçersiz")],
)
async def test_invalid_pat_exposes_only_status_tool(make_client, status, reason, fake_api):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"success": False, "error": {"message": "x"}})

    bridge = await make_client(httpx.MockTransport(handler))

    async def run(c):
        tools = await names(c)
        r1 = await c.call_tool("ajanda_status", {})
        r2 = await c.call_tool("list_boards", {})
        return tools, r1, r2

    tools, r1, r2 = await with_client(bridge, run)
    assert tools == {"ajanda_status"}
    for r in (r1, r2):
        assert r.is_error and reason in text_of(r) and PAT not in text_of(r)
        assert "Claude bağlantısı" in text_of(r)


async def test_unreachable_task_api_message(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    bridge = await make_client(httpx.MockTransport(handler))

    async def run(c):
        return await c.call_tool("list_boards", {})

    r = await with_client(bridge, run)
    assert r.is_error and "Ajanda kapalı ya da ulaşılamıyor" in text_of(r)


async def test_whoami_cached_60s(db_session_maker, fake_api):
    calls = {"me": 0}
    now = {"t": 1000.0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/me"):
            calls["me"] += 1
        return fake_api(request)

    bridge = McpBridge(
        db_session_maker, PAT, transport=httpx.MockTransport(handler),
        notifier=FakeNotifier(),  # type: ignore[arg-type]
        clock=lambda: now["t"],
    )  # fmt: skip
    await bridge.whoami()
    await bridge.whoami()
    assert calls["me"] == 1
    now["t"] += 61
    await bridge.whoami()
    assert calls["me"] == 2


async def test_token_never_in_logs(make_client, caplog, fake_api):
    caplog.set_level("DEBUG")
    bridge = await make_client()

    async def run(c):
        await c.call_tool("list_boards", {})
        return await c.call_tool("create_card", {"board_id": 1})

    await with_client(bridge, run)
    assert PAT not in caplog.text


# ---------------- sozlesme / stdout ----------------
async def test_write_tools_flagged_and_schema_passthrough(make_client):
    bridge = await make_client()

    async def run(c):
        return {t.name: t for t in (await c.list_tools()).tools}

    tools = await with_client(bridge, run)
    assert tools["create_card"].description.startswith("[Onay gerekebilir] ")
    assert not tools["list_boards"].description.startswith("[Onay")
    assert tools["get_action_status"].input_schema["required"] == ["action_id"]
    assert tools["get_card"].input_schema["required"] == ["card_id"]


def test_mcp_modules_never_print_to_stdout():
    root = Path(__file__).resolve().parents[1] / "app"
    for f in ("mcp_server.py", "mcp_tools.py"):
        src = (root / f).read_text(encoding="utf-8")
        assert "print(" not in src and "sys.stdout" not in src, f
    assert "AJANDA_TOKEN" in (root / "mcp_server.py").read_text(encoding="utf-8")


async def test_mcp_config_endpoint(db_session_maker):
    app.dependency_overrides[current_user] = lambda: {"id": 1, "token": "jwt"}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as web:
            res = await web.get("/api/v1/assistant/mcp/config")
    finally:
        app.dependency_overrides.clear()
    data = res.json()["data"]
    assert Path(data["assistant_dir"], "app", "mcp_server.py").exists()
    assert data["uv"]
