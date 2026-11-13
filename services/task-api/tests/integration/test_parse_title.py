from datetime import datetime

from httpx import AsyncClient

URL = "/api/v1/cards/parse-title"


class TestParseTitle:
    async def test_requires_auth(self, client: AsyncClient):
        r = await client.post(URL, json={"text": "Fatura yarın"})
        assert r.status_code == 401

    async def test_basic(self, client: AsyncClient, auth_headers):
        r = await client.post(
            URL,
            json={"text": "Fatura öde yarın 15'te", "now": "2026-11-12T07:00:00+00:00"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        m = r.json()["data"]["match"]
        assert m["clean_title"] == "Fatura öde"
        assert m["has_time"] is True
        assert datetime.fromisoformat(m["due_date"]) == datetime.fromisoformat(
            "2026-11-13T15:00:00+03:00"
        )
        assert isinstance(m["spans"][0], list)

    async def test_no_match(self, client: AsyncClient, auth_headers):
        r = await client.post(URL, json={"text": "Fatura"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["match"] is None

    async def test_timezone(self, client: AsyncClient, auth_headers):
        body = {"text": "Rapor yarın", "now": "2026-11-12T22:30:00+00:00"}
        r = await client.post(URL, json=body, headers=auth_headers)
        due = r.json()["data"]["match"]["due_date"]
        assert datetime.fromisoformat(due) == datetime.fromisoformat(
            "2026-11-14T23:59:00+03:00"
        )
        await client.put(
            "/api/v1/settings/", json={"timezone": "UTC"}, headers=auth_headers
        )
        r = await client.post(URL, json=body, headers=auth_headers)
        due = r.json()["data"]["match"]["due_date"]
        assert datetime.fromisoformat(due) == datetime.fromisoformat(
            "2026-11-13T23:59:00+00:00"
        )

    async def test_week_start(self, client: AsyncClient, auth_headers):
        body = {"text": "Yürüyüş haftaya pazar", "now": "2026-11-12T07:00:00+00:00"}
        r = await client.post(URL, json=body, headers=auth_headers)
        assert r.json()["data"]["match"]["due_date"].startswith("2026-11-22")
        await client.put(
            "/api/v1/settings/", json={"week_start": 6}, headers=auth_headers
        )
        r = await client.post(URL, json=body, headers=auth_headers)
        assert r.json()["data"]["match"]["due_date"].startswith("2026-11-15")

    async def test_does_not_write(self, client: AsyncClient, auth_headers):
        before = (await client.get("/api/v1/boards", headers=auth_headers)).json()["data"]
        await client.post(URL, json={"text": "Rapor yarın"}, headers=auth_headers)
        after = (await client.get("/api/v1/boards", headers=auth_headers)).json()["data"]
        assert before == after

    async def test_too_long_rejected(self, client: AsyncClient, auth_headers):
        r = await client.post(URL, json={"text": "a" * 201}, headers=auth_headers)
        assert r.status_code == 422

    async def test_strong_flag(self, client: AsyncClient, auth_headers):
        now = "2026-11-13T07:00:00Z"
        r = await client.post(
            URL, json={"text": "Pazartesi toplantısı notları", "now": now}, headers=auth_headers
        )
        assert r.json()["data"]["match"]["strong"] is False
        r = await client.post(
            URL, json={"text": "yarın 15.00 da diş hekimi", "now": now}, headers=auth_headers
        )
        m = r.json()["data"]["match"]
        assert m["strong"] is True
        assert datetime.fromisoformat(m["due_date"]) == datetime.fromisoformat(
            "2026-11-14T15:00:00+03:00"
        )
        assert m["clean_title"] == "diş hekimi"
