"""Faz 1b: alt kartlar, bagimliliklar, bolme, grafik."""

import pytest
from httpx import AsyncClient

from tests.integration.test_boards_cards import API, create_board, create_card


@pytest.fixture
async def board(client: AsyncClient, auth_headers):
    return await create_board(client, auth_headers, name="Eğitimler")


async def get_card(client, headers, card_id):
    return (await client.get(f"{API}/cards/{card_id}", headers=headers)).json()["data"]


async def complete(client, headers, card_id):
    res = await client.patch(
        f"{API}/cards/{card_id}", json={"status": "completed"}, headers=headers
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


class TestSubtasks:
    async def test_create_subtask_inherits_list_and_rolls_up(
        self, client, auth_headers, board
    ):
        parent = await create_card(
            client, auth_headers, board["lists"][0]["id"], "Kurs"
        )
        res = await client.post(
            f"{API}/cards",
            json={
                "parent_id": parent["id"],
                "title": "Bölüm 1",
                "estimated_minutes": 60,
            },
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
        child = res.json()["data"]
        assert child["parent_id"] == parent["id"]
        assert child["list_id"] == parent["list_id"]

        detail = await get_card(client, auth_headers, parent["id"])
        assert (detail["subtask_total"], detail["subtask_done"]) == (1, 0)
        assert detail["subtask_estimated_minutes"] == 60
        assert [s["title"] for s in detail["subtasks"]] == ["Bölüm 1"]
        assert (await get_card(client, auth_headers, child["id"]))["parent"]["id"] == (
            parent["id"]
        )

    async def test_parent_cycle_rejected(self, client, auth_headers, board):
        a = await create_card(client, auth_headers, board["lists"][0]["id"], "A")
        b = await create_card(client, auth_headers, board["lists"][0]["id"], "B")
        await client.patch(
            f"{API}/cards/{b['id']}", json={"parent_id": a["id"]}, headers=auth_headers
        )
        res = await client.patch(
            f"{API}/cards/{a['id']}", json={"parent_id": b["id"]}, headers=auth_headers
        )
        assert res.status_code == 422
        res = await client.patch(
            f"{API}/cards/{a['id']}", json={"parent_id": a["id"]}, headers=auth_headers
        )
        assert res.status_code == 422

    async def test_deleting_parent_detaches_children(self, client, auth_headers, board):
        parent = await create_card(client, auth_headers, board["lists"][0]["id"], "P")
        await client.post(
            f"{API}/cards/{parent['id']}/split", json={"parts": 2}, headers=auth_headers
        )
        children = (await get_card(client, auth_headers, parent["id"]))["subtasks"]
        await client.delete(f"{API}/cards/{parent['id']}", headers=auth_headers)
        for c in children:
            detail = await get_card(client, auth_headers, c["id"])
            assert detail["parent_id"] is None


class TestDependencies:
    async def test_blocked_until_prerequisite_done(self, client, auth_headers, board):
        list_id = board["lists"][0]["id"]
        a = await create_card(client, auth_headers, list_id, "A")
        b = await create_card(client, auth_headers, list_id, "B")
        res = await client.post(
            f"{API}/cards/{b['id']}/dependencies",
            json={"depends_on_id": a["id"]},
            headers=auth_headers,
        )
        assert res.status_code == 200
        detail = res.json()["data"]
        assert detail["blocked"] is True
        assert detail["blocked_by_count"] == 1
        assert [d["id"] for d in detail["depends_on"]] == [a["id"]]
        assert [
            d["id"]
            for d in (await get_card(client, auth_headers, a["id"]))["dependents"]
        ] == [b["id"]]

        await complete(client, auth_headers, a["id"])
        assert (await get_card(client, auth_headers, b["id"]))["blocked"] is False

        # B'nin gecmisinde "unblocked" olmali
        acts = (
            await client.get(f"{API}/cards/{b['id']}/activity", headers=auth_headers)
        ).json()["data"]
        assert "unblocked" in [x["action"] for x in acts]

    async def test_cycle_rejected(self, client, auth_headers, board):
        list_id = board["lists"][0]["id"]
        a, b, c = [await create_card(client, auth_headers, list_id, t) for t in "ABC"]
        for card, dep in ((b, a), (c, b)):
            await client.post(
                f"{API}/cards/{card['id']}/dependencies",
                json={"depends_on_id": dep["id"]},
                headers=auth_headers,
            )
        res = await client.post(
            f"{API}/cards/{a['id']}/dependencies",
            json={"depends_on_id": c["id"]},
            headers=auth_headers,
        )
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "DEPENDENCY_CYCLE"

        res = await client.post(
            f"{API}/cards/{a['id']}/dependencies",
            json={"depends_on_id": a["id"]},
            headers=auth_headers,
        )
        assert res.status_code == 422

    async def test_remove_dependency_and_idempotent_add(
        self, client, auth_headers, board
    ):
        list_id = board["lists"][0]["id"]
        a = await create_card(client, auth_headers, list_id, "A")
        b = await create_card(client, auth_headers, list_id, "B")
        for _ in range(2):
            await client.post(
                f"{API}/cards/{b['id']}/dependencies",
                json={"depends_on_id": a["id"]},
                headers=auth_headers,
            )
        assert len((await get_card(client, auth_headers, b["id"]))["depends_on"]) == 1
        res = await client.delete(
            f"{API}/cards/{b['id']}/dependencies/{a['id']}", headers=auth_headers
        )
        assert res.json()["data"]["blocked"] is False

    async def test_cross_board_dependency_shows_in_graph(
        self, client, auth_headers, board
    ):
        other = await create_board(client, auth_headers, name="İş")
        work = await create_card(client, auth_headers, other["lists"][0]["id"], "Sunum")
        course = await create_card(
            client, auth_headers, board["lists"][0]["id"], "Kurs"
        )
        await client.post(
            f"{API}/cards/{work['id']}/dependencies",
            json={"depends_on_id": course["id"]},
            headers=auth_headers,
        )
        graph = (
            await client.get(
                f"{API}/boards/{board['board']['id']}/graph", headers=auth_headers
            )
        ).json()["data"]
        assert {n["id"] for n in graph["nodes"]} == {course["id"], work["id"]}
        assert graph["edges"] == [
            {"source": course["id"], "target": work["id"], "type": "dependency"}
        ]


class TestSplit:
    async def test_split_into_chained_parts(self, client, auth_headers, board):
        """'20 saatlik egitim, 9 part' senaryosu."""
        parent = await create_card(
            client, auth_headers, board["lists"][0]["id"], "Docker eğitimi"
        )
        res = await client.post(
            f"{API}/cards/{parent['id']}/split",
            json={"parts": 9, "total_minutes": 1200, "chain": True},
            headers=auth_headers,
        )
        assert res.status_code == 200, res.text
        detail = res.json()["data"]
        subs = detail["subtasks"]
        assert len(subs) == 9
        assert sum(s["estimated_minutes"] for s in subs) == 1200
        assert subs[0]["title"] == "Docker eğitimi — Bölüm 1/9"
        assert detail["estimated_minutes"] == 1200
        # Sadece ilk parca acik, digerleri sirada bekliyor
        assert [s["blocked"] for s in subs] == [False] + [True] * 8
        # Her alt kartin kendi gecmisi 'created' ile baslar
        res = await client.get(
            f"{API}/cards/{subs[3]['id']}/activity", headers=auth_headers
        )
        assert [a["action"] for a in res.json()["data"]] == ["created"]

        await complete(client, auth_headers, subs[0]["id"])
        subs = (await get_card(client, auth_headers, parent["id"]))["subtasks"]
        assert [s["blocked"] for s in subs] == [False, False] + [True] * 7
        detail = await get_card(client, auth_headers, parent["id"])
        assert (detail["subtask_total"], detail["subtask_done"]) == (9, 1)

        graph = (
            await client.get(
                f"{API}/boards/{board['board']['id']}/graph", headers=auth_headers
            )
        ).json()["data"]
        types = [e["type"] for e in graph["edges"]]
        assert types.count("dependency") == 8
        assert types.count("parent") == 9

    async def test_split_with_titles_unchained(self, client, auth_headers, board):
        parent = await create_card(client, auth_headers, board["lists"][0]["id"], "P")
        res = await client.post(
            f"{API}/cards/{parent['id']}/split",
            json={"titles": ["Giriş", "Uygulama"], "chain": False},
            headers=auth_headers,
        )
        subs = res.json()["data"]["subtasks"]
        assert [s["title"] for s in subs] == ["Giriş", "Uygulama"]
        assert not any(s["blocked"] for s in subs)

    async def test_split_requires_titles_or_parts(self, client, auth_headers, board):
        parent = await create_card(client, auth_headers, board["lists"][0]["id"], "P")
        res = await client.post(
            f"{API}/cards/{parent['id']}/split", json={}, headers=auth_headers
        )
        assert res.status_code == 422


class TestGraphOwnership:
    async def test_other_user_cannot_link_or_view(self, client, auth_headers, board):
        mine = await create_card(client, auth_headers, board["lists"][0]["id"], "Benim")
        creds = {"email": "x2@example.com", "password": "otherpassword123"}
        await client.post(f"{API}/auth/register", json=creds)
        token = (await client.post(f"{API}/auth/login", json=creds)).json()["data"][
            "access_token"
        ]
        h = {"Authorization": f"Bearer {token}"}
        theirs_board = await create_board(client, h)
        theirs = await create_card(client, h, theirs_board["lists"][0]["id"], "Onun")

        checks = [
            await client.post(
                f"{API}/cards/{theirs['id']}/dependencies",
                json={"depends_on_id": mine["id"]},
                headers=h,
            ),
            await client.post(
                f"{API}/cards/{mine['id']}/split", json={"parts": 2}, headers=h
            ),
            await client.get(f"{API}/boards/{board['board']['id']}/graph", headers=h),
            await client.post(
                f"{API}/cards", json={"parent_id": mine["id"], "title": "x"}, headers=h
            ),
            await client.patch(
                f"{API}/cards/{theirs['id']}", json={"parent_id": mine["id"]}, headers=h
            ),
        ]
        assert [r.status_code for r in checks] == [404] * len(checks)


class TestUnblockedSignal:
    async def _unblocked_count(self, client, headers, card_id):
        res = await client.get(f"{API}/cards/{card_id}/activity", headers=headers)
        return [a["action"] for a in res.json()["data"]].count("unblocked")

    async def test_completing_prereq_unblocks_once(self, client, auth_headers, board):
        list_id = board["lists"][0]["id"]
        a = await create_card(client, auth_headers, list_id, "A")
        b = await create_card(client, auth_headers, list_id, "B")
        await client.post(
            f"{API}/cards/{b['id']}/dependencies",
            json={"depends_on_id": a["id"]},
            headers=auth_headers,
        )
        await complete(client, auth_headers, a["id"])
        assert await self._unblocked_count(client, auth_headers, b["id"]) == 1

        # Zaten tamamlanmis on kosulun ipini silmek yeni "unblocked" uretmemeli
        await client.delete(
            f"{API}/cards/{b['id']}/dependencies/{a['id']}", headers=auth_headers
        )
        assert await self._unblocked_count(client, auth_headers, b["id"]) == 1

    async def test_removing_open_prereq_unblocks(self, client, auth_headers, board):
        list_id = board["lists"][0]["id"]
        a = await create_card(client, auth_headers, list_id, "A")
        b = await create_card(client, auth_headers, list_id, "B")
        await client.post(
            f"{API}/cards/{b['id']}/dependencies",
            json={"depends_on_id": a["id"]},
            headers=auth_headers,
        )
        await client.delete(
            f"{API}/cards/{b['id']}/dependencies/{a['id']}", headers=auth_headers
        )
        assert await self._unblocked_count(client, auth_headers, b["id"]) == 1
