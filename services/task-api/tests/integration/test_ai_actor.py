"""X-Actor: ai -> asistanin yaptigi islemler 'ai' olarak isaretlenir (Faz 5)."""

from tests.integration.test_boards_cards import API, create_board, create_card


async def test_ai_actor_marks_cards_events_and_history(client, auth_headers):
    board = await create_board(client, auth_headers)
    list_id = board["lists"][0]["id"]
    ai = {**auth_headers, "X-Actor": "ai"}

    res = await client.post(
        f"{API}/cards", json={"list_id": list_id, "title": "AI kartı"}, headers=ai
    )
    card = res.json()["data"]
    assert card["created_by"] == "ai"

    res = await client.post(
        f"{API}/cards/{card['id']}/split", json={"parts": 2}, headers=ai
    )
    assert {s["title"] for s in res.json()["data"]["subtasks"]}
    sub_id = res.json()["data"]["subtasks"][0]["id"]
    sub = (await client.get(f"{API}/cards/{sub_id}", headers=auth_headers)).json()[
        "data"
    ]
    assert sub["created_by"] == "ai"

    res = await client.post(
        f"{API}/events",
        json={
            "card_id": card["id"],
            "start_at": "2026-11-10T10:00:00Z",
            "end_at": "2026-11-10T11:00:00Z",
        },
        headers=ai,
    )
    assert res.json()["data"]["created_by"] == "ai"

    history = (
        await client.get(f"{API}/cards/{card['id']}/activity", headers=auth_headers)
    ).json()["data"]
    assert {a["actor"] for a in history} == {"ai"}

    # Basliksiz istek kullanici olarak kalir
    mine = await create_card(client, auth_headers, list_id, "Benim kartım")
    assert mine["created_by"] == "user"
