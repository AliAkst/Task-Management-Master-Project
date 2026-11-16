"""Faz 13j2: yerel Ingilizce kocu - dogrulayici (G1), uclar, izin kapisi, yerel zorunlulugu.

Gercek model yok (FakeProvider); saat/zaman duvar saatine bagli degil (today_fn sabit).
"""

import json
from datetime import date
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

import app.api.english as english_module
from app.agent.actions import set_mode
from app.agent.english_coach import parse_correction
from app.api.deps import current_user
from app.db.models import AiActionEntity
from app.main import app
from app.tools.task_api import TaskApiClient
from tests.conftest import FakeProvider, text
from tests.test_chat_api import USER

API = "/api/v1/assistant/english"
TODAY = date(2026, 11, 10)


# ---------------- sahte task-api (Ingilizce uclari) ----------------
class FakeEnglishApi:
    """/english/* uclarini taklit eder; geri kalani FakeTaskApi'ye birakir."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.writes: list[dict[str, Any]] = []
        self.vocab = [
            {"id": 1, "term": "reluctant", "meaning_tr": "isteksiz"},
            {"id": 2, "term": "thrive", "meaning_tr": "gelişmek"},
            {"id": 3, "term": "gather", "meaning_tr": "toplamak"},
        ]
        self.mistakes: list[dict[str, Any]] = []
        self.sessions: list[dict[str, Any]] = []
        self.profile: dict[str, Any] | None = {"target_level": "B2", "daily_minutes": 15}
        self.top_categories = [{"category": "tense", "count": 4}]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        if not path.startswith("/english"):
            return self.inner(request)
        method = request.method

        def ok(data: Any) -> httpx.Response:
            return httpx.Response(200, json={"success": True, "data": data})

        body = json.loads(request.content) if request.content else None
        if method == "GET" and path == "/english/vocab":
            return ok(self.vocab)
        if method == "GET" and path == "/english/mistakes":
            return ok(self.mistakes)
        if method == "GET" and path == "/english/sessions":
            return ok(self.sessions)
        if method == "GET" and path == "/english/today":
            return ok(
                {
                    "profile": self.profile,
                    "due_vocab": self.vocab,
                    "top_categories": self.top_categories,
                    "practiced_today": False,
                    "task": None,
                }
            )
        if method == "POST":
            self.writes.append(
                {"path": path, "body": body, "actor": request.headers.get("x-actor")}
            )
            if path == "/english/mistakes":
                self.mistakes += body["items"]
            if path == "/english/sessions":
                self.sessions.append(
                    {**body, "started_at": f"{TODAY.isoformat()}T09:00:00+03:00"}
                )
            return ok({"id": 1})
        return httpx.Response(404, json={"success": False, "error": {"message": "yok"}})


@pytest.fixture
def eng_api(fake_api) -> FakeEnglishApi:
    return FakeEnglishApi(fake_api)


def good(*rows: dict) -> str:
    return json.dumps({"results": list(rows)}, ensure_ascii=False)


ROW1 = {
    "i": 1,
    "corrected": "I went home yesterday.",
    "mistakes": [
        {
            "original": "I have went",
            "corrected": "I went",
            "category": "tense",
            "explanation_tr": "Geçmiş zaman",
        }
    ],
}
ROW2 = {"i": 2, "corrected": "She happy.", "mistakes": []}


@pytest.fixture
async def client(monkeypatch, db_session_maker, eng_api):
    holder: dict[str, Any] = {"provider": None, "installed": ["ollama:fake"]}

    async def installed():
        from app.llm.types import ModelInfo

        return [
            ModelInfo(id=i, provider="ollama", model=i, label=i, is_local=True)
            for i in holder["installed"]
        ]

    monkeypatch.setattr(english_module, "list_local_models", installed)
    monkeypatch.setattr(
        english_module, "build_provider", lambda mid, cloud=None, **_: holder["provider"]
    )
    monkeypatch.setattr(english_module, "session_maker", db_session_maker)
    monkeypatch.setattr(english_module, "today_fn", lambda tz: TODAY)
    monkeypatch.setattr(
        english_module,
        "TaskApiClient",
        lambda token: TaskApiClient(token, transport=httpx.MockTransport(eng_api)),
    )

    async def fake_session():
        async with db_session_maker() as s:
            yield s

    app.dependency_overrides[current_user] = lambda: USER
    app.dependency_overrides[english_module.get_session] = fake_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.holder = holder  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


def set_provider(client, script):
    p = FakeProvider([[text(s)] for s in script])
    client.holder["provider"] = p
    return p


# ---------------- G1: parse_correction bozuk girdi listesi (n=2) ----------------
S2 = ["I have went home.", "She happy."]


def test_parse_not_json_is_none():
    assert parse_correction("", S2) is None
    assert parse_correction("Sure! Here you go", S2) is None


def test_parse_results_not_list_is_none():
    assert parse_correction('{"results": "x"}', S2) is None


def test_parse_empty_results_all_unevaluated():
    out = parse_correction('{"results": []}', S2)
    assert [r.ok for r in out] == [None, None]
    assert [r.corrected for r in out] == S2


def test_parse_missing_second_sentence():
    raw = json.dumps({"results": [{"i": 1, "corrected": "I went home.", "mistakes": []}]})
    out = parse_correction(raw, S2)
    assert out[0].corrected == "I went home." and out[0].ok is False
    assert out[1].ok is None and out[1].mistakes == []


def test_parse_out_of_range_index_ignored():
    out = parse_correction(json.dumps({"results": [{"i": 3, "corrected": "X."}]}), S2)
    assert [r.ok for r in out] == [None, None]


def test_parse_missing_i_maps_in_order():
    out = parse_correction(good({"corrected": "A."}, {"corrected": "B."}), S2)
    assert [r.corrected for r in out] == ["A.", "B."]


def _mistake_row(**kw):
    m = {"original": "went", "corrected": "go", "category": "tense", "explanation_tr": "x"}
    m.update(kw)
    return good({"i": 1, "corrected": "I go home.", "mistakes": [m]})


def test_parse_category_case_insensitive():
    out = parse_correction(_mistake_row(category="Grammar"), S2)
    assert out[0].mistakes[0]["category"] == "grammar"


def test_parse_unknown_category_becomes_other():
    out = parse_correction(_mistake_row(category="syntax"), S2)
    assert out[0].mistakes[0]["category"] == "other"


def test_parse_mistakes_not_list_is_empty():
    raw = good({"i": 1, "corrected": "I went home.", "mistakes": "none"})
    out = parse_correction(raw, S2)
    assert out[0].mistakes == []


def test_parse_long_corrected_uses_original_unevaluated():
    out = parse_correction(good({"i": 1, "corrected": "x" * 1000, "mistakes": []}), S2)
    assert out[0].corrected == S2[0] and out[0].ok is None


def test_parse_code_fence_is_stripped():
    raw = "```json\n" + good(ROW1, ROW2) + "\n```"
    out = parse_correction(raw, S2)
    assert out is not None and out[0].ok is False and out[1].ok is True


def test_parse_two_objects_in_a_row_is_none():
    assert parse_correction(good(ROW1) + "\n" + good(ROW2), S2) is None


def test_parse_same_as_original_clears_mistakes():
    raw = good({"i": 2, "corrected": S2[1], "mistakes": ROW1["mistakes"]})
    out = parse_correction(raw, S2)
    assert out[1].ok is True and out[1].mistakes == []


def test_parse_empty_mistake_original_skipped():
    out = parse_correction(_mistake_row(original=""), S2)
    assert out[0].mistakes == []


def test_parse_string_index_accepted():
    out = parse_correction(good({"i": "2", "corrected": "She is happy."}), S2)
    assert out[1].corrected == "She is happy." and out[0].ok is None


def test_parse_duplicate_index_keeps_first():
    out = parse_correction(good({"i": 1, "corrected": "A."}, {"i": 1, "corrected": "B."}), S2)
    assert out[0].corrected == "A."


def test_parse_hostile_shapes_do_not_raise():
    for raw in ("[]", "null", '{"results":[1,"a",null,[]]}', '{"results":[{"i":true}]}',
                '{"results":[{"i":1,"mistakes":[1,null,{"original":5}]}]}'):  # fmt: skip
        out = parse_correction(raw, S2)
        assert out is None or len(out) == 2


# ---------------- uc: correct ----------------
async def test_correct_saves_mistakes_as_local_when_auto(client, eng_api):
    p = set_provider(client, [good(ROW1, ROW2)])
    res = await client.post(f"{API}/correct", json={"sentences": S2})
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert [r["ok"] for r in data["results"]] == [False, True]
    assert data["saved"] == 1 and data["model"] == "ollama:fake"
    posts = {w["path"]: w for w in eng_api.writes}
    m = posts["/english/mistakes"]
    assert m["body"]["items"][0]["source"] == "local" and m["actor"] == "ai"
    assert m["body"]["items"][0]["original"] == "I have went"
    s = posts["/english/sessions"]["body"]
    assert s["kind"] == "daily" and s["minutes"] == 5 and s["mistakes_count"] == 1
    assert "/english/vocab" not in posts  # kelime hic eklenmez
    assert "Sentences:" in p.all_text_sent() and "1) I have went home." in p.all_text_sent()


async def test_correct_ask_mode_proposes_instead_of_writing(client, eng_api, db_session_maker):
    async with db_session_maker() as s:
        await set_mode(s, USER["id"], "log_english", "ask")
        await s.commit()
    set_provider(client, [good(ROW1, ROW2)])
    data = (await client.post(f"{API}/correct", json={"sentences": S2})).json()["data"]
    assert data["saved"] == 0 and isinstance(data["pending_action_id"], int)
    assert [w for w in eng_api.writes if w["path"].startswith("/english")] == []
    async with db_session_maker() as s:
        row = await s.get(AiActionEntity, data["pending_action_id"])
        assert row.status == "proposed" and row.action_type == "log_english"


async def test_correct_never_mode_still_returns_corrections_without_saving(
    client, eng_api, db_session_maker
):
    async with db_session_maker() as s:
        await set_mode(s, USER["id"], "log_english", "never")
        await s.commit()
    set_provider(client, [good(ROW1, ROW2)])
    res = await client.post(f"{API}/correct", json={"sentences": S2})
    assert res.status_code == 200 and res.json()["data"]["saved"] == 0
    assert eng_api.writes == []


async def test_correct_invalid_reply_retries_once_then_502(client):
    p = set_provider(client, ["Sure!", "still not json"])
    res = await client.post(f"{API}/correct", json={"sentences": S2})
    assert res.status_code == 502 and "geçerli yanıt" in res.json()["error"]["message"]
    assert len(p.received) == 2


async def test_correct_retry_can_succeed(client):
    p = set_provider(client, ["nope", good(ROW1, ROW2)])
    res = await client.post(f"{API}/correct", json={"sentences": S2})
    assert res.status_code == 200 and len(p.received) == 2


async def test_correct_without_mistakes_writes_nothing(client, eng_api):
    set_provider(client, [good({"i": 1, "corrected": S2[0]}, {"i": 2, "corrected": S2[1]})])
    data = (await client.post(f"{API}/correct", json={"sentences": S2})).json()["data"]
    assert data["saved"] == 0 and all(r["ok"] for r in data["results"])
    assert eng_api.writes == []


async def test_second_correct_same_day_writes_no_new_session(client, eng_api):
    set_provider(client, [good(ROW1, ROW2), good(ROW1, ROW2)])
    await client.post(f"{API}/correct", json={"sentences": S2})
    await client.post(f"{API}/correct", json={"sentences": S2})
    sessions = [w for w in eng_api.writes if w["path"] == "/english/sessions"]
    assert len(sessions) == 1
    assert len([w for w in eng_api.writes if w["path"] == "/english/mistakes"]) == 2


@pytest.mark.parametrize(
    "body",
    [
        {"sentences": []},
        {"sentences": ["a"] * 6},
        {"sentences": [""]},
        {"sentences": ["x" * 301]},
        {},
    ],
)
async def test_correct_validates_input(client, body):
    set_provider(client, [])
    assert (await client.post(f"{API}/correct", json=body)).status_code == 422


async def test_correct_never_uses_cloud_provider(client, monkeypatch, db_session_maker):
    """Arka plan modeli bulut olsa da yerel model kullanilir; yerel yoksa 503."""
    from app.db.models import ModelPrefEntity

    async with db_session_maker() as s:
        s.add(
            ModelPrefEntity(
                user_id=USER["id"],
                default_model_id="anthropic:claude-x",
                background_model_id="openai:gpt-x",
            )
        )
        await s.commit()
    built: list[str] = []
    prov = FakeProvider([[text(good(ROW1, ROW2))]])

    def build(mid, cloud=None, **_):
        built.append(mid)
        return prov

    monkeypatch.setattr(english_module, "build_provider", build)
    res = await client.post(f"{API}/correct", json={"sentences": S2})
    assert res.status_code == 200 and built == ["ollama:fake"]

    client.holder["installed"] = []
    res = await client.post(f"{API}/correct", json={"sentences": S2})
    assert res.status_code == 503 and "Yerel model yok" in res.json()["error"]["message"]
    assert built == ["ollama:fake"]  # bulut icin hic provider kurulmadi


async def test_endpoints_need_login_and_reject_pat(client):
    app.dependency_overrides.pop(current_user, None)
    res = await client.post(f"{API}/correct", json={"sentences": S2})
    assert res.status_code == 401
    res = await client.post(
        f"{API}/correct", json={"sentences": S2}, headers={"Authorization": "Bearer pat_x"}
    )
    assert res.status_code == 403


# ---------------- uc: dialog ----------------
async def test_dialog_returns_reply_and_corrections(client):
    raw = json.dumps(
        {
            "reply": "Nice! Where did you go?",
            "corrections": [
                {"original": "I goed", "corrected": "I went", "category": "tense",
                 "explanation_tr": "Düzensiz fiil"}  # fmt: skip
            ],
        }
    )
    p = set_provider(client, [raw])
    body = {
        "history": [{"role": "coach", "text": "Hi!"}, {"role": "user", "text": "Hello"}],
        "user_text": "I goed to cinema",
    }
    data = (await client.post(f"{API}/dialog", json=body)).json()["data"]
    assert data["reply"].startswith("Nice") and data["corrections"][0]["corrected"] == "I went"
    assert "I goed to cinema" in p.all_text_sent()


async def test_dialog_limits_history_to_ten_turns(client):
    set_provider(client, [])
    hist = [{"role": "user", "text": "hi"}] * 11
    res = await client.post(f"{API}/dialog", json={"history": hist, "user_text": "ok"})
    assert res.status_code == 422
    bad_role = [{"role": "system", "text": "hi"}]
    res = await client.post(f"{API}/dialog", json={"history": bad_role, "user_text": "ok"})
    assert res.status_code == 422


async def test_dialog_invalid_reply_502_after_one_retry(client):
    p = set_provider(client, ["garbage", "more garbage"])
    res = await client.post(f"{API}/dialog", json={"history": [], "user_text": "hello"})
    assert res.status_code == 502 and len(p.received) == 2


# ---------------- uc: example ----------------
async def test_example_builds_prompt_without_model(client):
    p = set_provider(client, [])
    client.holder["provider"] = None  # model kurulursa patlar
    res = await client.post(f"{API}/example", json={"vocab_ids": [1, 3]})
    assert res.status_code == 200, res.text
    prompt = res.json()["data"]["prompt"]
    assert "reluctant" in prompt and "gather" in prompt and "thrive" not in prompt
    assert p.received == []


async def test_example_validates_ids(client):
    assert (await client.post(f"{API}/example", json={"vocab_ids": []})).status_code == 422
    too_many = {"vocab_ids": [1, 2, 3, 4, 5, 6]}
    assert (await client.post(f"{API}/example", json=too_many)).status_code == 422
    res = await client.post(f"{API}/example", json={"vocab_ids": [99]})
    assert res.status_code == 404
