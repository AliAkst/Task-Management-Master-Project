"""Faz 10c: create_card baslikta zaman ifadesini task-api parse-title ile ayiklar,
saatli due_date (create_card / update_card)."""

from zoneinfo import ZoneInfo

import pytest

from app.tools.privacy import PrivacyFilter
from app.tools.task_api import TaskApiClient
from app.tools.write_tools import WRITE_SPECS, WriteTools, _due_iso
from tests.conftest import CARDS, _card

TZ = ZoneInfo("Europe/Istanbul")

MATCH_15 = {
    "spans": [[11, 22]],
    "phrase": "yarın 15'te",
    "due_date": "2026-11-13T15:00:00+03:00",
    "has_time": True,
    "estimated_minutes": None,
    "label": "📅 Cum 13 Kas 15:00",
    "clean_title": "Diş hekimi",
}
TITLE = "Diş hekimi yarın 15'te"


def writer(transport):
    api = TaskApiClient("t", transport=transport)
    return WriteTools(api, PrivacyFilter(active=False, hidden_boards=set(), hidden_cards=set()), TZ)


async def prep(transport, **args):
    args.setdefault("board_id", 1)
    return await writer(transport).prepare("create_card", args)


async def test_title_phrase_extracted(task_api_transport, fake_api):
    fake_api.parse_result = MATCH_15
    p = await prep(task_api_transport, title=TITLE)
    assert p.args["title"] == "Diş hekimi"
    assert p.args["due_date"] == "2026-11-13T15:00:00+03:00"
    assert "(başlıktan)" in p.summary and "15:00" in p.summary
    assert fake_api.parse_calls[0]["actor"] is None
    assert fake_api.writes == []


async def test_model_same_day_date_only_uses_title_time(task_api_transport, fake_api):
    fake_api.parse_result = MATCH_15
    p = await prep(task_api_transport, title=TITLE, due_date="2026-11-13")
    assert p.args["title"] == "Diş hekimi"
    assert p.args["due_date"] == "2026-11-13T15:00:00+03:00"


async def test_model_timed_due_wins(task_api_transport, fake_api):
    fake_api.parse_result = MATCH_15
    p = await prep(task_api_transport, title=TITLE, due_date="2026-11-13T09:00")
    assert p.args["title"] == "Diş hekimi"
    assert p.args["due_date"] == "2026-11-13T09:00:00+03:00"
    assert "(başlıktan)" not in p.summary


async def test_model_different_day_wins_title_kept(task_api_transport, fake_api):
    fake_api.parse_result = {**MATCH_15, "estimated_minutes": 45}
    p = await prep(task_api_transport, title=TITLE, due_date="2026-11-20")
    assert p.args["title"] == TITLE
    assert p.args["due_date"] == "2026-11-20T23:59:00+03:00"
    assert "estimated_minutes" not in p.args


async def test_duration_only(task_api_transport, fake_api):
    fake_api.parse_result = {
        **MATCH_15,
        "due_date": None,
        "has_time": False,
        "estimated_minutes": 120,
        "clean_title": "Rapor",
    }
    p = await prep(task_api_transport, title="Rapor 2 saat")
    assert p.args["title"] == "Rapor"
    assert p.args["estimated_minutes"] == 120
    assert "due_date" not in p.args
    assert "⏱ 120 dk (başlıktan)" in p.summary
    p = await prep(task_api_transport, title="Rapor 2 saat", estimated_minutes=30)
    assert p.args["estimated_minutes"] == 30 and p.args["title"] == "Rapor"


async def test_no_match_unchanged(task_api_transport, fake_api):
    fake_api.parse_result = None
    p = await prep(task_api_transport, title="Diş hekimi", due_date="2026-11-13")
    assert p.args["title"] == "Diş hekimi"
    assert p.args["due_date"] == "2026-11-13T23:59:00+03:00"


async def test_parse_error_still_creates(task_api_transport, fake_api):
    fake_api.parse_status = 404
    p = await prep(task_api_transport, title=TITLE)
    assert p.args["title"] == TITLE and "due_date" not in p.args


async def test_duplicate_guard_uses_clean_title(task_api_transport, fake_api, monkeypatch):
    monkeypatch.setitem(CARDS, 31, _card(31, "Diş hekimi", 1))
    fake_api.parse_result = MATCH_15
    with pytest.raises(ValueError, match="zaten var"):
        await prep(task_api_transport, title=TITLE)
    p = await prep(task_api_transport, title=TITLE, force_new=True)
    assert p.action_type == "create_card"


def test_due_iso_variants():
    assert _due_iso("2026-11-13", TZ) == "2026-11-13T23:59:00+03:00"
    assert _due_iso("2026-11-13T15:00", TZ) == "2026-11-13T15:00:00+03:00"
    assert _due_iso("2026-11-13T15:00:00+00:00", TZ) == "2026-11-13T15:00:00+00:00"
    with pytest.raises(ValueError, match="YYYY-MM-DDTHH:MM"):
        _due_iso("13 Kasım", TZ)


async def test_update_card_timed_due(task_api_transport):
    p = await writer(task_api_transport).prepare(
        "update_card", {"card": "11", "due_date": "2026-11-13T15:00"}
    )
    assert p.args["patch"]["due_date"] == "2026-11-13T15:00:00+03:00"
    assert "15:00" in p.summary


def test_specs_due_descriptions():
    specs = {s.name: s for s in WRITE_SPECS}
    for n in ("create_card", "update_card"):
        d = specs[n].parameters["properties"]["due_date"]["description"]
        assert "YYYY-MM-DDTHH:MM" in d
    assert specs["plan_day"].parameters["properties"]["date"]["description"] == "YYYY-MM-DD"


async def test_execute_posts_clean_title(task_api_transport, fake_api):
    fake_api.parse_result = MATCH_15
    w = writer(task_api_transport)
    p = await w.prepare("create_card", {"board_id": 1, "title": TITLE})
    await w.execute(p.action_type, p.args)
    posts = [x for x in fake_api.writes if x["path"] == "/cards"]
    assert len(posts) == 1
    assert not [x for x in fake_api.writes if "parse-title" in x["path"]]
    assert posts[0]["body"]["title"] == "Diş hekimi"
    assert posts[0]["body"]["due_date"] == "2026-11-13T15:00:00+03:00"
