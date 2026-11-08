"""OAuth uygulama kimliginin arayuzden girilmesi (kurulum sihirbazi; .env gerekmez)."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.db.entities import IntegrationAccountEntity, OAuthClientEntity
from tests.integration.test_boards_cards import API
from tests.integration.test_integrations_google import FakeGoogle, connect

GOOGLE_ID = "123-abc.apps.googleusercontent.com"
GOOGLE_SECRET = "GOCSPX-supersecretvalue"
MS_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"


@pytest.fixture(autouse=True)
def no_env_clients(monkeypatch):
    for name in (
        "google_client_id",
        "google_client_secret",
        "microsoft_client_id",
        "microsoft_client_secret",
    ):
        monkeypatch.setattr(settings, name, None)


@pytest.fixture
def google_net(monkeypatch) -> FakeGoogle:
    fake = FakeGoogle()
    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr("app.integrations.oauth.HTTP_TRANSPORT", transport)
    monkeypatch.setattr("app.integrations.google_calendar.HTTP_TRANSPORT", transport)
    return fake


@pytest.fixture
async def other_headers(client):
    creds = {"email": "other2@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def save_google(client, headers, cid=GOOGLE_ID, secret=GOOGLE_SECRET):
    return await client.put(
        f"{API}/integrations/google/oauth-client",
        json={"client_id": cid, "client_secret": secret},
        headers=headers,
    )


async def infos(client, headers) -> dict[str, dict]:
    res = await client.get(f"{API}/integrations/oauth-clients", headers=headers)
    assert res.status_code == 200, res.text
    return {i["provider"]: i for i in res.json()["data"]}


class TestOAuthClientSetup:
    async def test_initially_not_configured_with_redirect_uri(self, client, auth_headers):
        data = await infos(client, auth_headers)
        assert data["google"]["configured"] is False
        assert data["google"]["source"] is None
        assert data["google"]["redirect_uri"] == (
            "http://localhost:8000/api/v1/integrations/google/callback"
        )
        assert data["microsoft"]["redirect_uri"].endswith("/integrations/microsoft/callback")

    async def test_connect_without_client_explains_where_to_set_it(
        self, client, auth_headers
    ):
        res = await client.post(f"{API}/integrations/google/connect", headers=auth_headers)
        assert res.status_code == 422
        err = res.json()["error"]
        assert err["code"] == "OAUTH_NOT_CONFIGURED"
        assert "Bağlantılar" in err["message"] and ".env" not in err["message"]

    async def test_save_encrypts_secret_and_never_returns_it(
        self, client, auth_headers, test_session
    ):
        res = await save_google(client, auth_headers)
        assert res.status_code == 200, res.text
        assert GOOGLE_SECRET not in res.text
        assert res.json()["data"] == {
            "provider": "google",
            "configured": True,
            "source": "app",
            "client_id": GOOGLE_ID,
            "redirect_uri": "http://localhost:8000/api/v1/integrations/google/callback",
        }
        row = (await test_session.execute(select(OAuthClientEntity))).scalar_one()
        assert GOOGLE_SECRET not in row.client_secret_encrypted
        listed = await client.get(f"{API}/integrations/oauth-clients", headers=auth_headers)
        assert GOOGLE_SECRET not in listed.text

    async def test_saved_client_used_for_full_connect(
        self, client, auth_headers, google_net, test_session
    ):
        await save_google(client, auth_headers)
        res = await client.post(f"{API}/integrations/google/connect", headers=auth_headers)
        q = parse_qs(urlparse(res.json()["data"]["authorize_url"]).query)
        assert q["client_id"] == [GOOGLE_ID]
        cb = await connect(client, auth_headers)
        assert "connected=google" in cb.headers["location"], cb.headers["location"]
        token_req = google_net.token_requests[-1]
        assert token_req["client_id"] == GOOGLE_ID
        assert token_req["client_secret"] == GOOGLE_SECRET
        account = (await test_session.execute(select(IntegrationAccountEntity))).scalar_one()
        assert account.status == "active"

    async def test_update_replaces_values(self, client, auth_headers):
        await save_google(client, auth_headers)
        res = await save_google(client, auth_headers, cid="999-x.apps.googleusercontent.com")
        assert res.json()["data"]["client_id"] == "999-x.apps.googleusercontent.com"

    async def test_values_are_trimmed(self, client, auth_headers):
        res = await save_google(client, auth_headers, cid=f"  {GOOGLE_ID}\n")
        assert res.status_code == 200
        assert res.json()["data"]["client_id"] == GOOGLE_ID

    async def test_app_value_wins_over_env_and_delete_falls_back(
        self, client, auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "google_client_id", "env.apps.googleusercontent.com")
        monkeypatch.setattr(settings, "google_client_secret", "env-secret")
        assert (await infos(client, auth_headers))["google"]["source"] == "env"
        await save_google(client, auth_headers)
        assert (await infos(client, auth_headers))["google"]["source"] == "app"
        res = await client.delete(
            f"{API}/integrations/google/oauth-client", headers=auth_headers
        )
        assert res.status_code == 204
        data = (await infos(client, auth_headers))["google"]
        assert data["source"] == "env"
        assert data["client_id"] == "env.apps.googleusercontent.com"

    async def test_per_user(self, client, auth_headers, other_headers):
        await save_google(client, auth_headers)
        assert (await infos(client, other_headers))["google"]["configured"] is False

    async def test_unknown_provider_404(self, client, auth_headers):
        res = await client.put(
            f"{API}/integrations/nope/oauth-client",
            json={"client_id": "a", "client_secret": "b"},
            headers=auth_headers,
        )
        assert res.status_code == 404


class TestValidation:
    @pytest.mark.parametrize(
        ("cid", "secret", "hint"),
        [
            ("123-abc", GOOGLE_SECRET, "apps.googleusercontent.com"),
            (GOOGLE_ID, GOOGLE_ID, "Client secret"),
            (GOOGLE_ID, "GOCSPX abc", "boşluk"),
        ],
    )
    async def test_google_copy_mistakes(self, client, auth_headers, cid, secret, hint):
        res = await save_google(client, auth_headers, cid=cid, secret=secret)
        assert res.status_code == 422
        assert hint in res.json()["error"]["message"]

    async def test_microsoft_secret_id_instead_of_value(self, client, auth_headers):
        res = await client.put(
            f"{API}/integrations/microsoft/oauth-client",
            json={"client_id": MS_ID, "client_secret": "6f1c2b9e-1111-2222-3333-444455556666"},
            headers=auth_headers,
        )
        assert res.status_code == 422
        assert "Value" in res.json()["error"]["message"]

    async def test_microsoft_client_id_must_be_guid(self, client, auth_headers):
        res = await client.put(
            f"{API}/integrations/microsoft/oauth-client",
            json={"client_id": "not-a-guid", "client_secret": "abc~DEF.ghi_123"},
            headers=auth_headers,
        )
        assert res.status_code == 422
        assert "Application (client) ID" in res.json()["error"]["message"]

    async def test_microsoft_ok(self, client, auth_headers):
        res = await client.put(
            f"{API}/integrations/microsoft/oauth-client",
            json={"client_id": MS_ID, "client_secret": "abc~DEF.ghi_123"},
            headers=auth_headers,
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["source"] == "app"


class TestErrorMessages:
    async def test_wrong_secret_gives_actionable_message(
        self, client, auth_headers, google_net, monkeypatch
    ):
        await save_google(client, auth_headers)
        original = google_net.handler

        def bad_client(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                return httpx.Response(401, json={"error": "invalid_client"})
            return original(request)

        monkeypatch.setattr(
            "app.integrations.oauth.HTTP_TRANSPORT", httpx.MockTransport(bad_client)
        )
        cb = await connect(client, auth_headers)
        location = cb.headers["location"]
        assert "connect_error=google" in location
        message = parse_qs(urlparse(location).query)["message"][0]
        assert "Kimlik bilgilerini değiştir" in message

    async def test_provider_error_description_is_shown(self, client, auth_headers):
        cb = await client.get(
            f"{API}/integrations/microsoft/callback",
            params={
                "error": "invalid_request",
                "error_description": "AADSTS50194: Application is not configured as multi-tenant.\r\nTrace ID: x",
            },
            follow_redirects=False,
        )
        message = parse_qs(urlparse(cb.headers["location"]).query)["message"][0]
        assert "AADSTS50194" in message and "Trace ID" not in message

    async def test_access_denied_stays_short(self, client, auth_headers):
        cb = await client.get(
            f"{API}/integrations/google/callback",
            params={"error": "access_denied"},
            follow_redirects=False,
        )
        message = parse_qs(urlparse(cb.headers["location"]).query)["message"][0]
        assert message == "İzin verilmedi ya da bağlantı iptal edildi."
