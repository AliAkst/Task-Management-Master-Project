"""Faz 13h1: iş özeti (Markdown) ucu."""

from datetime import timedelta

import pytest

from app.services.timeutil import local_today
from tests.integration.test_boards_cards import API, create_board, create_card
from tests.integration.test_day_plans import TZ, at, log_time, review, save_plan

D = local_today(TZ) - timedelta(days=1)
URL = f"{API}/reports/work-summary"


@pytest.fixture
async def other_headers(client) -> dict[str, str]:
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def summary(client, headers, day=D, expect=200, **params):
    res = await client.get(URL, params={"date": str(day), **params}, headers=headers)
    assert res.status_code == expect, res.text
    return res.json()["data"]


async def test_empty_day_text(client, auth_headers):
    data = await summary(client, auth_headers)
    assert data["sections"] == {
        "completed": [],
        "worked": [],
        "not_done": [],
        "tomorrow": [],
    }
    assert data["text"].endswith("\n\nBu gün için kayıtlı iş yok.")
    assert data["text"].startswith("**İş özeti — ")


async def test_full_text_format(client, auth_headers):
    board = await create_board(client, auth_headers, name="Spor")
    todo = board["lists"][0]["id"]
    done_card = await create_card(client, auth_headers, todo, "Koşu")
    worked_card = await create_card(client, auth_headers, todo, "Rapor")
    skipped = await create_card(client, auth_headers, todo, "Vergi")
    await log_time(client, auth_headers, at(D, 9), at(D, 10, 30), done_card["id"])
    await log_time(client, auth_headers, at(D, 11), at(D, 11, 45), worked_card["id"])
    await save_plan(
        client,
        auth_headers,
        [
            {"card_id": done_card["id"], "title": "Koşu"},
            {"card_id": skipped["id"], "title": "Vergi"},
            {"title": "Kuyumcu"},
            {"title": "Fatura"},
        ],
    )
    plan = (await client.get(f"{API}/day-plans/{D}", headers=auth_headers)).json()["data"]
    ids = {i["title"]: i["id"] for i in plan["items"]}
    nxt = D + timedelta(days=3)
    await review(
        client,
        auth_headers,
        {
            "items": [
                {"id": ids["Koşu"], "outcome": "done"},
                {
                    "id": ids["Vergi"],
                    "outcome": "postponed",
                    "reason": "vakit yok",
                    "postponed_to": str(nxt),
                },
                {"id": ids["Kuyumcu"], "outcome": "done"},
                {"id": ids["Fatura"], "outcome": "not_done", "reason": "kapalıydı"},
            ]
        },
    )
    await save_plan(client, auth_headers, [{"title": "Yarınki iş"}], day=D + timedelta(days=1))
    data = await summary(client, auth_headers)
    s = data["sections"]
    assert {c["title"] for c in s["completed"]} == {"Koşu", "Kuyumcu"}
    assert next(c for c in s["completed"] if c["title"] == "Koşu")["minutes"] == 90
    assert s["worked"] == [{"title": "Rapor", "minutes": 45}]
    assert {n["title"]: n["reason"] for n in s["not_done"]} == {
        "Vergi": "vakit yok",
        "Fatura": "kapalıydı",
    }
    assert [t["title"] for t in s["tomorrow"]] == ["Yarınki iş"]
    text = data["text"]
    assert "**Tamamlananlar**\n- Koşu (1 sa 30 dk)" in text
    assert "- Kuyumcu\n" in text or text.count("- Kuyumcu") == 1
    assert "**Üzerinde çalışılanlar**\n- Rapor (45 dk)" in text
    assert "**Yapılamayanlar**" in text
    assert f"- Vergi — neden: vakit yok (→ {nxt.day} " in text
    assert "- Fatura — neden: kapalıydı" in text
    assert "**Yarın**\n- Yarınki iş" in text
    # sıra: Tamamlananlar < Üzerinde < Yapılamayanlar < Yarın
    order = [text.index(h) for h in ("**Tamamlananlar", "**Üzerinde", "**Yapılamayanlar", "**Yarın")]
    assert order == sorted(order)


async def test_board_filter_and_foreign_board_404(
    client, auth_headers, other_headers
):
    a = await create_board(client, auth_headers, name="A")
    b = await create_board(client, auth_headers, name="B")
    ca = await create_card(client, auth_headers, a["lists"][0]["id"], "Kart A")
    cb = await create_card(client, auth_headers, b["lists"][0]["id"], "Kart B")
    await log_time(client, auth_headers, at(D, 9), at(D, 10), ca["id"])
    await log_time(client, auth_headers, at(D, 10), at(D, 11), cb["id"])
    both = await summary(client, auth_headers)
    assert {w["title"] for w in both["sections"]["worked"]} == {"Kart A", "Kart B"}
    only_a = await summary(client, auth_headers, board_ids=str(a["board"]["id"]))
    assert [w["title"] for w in only_a["sections"]["worked"]] == ["Kart A"]
    foreign = await create_board(client, other_headers, name="Yabancı")
    await summary(
        client,
        auth_headers,
        expect=404,
        board_ids=f"{a['board']['id']},{foreign['board']['id']}",
    )
    await summary(client, auth_headers, expect=422, board_ids="abc")


async def test_minutes_format_variants(client, auth_headers):
    board = await create_board(client, auth_headers)
    todo = board["lists"][0]["id"]
    c1 = await create_card(client, auth_headers, todo, "Tam saat")
    await log_time(client, auth_headers, at(D, 9), at(D, 11), c1["id"])
    data = await summary(client, auth_headers)
    assert "- Tam saat (2 sa)" in data["text"]
