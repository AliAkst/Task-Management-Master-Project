"""Faz 5b: hedefler."""

from tests.integration.test_boards_cards import API, create_board, create_card


async def test_goal_crud_and_history(client, auth_headers):
    board = await create_board(client, auth_headers, name="Eğitimler")
    card = await create_card(
        client, auth_headers, board["lists"][0]["id"], "Docker kursu"
    )
    res = await client.post(
        f"{API}/goals",
        json={
            "title": "Docker sertifikası almak",
            "why": "İşte daha fazla sorumluluk almak istiyorum",
            "target_date": "2027-03-01",
            "board_id": board["board"]["id"],
            "root_card_id": card["id"],
        },
        headers={**auth_headers, "X-Actor": "ai"},
    )
    assert res.status_code == 201, res.text
    goal = res.json()["data"]
    assert goal["status"] == "active" and goal["created_by"] == "ai"

    res = await client.patch(
        f"{API}/goals/{goal['id']}", json={"status": "achieved"}, headers=auth_headers
    )
    assert res.json()["data"]["status"] == "achieved"

    active = await client.get(
        f"{API}/goals", params={"status": "active"}, headers=auth_headers
    )
    assert active.json()["data"] == []
    everything = await client.get(f"{API}/goals", headers=auth_headers)
    assert [g["title"] for g in everything.json()["data"]] == [
        "Docker sertifikası almak"
    ]

    res = await client.delete(f"{API}/goals/{goal['id']}", headers=auth_headers)
    assert res.status_code == 204


async def test_goal_validation_and_ownership(client, auth_headers):
    res = await client.post(f"{API}/goals", json={"title": ""}, headers=auth_headers)
    assert res.status_code == 422
    res = await client.post(
        f"{API}/goals", json={"title": "x", "board_id": 999}, headers=auth_headers
    )
    assert res.status_code == 404

    goal = (
        await client.post(f"{API}/goals", json={"title": "Benim"}, headers=auth_headers)
    ).json()["data"]
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    token = (await client.post(f"{API}/auth/login", json=creds)).json()["data"][
        "access_token"
    ]
    h = {"Authorization": f"Bearer {token}"}
    assert (await client.get(f"{API}/goals", headers=h)).json()["data"] == []
    res = await client.patch(
        f"{API}/goals/{goal['id']}", json={"title": "y"}, headers=h
    )
    assert res.status_code == 404
    assert (
        await client.delete(f"{API}/goals/{goal['id']}", headers=h)
    ).status_code == 404


async def test_deleting_board_or_card_keeps_goal(client, auth_headers):
    board = await create_board(client, auth_headers, name="Eğitimler")
    card = await create_card(client, auth_headers, board["lists"][0]["id"], "Kurs")
    goal = (
        await client.post(
            f"{API}/goals",
            json={
                "title": "Hedef",
                "board_id": board["board"]["id"],
                "root_card_id": card["id"],
            },
            headers=auth_headers,
        )
    ).json()["data"]
    await client.delete(f"{API}/cards/{card['id']}", headers=auth_headers)
    await client.delete(f"{API}/boards/{board['board']['id']}", headers=auth_headers)
    [g] = (await client.get(f"{API}/goals", headers=auth_headers)).json()["data"]
    assert (g["id"], g["board_id"], g["root_card_id"]) == (goal["id"], None, None)
