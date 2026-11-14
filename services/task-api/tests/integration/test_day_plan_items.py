"""Faz 12a: plan maddesi uclari (PATCH / to-card / move) ve korunan kaydetme."""

from datetime import UTC, datetime, time, timedelta

import pytest

from app.services.timeutil import local_today
from tests.integration.test_boards_cards import API, create_board, create_card
from tests.integration.test_day_plans import (
    TZ,
    D,
    activity,
    at,
    review,
    save_plan,
    suggestions,
)

T = local_today(TZ) + timedelta(days=1)


@pytest.fixture
async def spor(client, auth_headers):
    return await create_board(client, auth_headers, name="Spor", color="#22c55e")


@pytest.fixture
async def other_headers(client) -> dict[str, str]:
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def patch_item(client, headers, item_id, body, expect=200):
    res = await client.patch(
        f"{API}/day-plan-items/{item_id}", json=body, headers=headers
    )
    assert res.status_code == expect, res.text
    return res.json()


async def to_card(client, headers, item_id, body, expect=200):
    res = await client.post(
        f"{API}/day-plan-items/{item_id}/to-card", json=body, headers=headers
    )
    assert res.status_code == expect, res.text
    return res.json()


async def move(client, headers, item_id, body, expect=200):
    res = await client.post(
        f"{API}/day-plan-items/{item_id}/move", json=body, headers=headers
    )
    assert res.status_code == expect, res.text
    return res.json()


async def make_event(client, headers, day, hh, card_id=None, title="Blok", dur=1):
    body = {
        "title": title,
        "start_at": at(day, hh),
        "end_at": at(day, hh + dur),
    }
    if card_id:
        body["card_id"] = card_id
    res = await client.post(f"{API}/events", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()["data"]


def ids(plan):
    return [i["id"] for i in plan["items"]]


class TestSavePlan:
    async def test_put_keeps_outcome_with_id(self, client, auth_headers):
        plan = await save_plan(
            client, auth_headers, [{"title": "A"}, {"title": "B"}]
        )
        a, b = ids(plan)
        await patch_item(client, auth_headers, a, {"done": True})
        plan = await save_plan(
            client, auth_headers, [{"id": b}, {"id": a}]
        )
        assert ids(plan) == [b, a]
        by = {i["id"]: i for i in plan["items"]}
        assert by[a]["outcome"] == "done"
        assert by[b]["outcome"] is None

    async def test_put_without_id_matches_by_key(self, client, auth_headers, spor):
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "K")
        plan = await save_plan(
            client, auth_headers, [{"card_id": card["id"]}, {"title": "Serbest"}]
        )
        a, b = ids(plan)
        await patch_item(client, auth_headers, a, {"done": True})
        await patch_item(client, auth_headers, b, {"done": True})
        plan = await save_plan(
            client, auth_headers, [{"card_id": card["id"]}, {"title": "serbest"}]
        )
        assert ids(plan) == [a, b]
        assert all(i["outcome"] == "done" for i in plan["items"])

    async def test_put_unknown_id_treated_as_new(
        self, client, auth_headers, other_headers
    ):
        other = await save_plan(client, other_headers, [{"title": "Başkası"}])
        foreign = other["items"][0]["id"]
        plan = await save_plan(
            client, auth_headers, [{"id": foreign, "title": "Benim"}]
        )
        assert len(plan["items"]) == 1
        assert plan["items"][0]["id"] != foreign
        assert plan["items"][0]["title"] == "Benim"
        res = await client.get(f"{API}/day-plans/{D}", headers=other_headers)
        assert [i["id"] for i in res.json()["data"]["items"]] == [foreign]
        assert res.json()["data"]["items"][0]["title"] == "Başkası"

    async def test_put_unknown_id_without_ref_404(self, client, auth_headers):
        before = await save_plan(client, auth_headers, [{"title": "A"}])
        await save_plan(client, auth_headers, [{"id": 999999}], expect=404)
        res = await client.get(f"{API}/day-plans/{D}", headers=auth_headers)
        assert ids(res.json()["data"]) == ids(before)

    async def test_put_removes_unmatched(self, client, auth_headers):
        plan = await save_plan(
            client, auth_headers, [{"title": "A"}, {"title": "B"}, {"title": "C"}]
        )
        a, b, _c = ids(plan)
        plan = await save_plan(client, auth_headers, [{"id": a}, {"id": b}])
        assert ids(plan) == [a, b]

    async def test_put_event_attaches_to_card_row(self, client, auth_headers, spor):
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "K")
        plan = await save_plan(client, auth_headers, [{"card_id": card["id"]}])
        row = plan["items"][0]["id"]
        ev = await make_event(client, auth_headers, D, 9, card_id=card["id"])
        plan = await save_plan(
            client, auth_headers, [{"id": row}, {"event_id": ev["id"]}]
        )
        assert len(plan["items"]) == 1
        item = plan["items"][0]
        assert item["id"] == row
        assert item["event_id"] == ev["id"]
        assert item["planned_start"] is not None
        assert item["planned_minutes"] == 60

    async def test_put_duplicate_card_once(self, client, auth_headers, spor):
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "K")
        plan = await save_plan(
            client,
            auth_headers,
            [{"card_id": card["id"]}, {"card_id": card["id"]}],
        )
        assert len(plan["items"]) == 1

    async def test_put_planned_start_validation(self, client, auth_headers):
        plan = await save_plan(
            client,
            auth_headers,
            [{"title": "Saatli", "planned_start": at(D, 10)}],
        )
        assert plan["items"][0]["planned_start"] is not None
        await save_plan(
            client,
            auth_headers,
            [{"title": "Yanlış", "planned_start": at(D + timedelta(days=1), 10)}],
            expect=422,
        )

    async def test_put_title_duplicates_allowed(self, client, auth_headers):
        plan = await save_plan(
            client, auth_headers, [{"title": "Su iç"}, {"title": "Su iç"}]
        )
        assert len(plan["items"]) == 2

    async def test_put_reviewed_conflict(self, client, auth_headers):
        await save_plan(client, auth_headers, [{"title": "A"}])
        await review(client, auth_headers, {})
        await save_plan(client, auth_headers, [{"title": "B"}], expect=409)

    async def test_put_updates_minutes_only_when_given(self, client, auth_headers):
        plan = await save_plan(
            client, auth_headers, [{"title": "A", "planned_minutes": 25}]
        )
        a = plan["items"][0]["id"]
        plan = await save_plan(client, auth_headers, [{"id": a}])
        assert plan["items"][0]["planned_minutes"] == 25
        plan = await save_plan(
            client, auth_headers, [{"id": a, "planned_minutes": 40}]
        )
        assert plan["items"][0]["planned_minutes"] == 40


class TestPatch:
    async def test_patch_done_free_item(self, client, auth_headers):
        plan = await save_plan(client, auth_headers, [{"title": "A"}])
        a = plan["items"][0]["id"]
        res = await patch_item(client, auth_headers, a, {"done": True})
        assert res["data"]["items"][0]["outcome"] == "done"
        res = await patch_item(client, auth_headers, a, {"done": False})
        assert res["data"]["items"][0]["outcome"] is None

    async def test_patch_done_card_completes_card(self, client, auth_headers, spor):
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "K")
        plan = await save_plan(client, auth_headers, [{"card_id": card["id"]}])
        a = plan["items"][0]["id"]
        res = await patch_item(client, auth_headers, a, {"done": True})
        item = res["data"]["items"][0]
        assert item["outcome"] == "done"
        assert item["card_status"] == "completed"
        assert "completed" in await activity(client, auth_headers, card["id"])
        res = await patch_item(client, auth_headers, a, {"done": False})
        item = res["data"]["items"][0]
        assert item["outcome"] is None
        assert item["card_status"] == "pending"

    async def test_patch_fields(self, client, auth_headers):
        plan = await save_plan(client, auth_headers, [{"title": "A"}])
        a = plan["items"][0]["id"]
        res = await patch_item(
            client,
            auth_headers,
            a,
            {"title": "Yeni", "planned_minutes": 15, "planned_start": at(D, 11)},
        )
        item = res["data"]["items"][0]
        assert item["title"] == "Yeni"
        assert item["planned_minutes"] == 15
        assert item["planned_start"] is not None
        res = await patch_item(client, auth_headers, a, {"planned_start": None})
        assert res["data"]["items"][0]["planned_start"] is None

    async def test_patch_reviewed_day_only_done(self, client, auth_headers):
        plan = await save_plan(client, auth_headers, [{"title": "A"}])
        a = plan["items"][0]["id"]
        await review(client, auth_headers, {})
        await patch_item(client, auth_headers, a, {"done": True})
        await patch_item(client, auth_headers, a, {"title": "x"}, expect=409)

    async def test_patch_rules(self, client, auth_headers, other_headers, spor):
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "K")
        ev = await make_event(client, auth_headers, D, 9, title="Etk")
        plan = await save_plan(
            client,
            auth_headers,
            [{"card_id": card["id"]}, {"event_id": ev["id"]}, {"title": "S"}],
        )
        c, e, s = ids(plan)
        await patch_item(client, auth_headers, c, {"title": "x"}, expect=422)
        await patch_item(
            client, auth_headers, e, {"planned_start": at(D, 12)}, expect=422
        )
        await patch_item(client, auth_headers, s, {}, expect=422)
        await patch_item(client, auth_headers, s, {"done": True})
        await patch_item(client, other_headers, s, {"done": True}, expect=404)


class TestToCard:
    async def test_to_card_creates_card(self, client, auth_headers, spor):
        plan = await save_plan(
            client, auth_headers, [{"title": "Fatura", "planned_minutes": 30}]
        )
        a = plan["items"][0]["id"]
        res = await to_card(client, auth_headers, a, {"board_id": spor["board"]["id"]})
        item = res["data"]["items"][0]
        assert item["card_id"] is not None
        assert item["board_id"] == spor["board"]["id"]
        card = (
            await client.get(f"{API}/cards/{item['card_id']}", headers=auth_headers)
        ).json()["data"]
        assert card["title"] == "Fatura"
        assert card["estimated_minutes"] == 30
        assert card["list_id"] == spor["lists"][0]["id"]
        due = datetime.fromisoformat(card["due_date"].replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        assert due.astimezone(TZ) == datetime.combine(D, time(23, 59), tzinfo=TZ)
        assert "planned" in await activity(client, auth_headers, card["id"])

    async def test_to_card_links_event(self, client, auth_headers, spor):
        ev = await make_event(client, auth_headers, D, 9, title="Toplantı")
        plan = await save_plan(client, auth_headers, [{"event_id": ev["id"]}])
        a = plan["items"][0]["id"]
        res = await to_card(client, auth_headers, a, {"board_id": spor["board"]["id"]})
        card_id = res["data"]["items"][0]["card_id"]
        got = await client.get(f"{API}/events/{ev['id']}", headers=auth_headers)
        assert got.json()["data"]["card_id"] == card_id

    async def test_to_card_done_item_completes_card(self, client, auth_headers, spor):
        plan = await save_plan(client, auth_headers, [{"title": "Bitti"}])
        a = plan["items"][0]["id"]
        await patch_item(client, auth_headers, a, {"done": True})
        res = await to_card(client, auth_headers, a, {"board_id": spor["board"]["id"]})
        assert res["data"]["items"][0]["card_status"] == "completed"

    async def test_to_card_rules(self, client, auth_headers, other_headers, spor):
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "K")
        plan = await save_plan(
            client, auth_headers, [{"card_id": card["id"]}, {"title": "S"}]
        )
        c, s = ids(plan)
        res = await client.post(
            f"{API}/day-plan-items/{c}/to-card",
            json={"board_id": spor["board"]["id"]},
            headers=auth_headers,
        )
        assert res.status_code == 409 and "ITEM_HAS_CARD" in res.text
        await to_card(client, auth_headers, s, {}, expect=422)
        other_board = await create_board(client, other_headers, name="Başkası")
        await to_card(
            client, auth_headers, s, {"board_id": other_board["board"]["id"]}, expect=404
        )
        await to_card(client, other_headers, s, {"board_id": spor["board"]["id"]}, expect=404)


class TestMove:
    async def test_move_to_next_day(self, client, auth_headers):
        plan = await save_plan(client, auth_headers, [{"title": "Taşı"}], day=T)
        a = plan["items"][0]["id"]
        await move(client, auth_headers, a, {})
        src = await client.get(f"{API}/day-plans/{T}", headers=auth_headers)
        assert src.json()["data"]["items"] == []
        dst = await client.get(
            f"{API}/day-plans/{T + timedelta(days=1)}", headers=auth_headers
        )
        items = dst.json()["data"]["items"]
        assert [i["title"] for i in items] == ["Taşı"]
        assert items[0]["event_id"] is None and items[0]["planned_start"] is None

    async def test_move_dedupes_target(self, client, auth_headers):
        T2 = T + timedelta(days=1)
        plan = await save_plan(client, auth_headers, [{"title": "Aynı"}], day=T)
        await save_plan(client, auth_headers, [{"title": "aynı"}], day=T2)
        await move(client, auth_headers, plan["items"][0]["id"], {"date": str(T2)})
        dst = await client.get(f"{API}/day-plans/{T2}", headers=auth_headers)
        assert len(dst.json()["data"]["items"]) == 1

    async def test_move_card_item_keeps_card(self, client, auth_headers, spor):
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "K")
        plan = await save_plan(
            client, auth_headers, [{"card_id": card["id"]}], day=T
        )
        await move(client, auth_headers, plan["items"][0]["id"], {})
        dst = await client.get(
            f"{API}/day-plans/{T + timedelta(days=1)}", headers=auth_headers
        )
        assert dst.json()["data"]["items"][0]["card_id"] == card["id"]
        assert "planned" in await activity(client, auth_headers, card["id"])

    async def test_move_rules(self, client, auth_headers, other_headers):
        T2 = T + timedelta(days=1)
        src = await save_plan(client, auth_headers, [{"title": "A"}], day=T)
        a = src["items"][0]["id"]
        # hedef degerlendirilmis
        await save_plan(client, auth_headers, [{"title": "B"}], day=T2)
        await review(client, auth_headers, {}, day=T2)
        await move(client, auth_headers, a, {"date": str(T2)}, expect=409)
        # gecmis / ayni gun
        await move(client, auth_headers, a, {"date": str(D)}, expect=422)
        await move(client, auth_headers, a, {"date": str(T)}, expect=422)
        # baska kullanici
        await move(client, other_headers, a, {}, expect=404)
        # kaynak degerlendirilmis
        await review(client, auth_headers, {}, day=T)
        await move(
            client, auth_headers, a, {"date": str(T + timedelta(days=2))}, expect=409
        )

    async def test_move_unplanned_rejected(self, client, auth_headers):
        await save_plan(client, auth_headers, [{"title": "A"}])
        rv = await review(
            client,
            auth_headers,
            {"unplanned": [{"title": "Plansız", "outcome": "done"}]},
        )
        extra = next(i for i in rv["items"] if not i["was_planned"])
        await move(client, auth_headers, extra["id"], {}, expect=422)


class TestSuggestions:
    async def test_free_carry_over_marked_planned(self, client, auth_headers):
        plan = await save_plan(client, auth_headers, [{"title": "Ertelenen iş"}])
        a = plan["items"][0]["id"]
        await review(
            client,
            auth_headers,
            {"items": [{"id": a, "outcome": "postponed"}]},
        )
        day2 = D + timedelta(days=1)
        carry = [
            s
            for s in await suggestions(client, auth_headers, day2)
            if s["kind"] == "carry_over"
        ]
        assert len(carry) == 1 and carry[0]["already_planned"] is False
        await save_plan(
            client, auth_headers, [{"title": "ertelenen iş"}], day=day2
        )
        carry = [
            s
            for s in await suggestions(client, auth_headers, day2)
            if s["kind"] == "carry_over"
        ]
        assert carry[0]["already_planned"] is True


class TestAuditFixesFaz12:
    async def test_move_done_item_rejected(self, client, auth_headers):
        """D3: tamamlanmis madde tasinirsa outcome kaybolurdu -> 422."""
        plan = await save_plan(client, auth_headers, [{"title": "X"}], day=T)
        a = plan["items"][0]["id"]
        await patch_item(client, auth_headers, a, {"done": True})
        await move(client, auth_headers, a, {}, expect=422)
        # tamamlanmamis hala tasinabilir
        await patch_item(client, auth_headers, a, {"done": False})
        await move(client, auth_headers, a, {}, expect=200)
