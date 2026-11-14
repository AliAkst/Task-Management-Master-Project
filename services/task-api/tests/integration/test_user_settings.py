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


class TestDayRollover:
    async def test_defaults(self, client: AsyncClient, auth_headers):
        data = (await client.get("/api/v1/settings/", headers=auth_headers)).json()["data"]
        assert data["day_rollover"] == "04:00:00"
        assert data["morning_time"] is None

    async def test_update_rollover_and_morning(self, client: AsyncClient, auth_headers):
        r = await client.put(
            "/api/v1/settings/",
            json={"day_rollover": "03:30", "morning_time": "07:45"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["day_rollover"] == "03:30:00" and data["morning_time"] == "07:45:00"
        r = await client.put(
            "/api/v1/settings/", json={"morning_time": None}, headers=auth_headers
        )
        assert r.json()["data"]["morning_time"] is None

    async def test_rollover_out_of_range_rejected(self, client: AsyncClient, auth_headers):
        for bad in ("06:30", "12:00", None):
            r = await client.put(
                "/api/v1/settings/", json={"day_rollover": bad}, headers=auth_headers
            )
            assert r.status_code == 422, bad
