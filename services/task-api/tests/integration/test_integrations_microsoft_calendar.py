"""Faz 8d: Microsoft (Outlook/Teams) takvim senkronu (MockTransport, gercek ag yok)."""

import base64
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.db.entities import (
    EventEntity,
    ExternalLinkEntity,
    IntegrationAccountEntity,
    TaskEntity,
)
from app.integrations.microsoft_calendar import (
    consent_required,
    is_teams,
    map_event,
    week_window,
)
from tests.integration.test_boards_cards import API, create_board

BASE = "https://graph.microsoft.com/v1.0"
FULL_SCOPE = "User.Read Tasks.ReadWrite Calendars.Read openid email profile"
OLD_SCOPE = "User.Read Tasks.ReadWrite openid email profile"

NOW = datetime.now(UTC).replace(microsecond=0)
TOMORROW = NOW + timedelta(days=1)
IST = ZoneInfo("Europe/Istanbul")


def _id_token(username: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"preferred_username": username}).encode()
    ).decode()
    return f"x.{payload.rstrip('=')}.y"


def _gdt(dt: datetime) -> dict:
    return {"dateTime": dt.strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"}


def meeting(
    mid,
    subject,
    at,
    hours=1,
    change="c1",
    *,
    provider="teamsForBusiness",
    online=True,
    join=True,
    **extra,
):
    item = {
        "id": mid,
        "changeKey": change,
        "subject": subject,
        "start": _gdt(at),
        "end": _gdt(at + timedelta(hours=hours)),
        "isAllDay": False,
        "isCancelled": False,
        "isOnlineMeeting": online,
        "onlineMeetingProvider": provider if online else "unknown",
        "webLink": f"https://outlook.live.com/calendar/item/{mid}",
        "location": {"displayName": ""},
        "onlineMeeting": {"joinUrl": f"https://teams.live.com/meet/{mid}"}
        if join and online
        else None,
        **extra,
    }
    return item


class FakeGraph:
    """Microsoft token ucu + Graph calendarView (ve To Do listesi) taklidi."""

    def __init__(self):
        self.scope = FULL_SCOPE
        self.items: list[dict] = []
        self.page_size: int | None = None
        self.forbidden = False
        self.unauthorized = False
        self.revoked = False
        self.view_requests: list[httpx.Request] = []
        self.todo_tasks: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.host == "login.microsoftonline.com":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            if form["grant_type"] == "authorization_code":
                return httpx.Response(
                    200,
                    json={
                        "access_token": "at-1",
                        "refresh_token": "rt-1",
                        "expires_in": 3600,
                        "scope": self.scope,
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
            return httpx.Response(200, json={"value": [{"id": "L1", "displayName": "Liste"}]})
        if path.endswith("/tasks/delta"):
            return httpx.Response(
                200,
                json={
                    "value": self.todo_tasks,
                    "@odata.deltaLink": f"{BASE}{path}?$deltatoken=d1",
                },
            )

        assert path == "/me/calendarView", path
        self.view_requests.append(request)
        if self.unauthorized:
            return httpx.Response(401)
        if self.forbidden:
            return httpx.Response(403)
        skip = int(url.params.get("$skiptoken", 0))
        if self.page_size is None:
            return httpx.Response(200, json={"value": self.items})
        page = self.items[skip : skip + self.page_size]
        body: dict = {"value": page}
        if skip + self.page_size < len(self.items):
            body["@odata.nextLink"] = (
                f"{BASE}/me/calendarView?$skiptoken={skip + self.page_size}"
            )
        return httpx.Response(200, json=body)


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
async def other_headers(client):
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def connect(client, headers, code="good-code"):
    res = await client.post(f"{API}/integrations/microsoft/connect", headers=headers)
    assert res.status_code == 200, res.text
    state = parse_qs(urlparse(res.json()["data"]["authorize_url"]).query)["state"][0]
    cb = await client.get(
        f"{API}/integrations/microsoft/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )
    assert "connected=microsoft" in cb.headers["location"], cb.headers["location"]


async def put_calendar(client, headers, **body):
    payload = {"enabled": True, "teams_only": True, "weeks_ahead": 2, **body}
    return await client.put(
        f"{API}/integrations/microsoft/calendar", json=payload, headers=headers
    )


async def setup(client, headers, **body):
    await connect(client, headers)
    res = await put_calendar(client, headers, **body)
    assert res.status_code == 200, res.text
    return res


async def cal_sync(client, headers):
    return await client.post(
        f"{API}/integrations/microsoft/calendar/sync", headers=headers
    )


async def calendar_items(client, headers):
    res = await client.get(
        f"{API}/calendar",
        params={
            "start": (NOW - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": (NOW + timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return [i for i in res.json()["data"]["items"] if i["kind"] == "event"]


async def events_in_db(test_session) -> list[EventEntity]:
    test_session.expire_all()
    return list((await test_session.execute(select(EventEntity))).scalars().all())


# ====================================================================
# Saf fonksiyonlar
# ====================================================================
class TestWeekWindow:
    # 2026-11-11 Carsamba 10:00 UTC (Istanbul 13:00)
    NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)

    def test_monday_start(self):
        start, end = week_window(self.NOW, IST, 0, 2)
        # Pazartesi 2026-11-09 00:00 Istanbul (+03:00) = 08-11 21:00 UTC
        assert start == datetime(2026, 11, 8, 21, 0, tzinfo=UTC)
        assert end == start + timedelta(days=21)

    def test_sunday_start(self):
        start, end = week_window(self.NOW, IST, 6, 1)
        # Pazar 2026-11-08 00:00 Istanbul
        assert start == datetime(2026, 11, 7, 21, 0, tzinfo=UTC)
        assert end == start + timedelta(days=14)

    def test_timezone_changes_local_day(self):
        # UTC Pazartesi 22:00 = Istanbul Sali 01:00; hafta basi yine o Pazartesi
        now = datetime(2026, 11, 9, 22, 0, tzinfo=UTC)
        start, _ = week_window(now, IST, 0, 1)
        assert start == datetime(2026, 11, 8, 21, 0, tzinfo=UTC)
        # Pazartesi 22:00 UTC, UTC'de hala Pazartesi: hafta basi 9 Kasim 00:00 UTC
        start_utc, _ = week_window(now, ZoneInfo("UTC"), 0, 1)
        assert start_utc == datetime(2026, 11, 9, 0, 0, tzinfo=UTC)

    def test_weeks_ahead_extends_end(self):
        s1, e1 = week_window(self.NOW, IST, 0, 1)
        s4, e4 = week_window(self.NOW, IST, 0, 4)
        assert s1 == s4 and e4 - e1 == timedelta(days=21)


class TestTeamsDetection:
    def test_provider_values(self):
        for provider in ("teamsForBusiness", "skypeForConsumer", "skypeForBusiness"):
            assert is_teams({"isOnlineMeeting": True, "onlineMeetingProvider": provider})

    def test_join_url_host(self):
        for host in ("teams.live.com", "teams.microsoft.com"):
            item = {
                "isOnlineMeeting": True,
                "onlineMeetingProvider": "unknown",
                "onlineMeeting": {"joinUrl": f"https://{host}/l/meetup-join/x"},
            }
            assert is_teams(item)

    def test_not_online_or_other_provider(self):
        assert not is_teams({"isOnlineMeeting": False, "onlineMeetingProvider": "teamsForBusiness"})
        assert not is_teams({"isOnlineMeeting": True, "onlineMeetingProvider": "unknown"})
        assert not is_teams({})


class TestMapping:
    def test_untitled_location_and_join_url(self):
        item = meeting("a", "  ", TOMORROW, location={"displayName": " Oda 4 "})
        mapped = map_event(item, IST)
        assert mapped.title == "(Başlıksız toplantı)"
        assert mapped.location == "Oda 4"
        assert mapped.meeting_url == "https://teams.live.com/meet/a"
        assert mapped.url == "https://outlook.live.com/calendar/item/a"
        assert not mapped.all_day
        assert mapped.start_at == TOMORROW

    def test_all_day_is_local_midnight_exclusive_end(self):
        item = meeting(
            "d",
            "Tatil",
            TOMORROW,
            isAllDay=True,
            start={"dateTime": "2026-11-10T00:00:00.0000000", "timeZone": "UTC"},
            end={"dateTime": "2026-11-11T00:00:00.0000000", "timeZone": "UTC"},
        )
        mapped = map_event(item, IST)
        assert mapped.all_day
        assert mapped.start_at == datetime(2026, 11, 9, 21, 0, tzinfo=UTC)
        assert mapped.end_at == datetime(2026, 11, 10, 21, 0, tzinfo=UTC)

    def test_zero_duration_and_missing_start(self):
        item = meeting("z", "Sifir", TOMORROW, hours=0)
        assert map_event(item, IST).end_at - TOMORROW == timedelta(minutes=30)
        assert map_event({"id": "x", "subject": "?"}, IST) is None


# ====================================================================
# OAuth / izin
# ====================================================================
class TestConsent:
    async def test_authorize_url_requests_calendar_scope(self, client, auth_headers, graph):
        res = await client.post(f"{API}/integrations/microsoft/connect", headers=auth_headers)
        q = parse_qs(urlparse(res.json()["data"]["authorize_url"]).query)
        assert "Calendars.Read" in q["scope"][0].split()
        assert "prompt" not in q  # ilk baglanti: normal akis

    async def test_account_reports_consent_and_defaults(self, client, auth_headers, graph):
        await connect(client, auth_headers)
        data = (await client.get(f"{API}/integrations", headers=auth_headers)).json()["data"]
        ms = next(a for a in data if a["provider"] == "microsoft")
        assert ms["calendar_consent"] is True
        assert ms["settings"]["calendar"] == {
            "enabled": False,
            "teams_only": True,
            "board_id": None,
            "weeks_ahead": 2,
        }

    async def test_missing_scope_blocks_calendar_but_not_todo(
        self, client, auth_headers, graph
    ):
        graph.scope = OLD_SCOPE
        await connect(client, auth_headers)
        ms = next(
            a
            for a in (await client.get(f"{API}/integrations", headers=auth_headers)).json()[
                "data"
            ]
            if a["provider"] == "microsoft"
        )
        assert ms["calendar_consent"] is False

        res = await put_calendar(client, auth_headers)
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "CALENDAR_CONSENT_REQUIRED"
        assert (await cal_sync(client, auth_headers)).status_code == 409
        # To Do calismaya devam eder, hesap error'a dusmez
        todo = await client.post(f"{API}/integrations/microsoft/sync", headers=auth_headers)
        assert todo.status_code == 200, todo.text
        ms = next(
            a
            for a in (await client.get(f"{API}/integrations", headers=auth_headers)).json()[
                "data"
            ]
            if a["provider"] == "microsoft"
        )
        assert ms["status"] == "active"

    async def test_reconnect_without_consent_forces_prompt(self, client, auth_headers, graph):
        graph.scope = OLD_SCOPE
        await connect(client, auth_headers)
        res = await client.post(f"{API}/integrations/microsoft/connect", headers=auth_headers)
        q = parse_qs(urlparse(res.json()["data"]["authorize_url"]).query)
        assert q["prompt"] == ["consent"]
        graph.scope = FULL_SCOPE
        await connect(client, auth_headers)
        assert (await put_calendar(client, auth_headers)).status_code == 200

    async def test_graph_403_maps_to_consent_required(self, client, auth_headers, graph):
        await setup(client, auth_headers)
        graph.forbidden = True
        res = await cal_sync(client, auth_headers)
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "CALENDAR_CONSENT_REQUIRED"
        assert consent_required().error_code == "CALENDAR_CONSENT_REQUIRED"


# ====================================================================
# Senkron
# ====================================================================
class TestSync:
    async def test_enable_syncs_immediately_with_meeting_url(
        self, client, auth_headers, graph
    ):
        graph.items = [meeting("m1", "Haftalık toplantı", TOMORROW)]
        await setup(client, auth_headers)
        items = await calendar_items(client, auth_headers)
        assert len(items) == 1
        item = items[0]
        assert item["title"] == "Haftalık toplantı"
        assert item["meeting_url"] == "https://teams.live.com/meet/m1"
        assert item["external"]["provider"] == "microsoft"
        assert item["external"]["url"].startswith("https://outlook.live.com/")
        detail = await client.get(
            f"{API}/events/{item['event_id']}", headers=auth_headers
        )
        assert detail.json()["data"]["meeting_url"] == "https://teams.live.com/meet/m1"

    async def test_request_window_headers_and_select(self, client, auth_headers, graph):
        await setup(client, auth_headers)
        req = graph.view_requests[-1]
        params = dict(req.url.params)
        assert req.headers["prefer"] == 'outlook.timezone="UTC"'
        assert params["$top"] == "100"
        assert "onlineMeeting" in params["$select"] and "changeKey" in params["$select"]
        start = datetime.fromisoformat(params["startDateTime"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(params["endDateTime"].replace("Z", "+00:00"))
        assert start <= NOW + timedelta(seconds=5) and NOW - start < timedelta(days=7, hours=3)
        assert end - start == timedelta(days=21) or timedelta(days=20, hours=23) <= end - start

    async def test_pagination_follows_next_link(self, client, auth_headers, graph):
        graph.page_size = 2
        graph.items = [
            meeting(f"m{i}", f"Toplantı {i}", TOMORROW + timedelta(hours=i)) for i in range(5)
        ]
        await setup(client, auth_headers)
        assert len(await calendar_items(client, auth_headers)) == 5
        assert len(graph.view_requests) == 3

    async def test_teams_only_filter(self, client, auth_headers, graph):
        graph.items = [
            meeting("t", "Teams", TOMORROW),
            meeting("o", "Düz randevu", TOMORROW, online=False, join=False),
            meeting("z", "Başka", TOMORROW, provider="unknown", join=False),
        ]
        await setup(client, auth_headers)
        assert [i["title"] for i in await calendar_items(client, auth_headers)] == ["Teams"]

        # teams_only=false: online olmayan randevu da gelir; Teams olmayan kalan 'unknown' online
        res = await put_calendar(client, auth_headers, teams_only=False)
        assert res.status_code == 200
        titles = sorted(i["title"] for i in await calendar_items(client, auth_headers))
        assert titles == ["Başka", "Düz randevu", "Teams"]

        # tekrar acik: Teams olmayanlar silinir
        await put_calendar(client, auth_headers, teams_only=True)
        assert [i["title"] for i in await calendar_items(client, auth_headers)] == ["Teams"]

    async def test_cancelled_is_removed(self, client, auth_headers, graph):
        graph.items = [meeting("m1", "Silinecek", TOMORROW), meeting("m2", "Kalır", TOMORROW)]
        await setup(client, auth_headers)
        graph.items[0]["isCancelled"] = True
        body = (await cal_sync(client, auth_headers)).json()["data"]
        assert body["removed"] == 1
        assert [i["title"] for i in await calendar_items(client, auth_headers)] == ["Kalır"]

    async def test_dropped_from_window_deleted_past_untouched(
        self, client, auth_headers, graph, test_session
    ):
        past = NOW - timedelta(days=30)
        graph.items = [
            meeting("old", "Geçmiş", past),
            meeting("gone", "Kaybolacak", TOMORROW),
            meeting("stay", "Kalacak", TOMORROW),
        ]
        await setup(client, auth_headers)
        assert len(await calendar_items(client, auth_headers)) == 3
        # Pencere artik gecmisi/kayboleni donmuyor
        graph.items = [meeting("stay", "Kalacak", TOMORROW)]
        body = (await cal_sync(client, auth_headers)).json()["data"]
        assert body["removed"] == 1
        titles = sorted(i["title"] for i in await calendar_items(client, auth_headers))
        assert titles == ["Geçmiş", "Kalacak"]

    async def test_all_day_event(self, client, auth_headers, graph):
        day = (NOW + timedelta(days=2)).date()
        graph.items = [
            meeting(
                "ad",
                "Konferans",
                TOMORROW,
                isAllDay=True,
                start={"dateTime": f"{day.isoformat()}T00:00:00.0000000", "timeZone": "UTC"},
                end={
                    "dateTime": f"{(day + timedelta(days=1)).isoformat()}T00:00:00.0000000",
                    "timeZone": "UTC",
                },
            )
        ]
        await setup(client, auth_headers)
        (item,) = await calendar_items(client, auth_headers)
        assert item["all_day"] is True

    async def test_recurring_instances_are_separate_rows(
        self, client, auth_headers, graph, test_session
    ):
        graph.items = [
            meeting(f"occ{i}", "Haftalık", TOMORROW + timedelta(days=7 * i), change="c")
            for i in range(3)
        ]
        await setup(client, auth_headers)
        assert len(await events_in_db(test_session)) == 3
        assert all(e.recurrence_rule is None for e in await events_in_db(test_session))

    async def test_same_change_key_skips_changed_updates(self, client, auth_headers, graph):
        graph.items = [meeting("m1", "İlk", TOMORROW, change="c1")]
        await setup(client, auth_headers)
        again = (await cal_sync(client, auth_headers)).json()["data"]
        assert again["created"] == 0 and again["updated"] == 0

        graph.items = [meeting("m1", "Yeni ad", TOMORROW, change="c1")]
        assert (await cal_sync(client, auth_headers)).json()["data"]["updated"] == 0
        graph.items = [meeting("m1", "Yeni ad", TOMORROW, change="c2")]
        assert (await cal_sync(client, auth_headers)).json()["data"]["updated"] == 1
        assert [i["title"] for i in await calendar_items(client, auth_headers)] == ["Yeni ad"]

    async def test_board_move(self, client, auth_headers, graph):
        board = await create_board(client, auth_headers, name="İş")
        graph.items = [meeting("m1", "Toplantı", TOMORROW)]
        await setup(client, auth_headers)
        assert (await calendar_items(client, auth_headers))[0]["board_id"] is None
        res = await put_calendar(client, auth_headers, board_id=board["board"]["id"])
        assert res.status_code == 200
        assert (await calendar_items(client, auth_headers))[0]["board_id"] == board["board"]["id"]

    async def test_foreign_board_rejected(self, client, auth_headers, other_headers, graph):
        foreign = await create_board(client, other_headers, name="Başkası")
        await connect(client, auth_headers)
        res = await put_calendar(client, auth_headers, board_id=foreign["board"]["id"])
        assert res.status_code in (403, 404)

    async def test_weeks_ahead_validation(self, client, auth_headers, graph):
        await connect(client, auth_headers)
        assert (await put_calendar(client, auth_headers, weeks_ahead=0)).status_code == 422
        assert (await put_calendar(client, auth_headers, weeks_ahead=9)).status_code == 422
        assert (await put_calendar(client, auth_headers, weeks_ahead=8)).status_code == 200

    async def test_manual_sync_requires_enabled(self, client, auth_headers, graph):
        await connect(client, auth_headers)
        res = await cal_sync(client, auth_headers)
        assert res.status_code == 422

    async def test_last_sync_recorded_in_settings(self, client, auth_headers, graph):
        res = await setup(client, auth_headers)
        cal = res.json()["data"]["settings"]["calendar"]
        assert cal["last_synced_at"] and cal["last_error"] is None
        assert cal["enabled"] is True


# ====================================================================
# Kapatma / baglanti kesme / salt okunur / yalitim
# ====================================================================
class TestLifecycle:
    async def _todo_card(self, client, headers, graph):
        graph.todo_tasks = [
            {
                "id": "task-1",
                "@odata.etag": "v1",
                "title": "Süt al",
                "status": "notStarted",
                "importance": "normal",
            }
        ]
        res = await client.post(f"{API}/integrations/microsoft/sync", headers=headers)
        assert res.status_code == 200, res.text

    async def _todo_cards(self, test_session) -> list[TaskEntity]:
        test_session.expire_all()
        rows = await test_session.execute(select(TaskEntity).where(TaskEntity.title == "Süt al"))
        return list(rows.scalars().all())

    async def test_disable_deletes_events_keeps_todo_cards(
        self, client, auth_headers, graph, test_session
    ):
        graph.items = [meeting("m1", "Toplantı", TOMORROW)]
        await setup(client, auth_headers)
        await self._todo_card(client, auth_headers, graph)
        assert len(await events_in_db(test_session)) == 1

        res = await put_calendar(client, auth_headers, enabled=False)
        assert res.status_code == 200
        assert await events_in_db(test_session) == []
        assert len(await self._todo_cards(test_session)) == 1
        test_session.expire_all()
        kinds = {
            link.entity_type
            for link in (await test_session.execute(select(ExternalLinkEntity))).scalars()
        }
        assert kinds == {"card"}

    async def test_disconnect_deletes_events_keeps_todo_cards(
        self, client, auth_headers, graph, test_session
    ):
        graph.items = [meeting("m1", "Toplantı", TOMORROW)]
        await setup(client, auth_headers)
        await self._todo_card(client, auth_headers, graph)
        res = await client.delete(f"{API}/integrations/microsoft", headers=auth_headers)
        assert res.status_code == 204
        assert await events_in_db(test_session) == []
        assert len(await self._todo_cards(test_session)) == 1
        test_session.expire_all()
        accounts = (await test_session.execute(select(IntegrationAccountEntity))).scalars().all()
        assert list(accounts) == []

    async def test_events_are_read_only(self, client, auth_headers, graph):
        graph.items = [meeting("m1", "Toplantı", TOMORROW)]
        await setup(client, auth_headers)
        eid = (await calendar_items(client, auth_headers))[0]["event_id"]
        patch = await client.patch(
            f"{API}/events/{eid}", json={"title": "Değiş"}, headers=auth_headers
        )
        assert patch.status_code == 409
        assert patch.json()["error"]["code"] == "EVENT_READ_ONLY"
        assert "Outlook" in patch.json()["error"]["message"]
        delete = await client.delete(f"{API}/events/{eid}", headers=auth_headers)
        assert delete.status_code == 409

    async def test_user_isolation(self, client, auth_headers, other_headers, graph):
        graph.items = [meeting("m1", "Özel", TOMORROW)]
        await setup(client, auth_headers)
        assert await calendar_items(client, other_headers) == []
        assert (await cal_sync(client, other_headers)).status_code == 404
        assert (await put_calendar(client, other_headers)).status_code == 404

    async def test_graph_401_marks_account_for_reconnect(
        self, client, auth_headers, graph
    ):
        await setup(client, auth_headers)
        graph.unauthorized = True
        res = await cal_sync(client, auth_headers)
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "INTEGRATION_RECONNECT"
        data = (await client.get(f"{API}/integrations", headers=auth_headers)).json()["data"]
        assert next(a for a in data if a["provider"] == "microsoft")["status"] == "error"


class TestScheduler:
    async def test_run_once_order_and_isolation(self, monkeypatch):
        from app.integrations import scheduler

        called: list[str] = []

        async def fake_google():
            called.append("google")

        async def fake_todo():
            called.append("todo")
            raise RuntimeError("boom")  # biri patlasa dongu surer

        async def fake_calendar():
            called.append("takvim")

        monkeypatch.setattr("app.integrations.google_calendar.sync_all_accounts", fake_google)
        monkeypatch.setattr("app.integrations.microsoft_todo.sync_all_accounts", fake_todo)
        monkeypatch.setattr("app.integrations.microsoft_calendar.sync_all_accounts", fake_calendar)
        await scheduler.run_once()
        assert called == ["google", "todo", "takvim"]
