"""Faz 13g: kurslar (ilerleme / ETA), iki aktif kural, oneri kancasi, kalibrasyon."""

from datetime import timedelta

import pytest

from app.services.timeutil import local_today
from tests.integration.test_api_tokens import bearer, make_token
from tests.integration.test_boards_cards import API, create_board, create_card
from tests.integration.test_day_plans import (
    TZ,
    D,
    at,
    log_time,
    review,
    save_plan,
    suggestions,
)


@pytest.fixture
async def edu(client, auth_headers):
    return await create_board(
        client, auth_headers, name="Eğitimler", weekly_time_budget_min=300
    )


@pytest.fixture
async def other_headers(client):
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def make_root(client, headers, board, title, parts):
    """Kok kart + cocuk parcalar [(baslik, tahmin_dk)]; (kok, [parca...])."""
    root = await create_card(client, headers, board["lists"][0]["id"], title)
    kids = []
    for part_title, est in parts:
        kw = {"estimated_minutes": est} if est else {}
        kids.append(
            await create_card(
                client, headers, board["lists"][0]["id"], part_title,
                parent_id=root["id"], **kw,
            )
        )
    return root, kids


async def complete(client, headers, card_id):
    res = await client.patch(
        f"{API}/cards/{card_id}", json={"status": "completed"}, headers=headers
    )
    assert res.status_code == 200, res.text


async def track(client, headers, root, include="active"):
    res = await client.post(
        f"{API}/learning/courses", json={"root_card_id": root["id"]}, headers=headers
    )
    return res


async def courses(client, headers, include="active"):
    res = await client.get(
        f"{API}/learning/courses", params={"include": include}, headers=headers
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


PARTS = [("P10 Modelleme", 60), ("P2 Veri", 60), ("P1 Giriş", 60), ("P3 (Opsiyonel) ek", 60)]


class TestCourses:
    async def test_next_part_follows_natural_order(self, client, auth_headers, edu):
        root, kids = await make_root(client, auth_headers, edu, "Power BI Kursu", PARTS)
        res = await track(client, auth_headers, root)
        assert res.status_code == 201, res.text
        c = res.json()["data"]
        assert c["title"] == "Power BI Kursu" and c["status"] == "active"
        assert (c["parts_total"], c["parts_done"]) == (4, 0)
        assert c["next_part"]["title"] == "P1 Giriş"
        by = {k["title"]: k["id"] for k in kids}
        await complete(client, auth_headers, by["P1 Giriş"])
        await complete(client, auth_headers, by["P2 Veri"])
        c = (await courses(client, auth_headers))[0]
        assert (c["parts_done"], c["next_part"]["title"]) == (2, "P10 Modelleme")
        await complete(client, auth_headers, by["P10 Modelleme"])
        c = (await courses(client, auth_headers))[0]
        # Opsiyonel parca en sonda; yine de "siradaki" olur (baska parca kalmadi)
        assert c["next_part"]["title"] == "P3 (Opsiyonel) ek"
        await complete(client, auth_headers, by["P3 (Opsiyonel) ek"])
        c = (await courses(client, auth_headers))[0]
        assert c["next_part"] is None and c["eta_reason"] == "done"
        assert c["remaining_minutes"] == 0

    async def test_velocity_and_eta_from_board_budget(self, client, auth_headers, edu):
        root, kids = await make_root(client, auth_headers, edu, "Fabric", PARTS)
        await track(client, auth_headers, root)
        await complete(client, auth_headers, kids[0]["id"])
        c = (await courses(client, auth_headers))[0]
        assert c["velocity_per_week"] == 0.25  # 28 gunde 1 parca / 4 hafta
        assert c["remaining_minutes"] == 180  # 3 x 60, kalibrasyon yok -> 1.0
        # 180 / 300 hafta = 0.6 hafta -> ceil(4.2) = 5 gun
        assert c["eta_reason"] == "ok"
        assert c["eta_date"] == str(local_today(TZ) + timedelta(days=5))

    async def test_velocity_window_is_28_days(
        self, client, auth_headers, edu, monkeypatch
    ):
        root, kids = await make_root(client, auth_headers, edu, "Eski", PARTS)
        await track(client, auth_headers, root)
        await complete(client, auth_headers, kids[0]["id"])
        from datetime import UTC, datetime

        future = datetime.now(UTC) + timedelta(days=40)
        monkeypatch.setattr("app.services.learning._now", lambda: future)
        c = (await courses(client, auth_headers))[0]
        assert c["velocity_per_week"] is None

    async def test_no_budget_no_sessions_is_no_velocity(self, client, auth_headers):
        board = await create_board(client, auth_headers, name="Bütçesiz")
        root, _ = await make_root(client, auth_headers, board, "Kurs", PARTS)
        await track(client, auth_headers, root)
        c = (await courses(client, auth_headers))[0]
        assert c["eta_reason"] == "no_velocity" and c["eta_date"] is None
        assert c["velocity_per_week"] is None and c["remaining_minutes"] == 240

    async def test_budget_falls_back_to_tracked_minutes(self, client, auth_headers):
        board = await create_board(client, auth_headers, name="Bütçesiz")
        root, kids = await make_root(client, auth_headers, board, "Kurs", PARTS)
        await track(client, auth_headers, root)
        # Dun 2 saat parca uzerinde: 120 dk / 4 hafta = 30 dk/hafta
        await log_time(client, auth_headers, at(D, 9), at(D, 11), kids[0]["id"])
        c = (await courses(client, auth_headers))[0]
        assert c["eta_reason"] == "ok"
        # 240 dk / 30 dk-hafta = 8 hafta = 56 gun
        assert c["eta_date"] == str(local_today(TZ) + timedelta(days=56))

    async def test_missing_estimates_use_median_then_sixty(self, client, auth_headers):
        board = await create_board(client, auth_headers, name="B")
        root, _ = await make_root(
            client, auth_headers, board, "K", [("P1 a", 30), ("P2 b", 50), ("P3 c", None)]
        )
        await track(client, auth_headers, root)
        c = (await courses(client, auth_headers))[0]
        assert c["remaining_minutes"] == 30 + 50 + 50  # medyan(30,50) -> 50 (ust orta)
        root2, _ = await make_root(
            client, auth_headers, board, "K2", [("P1 a", None), ("P2 b", None)]
        )
        await track(client, auth_headers, root2)
        c2 = next(x for x in await courses(client, auth_headers) if x["title"] == "K2")
        assert c2["remaining_minutes"] == 120  # tahmin yok -> parca basina 60

    async def test_include_active_vs_all(self, client, auth_headers, edu):
        root, _ = await make_root(client, auth_headers, edu, "A", PARTS)
        goal = (await track(client, auth_headers, root)).json()["data"]
        await client.patch(
            f"{API}/goals/{goal['goal_id']}",
            json={"status": "dropped"},
            headers=auth_headers,
        )
        assert await courses(client, auth_headers) == []
        assert len(await courses(client, auth_headers, "all")) == 1
        await client.patch(
            f"{API}/goals/{goal['goal_id']}",
            json={"status": "paused"},
            headers=auth_headers,
        )
        assert [c["status"] for c in await courses(client, auth_headers)] == ["paused"]

    async def test_goal_without_root_is_not_a_course(self, client, auth_headers):
        await client.post(f"{API}/goals", json={"title": "Sade"}, headers=auth_headers)
        assert await courses(client, auth_headers, "all") == []

    async def test_other_user_sees_nothing(
        self, client, auth_headers, other_headers, edu
    ):
        root, _ = await make_root(client, auth_headers, edu, "Benim", PARTS)
        await track(client, auth_headers, root)
        assert await courses(client, other_headers, "all") == []
        res = await track(client, other_headers, root)
        assert res.status_code == 404  # baskasinin karti


class TestCreateCourse:
    async def test_rules(self, client, auth_headers, edu):
        lonely = await create_card(client, auth_headers, edu["lists"][0]["id"], "Tek")
        res = await track(client, auth_headers, lonely)
        assert res.status_code == 422
        assert "alt parçası yok" in res.text
        assert (
            await client.post(
                f"{API}/learning/courses", json={"root_card_id": 9999}, headers=auth_headers
            )
        ).status_code == 404

        r1, _ = await make_root(client, auth_headers, edu, "K1", PARTS)
        r2, _ = await make_root(client, auth_headers, edu, "K2", PARTS)
        r3, _ = await make_root(client, auth_headers, edu, "K3", PARTS)
        assert (await track(client, auth_headers, r1)).json()["data"]["status"] == "active"
        dup = await track(client, auth_headers, r1)
        assert dup.status_code == 409 and dup.json()["error"]["code"] == "COURSE_EXISTS"
        assert (await track(client, auth_headers, r2)).json()["data"]["status"] == "active"
        # Ucuncusu otomatik duraklatilmis olusur
        assert (await track(client, auth_headers, r3)).json()["data"]["status"] == "paused"


class TestTwoActiveRule:
    async def _two_active(self, client, headers, board):
        roots = []
        for n in ("K1", "K2", "K3"):
            roots.append((await make_root(client, headers, board, n, PARTS))[0])
        gids = []
        for r in roots:
            gids.append((await track(client, headers, r)).json()["data"]["goal_id"])
        return roots, gids  # ucuncu paused

    async def test_patch_third_active_is_409(self, client, auth_headers, edu):
        _, gids = await self._two_active(client, auth_headers, edu)
        res = await client.patch(
            f"{API}/goals/{gids[2]}", json={"status": "active"}, headers=auth_headers
        )
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "TOO_MANY_ACTIVE_COURSES"
        assert "En fazla 2 aktif kurs" in res.text
        # Biri duraklatilinca ucuncu aktif olabilir
        await client.patch(
            f"{API}/goals/{gids[0]}", json={"status": "paused"}, headers=auth_headers
        )
        res = await client.patch(
            f"{API}/goals/{gids[2]}", json={"status": "active"}, headers=auth_headers
        )
        assert res.status_code == 200

    async def test_create_goal_with_root_third_active_is_409(
        self, client, auth_headers, edu
    ):
        await self._two_active(client, auth_headers, edu)
        root, _ = await make_root(client, auth_headers, edu, "K4", PARTS)
        res = await client.post(
            f"{API}/goals",
            json={"title": "Yeni", "root_card_id": root["id"]},
            headers=auth_headers,
        )
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "TOO_MANY_ACTIVE_COURSES"

    async def test_attaching_root_to_active_goal_counts(
        self, client, auth_headers, edu
    ):
        await self._two_active(client, auth_headers, edu)
        plain = (
            await client.post(f"{API}/goals", json={"title": "Sade"}, headers=auth_headers)
        ).json()["data"]
        root, _ = await make_root(client, auth_headers, edu, "K5", PARTS)
        res = await client.patch(
            f"{API}/goals/{plain['id']}",
            json={"root_card_id": root["id"]},
            headers=auth_headers,
        )
        assert res.status_code == 409

    async def test_goals_without_root_are_unaffected(self, client, auth_headers, edu):
        await self._two_active(client, auth_headers, edu)
        for n in range(3):
            res = await client.post(
                f"{API}/goals", json={"title": f"Hedef {n}"}, headers=auth_headers
            )
            assert res.status_code == 201
        res = await client.patch(
            f"{API}/goals/{res.json()['data']['id']}",
            json={"status": "active", "title": "x"},
            headers=auth_headers,
        )
        assert res.status_code == 200

    async def test_active_to_active_patch_is_fine(self, client, auth_headers, edu):
        _, gids = await self._two_active(client, auth_headers, edu)
        res = await client.patch(
            f"{API}/goals/{gids[0]}",
            json={"status": "active", "why": "neden"},
            headers=auth_headers,
        )
        assert res.status_code == 200


class TestCourseSuggestions:
    async def test_course_kind_and_planned_part_skipped(
        self, client, auth_headers, edu
    ):
        root, kids = await make_root(client, auth_headers, edu, "Kurs", PARTS)
        root2, _ = await make_root(client, auth_headers, edu, "Paused", PARTS)
        await track(client, auth_headers, root)
        assert root2["id"]  # duraklatilmis degil, kurs olarak takip edilmiyor
        items = await suggestions(client, auth_headers)
        course = [i for i in items if i["kind"] == "course"]
        assert [i["title"] for i in course] == ["P1 Giriş"]
        assert course[0]["reason"] == "Sıradaki kurs parçası (Kurs)"
        assert course[0]["planned_minutes"] == 60
        # Parca o gun planda ise onerilmez
        p1 = next(k for k in kids if k["title"] == "P1 Giriş")
        await save_plan(client, auth_headers, [{"card_id": p1["id"]}])
        items = await suggestions(client, auth_headers)
        assert [i for i in items if i["kind"] == "course"] == []

    async def test_paused_course_not_suggested_and_max_two(
        self, client, auth_headers, edu
    ):
        for n in ("K1", "K2", "K3"):
            root, _ = await make_root(client, auth_headers, edu, n, PARTS)
            await track(client, auth_headers, root)  # 3. paused
        items = await suggestions(client, auth_headers)
        assert len([i for i in items if i["kind"] == "course"]) == 2


class TestCalibration:
    _seq = 0

    async def _finish_cards(self, client, headers, board, n, est=30):
        """n kart: tahmin est dk, dun 60 dk izlendi, tamamlandi (oran 2.0)."""
        for _ in range(n):
            TestCalibration._seq += 1
            k = TestCalibration._seq
            card = await create_card(
                client, headers, board["lists"][0]["id"], f"Is {k}", estimated_minutes=est
            )
            await log_time(client, headers, at(D, 1 + k), at(D, 2 + k), card["id"])
            await complete(client, headers, card["id"])

    async def _summary(self, client, headers):
        res = await client.get(
            f"{API}/analytics/summary",
            params={"start": str(D - timedelta(days=6)), "end": str(local_today(TZ))},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        return res.json()["data"]["estimate_accuracy"]

    async def test_by_board_cards(self, client, auth_headers, edu):
        await self._finish_cards(client, auth_headers, edu, 3)  # 30 dk tahmin, 60 dk gercek
        acc = await self._summary(client, auth_headers)
        assert acc["by_board"] == [
            {"board_id": edu["board"]["id"], "samples": 3, "median_ratio": 2.0}
        ]
        assert acc["sample_size"] == 3  # genel kural degismedi

    async def test_short_sessions_are_not_board_samples(self, client, auth_headers, edu):
        card = await create_card(
            client, auth_headers, edu["lists"][0]["id"], "Kısa", estimated_minutes=10
        )
        await log_time(client, auth_headers, at(D, 8), at(D, 8, 4), card["id"])  # 4 dk
        await complete(client, auth_headers, card["id"])
        acc = await self._summary(client, auth_headers)
        assert acc["by_board"] == []
        assert acc["sample_size"] == 1  # genel orandaki >= 60 sn kurali ayni

    async def test_by_board_includes_cardless_done_items(self, client, auth_headers, edu):
        board_id = edu["board"]["id"]
        ev = await client.post(
            f"{API}/events",
            json={
                "title": "Ders", "board_id": board_id,
                "start_at": at(D, 20), "end_at": at(D, 20, 30),
            },
            headers=auth_headers,
        )
        assert ev.status_code == 201, ev.text
        plan = await save_plan(client, auth_headers, [{"event_id": ev.json()["data"]["id"]}])
        item = plan["items"][0]
        assert item["card_id"] is None and item["board_id"] == board_id
        res = await client.post(
            f"{API}/sessions",
            json={
                "day_plan_item_id": item["id"],
                "started_at": at(D, 20), "ended_at": at(D, 21, 0),
            },
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
        await review(
            client, auth_headers,
            {"items": [{"id": item["id"], "outcome": "done"}]},
        )
        acc = await self._summary(client, auth_headers)
        # planned 30 dk, izlenen 60 dk -> oran 2.0; tek ornek
        assert acc["by_board"] == [{"board_id": board_id, "samples": 1, "median_ratio": 2.0}]

    async def test_course_remaining_uses_board_factor_only_from_three_samples(
        self, client, auth_headers, edu
    ):
        root, _ = await make_root(client, auth_headers, edu, "Kurs", PARTS)
        await track(client, auth_headers, root)
        await self._finish_cards(client, auth_headers, edu, 2)
        c = (await courses(client, auth_headers))[0]
        assert c["remaining_minutes"] == 240  # 2 ornek < 3 -> katsayi 1.0
        await self._finish_cards(client, auth_headers, edu, 1)
        c = (await courses(client, auth_headers))[0]
        assert c["remaining_minutes"] == 480  # 3 ornek, medyan 2.0


class TestPatPolicy:
    async def test_read_pat_reads_courses_but_cannot_create(
        self, client, auth_headers, edu
    ):
        root, _ = await make_root(client, auth_headers, edu, "Kurs", PARTS)
        read = (await make_token(client, auth_headers, scopes=["read"])).json()["data"]["token"]
        write = (
            await make_token(client, auth_headers, scopes=["read", "write"], name="W")
        ).json()["data"]["token"]
        res = await client.get(f"{API}/learning/courses", headers=bearer(read))
        assert res.status_code == 200, res.text
        res = await client.post(
            f"{API}/learning/courses", json={"root_card_id": root["id"]}, headers=bearer(read)
        )
        assert res.status_code == 403
        res = await client.post(
            f"{API}/learning/courses", json={"root_card_id": root["id"]}, headers=bearer(write)
        )
        assert res.status_code == 201, res.text
