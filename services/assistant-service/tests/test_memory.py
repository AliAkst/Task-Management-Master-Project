"""Faz 5b: kullanici hafizasi (bilgiler), hedefler, tanisma, profil API'si."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.api.chat as chat_module
from app.api.deps import current_user
from app.db.models import UserFactEntity
from app.main import app
from app.tools.task_api import TaskApiClient
from tests.conftest import FakeProvider, call, text
from tests.test_chat_api import USER, parse_sse

API = "/api/v1/assistant"


@pytest.fixture
async def client(monkeypatch, db_session_maker, task_api_transport):
    providers: dict[str, FakeProvider] = {}
    monkeypatch.setattr(chat_module, "build_provider", lambda mid: providers[mid])
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


async def chat(client, message, model="fake:local", conversation_id=None):
    res = await client.post(
        f"{API}/chat",
        json={
            "message": message,
            "model_id": model,
            "conversation_id": conversation_id,
        },
    )
    return parse_sse(res.text)


def system_prompt(provider: FakeProvider, turn: int = -1) -> str:
    return provider.received[turn][0].content


async def test_new_user_gets_acquaintance_instruction(client):
    client.providers["fake:local"] = FakeProvider([[text("Merhaba! Seni tanıyalım.")]])
    await chat(client, "Selam")
    prompt = system_prompt(client.providers["fake:local"])
    assert "henüz yeterince tanımıyorsun" in prompt and "TEK soru" in prompt


async def test_remember_fact_approval_then_in_context(client):
    client.providers["fake:local"] = FakeProvider(
        [
            [
                call(
                    "remember_fact",
                    category="routine",
                    content="Sabahları 7'de kalkıyor",
                )
            ],
            [text("Bunu hatırlamayı önerdim.")],
            [text("Tamam.")],
        ]
    )
    events = await chat(client, "Ben hep 7'de kalkarım")
    action = next(d for e, d in events if e == "action")
    assert action["status"] == "proposed" and "Rutinler" in action["summary"]

    res = await client.post(f"{API}/actions/{action['id']}/approve", json={})
    assert res.json()["data"]["status"] == "executed"

    facts = (await client.get(f"{API}/facts")).json()["data"]["facts"]
    assert [(f["content"], f["source"]) for f in facts] == [
        ("Sabahları 7'de kalkıyor", "ai_learned")
    ]

    await chat(client, "Yarın ne yapayım?")
    assert f"[{facts[0]['id']}, routine] Sabahları 7'de kalkıyor" in system_prompt(
        client.providers["fake:local"]
    )


async def test_private_facts_never_reach_cloud(client):
    await client.post(
        f"{API}/facts", json={"category": "health", "content": "Dizinde sakatlık var"}
    )
    await client.post(
        f"{API}/facts", json={"category": "work", "content": "Backend geliştirici"}
    )
    facts = (await client.get(f"{API}/facts")).json()["data"]["facts"]
    private = next(f for f in facts if f["category"] == "health")
    assert private["is_private"] is True  # saglik varsayilan olarak gizli

    cloud = FakeProvider(
        [[call("forget_fact", fact_id=private["id"])], [text("ok")]], is_local=False
    )
    client.providers["fake:cloud"] = cloud
    events = await chat(client, "Beni tanıyor musun?", model="fake:cloud")
    sent = cloud.all_text_sent()
    assert "Backend geliştirici" in sent
    assert "sakatlık" not in sent
    # Bulut model gizli bilgiyi silmeye calisirsa reddedilir (oneri bile olusmaz)
    assert not any(e == "action" for e, _ in events)


async def test_save_goal_goes_to_task_api_as_ai(client, fake_api):
    client.providers["fake:local"] = FakeProvider(
        [
            [
                call(
                    "save_goal",
                    title="Docker sertifikası",
                    why="Kariyer",
                    target_date="2027-03-01",
                    board_id=1,
                )
            ],
            [text("Hedefi önerdim.")],
            [text("ok")],
        ]
    )
    events = await chat(client, "Mart'a kadar Docker sertifikası almak istiyorum")
    action = next(d for e, d in events if e == "action")
    assert action["action_type"] == "manage_goal"
    assert action["summary"].startswith(
        "🎯 Yeni hedef: 'Docker sertifikası' (hedef tarih Pzt 1 Mar, Spor)"
    )
    await client.post(f"{API}/actions/{action['id']}/approve", json={})
    write = fake_api.writes[-1]
    assert (write["method"], write["path"], write["actor"]) == ("POST", "/goals", "ai")

    # Aktif hedef bir sonraki turda sistem mesajinda
    await chat(client, "Bu hafta ne yapayım?")
    assert "[hedef 1] Docker sertifikası" in system_prompt(
        client.providers["fake:local"]
    )


async def test_never_manage_goal_hides_save_goal(client):
    await client.put(f"{API}/permissions/manage_goal", json={"mode": "never"})
    provider = FakeProvider([[text("ok")]])
    client.providers["fake:local"] = provider
    await chat(client, "x")
    # FakeProvider arac listesini kaydeder
    tools = {t.name for t in provider.tools_seen[0]}
    assert "save_goal" not in tools and "remember_fact" in tools


async def test_facts_api_crud_and_ownership(client):
    res = await client.post(f"{API}/facts", json={"category": "yok", "content": "x"})
    assert res.status_code == 422
    f = (
        await client.post(
            f"{API}/facts", json={"category": "preference", "content": "Kahve sever"}
        )
    ).json()["data"]
    assert f["is_private"] is False and f["source"] == "user_entered"

    res = await client.patch(
        f"{API}/facts/{f['id']}", json={"content": "Çay sever", "is_private": True}
    )
    assert (
        res.json()["data"]["content"] == "Çay sever"
        and res.json()["data"]["is_private"] is True
    )

    app.dependency_overrides[current_user] = lambda: {**USER, "id": 99}
    assert (await client.get(f"{API}/facts")).json()["data"]["facts"] == []
    assert (
        await client.patch(f"{API}/facts/{f['id']}", json={"content": "y"})
    ).status_code == 404
    assert (await client.delete(f"{API}/facts/{f['id']}")).status_code == 404

    app.dependency_overrides[current_user] = lambda: USER
    assert (await client.delete(f"{API}/facts/{f['id']}")).status_code == 204
    async with client.db() as s:  # type: ignore[attr-defined]
        assert (await s.scalars(select(UserFactEntity))).all() == []


@pytest.fixture
def extraction_on(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "memory_extraction", True)


async def test_extractor_proposes_fact_when_chat_model_does_not(client, extraction_on):
    provider = FakeProvider(
        [
            [text("Harika, peki hafta sonları ne yaparsın?")],  # sohbet: arac yok
            [
                call(
                    "remember_fact",
                    category="routine",
                    content="Akşam 20-22 arası en verimli saatleri",
                )
            ],
        ]
    )
    client.providers["fake:local"] = provider
    events = await chat(client, "En verimli olduğum saatler akşam 20 ile 22 arası")
    action = next(d for e, d in events if e == "action")
    assert action["action_type"] == "remember_fact" and "20-22" in action["summary"]
    # Cikarim istemi odakli: sadece hafiza araclari + bilinen bilgiler listesi
    assert {t.name for t in provider.tools_seen[1]} == {"remember_fact", "save_goal"}
    assert "Bilinen bilgiler" in provider.received[1][0].content
    # Sohbet modeline "not aldım deme" talimati
    assert "DEME" in provider.received[0][0].content


async def test_extractor_skips_short_messages_and_when_chat_used_memory(
    client, extraction_on
):
    provider = FakeProvider([[text("Selam!")]])
    client.providers["fake:local"] = provider
    await chat(client, "Selam")
    assert len(provider.received) == 1  # kisa mesaj: cikarim yok

    provider = FakeProvider(
        [
            [call("remember_fact", category="work", content="Backend geliştirici")],
            [text("ok")],
        ]
    )
    client.providers["fake:local"] = provider
    await chat(client, "Ben backend geliştiricisiyim, uzun zamandır")
    assert len(provider.received) == 2  # sohbet zaten kaydetti: cikarim calismadi


async def test_extracted_proposals_survive_history_reload(client, extraction_on):
    client.providers["fake:local"] = FakeProvider(
        [
            [text("Güzel.")],
            [call("remember_fact", category="work", content="Backend geliştirici")],
        ]
    )
    events = await chat(client, "Ben backend geliştiricisiyim")
    conv = events[0][1]["conversation_id"]
    msgs = (await client.get(f"{API}/conversations/{conv}/messages")).json()["data"]
    answer = next(m for m in msgs if m["role"] == "assistant")
    assert [a["action_type"] for a in answer["actions"]] == ["remember_fact"]
