"""Faz 7d: asistan Gelen Kutusu'nu board'lara dagitir (arka plan isi + onay karti)."""

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
from app.agent.inbox_triage import (
    Candidate,
    Target,
    build_candidates,
    parse_output,
    pick,
    run_inbox_triage,
)
from app.api.deps import current_user
from app.db.models import AiActionEntity, AiPermissionEntity
from app.llm.types import ModelInfo
from app.main import app
from app.tools.task_api import TaskApiClient
from tests.conftest import FakeProvider, text

TZ = ZoneInfo("Europe/Istanbul")
USER = {"id": 7, "full_name": "Ali", "token": "tkn"}

INBOX_ID, SPOR_ID, IS_ID, GIZLI_ID = 5, 1, 3, 2


def _list(id_, name, done=False):
    return {"id": id_, "name": name, "is_done_list": done}


BOARDS = {
    INBOX_ID: {
        "id": INBOX_ID,
        "name": "Gelen Kutusu",
        "system_kind": "inbox",
        "privacy": "local_only",
        "scope_description": None,
        "is_archived": False,
        "lists": [_list(50, "Gelen")],
    },
    SPOR_ID: {
        "id": SPOR_ID,
        "name": "Spor",
        "system_kind": None,
        "privacy": "cloud_allowed",
        "scope_description": "Koşu, salon, beslenme",
        "is_archived": False,
        "lists": [_list(10, "Yapılacak"), _list(11, "Tamamlandı", True)],
    },
    IS_ID: {
        "id": IS_ID,
        "name": "İş",
        "system_kind": None,
        "privacy": "cloud_allowed",
        "scope_description": "Toplantılar, raporlar",
        "is_archived": False,
        "lists": [_list(30, "Yapılacak"), _list(31, "Sürüyor")],
    },
    GIZLI_ID: {
        "id": GIZLI_ID,
        "name": "Gizli date planları",
        "system_kind": None,
        "privacy": "local_only",
        "scope_description": "Özel",
        "is_archived": False,
        "lists": [_list(20, "Yapılacak")],
    },
}


def _card(id_, title, board_id=INBOX_ID, **kw):
    return {
        "id": id_,
        "title": title,
        "board_id": board_id,
        "list_id": 50,
        "status": "pending",
        "priority": "medium",
        "due_date": None,
        "is_archived": False,
        "parent_id": None,
        **kw,
    }


class InboxApi:
    """Gelen Kutusu'nda 3 kart; tasima isteklerini kaydeder, kartin board'unu gunceller."""

    def __init__(self) -> None:
        self.cards = {
            101: _card(101, "Koşu ayakkabısı al", description="Salon için"),
            102: _card(102, "Haftalık raporu hazırla"),
            103: _card(103, "Belirsiz not"),
            104: _card(104, "Bitmiş iş", status="completed"),
        }
        self.writes: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")

        def ok(data):
            return httpx.Response(200, json={"success": True, "data": data})

        if request.method == "GET" and path == "/settings/":
            return ok({"timezone": "Europe/Istanbul"})
        if request.method == "GET" and path == "/boards":
            return ok([{k: v for k, v in b.items() if k != "lists"} for b in BOARDS.values()])
        if request.method == "GET" and path.startswith("/boards/"):
            b = BOARDS[int(path.split("/")[2])]
            return ok(
                {
                    "board": {k: v for k, v in b.items() if k != "lists"},
                    "lists": b["lists"],
                    "cards": [c for c in self.cards.values() if c["board_id"] == b["id"]],
                    "labels": [],
                }
            )
        if request.method == "GET" and path.startswith("/cards/"):
            c = self.cards[int(path.split("/")[2])]
            return ok({"description": None, **c})
        if request.method == "POST" and path.endswith("/move"):
            body = json.loads(request.content)
            cid = int(path.split("/")[2])
            self.writes.append(
                {"path": path, "body": body, "actor": request.headers.get("X-Actor")}
            )
            board = next(
                b for b in BOARDS.values() if body["list_id"] in [x["id"] for x in b["lists"]]
            )
            self.cards[cid]["board_id"] = board["id"]
            self.cards[cid]["list_id"] = body["list_id"]
            return ok(self.cards[cid])
        return httpx.Response(404, json={"success": False, "error": {"message": "yok"}})


@pytest.fixture
def inbox_api() -> InboxApi:
    return InboxApi()


REPLY = json.dumps(
    {
        "moves": [
            {"card_id": 101, "board_id": SPOR_ID, "list_id": 10, "reason": "Spor malzemesi"},
            {"card_id": 102, "board_id": IS_ID, "reason": "İş raporu"},
            {"card_id": 103, "board_id": 99, "reason": "uydurma board"},
            {"card_id": 777, "board_id": SPOR_ID, "reason": "uydurma kart"},
            {"card_id": 101, "board_id": IS_ID, "reason": "tekrar"},
            {"card_id": 102, "board_id": INBOX_ID, "reason": "kendisine"},
            {"card_id": 104, "board_id": SPOR_ID, "reason": "bitmiş kart aday değil"},
        ]
    },
    ensure_ascii=False,
)


def _provider(reply=REPLY, *, is_local=True):
    return FakeProvider([[text(reply)]], is_local=is_local)


async def _run(api_obj, provider, maker):
    api = TaskApiClient("tkn", transport=httpx.MockTransport(api_obj))
    try:
        return await run_inbox_triage(api, provider, maker, user_id=7, tz=TZ)
    finally:
        await api.close()


# ---------------- saf yardimcilar ----------------
def test_parse_output_tolerates_fences_and_rejects_garbage():
    assert parse_output('```json\n{"moves": [{"card_id": 1}]}\n```') == [{"card_id": 1}]
    assert parse_output("düz metin") is None
    assert parse_output('{"moves": "x"}') is None


def test_candidates_skip_done_archived_subtasks_and_excluded():
    cards = [
        _card(1, "A"),
        _card(2, "B", status="completed"),
        _card(3, "C", is_archived=True),
        _card(4, "D", parent_id=1),
        _card(5, "E"),
    ]
    got = build_candidates(cards, {1: {"description": "  uzun   açıklama "}}, {5})
    assert [(c.card_id, c.description) for c in got] == [(1, "uzun açıklama")]


def test_candidates_capped_at_twenty():
    cards = [_card(i, f"K{i}") for i in range(1, 40)]
    assert len(build_candidates(cards, {}, set())) == 20


def test_pick_validates_ids_dedups_and_defaults_list():
    cands = [Candidate(1, "A", None, None, None), Candidate(2, "B", None, None, None)]
    targets = {
        SPOR_ID: Target(SPOR_ID, "Spor", None, BOARDS[SPOR_ID]["lists"]),
    }
    got = pick(
        cands,
        targets,
        [
            {"card_id": 1, "board_id": SPOR_ID, "list_id": 999, "reason": " iyi "},
            {"card_id": 1, "board_id": SPOR_ID},  # tekrar
            {"card_id": 2, "board_id": 42},  # bilinmeyen board
            {"card_id": 9, "board_id": SPOR_ID},  # bilinmeyen kart
            "bozuk",
            {"card_id": "x", "board_id": SPOR_ID},
        ],
    )
    # Gecersiz liste -> ilk bitmemis liste
    assert got == [
        {"card_id": 1, "title": "A", "board_id": SPOR_ID, "list_id": 10, "reason": "iyi"}
    ]


# ---------------- uctan uca ----------------
async def test_local_run_proposes_validated_moves(inbox_api, db_session_maker):
    provider = _provider()
    result, action_id = await _run(inbox_api, provider, db_session_maker)

    assert [(m["card_id"], m["board_id"], m["list_id"]) for m in result["moves"]] == [
        (101, SPOR_ID, 10),
        (102, IS_ID, 30),  # liste verilmedi -> ilk liste
    ]
    assert result["candidate_count"] == 3  # tamamlanmis kart aday degil
    assert result["moves"][0]["reason"] == "Spor malzemesi"
    assert result["action_status"] == "proposed"
    # Onay bekler: kartlara henuz dokunulmadi
    assert inbox_api.writes == []
    async with db_session_maker() as s:
        action = await s.get(AiActionEntity, action_id)
    assert action.action_type == "triage_inbox" and action.status == "proposed"
    assert action.conversation_id is None
    assert "Koşu ayakkabısı al → Spor / Yapılacak" in action.summary
    sent = provider.all_text_sent()
    assert "Salon için" in sent  # aciklama yonlendirmeye yardim eder
    assert "Koşu, salon, beslenme" in sent  # board kapsami
    assert "Gizli date planları" in sent  # local model hepsini gorur


async def test_cloud_model_never_sees_private_inbox(inbox_api, db_session_maker):
    provider = _provider(is_local=False)
    result, action_id = await _run(inbox_api, provider, db_session_maker)
    # Gelen Kutusu varsayilan local_only -> bulut modele hicbir sey gitmez
    assert action_id is None and result["moves"] == []
    assert provider.received == []
    assert "gizli" in result["notes"][0]


async def test_cloud_with_open_inbox_hides_private_target_boards(
    inbox_api, db_session_maker, monkeypatch
):
    monkeypatch.setitem(BOARDS[INBOX_ID], "privacy", "cloud_allowed")
    provider = _provider(
        json.dumps({"moves": [{"card_id": 101, "board_id": GIZLI_ID, "reason": "x"}]}),
        is_local=False,
    )
    result, action_id = await _run(inbox_api, provider, db_session_maker)
    sent = provider.all_text_sent()
    assert "Gizli date planları" not in sent and "Özel" not in sent
    assert action_id is None and result["moves"] == []  # gizli board gecersiz sayildi


async def test_empty_inbox_does_not_call_model(inbox_api, db_session_maker):
    inbox_api.cards = {104: _card(104, "Bitmiş", status="completed")}
    provider = _provider()
    result, action_id = await _run(inbox_api, provider, db_session_maker)
    assert action_id is None and provider.received == []
    assert "yeni kart yok" in result["notes"][0]


async def test_unparseable_reply_gives_note(inbox_api, db_session_maker):
    result, action_id = await _run(inbox_api, _provider("bilmiyorum"), db_session_maker)
    assert action_id is None and "biçimde" in result["notes"][0]


async def test_model_unsure_about_all_cards(inbox_api, db_session_maker):
    result, action_id = await _run(
        inbox_api, _provider('{"moves": []}'), db_session_maker
    )
    assert action_id is None and "emin olamadı" in result["notes"][0]


async def test_rejected_and_pending_cards_not_proposed_again(inbox_api, db_session_maker):
    first, action_id = await _run(inbox_api, _provider(), db_session_maker)
    assert action_id

    async def second_prompt() -> str:
        provider = _provider('{"moves": []}')
        await _run(inbox_api, provider, db_session_maker)
        return provider.all_text_sent()

    # Bekleyen oneri varken 101/102 aday degil (sadece onerilmemis 103 kaldi)
    sent = await second_prompt()
    assert "Belirsiz not" in sent and "Koşu ayakkabısı" not in sent

    # Reddedilen de 14 gun beklenir
    async with db_session_maker() as s:
        a = await s.get(AiActionEntity, action_id)
        a.status, a.user_feedback = "rejected", "Hepsi iş değil"
        await s.commit()
    sent = await second_prompt()
    assert "Koşu ayakkabısı" not in sent and "Hepsi iş değil" in sent

    # 15 gun sonra tekrar aday olur
    async with db_session_maker() as s:
        a = await s.get(AiActionEntity, action_id)
        a.created_at = datetime.now(TZ) - timedelta(days=15)
        await s.commit()
    assert "Koşu ayakkabısı" in await second_prompt()


async def test_all_cards_already_proposed_skips_model(inbox_api, db_session_maker):
    await _run(inbox_api, _provider(), db_session_maker)  # 101, 102 onerildi
    inbox_api.cards.pop(103)
    provider = _provider()
    result, none_id = await _run(inbox_api, provider, db_session_maker)
    assert none_id is None and provider.received == []
    assert "zaten öneri var" in result["notes"][0]


async def test_only_unproposed_cards_are_candidates(inbox_api, db_session_maker):
    await _run(inbox_api, _provider(), db_session_maker)  # 101, 102 onerildi
    provider = _provider(
        json.dumps({"moves": [{"card_id": 103, "board_id": IS_ID, "reason": "y"}]})
    )
    result, new_id = await _run(inbox_api, provider, db_session_maker)
    assert result["candidate_count"] == 1 and new_id
    assert "Belirsiz not" in provider.all_text_sent()
    assert "Koşu ayakkabısı" not in provider.all_text_sent()


async def test_permission_modes(inbox_api, db_session_maker):
    async with db_session_maker() as s:
        s.add(AiPermissionEntity(user_id=7, action_type="triage_inbox", mode="auto"))
        await s.commit()
    result, action_id = await _run(inbox_api, _provider(), db_session_maker)
    assert result["action_status"] == "executed"
    assert [w["actor"] for w in inbox_api.writes] == ["ai", "ai"]
    assert inbox_api.cards[101]["board_id"] == SPOR_ID
    assert inbox_api.cards[102]["board_id"] == IS_ID
    assert inbox_api.cards[103]["board_id"] == INBOX_ID

    async with db_session_maker() as s:
        row = await s.scalar(select(AiPermissionEntity))
        row.mode = "never"
        await s.commit()
    inbox_api.cards[101]["board_id"] = INBOX_ID  # tekrar gelen kutusunda
    inbox_api.cards[102]["board_id"] = INBOX_ID
    async with db_session_maker() as s:  # onceki oneri kaydi yeni isi etkilemesin
        for a in await s.scalars(select(AiActionEntity)):
            await s.delete(a)
        await s.commit()
    result, action_id = await _run(inbox_api, _provider(), db_session_maker)
    assert action_id is None and "kapalı" in result["notes"][0]


# ---------------- API: is + onay (madde madde) ----------------
@pytest.fixture
async def client(monkeypatch, db_session_maker, inbox_api):
    transport = httpx.MockTransport(inbox_api)

    async def installed():
        return [ModelInfo("ollama:gemma4:26b", "ollama", "gemma4:26b", "gemma4", True)]

    monkeypatch.setattr(chat_module, "list_local_models", installed)
    monkeypatch.setattr(chat_module, "session_maker", db_session_maker)
    monkeypatch.setattr(
        chat_module, "TaskApiClient", lambda token: TaskApiClient(token, transport=transport)
    )
    monkeypatch.setattr(
        chat_module, "build_provider", lambda mid, cloud=None, **_: _provider()
    )
    async def fake_session():
        async with db_session_maker() as s:
            yield s

    app.dependency_overrides[current_user] = lambda: USER
    app.dependency_overrides[chat_module.get_session] = fake_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()


async def test_job_then_approve_with_excluded_card(client, inbox_api):
    assert (await client.get("/api/v1/assistant/inbox-triage")).json()["data"] is None
    res = await client.post("/api/v1/assistant/inbox-triage")
    assert res.status_code == 200, res.text
    await asyncio.gather(*jobs_module._TASKS)

    job = (await client.get("/api/v1/assistant/inbox-triage")).json()["data"]
    assert job["status"] == "done", job
    assert [m["card_id"] for m in job["result"]["moves"]] == [101, 102]
    assert job["action"]["status"] == "proposed"
    action_id = job["action"]["id"]

    # 102'yi cikar, 101'i onayla
    res = await client.post(
        f"/api/v1/assistant/actions/{action_id}/approve",
        json={"exclude_card_ids": [102]},
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["status"] == "executed"
    assert [m["card_id"] for m in data["result"]["moved"]] == [101]
    assert "Haftalık rapor" not in data["summary"]
    assert [w["path"] for w in inbox_api.writes] == ["/cards/101/move"]
    assert inbox_api.cards[102]["board_id"] == INBOX_ID


async def test_cannot_exclude_every_card(client):
    await client.post("/api/v1/assistant/inbox-triage")
    await asyncio.gather(*jobs_module._TASKS)
    job = (await client.get("/api/v1/assistant/inbox-triage")).json()["data"]
    res = await client.post(
        f"/api/v1/assistant/actions/{job['action']['id']}/approve",
        json={"exclude_card_ids": [101, 102]},
    )
    assert res.status_code == 422


async def test_approval_skips_card_user_already_moved(client, inbox_api):
    await client.post("/api/v1/assistant/inbox-triage")
    await asyncio.gather(*jobs_module._TASKS)
    job = (await client.get("/api/v1/assistant/inbox-triage")).json()["data"]
    inbox_api.cards[101]["board_id"] = GIZLI_ID  # kullanici arada elle tasidi
    res = await client.post(
        f"/api/v1/assistant/actions/{job['action']['id']}/approve", json={}
    )
    data = res.json()["data"]
    assert [m["card_id"] for m in data["result"]["moved"]] == [102]
    assert [m["card_id"] for m in data["result"]["skipped"]] == [101]
    assert inbox_api.cards[101]["board_id"] == GIZLI_ID


async def test_permission_listed_with_label(client):
    perms = (await client.get("/api/v1/assistant/permissions")).json()["data"]
    row = next(p for p in perms if p["action_type"] == "triage_inbox")
    assert row["mode"] == "ask" and "Gelen Kutusu" in row["label"]
