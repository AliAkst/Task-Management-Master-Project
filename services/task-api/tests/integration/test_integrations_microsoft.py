"""Faz 7c: Microsoft To Do iki yonlu tamamlama (MockTransport, gercek ag yok)."""

import base64
import json
import time
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.core import crypto
from app.db.entities import ExternalLinkEntity, IntegrationAccountEntity
from app.integrations import microsoft_todo
from app.integrations.microsoft_todo import map_task
from tests.integration.test_boards_cards import API, create_board

BASE = "https://graph.microsoft.com/v1.0"


def _id_token(username: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"preferred_username": username}).encode()
    ).decode()
    return f"x.{payload.rstrip('=')}.y"


def task(tid, title, *, status="notStarted", version="v1", **extra):
    return {
        "id": tid,
        "@odata.etag": version,
        "title": title,
        "status": status,
        "importance": "normal",
        **extra,
    }


class FakeGraph:
    """Microsoft token ucu + Graph To Do API'sinin kucuk taklidi."""

    def __init__(self):
        self.lists = [
            {"id": "L1", "displayName": "Hatırlatıcılar"},
            {"id": "L2", "displayName": "Alışveriş"},
        ]
        self.tasks: dict[str, dict[str, dict]] = {"L1": {}, "L2": {}}
        self.delta: dict[str, list[dict]] = {}
        self.expire_delta = False
        self.revoked = False
        self.fail_patch = False  # 500
        self.missing_on_patch: set[str] = set()  # 404
        self.page_size: int | None = None
        self.patches: list[tuple[str, str, dict]] = []
        self.token_requests: list[dict[str, str]] = []
        self.counter = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.host == "login.microsoftonline.com":
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
                        "id_token": _id_token("ben@outlook.com"),
                    },
                )
            if self.revoked:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200,
                json={"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 3600},
            )

        assert url.host == "graph.microsoft.com"
        if not request.headers.get("authorization", "").startswith("Bearer at-"):
            return httpx.Response(401)
        path = url.path.removeprefix("/v1.0")
        if path == "/me/todo/lists":
            return httpx.Response(200, json={"value": self.lists})

        parts = path.split("/")  # '', me, todo, lists, L, tasks, ...
        list_id = parts[4]
        if request.method == "PATCH":
            task_id = parts[6]
            body = json.loads(request.content)
            self.patches.append((list_id, task_id, body))
            if task_id in self.missing_on_patch:
                return httpx.Response(404)
            if self.fail_patch:
                return httpx.Response(500)
            current = self.tasks[list_id].setdefault(task_id, task(task_id, "?"))
            current.update(body)
            return httpx.Response(200, json=current)

        assert path.endswith("/tasks/delta"), path
        params = dict(url.params)
        if "$deltatoken" in params:
            if self.expire_delta:
                return httpx.Response(410)
            items = self.delta.pop(list_id, [])
        else:
            items = [dict(t) for t in self.tasks[list_id].values()]
        self.counter += 1
        base = f"{BASE}/me/todo/lists/{list_id}/tasks/delta"
        if self.page_size and "$deltatoken" not in params:
            skip = int(params.get("$skiptoken", 0))
            page = items[skip : skip + self.page_size]
            if skip + self.page_size < len(items):
                return httpx.Response(
                    200,
                    json={
                        "value": page,
                        "@odata.nextLink": f"{base}?$skiptoken={skip + self.page_size}",
                    },
                )
            items = page
        return httpx.Response(
            200,
            json={
                "value": items,
                "@odata.deltaLink": f"{base}?$deltatoken=d{self.counter}",
            },
        )


@pytest.fixture
def graph(monkeypatch) -> FakeGraph:
    fake = FakeGraph()
    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr("app.integrations.oauth.HTTP_TRANSPORT", transport)
    monkeypatch.setattr("app.integrations.microsoft_todo.HTTP_TRANSPORT", transport)
    monkeypatch.setattr(settings, "microsoft_client_id", "mid")
    monkeypatch.setattr(settings, "microsoft_client_secret", "msecret")
    return fake


@pytest.fixture
def pushes(monkeypatch) -> list[int]:
    """Arka plan geri yazmayi (yeni oturum acar) kaydedip engeller."""
    calls: list[int] = []
    monkeypatch.setattr(microsoft_todo, "schedule_push", calls.append)
    return calls


@pytest.fixture
async def other_headers(client):
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def connect(client, headers, code="good-code"):
    res = await client.post(f"{API}/integrations/microsoft/connect", headers=headers)
    assert res.status_code == 200, res.text
    state = parse_qs(urlparse(res.json()["data"]["authorize_url"]).query)["state"][0]
    return await client.get(
        f"{API}/integrations/microsoft/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )


async def setup(client, headers):
    cb = await connect(client, headers)
    assert "connected=microsoft" in cb.headers["location"], cb.headers["location"]


async def sync(client, headers):
    return await client.post(f"{API}/integrations/microsoft/sync", headers=headers)


async def inbox_cards(client, headers) -> list[dict]:
    boards = (await client.get(f"{API}/boards", headers=headers)).json()["data"]
    inbox = next(b for b in boards if b["system_kind"] == "inbox")
    detail = (await client.get(f"{API}/boards/{inbox['id']}", headers=headers)).json()[
        "data"
    ]
    return detail["cards"]


async def card_by_title(client, headers, title) -> dict:
    cards = [c for c in await inbox_cards(client, headers) if c["title"] == title]
    assert len(cards) == 1, f"{title}: {len(cards)} kart"
    res = await client.get(f"{API}/cards/{cards[0]['id']}", headers=headers)
    return res.json()["data"]


async def links(test_session) -> list[ExternalLinkEntity]:
    test_session.expire_all()
    result = await test_session.execute(
        select(ExternalLinkEntity).where(ExternalLinkEntity.provider == "microsoft")
    )
    return list(result.scalars().all())


class TestMapping:
    TZ = ZoneInfo("Europe/Istanbul")

    def test_basic_fields_and_priority(self):
        mapped = map_task(
            {
                "id": "t",
                "title": "  Süt al  ",
                "importance": "high",
                "status": "notStarted",
                "body": {"contentType": "text", "content": " iki litre "},
            },
            self.TZ,
        )
        assert mapped.title == "Süt al"
        assert mapped.description == "iki litre"
        assert mapped.priority.value == "high"
        assert not mapped.completed and mapped.due_date is None

    def test_html_body_is_stripped(self):
        mapped = map_task(
            {"title": "x", "body": {"contentType": "html", "content": "<p>A&amp;B</p><br>C"}},
            self.TZ,
        )
        assert mapped.description == "A&B\nC"

    def test_due_date_is_local_end_of_day(self):
        # To Do tarihi 00:00 UTC olarak yollar; gun degismemeli, 23:59 yerel olmali
        mapped = map_task(
            {
                "title": "x",
                "dueDateTime": {"dateTime": "2026-11-09T00:00:00.0000000", "timeZone": "UTC"},
            },
            self.TZ,
        )
        assert mapped.due_date == datetime(2026, 11, 9, 20, 59, tzinfo=UTC)  # 23:59 +03

    def test_reminder_used_when_no_due_and_windows_zone_falls_back_to_utc(self):
        mapped = map_task(
            {
                "title": "x",
                "reminderDateTime": {
                    "dateTime": "2026-11-09T06:30:00.0000000",
                    "timeZone": "Turkey Standard Time",
                },
            },
            self.TZ,
        )
        assert mapped.due_date == datetime(2026, 11, 9, 6, 30, tzinfo=UTC)

    def test_untitled_and_low_importance(self):
        mapped = map_task({"title": "", "importance": "low", "status": "completed"}, self.TZ)
        assert mapped.title == "(Başlıksız)"
        assert mapped.priority.value == "low" and mapped.completed

    def test_fingerprint_ignores_completion(self):
        a = map_task({"title": "x", "status": "notStarted"}, self.TZ)
        b = map_task({"title": "x", "status": "completed"}, self.TZ)
        c = map_task({"title": "y"}, self.TZ)
        assert a.fingerprint() == b.fingerprint() != c.fingerprint()


class TestOAuth:
    async def test_connect_url(self, client, auth_headers, graph):
        res = await client.post(
            f"{API}/integrations/microsoft/connect", headers=auth_headers
        )
        url = urlparse(res.json()["data"]["authorize_url"])
        q = parse_qs(url.query)
        assert url.netloc == "login.microsoftonline.com"
        assert url.path == "/consumers/oauth2/v2.0/authorize"
        assert q["client_id"] == ["mid"]
        scopes = q["scope"][0].split()
        assert {"offline_access", "User.Read", "Tasks.ReadWrite"} <= set(scopes)
        assert q["redirect_uri"] == [
            "http://localhost:8000/api/v1/integrations/microsoft/callback"
        ]
        assert "msecret" not in res.text

    async def test_not_configured_is_422(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(settings, "microsoft_client_id", None)
        res = await client.post(
            f"{API}/integrations/microsoft/connect", headers=auth_headers
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "OAUTH_NOT_CONFIGURED"

    async def test_callback_saves_encrypted_tokens_and_creates_inbox(
        self, client, auth_headers, graph, test_session
    ):
        await setup(client, auth_headers)
        account = (
            await test_session.execute(select(IntegrationAccountEntity))
        ).scalar_one()
        assert account.provider == "microsoft"
        assert account.account_label == "ben@outlook.com"
        assert "at-1" not in account.tokens_encrypted
        assert crypto.decrypt_json(account.tokens_encrypted)["refresh_token"] == "rt-1"
        boards = (await client.get(f"{API}/boards", headers=auth_headers)).json()["data"]
        assert [b["system_kind"] for b in boards].count("inbox") == 1

    async def test_state_of_other_provider_rejected(self, client, auth_headers, graph):
        res = await client.post(
            f"{API}/integrations/google/connect", headers=auth_headers
        )
        # google yapilandirilmamis olabilir; asil kontrol: google state'i microsoft'ta gecmez
        from app.integrations import oauth

        state = oauth.make_state(1, "google")
        cb = await client.get(
            f"{API}/integrations/microsoft/callback",
            params={"code": "good-code", "state": state},
            follow_redirects=False,
        )
        assert "connect_error=microsoft" in cb.headers["location"]
        assert res is not None

    async def test_revoked_refresh_marks_account_error(
        self, client, auth_headers, graph, test_session
    ):
        await setup(client, auth_headers)
        account = (
            await test_session.execute(select(IntegrationAccountEntity))
        ).scalar_one()
        account.tokens_encrypted = crypto.encrypt_json(
            {"access_token": "at-old", "refresh_token": "rt-1", "expires_at": 0}
        )
        await test_session.commit()
        graph.revoked = True
        res = await sync(client, auth_headers)
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "INTEGRATION_RECONNECT"
        await test_session.refresh(account)
        assert account.status == "error"

    async def test_refresh_rotates_refresh_token(
        self, client, auth_headers, graph, test_session
    ):
        await setup(client, auth_headers)
        account = (
            await test_session.execute(select(IntegrationAccountEntity))
        ).scalar_one()
        account.tokens_encrypted = crypto.encrypt_json(
            {"access_token": "at-old", "refresh_token": "rt-1", "expires_at": time.time() + 5}
        )
        await test_session.commit()
        res = await client.get(f"{API}/integrations/microsoft/lists", headers=auth_headers)
        assert res.status_code == 200, res.text
        await test_session.refresh(account)
        stored = crypto.decrypt_json(account.tokens_encrypted)
        assert stored["access_token"] == "at-2" and stored["refresh_token"] == "rt-2"


class TestInboundSync:
    async def test_new_tasks_become_inbox_cards(self, client, auth_headers, graph, pushes):
        graph.tasks["L1"] = {
            "a": task(
                "a",
                "Süt al",
                importance="high",
                body={"contentType": "text", "content": "iki litre"},
                dueDateTime={"dateTime": "2026-11-09T00:00:00.0000000", "timeZone": "UTC"},
            ),
            "b": task("b", "Faturayı öde"),
            "old": task("old", "Eski bitmiş iş", status="completed"),
        }
        graph.tasks["L2"] = {"c": task("c", "Ekmek")}
        await setup(client, auth_headers)
        res = await sync(client, auth_headers)
        assert res.status_code == 200, res.text
        assert res.json()["data"] == {"created": 3, "updated": 0, "removed": 0, "errors": []}

        titles = sorted(c["title"] for c in await inbox_cards(client, auth_headers))
        assert titles == ["Ekmek", "Faturayı öde", "Süt al"]  # tamamlanmış eski görev yok

        card = await card_by_title(client, auth_headers, "Süt al")
        assert card["priority"] == "high"
        assert card["description"] == "iki litre"
        assert card["due_date"] is not None
        assert card["created_by"] == "integration"
        assert card["external"]["provider"] == "microsoft"
        assert card["external"]["pending_push"] is False
        assert pushes == []  # içe alma geri yazmayı tetiklemez

    async def test_second_sync_is_idempotent(self, client, auth_headers, graph, pushes):
        graph.tasks["L1"] = {"a": task("a", "Süt al")}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        again = await sync(client, auth_headers)
        assert again.json()["data"]["created"] == 0
        assert len(await inbox_cards(client, auth_headers)) == 1

    async def test_paged_delta_is_followed(self, client, auth_headers, graph, pushes):
        graph.tasks["L1"] = {f"t{i}": task(f"t{i}", f"Görev {i}") for i in range(5)}
        graph.page_size = 2
        await setup(client, auth_headers)
        res = await sync(client, auth_headers)
        assert res.json()["data"]["created"] == 5

    async def test_remote_update_changes_card(self, client, auth_headers, graph, pushes):
        graph.tasks["L1"] = {"a": task("a", "Süt al")}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        graph.delta["L1"] = [
            task("a", "Süt ve yoğurt al", version="v2", importance="low")
        ]
        res = await sync(client, auth_headers)
        assert res.json()["data"]["updated"] == 1
        card = await card_by_title(client, auth_headers, "Süt ve yoğurt al")
        assert card["priority"] == "low"

    async def test_remote_completion_completes_card_and_unblocks(
        self, client, auth_headers, graph, pushes, test_session
    ):
        graph.tasks["L1"] = {"a": task("a", "Süt al")}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        a = await card_by_title(client, auth_headers, "Süt al")

        other = await create_board(client, auth_headers, name="Mutfak")
        dependent = (
            await client.post(
                f"{API}/cards",
                json={"list_id": other["lists"][0]["id"], "title": "Kahvaltı hazırla"},
                headers=auth_headers,
            )
        ).json()["data"]
        dep = await client.post(
            f"{API}/cards/{dependent['id']}/dependencies",
            json={"depends_on_id": a["id"]},
            headers=auth_headers,
        )
        assert dep.status_code in (200, 201), dep.text
        assert (await client.get(f"{API}/cards/{dependent['id']}", headers=auth_headers)).json()[
            "data"
        ]["blocked"] is True

        graph.delta["L1"] = [task("a", "Süt al", status="completed", version="v2")]
        await sync(client, auth_headers)

        a = await card_by_title(client, auth_headers, "Süt al")
        assert a["status"] == "completed" and a["completed_at"]
        after = (await client.get(f"{API}/cards/{dependent['id']}", headers=auth_headers)).json()[
            "data"
        ]
        assert after["blocked"] is False  # unblock yolu çalıştı
        # Uzak tamamlama geri yazılmaz (döngü yok)
        assert pushes == [] and graph.patches == []
        assert [link.pending_push for link in await links(test_session)] == [False]

    async def test_remote_reopen_reopens_card(self, client, auth_headers, graph, pushes):
        graph.tasks["L1"] = {"a": task("a", "Süt al")}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        graph.delta["L1"] = [task("a", "Süt al", status="completed", version="v2")]
        await sync(client, auth_headers)
        graph.delta["L1"] = [task("a", "Süt al", status="notStarted", version="v3")]
        await sync(client, auth_headers)
        card = await card_by_title(client, auth_headers, "Süt al")
        assert card["status"] == "pending" and card["completed_at"] is None
        assert graph.patches == []

    async def test_removed_task_archives_card(self, client, auth_headers, graph, pushes):
        graph.tasks["L1"] = {"a": task("a", "Süt al")}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        card_id = (await card_by_title(client, auth_headers, "Süt al"))["id"]
        graph.delta["L1"] = [{"id": "a", "@removed": {"reason": "deleted"}}]
        res = await sync(client, auth_headers)
        assert res.json()["data"]["removed"] == 1
        card = (await client.get(f"{API}/cards/{card_id}", headers=auth_headers)).json()["data"]
        assert card["is_archived"] is True  # silinmez, arşivlenir

    async def test_locally_deleted_card_does_not_come_back(
        self, client, auth_headers, graph, pushes
    ):
        graph.tasks["L1"] = {"a": task("a", "Süt al")}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        card = await card_by_title(client, auth_headers, "Süt al")
        await client.delete(f"{API}/cards/{card['id']}", headers=auth_headers)
        graph.delta["L1"] = [task("a", "Süt al", version="v2", importance="high")]
        res = await sync(client, auth_headers)
        assert res.json()["data"]["created"] == 0
        assert await inbox_cards(client, auth_headers) == []

    async def test_expired_delta_triggers_full_resync(
        self, client, auth_headers, graph, pushes
    ):
        graph.tasks["L1"] = {"a": task("a", "Süt al"), "b": task("b", "Ekmek")}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        ekmek_id = (await card_by_title(client, auth_headers, "Ekmek"))["id"]
        # 410: delta geçersiz; tam senkronda "b" artık uzakta yok -> arşivlenir, "c" gelir
        graph.expire_delta = True
        graph.tasks["L1"] = {"a": task("a", "Süt al"), "c": task("c", "Yeni iş")}
        res = await sync(client, auth_headers)
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["created"] == 1 and data["removed"] == 1
        ekmek = (await client.get(f"{API}/cards/{ekmek_id}", headers=auth_headers)).json()["data"]
        assert ekmek["is_archived"] is True
        assert "Yeni iş" in {c["title"] for c in await inbox_cards(client, auth_headers)}

    async def test_list_error_does_not_stop_other_lists(
        self, client, auth_headers, graph, pushes, monkeypatch
    ):
        graph.tasks["L2"] = {"c": task("c", "Ekmek")}
        graph.lists.insert(0, {"id": "BAD", "displayName": "Bozuk"})
        graph.tasks["BAD"] = {}
        original = graph.handler

        def handler(request):
            if "/lists/BAD/" in request.url.path:
                return httpx.Response(500)
            return original(request)

        transport = httpx.MockTransport(handler)
        monkeypatch.setattr("app.integrations.microsoft_todo.HTTP_TRANSPORT", transport)
        await setup(client, auth_headers)
        res = (await sync(client, auth_headers)).json()["data"]
        assert res["created"] == 1
        assert len(res["errors"]) == 1 and "Bozuk" in res["errors"][0]


class TestOutbox:
    async def _synced_card(self, client, auth_headers, graph, title="Süt al"):
        graph.tasks["L1"] = {"a": task("a", title)}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        return await card_by_title(client, auth_headers, title)

    async def test_local_completion_is_pushed(
        self, client, auth_headers, graph, pushes, test_session
    ):
        card = await self._synced_card(client, auth_headers, graph)
        res = await client.patch(
            f"{API}/cards/{card['id']}", json={"status": "completed"}, headers=auth_headers
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["external"]["pending_push"] is True
        assert len(pushes) == 1  # arka plan itişi tetiklendi
        status = (
            await client.get(f"{API}/integrations/microsoft/status", headers=auth_headers)
        ).json()["data"]
        assert status == {"pending_push": 1, "failed_push": 0}

        await sync(client, auth_headers)  # tur başında bekleyen push gider
        assert graph.patches == [("L1", "a", {"status": "completed"})]
        assert [link.pending_push for link in await links(test_session)] == [False]
        detail = await client.get(f"{API}/cards/{card['id']}", headers=auth_headers)
        assert detail.json()["data"]["status"] == "completed"

    async def test_move_to_done_list_is_pushed_and_reopen_too(
        self, client, auth_headers, graph, pushes
    ):
        card = await self._synced_card(client, auth_headers, graph)
        # Gelen Kutusu'nda "bitti" listesi yok; başka board'daki done listesine taşı
        board = await create_board(client, auth_headers, name="Hedef")
        done = next(lst for lst in board["lists"] if lst["is_done_list"])
        todo = next(lst for lst in board["lists"] if not lst["is_done_list"])
        await client.post(
            f"{API}/cards/{card['id']}/move",
            json={"list_id": done["id"], "index": 0},
            headers=auth_headers,
        )
        await client.post(
            f"{API}/cards/{card['id']}/move",
            json={"list_id": todo["id"], "index": 0},
            headers=auth_headers,
        )
        assert len(pushes) == 2
        await sync(client, auth_headers)
        # Son durum (yeniden açık) tek PATCH ile gönderilir
        assert graph.patches == [("L1", "a", {"status": "notStarted"})]

    async def test_pending_push_wins_over_remote_state(
        self, client, auth_headers, graph, pushes
    ):
        card = await self._synced_card(client, auth_headers, graph)
        await client.patch(
            f"{API}/cards/{card['id']}", json={"status": "completed"}, headers=auth_headers
        )
        # Geri yazma başarısız (bekliyor) ve uzakta görev "yeni sürüm, hâlâ açık" geliyor
        graph.fail_patch = True
        graph.delta["L1"] = [task("a", "Süt al", status="notStarted", version="v2")]
        await sync(client, auth_headers)
        assert graph.patches == [("L1", "a", {"status": "completed"})]  # önce push denendi
        detail = (await client.get(f"{API}/cards/{card['id']}", headers=auth_headers)).json()[
            "data"
        ]
        assert detail["status"] == "completed"  # yerel tamamlama uzak durumla ezilmedi
        assert detail["external"]["pending_push"] is True

        graph.fail_patch = False  # sonraki tur: push gider, kayıp yok
        await sync(client, auth_headers)
        assert graph.patches[-1] == ("L1", "a", {"status": "completed"})
        assert graph.tasks["L1"]["a"]["status"] == "completed"

    async def test_failed_push_is_retried_next_round(
        self, client, auth_headers, graph, pushes, test_session
    ):
        card = await self._synced_card(client, auth_headers, graph)
        await client.patch(
            f"{API}/cards/{card['id']}", json={"status": "completed"}, headers=auth_headers
        )
        graph.fail_patch = True
        res = await sync(client, auth_headers)
        assert res.status_code == 200
        assert res.json()["data"]["errors"]
        link = (await links(test_session))[0]
        assert link.pending_push is True and link.push_error
        status = (
            await client.get(f"{API}/integrations/microsoft/status", headers=auth_headers)
        ).json()["data"]
        assert status == {"pending_push": 1, "failed_push": 1}

        graph.fail_patch = False
        await sync(client, auth_headers)
        link = (await links(test_session))[0]
        assert link.pending_push is False and link.push_error is None
        assert graph.patches[-1] == ("L1", "a", {"status": "completed"})

    async def test_push_to_deleted_remote_task_is_dropped(
        self, client, auth_headers, graph, pushes, test_session
    ):
        card = await self._synced_card(client, auth_headers, graph)
        await client.patch(
            f"{API}/cards/{card['id']}", json={"status": "completed"}, headers=auth_headers
        )
        graph.missing_on_patch.add("a")
        await sync(client, auth_headers)
        link = (await links(test_session))[0]
        assert link.pending_push is False  # sonsuza dek denenmez
        assert "bulunamadı" in link.push_error

    async def test_push_now_sends_immediately(
        self, client, auth_headers, graph, pushes, test_session
    ):
        from app.db.unit_of_work import TaskUnitOfWork

        card = await self._synced_card(client, auth_headers, graph)
        await client.patch(
            f"{API}/cards/{card['id']}", json={"status": "completed"}, headers=auth_headers
        )
        user_id = pushes[0]
        await microsoft_todo.MicrosoftTodoService(TaskUnitOfWork(test_session)).push_now(
            user_id
        )
        assert graph.patches == [("L1", "a", {"status": "completed"})]
        assert [link.pending_push for link in await links(test_session)] == [False]

    async def test_echo_of_own_push_does_not_overwrite_local_edits(
        self, client, auth_headers, graph, pushes
    ):
        card = await self._synced_card(client, auth_headers, graph)
        await client.patch(
            f"{API}/cards/{card['id']}",
            json={"title": "Süt al (organik)", "status": "completed"},
            headers=auth_headers,
        )
        await sync(client, auth_headers)  # push gider
        # Graph aynı görevi yeni sürümle (tamamlanmış, eski başlıkla) yankılar
        graph.delta["L1"] = [task("a", "Süt al", status="completed", version="v2")]
        res = await sync(client, auth_headers)
        assert res.json()["data"]["updated"] == 0
        detail = (await client.get(f"{API}/cards/{card['id']}", headers=auth_headers)).json()[
            "data"
        ]
        assert detail["title"] == "Süt al (organik)"

    async def test_ai_actor_completion_is_pushed(
        self, client, auth_headers, graph, pushes
    ):
        card = await self._synced_card(client, auth_headers, graph)
        await client.patch(
            f"{API}/cards/{card['id']}",
            json={"status": "completed"},
            headers={**auth_headers, "X-Actor": "ai"},
        )
        assert len(pushes) == 1


class TestSettings:
    async def test_lists_endpoint_marks_selection(self, client, auth_headers, graph):
        await setup(client, auth_headers)
        res = await client.get(f"{API}/integrations/microsoft/lists", headers=auth_headers)
        assert [(lst["name"], lst["selected"]) for lst in res.json()["data"]] == [
            ("Hatırlatıcılar", True),
            ("Alışveriş", True),
        ]
        await client.put(
            f"{API}/integrations/microsoft/settings",
            json={"list_ids": ["L1"]},
            headers=auth_headers,
        )
        res = await client.get(f"{API}/integrations/microsoft/lists", headers=auth_headers)
        assert [lst["selected"] for lst in res.json()["data"]] == [True, False]

    async def test_only_selected_lists_sync_and_deselect_keeps_cards(
        self, client, auth_headers, graph, pushes, test_session
    ):
        graph.tasks["L1"] = {"a": task("a", "Süt al")}
        graph.tasks["L2"] = {"c": task("c", "Ekmek")}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        assert len(await inbox_cards(client, auth_headers)) == 2

        await client.put(
            f"{API}/integrations/microsoft/settings",
            json={"list_ids": ["L1"]},
            headers=auth_headers,
        )
        # L2'nin bağlantıları kalktı ama kart duruyor
        assert len(await inbox_cards(client, auth_headers)) == 2
        assert {link.external_parent_id for link in await links(test_session)} == {"L1"}
        graph.delta["L1"] = []
        graph.tasks["L2"]["d"] = task("d", "Yeni L2 işi")
        await sync(client, auth_headers)
        assert "Yeni L2 işi" not in {c["title"] for c in await inbox_cards(client, auth_headers)}

    async def test_empty_selection_is_rejected_on_sync(self, client, auth_headers, graph):
        await setup(client, auth_headers)
        await client.put(
            f"{API}/integrations/microsoft/settings",
            json={"list_ids": []},
            headers=auth_headers,
        )
        res = await sync(client, auth_headers)
        assert res.status_code == 422

    async def test_disconnect_keeps_cards_and_drops_links(
        self, client, auth_headers, graph, pushes, test_session
    ):
        graph.tasks["L1"] = {"a": task("a", "Süt al")}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        res = await client.delete(f"{API}/integrations/microsoft", headers=auth_headers)
        assert res.status_code == 204
        assert len(await inbox_cards(client, auth_headers)) == 1
        assert await links(test_session) == []

    async def test_other_user_is_isolated(
        self, client, auth_headers, other_headers, graph, pushes
    ):
        graph.tasks["L1"] = {"a": task("a", "Süt al")}
        await setup(client, auth_headers)
        await sync(client, auth_headers)
        res = await client.get(f"{API}/integrations/microsoft/lists", headers=other_headers)
        assert res.status_code == 404
        res = await client.get(f"{API}/integrations/microsoft/status", headers=other_headers)
        assert res.json()["data"] == {"pending_push": 0, "failed_push": 0}
        assert (await sync(client, other_headers)).status_code == 404

    async def test_requires_auth(self, client):
        res = await client.get(f"{API}/integrations/microsoft/lists")
        assert res.status_code in (401, 403)


class TestScheduler:
    async def test_run_once_includes_microsoft(self, monkeypatch):
        from app.integrations import scheduler

        called: list[str] = []

        async def fake_google():
            called.append("google")

        async def fake_microsoft():
            called.append("microsoft")
            raise RuntimeError("boom")  # biri patlasa döngü sürer

        monkeypatch.setattr("app.integrations.google_calendar.sync_all_accounts", fake_google)

        async def fake_calendar():
            called.append("takvim")

        monkeypatch.setattr("app.integrations.microsoft_todo.sync_all_accounts", fake_microsoft)
        monkeypatch.setattr("app.integrations.microsoft_calendar.sync_all_accounts", fake_calendar)
        await scheduler.run_once()
        assert called == ["google", "microsoft", "takvim"]
