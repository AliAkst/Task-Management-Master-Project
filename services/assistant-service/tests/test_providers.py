"""Faz 5c: sifreli saglayici ayarlari, local varsayilan, model yonlendirme."""

import httpx
import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.api.chat as chat_module
import app.llm.registry as registry
import app.security as security
from app.api.deps import current_user
from app.config import settings
from app.db.models import ProviderConfigEntity
from app.llm.router import resolve_model
from app.main import app
from app.tools.task_api import TaskApiClient

USER = {"id": 7, "full_name": "Ali", "token": "tkn"}
KEY = "sk-ant-test-0123456789abcd"


@pytest.fixture
async def client(monkeypatch, db_session_maker, task_api_transport):
    async def no_ollama():
        return []

    monkeypatch.setattr(chat_module, "list_local_models", no_ollama)
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
        c.db = db_session_maker  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


# ---------------- sifreleme ----------------
def test_encrypt_roundtrip_and_mask():
    token = security.encrypt(KEY)
    assert KEY not in token
    assert security.decrypt(token) == KEY
    assert security.mask(KEY) == "…abcd"
    assert security.mask("kisa") == "…"


def test_decrypt_with_other_master_key_fails(monkeypatch):
    token = security.encrypt(KEY)
    monkeypatch.setattr(settings, "secret_key", Fernet.generate_key().decode())
    security._fernet.cache_clear()
    with pytest.raises(security.SecretError):
        security.decrypt(token)


# ---------------- saglayici API'si ----------------
async def test_provider_key_is_encrypted_and_never_returned(client):
    res = await client.put(
        "/api/v1/assistant/providers/anthropic",
        json={"api_key": KEY, "models": ["claude-sonnet-5-5", " claude-sonnet-5-5 "]},
    )
    assert res.status_code == 200, res.text
    assert KEY not in res.text
    data = res.json()["data"]
    assert data["key_hint"] == "…abcd"
    assert data["models"] == ["claude-sonnet-5-5"]  # tekrar ve bosluk temizlenir

    async with client.db() as s:
        row = await s.scalar(select(ProviderConfigEntity))
        assert row.api_key_encrypted != KEY and KEY not in row.api_key_encrypted
        assert security.decrypt(row.api_key_encrypted) == KEY

    listing = await client.get("/api/v1/assistant/providers")
    assert KEY not in listing.text
    by_id = {p["provider"]: p for p in listing.json()["data"]}
    assert set(by_id) == {"anthropic", "openai", "gemini"}
    assert by_id["anthropic"]["connected"] and not by_id["gemini"]["connected"]


async def test_update_without_key_keeps_key(client):
    await client.put(
        "/api/v1/assistant/providers/anthropic",
        json={"api_key": KEY, "models": ["claude-sonnet-5-5"]},
    )
    res = await client.put(
        "/api/v1/assistant/providers/anthropic",
        json={"models": ["claude-haiku-5-5"], "is_enabled": False},
    )
    assert res.status_code == 200
    async with client.db() as s:
        row = await s.scalar(select(ProviderConfigEntity))
        assert security.decrypt(row.api_key_encrypted) == KEY
        assert row.models == ["claude-haiku-5-5"] and row.is_enabled is False


async def test_provider_validation_and_delete(client):
    url = "/api/v1/assistant/providers"
    assert (await client.put(f"{url}/gemini", json={"models": []})).status_code == 422
    bad = await client.put(f"{url}/openai", json={"api_key": KEY, "models": ["a b"]})
    assert bad.status_code == 422
    assert (
        await client.put(f"{url}/mistral", json={"api_key": KEY})
    ).status_code == 404
    await client.put(f"{url}/gemini", json={"api_key": KEY, "models": ["g-1"]})
    assert (await client.delete(f"{url}/gemini")).status_code == 204
    async with client.db() as s:
        assert await s.scalar(select(ProviderConfigEntity)) is None


async def test_models_list_cloud_as_paid_and_default_stays_local(client):
    await client.put(
        "/api/v1/assistant/providers/anthropic",
        json={"api_key": KEY, "models": ["claude-sonnet-5-5"]},
    )
    await client.put(
        "/api/v1/assistant/providers/openai",
        json={"api_key": KEY, "models": ["gpt-x"], "is_enabled": False},
    )
    data = (await client.get("/api/v1/assistant/models")).json()["data"]
    assert data["default"] == settings.default_model
    assert data["default"].startswith("ollama:")
    ids = [m["id"] for m in data["models"]]
    assert ids == ["anthropic:claude-sonnet-5-5"]  # devre disi saglayici gorunmez
    m = data["models"][0]
    assert m["is_local"] is False and "ücretli" in m["label"]
    assert m["label"].startswith("Claude Sonnet 5.5")


async def test_default_model_must_be_local(client):
    url = "/api/v1/assistant/preferences"
    res = await client.put(url, json={"default_model_id": "anthropic:claude-opus-5-5"})
    assert res.status_code == 422
    res = await client.put(url, json={"default_model_id": "ollama:gemma4:26b"})
    assert res.status_code == 200
    assert (await client.get(url)).json()["data"]["default_model_id"] == (
        "ollama:gemma4:26b"
    )
    models = (await client.get("/api/v1/assistant/models")).json()["data"]
    assert models["default"] == "ollama:gemma4:26b"


async def test_chat_with_unconnected_cloud_model_is_rejected(client):
    res = await client.post(
        "/api/v1/assistant/chat",
        json={"message": "x", "model_id": "anthropic:claude-opus-5-5"},
    )
    assert res.status_code == 422
    assert "bağlı değil" in res.json()["error"]["message"]


async def test_chat_builds_claude_with_decrypted_key(client, monkeypatch):
    await client.put(
        "/api/v1/assistant/providers/anthropic",
        json={"api_key": KEY, "models": ["claude-sonnet-5-5"]},
    )
    seen = {}

    def spy(model_id, cloud=None):
        seen["model_id"], seen["cloud"] = model_id, cloud
        raise chat_module.LLMError("durdur")

    monkeypatch.setattr(chat_module, "build_provider", spy)
    res = await client.post(
        "/api/v1/assistant/chat",
        json={"message": "x", "model_id": "anthropic:claude-sonnet-5-5"},
    )
    assert res.status_code == 422
    assert seen["model_id"] == "anthropic:claude-sonnet-5-5"
    assert seen["cloud"].api_key == KEY and seen["cloud"].provider == "anthropic"


def test_build_provider_checks_enabled_models():
    cloud = registry.CloudConfig("anthropic", KEY, ["claude-sonnet-5-5"])
    p = registry.build_provider("anthropic:claude-sonnet-5-5", cloud)
    assert type(p).__name__ == "AnthropicProvider" and p.info.is_local is False
    with pytest.raises(registry.LLMError):
        registry.build_provider("anthropic:claude-opus-5-5", cloud)
    gem = registry.build_provider(
        "gemini:g-1", registry.CloudConfig("gemini", KEY, ["g-1"])
    )
    assert str(gem.client.base_url).startswith(settings.gemini_base_url)


# ---------------- model yonlendirme ----------------
def _board_api(board: dict) -> TaskApiClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "data": {"board": board}})

    return TaskApiClient("t", transport=httpx.MockTransport(handler))


async def test_route_order_message_board_user():
    api = _board_api(
        {
            "id": 1,
            "privacy": "cloud_allowed",
            "default_model_id": "anthropic:claude-haiku-5-5",
        }
    )
    r = await resolve_model(
        api, requested="ollama:a", board_id=1, user_default="ollama:u"
    )
    assert (r.model_id, r.source) == ("ollama:a", "message")
    r = await resolve_model(api, requested=None, board_id=1, user_default="ollama:u")
    assert (r.model_id, r.source) == ("anthropic:claude-haiku-5-5", "board")
    r = await resolve_model(api, requested=None, board_id=None, user_default="ollama:u")
    assert (r.model_id, r.source) == ("ollama:u", "user")


async def test_local_only_board_never_defaults_to_cloud():
    api = _board_api(
        {"id": 2, "privacy": "local_only", "default_model_id": "openai:gpt-x"}
    )
    r = await resolve_model(api, requested=None, board_id=2, user_default="ollama:u")
    assert (r.model_id, r.source) == ("ollama:u", "user")
    api = _board_api(
        {"id": 2, "privacy": "local_only", "default_model_id": "ollama:gemma4:26b"}
    )
    r = await resolve_model(api, requested=None, board_id=2, user_default="ollama:u")
    assert r.model_id == "ollama:gemma4:26b"
