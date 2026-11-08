"""Faz 6b: haftalik analiz -> gozlemler (ai_insights) -> onay ile kalici bilgi."""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.api.chat as chat_module
import app.api.jobs as jobs_module
from app.agent.insights import (
    Signal,
    budget_signals,
    compute_signals,
    estimate_signal,
    fresh_signals,
    parse_reply,
    peak_hours_signal,
    run_weekly_insights,
    weekday_signal,
)
from app.api.deps import current_user
from app.db.models import AiInsightEntity, AiJobEntity, UserFactEntity
from app.llm.types import ModelInfo
from app.main import app
from app.tools.privacy import PrivacyFilter
from app.tools.task_api import TaskApiClient
from tests.conftest import FakeProvider, FakeTaskApi, text

END = date(2026, 11, 8)  # Pazar
USER = {"id": 7, "full_name": "Ali", "token": "tkn"}


def month_days() -> list[dict]:
    """28 gun: sali gunleri planin %25'i, diger gunler %100 biter."""
    out = []
    for i in range(28):
        d = END - timedelta(days=i)
        tuesday = d.weekday() == 1
        out.append(
            {
                "date": d.isoformat(),
                "reviewed": True,
                "planned": 4,
                "done": 1 if tuesday else 4,
                "partial": 0,
                "energy": 2 if tuesday else 4,
            }
        )
    return out


MONTH = {
    "days": month_days(),
    "estimate_accuracy": {"sample_size": 5, "median_ratio": 1.4},
    "productive_hours": [0] * 20 + [200, 200, 0, 0],
    "most_postponed": [{"card_id": 21, "title": "Gizli date planı", "count": 4}],
    "boards": [],
    "totals": {},
}
WEEK = {
    "totals": {
        "tracked_min": 400,
        "done_items": 20,
        "planned_items": 25,
        "reviewed_days": 7,
    },
    "boards": [
        {"board_id": 1, "name": "Spor", "tracked_min": 60, "budget_min": 210},
        {"board_id": 2, "name": "Date planları", "tracked_min": 0, "budget_min": 120},
    ],
}


# ---------------- sinyaller ----------------
def test_weekday_signal_finds_weak_day():
    s = weekday_signal(month_days())
    assert s.key == "weekday_low:1" and s.evidence["weekday"] == "Salı"
    assert "%25" in s.text
    assert weekday_signal(month_days()[:3]) is None  # az veri


def test_other_signals():
    assert (
        estimate_signal(MONTH).text
        == "İşlerin genelde tahmin ettiğinden %40 uzun sürüyor."
    )
    assert (
        estimate_signal({"estimate_accuracy": {"sample_size": 5, "median_ratio": 1.1}})
        is None
    )
    peak = peak_hours_signal(MONTH["productive_hours"])
    assert peak.key == "peak_hours:20" and "20:00–22:00" in peak.text
    assert peak_hours_signal([1] * 24) is None


def test_cloud_hides_private_board_and_postponed_cards():
    cloud = PrivacyFilter(active=True, hidden_boards={2})
    assert [s.key for s in budget_signals(WEEK["boards"], cloud)] == ["budget_low:1"]
    keys = {s.key for s in compute_signals(MONTH, WEEK, cloud)}
    assert "postponed:21" not in keys and "budget_low:2" not in keys
    local = {s.key for s in compute_signals(MONTH, WEEK, PrivacyFilter())}
    assert {"postponed:21", "budget_low:2", "energy_effect", "weekday_low:1"} <= local


def test_parse_reply():
    summary, texts = parse_reply(
        '```json\n{"week_summary": "İyi hafta.", "insights": '
        '[{"id": "s2", "text": "B"}, {"id": "9", "text": "x"}, {"id": "s1", "text": " A "}]}```',
        2,
    )
    assert summary == "İyi hafta." and texts == {1: "A", 2: "B"}
    assert parse_reply("metin", 2) == (None, {})


async def test_fresh_signals_skip_confirmed_and_recent(db_session_maker):
    now = datetime.now(UTC)
    async with db_session_maker() as s:
        for key, status, age in (
            ("a", "confirmed", 90),
            ("b", "rejected", 5),
            ("c", "rejected", 40),
        ):
            s.add(
                AiInsightEntity(
                    user_id=7,
                    key=key,
                    observation=key,
                    status=status,
                    created_at=now - timedelta(days=age),
                )
            )
        await s.commit()
        sig = [Signal(k, "routine", k) for k in "abcd"]
        assert [x.key for x in await fresh_signals(s, 7, sig, now)] == ["c", "d"]


# ---------------- is ----------------
class InsightApi(FakeTaskApi):
    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        if path == "/analytics/summary":
            start = date.fromisoformat(request.url.params["start"])
            data = WEEK if (END - start).days < 7 else MONTH
            return httpx.Response(200, json={"success": True, "data": data})
        return super().__call__(request)


async def test_run_creates_insights_with_model_text(db_session_maker):
    api = TaskApiClient("tkn", transport=httpx.MockTransport(InsightApi()))
    reply = json.dumps(
        {
            "week_summary": "Yoğun bir hafta.",
            "insights": [{"id": "s1", "text": "Salı zor geçiyor."}],
        },
        ensure_ascii=False,
    )
    provider = FakeProvider([[text(reply)]])
    result = await run_weekly_insights(
        api, provider, db_session_maker, user_id=7, end=END
    )
    await api.close()
    assert result["week_summary"] == "Yoğun bir hafta."
    async with db_session_maker() as s:
        rows = list(
            await s.scalars(select(AiInsightEntity).order_by(AiInsightEntity.id))
        )
    assert len(rows) == 4 and all(r.status == "new" for r in rows)
    assert rows[0].observation == "Salı zor geçiyor."
    assert rows[0].evidence["data_text"]  # verideki hali kanit olarak saklanir
    assert (
        rows[1].observation == rows[1].evidence["data_text"]
    )  # model yazmadiysa veri cumlesi

    # Sonraki calismalar ayni gozlemleri tekrar onermez: once kalan 3 sinyal,
    # sonra hicbiri (model hic cagrilmaz)
    counts = []
    for _ in range(2):
        api = TaskApiClient("tkn", transport=httpx.MockTransport(InsightApi()))
        provider2 = FakeProvider([])
        result = await run_weekly_insights(
            api, provider2, db_session_maker, user_id=7, end=END
        )
        await api.close()
        counts.append((len(result["insight_ids"]), len(provider2.received)))
    assert counts == [(3, 1), (0, 0)]


# ---------------- API ----------------
@pytest.fixture
async def client(monkeypatch, db_session_maker):
    transport = httpx.MockTransport(InsightApi())

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
        chat_module, "build_provider", lambda mid, cloud=None, **_: FakeProvider([])
    )

    async def fake_session():
        async with db_session_maker() as s:
            yield s

    app.dependency_overrides[current_user] = lambda: USER
    app.dependency_overrides[chat_module.get_session] = fake_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.db = db_session_maker  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


async def test_analyze_confirm_and_reject(client):
    res = await client.post(f"/api/v1/assistant/insights/analyze?day={END}")
    assert res.status_code == 200, res.text
    await asyncio.gather(*jobs_module._TASKS)
    data = (await client.get("/api/v1/assistant/insights")).json()["data"]
    assert data["job"]["status"] == "done"
    items = data["items"]
    assert len(items) == 4

    first, second = items[0], items[1]
    res = await client.post(
        f"/api/v1/assistant/insights/{first['id']}/confirm",
        json={"content": "Salı günleri daha az iş bitiriyorum."},
    )
    assert res.json()["data"]["status"] == "confirmed"
    async with client.db() as s:
        fact = await s.scalar(select(UserFactEntity))
    assert fact.source == "insight_confirmed"
    assert fact.content == "Salı günleri daha az iş bitiriyorum."

    res = await client.post(
        f"/api/v1/assistant/insights/{second['id']}/reject", json={"reason": "tesadüf"}
    )
    assert res.json()["data"]["user_feedback"] == "tesadüf"
    again = await client.post(
        f"/api/v1/assistant/insights/{second['id']}/reject", json={}
    )
    assert again.status_code == 409


async def test_weekly_runs_after_day_review_once_a_week(client):
    async with client.db() as s:
        job = AiJobEntity(
            user_id=7,
            kind="day_review",
            target_date=str(END),
            status="queued",
            model_id="ollama:gemma4:26b",
        )
        s.add(job)
        await s.commit()
    # Gun sonu isi basarisiz olsa da (sahte veride gun degerlendirilmemis) haftalik calismaz
    await jobs_module.run_job(job.id, "day_review", USER, "ollama:gemma4:26b", END)
    async with client.db() as s:
        kinds = [j.kind for j in await s.scalars(select(AiJobEntity))]
    assert kinds == ["day_review"]

    original = jobs_module._execute
    calls: list[str] = []

    async def spy(job_id, kind, *a):
        calls.append(kind)
        return True if kind == "day_review" else await original(job_id, kind, *a)

    jobs_module._execute = spy  # type: ignore[assignment]
    try:
        await jobs_module.run_job(job.id, "day_review", USER, "ollama:gemma4:26b", END)
        await jobs_module.run_job(job.id, "day_review", USER, "ollama:gemma4:26b", END)
    finally:
        jobs_module._execute = original  # type: ignore[assignment]
    assert calls == ["day_review", "weekly_insight", "day_review"]
