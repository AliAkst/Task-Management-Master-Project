"""Gun planlama adimi: istek tanima, tek arac, hata geri bildirimiyle yeniden deneme."""

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.chat as chat_module
from app.agent.day_planner import is_schedule_request
from app.api.deps import current_user
from app.main import app
from app.tools.task_api import TaskApiClient
from tests.conftest import FakeProvider, call, text
from tests.test_chat_api import USER, parse_sse

API = "/api/v1/assistant"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Bana salı günü için ... kalan zamanı da kalan işler için planla.", True),
        ("Yarın için günümü saat saat planla", True),
        ("Çarşamba gününü programla: 9-18 iş", True),
        ("Bugün neler planlı?", False),
        ("Yarın planımı göster", False),
        ("Spor kartı aç", False),
    ],
)
def test_is_schedule_request(message, expected):
    assert is_schedule_request(message) is expected


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
        yield c
    app.dependency_overrides.clear()


async def chat(client, message):
    res = await client.post(
        f"{API}/chat", json={"message": message, "model_id": "fake:local"}
    )
    return parse_sse(res.text)


PLAN = "Yarın için günümü planla: 9-18 iş, sonra 45 dk koşu"


async def test_planner_proposes_whole_day_in_one_card(client, fake_api):
    provider = FakeProvider(
        [
            [
                call(
                    "schedule_day",
                    day="yarın",
                    blocks=[
                        {
                            "title": "İş",
                            "start": "09:00",
                            "end": "18:00",
                            "card": False,
                        },
                        {"title": "Koşu", "minutes": 45, "board": "Spor"},
                    ],
                )
            ]
        ]
    )
    client.providers["fake:local"] = provider
    events = await chat(client, PLAN)
    actions = [d for e, d in events if e == "action"]
    assert len(actions) == 1 and actions[0]["action_type"] == "schedule_day"
    assert "18:00–18:45 Koşu (kart, Spor)" in actions[0]["summary"]
    assert actions[0]["status"] == "proposed" and fake_api.writes == []
    reply = "".join(d["text"] for e, d in events if e == "token")
    assert "Onay kartından" in reply
    assert events[-1][0] == "done"
    # Odakli cagri: modele sadece schedule_day araci gosterildi, tek cagri
    assert [t.name for t in provider.tools_seen[0]] == ["schedule_day"]
    assert len(provider.received) == 1


async def test_planner_retries_with_error_feedback(client):
    provider = FakeProvider(
        [
            [
                call(
                    "schedule_day",
                    day="yarın",
                    blocks=[{"title": "İş", "start": "09:00"}],
                )
            ],
            [
                call(
                    "schedule_day",
                    day="yarın",
                    blocks=[{"title": "İş", "start": "09:00", "minutes": 60}],
                )
            ],
        ]
    )
    client.providers["fake:local"] = provider
    events = await chat(client, PLAN)
    assert [d["action_type"] for e, d in events if e == "action"] == ["schedule_day"]
    # Ikinci denemede model ilk hatayi gordu
    assert "süre (minutes)" in provider.all_text_sent()


async def test_planner_failure_falls_back_to_chat(client):
    provider = FakeProvider([[text("Plan yapamadım")], [text("Normal cevap")]])
    client.providers["fake:local"] = provider
    events = await chat(client, PLAN)
    reply = "".join(d["text"] for e, d in events if e == "token")
    assert reply == "Normal cevap"
    assert not [d for e, d in events if e == "action"]
