"""Birim testleri: stream ayristirma, gizlilik filtresi, arac seti, agent dongusu."""

import json
from zoneinfo import ZoneInfo

from app.agent.loop import run_agent
from app.api.chat import sanitize
from app.db.models import MessageEntity
from app.llm.openai_provider import _ThinkFilter, parse_arguments
from app.llm.types import Msg, ToolCall
from app.tools.read_tools import ToolBox
from app.tools.task_api import TaskApiClient
from tests.conftest import FakeProvider, call, text

TZ = ZoneInfo("Europe/Istanbul")


class TestStreamParsing:
    def test_think_blocks_removed_even_when_split(self):
        f = _ThinkFilter()
        parts = ["Mer", "haba <thi", "nk>gizli düşünce</th", "ink> dünya", "!"]
        out = "".join(f.feed(p) for p in parts) + f.flush()
        assert out == "Merhaba dünya!"

    def test_unclosed_think_is_dropped(self):
        f = _ThinkFilter()
        out = f.feed("Cevap <think>yarım kaldı") + f.flush()
        assert out == "Cevap "

    def test_parse_arguments(self):
        assert parse_arguments('{"a": 1}') == ({"a": 1}, True)
        assert parse_arguments("") == ({}, True)
        assert parse_arguments("{bozuk") == ({}, False)
        assert parse_arguments("[1,2]") == ({}, False)


class TestPrivacy:
    async def _box(self, transport, cloud: bool) -> ToolBox:
        api = TaskApiClient("t", transport=transport)
        return await ToolBox.create(api, cloud=cloud, tz=TZ)

    async def _run(self, box: ToolBox, name: str, **args):
        result, ok = await box.execute(ToolCall(id="x", name=name, arguments=args))
        return json.loads(result.removesuffix('… (kısaltıldı)"')), ok

    async def test_local_model_sees_everything(self, task_api_transport):
        box = await self._box(task_api_transport, cloud=False)
        boards, _ = await self._run(box, "list_boards")
        assert [b["name"] for b in boards] == ["Spor", "Date planları"]
        cal, _ = await self._run(
            box, "get_calendar", start_date="2026-11-09", end_date="2026-11-10"
        )
        assert len(cal) == 3

    async def test_cloud_model_never_sees_local_only_data(self, task_api_transport):
        box = await self._box(task_api_transport, cloud=True)
        dumped = []
        for name, args in [
            ("list_boards", {}),
            ("get_calendar", {"start_date": "2026-11-09", "end_date": "2026-11-10"}),
            ("search_cards", {"query": "a"}),
            ("get_stats_summary", {}),
            ("get_board", {"board_id": 2}),
            ("get_card", {"card_id": 21}),
        ]:
            result, _ = await box.execute(ToolCall(id="x", name=name, arguments=args))
            dumped.append(result)
        everything = "\n".join(dumped)
        for secret in ("Date planları", "Gizli date planı", "Gizli akşam yemeği"):
            assert secret not in everything, secret
        # Gizli board/kart istenirse aciklayici hata
        board, ok = await self._run(box, "get_board", board_id=2)
        assert ok is False and "gizli" in board["error"]
        # Normal veri hala gorunur
        assert "Koşu" in everything

    async def test_tool_errors_are_reported_not_raised(self, task_api_transport):
        box = await self._box(task_api_transport, cloud=False)
        for name, args in [
            ("bilinmeyen", {}),
            ("get_board", {}),  # eksik arguman
            ("get_calendar", {"start_date": "2026-11-10", "end_date": "2026-11-01"}),
        ]:
            result, ok = await box.execute(ToolCall(id="x", name=name, arguments=args))
            assert ok is False and "error" in json.loads(result)
        bad = ToolCall(
            id="x", name="list_boards", arguments={}, raw_arguments="{", valid=False
        )
        _, ok = await box.execute(bad)
        assert ok is False


class TestAgentLoop:
    async def test_tool_round_trip(self, task_api_transport):
        box = await ToolBox.create(
            TaskApiClient("t", transport=task_api_transport), cloud=False, tz=TZ
        )
        provider = FakeProvider(
            [
                [text("Bakıyorum. "), call("list_boards")],
                [text("İki board'un var: Spor ve Date planları.")],
            ]
        )
        msgs = [Msg("system", "s"), Msg("user", "Board'larım neler?")]
        events = [e async for e in run_agent(provider, msgs, box)]
        kinds = [e.type for e in events]
        assert kinds.count("tool_start") == 1 and kinds.count("tool_end") == 1
        # 2. turda model arac sonucunu gordu
        second = provider.received[1]
        assert second[-1].role == "tool" and "Spor" in second[-1].content
        assert msgs[-1].content == "İki board'un var: Spor ve Date planları."

    async def test_round_limit_forces_answer(self, task_api_transport):
        box = await ToolBox.create(
            TaskApiClient("t", transport=task_api_transport), cloud=False, tz=TZ
        )
        provider = FakeProvider([[call("list_boards")]] * 3 + [[text("Özet.")]])
        msgs = [Msg("system", "s"), Msg("user", "?")]
        events = [e async for e in run_agent(provider, msgs, box, max_rounds=3)]
        assert sum(e.type == "tool_start" for e in events) == 3
        # Son turda arac verilmedi ve cevap istendi
        assert provider.tools_seen[-1] is None
        assert msgs[-1].content == "Özet."


class TestHistorySanitize:
    def test_drops_unanswered_tool_calls(self):
        def m(role, **kw):
            return MessageEntity(role=role, **kw)

        rows = [
            m("user", content="a"),
            m("assistant", content="", tool_calls=[{"id": "1", "name": "x"}]),
            m("tool", tool_call_id="1", content="{}"),
            m(
                "assistant", content="", tool_calls=[{"id": "2", "name": "x"}]
            ),  # cevapsiz
            m("tool", tool_call_id="9", content="{}"),  # cagrisiz
            m("assistant", content="son"),
        ]
        kept = sanitize(rows)
        assert [(r.role, r.tool_call_id) for r in kept] == [
            ("user", None),
            ("assistant", None),
            ("tool", "1"),
            ("assistant", None),
        ]
