"""Faz 7b: OAuth altyapisi + Google Takvim tek yonlu senkron (MockTransport, gercek ag yok)."""

import base64
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import func, select

from app.config import settings
from app.core import crypto
from app.db.entities import EventEntity, ExternalLinkEntity, IntegrationAccountEntity
from app.integrations import oauth
from tests.integration.test_boards_cards import API, create_board


def _id_token(email: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode()
    return f"x.{payload.rstrip('=')}.y"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


NOW = datetime.now(UTC).replace(microsecond=0)
TOMORROW = NOW + timedelta(days=1)


def timed(eid, title, start, hours=1, etag="e1", **extra):
    return {
        "id": eid,
        "etag": etag,
        "status": "confirmed",
        "summary": title,
        "htmlLink": f"https://calendar.google.com/event?eid={eid}",
        "start": {"dateTime": _iso(start)},
        "end": {"dateTime": _iso(start + timedelta(hours=hours))},
        **extra,
    }


def all_day(eid, title, day: str, next_day: str, etag="e1"):
    return {
        "id": eid,
        "etag": etag,
        "status": "confirmed",
        "summary": title,
        "start": {"date": day},
        "end": {"date": next_day},
    }


class FakeGoogle:
    """OAuth token ucu + Calendar API'nin kucuk taklidi."""

    def __init__(self):
        self.calendars = [
            {"id": "me@example.com", "summary": "Ben", "primary": True},
            {"id": "team@group.calendar.google.com", "summary": "Takim"},
        ]
        self.events: dict[str, dict[str, dict]] = {c["id"]: {} for c in self.calendars}
        self.delta: dict[str, list[dict]] = {}
        self.expire_sync_token = False
        self.revoked = False
        self.token_requests: list[dict[str, str]] = []
        self.event_requests: list[dict[str, str]] = []
        self.sync_counter = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.host == "oauth2.googleapis.com":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.token_requests.append(form)
            if form["grant_type"] == "authorization_code":
                if form["code"] != "good-code":
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(
                    200,
                    json={
                        "access_token": "at-1",
                        "refresh_token": "rt-1",
                        "expires_in": 3600,
                        "scope": "openid email calendar.readonly",
                        "id_token": _id_token("me@example.com"),
                    },
                )
            if self.revoked:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200, json={"access_token": "at-2", "expires_in": 3600}
            )

        # Calendar API
        if not request.headers.get("authorization", "").startswith("Bearer at-"):
            return httpx.Response(401)
        path = url.path
        if path.endswith("/calendarList"):
            return httpx.Response(200, json={"items": self.calendars})
        if path.startswith("/calendar/v3/calendars/") and path.endswith("/events"):
            cal = path[len("/calendar/v3/calendars/") : -len("/events")]
            params = dict(url.params)
            self.event_requests.append(params)
            if "syncToken" in params:
                if self.expire_sync_token:
                    return httpx.Response(410)
                items = self.delta.pop(cal, [])
            else:
                items = [
                    e
                    for e in self.events[cal].values()
                    if e.get("status") != "cancelled"
                ]
            self.sync_counter += 1
            return httpx.Response(
                200,
                json={"items": items, "nextSyncToken": f"sync-{self.sync_counter}"},
            )
        return httpx.Response(404)


@pytest.fixture
def google(monkeypatch) -> FakeGoogle:
    fake = FakeGoogle()
    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr("app.integrations.oauth.HTTP_TRANSPORT", transport)
    monkeypatch.setattr("app.integrations.google_calendar.HTTP_TRANSPORT", transport)
    monkeypatch.setattr(settings, "google_client_id", "cid")
    monkeypatch.setattr(settings, "google_client_secret", "csecret")
    return fake


@pytest.fixture
async def other_headers(client):
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def connect(client, headers, code="good-code"):
    """connect -> callback; callback'in yonlendirme adresini dondurur."""
    res = await client.post(f"{API}/integrations/google/connect", headers=headers)
    assert res.status_code == 200, res.text
    state = parse_qs(urlparse(res.json()["data"]["authorize_url"]).query)["state"][0]
    cb = await client.get(
        f"{API}/integrations/google/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )
    return cb


async def setup(client, headers, calendars=("me@example.com",), board_id=None):
    cb = await connect(client, headers)
    assert "connected=google" in cb.headers["location"], cb.headers["location"]
    res = await client.put(
        f"{API}/integrations/google/settings",
        json={"calendar_ids": list(calendars), "board_id": board_id},
        headers=headers,
    )
    assert res.status_code == 200, res.text


async def sync(client, headers):
    return await client.post(f"{API}/integrations/google/sync", headers=headers)


async def calendar_items(client, headers):
    start = _iso(NOW - timedelta(days=40))
    end = _iso(NOW + timedelta(days=120))
    res = await client.get(
        f"{API}/calendar", params={"start": start, "end": end}, headers=headers
    )
    assert res.status_code == 200, res.text
    return [i for i in res.json()["data"]["items"] if i["kind"] == "event"]


class TestOAuth:
    async def test_connect_returns_authorize_url_with_signed_state(
        self, client, auth_headers, google
    ):
        res = await client.post(
            f"{API}/integrations/google/connect", headers=auth_headers
        )
        url = urlparse(res.json()["data"]["authorize_url"])
        q = parse_qs(url.query)
        assert url.netloc == "accounts.google.com"
        assert q["client_id"] == ["cid"]
        assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
        assert "calendar.readonly" in q["scope"][0]
        assert q["redirect_uri"] == [
            "http://localhost:8000/api/v1/integrations/google/callback"
        ]
        assert "csecret" not in res.text

    async def test_not_configured_is_422(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(settings, "google_client_id", None)
        res = await client.post(
            f"{API}/integrations/google/connect", headers=auth_headers
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "OAUTH_NOT_CONFIGURED"

    async def test_unknown_provider_404(self, client, auth_headers):
        res = await client.post(f"{API}/integrations/nope/connect", headers=auth_headers)
        assert res.status_code == 404

    async def test_callback_saves_encrypted_tokens(
        self, client, auth_headers, google, test_session
    ):
        cb = await connect(client, auth_headers)
        assert cb.status_code == 302
        assert cb.headers["location"] == (
            "http://localhost:5173/settings?connected=google#baglantilar"
        )
        account = (
            await test_session.execute(select(IntegrationAccountEntity))
        ).scalar_one()
        assert account.account_label == "me@example.com"
        assert account.status == "active"
        assert "at-1" not in account.tokens_encrypted
        assert "rt-1" not in account.tokens_encrypted
        tokens = crypto.decrypt_json(account.tokens_encrypted)
        assert tokens["access_token"] == "at-1" and tokens["refresh_token"] == "rt-1"
        # Gelen Kutusu hazir
        boards = (await client.get(f"{API}/boards", headers=auth_headers)).json()["data"]
        assert any(b.get("system_kind") == "inbox" for b in boards)
        listed = await client.get(f"{API}/integrations", headers=auth_headers)
        assert "at-1" not in listed.text and "rt-1" not in listed.text

    async def test_forged_state_rejected(self, client, auth_headers, google, test_session):
        cb = await client.get(
            f"{API}/integrations/google/callback",
            params={"code": "good-code", "state": "forged.state.value"},
            follow_redirects=False,
        )
        assert cb.status_code == 302
        assert "connect_error=google" in cb.headers["location"]
        assert google.token_requests == []  # token degisimine bile gidilmedi
        n = (
            await test_session.execute(
                select(func.count()).select_from(IntegrationAccountEntity)
            )
        ).scalar()
        assert n == 0

    async def test_state_for_other_provider_or_expired_rejected(self, google):
        import jwt

        good = oauth.make_state(1, "google")
        assert oauth.read_state(good, "google") == 1
        with pytest.raises(oauth.IntegrationError):
            oauth.read_state(good, "microsoft")
        expired = jwt.encode(
            {
                "sub": "1",
                "provider": "google",
                "purpose": "oauth_state",
                "exp": datetime.now(UTC) - timedelta(minutes=1),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(oauth.IntegrationError):
            oauth.read_state(expired, "google")
        # access token'i state olarak kullanmak (purpose yok) da calismaz
        from app.core.security import create_access_token

        with pytest.raises(oauth.IntegrationError):
            oauth.read_state(create_access_token(1), "google")

    async def test_denied_by_user_redirects_with_error(self, client, auth_headers, google):
        cb = await client.get(
            f"{API}/integrations/google/callback",
            params={"error": "access_denied"},
            follow_redirects=False,
        )
        assert "connect_error=google" in cb.headers["location"]

    async def test_bad_code_redirects_with_error(self, client, auth_headers, google):
        cb = await connect(client, auth_headers, code="bad-code")
        assert "connect_error=google" in cb.headers["location"]

    async def test_token_refreshed_when_near_expiry(
        self, client, auth_headers, google, test_session
    ):
        await setup(client, auth_headers)
        account = (
            await test_session.execute(select(IntegrationAccountEntity))
        ).scalar_one()
        account.tokens_encrypted = crypto.encrypt_json(
            {"access_token": "at-old", "refresh_token": "rt-1", "expires_at": time.time() + 10}
        )
        await test_session.commit()
        res = await client.get(f"{API}/integrations/google/calendars", headers=auth_headers)
        assert res.status_code == 200, res.text
        refresh = [r for r in google.token_requests if r["grant_type"] == "refresh_token"]
        assert len(refresh) == 1 and refresh[0]["refresh_token"] == "rt-1"
        await test_session.refresh(account)
        stored = crypto.decrypt_json(account.tokens_encrypted)
        assert stored["access_token"] == "at-2"
        assert stored["refresh_token"] == "rt-1"  # eskisi korunur

    async def test_revoked_refresh_marks_account_error(
        self, client, auth_headers, google, test_session
    ):
        await setup(client, auth_headers)
        account = (
            await test_session.execute(select(IntegrationAccountEntity))
        ).scalar_one()
        account.tokens_encrypted = crypto.encrypt_json(
            {"access_token": "at-old", "refresh_token": "rt-1", "expires_at": 0}
        )
        await test_session.commit()
        google.revoked = True
        res = await sync(client, auth_headers)
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "INTEGRATION_RECONNECT"
        await test_session.refresh(account)
        assert account.status == "error"
        assert "Yeniden bağlan" in account.last_error
        # hata durumunda tekrar senkron denemesi aninda reddedilir
        again = await sync(client, auth_headers)
        assert again.status_code == 409

    async def test_reconnect_after_error_restores_active(
        self, client, auth_headers, google, test_session
    ):
        await setup(client, auth_headers, calendars=["me@example.com"])
        account = (
            await test_session.execute(select(IntegrationAccountEntity))
        ).scalar_one()
        account.status = "error"
        account.last_error = "Yeniden bağlan"
        await test_session.commit()
        cb = await connect(client, auth_headers)
        assert "connected=google" in cb.headers["location"]
        await test_session.refresh(account)
        assert account.status == "active" and account.last_error is None
        assert account.settings["calendar_ids"] == ["me@example.com"]  # ayarlar korunur


class TestCalendarsAndSettings:
    async def test_list_calendars_marks_selected(self, client, auth_headers, google):
        await setup(client, auth_headers, calendars=["team@group.calendar.google.com"])
        res = await client.get(f"{API}/integrations/google/calendars", headers=auth_headers)
        data = res.json()["data"]
        assert [c["id"] for c in data] == ["me@example.com", "team@group.calendar.google.com"]
        assert [c["selected"] for c in data] == [False, True]

    async def test_settings_requires_connection(self, client, auth_headers, google):
        res = await client.put(
            f"{API}/integrations/google/settings",
            json={"calendar_ids": ["x"]},
            headers=auth_headers,
        )
        assert res.status_code == 404

    async def test_settings_rejects_foreign_board(
        self, client, auth_headers, other_headers, google
    ):
        foreign = await create_board(client, other_headers, name="Baskasi")
        await connect(client, auth_headers)
        res = await client.put(
            f"{API}/integrations/google/settings",
            json={"calendar_ids": ["me@example.com"], "board_id": foreign["board"]["id"]},
            headers=auth_headers,
        )
        assert res.status_code == 404

    async def test_sync_without_selection_is_422(self, client, auth_headers, google):
        await connect(client, auth_headers)
        res = await sync(client, auth_headers)
        assert res.status_code == 422

    async def test_sync_unsupported_provider(self, client, auth_headers):
        res = await client.post(f"{API}/integrations/trello/sync", headers=auth_headers)
        assert res.status_code == 404


class TestSync:
    async def test_first_sync_creates_events_with_window(
        self, client, auth_headers, google, test_session
    ):
        google.events["me@example.com"] = {
            "a": timed(
                "a", "Toplanti", TOMORROW, location="Ofis", description="Gundem"
            ),
            "b": all_day("b", "Tatil", "2026-12-24", "2026-12-26"),
        }
        await setup(client, auth_headers)
        res = await sync(client, auth_headers)
        assert res.status_code == 200, res.text
        assert res.json()["data"] == {"created": 2, "updated": 0, "removed": 0, "errors": []}

        params = google.event_requests[0]
        assert params["singleEvents"] == "true"
        assert "timeMin" in params and "timeMax" in params and "syncToken" not in params

        items = {i["title"]: i for i in await calendar_items(client, auth_headers)}
        meeting = items["Toplanti"]
        assert meeting["external"] == {
            "provider": "google",
            "url": "https://calendar.google.com/event?eid=a",
        }
        assert meeting["location"] == "Ofis"
        assert meeting["all_day"] is False
        vacation = items["Tatil"]
        assert vacation["all_day"] is True
        start = datetime.fromisoformat(vacation["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(vacation["end"].replace("Z", "+00:00"))
        assert end - start == timedelta(days=2)  # bitis haric (exclusive)

        event = (
            await test_session.execute(
                select(EventEntity).where(EventEntity.title == "Toplanti")
            )
        ).scalar_one()
        assert event.created_by == "integration" and event.notes == "Gundem"

    async def test_events_land_on_chosen_board(self, client, auth_headers, google):
        board = await create_board(client, auth_headers, name="Is", color="#ef4444")
        google.events["me@example.com"] = {"a": timed("a", "Toplanti", TOMORROW)}
        await setup(client, auth_headers, board_id=board["board"]["id"])
        await sync(client, auth_headers)
        [item] = await calendar_items(client, auth_headers)
        assert item["board_id"] == board["board"]["id"] and item["color"] == "#ef4444"

    async def test_second_sync_uses_sync_token_and_is_idempotent(
        self, client, auth_headers, google, test_session
    ):
        google.events["me@example.com"] = {"a": timed("a", "Toplanti", TOMORROW)}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        res = await sync(client, auth_headers)
        assert res.json()["data"]["created"] == 0
        assert google.event_requests[1]["syncToken"] == "sync-1"
        assert "timeMin" not in google.event_requests[1]
        n = (
            await test_session.execute(select(func.count()).select_from(EventEntity))
        ).scalar()
        assert n == 1

    async def test_incremental_update_and_cancel(self, client, auth_headers, google):
        google.events["me@example.com"] = {
            "a": timed("a", "Toplanti", TOMORROW),
            "b": timed("b", "Yemek", TOMORROW + timedelta(hours=3)),
        }
        await setup(client, auth_headers)
        await sync(client, auth_headers)

        google.delta["me@example.com"] = [
            timed("a", "Toplanti (yeni)", TOMORROW + timedelta(hours=1), etag="e2"),
            {"id": "b", "status": "cancelled"},
            timed("c", "Yeni", TOMORROW + timedelta(days=1)),
        ]
        res = await sync(client, auth_headers)
        assert res.json()["data"] == {"created": 1, "updated": 1, "removed": 1, "errors": []}
        titles = sorted(i["title"] for i in await calendar_items(client, auth_headers))
        assert titles == ["Toplanti (yeni)", "Yeni"]

    async def test_same_etag_is_skipped(self, client, auth_headers, google):
        google.events["me@example.com"] = {"a": timed("a", "Toplanti", TOMORROW)}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        google.delta["me@example.com"] = [timed("a", "Degismemis?", TOMORROW)]  # etag e1
        res = await sync(client, auth_headers)
        assert res.json()["data"]["updated"] == 0
        [item] = await calendar_items(client, auth_headers)
        assert item["title"] == "Toplanti"

    async def test_410_triggers_full_resync_and_drops_vanished(
        self, client, auth_headers, google
    ):
        google.events["me@example.com"] = {
            "a": timed("a", "Kalan", TOMORROW),
            "b": timed("b", "Silinen", TOMORROW + timedelta(hours=3)),
        }
        await setup(client, auth_headers)
        await sync(client, auth_headers)

        del google.events["me@example.com"]["b"]  # Google'da silindi, delta kacirildi
        google.expire_sync_token = True
        res = await sync(client, auth_headers)
        assert res.status_code == 200, res.text
        assert res.json()["data"]["removed"] == 1
        assert [i["title"] for i in await calendar_items(client, auth_headers)] == ["Kalan"]
        # tam yeniden senkron: son istek syncToken'siz, timeMin'li
        assert "syncToken" not in google.event_requests[-1]
        assert "timeMin" in google.event_requests[-1]

    async def test_cancelled_event_never_created(self, client, auth_headers, google):
        google.events["me@example.com"] = {
            "x": {"id": "x", "status": "cancelled"},
        }
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        google.delta["me@example.com"] = [{"id": "never-seen", "status": "cancelled"}]
        res = await sync(client, auth_headers)
        assert res.json()["data"]["removed"] == 0
        assert await calendar_items(client, auth_headers) == []

    async def test_event_without_title_and_zero_length(self, client, auth_headers, google):
        zero = timed("z", "", TOMORROW, hours=0)
        zero["summary"] = None
        google.events["me@example.com"] = {"z": zero}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        [item] = await calendar_items(client, auth_headers)
        assert item["title"] == "(Başlıksız)"
        start = datetime.fromisoformat(item["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(item["end"].replace("Z", "+00:00"))
        assert end > start

    async def test_event_recreated_if_deleted_locally(
        self, client, auth_headers, google, test_session
    ):
        google.events["me@example.com"] = {"a": timed("a", "Toplanti", TOMORROW)}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        # Yerelde kayit kaybolmus (orn. board silinmesi): baglanti kalir
        event = (await test_session.execute(select(EventEntity))).scalar_one()
        await test_session.delete(event)
        await test_session.commit()
        google.delta["me@example.com"] = [
            timed("a", "Toplanti", TOMORROW, etag="e2")
        ]
        res = await sync(client, auth_headers)
        assert res.json()["data"]["created"] == 1
        links = (await test_session.execute(select(ExternalLinkEntity))).scalars().all()
        assert len(links) == 1  # baglanti cogalmadi, yeni etkinlige tasindi

    async def test_one_calendar_failure_does_not_stop_others(
        self, client, auth_headers, google
    ):
        google.events["me@example.com"] = {"a": timed("a", "Ben", TOMORROW)}
        # ikinci takvimin olay listesi 404 versin
        del google.events["team@group.calendar.google.com"]
        await setup(
            client,
            auth_headers,
            calendars=["team@group.calendar.google.com", "me@example.com"],
        )
        original = google.handler

        def handler(request):
            if "team" in request.url.path and request.url.path.endswith("/events"):
                return httpx.Response(404)
            return original(request)

        # transport'u degistir
        import app.integrations.google_calendar as gc

        gc.HTTP_TRANSPORT = httpx.MockTransport(handler)
        try:
            res = await sync(client, auth_headers)
        finally:
            gc.HTTP_TRANSPORT = None
        data = res.json()["data"]
        assert data["created"] == 1
        assert len(data["errors"]) == 1 and "team@group" in data["errors"][0]

    async def test_user_isolation(self, client, auth_headers, other_headers, google):
        google.events["me@example.com"] = {"a": timed("a", "Ozel", TOMORROW)}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        assert await calendar_items(client, other_headers) == []


class TestReadOnly:
    async def _synced_event_id(self, client, headers, google):
        google.events["me@example.com"] = {"a": timed("a", "Toplanti", TOMORROW)}
        await setup(client, headers)
        await sync(client, headers)
        [item] = await calendar_items(client, headers)
        return item["event_id"]

    async def test_update_and_delete_rejected(self, client, auth_headers, google):
        eid = await self._synced_event_id(client, auth_headers, google)
        patch = await client.patch(
            f"{API}/events/{eid}", json={"title": "Degis"}, headers=auth_headers
        )
        assert patch.status_code == 409
        assert patch.json()["error"]["code"] == "EVENT_READ_ONLY"
        delete = await client.delete(f"{API}/events/{eid}", headers=auth_headers)
        assert delete.status_code == 409
        got = await client.get(f"{API}/events/{eid}", headers=auth_headers)
        assert got.json()["data"]["external"]["provider"] == "google"
        assert got.json()["data"]["title"] == "Toplanti"

    async def test_local_events_stay_editable(self, client, auth_headers, google):
        res = await client.post(
            f"{API}/events",
            json={
                "title": "Yerel",
                "start_at": _iso(TOMORROW),
                "end_at": _iso(TOMORROW + timedelta(hours=1)),
            },
            headers=auth_headers,
        )
        eid = res.json()["data"]["id"]
        assert res.json()["data"]["external"] is None
        patch = await client.patch(
            f"{API}/events/{eid}", json={"title": "Yeni"}, headers=auth_headers
        )
        assert patch.status_code == 200


class TestDeselectAndDisconnect:
    async def test_deselecting_calendar_removes_its_events(
        self, client, auth_headers, google
    ):
        google.events["me@example.com"] = {"a": timed("a", "Ben", TOMORROW)}
        google.events["team@group.calendar.google.com"] = {
            "t": timed("t", "Takim", TOMORROW)
        }
        await setup(
            client,
            auth_headers,
            calendars=["me@example.com", "team@group.calendar.google.com"],
        )
        await sync(client, auth_headers)
        assert len(await calendar_items(client, auth_headers)) == 2
        await client.put(
            f"{API}/integrations/google/settings",
            json={"calendar_ids": ["me@example.com"]},
            headers=auth_headers,
        )
        assert [i["title"] for i in await calendar_items(client, auth_headers)] == ["Ben"]

    async def test_changing_board_moves_existing_events(self, client, auth_headers, google):
        board = await create_board(client, auth_headers, name="Is", color="#ef4444")
        google.events["me@example.com"] = {"a": timed("a", "Ben", TOMORROW)}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        await client.put(
            f"{API}/integrations/google/settings",
            json={"calendar_ids": ["me@example.com"], "board_id": board["board"]["id"]},
            headers=auth_headers,
        )
        [item] = await calendar_items(client, auth_headers)
        assert item["board_id"] == board["board"]["id"]

    async def test_disconnect_removes_google_events_keeps_local(
        self, client, auth_headers, google, test_session
    ):
        google.events["me@example.com"] = {"a": timed("a", "Google", TOMORROW)}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        await client.post(
            f"{API}/events",
            json={
                "title": "Yerel",
                "start_at": _iso(TOMORROW),
                "end_at": _iso(TOMORROW + timedelta(hours=1)),
            },
            headers=auth_headers,
        )
        res = await client.delete(f"{API}/integrations/google", headers=auth_headers)
        assert res.status_code == 204
        assert [i["title"] for i in await calendar_items(client, auth_headers)] == ["Yerel"]
        n = (
            await test_session.execute(
                select(func.count()).select_from(ExternalLinkEntity)
            )
        ).scalar()
        assert n == 0


class TestScheduler:
    async def test_sync_all_accounts_runs_for_active_accounts(
        self, client, auth_headers, google, test_session, monkeypatch
    ):
        google.events["me@example.com"] = {"a": timed("a", "Toplanti", TOMORROW)}
        await setup(client, auth_headers)

        class _Ctx:
            async def __aenter__(self_):
                return test_session

            async def __aexit__(self_, *exc):
                return False

        monkeypatch.setattr("app.db.database.async_session_maker", lambda: _Ctx())
        from app.integrations.scheduler import run_once

        await run_once()
        assert [i["title"] for i in await calendar_items(client, auth_headers)] == [
            "Toplanti"
        ]

    async def test_loop_survives_failures(self, monkeypatch):
        import asyncio

        from app.integrations import scheduler

        calls = 0

        async def boom():
            nonlocal calls
            calls += 1
            raise RuntimeError("x")

        monkeypatch.setattr(
            "app.integrations.google_calendar.sync_all_accounts", boom
        )
        async def noop():
            return None

        monkeypatch.setattr("app.integrations.microsoft_todo.sync_all_accounts", noop)
        monkeypatch.setattr("app.integrations.microsoft_calendar.sync_all_accounts", noop)
        task = asyncio.create_task(scheduler.sync_loop(first_delay=0, interval=0.01))
        await asyncio.sleep(0.1)
        task.cancel()
        assert calls >= 2
