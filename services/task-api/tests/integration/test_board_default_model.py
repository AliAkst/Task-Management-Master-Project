"""Faz 5c: board bazli varsayilan model ve gizlilik kurali."""

from httpx import AsyncClient

from tests.integration.test_boards_cards import API, create_board


async def test_board_default_model_roundtrip(client: AsyncClient, auth_headers):
    detail = await create_board(
        client, auth_headers, default_model_id="anthropic:claude-sonnet-5-5"
    )
    board = detail["board"]
    assert board["default_model_id"] == "anthropic:claude-sonnet-5-5"
    res = await client.patch(
        f"{API}/boards/{board['id']}",
        json={"default_model_id": None},
        headers=auth_headers,
    )
    assert res.status_code == 200 and res.json()["data"]["default_model_id"] is None


async def test_invalid_model_id_rejected(client: AsyncClient, auth_headers):
    res = await client.post(
        f"{API}/boards",
        json={"name": "X", "default_model_id": "bosluklu model"},
        headers=auth_headers,
    )
    assert res.status_code == 422


async def test_local_only_board_cannot_default_to_cloud(
    client: AsyncClient, auth_headers
):
    res = await client.post(
        f"{API}/boards",
        json={
            "name": "Gizli",
            "privacy": "local_only",
            "default_model_id": "openai:gpt-x",
        },
        headers=auth_headers,
    )
    assert res.status_code == 422
    detail = await create_board(
        client, auth_headers, privacy="local_only", default_model_id="ollama:gemma4:26b"
    )
    bid = detail["board"]["id"]
    res = await client.patch(
        f"{API}/boards/{bid}",
        json={"default_model_id": "anthropic:claude-haiku-5-5"},
        headers=auth_headers,
    )
    assert res.status_code == 422


async def test_switching_to_local_only_clears_cloud_default(
    client: AsyncClient, auth_headers
):
    detail = await create_board(
        client, auth_headers, default_model_id="gemini:gemini-x"
    )
    bid = detail["board"]["id"]
    res = await client.patch(
        f"{API}/boards/{bid}", json={"privacy": "local_only"}, headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["privacy"] == "local_only" and data["default_model_id"] is None
