"""Faz 13f: bildirim kanallari - Telegram (MockTransport), Windows bildirimi, uclar, gizlilik."""

import json
import logging

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.api.chat as chat_module
import app.api.notify as notify_module
from app.api.deps import current_user
from app.db.models import (
    NotificationChannelEntity,
    ServiceCredentialEntity,
)
from app.main import app
from app.notify import toast
from app.notify.base import Notification, Notifier
from app.notify.telegram import TelegramClient, TelegramError, latest_start_chat
from app.security import decrypt, encrypt
from app.tools.task_api import TaskApiClient

API = "/api/v1/assistant/notify"
USER = {"id": 7, "full_name": "Ali", "token": "jwt-token"}
BOT = "123456789:AAFakeTokenForTestsOnly_abcdefghijk"  # uydurma, gercek degil
PAT = "pat_FakePatForTestsOnly_0123456789abcdef"


class FakeTelegram:
    """Telegram Bot API taklidi: istekleri kaydeder."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.me_ok = True
        self.updates: list[dict] = []
        self.send_ok = True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "getMe":
            if not self.me_ok:
                return httpx.Response(
                    401, json={"ok": False, "description": "Unauthorized"}
                )
            return httpx.Response(
                200, json={"ok": True, "result": {"username": "ajanda_bot"}}
            )
        if method == "getUpdates":
            return httpx.Response(200, json={"ok": True, "result": self.updates})
        if method == "sendMessage":
            if not self.send_ok:
                return httpx.Response(
                    403, json={"ok": False, "description": "Forbidden: bot was blocked"}
                )
            return httpx.Response(200, json={"ok": True, "result": {}})
        return httpx.Response(404, json={"ok": False})

    def sent(self) -> list[dict]:
        return [
            json.loads(r.content)
            for r in self.requests
            if r.url.path.endswith("/sendMessage")
        ]


class FakeAuthApi:
    """task-api /auth/tokens taklidi."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, body))
        if request.method == "POST" and path == "/auth/tokens":
            return httpx.Response(
                201,
                json={
                    "success": True,
                    "data": {"id": 42, "token": PAT, "scopes": ["read"]},
                },
            )
        if request.method == "DELETE" and path == "/auth/tokens/42":
            return httpx.Response(204)
        return httpx.Response(404, json={"success": False, "error": {"message": "yok"}})


@pytest.fixture
def tg(monkeypatch) -> FakeTelegram:
    fake = FakeTelegram()
    monkeypatch.setattr(notify_module, "TRANSPORT", httpx.MockTransport(fake))
    return fake


@pytest.fixture
def auth_api(monkeypatch) -> FakeAuthApi:
    fake = FakeAuthApi()
    monkeypatch.setattr(
        chat_module,
        "TaskApiClient",
        lambda token, **kw: TaskApiClient(token, transport=httpx.MockTransport(fake)),
    )
    return fake


@pytest.fixture
async def client(monkeypatch, db_session_maker, tg, auth_api):
    monkeypatch.setattr(chat_module, "session_maker", db_session_maker)

    async def fake_session():
        async with db_session_maker() as s:
            yield s

    app.dependency_overrides[current_user] = lambda: USER
    app.dependency_overrides[notify_module.get_session] = fake_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.db = db_session_maker  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


async def channel(db, kind: str) -> NotificationChannelEntity:
    async with db() as s:
        return await s.scalar(
            select(NotificationChannelEntity).where(
                NotificationChannelEntity.kind == kind
            )
        )


# ---------------- Telegram istemcisi ----------------
async def test_send_message_body_is_plain_text_and_truncated():
    fake = FakeTelegram()
    client = TelegramClient(BOT, httpx.MockTransport(fake))
    await client.send_message(99, "x" * 5000)
    body = fake.sent()[0]
    assert body["chat_id"] == 99
    assert len(body["text"]) == 4000
    assert body["disable_web_page_preview"] is True
    assert "parse_mode" not in body
    assert fake.requests[0].url.path == f"/bot{BOT}/sendMessage"


async def test_telegram_errors_never_contain_token():
    def boom(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")

    client = TelegramClient(BOT, httpx.MockTransport(boom))
    with pytest.raises(TelegramError) as e:
        await client.get_me()
    assert BOT not in str(e.value)

    fake = FakeTelegram()
    fake.me_ok = False
    with pytest.raises(TelegramError) as e2:
        await TelegramClient(BOT, httpx.MockTransport(fake)).get_me()
    assert BOT not in str(e2.value)


def test_latest_start_requires_matching_code_and_picks_newest():
    def upd(i, text, chat, **extra):
        return {
            "update_id": i,
            "message": {"text": text, "chat": {"id": chat, **extra}},
        }

    updates = [
        upd(1, "/start 111111", 11, first_name="Ali"),
        upd(3, "merhaba", 33),
        upd(2, "/start 111111", 22, username="veli"),
        upd(4, "/start 999999", 44),  # yanlis kod
        upd(5, "/start", 55),  # kodsuz
    ]
    assert latest_start_chat(updates, "111111") == (22, "veli")
    assert latest_start_chat(updates, "222222") is None
    assert latest_start_chat([updates[4]], "111111") is None
    assert latest_start_chat([], "111111") is None
    assert latest_start_chat(updates, "") is None


# ---------------- Windows bildirimi ----------------
async def test_toast_is_noop_outside_windows(monkeypatch):
    called = []

    async def fake_exec(*a, **kw):
        called.append(a)

    monkeypatch.setattr(toast.sys, "platform", "linux")
    monkeypatch.setattr(toast.asyncio, "create_subprocess_exec", fake_exec)
    await toast.send_toast("t", "b")
    assert called == []


async def test_toast_runs_powershell_script_on_windows(monkeypatch):
    captured = []

    class Proc:
        async def wait(self):
            return 0

    async def fake_exec(*a, **kw):
        captured.append(a)
        return Proc()

    monkeypatch.setattr(toast.sys, "platform", "win32")
    monkeypatch.setattr(toast.asyncio, "create_subprocess_exec", fake_exec)
    await toast.send_toast("Başlık", "Gövde")
    args = captured[0]
    assert args[0] == "powershell"
    assert "-NoProfile" in args and "Bypass" in args
    assert str(toast.TOAST_SCRIPT) in args
    assert args[-4:] == ("-Title", "Başlık", "-Body", "Gövde")


# ---------------- uclar ----------------
async def test_put_telegram_invalid_token_is_422(client, tg):
    tg.me_ok = False
    res = await client.put(f"{API}/telegram", json={"bot_token": BOT})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "TELEGRAM_TOKEN_INVALID"
    assert BOT not in res.text
    assert await channel(client.db, "telegram") is None


async def test_telegram_pairing_flow_and_no_token_in_responses(client, tg):
    res = await client.put(f"{API}/telegram", json={"bot_token": BOT})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["bot_username"] == "ajanda_bot"
    assert len(res.json()["data"]["pair_code"]) == 6
    assert BOT not in res.text

    code = (await client.get(API)).json()["data"]["channels"][0]["pair_code"]
    assert len(code) == 6 and code.isdigit()

    # /start yok -> 409
    res = await client.post(f"{API}/telegram/pair")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "TELEGRAM_NO_START"
    assert BOT not in res.text

    tg.updates = [
        {
            "update_id": 5,
            "message": {
                "text": f"/start {code}",
                "chat": {"id": 555, "first_name": "Ali"},
            },
        }
    ]
    res = await client.post(f"{API}/telegram/pair")
    assert res.status_code == 200, res.text
    assert res.json()["data"]["chat_name"] == "Ali"
    assert "pair_code" not in res.json()["data"]
    assert BOT not in res.text
    assert tg.sent()[-1] == {
        "chat_id": 555,
        "text": "Ajanda bağlandı ✅",
        "disable_web_page_preview": True,
    }

    row = await channel(client.db, "telegram")
    assert row.is_enabled is True
    assert BOT not in row.config_encrypted  # duz metin degil
    saved = json.loads(decrypt(row.config_encrypted))
    assert saved["chat_id"] == 555
    assert "pair_code" not in saved  # tek kullanimlik

    got = await client.get(API)
    assert got.status_code == 200
    assert BOT not in got.text and "bot_token" not in got.text
    tel = next(c for c in got.json()["data"]["channels"] if c["kind"] == "telegram")
    assert tel["is_enabled"] is True and tel["bot_username"] == "ajanda_bot"


async def start_and_pair(client, tg, chat_id=9):
    """Kodu config'ten okuyup bota '/start <kod>' yazilmis gibi eslestirir."""
    code = (await client.get(API)).json()["data"]["channels"][0]["pair_code"]
    tg.updates = [
        {"update_id": 1, "message": {"text": f"/start {code}", "chat": {"id": chat_id}}}
    ]
    return await client.post(f"{API}/telegram/pair")


async def test_pairing_rejects_foreign_start_without_or_with_wrong_code(client, tg):
    await client.put(f"{API}/telegram", json={"bot_token": BOT})
    for text in ("/start", "/start 000000x", "/start 1"):
        tg.updates = [{"update_id": 9, "message": {"text": text, "chat": {"id": 666}}}]
        res = await client.post(f"{API}/telegram/pair")
        assert res.status_code == 409, text
        assert res.json()["error"]["code"] == "TELEGRAM_NO_START"
    row = await channel(client.db, "telegram")
    assert row.is_enabled is False
    assert "chat_id" not in json.loads(decrypt(row.config_encrypted))
    assert tg.sent() == []  # yabanciya mesaj gitmedi


async def test_pairing_code_is_single_use_and_expires(client, tg, monkeypatch):
    await client.put(f"{API}/telegram", json={"bot_token": BOT})
    code = (await client.get(API)).json()["data"]["channels"][0]["pair_code"]
    real = notify_module.time.time()
    monkeypatch.setattr(notify_module.time, "time", lambda: real + 601)
    tg.updates = [
        {"update_id": 1, "message": {"text": f"/start {code}", "chat": {"id": 7}}}
    ]
    res = await client.post(f"{API}/telegram/pair")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "TELEGRAM_CODE_EXPIRED"
    chan = (await client.get(API)).json()["data"]["channels"][0]
    assert chan.get("pair_code") is None
    res = await client.post(f"{API}/telegram/code")
    new = res.json()["data"]["pair_code"]
    assert len(new) == 6
    tg.updates = [
        {"update_id": 2, "message": {"text": f"/start {new}", "chat": {"id": 7}}}
    ]
    assert (await client.post(f"{API}/telegram/pair")).status_code == 200
    # eslestikten sonra ayni kodla yeniden eslestirme olmaz
    res = await client.post(f"{API}/telegram/pair")
    assert res.status_code == 409


async def test_delete_telegram_removes_channel(client, tg):
    await client.put(f"{API}/telegram", json={"bot_token": BOT})
    assert (await client.delete(f"{API}/telegram")).status_code == 200
    got = (await client.get(API)).json()["data"]
    assert got["channels"] == []


async def test_toast_toggle_and_settings(client):
    res = await client.put(f"{API}/toast", json={"enabled": True})
    assert res.json()["data"]["is_enabled"] is True
    res = await client.put(
        f"{API}/settings",
        json={"kinds": {"weekly": False}, "browser_reminders_off": False},
    )
    data = res.json()["data"]
    assert data["kinds"] == {
        "night_plan": True,
        "morning": True,
        "overdue": True,
        "weekly": False,
    }
    assert data["browser_reminders_off"] is False
    bad = await client.put(f"{API}/settings", json={"kinds": {"spam": True}})
    assert bad.status_code == 422


async def test_enable_creates_read_pat_and_stores_it_encrypted(client, auth_api):
    res = await client.post(f"{API}/enable")
    assert res.status_code == 200, res.text
    assert PAT not in res.text
    assert auth_api.calls[0] == (
        "POST",
        "/auth/tokens",
        {"name": "Ajanda zamanlayıcı", "scopes": ["read"]},
    )
    async with client.db() as s:
        cred = await s.scalar(select(ServiceCredentialEntity))
    assert cred.token_id == 42
    assert PAT not in cred.token_encrypted and decrypt(cred.token_encrypted) == PAT
    got = (await client.get(API)).json()
    assert got["data"]["enabled"] is True and PAT not in json.dumps(got)

    # ikinci enable yeni anahtar uretmez
    await client.post(f"{API}/enable")
    assert len([c for c in auth_api.calls if c[0] == "POST"]) == 1

    res = await client.post(f"{API}/disable")
    assert res.json()["data"] == {"enabled": False}
    assert ("DELETE", "/auth/tokens/42", None) in auth_api.calls
    async with client.db() as s:
        assert await s.scalar(select(ServiceCredentialEntity)) is None


async def test_test_endpoint_sends_to_enabled_channels(client, tg):
    await client.put(f"{API}/telegram", json={"bot_token": BOT})
    await start_and_pair(client, tg)
    res = await client.post(f"{API}/test")
    assert res.json()["data"]["results"] == {"telegram": "ok"}
    assert tg.sent()[-1]["text"] == "Ajanda\nDeneme bildirimi"


# ---------------- Notifier ----------------
async def test_notifier_records_success_and_error(db_session_maker):
    async with db_session_maker() as s:
        s.add(
            NotificationChannelEntity(
                user_id=7,
                kind="telegram",
                is_enabled=True,
                config_encrypted=encrypt(json.dumps({"bot_token": BOT, "chat_id": 1})),
            )
        )
        s.add(NotificationChannelEntity(user_id=7, kind="toast", is_enabled=False))
        await s.commit()

    fake = FakeTelegram()
    notifier = Notifier(db_session_maker, httpx.MockTransport(fake))
    res = await notifier.send(7, Notification("morning", "Başlık", "Gövde"))
    assert res == {"telegram": "ok"}  # toast kapali: gonderilmez
    assert fake.sent()[0]["text"] == "Başlık\nGövde"
    row = await channel(db_session_maker, "telegram")
    assert row.last_sent_at is not None and row.last_error is None

    fake.send_ok = False
    res = await notifier.send(7, Notification("morning", "B", "G"))
    assert res == {"telegram": "hata"}
    row = await channel(db_session_maker, "telegram")
    assert row.last_error and BOT not in row.last_error


async def test_no_secrets_in_logs(client, tg, caplog):
    caplog.set_level(logging.DEBUG)
    await client.put(f"{API}/telegram", json={"bot_token": BOT})
    await start_and_pair(client, tg)
    await client.post(f"{API}/enable")
    await client.post(f"{API}/test")
    assert BOT not in caplog.text and PAT not in caplog.text
