"""Faz 13e — "yaptım" koruması: SSE sırası ve kalıcı mesaj."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.api.chat as chat_module
from app.agent.guard import NOOP_WARNING, PENDING_WARNING
from app.api.deps import current_user
from app.db.models import AiPermissionEntity, MessageEntity
from app.main import app
from app.tools.task_api import TaskApiClient
from tests.conftest import FakeProvider, call, text
from tests.test_chat_api import USER, parse_sse

API = "/api/v1/assistant"


@pytest.fixture
async def client(monkeypatch, db_session_maker, task_api_transport):
    providers: dict[str, FakeProvider] = {}

    async def no_models():
        return []

    monkeypatch.setattr(chat_module, "list_local_models", no_models)
    monkeypatch.setattr(
        chat_module, "build_provider", lambda mid, cloud=None, **_: providers[mid]
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
        c.db = db_session_maker  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


async def say(client, message):
    res = await client.post(
        f"{API}/chat", json={"message": message, "model_id": "fake:local"}
    )
    return parse_sse(res.text)


async def last_assistant(client) -> str:
    async with client.db() as s:
        row = await s.scalar(
            select(MessageEntity)
            .where(MessageEntity.role == "assistant")
            .order_by(MessageEntity.id.desc())
            .limit(1)
        )
        return row.content


def create_card_call():
    return call("create_card", board_id=1, title="Koşu", force_new=True)


async def test_claim_with_pending_action_warns_in_sse_and_message(client):
    client.providers["fake:local"] = FakeProvider(
        [[create_card_call()], [text("Kartı ekledim!")]]
    )
    events = await say(client, "Koşu kartı ekle")
    names = [e for e, _ in events]
    assert names.index("action") < names.index("guard") < names.index("done")
    (guard,) = [d for e, d in events if e == "guard"]
    assert guard["text"] == PENDING_WARNING
    stored = await last_assistant(client)
    assert stored.startswith("Kartı ekledim!") and stored.endswith(PENDING_WARNING)


async def test_claim_without_any_write_warns_noop(client):
    client.providers["fake:local"] = FakeProvider([[text("Takvime koydum.")]])
    events = await say(client, "selam")
    (guard,) = [d for e, d in events if e == "guard"]
    assert guard["text"] == NOOP_WARNING
    assert (await last_assistant(client)).endswith(NOOP_WARNING)


async def test_auto_mode_has_no_guard(client):
    async with client.db() as s:
        s.add(AiPermissionEntity(user_id=7, action_type="create_card", mode="auto"))
        await s.commit()
    client.providers["fake:local"] = FakeProvider(
        [[create_card_call()], [text("Kartı ekledim!")]]
    )
    events = await say(client, "Koşu kartı ekle")
    assert [d for e, d in events if e == "action"][0]["status"] == "executed"
    assert not [1 for e, _ in events if e == "guard"]
    assert await last_assistant(client) == "Kartı ekledim!"


async def test_honest_reply_has_no_guard(client):
    client.providers["fake:local"] = FakeProvider(
        [[create_card_call()], [text("Onay kartını hazırladım; onaylarsan eklenecek.")]]
    )
    events = await say(client, "Koşu kartı ekle")
    assert not [1 for e, _ in events if e == "guard"]
