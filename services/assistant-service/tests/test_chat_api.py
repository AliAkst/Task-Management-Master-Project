"""Uctan uca sohbet API: SSE, kalicilik, local->cloud gecmis suzme, sahiplik."""

import json

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.chat as chat_module
from app.api.deps import current_user
from app.main import app
from app.tools.task_api import TaskApiClient
from tests.conftest import FakeProvider, call, text

USER = {"id": 7, "full_name": "Ali", "token": "tkn"}


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


@pytest.fixture
async def client(monkeypatch, db_session_maker, task_api_transport):
    providers: dict[str, FakeProvider] = {}

    def fake_build(model_id: str, cloud=None):
        if model_id not in providers:
            raise chat_module.LLMError(f"yok: {model_id}")
        return providers[model_id]

    monkeypatch.setattr(chat_module, "build_provider", fake_build)
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


async def send(client, message, model_id, conversation_id=None):
    res = await client.post(
        "/api/v1/assistant/chat",
        json={
            "message": message,
            "model_id": model_id,
            "conversation_id": conversation_id,
        },
    )
    assert res.status_code == 200, res.text
    return parse_sse(res.text)


async def test_chat_streams_and_persists(client):
    client.providers["fake:local"] = FakeProvider(
        [[call("list_boards")], [text("Merhaba "), text("Ali!")]]
    )
    events = await send(client, "Board'larım?", "fake:local")
    names = [e for e, _ in events]
    assert names[0] == "start" and names[-1] == "done"
    assert "tool_start" in names and "tool_end" in names
    assert "".join(d["text"] for e, d in events if e == "token") == "Merhaba Ali!"
    conv_id = events[0][1]["conversation_id"]

    # Sistem mesaji kullanici adini ve board'lari icerir
    system = client.providers["fake:local"].received[0][0].content
    assert "Ali" in system and "Spor" in system

    res = await client.get(f"/api/v1/assistant/conversations/{conv_id}/messages")
    msgs = res.json()["data"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "assistant"]
    assert msgs[1]["tools"] == ["list_boards"]
    assert msgs[-1]["content"] == "Merhaba Ali!"

    convs = (await client.get("/api/v1/assistant/conversations")).json()["data"]
    assert convs[0]["title"] == "Board'larım?"


async def test_history_is_replayed_to_model(client):
    client.providers["fake:local"] = FakeProvider(
        [[text("İlk cevap")], [text("İkinci cevap")]]
    )
    first = await send(client, "Birinci soru", "fake:local")
    conv_id = first[0][1]["conversation_id"]
    await send(client, "İkinci soru", "fake:local", conv_id)
    sent = [(m.role, m.content) for m in client.providers["fake:local"].received[1]]
    assert ("user", "Birinci soru") in sent and ("assistant", "İlk cevap") in sent


async def test_switching_to_cloud_drops_local_history(client):
    local = FakeProvider(
        [[call("get_board", board_id=2)], [text("Date planın: gizli yemek")]]
    )
    cloud = FakeProvider([[text("Bulut cevabı")]], is_local=False)
    client.providers.update({"fake:local": local, "fake:cloud": cloud})

    first = await send(client, "Date planım ne?", "fake:local")
    conv_id = first[0][1]["conversation_id"]
    events = await send(client, "Peki şimdi?", "fake:cloud", conv_id)

    assert events[0][1]["dropped_local_messages"] >= 3
    sent = cloud.all_text_sent()
    for secret in (
        "Date planım ne?",
        "gizli yemek",
        "Gizli date planı",
        "Date planları",
    ):
        assert secret not in sent, secret
    assert "Peki şimdi?" in sent


async def test_unknown_model_and_foreign_conversation(client):
    res = await client.post(
        "/api/v1/assistant/chat", json={"message": "x", "model_id": "yok:model"}
    )
    assert res.status_code == 422
    assert res.json()["error"]["message"].startswith("yok")

    client.providers["fake:local"] = FakeProvider([[text("ok")]])
    conv_id = (await send(client, "benim", "fake:local"))[0][1]["conversation_id"]

    app.dependency_overrides[current_user] = lambda: {**USER, "id": 99}
    for res in [
        await client.get(f"/api/v1/assistant/conversations/{conv_id}/messages"),
        await client.delete(f"/api/v1/assistant/conversations/{conv_id}"),
        await client.post(
            "/api/v1/assistant/chat",
            json={"message": "x", "model_id": "fake:local", "conversation_id": conv_id},
        ),
    ]:
        assert res.status_code == 404
    assert (await client.get("/api/v1/assistant/conversations")).json()["data"] == []


async def test_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        res = await c.get("/api/v1/assistant/conversations")
    assert res.status_code == 401
