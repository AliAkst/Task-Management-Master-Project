from datetime import date

from httpx import AsyncClient

MON, TUE, WED = date(2026, 12, 7), date(2026, 12, 8), date(2026, 12, 9)


def office(**kw):
    body = {
        "name": "Ofis günü",
        "weekdays": [0, 1],
        "blocks": [
            {"title": "Mesai", "start": "09:00", "end": "18:00", "kind": "mesai"},
            {"title": "Yol", "start": "07:00", "end": "09:00", "kind": "yol"},
        ],
        "day_start": "07:00",
        "day_end": "23:00",
        "buffer_min": 5,
    }
    body.update(kw)
    return body


async def make(client, headers, **kw):
    r = await client.post("/api/v1/day-templates", json=office(**kw), headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]


async def get_plan(client, headers, day):
    r = await client.get(f"/api/v1/day-plans/{day}", headers=headers)
    return r.json()["data"]


async def tpl_for(client, headers, day):
    r = await client.get(f"/api/v1/day-plans/{day}/template", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def put_tpl(client, headers, day, body):
    return await client.put(
        f"/api/v1/day-plans/{day}/template", json=body, headers=headers
    )


async def apply(client, headers, day, body=None):
    return await client.post(
        f"/api/v1/day-plans/{day}/apply-template", json=body or {}, headers=headers
    )


async def other_headers(client):
    u = {"email": "other@example.com", "password": "otherpass12345", "full_name": "O"}
    await client.post("/api/v1/auth/register", json=u)
    r = await client.post(
        "/api/v1/auth/login", json={"email": u["email"], "password": u["password"]}
    )
    return {"Authorization": f"bearer {r.json()['data']['access_token']}"}


class TestCrud:
    async def test_create_sorts_blocks_and_lists(self, client: AsyncClient, auth_headers):
        t = await make(client, auth_headers)
        assert [b["title"] for b in t["blocks"]] == ["Yol", "Mesai"]
        r = await client.get("/api/v1/day-templates", headers=auth_headers)
        assert [x["name"] for x in r.json()["data"]] == ["Ofis günü"]

    async def test_overlapping_blocks_422(self, client: AsyncClient, auth_headers):
        blocks = [
            {"title": "A", "start": "09:00", "end": "12:00", "kind": "mesai"},
            {"title": "B", "start": "11:00", "end": "13:00", "kind": "diger"},
        ]
        r = await client.post(
            "/api/v1/day-templates", json=office(blocks=blocks), headers=auth_headers
        )
        assert r.status_code == 422
        assert "Bloklar çakışıyor" in r.text

    async def test_bad_block_end_422(self, client: AsyncClient, auth_headers):
        blocks = [{"title": "A", "start": "10:00", "end": "10:00", "kind": "mesai"}]
        r = await client.post(
            "/api/v1/day-templates", json=office(blocks=blocks), headers=auth_headers
        )
        assert r.status_code == 422

    async def test_24_00_end_allowed(self, client: AsyncClient, auth_headers):
        blocks = [{"title": "Gece", "start": "22:00", "end": "24:00", "kind": "rutin"}]
        t = await make(client, auth_headers, blocks=blocks, weekdays=[])
        assert t["blocks"][0]["end"] == "24:00"

    async def test_buffer_and_day_range_422(self, client: AsyncClient, auth_headers):
        r = await client.post(
            "/api/v1/day-templates", json=office(buffer_min=7), headers=auth_headers
        )
        assert r.status_code == 422
        r = await client.post(
            "/api/v1/day-templates",
            json=office(day_start="20:00", day_end="10:00"),
            headers=auth_headers,
        )
        assert r.status_code == 422

    async def test_weekday_taken_409(self, client: AsyncClient, auth_headers):
        await make(client, auth_headers)
        r = await client.post(
            "/api/v1/day-templates",
            json=office(name="Ev günü", weekdays=[1, 2]),
            headers=auth_headers,
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "WEEKDAY_TAKEN"
        assert "Ofis günü" in r.json()["error"]["message"]

    async def test_duplicate_name_409(self, client: AsyncClient, auth_headers):
        await make(client, auth_headers)
        r = await client.post(
            "/api/v1/day-templates", json=office(weekdays=[]), headers=auth_headers
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "TEMPLATE_NAME_TAKEN"

    async def test_limit_409(self, client: AsyncClient, auth_headers):
        for i in range(10):
            await make(client, auth_headers, name=f"S{i}", weekdays=[])
        r = await client.post(
            "/api/v1/day-templates",
            json=office(name="S10", weekdays=[]),
            headers=auth_headers,
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "TOO_MANY_TEMPLATES"

    async def test_patch_and_delete(self, client: AsyncClient, auth_headers):
        t = await make(client, auth_headers)
        r = await client.patch(
            f"/api/v1/day-templates/{t['id']}",
            json={"name": "Yeni ad", "weekdays": [3]},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "Yeni ad"
        assert r.json()["data"]["weekdays"] == [3]
        # kendi gunlerini tekrar gondermek cakisma degildir
        r = await client.patch(
            f"/api/v1/day-templates/{t['id']}",
            json={"weekdays": [3]},
            headers=auth_headers,
        )
        assert r.status_code == 200
        r = await client.delete(f"/api/v1/day-templates/{t['id']}", headers=auth_headers)
        assert r.status_code == 204
        r = await client.get("/api/v1/day-templates", headers=auth_headers)
        assert r.json()["data"] == []

    async def test_patch_overlap_422(self, client: AsyncClient, auth_headers):
        t = await make(client, auth_headers)
        blocks = [
            {"title": "A", "start": "09:00", "end": "12:00", "kind": "mesai"},
            {"title": "B", "start": "11:00", "end": "13:00", "kind": "diger"},
        ]
        r = await client.patch(
            f"/api/v1/day-templates/{t['id']}",
            json={"blocks": blocks},
            headers=auth_headers,
        )
        assert r.status_code == 422

    async def test_other_users_template_404(self, client: AsyncClient, auth_headers):
        t = await make(client, auth_headers)
        other = await other_headers(client)
        r = await client.patch(
            f"/api/v1/day-templates/{t['id']}", json={"name": "x"}, headers=other
        )
        assert r.status_code == 404
        r = await client.delete(f"/api/v1/day-templates/{t['id']}", headers=other)
        assert r.status_code == 404
        r = await client.get("/api/v1/day-templates", headers=other)
        assert r.json()["data"] == []

    async def test_delete_template_clears_override(self, client: AsyncClient, auth_headers):
        home = await make(client, auth_headers, name="Ev günü", weekdays=[])
        await put_tpl(client, auth_headers, WED, {"mode": "template", "template_id": home["id"]})
        await client.delete(f"/api/v1/day-templates/{home['id']}", headers=auth_headers)
        assert (await tpl_for(client, auth_headers, WED))["source"] is None


class TestResolve:
    async def test_row4_none(self, client: AsyncClient, auth_headers):
        d = await tpl_for(client, auth_headers, MON)
        assert d["template"] is None and d["source"] is None

    async def test_row3_weekday(self, client: AsyncClient, auth_headers):
        t = await make(client, auth_headers)
        d = await tpl_for(client, auth_headers, MON)
        assert d["source"] == "weekday" and d["template"]["id"] == t["id"]
        assert (await tpl_for(client, auth_headers, WED))["source"] is None

    async def test_row2_override(self, client: AsyncClient, auth_headers):
        await make(client, auth_headers)
        home = await make(client, auth_headers, name="Ev günü", weekdays=[])
        r = await put_tpl(
            client, auth_headers, MON, {"mode": "template", "template_id": home["id"]}
        )
        assert r.status_code == 200
        d = await tpl_for(client, auth_headers, MON)
        assert d["source"] == "override" and d["template"]["id"] == home["id"]

    async def test_row1_off_wins(self, client: AsyncClient, auth_headers):
        await make(client, auth_headers)
        r = await put_tpl(client, auth_headers, MON, {"mode": "off"})
        assert r.status_code == 200
        d = await tpl_for(client, auth_headers, MON)
        assert d["source"] == "off" and d["template"] is None

    async def test_auto_resets(self, client: AsyncClient, auth_headers):
        await make(client, auth_headers)
        await put_tpl(client, auth_headers, MON, {"mode": "off"})
        await put_tpl(client, auth_headers, MON, {"mode": "auto"})
        assert (await tpl_for(client, auth_headers, MON))["source"] == "weekday"

    async def test_template_mode_needs_owned_id(self, client: AsyncClient, auth_headers):
        r = await put_tpl(client, auth_headers, MON, {"mode": "template"})
        assert r.status_code == 422
        other = await other_headers(client)
        theirs = (
            await client.post(
                "/api/v1/day-templates", json=office(weekdays=[]), headers=other
            )
        ).json()["data"]
        r = await put_tpl(
            client, auth_headers, MON, {"mode": "template", "template_id": theirs["id"]}
        )
        assert r.status_code == 404

    async def test_reviewed_day_409(self, client: AsyncClient, auth_headers):
        await make(client, auth_headers)
        await client.put(f"/api/v1/day-plans/{MON}", json={"items": []}, headers=auth_headers)
        await client.post(f"/api/v1/day-plans/{MON}/review", json={}, headers=auth_headers)
        r = await put_tpl(client, auth_headers, MON, {"mode": "off"})
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "PLAN_ALREADY_REVIEWED"
        r = await apply(client, auth_headers, MON)
        assert r.status_code == 409


class TestApply:
    async def test_no_template(self, client: AsyncClient, auth_headers):
        r = await apply(client, auth_headers, MON)
        assert r.status_code == 200
        assert r.json()["data"] == {"added": 0, "reason": "no_template"}

    async def test_apply_adds_blocks_in_time_order(self, client: AsyncClient, auth_headers):
        await make(client, auth_headers)
        r = await apply(client, auth_headers, MON)
        assert r.json()["data"] == {"added": 2, "reason": "applied"}
        items = (await get_plan(client, auth_headers, MON))["items"]
        assert [i["title"] for i in items] == ["Yol", "Mesai"]
        assert all(i["source"] == "template" and i["card_id"] is None for i in items)
        assert items[0]["planned_minutes"] == 120 and items[1]["planned_minutes"] == 540
        assert items[0]["planned_start"].startswith("2026-12-07T04:00:00")  # 07:00 +03

    async def test_idempotent_and_force_skips_same_title(
        self, client: AsyncClient, auth_headers
    ):
        await make(client, auth_headers)
        await apply(client, auth_headers, MON)
        r = await apply(client, auth_headers, MON)
        assert r.json()["data"] == {"added": 0, "reason": "already_applied"}
        r = await apply(client, auth_headers, MON, {"force": True})
        assert r.json()["data"]["added"] == 0
        assert len((await get_plan(client, auth_headers, MON))["items"]) == 2

    async def test_skips_existing_title_case_insensitive(
        self, client: AsyncClient, auth_headers
    ):
        await make(client, auth_headers)
        await client.put(
            f"/api/v1/day-plans/{MON}", json={"items": [{"title": "mesai"}]}, headers=auth_headers
        )
        r = await apply(client, auth_headers, MON)
        assert r.json()["data"]["added"] == 1

    async def test_put_with_ids_keeps_source_and_deleted_row_stays_gone(
        self, client: AsyncClient, auth_headers
    ):
        await make(client, auth_headers)
        await apply(client, auth_headers, MON)
        items = (await get_plan(client, auth_headers, MON))["items"]
        keep = [{"id": i["id"]} for i in items if i["title"] == "Yol"]
        r = await client.put(f"/api/v1/day-plans/{MON}", json={"items": keep}, headers=auth_headers)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert [i["title"] for i in items] == ["Yol"] and items[0]["source"] == "template"
        r = await apply(client, auth_headers, MON)
        assert r.json()["data"]["reason"] == "already_applied"
        assert len((await get_plan(client, auth_headers, MON))["items"]) == 1

    async def test_new_rows_have_no_source(self, client: AsyncClient, auth_headers):
        r = await client.put(
            f"/api/v1/day-plans/{MON}", json={"items": [{"title": "Elle"}]}, headers=auth_headers
        )
        assert r.json()["data"]["items"][0]["source"] is None

    async def test_template_applied_at_reported(self, client: AsyncClient, auth_headers):
        await make(client, auth_headers)
        assert (await tpl_for(client, auth_headers, MON))["applied_at"] is None
        await apply(client, auth_headers, MON)
        assert (await tpl_for(client, auth_headers, MON))["applied_at"] is not None
