"""Faz 6a: gun sonu ozeti + ertesi gun plan onerisi (arka plan isi)."""

import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.api.chat as chat_module
import app.api.jobs as jobs_module
from app.agent.day_review import (
    Candidate,
    adjust_minutes,
    build_candidates,
    daily_cap,
    estimate_factor,
    factor_text,
    parse_output,
    pick,
    run_day_review,
)
from app.api.deps import current_user
from app.db.models import AiActionEntity, AiPermissionEntity
from app.llm.types import ModelInfo
from app.main import app
from app.tools.privacy import PrivacyFilter
from app.tools.task_api import TaskApiClient
from tests.conftest import FakeProvider, FakeTaskApi, text

TZ = ZoneInfo("Europe/Istanbul")
DAY = datetime.now(TZ).date()
TOMORROW = DAY + timedelta(days=1)
USER = {"id": 7, "full_name": "Ali", "token": "tkn"}


# ---------------- saf yardimcilar ----------------
def test_estimate_factor_needs_samples_and_is_clamped():
    acc = lambda n, r: {"estimate_accuracy": {"sample_size": n, "median_ratio": r}}  # noqa: E731
    assert estimate_factor(acc(2, 1.4)) is None
    assert estimate_factor(acc(3, 1.35)) == 1.35
    assert estimate_factor(acc(5, 9.0)) == 3.0
    assert estimate_factor(None) is None


def test_adjust_and_describe():
    assert adjust_minutes(120, 1.35) == 160  # 162 -> 5'in katina
    assert adjust_minutes(10, 0.2) == 5
    assert adjust_minutes(None, 1.3) is None
    assert adjust_minutes(30, None) == 30
    assert factor_text(1.35) == "İşlerin genelde tahmininden %35 uzun sürüyor"
    assert factor_text(0.8) == "İşlerin genelde tahmininden %20 kısa sürüyor"
    assert factor_text(None) is None


def test_daily_cap_from_history():
    assert daily_cap(None) == 360
    assert daily_cap({"totals": {"reviewed_days": 4, "tracked_min": 800}}) == 240
    assert daily_cap({"totals": {"reviewed_days": 4, "tracked_min": 99999}}) == 480


def test_parse_output_tolerates_fences_and_rejects_garbage():
    out = parse_output(
        'Tamam:\n```json\n{"summary": " İyi gün. ", "plan": [{"n": 1}]}\n```'
    )
    assert out == {"summary": "İyi gün.", "plan": [{"n": 1}], "tip": None}
    assert parse_output("düz metin") is None
    assert parse_output("{bozuk json}") is None


def _cand(n, kind="due", adjusted=60, **kw) -> Candidate:
    return Candidate(
        n=n,
        kind=kind,
        title=f"İş {n}",
        card_id=kw.get("card_id", n),
        event_id=kw.get("event_id"),
        board=None,
        minutes=adjusted,
        adjusted=adjusted,
        planned_start=None,
        due_date=None,
    )


def test_pick_validates_and_respects_cap():
    cands = [_cand(1, adjusted=200), _cand(2, adjusted=200), _cand(3, "event", 0)]
    chosen = [
        {"n": 1, "reason": "son gün"},
        {"n": 1},
        {"n": "x"},
        {"n": 9},
        2,
        {"n": 3},
    ]
    picked = pick(cands, chosen, cap=300)
    # 2 kapasiteyi asar -> atlanir; etkinlik her zaman alinir; tekrar/gecersizler yok
    assert [(c.n, r) for c, r in picked] == [(1, "son gün"), (3, None)]


def test_candidates_skip_blocked_planned_and_hidden():
    suggestions = [
        {
            "kind": "due",
            "card_id": 11,
            "title": "Koşu",
            "board_id": 1,
            "planned_minutes": 60,
        },
        {"kind": "due", "card_id": 11, "title": "Koşu (tekrar)", "board_id": 1},
        {"kind": "carry_over", "card_id": 12, "title": "Bloke", "blocked": True},
        {"kind": "due", "card_id": 13, "title": "Planlı", "already_planned": True},
        {"kind": "due", "card_id": 21, "title": "Gizli", "board_id": 2},
        {"kind": "event", "event_id": 5, "title": "Toplantı", "planned_minutes": 30},
    ]
    privacy = PrivacyFilter(active=True, hidden_boards={2})
    cands = build_candidates(suggestions, {1: "Spor"}, privacy, factor=1.5)
    assert [(c.title, c.adjusted) for c in cands] == [("Koşu", 90), ("Toplantı", 30)]
    assert cands[0].board == "Spor" and cands[1].event_id == 5


# ---------------- uctan uca (sahte task-api + sahte model) ----------------
class ReviewApi(FakeTaskApi):
    """Degerlendirilmis bir gun, yarin icin oneriler ve gizli bir board."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")

        def ok(data):
            return httpx.Response(200, json={"success": True, "data": data})

        if request.method == "PUT" and path.endswith("/ai-summary"):
            body = json.loads(request.content)
            self.writes.append(
                {
                    "method": "PUT",
                    "path": path,
                    "body": body,
                    "actor": request.headers.get("X-Actor"),
                }
            )
            return ok({"date": str(DAY), **body})
        if request.method == "GET" and path == f"/day-plans/{DAY}":
            return ok(
                {
                    "date": str(DAY),
                    "exists": True,
                    "status": "reviewed",
                    "mood": 4,
                    "energy": 2,
                    "reflection": "Gizli bir not",
                    "items": [
                        {
                            "title": "Koşu",
                            "card_id": 11,
                            "board_id": 1,
                            "was_planned": True,
                            "planned_minutes": 30,
                            "tracked_sec": 2400,
                            "outcome": "done",
                            "reason": None,
                        },
                        {
                            "title": "Gizli date planı",
                            "card_id": 21,
                            "board_id": 2,
                            "was_planned": True,
                            "planned_minutes": 60,
                            "tracked_sec": 0,
                            "outcome": "postponed",
                            "reason": "vakit kalmadı",
                        },
                    ],
                }
            )
        if request.method == "GET" and path == f"/day-plans/{TOMORROW}/suggestions":
            return ok(
                {
                    "date": str(TOMORROW),
                    "items": [
                        {
                            "kind": "due",
                            "card_id": 11,
                            "title": "Koşu",
                            "board_id": 1,
                            "planned_minutes": 40,
                        },
                        {
                            "kind": "carry_over",
                            "card_id": 21,
                            "title": "Gizli date planı",
                            "board_id": 2,
                            "planned_minutes": 60,
                        },
                    ],
                }
            )
        if request.method == "GET" and path == "/analytics/summary":
            return ok(
                {
                    "totals": {"reviewed_days": 0, "tracked_min": 0},
                    "estimate_accuracy": {"sample_size": 4, "median_ratio": 1.5},
                }
            )
        return super().__call__(request)


@pytest.fixture
def review_api() -> ReviewApi:
    return ReviewApi()


def _provider(reply: str, *, is_local=True) -> FakeProvider:
    return FakeProvider([[text(reply)]], is_local=is_local)


REPLY = json.dumps(
    {
        "summary": "Koşuyu yaptın, date planını erteledin.",
        "plan": [{"n": 1, "reason": "Rutini koru"}, {"n": 2, "reason": "Ertelendi"}],
        "tip": "Erken başla",
    },
    ensure_ascii=False,
)


async def test_local_run_writes_summary_and_proposes_adjusted_plan(
    review_api, db_session_maker
):
    api = TaskApiClient("tkn", transport=httpx.MockTransport(review_api))
    provider = _provider(REPLY)
    result, action_id = await run_day_review(
        api, provider, db_session_maker, user_id=7, day=DAY, tz=TZ
    )
    await api.close()

    summary_write = next(
        w for w in review_api.writes if w["path"].endswith("/ai-summary")
    )
    assert summary_write["body"] == {
        "ai_summary": "Koşuyu yaptın, date planını erteledin."
    }
    assert summary_write["actor"] == "ai"
    # Onay bekler (varsayilan "sor"): plana henuz hicbir sey yazilmadi
    assert not any(w["path"] == f"/day-plans/{TOMORROW}" for w in review_api.writes)
    async with db_session_maker() as s:
        action = await s.get(AiActionEntity, action_id)
    assert action.status == "proposed" and action.conversation_id is None
    # Tahmin katsayisi 1.5: 40 dk -> 60 dk, 60 dk -> 90 dk
    assert action.args["items"] == [
        {"card_id": 11, "planned_minutes": 60},
        {"card_id": 21, "planned_minutes": 90},
    ]
    assert result["estimate_text"] == "İşlerin genelde tahmininden %50 uzun sürüyor"
    assert [p["reason"] for p in result["plan"]] == ["Rutini koru", "Ertelendi"]
    sent = provider.all_text_sent()
    assert "Gizli bir not" in sent  # local model kullanicinin notunu gorur


async def test_cloud_run_hides_private_board_and_reflection(
    review_api, db_session_maker
):
    api = TaskApiClient("tkn", transport=httpx.MockTransport(review_api))
    provider = _provider(REPLY, is_local=False)
    result, action_id = await run_day_review(
        api, provider, db_session_maker, user_id=7, day=DAY, tz=TZ
    )
    await api.close()
    sent = provider.all_text_sent()
    assert "Gizli date planı" not in sent and "Gizli bir not" not in sent
    async with db_session_maker() as s:
        action = await s.get(AiActionEntity, action_id)
    # Gizli board'un adayi listede yoktu: 2 numara gecersiz sayilir
    assert action.args["items"] == [{"card_id": 11, "planned_minutes": 60}]


async def test_auto_mode_applies_and_never_mode_skips(review_api, db_session_maker):
    async with db_session_maker() as s:
        s.add(AiPermissionEntity(user_id=7, action_type="plan_day", mode="auto"))
        await s.commit()
    api = TaskApiClient("tkn", transport=httpx.MockTransport(review_api))
    result, action_id = await run_day_review(
        api, _provider(REPLY), db_session_maker, user_id=7, day=DAY, tz=TZ
    )
    assert result["action_status"] == "executed"
    assert review_api.plans[str(TOMORROW)][0]["card_id"] == 11

    async with db_session_maker() as s:
        row = await s.scalar(select(AiPermissionEntity))
        row.mode = "never"
        await s.commit()
    result, action_id = await run_day_review(
        api, _provider(REPLY), db_session_maker, user_id=7, day=DAY, tz=TZ
    )
    await api.close()
    assert action_id is None and result["plan"] == []
    assert "kapalı" in result["notes"][0]


async def test_unparseable_reply_keeps_text_summary(review_api, db_session_maker):
    api = TaskApiClient("tkn", transport=httpx.MockTransport(review_api))
    result, action_id = await run_day_review(
        api, _provider("Güzel bir gündü."), db_session_maker, user_id=7, day=DAY, tz=TZ
    )
    await api.close()
    assert action_id is None and result["summary"] == "Güzel bir gündü."
    assert "biçimde" in result["notes"][0]


# ---------------- API: is baslat / durum ----------------
@pytest.fixture
async def client(monkeypatch, db_session_maker, review_api):
    transport = httpx.MockTransport(review_api)
    provider = _provider(REPLY)

    async def installed():
        return [ModelInfo("ollama:gemma4:26b", "ollama", "gemma4:26b", "gemma4", True)]

    monkeypatch.setattr(chat_module, "list_local_models", installed)
    monkeypatch.setattr(chat_module, "session_maker", db_session_maker)
    monkeypatch.setattr(
        chat_module,
        "TaskApiClient",
        lambda token: TaskApiClient(token, transport=transport),
    )
    monkeypatch.setattr(
        chat_module, "build_provider", lambda mid, cloud=None, **_: provider
    )
    app.dependency_overrides[current_user] = lambda: USER
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()


async def test_job_runs_in_background_and_reports_result(client):
    res = await client.post(f"/api/v1/assistant/day-review/{DAY}")
    assert res.status_code == 200, res.text
    job = res.json()["data"]
    assert (
        job["status"] in ("queued", "running")
        and job["model_id"] == "ollama:gemma4:26b"
    )
    await asyncio.gather(*jobs_module._TASKS)

    res = await client.get(f"/api/v1/assistant/day-review/{DAY}")
    job = res.json()["data"]
    assert job["status"] == "done", job
    assert job["result"]["summary"].startswith("Koşuyu")
    assert job["action"]["status"] == "proposed"
    assert (await client.get(f"/api/v1/assistant/day-review/{TOMORROW}")).json()[
        "data"
    ] is None


async def test_missing_background_model_is_reported(client, monkeypatch):
    async def none():
        return []

    monkeypatch.setattr(chat_module, "list_local_models", none)
    # Kurulu degilse sohbet varsayilanina duser; o da kurulu degilse 422
    res = await client.post(f"/api/v1/assistant/day-review/{DAY}")
    assert res.status_code == 422 and "kurulu değil" in res.text


async def test_stale_jobs_are_closed_on_startup(client, db_session_maker):
    from app.db.models import AiJobEntity

    async with db_session_maker() as s:
        s.add(
            AiJobEntity(
                user_id=7,
                kind="day_review",
                target_date=str(DAY),
                status="running",
                model_id="ollama:x",
            )
        )
        await s.commit()
    await jobs_module.recover_stale_jobs()
    job = (await client.get(f"/api/v1/assistant/day-review/{DAY}")).json()["data"]
    assert job["status"] == "failed" and "yeniden başladı" in job["error"]


# ---------------- Faz 13g: katmanli kalibrasyon + kurs arac ----------------
def _acc(general_n, general_r, by_board):
    return {
        "estimate_accuracy": {
            "sample_size": general_n,
            "median_ratio": general_r,
            "by_board": [
                {"board_id": b, "samples": n, "median_ratio": r}
                for b, n, r in by_board
            ],
        }
    }


def test_estimate_factor_board_first_then_general_then_none():
    s = _acc(5, 1.2, [(1, 3, 2.0), (2, 2, 3.0)])
    assert estimate_factor(s, 1) == 2.0  # board ornegi >= 3 -> board medyani
    assert estimate_factor(s, 2) == 1.2  # board ornegi < 3 -> genel medyan
    assert estimate_factor(s, 9) == 1.2  # bilinmeyen board -> genel
    assert estimate_factor(s) == 1.2  # board verilmedi -> bugunku davranis
    assert estimate_factor(_acc(2, 1.2, [(1, 2, 2.0)]), 1) is None  # hicbiri yeterli degil
    assert estimate_factor(_acc(5, 1.2, [(1, 4, 9.0)]), 1) == 3.0  # FACTOR_BOUNDS aynen
    assert estimate_factor(_acc(5, 1.2, [(1, 4, 0.1)]), 1) == 0.5


def test_build_candidates_uses_board_factor_when_summary_given():
    suggestions = [
        {"kind": "due", "card_id": 1, "title": "A", "board_id": 1, "planned_minutes": 60},
        {"kind": "due", "card_id": 2, "title": "B", "board_id": 2, "planned_minutes": 60},
    ]
    summary = _acc(5, 1.0, [(1, 3, 2.0)])
    cands = build_candidates(
        suggestions, {1: "Eğitim", 2: "Spor"}, PrivacyFilter(active=False), 1.0, summary
    )
    assert [(c.title, c.adjusted) for c in cands] == [("A", 120), ("B", 60)]


def _courses_tools(courses, hidden_boards=()):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        if path == "/learning/courses":
            return httpx.Response(200, json={"success": True, "data": courses})
        if path == "/boards":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": [
                        {"id": b, "name": f"B{b}", "privacy": "local_only"}
                        for b in hidden_boards
                    ],
                },
            )
        if path.startswith("/boards/"):
            return httpx.Response(
                200, json={"success": True, "data": {"board": {}, "cards": []}}
            )
        return httpx.Response(404, json={"success": False})

    return httpx.MockTransport(handler)


def _course(**kw):
    base = {
        "goal_id": 1,
        "title": "Power BI Kursu",
        "status": "active",
        "root_card": {"id": 10, "title": "Power BI Kursu", "board_id": 1},
        "parts_total": 21,
        "parts_done": 1,
        "next_part": {"id": 11, "title": "P2 — Veri kalitesi", "estimated_minutes": 60},
        "velocity_per_week": 0.5,
        "remaining_minutes": 1200,
        "eta_date": "2027-03-12",
        "eta_reason": "ok",
    }
    base.update(kw)
    return base


async def test_get_courses_text_and_hidden_board_course():
    from app.llm.types import ToolCall
    from app.tools.read_tools import ToolBox

    visible = _course()
    secret = _course(
        goal_id=2,
        title="Gizli kurs",
        root_card={"id": 20, "title": "Gizli kurs", "board_id": 2},
        next_part={"id": 21, "title": "Gizli parça", "estimated_minutes": None},
    )
    no_vel = _course(
        goal_id=3,
        title="Fabric",
        root_card={"id": 30, "title": "Fabric", "board_id": 1},
        velocity_per_week=None,
        eta_date=None,
        eta_reason="no_velocity",
        next_part={"id": 31, "title": "F1 — Giriş", "estimated_minutes": None},
        parts_done=0,
        parts_total=9,
    )
    transport = _courses_tools([visible, secret, no_vel], hidden_boards=(2,))
    for cloud in (False, True):
        box = await ToolBox.create(
            TaskApiClient("t", transport=transport), cloud=cloud, tz=TZ
        )
        out = (await box.execute(ToolCall(id="x", name="get_courses", arguments={}))).text
        assert (
            "Power BI Kursu: 1/21 parça · sıradaki P2 — Veri kalitesi · "
            "haftada 0,5 parça · bitiş ~12 Mart" in out
        )
        assert "Fabric: 0/9 parça · sıradaki F1 — Giriş · hız verisi yok" in out
        if cloud:
            assert "Gizli" not in out  # gizli board kursu bulut modele gitmez
        else:
            assert "Gizli kurs" in out
