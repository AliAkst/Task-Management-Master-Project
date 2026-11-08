"""Faz 3b: gunluk planlama, gun sonu degerlendirmesi ve istatistikler."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from app.services.timeutil import local_today
from tests.integration.test_boards_cards import API, create_board, create_card

TZ = ZoneInfo("Europe/Istanbul")
# Senaryolar "dun" uzerine kurulur: elle girilen oturumlar gecmiste kalir
D = local_today(TZ) - timedelta(days=1)


def at(day: date, hh: int, mm: int = 0) -> str:
    """Yerel (Istanbul) saat -> ISO."""
    return datetime.combine(day, time(hh, mm), tzinfo=TZ).isoformat()


async def log_time(client, headers, start: str, end: str, card_id=None):
    res = await client.post(
        f"{API}/sessions",
        json={"card_id": card_id, "started_at": start, "ended_at": end},
        headers=headers,
    )
    assert res.status_code == 201, res.text


async def suggestions(client, headers, day=D):
    res = await client.get(f"{API}/day-plans/{day}/suggestions", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]["items"]


async def save_plan(client, headers, items, day=D, expect=200):
    res = await client.put(
        f"{API}/day-plans/{day}", json={"items": items}, headers=headers
    )
    assert res.status_code == expect, res.text
    return res.json()["data"]


async def review(client, headers, body, day=D, expect=200):
    res = await client.post(f"{API}/day-plans/{day}/review", json=body, headers=headers)
    assert res.status_code == expect, res.text
    return res.json()["data"]


async def activity(client, headers, card_id):
    res = await client.get(f"{API}/cards/{card_id}/activity", headers=headers)
    return [a["action"] for a in res.json()["data"]]


@pytest.fixture
async def spor(client: AsyncClient, auth_headers):
    return await create_board(
        client, auth_headers, name="Spor", color="#22c55e", weekly_time_budget_min=210
    )


@pytest.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


class TestPlanning:
    async def test_empty_day(self, client, auth_headers):
        res = await client.get(f"{API}/day-plans/{D}", headers=auth_headers)
        data = res.json()["data"]
        assert data["exists"] is False and data["items"] == []

    async def test_suggestions_collect_and_dedupe(self, client, auth_headers, spor):
        todo, doing, done = spor["lists"]
        due = await create_card(
            client, auth_headers, todo["id"], "Bugün son", due_date=at(D, 20)
        )
        late = await create_card(
            client,
            auth_headers,
            todo["id"],
            "Gecikmiş",
            due_date=at(D - timedelta(days=3), 20),
        )
        await create_card(
            client,
            auth_headers,
            todo["id"],
            "Uzak",
            due_date=at(D + timedelta(days=9), 20),
        )
        prog = await create_card(client, auth_headers, doing["id"], "Devam eden")
        await client.patch(
            f"{API}/cards/{prog['id']}",
            json={"status": "in_progress"},
            headers=auth_headers,
        )
        blocked = await create_card(client, auth_headers, doing["id"], "Bekleyen")
        await client.patch(
            f"{API}/cards/{blocked['id']}",
            json={"status": "in_progress"},
            headers=auth_headers,
        )
        await client.post(
            f"{API}/cards/{blocked['id']}/dependencies",
            json={"depends_on_id": late["id"]},
            headers=auth_headers,
        )
        await create_card(
            client, auth_headers, done["id"], "Bitmiş", due_date=at(D, 12)
        )
        # Takvim blogu: "Bugün son" kartina -> event olarak (bir kez) onerilmeli
        await client.post(
            f"{API}/events",
            json={"card_id": due["id"], "start_at": at(D, 18), "end_at": at(D, 19, 30)},
            headers=auth_headers,
        )
        worked = await create_card(
            client, auth_headers, todo["id"], "Plansız çalışılan"
        )
        await log_time(client, auth_headers, at(D, 10), at(D, 10, 45), worked["id"])

        items = await suggestions(client, auth_headers)
        kinds = {i["title"]: i["kind"] for i in items}
        assert kinds == {
            "Bugün son": "event",
            "Gecikmiş": "overdue",
            "Devam eden": "in_progress",
            "Bekleyen": "in_progress",
            "Plansız çalışılan": "worked",
        }
        by_title = {i["title"]: i for i in items}
        assert by_title["Bugün son"]["planned_minutes"] == 90
        assert by_title["Bekleyen"]["blocked"] is True
        assert by_title["Plansız çalışılan"]["tracked_sec"] == 45 * 60

    async def test_save_plan_snapshots_and_replaces(self, client, auth_headers, spor):
        card = await create_card(
            client, auth_headers, spor["lists"][0]["id"], "Koşu", estimated_minutes=40
        )
        res = await client.post(
            f"{API}/events",
            json={"title": "Yoga", "start_at": at(D, 19), "end_at": at(D, 20)},
            headers=auth_headers,
        )
        event = res.json()["data"]
        plan = await save_plan(
            client,
            auth_headers,
            [
                {"card_id": card["id"]},
                {"event_id": event["id"]},
                {"title": "Alışveriş", "planned_minutes": 30},
            ],
        )
        assert plan["exists"] is True and plan["status"] == "planned"
        assert [(i["title"], i["planned_minutes"]) for i in plan["items"]] == [
            ("Koşu", 40),
            ("Yoga", 60),
            ("Alışveriş", 30),
        ]
        assert "planned" in await activity(client, auth_headers, card["id"])

        plan = await save_plan(client, auth_headers, [{"card_id": card["id"]}])
        assert [i["title"] for i in plan["items"]] == ["Koşu"]
        # Ayni kart tekrar planlaninca 'planned' bir kez yazilir
        assert (await activity(client, auth_headers, card["id"])).count("planned") == 1

    async def test_plan_item_needs_reference(self, client, auth_headers):
        res = await client.put(
            f"{API}/day-plans/{D}", json={"items": [{}]}, headers=auth_headers
        )
        assert res.status_code == 422


class TestReview:
    async def test_full_review_flow(self, client, auth_headers, spor):
        todo = spor["lists"][0]["id"]
        a = await create_card(
            client, auth_headers, todo, "A: yapılacak", estimated_minutes=60
        )
        b = await create_card(client, auth_headers, todo, "B: ertelenecek")
        c = await create_card(client, auth_headers, todo, "C: yapılmayacak")
        nxt = await create_card(client, auth_headers, todo, "A'yı bekleyen")
        await client.post(
            f"{API}/cards/{nxt['id']}/dependencies",
            json={"depends_on_id": a["id"]},
            headers=auth_headers,
        )
        extra = await create_card(client, auth_headers, todo, "Plansız iş")
        await log_time(client, auth_headers, at(D, 9), at(D, 10, 30), a["id"])

        plan = await save_plan(
            client,
            auth_headers,
            [{"card_id": a["id"]}, {"card_id": b["id"]}, {"card_id": c["id"]}],
        )
        ids = {i["card_id"]: i["id"] for i in plan["items"]}
        result = await review(
            client,
            auth_headers,
            {
                "mood": 4,
                "energy": 3,
                "reflection": "Fena değil",
                "items": [
                    {"id": ids[a["id"]], "outcome": "done"},
                    {
                        "id": ids[b["id"]],
                        "outcome": "postponed",
                        "reason": "Vakit kalmadı",
                    },
                    {"id": ids[c["id"]], "outcome": "not_done", "reason": "Yorgundum"},
                ],
                "unplanned": [{"card_id": extra["id"], "outcome": "done"}],
            },
        )
        assert result["status"] == "reviewed" and result["mood"] == 4
        items = {i["title"]: i for i in result["items"]}
        assert items["A: yapılacak"]["tracked_sec"] == 90 * 60
        assert items["B: ertelenecek"]["postponed_to"] == str(D + timedelta(days=1))
        assert items["Plansız iş"]["was_planned"] is False

        # done -> kart tamamlandi, "Tamamlandı" listesine gecti, bagimlisi acildi
        card_a = (
            await client.get(f"{API}/cards/{a['id']}", headers=auth_headers)
        ).json()["data"]
        assert card_a["status"] == "completed"
        assert card_a["list_id"] == spor["lists"][2]["id"]
        assert "unblocked" in await activity(client, auth_headers, nxt["id"])
        assert "postponed" in await activity(client, auth_headers, b["id"])
        assert "skipped" in await activity(client, auth_headers, c["id"])

        # Ertelenen ertesi gunun onerilerine duser
        tomorrow = await suggestions(client, auth_headers, D + timedelta(days=1))
        assert {"kind": "carry_over", "title": "B: ertelenecek"}.items() <= next(
            i for i in tomorrow if i["card_id"] == b["id"]
        ).items()

        # Degerlendirilmis gunun plani degistirilemez
        await save_plan(client, auth_headers, [], expect=409)

        # Tekrar degerlendirme: yan etkiler tekrarlanmaz
        await review(
            client, auth_headers, {"items": [{"id": ids[a["id"]], "outcome": "done"}]}
        )
        assert (await activity(client, auth_headers, a["id"])).count("completed") == 1

    async def test_review_without_plan(self, client, auth_headers, spor):
        res = await review(
            client,
            auth_headers,
            {"energy": 2, "unplanned": [{"title": "Ev temizliği", "outcome": "done"}]},
        )
        assert res["exists"] is True
        assert [(i["title"], i["was_planned"]) for i in res["items"]] == [
            ("Ev temizliği", False)
        ]

    async def test_validation(self, client, auth_headers):
        res = await client.post(
            f"{API}/day-plans/{D}/review", json={"mood": 6}, headers=auth_headers
        )
        assert res.status_code == 422
        res = await client.post(
            f"{API}/day-plans/{D}/review",
            json={"items": [{"id": 999, "outcome": "done"}]},
            headers=auth_headers,
        )
        assert res.status_code == 404

    async def test_deleted_card_keeps_plan_history(self, client, auth_headers, spor):
        card = await create_card(
            client, auth_headers, spor["lists"][0]["id"], "Silinecek"
        )
        await save_plan(client, auth_headers, [{"card_id": card["id"]}])
        await client.delete(f"{API}/cards/{card['id']}", headers=auth_headers)
        plan = (await client.get(f"{API}/day-plans/{D}", headers=auth_headers)).json()[
            "data"
        ]
        assert [(i["title"], i["card_id"]) for i in plan["items"]] == [
            ("Silinecek", None)
        ]


class TestAnalytics:
    async def test_summary(self, client, auth_headers, spor):
        todo = spor["lists"][0]["id"]
        a = await create_card(client, auth_headers, todo, "Koşu", estimated_minutes=60)
        b = await create_card(client, auth_headers, todo, "Esneme")
        await log_time(client, auth_headers, at(D, 9), at(D, 10, 30), a["id"])  # 90 dk
        await log_time(client, auth_headers, at(D, 14), at(D, 14, 30))  # serbest 30 dk
        plan = await save_plan(
            client, auth_headers, [{"card_id": a["id"]}, {"card_id": b["id"]}]
        )
        ids = {i["card_id"]: i["id"] for i in plan["items"]}
        await review(
            client,
            auth_headers,
            {
                "mood": 5,
                "items": [
                    {"id": ids[a["id"]], "outcome": "done"},
                    {"id": ids[b["id"]], "outcome": "postponed"},
                ],
            },
        )

        start = D - timedelta(days=6)
        res = await client.get(
            f"{API}/analytics/summary",
            params={"start": str(start), "end": str(D)},
            headers=auth_headers,
        )
        assert res.status_code == 200, res.text
        s = res.json()["data"]
        assert len(s["days"]) == 7
        day = s["days"][-1]
        assert (day["tracked_min"], day["planned"], day["done"], day["postponed"]) == (
            120,
            2,
            1,
            1,
        )
        assert day["mood"] == 5 and day["reviewed"] is True

        t = s["totals"]
        assert t["tracked_min"] == 120
        assert t["completion_rate"] == 0.5
        assert t["completed_cards"] == 1
        assert t["current_streak"] == 1  # dun degerlendirildi, bugun henuz degil

        spor_stat = next(x for x in s["boards"] if x["name"] == "Spor")
        assert spor_stat["tracked_min"] == 90
        assert spor_stat["budget_min"] == 210  # 7 gunluk aralik = haftalik hedef
        assert any(
            x["board_id"] is None and x["tracked_min"] == 30 for x in s["boards"]
        )

        assert s["productive_hours"][9] == 60 and s["productive_hours"][10] == 30
        assert s["weekdays"][D.weekday()] == 120
        acc = s["estimate_accuracy"]
        assert acc["sample_size"] == 1 and acc["mean_ratio"] == 1.5
        assert s["most_postponed"] == [
            {"card_id": b["id"], "title": "Esneme", "count": 1}
        ]

    async def test_session_across_midnight_is_split(self, client, auth_headers):
        prev = D - timedelta(days=1)
        await log_time(client, auth_headers, at(prev, 23, 30), at(D, 0, 45))
        res = await client.get(
            f"{API}/analytics/summary",
            params={"start": str(prev), "end": str(D)},
            headers=auth_headers,
        )
        days = res.json()["data"]["days"]
        assert [d["tracked_min"] for d in days] == [30, 45]

    async def test_range_validation(self, client, auth_headers):
        bad = [
            {"start": str(D), "end": str(D - timedelta(days=1))},
            {"start": str(D - timedelta(days=400)), "end": str(D)},
        ]
        for params in bad:
            res = await client.get(
                f"{API}/analytics/summary", params=params, headers=auth_headers
            )
            assert res.status_code == 422


class TestDayPlanOwnership:
    async def test_other_user_isolated(self, client, auth_headers, other_headers, spor):
        card = await create_card(client, auth_headers, spor["lists"][0]["id"], "Gizli")
        await log_time(client, auth_headers, at(D, 9), at(D, 10), card["id"])
        plan = await save_plan(client, auth_headers, [{"card_id": card["id"]}])
        item_id = plan["items"][0]["id"]
        h = other_headers

        res = await client.put(
            f"{API}/day-plans/{D}", json={"items": [{"card_id": card["id"]}]}, headers=h
        )
        assert res.status_code == 404
        res = await client.post(
            f"{API}/day-plans/{D}/review",
            json={"items": [{"id": item_id, "outcome": "done"}]},
            headers=h,
        )
        assert res.status_code == 404
        res = await client.delete(f"{API}/day-plan-items/{item_id}", headers=h)
        assert res.status_code == 404
        assert (await client.get(f"{API}/day-plans/{D}", headers=h)).json()["data"][
            "exists"
        ] is False
        assert await suggestions(client, h) == []
        res = await client.get(
            f"{API}/analytics/summary",
            params={"start": str(D), "end": str(D)},
            headers=h,
        )
        assert res.json()["data"]["totals"]["tracked_min"] == 0
        # benim kartim etkilenmedi
        mine = (
            await client.get(f"{API}/cards/{card['id']}", headers=auth_headers)
        ).json()["data"]
        assert mine["status"] == "pending"
