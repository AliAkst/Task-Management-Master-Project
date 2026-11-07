from httpx import AsyncClient


class TestUserSettings:
    """GET/PUT /api/v1/settings testleri."""

    async def test_get_returns_defaults(self, client: AsyncClient, auth_headers):
        response = await client.get("/api/v1/settings/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["timezone"] == "Europe/Istanbul"
        assert data["planning_time"] is None
        assert data["review_time"] is None
        assert data["reminders_enabled"] is True
        assert data["week_start"] == 0

    async def test_partial_update(self, client: AsyncClient, auth_headers):
        response = await client.put(
            "/api/v1/settings/",
            json={"review_time": "22:00:00", "planning_time": "08:30:00"},
            headers=auth_headers,
        )
        assert response.status_code == 200

        data = (await client.get("/api/v1/settings/", headers=auth_headers)).json()[
            "data"
        ]
        assert data["review_time"] == "22:00:00"
        assert data["planning_time"] == "08:30:00"
        assert data["timezone"] == "Europe/Istanbul"  # dokunulmayan alan korunur

    async def test_invalid_timezone_rejected(self, client: AsyncClient, auth_headers):
        response = await client.put(
            "/api/v1/settings/", json={"timezone": "Mars/Olympus"}, headers=auth_headers
        )
        assert response.status_code == 422

    async def test_invalid_week_start_rejected(self, client: AsyncClient, auth_headers):
        response = await client.put(
            "/api/v1/settings/", json={"week_start": 7}, headers=auth_headers
        )
        assert response.status_code == 422

    async def test_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/settings/")
        assert response.status_code in (401, 403)
