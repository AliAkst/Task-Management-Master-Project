"""Faz 13 T3-D4: asistan zamanlayicisinin kullandigi GET'ler `read` PAT ile calisir.

Zamanlayici (assistant-service/app/scheduler.py) task-api'ye `read` kapsamli PAT ile
girer ve yalniz bu uclari okur. Birisi `pat_policy.py`'ye bir yasak eklerse bu test
kirmizi olur (zamanlayici hatalari sessizce yutuyor, baska turlu fark edilmez).
"""

import pytest

from tests.integration.test_api_tokens import bearer, make_token
from tests.integration.test_boards_cards import API, create_board, create_card

DAY = "2026-11-10"
RANGE = {"start": "2026-11-10T00:00:00+03:00", "end": "2026-11-11T00:00:00+03:00"}

# assistant-service sahte yanitlarinin (tests/test_scheduler_jobs.py) kullandigi alanlar
CARD_KEYS = {
    "id",
    "title",
    "status",
    "board_id",
    "due_date",
    "blocked",
    "parent_id",
    "is_archived",
}
EVENT_KEYS = {"kind", "all_day", "event_id", "start", "title"}


@pytest.fixture
async def read_pat(client, auth_headers) -> str:
    res = await make_token(client, auth_headers, scopes=["read"])
    assert res.status_code == 201, res.text
    return res.json()["data"]["token"]


@pytest.fixture
async def seeded(client, auth_headers):
    board = await create_board(client, auth_headers)
    card = await create_card(client, auth_headers, board["lists"][0]["id"], "Vergi")
    ev = await client.post(
        f"{API}/events",
        json={
            "title": "Yoga",
            "start_at": "2026-11-10T10:00:00+03:00",
            "end_at": "2026-11-10T11:00:00+03:00",
        },
        headers=auth_headers,
    )
    assert ev.status_code == 201, ev.text
    return board, card


async def test_scheduler_gets_work_with_read_pat(client, read_pat, seeded):
    board, card = seeded
    h = bearer(read_pat)
    paths = [
        ("/settings/", None),
        (f"/day-plans/{DAY}", None),
        (f"/day-plans/{DAY}/template", None),
        ("/calendar", RANGE),
        ("/boards", {"include_archived": "true"}),
        (f"/boards/{board['board']['id']}", None),
        (f"/cards/{card['id']}", None),
        ("/analytics/summary", {"start": "2026-10-14", "end": DAY}),
        ("/learning/courses", None),  # 13g: sabah ozeti kurs satiri
    ]
    bodies = {}
    for path, params in paths:
        res = await client.get(f"{API}{path}", params=params, headers=h)
        assert res.status_code == 200, (path, res.status_code, res.text)
        bodies[path] = res.json()["data"]

    # asistanin okudugu alan adlari
    assert "timezone" in bodies["/settings/"]
    plan = bodies[f"/day-plans/{DAY}"]
    assert {"items"} <= set(plan)
    assert "template" in bodies[f"/day-plans/{DAY}/template"]
    cal = bodies["/calendar"]["items"]
    assert cal and EVENT_KEYS <= set(cal[0])
    assert bodies["/boards"] and {"id", "privacy"} <= set(bodies["/boards"][0])
    detail = bodies[f"/boards/{board['board']['id']}"]
    assert detail["cards"] and CARD_KEYS <= set(detail["cards"][0])
    assert "depends_on" in bodies[f"/cards/{card['id']}"]
    assert "most_postponed" in bodies["/analytics/summary"]


async def test_read_pat_cannot_write_settings(client, read_pat):
    res = await client.put(
        f"{API}/settings/", json={"timezone": "UTC"}, headers=bearer(read_pat)
    )
    assert res.status_code == 403
