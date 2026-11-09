"""Faz 8g: tema/zemin ayarlari ve board arka plani."""

from httpx import AsyncClient

from tests.integration.test_boards_cards import API, create_board


async def test_theme_settings_defaults_and_save(client: AsyncClient, auth_headers):
    data = (await client.get(f"{API}/settings/", headers=auth_headers)).json()["data"]
    assert data["theme"] == "system" and data["background"] == "kagit"
    res = await client.put(
        f"{API}/settings/",
        json={"theme": "dark", "background": "lavanta"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = (await client.get(f"{API}/settings/", headers=auth_headers)).json()["data"]
    assert data["theme"] == "dark" and data["background"] == "lavanta"
    assert data["timezone"] == "Europe/Istanbul"  # dokunulmayan alan korunur


async def test_theme_settings_invalid_rejected(client: AsyncClient, auth_headers):
    for body in ({"theme": "mor"}, {"background": "neon"}):
        res = await client.put(f"{API}/settings/", json=body, headers=auth_headers)
        assert res.status_code == 422


async def test_board_background_roundtrip(client: AsyncClient, auth_headers):
    detail = await create_board(client, auth_headers, background="deniz")
    board = detail["board"]
    assert board["background"] == "deniz"
    res = await client.patch(
        f"{API}/boards/{board['id']}", json={"background": "tint"}, headers=auth_headers
    )
    assert res.status_code == 200 and res.json()["data"]["background"] == "tint"
    res = await client.patch(
        f"{API}/boards/{board['id']}", json={"background": None}, headers=auth_headers
    )
    assert res.status_code == 200 and res.json()["data"]["background"] is None


async def test_board_background_invalid_rejected(client: AsyncClient, auth_headers):
    res = await client.post(
        f"{API}/boards", json={"name": "X", "background": "pembe"}, headers=auth_headers
    )
    assert res.status_code == 422
