"""Board / liste / kart / not / checklist integration testleri."""

from typing import Any

import pytest
from httpx import AsyncClient

API = "/api/v1"


async def create_board(client: AsyncClient, headers, **kwargs) -> dict[str, Any]:
    payload = {"name": "Spor", **kwargs}
    res = await client.post(f"{API}/boards", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    detail = await client.get(
        f"{API}/boards/{res.json()['data']['id']}", headers=headers
    )
    return detail.json()["data"]


async def create_card(client: AsyncClient, headers, list_id: int, title: str, **kw):
    res = await client.post(
        f"{API}/cards", json={"list_id": list_id, "title": title, **kw}, headers=headers
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


@pytest.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    """Ikinci kullanici (sahiplik testleri icin)."""
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


class TestBoards:
    async def test_create_board_with_default_lists(self, client, auth_headers):
        detail = await create_board(
            client,
            auth_headers,
            scope_description="Antrenman, koşu",
            weekly_time_budget_min=300,
            privacy="local_only",
        )
        board = detail["board"]
        assert board["privacy"] == "local_only"
        assert board["weekly_time_budget_min"] == 300
        assert [lst["name"] for lst in detail["lists"]] == [
            "Yapılacak",
            "Yapılıyor",
            "Tamamlandı",
        ]
        assert [lst["is_done_list"] for lst in detail["lists"]] == [False, False, True]

    async def test_custom_lists_and_listing_counts(self, client, auth_headers):
        detail = await create_board(
            client, auth_headers, lists=["Fikirler", "Seçilenler"]
        )
        assert [lst["name"] for lst in detail["lists"]] == ["Fikirler", "Seçilenler"]
        await create_card(client, auth_headers, detail["lists"][0]["id"], "Fikir 1")

        res = await client.get(f"{API}/boards", headers=auth_headers)
        boards = res.json()["data"]
        assert boards[0]["open_card_count"] == 1

    async def test_invalid_color_rejected(self, client, auth_headers):
        res = await client.post(
            f"{API}/boards", json={"name": "X", "color": "red"}, headers=auth_headers
        )
        assert res.status_code == 422

    async def test_archive_hides_board(self, client, auth_headers):
        detail = await create_board(client, auth_headers)
        board_id = detail["board"]["id"]
        await client.patch(
            f"{API}/boards/{board_id}", json={"is_archived": True}, headers=auth_headers
        )
        res = await client.get(f"{API}/boards", headers=auth_headers)
        assert res.json()["data"] == []
        res = await client.get(
            f"{API}/boards", params={"include_archived": True}, headers=auth_headers
        )
        assert len(res.json()["data"]) == 1

    async def test_delete_board_removes_cards(self, client, auth_headers):
        detail = await create_board(client, auth_headers)
        card = await create_card(client, auth_headers, detail["lists"][0]["id"], "Koşu")
        res = await client.delete(
            f"{API}/boards/{detail['board']['id']}", headers=auth_headers
        )
        assert res.status_code == 204
        res = await client.get(f"{API}/cards/{card['id']}", headers=auth_headers)
        assert res.status_code == 404


class TestLists:
    async def test_add_move_and_delete_list(self, client, auth_headers):
        detail = await create_board(client, auth_headers)
        board_id = detail["board"]["id"]
        res = await client.post(
            f"{API}/boards/{board_id}/lists",
            json={"name": "Beklemede"},
            headers=auth_headers,
        )
        new_list = res.json()["data"]

        await client.post(
            f"{API}/lists/{new_list['id']}/move",
            json={"index": 0},
            headers=auth_headers,
        )
        lists = (
            await client.get(f"{API}/boards/{board_id}", headers=auth_headers)
        ).json()["data"]["lists"]
        assert lists[0]["name"] == "Beklemede"

        res = await client.delete(f"{API}/lists/{new_list['id']}", headers=auth_headers)
        assert res.status_code == 204

    async def test_cannot_delete_non_empty_list(self, client, auth_headers):
        detail = await create_board(client, auth_headers)
        list_id = detail["lists"][0]["id"]
        await create_card(client, auth_headers, list_id, "Koşu")
        res = await client.delete(f"{API}/lists/{list_id}", headers=auth_headers)
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "LIST_NOT_EMPTY"


class TestCards:
    async def test_create_and_order_cards(self, client, auth_headers):
        detail = await create_board(client, auth_headers)
        list_id = detail["lists"][0]["id"]
        a = await create_card(client, auth_headers, list_id, "A", estimated_minutes=45)
        await create_card(client, auth_headers, list_id, "B")
        assert a["estimated_minutes"] == 45
        assert a["status"] == "pending"
        assert a["created_by"] == "user"

        cards = (
            await client.get(
                f"{API}/boards/{detail['board']['id']}", headers=auth_headers
            )
        ).json()["data"]["cards"]
        assert [c["title"] for c in sorted(cards, key=lambda c: c["position"])] == [
            "A",
            "B",
        ]

    async def test_move_to_done_list_completes_and_back_reopens(
        self, client, auth_headers
    ):
        detail = await create_board(client, auth_headers)
        todo, _, done = detail["lists"]
        card = await create_card(client, auth_headers, todo["id"], "Koşu")

        res = await client.post(
            f"{API}/cards/{card['id']}/move",
            json={"list_id": done["id"], "index": 0},
            headers=auth_headers,
        )
        moved = res.json()["data"]
        assert moved["status"] == "completed"
        assert moved["completed_at"] is not None

        res = await client.post(
            f"{API}/cards/{card['id']}/move",
            json={"list_id": todo["id"], "index": 0},
            headers=auth_headers,
        )
        back = res.json()["data"]
        assert back["status"] == "pending"
        assert back["completed_at"] is None

    async def test_reorder_within_list(self, client, auth_headers):
        detail = await create_board(client, auth_headers)
        list_id = detail["lists"][0]["id"]
        await create_card(client, auth_headers, list_id, "A")
        await create_card(client, auth_headers, list_id, "B")
        c = await create_card(client, auth_headers, list_id, "C")

        await client.post(
            f"{API}/cards/{c['id']}/move",
            json={"list_id": list_id, "index": 0},
            headers=auth_headers,
        )
        cards = (
            await client.get(
                f"{API}/boards/{detail['board']['id']}", headers=auth_headers
            )
        ).json()["data"]["cards"]
        assert [x["title"] for x in sorted(cards, key=lambda x: x["position"])] == [
            "C",
            "A",
            "B",
        ]

    async def test_status_completed_moves_to_done_list(self, client, auth_headers):
        detail = await create_board(client, auth_headers)
        todo, _, done = detail["lists"]
        card = await create_card(client, auth_headers, todo["id"], "Koşu")

        res = await client.patch(
            f"{API}/cards/{card['id']}",
            json={"status": "completed"},
            headers=auth_headers,
        )
        updated = res.json()["data"]
        assert updated["list_id"] == done["id"]
        assert updated["completed_at"] is not None

        res = await client.patch(
            f"{API}/cards/{card['id']}",
            json={"status": "in_progress"},
            headers=auth_headers,
        )
        reopened = res.json()["data"]
        assert reopened["list_id"] == todo["id"]
        assert reopened["status"] == "in_progress"
        assert reopened["completed_at"] is None

    async def test_labels_must_belong_to_card_board(self, client, auth_headers):
        b1 = await create_board(client, auth_headers, name="Spor")
        b2 = await create_board(client, auth_headers, name="İş")
        res = await client.post(
            f"{API}/boards/{b2['board']['id']}/labels",
            json={"name": "Acil", "color": "#ef4444"},
            headers=auth_headers,
        )
        foreign_label = res.json()["data"]["id"]
        res = await client.post(
            f"{API}/cards",
            json={
                "list_id": b1["lists"][0]["id"],
                "title": "X",
                "label_ids": [foreign_label],
            },
            headers=auth_headers,
        )
        assert res.status_code == 422

        res = await client.post(
            f"{API}/boards/{b1['board']['id']}/labels",
            json={"name": "Kardiyo"},
            headers=auth_headers,
        )
        own_label = res.json()["data"]["id"]
        card = await create_card(
            client, auth_headers, b1["lists"][0]["id"], "Koşu", label_ids=[own_label]
        )
        assert card["label_ids"] == [own_label]

    async def test_label_without_color_gets_next_free_palette_color(
        self, client, auth_headers
    ):
        from app.services.palette import BOARD_PALETTE

        b = await create_board(client, auth_headers, name="Renk")
        url = f"{API}/boards/{b['board']['id']}/labels"
        colors = []
        for name in ("A", "B", "C"):
            res = await client.post(url, json={"name": name}, headers=auth_headers)
            assert res.status_code == 201, res.text
            colors.append(res.json()["data"]["color"])
        assert colors == BOARD_PALETTE[:3]

        # Acik renk verilirse ona dokunulmaz; sirada kullanilmayan ilk renk kalir
        res = await client.post(
            url, json={"name": "D", "color": BOARD_PALETTE[3]}, headers=auth_headers
        )
        assert res.json()["data"]["color"] == BOARD_PALETTE[3]
        res = await client.post(url, json={"name": "E"}, headers=auth_headers)
        assert res.json()["data"]["color"] == BOARD_PALETTE[4]

    async def test_label_color_falls_back_to_first_when_palette_exhausted(
        self, client, auth_headers
    ):
        from app.services.palette import BOARD_PALETTE

        b = await create_board(client, auth_headers, name="Dolu")
        url = f"{API}/boards/{b['board']['id']}/labels"
        for i, color in enumerate(BOARD_PALETTE):
            await client.post(
                url, json={"name": f"L{i}", "color": color}, headers=auth_headers
            )
        res = await client.post(url, json={"name": "Fazla"}, headers=auth_headers)
        assert res.json()["data"]["color"] == BOARD_PALETTE[0]

    async def test_notes_checklist_and_summary_counts(self, client, auth_headers):
        detail = await create_board(client, auth_headers)
        card = await create_card(
            client, auth_headers, detail["lists"][0]["id"], "Eğitim"
        )
        cid = card["id"]

        await client.post(
            f"{API}/cards/{cid}/notes",
            json={"content": "**Bölüm 1** bitti"},
            headers=auth_headers,
        )
        items = []
        for text in ("Video 1", "Video 2"):
            res = await client.post(
                f"{API}/cards/{cid}/checklist",
                json={"text": text},
                headers=auth_headers,
            )
            items.append(res.json()["data"])
        await client.patch(
            f"{API}/checklist/{items[0]['id']}",
            json={"is_done": True},
            headers=auth_headers,
        )

        full = (await client.get(f"{API}/cards/{cid}", headers=auth_headers)).json()[
            "data"
        ]
        assert full["note_count"] == 1
        assert full["notes"][0]["content"] == "**Bölüm 1** bitti"
        assert [i["text"] for i in full["checklist"]] == ["Video 1", "Video 2"]
        assert (full["checklist_total"], full["checklist_done"]) == (2, 1)

    async def test_activity_log_records_history(self, client, auth_headers):
        detail = await create_board(client, auth_headers)
        todo, _, done = detail["lists"]
        card = await create_card(client, auth_headers, todo["id"], "Koşu")
        await client.patch(
            f"{API}/cards/{card['id']}",
            json={"estimated_minutes": 30},
            headers=auth_headers,
        )
        await client.post(
            f"{API}/cards/{card['id']}/move",
            json={"list_id": done["id"], "index": 0},
            headers=auth_headers,
        )
        await client.delete(f"{API}/cards/{card['id']}", headers=auth_headers)

        # Silinen kartin gecmisi hala okunabilir
        res = await client.get(
            f"{API}/cards/{card['id']}/activity", headers=auth_headers
        )
        assert res.status_code == 200
        actions = [a["action"] for a in res.json()["data"]]
        assert actions == ["deleted", "completed", "estimate_changed", "created"]

    async def test_legacy_tasks_api_lands_in_default_board(self, client, auth_headers):
        res = await client.post(
            f"{API}/tasks/", json={"title": "Eski API"}, headers=auth_headers
        )
        assert res.status_code == 201
        boards = (await client.get(f"{API}/boards", headers=auth_headers)).json()[
            "data"
        ]
        assert [b["name"] for b in boards] == ["Genel"]
        assert boards[0]["open_card_count"] == 1


class TestOwnership:
    """Baska kullanicinin kayitlarina erisim -> 404 (varligi sizdirmadan)."""

    async def test_other_user_cannot_touch_anything(
        self, client, auth_headers, other_headers
    ):
        detail = await create_board(client, auth_headers)
        board_id = detail["board"]["id"]
        list_id = detail["lists"][0]["id"]
        card = await create_card(client, auth_headers, list_id, "Gizli")
        note = (
            await client.post(
                f"{API}/cards/{card['id']}/notes",
                json={"content": "x"},
                headers=auth_headers,
            )
        ).json()["data"]
        item = (
            await client.post(
                f"{API}/cards/{card['id']}/checklist",
                json={"text": "x"},
                headers=auth_headers,
            )
        ).json()["data"]

        h = other_headers
        checks = [
            await client.get(f"{API}/boards/{board_id}", headers=h),
            await client.patch(
                f"{API}/boards/{board_id}", json={"name": "y"}, headers=h
            ),
            await client.delete(f"{API}/boards/{board_id}", headers=h),
            await client.post(
                f"{API}/boards/{board_id}/lists", json={"name": "y"}, headers=h
            ),
            await client.patch(f"{API}/lists/{list_id}", json={"name": "y"}, headers=h),
            await client.post(
                f"{API}/cards", json={"list_id": list_id, "title": "y"}, headers=h
            ),
            await client.get(f"{API}/cards/{card['id']}", headers=h),
            await client.patch(
                f"{API}/cards/{card['id']}", json={"title": "y"}, headers=h
            ),
            await client.delete(f"{API}/cards/{card['id']}", headers=h),
            await client.get(f"{API}/cards/{card['id']}/activity", headers=h),
            await client.patch(
                f"{API}/notes/{note['id']}", json={"content": "y"}, headers=h
            ),
            await client.patch(
                f"{API}/checklist/{item['id']}", json={"is_done": True}, headers=h
            ),
        ]
        assert [r.status_code for r in checks] == [404] * len(checks)

        # Kendi listesine baskasinin kartini tasiyamaz
        own = await create_board(client, h)
        res = await client.post(
            f"{API}/cards/{card['id']}/move",
            json={"list_id": own["lists"][0]["id"], "index": 0},
            headers=h,
        )
        assert res.status_code == 404
        assert (await client.get(f"{API}/boards", headers=h)).json()["data"][0][
            "open_card_count"
        ] == 0


class TestTimestamps:
    async def test_timestamps_are_timezone_aware(self, client, auth_headers):
        """SQLite'ta bile zamanlar UTC isaretli donmeli (yoksa tarayici yerel saat sanar)."""
        detail = await create_board(client, auth_headers)
        card = await create_card(client, auth_headers, detail["lists"][0]["id"], "X")
        note = (
            await client.post(
                f"{API}/cards/{card['id']}/notes",
                json={"content": "n"},
                headers=auth_headers,
            )
        ).json()["data"]
        for value in (
            card["created_at"],
            note["created_at"],
            detail["board"]["created_at"],
        ):
            assert value.endswith("Z") or value.endswith("+00:00"), value
