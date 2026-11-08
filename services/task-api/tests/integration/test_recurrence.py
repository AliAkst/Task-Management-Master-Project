"""Faz 6c: tekrarlayan etkinlikler (RRULE) ve tekrarlayan kartlar (seriler)."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from app.core.exceptions import ValidationException
from app.services.recurrence import normalize_rule
from app.services.timeutil import local_today
from tests.integration.test_boards_cards import API, create_board, create_card

TZ = ZoneInfo("Europe/Istanbul")
TODAY = local_today(TZ)


def at(day, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(day, time(hh, mm), tzinfo=TZ)


def test_normalize_rule():
    assert (
        normalize_rule(" rrule:freq=weekly;byday=mo,we ") == "FREQ=WEEKLY;BYDAY=MO,WE"
    )
    assert normalize_rule("") is None and normalize_rule(None) is None
    for bad in ("FREQ=HOURLY", "FREQ=SOMETIMES", "BYDAY=MO", "FREQ=DAILY\nFREQ=DAILY"):
        with pytest.raises(ValidationException):
            normalize_rule(bad)


@pytest.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


@pytest.fixture
async def board(client: AsyncClient, auth_headers):
    return await create_board(client, auth_headers, name="Spor")


async def calendar(client, headers, start, end):
    res = await client.get(
        f"{API}/calendar",
        params={"start": start.isoformat(), "end": end.isoformat()},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return [i for i in res.json()["data"]["items"] if i["kind"] == "event"]


class TestRecurringEvents:
    async def test_weekly_event_expands_in_calendar(self, client, auth_headers, board):
        monday = TODAY - timedelta(days=TODAY.weekday())
        res = await client.post(
            f"{API}/events",
            json={
                "title": "Koşu",
                "start_at": at(monday, 7).isoformat(),
                "end_at": at(monday, 8).isoformat(),
                "board_id": board["board"]["id"],
                "recurrence_rule": "freq=weekly;byday=mo,we,fr",
            },
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
        event = res.json()["data"]
        assert event["recurrence_rule"] == "FREQ=WEEKLY;BYDAY=MO,WE,FR"

        items = await calendar(
            client, auth_headers, at(monday, 0), at(monday + timedelta(days=14), 0)
        )
        assert len(items) == 6
        assert len({i["id"] for i in items}) == 6  # takvimde benzersiz
        assert all(i["event_id"] == event["id"] for i in items)
        starts = [datetime.fromisoformat(i["start"]).astimezone(TZ) for i in items]
        assert [s.weekday() for s in starts[:3]] == [0, 2, 4]
        assert all(s.hour == 7 for s in starts)  # yerel saat korunur
        # Ilk tekrardan once baslayan aralikta hicbir sey yok
        assert (
            await calendar(
                client, auth_headers, at(monday - timedelta(days=7), 0), at(monday, 0)
            )
            == []
        )

        res = await client.patch(
            f"{API}/events/{event['id']}",
            json={"recurrence_rule": None},
            headers=auth_headers,
        )
        assert res.json()["data"]["recurrence_rule"] is None
        items = await calendar(
            client, auth_headers, at(monday, 0), at(monday + timedelta(days=14), 0)
        )
        assert len(items) == 1 and items[0]["id"] == f"event-{event['id']}"

    async def test_invalid_rule_rejected(self, client, auth_headers):
        res = await client.post(
            f"{API}/events",
            json={
                "title": "x",
                "start_at": at(TODAY, 7).isoformat(),
                "end_at": at(TODAY, 8).isoformat(),
                "recurrence_rule": "FREQ=MINUTELY",
            },
            headers=auth_headers,
        )
        assert res.status_code == 422

    async def test_daily_event_in_future_day_suggestions_and_plan(
        self, client, auth_headers
    ):
        start = TODAY - timedelta(days=3)
        res = await client.post(
            f"{API}/events",
            json={
                "title": "Meditasyon",
                "start_at": at(start, 6, 30).isoformat(),
                "end_at": at(start, 6, 50).isoformat(),
                "recurrence_rule": "FREQ=DAILY",
            },
            headers=auth_headers,
        )
        eid = res.json()["data"]["id"]
        tomorrow = TODAY + timedelta(days=1)
        res = await client.get(
            f"{API}/day-plans/{tomorrow}/suggestions", headers=auth_headers
        )
        sugg = [s for s in res.json()["data"]["items"] if s["event_id"] == eid]
        assert len(sugg) == 1 and sugg[0]["planned_minutes"] == 20
        assert datetime.fromisoformat(sugg[0]["planned_start"]) == at(tomorrow, 6, 30)

        res = await client.put(
            f"{API}/day-plans/{tomorrow}",
            json={"items": [{"event_id": eid}]},
            headers=auth_headers,
        )
        item = res.json()["data"]["items"][0]
        assert datetime.fromisoformat(item["planned_start"]) == at(tomorrow, 6, 30)


class TestRecurringCards:
    async def test_completing_creates_next_once(self, client, auth_headers, board):
        lists = board["lists"]
        todo = next(x for x in lists if not x["is_done_list"])
        card = await create_card(
            client,
            auth_headers,
            todo["id"],
            "Koşu",
            due_date=at(TODAY - timedelta(days=1), 18).isoformat(),
            estimated_minutes=45,
        )
        await client.post(
            f"{API}/cards/{card['id']}/checklist",
            json={"text": "Isın"},
            headers=auth_headers,
        )
        res = await client.put(
            f"{API}/cards/{card['id']}/recurrence",
            json={"rule": "FREQ=DAILY"},
            headers=auth_headers,
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["recurrence_rule"] == "FREQ=DAILY" and data["series_index"] == 1
        series_id = data["series_id"]

        async def complete(cid):
            r = await client.patch(
                f"{API}/cards/{cid}", json={"status": "completed"}, headers=auth_headers
            )
            assert r.status_code == 200, r.text

        async def series_cards():
            r = await client.get(
                f"{API}/boards/{board['board']['id']}", headers=auth_headers
            )
            return sorted(
                (c for c in r.json()["data"]["cards"] if c["series_id"] == series_id),
                key=lambda c: c["series_index"],
            )

        await complete(card["id"])
        cards = await series_cards()
        assert [c["series_index"] for c in cards] == [1, 2]
        nxt = cards[1]
        assert nxt["status"] == "pending" and nxt["list_id"] == todo["id"]
        assert nxt["estimated_minutes"] == 45 and nxt["series_done_count"] == 1
        due = datetime.fromisoformat(nxt["due_date"]).astimezone(TZ)
        assert due.hour == 18 and due > datetime.now(UTC)
        assert due - datetime.now(UTC) <= timedelta(days=1)  # kacirilan gunler atlanir
        detail = (
            await client.get(f"{API}/cards/{nxt['id']}", headers=auth_headers)
        ).json()["data"]
        assert [(i["text"], i["is_done"]) for i in detail["checklist"]] == [
            ("Isın", False)
        ]

        # Yeniden ac + tamamla: ikinci kopya olusmaz
        await client.patch(
            f"{API}/cards/{card['id']}",
            json={"status": "pending"},
            headers=auth_headers,
        )
        await complete(card["id"])
        assert len(await series_cards()) == 2

        # Tekrari durdur: siradaki tamamlaninca yenisi acilmaz, seri sayaci kalir
        res = await client.put(
            f"{API}/cards/{nxt['id']}/recurrence",
            json={"rule": None},
            headers=auth_headers,
        )
        assert res.json()["data"]["recurrence_rule"] is None
        await complete(nxt["id"])
        cards = await series_cards()
        assert len(cards) == 2 and cards[1]["series_done_count"] == 2

    async def test_until_rule_ends_series(self, client, auth_headers, board):
        todo = next(x for x in board["lists"] if not x["is_done_list"])
        card = await create_card(
            client,
            auth_headers,
            todo["id"],
            "Kurs",
            due_date=at(TODAY - timedelta(days=2), 9).isoformat(),
        )
        until = (TODAY - timedelta(days=1)).strftime("%Y%m%d")
        await client.put(
            f"{API}/cards/{card['id']}/recurrence",
            json={"rule": f"FREQ=DAILY;UNTIL={until}T235959"},
            headers=auth_headers,
        )
        await client.patch(
            f"{API}/cards/{card['id']}",
            json={"status": "completed"},
            headers=auth_headers,
        )
        detail = (
            await client.get(f"{API}/cards/{card['id']}", headers=auth_headers)
        ).json()["data"]
        assert detail["recurrence_rule"] is None  # kural bitti, seri durdu

    async def test_recurrence_validation_and_ownership(
        self, client, auth_headers, board, other_headers
    ):
        todo = next(x for x in board["lists"] if not x["is_done_list"])
        card = await create_card(client, auth_headers, todo["id"], "X")
        res = await client.put(
            f"{API}/cards/{card['id']}/recurrence",
            json={"rule": "FREQ=SECONDLY"},
            headers=auth_headers,
        )
        assert res.status_code == 422
        res = await client.put(
            f"{API}/cards/{card['id']}/recurrence",
            json={"rule": "FREQ=DAILY"},
            headers=other_headers,
        )
        assert res.status_code == 404
