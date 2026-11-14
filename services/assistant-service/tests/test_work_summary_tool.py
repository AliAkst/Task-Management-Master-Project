"""Faz 13h1: get_work_summary okuma aracı (metin aynen; bulutta gizli board'lar dışarıda)."""

import json
from zoneinfo import ZoneInfo

import httpx

from app.llm.types import ToolCall
from app.tools.read_tools import ToolBox
from app.tools.task_api import TaskApiClient

TZ = ZoneInfo("Europe/Istanbul")
TEXT = "**İş özeti — 14 Kasım 2026, Cumartesi**\n\n**Tamamlananlar**\n- Koşu (1 sa 30 dk)"


def _transport(seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        seen.append(request)
        if path == "/reports/work-summary":
            return httpx.Response(
                200, json={"success": True, "data": {"text": TEXT, "sections": {}}}
            )
        if path == "/boards":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": [
                        {"id": 1, "name": "A", "privacy": "cloud_allowed"},
                        {"id": 2, "name": "Gizli", "privacy": "local_only"},
                        {"id": 3, "name": "B", "privacy": "cloud_allowed"},
                    ],
                },
            )
        if path.startswith("/boards/"):
            return httpx.Response(
                200, json={"success": True, "data": {"board": {}, "cards": []}}
            )
        return httpx.Response(404, json={"success": False})

    return httpx.MockTransport(handler)


async def _run(cloud: bool, args: dict):
    seen: list[httpx.Request] = []
    box = await ToolBox.create(
        TaskApiClient("t", transport=_transport(seen)), cloud=cloud, tz=TZ
    )
    out = await box.execute(ToolCall(id="x", name="get_work_summary", arguments=args))
    report = [r for r in seen if r.url.path.endswith("/reports/work-summary")]
    return out, report


async def test_local_returns_text_verbatim_for_all_boards():
    out, report = await _run(False, {"date": "2026-11-14"})
    assert out.ok
    assert json.loads(out.text)["text"] == TEXT
    assert report[0].url.params["date"] == "2026-11-14"
    assert "board_ids" not in report[0].url.params


async def test_cloud_excludes_hidden_boards_and_defaults_to_today():
    out, report = await _run(True, {})
    assert out.ok and json.loads(out.text)["text"] == TEXT
    assert report[0].url.params["board_ids"] == "1,3"  # gizli board 2 yok
    assert len(report[0].url.params["date"]) == 10


def test_spec_tells_model_to_show_text_verbatim():
    spec = next(s for s in ToolBox.read_specs() if s.name == "get_work_summary")
    assert "aynen" in spec.description
