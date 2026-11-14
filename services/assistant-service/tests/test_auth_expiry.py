"""Faz 13b: token suresi dolarsa AUTH_EXPIRED, tek tekrar (resend), onbellek, X-Actor."""

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.api.chat as chat_module
import app.api.deps as deps_module
from app.api.deps import current_user
from app.db.models import MessageEntity
from app.main import app
from app.tools.task_api import TaskApiAuthError, TaskApiClient, TaskApiError
from tests.conftest import FakeProvider, call, text
from tests.test_chat_api import USER, parse_sse

API = "/api/v1/assistant"


def expired(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        401,
        json={
            "success": False,
            "data": None,
            "error": {"code": "AUTHENTICATION_FAILED", "message": "Invalid or expired Token"},
        },
    )


@pytest.fixture
def mode():
    """'ok' | 'boards_401' | 'all_401': sahte task-api'nin o anki davranisi."""
    return {"v": "ok"}


@pytest.fixture
async def client(monkeypatch, db_session_maker, fake_api, mode):
    providers: dict[str, FakeProvider] = {}

    def transport(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        if mode["v"] == "all_401":
            return expired(request)
        if mode["v"] == "boards_401" and path.startswith("/boards/"):
            return expired(request)
        return fake_api(request)

    monkeypatch.setattr(chat_module, "build_provider", lambda mid, cloud=None: providers[mid])
    monkeypatch.setattr(chat_module, "session_maker", db_session_maker)
    monkeypatch.setattr(
        chat_module,
        "TaskApiClient",
        lambda token: TaskApiClient(token, transport=httpx.MockTransport(transport)),
    )

    async def fake_session():
        async with db_session_maker() as s:
            yield s

    app.dependency_overrides[current_user] = lambda: USER
    app.dependency_overrides[chat_module.get_session] = fake_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.providers = providers  # type: ignore[attr-defined]
        c.maker = db_session_maker  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


async def chat(client, message, conversation_id=None, resend=False):
    res = await client.post(
        f"{API}/chat",
        json={
            "message": message,
            "model_id": "fake:local",
            "conversation_id": conversation_id,
            "resend": resend,
        },
    )
    assert res.status_code == 200, res.text
    return parse_sse(res.text)


async def rows(client, role):
    async with client.maker() as s:
        return list(
            await s.scalars(select(MessageEntity).where(MessageEntity.role == role))
        )


async def test_401_in_tool_emits_auth_expired_without_tool_result(client, mode):
    mode["v"] = "boards_401"
    client.providers["fake:local"] = FakeProvider([[call("get_board", board_id=1)], [text("x")]])
    events = await chat(client, "Board'larım?")
    err = [d for e, d in events if e == "error"]
    assert len(err) == 1 and err[0]["code"] == "AUTH_EXPIRED"
    assert err[0]["conversation_id"] is not None
    assert "done" not in [e for e, _ in events]
    # Arac sonucu ne modele ne kayda gitti
    assert await rows(client, "tool") == []
    assert len(client.providers["fake:local"].received) == 1


async def test_401_before_stream_start_emits_auth_expired(client, mode):
    mode["v"] = "all_401"
    client.providers["fake:local"] = FakeProvider([[text("x")]])
    events = await chat(client, "Merhaba")
    assert [(e, d["code"]) for e, d in events] == [("error", "AUTH_EXPIRED")]


async def test_resend_does_not_duplicate_user_message(client, mode):
    mode["v"] = "boards_401"
    client.providers["fake:local"] = FakeProvider(
        [[call("get_board", board_id=1)], [call("get_board", board_id=1)], [text("Tamam.")]]
    )
    first = await chat(client, "Board'larım?")
    conv_id = next(d for e, d in first if e == "error")["conversation_id"]
    assert len(await rows(client, "user")) == 1

    mode["v"] = "ok"
    second = await chat(client, "Board'larım?", conversation_id=conv_id, resend=True)
    assert second[-1][0] == "done"
    users = await rows(client, "user")
    assert len(users) == 1 and users[0].content == "Board'larım?"

    # resend=False ayni metinde yeni satir ekler (normal davranis)
    client.providers["fake:local"] = FakeProvider([[text("Evet.")]])
    await chat(client, "Board'larım?", conversation_id=conv_id)
    assert len(await rows(client, "user")) == 2

    # Tamamlanmis tur varsa resend=True bile yeni satir ekler (yalniz yarim tur yeniden kullanilir)
    client.providers["fake:local"] = FakeProvider([[text("Yine.")]])
    await chat(client, "Board'larım?", conversation_id=conv_id, resend=True)
    assert len(await rows(client, "user")) == 3


async def test_approve_401_returns_http_401(client, mode, monkeypatch):
    client.providers["fake:local"] = FakeProvider(
        [
            [call("create_card", board_id=1, title="Koşu", force_new=True)],
            [text("Önerdim.")],
        ]
    )
    events = await chat(client, "Spor'a koşu kartı ekle")
    action = next(d for e, d in events if e == "action")
    mode["v"] = "all_401"
    res = await client.post(f"{API}/actions/{action['id']}/approve", json={})
    assert res.status_code == 401


async def test_job_start_failure_marks_auth_expired(client, mode):
    from app.api import jobs

    mode["v"] = "all_401"
    job_id = await jobs._weekly_due(USER["id"], __import__("datetime").date.today(), "fake:local")
    ok = await jobs._execute(
        job_id, jobs.INBOX, USER, "fake:local", __import__("datetime").date.today()
    )
    assert ok is False
    async with client.maker() as s:
        from app.db.models import AiJobEntity

        job = await s.get(AiJobEntity, job_id)
    assert job.status == "failed" and job.error == "AUTH_EXPIRED"


async def test_auth_error_is_not_a_task_api_error():
    # Mevcut 'except TaskApiError' yakalayicilari 401'i yutmasin
    assert not issubclass(TaskApiAuthError, TaskApiError)


async def test_actor_parameter_sets_header():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("x-actor"))
        return httpx.Response(200, json={"success": True, "data": {}})

    for actor, expected in [(None, "ai"), ("mcp", "mcp")]:
        kwargs = {} if actor is None else {"actor": actor}
        api = TaskApiClient("t", transport=httpx.MockTransport(handler), **kwargs)
        await api.write("POST", "/cards", {"a": 1})
        await api.close()
        assert seen[-1] == expected


def _jwt(exp: float) -> str:
    import base64
    import json

    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{b64({'alg': 'HS256'})}.{b64({'sub': '7', 'exp': exp})}.sig"


async def test_deps_cache_respects_token_exp(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(deps_module.time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(deps_module.time, "time", lambda: 5000.0)
    deps_module._CACHE.clear()
    calls = {"n": 0}

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k):
            calls["n"] += 1
            return httpx.Response(
                200,
                json={"success": True, "data": {"id": 7}},
                request=httpx.Request("GET", "http://x"),
            )

    monkeypatch.setattr(deps_module.httpx, "AsyncClient", FakeClient)
    token = _jwt(5010)  # 10 sn kaldi
    await current_user(authorization=f"Bearer {token}")
    now["t"] = 1005.0
    await current_user(authorization=f"Bearer {token}")
    assert calls["n"] == 1  # 5 sn: hala onbellekte
    now["t"] = 1011.0
    await current_user(authorization=f"Bearer {token}")
    assert calls["n"] == 2  # 10 sn'den uzun tutulmadi

    # Suresi gecmis token onbellege hic girmez
    deps_module._CACHE.clear()
    old = _jwt(4990)
    await current_user(authorization=f"Bearer {old}")
    await current_user(authorization=f"Bearer {old}")
    assert calls["n"] == 4
