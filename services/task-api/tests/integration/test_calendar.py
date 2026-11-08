"""Faz 2: etkinlikler ve birlesik takvim."""

import pytest
from httpx import AsyncClient

from tests.integration.test_boards_cards import API, create_board, create_card

WEEK = {"start": "2026-11-09T00:00:00+03:00", "end": "2026-11-16T00:00:00+03:00"}


async def create_event(client, headers, **data):
    res = await client.post(f"{API}/events", json=data, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def calendar(client, headers, **params):
    res = await client.get(
        f"{API}/calendar", params={**WEEK, **params}, headers=headers
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["items"]


@pytest.fixture
async def spor(client: AsyncClient, auth_headers):
    return await create_board(client, auth_headers, name="Spor", color="#22c55e")


@pytest.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


class TestEvents:
    async def test_standalone_event(self, client, auth_headers, spor):
        ev = await create_event(
            client,
            auth_headers,
            title="Yoga dersi",
            start_at="2026-11-10T18:00:00+03:00",
            end_at="2026-11-10T19:00:00+03:00",
            board_id=spor["board"]["id"],
            location="Salon",
        )
        assert ev["card_id"] is None
        assert ev["board_id"] == spor["board"]["id"]
        # UTC olarak saklanir, timezone'lu doner
        assert ev["start_at"].startswith("2026-11-10T15:00:00")

    async def test_time_block_for_card_inherits_board_and_title(
        self, client, auth_headers, spor
    ):
        card = await create_card(
            client, auth_headers, spor["lists"][0]["id"], "5 km koşu"
        )
        ev = await create_event(
            client,
            auth_headers,
            card_id=card["id"],
            start_at="2026-11-11T07:00:00+03:00",
            end_at="2026-11-11T07:45:00+03:00",
        )
        assert ev["title"] == "5 km koşu"
        assert ev["board_id"] == spor["board"]["id"]

        res = await client.get(f"{API}/cards/{card['id']}/events", headers=auth_headers)
        assert [e["id"] for e in res.json()["data"]] == [ev["id"]]

    @pytest.mark.parametrize(
        "payload",
        [
            # bitis baslangictan once
            {
                "title": "x",
                "start_at": "2026-11-10T10:00:00Z",
                "end_at": "2026-11-10T09:00:00Z",
            },
            # baslik da kart da yok
            {"start_at": "2026-11-10T10:00:00Z", "end_at": "2026-11-10T11:00:00Z"},
        ],
    )
    async def test_validation(self, client, auth_headers, payload):
        res = await client.post(f"{API}/events", json=payload, headers=auth_headers)
        assert res.status_code == 422

    async def test_update_rejects_inverted_range(self, client, auth_headers):
        ev = await create_event(
            client,
            auth_headers,
            title="x",
            start_at="2026-11-10T10:00:00Z",
            end_at="2026-11-10T11:00:00Z",
        )
        # Sadece start gonderilir ama mevcut end'den sonraya kayar
        res = await client.patch(
            f"{API}/events/{ev['id']}",
            json={"start_at": "2026-11-10T12:00:00Z"},
            headers=auth_headers,
        )
        assert res.status_code == 422

    async def test_card_linked_event_cannot_change_board(
        self, client, auth_headers, spor
    ):
        is_board = await create_board(client, auth_headers, name="İş")
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "Koşu")
        ev = await create_event(
            client,
            auth_headers,
            card_id=card["id"],
            start_at="2026-11-10T10:00:00Z",
            end_at="2026-11-10T11:00:00Z",
        )
        res = await client.patch(
            f"{API}/events/{ev['id']}",
            json={"board_id": is_board["board"]["id"]},
            headers=auth_headers,
        )
        assert res.status_code == 422

    async def test_reschedule_is_logged_on_card(self, client, auth_headers, spor):
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "Koşu")
        ev = await create_event(
            client,
            auth_headers,
            card_id=card["id"],
            start_at="2026-11-10T10:00:00Z",
            end_at="2026-11-10T11:00:00Z",
        )
        await client.patch(
            f"{API}/events/{ev['id']}",
            json={"start_at": "2026-11-12T10:00:00Z", "end_at": "2026-11-12T11:00:00Z"},
            headers=auth_headers,
        )
        await client.delete(f"{API}/events/{ev['id']}", headers=auth_headers)
        res = await client.get(
            f"{API}/cards/{card['id']}/activity", headers=auth_headers
        )
        assert [a["action"] for a in res.json()["data"]] == [
            "unscheduled",
            "rescheduled",
            "scheduled",
            "created",
        ]


class TestCalendar:
    async def test_merges_events_and_deadlines_with_board_colors(
        self, client, auth_headers, spor
    ):
        list_id = spor["lists"][0]["id"]
        await create_card(
            client,
            auth_headers,
            list_id,
            "Maraton kaydı",
            due_date="2026-11-13T20:59:00Z",
        )
        await create_card(  # aralik disi
            client, auth_headers, list_id, "Uzak", due_date="2026-12-20T20:59:00Z"
        )
        await create_event(
            client,
            auth_headers,
            title="Bağımsız",
            start_at="2026-11-12T10:00:00Z",
            end_at="2026-11-12T11:00:00Z",
        )
        items = await calendar(client, auth_headers)
        by_title = {i["title"]: i for i in items}
        assert set(by_title) == {"Maraton kaydı", "Bağımsız"}
        assert by_title["Maraton kaydı"]["kind"] == "deadline"
        assert by_title["Maraton kaydı"]["all_day"] is True
        assert by_title["Maraton kaydı"]["color"] == "#22c55e"
        assert by_title["Bağımsız"]["color"] == "#64748b"  # board'suz

    async def test_event_overlapping_range_edges_is_included(
        self, client, auth_headers
    ):
        await create_event(  # araliktan once baslayip icinde biter
            client,
            auth_headers,
            title="Gece",
            start_at="2026-11-08T22:00:00+03:00",
            end_at="2026-11-09T02:00:00+03:00",
        )
        await create_event(  # tam aralik sonunda baslar -> dahil degil
            client,
            auth_headers,
            title="Sonra",
            start_at="2026-11-16T00:00:00+03:00",
            end_at="2026-11-16T01:00:00+03:00",
        )
        assert [i["title"] for i in await calendar(client, auth_headers)] == ["Gece"]

    async def test_board_filter_and_archived_hidden(self, client, auth_headers, spor):
        is_board = await create_board(client, auth_headers, name="İş")
        for board, title in ((spor, "Spor ev"), (is_board, "İş ev")):
            await create_event(
                client,
                auth_headers,
                title=title,
                board_id=board["board"]["id"],
                start_at="2026-11-10T10:00:00Z",
                end_at="2026-11-10T11:00:00Z",
            )
        items = await calendar(client, auth_headers, board_id=[spor["board"]["id"]])
        assert [i["title"] for i in items] == ["Spor ev"]

        await client.patch(
            f"{API}/boards/{spor['board']['id']}",
            json={"is_archived": True},
            headers=auth_headers,
        )
        assert [i["title"] for i in await calendar(client, auth_headers)] == ["İş ev"]

    async def test_time_block_follows_card_to_new_board(
        self, client, auth_headers, spor
    ):
        is_board = await create_board(client, auth_headers, name="İş", color="#3b82f6")
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "Koşu")
        await create_event(
            client,
            auth_headers,
            card_id=card["id"],
            start_at="2026-11-10T10:00:00Z",
            end_at="2026-11-10T11:00:00Z",
        )
        await client.post(
            f"{API}/cards/{card['id']}/move",
            json={"list_id": is_board["lists"][0]["id"], "index": 0},
            headers=auth_headers,
        )
        [item] = await calendar(client, auth_headers)
        assert item["board_id"] == is_board["board"]["id"]
        assert item["color"] == "#3b82f6"

    async def test_range_validation(self, client, auth_headers):
        res = await client.get(
            f"{API}/calendar",
            params={"start": "2026-11-10T00:00:00Z", "end": "2026-11-09T00:00:00Z"},
            headers=auth_headers,
        )
        assert res.status_code == 422
        res = await client.get(
            f"{API}/calendar",
            params={"start": "2026-01-01T00:00:00Z", "end": "2028-01-01T00:00:00Z"},
            headers=auth_headers,
        )
        assert res.status_code == 422


class TestCleanup:
    async def test_deleting_card_removes_its_time_blocks(
        self, client, auth_headers, spor
    ):
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "Koşu")
        ev = await create_event(
            client,
            auth_headers,
            card_id=card["id"],
            start_at="2026-11-10T10:00:00Z",
            end_at="2026-11-10T11:00:00Z",
        )
        await client.delete(f"{API}/cards/{card['id']}", headers=auth_headers)
        res = await client.get(f"{API}/events/{ev['id']}", headers=auth_headers)
        assert res.status_code == 404
        assert await calendar(client, auth_headers) == []

    async def test_deleting_board_removes_its_events(self, client, auth_headers, spor):
        await create_event(
            client,
            auth_headers,
            title="Spor ev",
            board_id=spor["board"]["id"],
            start_at="2026-11-10T10:00:00Z",
            end_at="2026-11-10T11:00:00Z",
        )
        await client.delete(f"{API}/boards/{spor['board']['id']}", headers=auth_headers)
        assert await calendar(client, auth_headers) == []


class TestEventOwnership:
    async def test_other_user_cannot_see_or_touch(
        self, client, auth_headers, other_headers, spor
    ):
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "Gizli")
        ev = await create_event(
            client,
            auth_headers,
            title="Gizli plan",
            start_at="2026-11-10T10:00:00Z",
            end_at="2026-11-10T11:00:00Z",
        )
        h = other_headers
        checks = [
            await client.get(f"{API}/events/{ev['id']}", headers=h),
            await client.patch(
                f"{API}/events/{ev['id']}", json={"title": "y"}, headers=h
            ),
            await client.delete(f"{API}/events/{ev['id']}", headers=h),
            await client.get(f"{API}/cards/{card['id']}/events", headers=h),
            # baskasinin kartina / board'una zaman blogu acamaz
            await client.post(
                f"{API}/events",
                json={
                    "card_id": card["id"],
                    "start_at": "2026-11-10T10:00:00Z",
                    "end_at": "2026-11-10T11:00:00Z",
                },
                headers=h,
            ),
            await client.post(
                f"{API}/events",
                json={
                    "title": "x",
                    "board_id": spor["board"]["id"],
                    "start_at": "2026-11-10T10:00:00Z",
                    "end_at": "2026-11-10T11:00:00Z",
                },
                headers=h,
            ),
        ]
        assert [r.status_code for r in checks] == [404] * len(checks)
        assert await calendar(client, h) == []
