"""Faz 13j1: Ingilizce kocu - profil, kelime (SRS), hata gunlugu, seanslar, bugun, ilerleme.

Saat sabittir (`clock` fixture): gercek duvar saatine bagli degil, gece 00:00-04:00 arasi
kosulunca da yesil kalir. "Bugun" = 2026-11-18 (Carsamba), Istanbul 12:00.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import update

from app.db.entities.english import EnglishMistakeEntity, EnglishVocabEntity
from tests.integration.test_api_tokens import bearer, make_token
from tests.integration.test_boards_cards import API, create_board, create_card
from tests.integration.test_day_plans import save_plan, suggestions

NOW = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)  # Istanbul 12:00
TODAY = date(2026, 11, 18)
E = f"{API}/english"
PROFILE = {
    "target_level": "B2",
    "current_level": "B1",
    "daily_minutes": 15,
    "focus": ["speaking", "writing", "vocab", "grammar"],
}


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr("app.services.english._now", lambda: NOW)
    return NOW


@pytest.fixture
async def other_headers(client):
    creds = {"email": "other@example.com", "password": "otherpassword123"}
    await client.post(f"{API}/auth/register", json=creds)
    res = await client.post(f"{API}/auth/login", json=creds)
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def put_profile(client, headers, **over):
    return await client.put(f"{E}/profile", json={**PROFILE, **over}, headers=headers)


async def add_vocab(client, headers, term="serendipity", meaning="tesadüf", **extra):
    res = await client.post(
        f"{E}/vocab",
        json={"term": term, "meaning_tr": meaning, **extra},
        headers=headers,
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]


async def add_session(client, headers, started: datetime, minutes=10, **extra):
    body = {"kind": "daily", "started_at": started.isoformat(), "minutes": minutes}
    res = await client.post(f"{E}/sessions", json={**body, **extra}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()["data"]


def mistake_body(**over):
    return {
        "source": "claude",
        "original": "I am agree",
        "corrected": "I agree",
        "category": "grammar",
        "explanation_tr": "agree bir fiildir.",
        **over,
    }


# ---------------------------------------------------------------- profil
class TestProfile:
    async def test_missing_is_404_with_code(self, client, auth_headers):
        res = await client.get(f"{E}/profile", headers=auth_headers)
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "ENGLISH_PROFILE_MISSING"

    async def test_put_creates_then_updates(self, client, auth_headers):
        res = await put_profile(client, auth_headers)
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert data["target_level"] == "B2" and data["daily_minutes"] == 15
        assert data["started_at"] == TODAY.isoformat()
        res = await put_profile(client, auth_headers, daily_minutes=30, target_level="C1")
        assert res.status_code == 200
        got = (await client.get(f"{E}/profile", headers=auth_headers)).json()["data"]
        assert got["daily_minutes"] == 30 and got["target_level"] == "C1"
        assert got["started_at"] == TODAY.isoformat()  # guncellemede degismez

    @pytest.mark.parametrize(
        "over",
        [
            {"target_level": "D1"},
            {"current_level": "x"},
            {"daily_minutes": 4},
            {"daily_minutes": 121},
            {"focus": ["dancing"]},
            {"focus": []},
            {"focus": ["vocab", "vocab"]},
        ],
    )
    async def test_validation(self, client, auth_headers, over):
        assert (await put_profile(client, auth_headers, **over)).status_code == 422

    async def test_profiles_are_per_user(self, client, auth_headers, other_headers):
        await put_profile(client, auth_headers)
        res = await client.get(f"{E}/profile", headers=other_headers)
        assert res.status_code == 404


# ---------------------------------------------------------------- kelime
class TestVocab:
    async def test_create_single_and_defaults(self, client, auth_headers):
        v = await add_vocab(client, auth_headers, example="Pure serendipity.")
        assert v["term"] == "serendipity" and v["existing"] is False
        assert (v["ease"], v["interval_days"], v["reps"], v["lapses"]) == (2.5, 0, 0, 0)
        assert v["due_on"] == TODAY.isoformat()
        assert v["source"] == "self"

    async def test_actor_sets_default_source(self, client, auth_headers):
        v = await add_vocab(client, {**auth_headers, "X-Actor": "mcp"}, term="ubiquitous")
        assert v["source"] == "claude"

    async def test_batch_and_duplicates_return_existing(self, client, auth_headers):
        first = await add_vocab(client, auth_headers, term="Ephemeral", meaning="geçici")
        items = [
            {"term": "  ephemeral ", "meaning_tr": "başka"},
            {"term": "mitigate", "meaning_tr": "hafifletmek"},
            {"term": "Mitigate", "meaning_tr": "yine"},
        ]
        res = await client.post(f"{E}/vocab", json={"items": items}, headers=auth_headers)
        assert res.status_code == 201, res.text
        out = res.json()["data"]
        assert [i["existing"] for i in out] == [True, False, True]
        assert out[0]["id"] == first["id"] and out[0]["meaning_tr"] == "geçici"
        assert out[1]["id"] == out[2]["id"]

    async def test_single_duplicate_is_200(self, client, auth_headers):
        await add_vocab(client, auth_headers)
        res = await client.post(
            f"{E}/vocab", json={"term": "SERENDIPITY", "meaning_tr": "x"}, headers=auth_headers
        )
        assert res.status_code == 200
        assert res.json()["data"]["existing"] is True

    async def test_batch_limit_20(self, client, auth_headers):
        body = [{"term": f"w{i}", "meaning_tr": "x"} for i in range(21)]
        res = await client.post(f"{E}/vocab", json={"items": body}, headers=auth_headers)
        assert res.status_code == 422
        res = await client.post(f"{E}/vocab", json={"items": body[:20]}, headers=auth_headers)
        assert res.status_code == 201

    async def test_validation(self, client, auth_headers):
        for body in (
            {"term": "", "meaning_tr": "x"},
            {"term": "a" * 101, "meaning_tr": "x"},
            {"term": "a", "meaning_tr": "x" * 301},
            {"term": "a", "meaning_tr": "x", "source": "robot"},
            {"term": "a"},
        ):
            res = await client.post(f"{E}/vocab", json=body, headers=auth_headers)
            assert res.status_code == 422, body

    async def test_patch_and_delete(self, client, auth_headers):
        v = await add_vocab(client, auth_headers)
        res = await client.patch(
            f"{E}/vocab/{v['id']}", json={"meaning_tr": "şans eseri"}, headers=auth_headers
        )
        assert res.status_code == 200 and res.json()["data"]["meaning_tr"] == "şans eseri"
        assert (await client.delete(f"{E}/vocab/{v['id']}", headers=auth_headers)).status_code == 204
        assert (await client.delete(f"{E}/vocab/{v['id']}", headers=auth_headers)).status_code == 404

    async def test_patch_term_collision_is_409(self, client, auth_headers):
        await add_vocab(client, auth_headers, term="alpha")
        b = await add_vocab(client, auth_headers, term="beta")
        res = await client.patch(
            f"{E}/vocab/{b['id']}", json={"term": " ALPHA"}, headers=auth_headers
        )
        assert res.status_code == 409

    async def test_review_applies_sm2(self, client, auth_headers):
        v = await add_vocab(client, auth_headers)
        url = f"{E}/vocab/{v['id']}/review"
        r = (await client.post(url, json={"grade": 5}, headers=auth_headers)).json()["data"]
        assert (r["reps"], r["interval_days"], r["ease"]) == (1, 1, 2.6)
        assert r["due_on"] == (TODAY + timedelta(days=1)).isoformat()
        r = (await client.post(url, json={"grade": 4}, headers=auth_headers)).json()["data"]
        assert (r["reps"], r["interval_days"], r["ease"]) == (2, 6, 2.6)
        r = (await client.post(url, json={"grade": 3}, headers=auth_headers)).json()["data"]
        assert (r["reps"], r["interval_days"], r["ease"]) == (3, 16, 2.46)
        r = (await client.post(url, json={"grade": 1}, headers=auth_headers)).json()["data"]
        assert (r["reps"], r["interval_days"], r["lapses"]) == (0, 1, 1)
        assert r["last_reviewed_at"].startswith("2026-11-18T09:00:00")

    @pytest.mark.parametrize("grade", [-1, 6, "a"])
    async def test_review_grade_validation(self, client, auth_headers, grade):
        v = await add_vocab(client, auth_headers)
        res = await client.post(
            f"{E}/vocab/{v['id']}/review", json={"grade": grade}, headers=auth_headers
        )
        assert res.status_code == 422

    async def test_due_list_order_and_limit(self, client, auth_headers):
        a = await add_vocab(client, auth_headers, term="aaa")
        b = await add_vocab(client, auth_headers, term="bbb")
        c = await add_vocab(client, auth_headers, term="ccc")
        await client.post(f"{E}/vocab/{b['id']}/review", json={"grade": 5}, headers=auth_headers)
        due = (await client.get(f"{E}/vocab?due=true", headers=auth_headers)).json()["data"]
        assert [v["id"] for v in due] == [a["id"], c["id"]]  # b yarina ertelendi
        allv = (await client.get(f"{E}/vocab", headers=auth_headers)).json()["data"]
        assert len(allv) == 3
        lim = (await client.get(f"{E}/vocab?due=true&limit=1", headers=auth_headers)).json()
        assert len(lim["data"]) == 1
        assert (await client.get(f"{E}/vocab?limit=0", headers=auth_headers)).status_code == 422

    async def test_idor_404(self, client, auth_headers, other_headers):
        v = await add_vocab(client, auth_headers)
        for method, path, body in (
            ("PATCH", f"/vocab/{v['id']}", {"meaning_tr": "x"}),
            ("DELETE", f"/vocab/{v['id']}", None),
            ("POST", f"/vocab/{v['id']}/review", {"grade": 3}),
        ):
            res = await client.request(method, f"{E}{path}", json=body, headers=other_headers)
            assert res.status_code == 404, (method, path)
        assert (await client.get(f"{E}/vocab", headers=other_headers)).json()["data"] == []
        mine = await add_vocab(client, other_headers)  # ayni terim, ayri kayit
        assert mine["existing"] is False and mine["id"] != v["id"]


# ---------------------------------------------------------------- hatalar
class TestMistakes:
    async def test_create_list_filter_delete(self, client, auth_headers):
        res = await client.post(f"{E}/mistakes", json=mistake_body(), headers=auth_headers)
        assert res.status_code == 201, res.text
        m = res.json()["data"]
        assert m["review_count"] == 0 and m["created_at"].startswith("2026-11-18T09:00:00")
        await client.post(
            f"{E}/mistakes",
            json=mistake_body(category="tense", original="He go"),
            headers=auth_headers,
        )
        allm = (await client.get(f"{E}/mistakes", headers=auth_headers)).json()["data"]
        assert [x["category"] for x in allm] == ["tense", "grammar"]  # yeni once
        only = (await client.get(f"{E}/mistakes?category=tense", headers=auth_headers)).json()
        assert len(only["data"]) == 1
        assert (await client.delete(f"{E}/mistakes/{m['id']}", headers=auth_headers)).status_code == 204
        assert (await client.delete(f"{E}/mistakes/{m['id']}", headers=auth_headers)).status_code == 404

    async def test_batch_up_to_20_and_21_is_422(self, client, auth_headers):
        items = [mistake_body(original=f"o{i}") for i in range(21)]
        res = await client.post(f"{E}/mistakes", json={"items": items}, headers=auth_headers)
        assert res.status_code == 422
        res = await client.post(f"{E}/mistakes", json={"items": items[:20]}, headers=auth_headers)
        assert res.status_code == 201 and len(res.json()["data"]) == 20

    @pytest.mark.parametrize(
        "over",
        [
            {"category": "slang"},
            {"original": ""},
            {"original": "x" * 501},
            {"corrected": "x" * 501},
            {"explanation_tr": "x" * 501},
            {"source": "robot"},
        ],
    )
    async def test_validation(self, client, auth_headers, over):
        res = await client.post(f"{E}/mistakes", json=mistake_body(**over), headers=auth_headers)
        assert res.status_code == 422

    async def test_idor_404(self, client, auth_headers, other_headers):
        res = await client.post(f"{E}/mistakes", json=mistake_body(), headers=auth_headers)
        m = res.json()["data"]
        res = await client.delete(f"{E}/mistakes/{m['id']}", headers=other_headers)
        assert res.status_code == 404
        assert (await client.get(f"{E}/mistakes", headers=other_headers)).json()["data"] == []


# ---------------------------------------------------------------- seanslar
class TestSessions:
    async def test_create_and_list(self, client, auth_headers):
        s = await add_session(
            client, auth_headers, NOW - timedelta(days=1), minutes=20,
            summary="Konuşma", new_vocab=3, mistakes_count=2, kind="speaking",
        )
        assert s["kind"] == "speaking" and s["minutes"] == 20 and s["new_vocab"] == 3
        newer = await add_session(client, auth_headers, NOW)
        res = (await client.get(f"{E}/sessions", headers=auth_headers)).json()["data"]
        assert [x["id"] for x in res] == [newer["id"], s["id"]]  # yeni once

    async def test_started_at_defaults_to_now(self, client, auth_headers):
        res = await client.post(
            f"{E}/sessions", json={"kind": "deep", "minutes": 30}, headers=auth_headers
        )
        assert res.status_code == 201
        assert res.json()["data"]["started_at"].startswith("2026-11-18T09:00:00")

    @pytest.mark.parametrize(
        "over",
        [
            {"minutes": 0},
            {"minutes": 241},
            {"kind": "nap"},
            {"summary": "x" * 2001},
            {"new_vocab": -1},
        ],
    )
    async def test_validation(self, client, auth_headers, over):
        body = {"kind": "daily", "minutes": 10, **over}
        res = await client.post(f"{E}/sessions", json=body, headers=auth_headers)
        assert res.status_code == 422

    async def test_user_isolation(self, client, auth_headers, other_headers):
        await add_session(client, auth_headers, NOW)
        assert (await client.get(f"{E}/sessions", headers=other_headers)).json()["data"] == []


# ---------------------------------------------------------------- bugun
class TestToday:
    async def test_without_profile(self, client, auth_headers):
        res = await client.get(f"{E}/today", headers=auth_headers)
        assert res.status_code == 200
        d = res.json()["data"]
        assert d["profile"] is None and d["task"] is None
        assert d["practiced_today"] is False and d["due_vocab"] == []

    async def test_task_cycles_with_ordinal(self, client, auth_headers, monkeypatch):
        await put_profile(client, auth_headers)
        focus = PROFILE["focus"]
        texts = {
            "speaking": "5 dk sesli konuş: bugünün planını İngilizce anlat.",
            "writing": "3–5 cümle yaz: dün ne yaptın?",
            "vocab": "Vadesi gelen kelimeleri tekrar et, 2 örnek cümle kur.",
            "grammar": "En sık hata kategorinden 5 düzeltme alıştırması.",
        }
        seen = []
        for i in range(5):
            day = NOW + timedelta(days=i)
            monkeypatch.setattr("app.services.english._now", lambda day=day: day)
            d = (await client.get(f"{E}/today", headers=auth_headers)).json()["data"]
            assert d["task"] == texts[focus[day.date().toordinal() % len(focus)]]
            seen.append(d["task"])
        assert len(set(seen[:4])) == 4 and seen[0] == seen[4]  # 4 gunde bir doner

    async def test_task_respects_focus_subset(self, client, auth_headers):
        await put_profile(client, auth_headers, focus=["vocab"])
        d = (await client.get(f"{E}/today", headers=auth_headers)).json()["data"]
        assert d["task"].startswith("Vadesi gelen kelimeleri")

    async def test_due_vocab_cap_15_oldest_first(self, client, auth_headers, test_session):
        await put_profile(client, auth_headers)
        ids = []
        for i in range(17):
            ids.append((await add_vocab(client, auth_headers, term=f"w{i:02d}"))["id"])
        for vid, due in ((ids[16], TODAY - timedelta(days=10)), (ids[0], TODAY + timedelta(days=1))):
            await test_session.execute(
                update(EnglishVocabEntity).where(EnglishVocabEntity.id == vid).values(due_on=due)
            )
        await test_session.commit()
        d = (await client.get(f"{E}/today", headers=auth_headers)).json()["data"]
        assert len(d["due_vocab"]) == 15
        assert d["due_vocab"][0]["term"] == "w16"  # en eski once
        assert "w00" not in {v["term"] for v in d["due_vocab"]}  # vadesi gelmedi

    async def test_top_categories_last_7_days(self, client, auth_headers, test_session):
        n = 0
        for cat, count in (
            ("tense", 3), ("article", 2), ("spelling", 2), ("grammar", 1), ("other", 1),
        ):
            for _ in range(count):
                n += 1
                body = mistake_body(category=cat, original=f"o{n}")
                await client.post(f"{E}/mistakes", json=body, headers=auth_headers)
        for _ in range(5):  # 8 gun onceki hatalar sayilmaz
            n += 1
            body = mistake_body(category="preposition", original=f"o{n}")
            res = await client.post(f"{E}/mistakes", json=body, headers=auth_headers)
            await test_session.execute(
                update(EnglishMistakeEntity)
                .where(EnglishMistakeEntity.id == res.json()["data"]["id"])
                .values(created_at=NOW - timedelta(days=8))
            )
        await test_session.commit()
        d = (await client.get(f"{E}/today", headers=auth_headers)).json()["data"]
        assert d["top_categories"] == [
            {"category": "tense", "count": 3},
            {"category": "article", "count": 2},
            {"category": "spelling", "count": 2},
        ]  # esitlikte alfabetik

    async def test_practiced_today_uses_local_day(self, client, auth_headers):
        # 17 Kas 21:30Z = Istanbul 18 Kas 00:30 -> "bugun" sayilir
        await add_session(client, auth_headers, datetime(2026, 11, 17, 21, 30, tzinfo=UTC))
        d = (await client.get(f"{E}/today", headers=auth_headers)).json()["data"]
        assert d["practiced_today"] is True

    async def test_not_practiced_when_only_yesterday(self, client, auth_headers):
        await add_session(client, auth_headers, datetime(2026, 11, 17, 20, 59, tzinfo=UTC))
        d = (await client.get(f"{E}/today", headers=auth_headers)).json()["data"]
        assert d["practiced_today"] is False


# ---------------------------------------------------------------- ilerleme
class TestProgress:
    async def test_empty(self, client, auth_headers):
        d = (await client.get(f"{E}/progress", headers=auth_headers)).json()["data"]
        assert d["streak_days"] == 0
        assert len(d["weekly_minutes"]) == 8
        assert all(w["minutes"] == 0 for w in d["weekly_minutes"])
        assert d["weekly_minutes"][-1]["week"] == "2026-W47"
        assert d["vocab_stats"] == {"total": 0, "due": 0, "mature": 0}
        assert d["mistakes_by_category"] == []

    async def test_streak_from_today(self, client, auth_headers):
        for back in (0, 1, 2, 4):  # 3 gun once yok -> seri 3
            await add_session(client, auth_headers, NOW - timedelta(days=back))
        d = (await client.get(f"{E}/progress", headers=auth_headers)).json()["data"]
        assert d["streak_days"] == 3

    async def test_streak_starts_yesterday_if_not_practiced_today(self, client, auth_headers):
        for back in (1, 2):
            await add_session(client, auth_headers, NOW - timedelta(days=back))
        d = (await client.get(f"{E}/progress", headers=auth_headers)).json()["data"]
        assert d["streak_days"] == 2

    async def test_streak_broken_when_gap_yesterday(self, client, auth_headers):
        await add_session(client, auth_headers, NOW - timedelta(days=2))
        d = (await client.get(f"{E}/progress", headers=auth_headers)).json()["data"]
        assert d["streak_days"] == 0

    async def test_weekly_minutes_and_weeks_param(self, client, auth_headers):
        await add_session(client, auth_headers, NOW, minutes=20)  # W47 (Pzt 16 Kas)
        await add_session(client, auth_headers, NOW - timedelta(days=1), minutes=15)  # W47
        await add_session(client, auth_headers, NOW - timedelta(days=3), minutes=30)  # W46
        d = (await client.get(f"{E}/progress?weeks=2", headers=auth_headers)).json()["data"]
        assert d["weekly_minutes"] == [
            {"week": "2026-W46", "minutes": 30},
            {"week": "2026-W47", "minutes": 35},
        ]
        assert (await client.get(f"{E}/progress?weeks=0", headers=auth_headers)).status_code == 422
        assert (await client.get(f"{E}/progress?weeks=53", headers=auth_headers)).status_code == 422

    async def test_vocab_stats_and_mistakes_by_category(self, client, auth_headers, test_session):
        a = await add_vocab(client, auth_headers, term="a1")
        b = await add_vocab(client, auth_headers, term="b1")
        await add_vocab(client, auth_headers, term="c1")
        for vid, interval in ((a["id"], 21), (b["id"], 20)):
            await test_session.execute(
                update(EnglishVocabEntity)
                .where(EnglishVocabEntity.id == vid)
                .values(interval_days=interval, due_on=TODAY + timedelta(days=interval))
            )
        await test_session.commit()
        for cat in ("tense", "tense", "article"):
            body = mistake_body(category=cat)
            await client.post(f"{E}/mistakes", json=body, headers=auth_headers)
        d = (await client.get(f"{E}/progress", headers=auth_headers)).json()["data"]
        assert d["vocab_stats"] == {"total": 3, "due": 1, "mature": 1}
        assert d["mistakes_by_category"] == [
            {"week": "2026-W47", "category": "article", "count": 1},
            {"week": "2026-W47", "category": "tense", "count": 2},
        ]


# ---------------------------------------------------------------- oneri (G2)
class TestSuggestion:
    async def seed_day(self, client, headers):
        board = await create_board(client, headers)
        await create_card(
            client, headers, board["lists"][0]["id"], "Vergi",
            due_date="2026-11-18T10:00:00+03:00",
        )

    async def test_existing_kinds_unchanged_and_english_appended(self, client, auth_headers):
        await self.seed_day(client, auth_headers)
        before = await suggestions(client, auth_headers, TODAY)
        assert before and all(s["kind"] != "english" for s in before)  # profil yok -> yok
        await put_profile(client, auth_headers, daily_minutes=25)
        after = await suggestions(client, auth_headers, TODAY)
        assert after[:-1] == before  # mevcut turlerin sirasi ve icerigi ayni (G2)
        eng = after[-1]
        assert eng["kind"] == "english" and eng["title"] == "İngilizce pratik"
        assert eng["planned_minutes"] == 25 and eng["card_id"] is None

    async def test_hidden_when_session_exists_that_day(self, client, auth_headers):
        await put_profile(client, auth_headers)
        assert any(s["kind"] == "english" for s in await suggestions(client, auth_headers, TODAY))
        await add_session(client, auth_headers, NOW)
        assert not any(
            s["kind"] == "english" for s in await suggestions(client, auth_headers, TODAY)
        )

    async def test_other_day_session_does_not_hide(self, client, auth_headers):
        await put_profile(client, auth_headers)
        await add_session(client, auth_headers, NOW - timedelta(days=1))
        assert any(s["kind"] == "english" for s in await suggestions(client, auth_headers, TODAY))

    async def test_hidden_when_plan_has_english_item(self, client, auth_headers):
        await put_profile(client, auth_headers)
        await save_plan(
            client, auth_headers,
            [{"title": "İNGİLİZCE konuşma", "planned_minutes": 20}], day=TODAY,
        )
        assert not any(
            s["kind"] == "english" for s in await suggestions(client, auth_headers, TODAY)
        )


# ---------------------------------------------------------------- PAT
class TestPatPolicy:
    async def test_read_pat_reads_but_cannot_write(self, client, auth_headers):
        read = (await make_token(client, auth_headers, scopes=["read"])).json()["data"]["token"]
        write = (
            await make_token(client, auth_headers, scopes=["read", "write"], name="W")
        ).json()["data"]["token"]
        assert (await client.get(f"{E}/today", headers=bearer(read))).status_code == 200
        assert (await client.get(f"{E}/vocab", headers=bearer(read))).status_code == 200
        body = {"term": "pat", "meaning_tr": "x"}
        res = await client.post(f"{E}/vocab", json=body, headers=bearer(read))
        assert res.status_code == 403 and res.json()["error"]["code"] == "PAT_SCOPE"
        res = await client.post(f"{E}/vocab", json=body, headers=bearer(write))
        assert res.status_code == 201, res.text
        res = await client.put(f"{E}/profile", json=PROFILE, headers=bearer(read))
        assert res.status_code == 403
        res = await client.put(f"{E}/profile", json=PROFILE, headers=bearer(write))
        assert res.status_code == 200

    def test_policy_table_does_not_forbid_english(self):
        from app.core.pat_policy import is_forbidden, needs_write

        for method, path in (
            ("GET", "/api/v1/english/today"),
            ("POST", "/api/v1/english/vocab"),
            ("PUT", "/api/v1/english/profile"),
            ("DELETE", "/api/v1/english/mistakes/1"),
        ):
            assert is_forbidden(method, path) is False
        assert needs_write("GET", "/api/v1/english/progress") is False
        assert needs_write("POST", "/api/v1/english/vocab/1/review") is True
