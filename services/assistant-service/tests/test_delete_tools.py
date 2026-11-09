"""Kart silme ve plan iptali: neyin silinecegini kod bulur, her zaman onay ister."""

from zoneinfo import ZoneInfo

import pytest

from app.agent.actions import ActionGate
from app.llm.types import ToolCall
from app.tools.privacy import PrivacyFilter
from app.tools.task_api import TaskApiClient
from app.tools.write_tools import WriteTools

TZ = ZoneInfo("Europe/Istanbul")


@pytest.fixture
def writer(task_api_transport):
    return WriteTools(
        TaskApiClient("t", transport=task_api_transport), PrivacyFilter(), TZ
    )


async def test_delete_by_title_board_and_all(writer):
    p = await writer.prepare("delete_cards", {"titles": ["koşu"]})
    assert p.args == {"card_ids": [11]} and "Koşu (Spor)" in p.summary
    p = await writer.prepare("delete_cards", {"board": "date"})
    assert p.args == {"card_ids": [21]}
    p = await writer.prepare("delete_cards", {"all": True})
    assert p.args == {"card_ids": [11, 21]} and "2 kart" in p.summary
    with pytest.raises(ValueError, match="Neyi sileceğimi"):
        await writer.prepare("delete_cards", {})
    with pytest.raises(ValueError, match="bulunamadı"):
        await writer.prepare("delete_cards", {"titles": ["yok böyle kart"]})


async def test_cloud_cannot_delete_private_cards(task_api_transport):
    privacy = PrivacyFilter(active=True, hidden_boards={2}, hidden_cards={21})
    w = WriteTools(TaskApiClient("t", transport=task_api_transport), privacy, TZ)
    p = await w.prepare("delete_cards", {"all": True})
    assert p.args == {"card_ids": [11]}


async def test_execute_deletes_as_ai(writer, fake_api):
    p = await writer.prepare("delete_cards", {"titles": ["koşu"]})
    result = await writer.execute(p.action_type, p.args)
    assert result["deleted_cards"] == [11]
    assert fake_api.writes == [
        {"method": "DELETE", "path": "/cards/11", "body": None, "actor": "ai"}
    ]


async def test_delete_always_asks_even_in_auto_mode(writer, fake_api, db_session_maker):
    gate = ActionGate(
        db_session_maker,
        writer,
        user_id=7,
        conversation_id=None,
        model_id="x",
        modes={"delete_cards": "auto"},
    )
    p = await writer.prepare("delete_cards", {"all": True})
    result = await gate.handle(ToolCall("c1", "delete_cards", {"all": True}), p)
    assert result.action["status"] == "proposed"
    assert fake_api.writes == []  # onaysiz hicbir sey silinmedi


async def test_cancel_day_clears_plan_and_events(writer, fake_api):
    fake_api.plans["2026-12-01"] = [{"card_id": 11}]
    p = await writer.prepare("cancel_day", {"day": "2026-12-01", "delete_cards": True})
    assert p.args["card_ids"] == [11]
    result = await writer.execute(p.action_type, p.args)
    assert fake_api.plans["2026-12-01"] == []
    assert result["deleted_cards"] == [11]
