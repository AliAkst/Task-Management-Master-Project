"""Faz 13h1: süpürme adayları + toplu kart işlemi (veri bütünlüğü)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.db.entities import ActivityLogEntity, TaskEntity
from tests.integration.test_boards_cards import API, create_board, create_card


@pytest.fixture
async def other_headers(client) -> dict[str, str]:
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


def iso(days_ago: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()


async def candidates(client, headers, board_id):
    res = await client.get(f"{API}/boards/{board_id}/sweep-candidates", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def bulk(client, headers, body, expect=200):
    res = await client.post(f"{API}/cards/bulk", json=body, headers=headers)
    assert res.status_code == expect, res.text
    return res.json()


async def card_state(client, headers, card_id):
    return (await client.get(f"{API}/cards/{card_id}", headers=headers)).json()["data"]


@pytest.fixture
async def seeded(client, auth_headers, test_session):
    detail = await create_board(
        client,
        auth_headers,
        name="Iş",
        lists=["Yapılacak", "Old Todos", "Completed(Same Week)", "Golden tasks"],
    )
    todo, old, _comp, golden = (lst["id"] for lst in detail["lists"])
    c = {}
    c["old1"] = await create_card(client, auth_headers, old, "Eski 1")
    c["old_overdue"] = await create_card(
        client, auth_headers, old, "Eski ve gecikmiş", due_date=iso(40)
    )
    c["overdue"] = await create_card(
        client, auth_headers, todo, "Gecikmiş", due_date=iso(20)
    )
    c["recent_due"] = await create_card(
        client, auth_headers, todo, "Yakın gecikmiş", due_date=iso(5)
    )
    c["golden"] = await create_card(client, auth_headers, golden, "Altın")
    c["m1"] = await create_card(client, auth_headers, todo, "Market")
    c["m2"] = await create_card(client, auth_headers, todo, "market.")
    c["k_done"] = await create_card(client, auth_headers, todo, "Kuyumcu")
    c["k_open"] = await create_card(client, auth_headers, todo, "  kuyumcu ")
    await client.patch(
        f"{API}/cards/{c['k_done']['id']}",
        json={"status": "completed"},
        headers=auth_headers,
    )
    c["stale"] = await create_card(client, auth_headers, todo, "Unutulmuş")
    sid = c["stale"]["id"]
    long_ago = datetime.now(UTC) - timedelta(days=60)
    await test_session.execute(
        update(TaskEntity).where(TaskEntity.id == sid).values(created_at=long_ago)
    )
    await test_session.execute(
        update(ActivityLogEntity)
        .where(ActivityLogEntity.card_id == sid)
        .values(occurred_at=long_ago)
    )
    await test_session.commit()
    return detail, c


class TestCandidates:
    async def test_group_order_and_single_group(self, client, auth_headers, seeded):
        detail, c = seeded
        data = await candidates(client, auth_headers, detail["board"]["id"])
        groups = {g["key"]: g for g in data["groups"]}
        assert [g["key"] for g in data["groups"]] == [
            "old_lists",
            "overdue",
            "duplicates",
            "stale",
        ]
        ids = {k: {x["id"] for x in g["cards"]} for k, g in groups.items()}
        assert ids["old_lists"] == {c["old1"]["id"], c["old_overdue"]["id"]}
        assert ids["overdue"] == {c["overdue"]["id"]}  # eski liste kartı burada yok
        assert ids["duplicates"] == {c["m2"]["id"], c["k_open"]["id"]}
        assert ids["stale"] == {c["stale"]["id"]}
        every = [x["id"] for g in groups.values() for x in g["cards"]]
        assert len(every) == len(set(every))  # kart tek grupta
        assert c["golden"]["id"] not in every and c["recent_due"]["id"] not in every
        assert c["k_done"]["id"] not in every  # tamamlanan aday değil
        dup = {x["id"]: x for x in groups["duplicates"]["cards"]}
        assert f"#{c['m1']['id']}" in dup[c["m2"]["id"]]["reason"]
        assert f"#{c['k_done']['id']}" in dup[c["k_open"]["id"]]["reason"]
        assert dup[c["m2"]["id"]]["list_name"] == "Yapılacak"

    async def test_done_list_hints(self, client, auth_headers, seeded):
        detail, _ = seeded
        data = await candidates(client, auth_headers, detail["board"]["id"])
        assert [h["name"] for h in data["done_list_hints"]] == ["Completed(Same Week)"]

    async def test_archived_cards_excluded(self, client, auth_headers, seeded):
        detail, c = seeded
        await bulk(client, auth_headers, {"ids": [c["old1"]["id"]], "op": "archive"})
        data = await candidates(client, auth_headers, detail["board"]["id"])
        old = next(g for g in data["groups"] if g["key"] == "old_lists")
        assert [x["id"] for x in old["cards"]] == [c["old_overdue"]["id"]]

    async def test_foreign_board_404(self, client, other_headers, seeded):
        detail, _ = seeded
        res = await client.get(
            f"{API}/boards/{detail['board']['id']}/sweep-candidates",
            headers=other_headers,
        )
        assert res.status_code == 404


class TestBulk:
    async def test_archive_and_unarchive_with_activity(
        self, client, auth_headers, seeded, test_session
    ):
        _, c = seeded
        ids = [c["old1"]["id"], c["overdue"]["id"]]
        res = await bulk(client, auth_headers, {"ids": ids, "op": "archive"})
        assert res["data"] == {"updated": 2}
        for i in ids:
            assert (await card_state(client, auth_headers, i))["is_archived"] is True
        rows = (
            await test_session.execute(
                select(ActivityLogEntity.card_id, ActivityLogEntity.action).where(
                    ActivityLogEntity.card_id.in_(ids)
                )
            )
        ).all()
        assert {(i, "archived") for i in ids} <= {tuple(r) for r in rows}
        await bulk(client, auth_headers, {"ids": ids, "op": "unarchive"})
        for i in ids:
            assert (await card_state(client, auth_headers, i))["is_archived"] is False

    async def test_mixed_ownership_is_404_and_changes_nothing(
        self, client, auth_headers, other_headers, seeded
    ):
        _, c = seeded
        theirs_board = await create_board(client, other_headers, name="Yabancı")
        theirs = await create_card(
            client, other_headers, theirs_board["lists"][0]["id"], "Onun kartı"
        )
        mine = [c["old1"]["id"], c["overdue"]["id"]]
        for body in (
            {"ids": mine + [theirs["id"]], "op": "archive"},
            {"ids": mine + [999999], "op": "archive"},
            {"ids": mine + [theirs["id"]], "op": "complete"},
        ):
            await bulk(client, auth_headers, body, expect=404)
        for i in mine:
            st = await card_state(client, auth_headers, i)
            assert st["is_archived"] is False and st["status"] != "completed"
        theirs_after = await card_state(client, other_headers, theirs["id"])
        assert theirs_after["is_archived"] is False

    async def test_validation(self, client, auth_headers, seeded):
        _, c = seeded
        one = c["old1"]["id"]
        await bulk(client, auth_headers, {"ids": list(range(1, 202)), "op": "archive"}, 422)
        await bulk(client, auth_headers, {"ids": [], "op": "archive"}, 422)
        await bulk(client, auth_headers, {"ids": [one, one], "op": "archive"}, 422)
        await bulk(client, auth_headers, {"ids": [one], "op": "delete"}, 422)
        await bulk(client, auth_headers, {"ids": [one], "op": "move"}, 422)
        # 200 id sınırı kabul edilir (sahipsiz id'ler -> 404, 422 değil)
        await bulk(
            client, auth_headers, {"ids": list(range(5000, 5200)), "op": "archive"}, 404
        )

    async def test_complete_uses_service_path(
        self, client, auth_headers, seeded, test_session
    ):
        _, c = seeded
        cid = c["overdue"]["id"]
        await bulk(client, auth_headers, {"ids": [cid], "op": "complete"})
        st = await card_state(client, auth_headers, cid)
        assert st["status"] == "completed" and st["completed_at"] is not None
        actions = (
            (
                await test_session.execute(
                    select(ActivityLogEntity.action).where(
                        ActivityLogEntity.card_id == cid
                    )
                )
            )
            .scalars()
            .all()
        )
        assert "completed" in actions

    async def test_move(self, client, auth_headers, seeded):
        detail, c = seeded
        target = detail["lists"][0]["id"]
        cid = c["old1"]["id"]
        await bulk(
            client,
            auth_headers,
            {"ids": [cid], "op": "move", "target_list_id": target},
        )
        assert (await card_state(client, auth_headers, cid))["list_id"] == target

    async def test_move_foreign_target_404(
        self, client, auth_headers, other_headers, seeded
    ):
        detail, c = seeded
        theirs = await create_board(client, other_headers, name="Yabancı")
        await bulk(
            client,
            auth_headers,
            {
                "ids": [c["old1"]["id"]],
                "op": "move",
                "target_list_id": theirs["lists"][0]["id"],
            },
            expect=404,
        )
        st = await card_state(client, auth_headers, c["old1"]["id"])
        assert st["list_id"] == detail["lists"][1]["id"]


class TestPatPolicy:
    """Faz 13h1: yeni uçlar için bilinçli PAT politikası (pat_policy.py'de değişiklik yok)."""

    async def test_read_pat_reads_but_cannot_bulk(self, client, auth_headers, seeded):
        from tests.integration.test_api_tokens import bearer, make_token

        detail, c = seeded
        read = (await make_token(client, auth_headers, scopes=["read"])).json()["data"][
            "token"
        ]
        write = (
            await make_token(client, auth_headers, scopes=["read", "write"], name="W")
        ).json()["data"]["token"]
        board_id = detail["board"]["id"]
        res = await client.get(
            f"{API}/boards/{board_id}/sweep-candidates", headers=bearer(read)
        )
        assert res.status_code == 200, res.text
        res = await client.get(
            f"{API}/reports/work-summary",
            params={"date": "2026-11-10"},
            headers=bearer(read),
        )
        assert res.status_code == 200, res.text
        body = {"ids": [c["old1"]["id"]], "op": "archive"}
        res = await client.post(f"{API}/cards/bulk", json=body, headers=bearer(read))
        assert res.status_code == 403
        res = await client.post(f"{API}/cards/bulk", json=body, headers=bearer(write))
        assert res.status_code == 200, res.text
