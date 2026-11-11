"""Faz 5a: yazma araclari, izin kapisi, onay/ret akisi."""

import json
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.chat as chat_module
from app.agent.actions import ActionGate
from app.api.deps import current_user
from app.main import app
from app.tools.privacy import PrivacyFilter
from app.tools.read_tools import ToolBox
from app.tools.task_api import TaskApiClient
from app.tools.write_tools import WriteTools
from tests.conftest import FakeProvider, call, text
from tests.test_chat_api import USER, parse_sse

TZ = ZoneInfo("Europe/Istanbul")
API = "/api/v1/assistant"


# ---------------- hazirlik (dogrulama + ozet) ----------------
class TestPrepare:
    def writer(self, transport, cloud=False):
        privacy = PrivacyFilter(
            active=cloud,
            hidden_boards={2} if cloud else set(),
            hidden_cards={21} if cloud else set(),
        )
        return WriteTools(TaskApiClient("t", transport=transport), privacy, TZ)

    async def test_create_card_resolves_list_and_due_date(self, task_api_transport):
        p = await self.writer(task_api_transport).prepare(
            "create_card",
            {
                "board_id": 1,
                "title": "Koşu",
                "force_new": True,
                "due_date": "2026-11-09",
                "estimated_minutes": 45,
            },
        )
        assert p.args["list_id"] == 10  # ilk "tamamlandi olmayan" liste
        assert p.args["due_date"] == "2026-11-09T23:59:00+03:00"
        assert p.summary.startswith("🗂 Yeni kart: 'Koşu' → Spor / Yapılacak")
        assert "Pzt 9 Kas" in p.summary and "45 dk" in p.summary

    async def test_helpful_errors_for_the_model(self, task_api_transport):
        w = self.writer(task_api_transport)
        cases = [
            (
                "create_card",
                {"board_id": 1, "title": "x", "list_name": "Yok"},
                "Mevcut listeler: Yapılacak, Tamamlandı",
            ),
            (
                "create_event",
                {
                    "title": "x",
                    "start_at": "2026-11-09T18:00",
                    "end_at": "2026-11-09T17:00",
                },
                "sonra olmalı",
            ),
            (
                "create_event",
                {"title": "x", "start_at": "2026-11-09", "end_at": "2026-11-10"},
                "saat de içermeli",
            ),
            ("split_card", {"card_id": 11}, "'parts' ya da 'titles'"),
            ("update_card", {"card_id": 11}, "Değişecek bir alan"),
        ]
        for name, args, expected in cases:
            with pytest.raises(ValueError, match=expected.replace("(", r"\(")):
                await w.prepare(name, args)

    async def test_naive_datetime_gets_user_timezone(self, task_api_transport):
        p = await self.writer(task_api_transport).prepare(
            "create_event",
            {
                "card_id": 11,
                "start_at": "2026-11-09T18:00:00",
                "end_at": "2026-11-09T18:45:00",
            },
        )
        assert p.args["start_at"] == "2026-11-09T18:00:00+03:00"
        assert (
            p.summary == "📅 'Koşu' — Pzt 9 Kas 18:00–18:45 (Spor, karta zaman bloğu)"
        )

    async def test_cloud_model_cannot_write_to_local_only(self, task_api_transport):
        w = self.writer(task_api_transport, cloud=True)
        for name, args in [
            ("create_card", {"board_id": 2, "title": "x"}),
            ("add_note", {"card_id": 21, "content": "x"}),
            ("link_cards", {"card_id": 11, "depends_on_id": 21}),
        ]:
            with pytest.raises(ValueError, match="gizli"):
                await w.prepare(name, args)


# ---------------- izin kapisi ----------------
async def make_box(transport, db_session_maker, modes):
    box = await ToolBox.create(
        TaskApiClient("t", transport=transport), cloud=False, tz=TZ
    )
    box.gate = ActionGate(
        db_session_maker,
        box.writer,
        user_id=7,
        conversation_id=None,
        model_id="m",
        modes={
            "create_card": "ask",
            "add_note": "ask",
            "create_event": "ask",
            "split_card": "ask",
            "link_cards": "ask",
            "plan_day": "ask",
            "update_card": "ask",
            **modes,
        },
    )
    return box


class TestGate:
    async def test_ask_mode_does_not_write(
        self, task_api_transport, fake_api, db_session_maker
    ):
        box = await make_box(task_api_transport, db_session_maker, {})
        r = await box.execute(call("create_card", board_id=1, title="Koşu", force_new=True).tool_call)
        body = json.loads(r.text)
        assert body["status"] == "pending_approval" and "YAPILMADI" in body["note"]
        assert r.action["status"] == "proposed"
        assert fake_api.writes == []

    async def test_auto_mode_writes_as_ai(
        self, task_api_transport, fake_api, db_session_maker
    ):
        box = await make_box(
            task_api_transport, db_session_maker, {"create_card": "auto"}
        )
        r = await box.execute(call("create_card", board_id=1, title="Koşu", force_new=True).tool_call)
        assert json.loads(r.text)["status"] == "done"
        assert r.action["status"] == "executed"
        assert fake_api.writes == [
            {
                "method": "POST",
                "path": "/cards",
                "body": {"list_id": 10, "title": "Koşu"},
                "actor": "ai",
            }
        ]

    async def test_never_mode_hides_tool(self, task_api_transport, db_session_maker):
        box = await make_box(
            task_api_transport, db_session_maker, {"create_card": "never"}
        )
        names = {s.name for s in box.specs()}
        assert "create_card" not in names and "add_note" in names
        r = await box.execute(call("create_card", board_id=1, title="x").tool_call)
        assert r.ok is False

    async def test_invalid_args_return_error_without_proposal(
        self, task_api_transport, fake_api, db_session_maker
    ):
        box = await make_box(task_api_transport, db_session_maker, {})
        r = await box.execute(call("create_card", board_id=1).tool_call)  # title eksik
        assert r.ok is False and r.action is None


# ---------------- uctan uca: sohbet -> onay karti -> onay/ret ----------------
@pytest.fixture
async def client(monkeypatch, db_session_maker, task_api_transport):
    providers: dict[str, FakeProvider] = {}
    monkeypatch.setattr(
        chat_module, "build_provider", lambda mid, cloud=None: providers[mid]
    )
    monkeypatch.setattr(chat_module, "session_maker", db_session_maker)
    monkeypatch.setattr(
        chat_module,
        "TaskApiClient",
        lambda token: TaskApiClient(token, transport=task_api_transport),
    )

    async def fake_session():
        async with db_session_maker() as s:
            yield s

    app.dependency_overrides[current_user] = lambda: USER
    app.dependency_overrides[chat_module.get_session] = fake_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.providers = providers  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


async def chat(client, message, conversation_id=None):
    res = await client.post(
        f"{API}/chat",
        json={
            "message": message,
            "model_id": "fake:local",
            "conversation_id": conversation_id,
        },
    )
    return parse_sse(res.text)


async def test_approval_flow(client, fake_api):
    client.providers["fake:local"] = FakeProvider(
        [
            [call("create_card", board_id=1, title="Koşu", force_new=True)],
            [text("Kartı önerdim, onaylarsan eklenecek.")],
            [call("create_card", board_id=1, title="Yüzme")],
            [text("Eklendi.")],
        ]
    )
    events = await chat(client, "Spor'a koşu kartı ekle")
    action = next(d for e, d in events if e == "action")
    assert action["status"] == "proposed" and "'Koşu'" in action["summary"]
    assert fake_api.writes == []
    conv_id = events[0][1]["conversation_id"]

    # Mesaj gecmisi islem kartini tasir (sayfa yenilense de gorunsun)
    msgs = (await client.get(f"{API}/conversations/{conv_id}/messages")).json()["data"]
    assert msgs[1]["actions"][0]["id"] == action["id"]

    res = await client.post(
        f"{API}/actions/{action['id']}/approve", json={"remember_auto": True}
    )
    assert res.json()["data"]["status"] == "executed"
    assert (
        fake_api.writes[0]["path"] == "/cards" and fake_api.writes[0]["actor"] == "ai"
    )
    # Ayni islem ikinci kez onaylanamaz
    assert (
        await client.post(f"{API}/actions/{action['id']}/approve", json={})
    ).status_code == 409

    # "Bundan sonra otomatik yap" kaydedildi
    perms = {
        p["action_type"]: p["mode"]
        for p in (await client.get(f"{API}/permissions")).json()["data"]
    }
    assert perms["create_card"] == "auto" and perms["create_event"] == "ask"

    # Sonraki turda model gecmiste onaylandigini gorur ve yeni kart otomatik eklenir
    events = await chat(client, "Bir de yüzme", conv_id)
    sent = client.providers["fake:local"].all_text_sent()
    assert "Kullanıcı onayladı" in sent
    assert next(d for e, d in events if e == "action")["status"] == "executed"
    assert len(fake_api.writes) == 2


async def test_reject_flow_records_reason(client, fake_api):
    client.providers["fake:local"] = FakeProvider(
        [
            [
                call(
                    "create_event",
                    card_id=11,
                    start_at="2026-11-09T06:00:00+03:00",
                    end_at="2026-11-09T07:00:00+03:00",
                )
            ],
            [text("Önerdim.")],
            [text("Anladım.")],
        ]
    )
    events = await chat(client, "Sabah koşu planla")
    action = next(d for e, d in events if e == "action")
    res = await client.post(
        f"{API}/actions/{action['id']}/reject", json={"reason": "Sabah çok erken"}
    )
    assert res.json()["data"]["status"] == "rejected"
    assert fake_api.writes == []

    await chat(client, "Tamam", events[0][1]["conversation_id"])
    assert "Sabah çok erken" in client.providers["fake:local"].all_text_sent()


async def test_self_link_rejected_before_proposal(client, fake_api):
    client.providers["fake:local"] = FakeProvider(
        [[call("link_cards", card_id=11, depends_on_id=11)], [text("ok")]]
    )
    # Ayni kart -> hazirlikta reddedilir, oneri olusmaz
    events = await chat(client, "bağla")
    assert not any(e == "action" for e, _ in events)


async def test_plan_day_merges_at_approval_time(client, fake_api):
    fake_api.plans["2026-11-09"] = [{"title": "Elle eklediğim"}]
    client.providers["fake:local"] = FakeProvider(
        [
            [
                call(
                    "plan_day",
                    date="2026-11-09",
                    items=[{"card_id": 11, "planned_minutes": 45}],
                )
            ],
            [text("Önerdim.")],
        ]
    )
    events = await chat(client, "Yarına koşuyu ekle")
    action = next(d for e, d in events if e == "action")
    # Oneriden sonra kullanici plana elle bir sey daha ekliyor
    fake_api.plans["2026-11-09"].append({"title": "Sonradan eklenen"})
    await client.post(f"{API}/actions/{action['id']}/approve", json={})
    titles = [i.get("title") or i.get("card_id") for i in fake_api.plans["2026-11-09"]]
    assert titles == ["Elle eklediğim", "Sonradan eklenen", 11]


async def test_other_user_cannot_decide(client):
    client.providers["fake:local"] = FakeProvider(
        [[call("add_note", card_id=11, content="x")], [text("ok")]]
    )
    events = await chat(client, "not ekle")
    action = next(d for e, d in events if e == "action")
    app.dependency_overrides[current_user] = lambda: {**USER, "id": 99}
    assert (
        await client.post(f"{API}/actions/{action['id']}/approve", json={})
    ).status_code == 404
    assert (
        await client.post(f"{API}/actions/{action['id']}/reject", json={})
    ).status_code == 404
    assert (await client.get(f"{API}/actions")).json()["data"] == []
