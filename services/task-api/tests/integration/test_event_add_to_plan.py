"""Faz 12d: takvimde olusturulan etkinlik (add_to_plan) gunun planina da girer."""

from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.services.timeutil import local_today
from tests.integration.test_boards_cards import API, create_board, create_card
from tests.integration.test_day_plans import (
    TZ,
    D,
    activity,
    at,
    review,
    save_plan,
)

T = local_today(TZ) + timedelta(days=1)


@pytest.fixture
async def spor(client: AsyncClient, auth_headers):
    return await create_board(client, auth_headers, name="Spor", color="#22c55e")


async def make_event(client, headers, day, hh, mm=0, minutes=30, **extra):
    start = at(day, hh, mm)
    end_total = hh * 60 + mm + minutes
    end = at(day, end_total // 60, end_total % 60)
    body = {"start_at": start, "end_at": end, **extra}
    res = await client.post(f"{API}/events", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def plan(client, headers, day):
    res = await client.get(f"{API}/day-plans/{day}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def test_create_with_flag_adds_free_item(client, auth_headers):
    ev = await make_event(
        client, auth_headers, T, 10, title="Fatura", add_to_plan=True
    )
    data = await plan(client, auth_headers, T)
    assert data["exists"] is True and len(data["items"]) == 1
    item = data["items"][0]
    assert item["event_id"] == ev["id"] and item["card_id"] is None
    assert item["title"] == "Fatura" and item["planned_minutes"] == 30
    assert "10:00" in item["planned_start"] or "07:00" in item["planned_start"]


async def test_create_with_flag_card_attaches(client, auth_headers, spor):
    card = await create_card(client, auth_headers, spor["lists"][0]["id"], "Koş")
    await save_plan(client, auth_headers, [{"card_id": card["id"]}], day=T)
    ev = await make_event(
        client, auth_headers, T, 9, card_id=card["id"], add_to_plan=True
    )
    items = (await plan(client, auth_headers, T))["items"]
    assert len(items) == 1
    assert items[0]["event_id"] == ev["id"] and items[0]["card_id"] == card["id"]
    assert items[0]["planned_start"] is not None


async def test_create_with_flag_card_new_row(client, auth_headers, spor):
    card = await create_card(client, auth_headers, spor["lists"][0]["id"], "Yüz")
    ev = await make_event(
        client, auth_headers, T, 18, card_id=card["id"], add_to_plan=True
    )
    items = (await plan(client, auth_headers, T))["items"]
    assert len(items) == 1
    assert items[0]["card_id"] == card["id"] and items[0]["event_id"] == ev["id"]
    assert "planned" in await activity(client, auth_headers, card["id"])


async def test_create_without_flag_no_plan(client, auth_headers):
    await make_event(client, auth_headers, T, 10, title="Plansız")
    assert (await plan(client, auth_headers, T))["exists"] is False


async def test_create_flag_reviewed_day_skipped(client, auth_headers, spor):
    card = await create_card(client, auth_headers, spor["lists"][0]["id"], "Eski")
    saved = await save_plan(client, auth_headers, [{"card_id": card["id"]}], day=D)
    await review(
        client,
        auth_headers,
        {"items": [{"id": saved["items"][0]["id"], "outcome": "done"}]},
        day=D,
    )
    before = await plan(client, auth_headers, D)
    await make_event(client, auth_headers, D, 11, title="Geç", add_to_plan=True)
    after = await plan(client, auth_headers, D)
    assert [i["id"] for i in after["items"]] == [i["id"] for i in before["items"]]
    assert after["status"] == "reviewed"


async def test_create_flag_twice_no_duplicate(client, auth_headers, test_session):
    from app.db.unit_of_work import TaskUnitOfWork
    from app.services.day_plan import DayPlanService

    ev = await make_event(client, auth_headers, T, 10, title="Bir", add_to_plan=True)
    uow = TaskUnitOfWork(test_session)
    event = await uow.events.get_by_id(ev["id"])
    added = await DayPlanService(uow).add_event_item(event.user_id, event)
    assert added is False
    assert len((await plan(client, auth_headers, T))["items"]) == 1


async def test_update_moves_snapshot(client, auth_headers):
    ev = await make_event(client, auth_headers, T, 10, title="Taşı", add_to_plan=True)
    res = await client.patch(
        f"{API}/events/{ev['id']}",
        json={"start_at": at(T, 14), "end_at": at(T, 15)},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    item = (await plan(client, auth_headers, T))["items"][0]
    assert item["planned_minutes"] == 60
    assert "14:00" in item["planned_start"] or "11:00" in item["planned_start"]

    nxt = T + timedelta(days=1)
    res = await client.patch(
        f"{API}/events/{ev['id']}",
        json={"start_at": at(nxt, 9), "end_at": at(nxt, 10)},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    items = (await plan(client, auth_headers, T))["items"]
    assert len(items) == 1 and items[0]["planned_start"] is None
    assert (await plan(client, auth_headers, nxt))["exists"] is False
