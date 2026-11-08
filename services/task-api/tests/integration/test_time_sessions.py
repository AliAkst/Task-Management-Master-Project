"""Faz 3a: kronometre ve elle girilen calisma sureleri."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.integration.test_boards_cards import API, create_board, create_card

T0 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)


class Clock:
    """Servisin 'simdi'sini kontrol eden sahte saat."""

    def __init__(self) -> None:
        self.now = T0

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


@pytest.fixture
def clock(monkeypatch) -> Clock:
    c = Clock()
    monkeypatch.setattr("app.services.time_session._now", lambda: c.now)
    return c


@pytest.fixture
async def board(client: AsyncClient, auth_headers):
    return await create_board(client, auth_headers, name="Eğitimler")


@pytest.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def start(client, headers, **body):
    res = await client.post(f"{API}/sessions/start", json=body, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def stop(client, headers):
    res = await client.post(f"{API}/sessions/stop", json={}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def active(client, headers):
    res = await client.get(f"{API}/sessions/active", headers=headers)
    return res.json()["data"]["session"]


def iso(dt: datetime) -> str:
    return dt.isoformat()


class TestStopwatch:
    async def test_start_stop_measures_duration(
        self, client, auth_headers, board, clock
    ):
        card = await create_card(
            client, auth_headers, board["lists"][0]["id"], "Bölüm 1"
        )
        s = await start(client, auth_headers, card_id=card["id"])
        assert s["is_running"] is True
        assert s["card_title"] == "Bölüm 1"
        assert s["board_id"] == board["board"]["id"]
        assert (await active(client, auth_headers))["id"] == s["id"]

        clock.advance(minutes=30)
        done = await stop(client, auth_headers)
        assert done["is_running"] is False
        assert done["duration_sec"] == 1800
        assert await active(client, auth_headers) is None

        res = await client.get(f"{API}/cards/{card['id']}", headers=auth_headers)
        assert res.json()["data"]["tracked_seconds"] == 1800

    async def test_starting_new_stops_running(self, client, auth_headers, board, clock):
        a = await create_card(client, auth_headers, board["lists"][0]["id"], "A")
        b = await create_card(client, auth_headers, board["lists"][0]["id"], "B")
        first = await start(client, auth_headers, card_id=a["id"])
        clock.advance(minutes=10)
        second = await start(client, auth_headers, card_id=b["id"])

        assert (await active(client, auth_headers))["id"] == second["id"]
        res = await client.get(f"{API}/sessions", headers=auth_headers)
        by_id = {s["id"]: s for s in res.json()["data"]}
        assert by_id[first["id"]]["duration_sec"] == 600
        assert by_id[first["id"]]["is_running"] is False

    async def test_free_session_without_card(self, client, auth_headers, clock):
        s = await start(client, auth_headers, note="Odaklanma")
        assert s["card_id"] is None and s["board_id"] is None
        clock.advance(minutes=5)
        assert (await stop(client, auth_headers))["duration_sec"] == 300

    async def test_stop_without_running_is_conflict(self, client, auth_headers):
        res = await client.post(f"{API}/sessions/stop", json={}, headers=auth_headers)
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "NO_ACTIVE_SESSION"

    async def test_subtask_time_rolls_up_to_parent(
        self, client, auth_headers, board, clock
    ):
        parent = await create_card(
            client, auth_headers, board["lists"][0]["id"], "Kurs"
        )
        res = await client.post(
            f"{API}/cards/{parent['id']}/split",
            json={"parts": 2, "chain": False},
            headers=auth_headers,
        )
        subs = res.json()["data"]["subtasks"]
        for sub, minutes in zip(subs, (20, 40), strict=True):
            await start(client, auth_headers, card_id=sub["id"])
            clock.advance(minutes=minutes)
        await stop(client, auth_headers)

        res = await client.get(f"{API}/cards/{parent['id']}", headers=auth_headers)
        detail = res.json()["data"]
        assert detail["tracked_seconds"] == 0
        assert detail["subtask_tracked_seconds"] == 3600


class TestManualEntries:
    async def test_manual_entry_and_overlap(self, client, auth_headers, board, clock):
        card = await create_card(client, auth_headers, board["lists"][0]["id"], "Koşu")
        body = {
            "card_id": card["id"],
            "started_at": iso(T0 - timedelta(hours=3)),
            "ended_at": iso(T0 - timedelta(hours=2)),
            "note": "saymayı unuttum",
        }
        res = await client.post(f"{API}/sessions", json=body, headers=auth_headers)
        assert res.status_code == 201, res.text
        assert res.json()["data"]["source"] == "manual"
        assert res.json()["data"]["duration_sec"] == 3600

        # Kesisen ikinci giris reddedilir (sure iki kez sayilmasin)
        body2 = {
            "started_at": iso(T0 - timedelta(hours=2, minutes=30)),
            "ended_at": iso(T0 - timedelta(hours=1)),
        }
        res = await client.post(f"{API}/sessions", json=body2, headers=auth_headers)
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "SESSION_OVERLAP"

        # Bitisik (tam bitis aninda baslayan) giris kabul edilir
        body3 = {
            "started_at": body["ended_at"],
            "ended_at": iso(T0 - timedelta(hours=1)),
        }
        res = await client.post(f"{API}/sessions", json=body3, headers=auth_headers)
        assert res.status_code == 201

    async def test_manual_overlapping_running_timer(self, client, auth_headers, clock):
        await start(client, auth_headers)  # T0'da basladi, hala calisiyor
        clock.advance(hours=1)
        body = {
            "started_at": iso(T0 + timedelta(minutes=10)),
            "ended_at": iso(T0 + timedelta(minutes=20)),
        }
        res = await client.post(f"{API}/sessions", json=body, headers=auth_headers)
        assert res.status_code == 409

    @pytest.mark.parametrize(
        ("start_off", "end_off", "code"),
        [
            (timedelta(hours=-1), timedelta(hours=-2), 422),  # ters aralik
            (timedelta(hours=-1), timedelta(hours=2), 422),  # gelecege tasiyor
            (timedelta(hours=-30), timedelta(hours=-1), 422),  # 24 saatten uzun
        ],
    )
    async def test_validation(
        self, client, auth_headers, clock, start_off, end_off, code
    ):
        body = {"started_at": iso(T0 + start_off), "ended_at": iso(T0 + end_off)}
        res = await client.post(f"{API}/sessions", json=body, headers=auth_headers)
        assert res.status_code == code

    async def test_edit_finished_session_recomputes(self, client, auth_headers, clock):
        s = await start(client, auth_headers)
        clock.advance(minutes=30)
        await stop(client, auth_headers)
        res = await client.patch(
            f"{API}/sessions/{s['id']}",
            json={"ended_at": iso(T0 + timedelta(minutes=45))},
            headers=auth_headers,
        )
        # 09:45 > simdi(09:30) -> gelecek, reddedilir
        assert res.status_code == 422
        res = await client.patch(
            f"{API}/sessions/{s['id']}",
            json={"started_at": iso(T0 - timedelta(minutes=15))},
            headers=auth_headers,
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["duration_sec"] == 45 * 60

    async def test_running_session_times_are_locked(self, client, auth_headers, clock):
        s = await start(client, auth_headers)
        res = await client.patch(
            f"{API}/sessions/{s['id']}",
            json={"started_at": iso(T0 - timedelta(minutes=5))},
            headers=auth_headers,
        )
        assert res.status_code == 422
        res = await client.patch(
            f"{API}/sessions/{s['id']}",
            json={"note": "derin odak"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["data"]["note"] == "derin odak"


class TestHistoryIsKept:
    async def test_deleting_card_keeps_session_snapshot(
        self, client, auth_headers, board, clock
    ):
        card = await create_card(
            client, auth_headers, board["lists"][0]["id"], "Silinecek"
        )
        await start(client, auth_headers, card_id=card["id"])
        clock.advance(minutes=15)
        await stop(client, auth_headers)
        await client.delete(f"{API}/cards/{card['id']}", headers=auth_headers)

        [s] = (await client.get(f"{API}/sessions", headers=auth_headers)).json()["data"]
        assert s["card_id"] is None
        assert s["card_title"] == "Silinecek"
        assert s["board_id"] == board["board"]["id"]
        assert s["duration_sec"] == 900

    async def test_list_filters(self, client, auth_headers, board, clock):
        a = await create_card(client, auth_headers, board["lists"][0]["id"], "A")
        await start(client, auth_headers, card_id=a["id"])
        clock.advance(hours=1)
        await start(client, auth_headers)  # serbest
        clock.advance(hours=1)
        await stop(client, auth_headers)

        res = await client.get(
            f"{API}/sessions", params={"card_id": a["id"]}, headers=auth_headers
        )
        assert [s["card_id"] for s in res.json()["data"]] == [a["id"]]
        res = await client.get(
            f"{API}/sessions",
            params={"start": iso(T0 + timedelta(hours=1, minutes=30))},
            headers=auth_headers,
        )
        assert [s["card_id"] for s in res.json()["data"]] == [None]


class TestSessionOwnership:
    async def test_other_user_cannot_touch(
        self, client, auth_headers, other_headers, board, clock
    ):
        card = await create_card(client, auth_headers, board["lists"][0]["id"], "Gizli")
        s = await start(client, auth_headers, card_id=card["id"])
        h = other_headers

        assert await active(client, h) is None
        checks = [
            await client.post(
                f"{API}/sessions/start", json={"card_id": card["id"]}, headers=h
            ),
            await client.patch(
                f"{API}/sessions/{s['id']}", json={"note": "x"}, headers=h
            ),
            await client.delete(f"{API}/sessions/{s['id']}", headers=h),
            await client.get(
                f"{API}/sessions", params={"card_id": card["id"]}, headers=h
            ),
        ]
        assert [r.status_code for r in checks] == [404] * len(checks)
        # Baskasinin stop'u benim kronometremi durdurmaz
        res = await client.post(f"{API}/sessions/stop", json={}, headers=h)
        assert res.status_code == 409
        assert (await active(client, auth_headers))["id"] == s["id"]
        assert (await client.get(f"{API}/sessions", headers=h)).json()["data"] == []
