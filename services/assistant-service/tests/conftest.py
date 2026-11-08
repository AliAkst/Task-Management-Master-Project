"""
Test altyapisi: gercek model ve task-api olmadan.
- FakeProvider: yazilmis cevap/arac cagrisi uretir, aldigi mesajlari kaydeder
- fake task-api: httpx.MockTransport; 1 normal + 1 'local_only' board
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.llm.types import ChatChunk, ModelInfo, Msg, ToolCall, ToolSpec, Usage

SPOR = {"id": 1, "name": "Spor", "privacy": "cloud_allowed"}
DATE = {"id": 2, "name": "Date planları", "privacy": "local_only"}


def _board(b: dict) -> dict:
    return {
        **b,
        "scope_description": f"{b['name']} işleri",
        "open_card_count": 1,
        "weekly_time_budget_min": None,
        "color": "#000000",
    }


def _card(id_: int, title: str, board_id: int) -> dict:
    return {
        "id": id_,
        "title": title,
        "status": "pending",
        "board_id": board_id,
        "list_id": board_id * 10,
        "priority": "medium",
        "due_date": None,
        "estimated_minutes": 30,
        "tracked_seconds": 0,
        "subtask_tracked_seconds": 0,
        "blocked": False,
        "parent_id": None,
        "subtask_total": 0,
        "subtask_done": 0,
        "checklist_total": 0,
        "checklist_done": 0,
    }


CARDS = {11: _card(11, "Koşu", 1), 21: _card(21, "Gizli date planı", 2)}


def fake_task_api(request: httpx.Request) -> httpx.Response:
    path = request.url.path.removeprefix("/api/v1")

    def ok(data: Any) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "data": data})

    if path == "/auth/me":
        return ok({"id": 7, "email": "a@example.com", "full_name": "Ali"})
    if path == "/settings/":
        return ok({"timezone": "Europe/Istanbul"})
    if path == "/boards":
        return ok([_board(SPOR), _board(DATE)])
    if path.startswith("/boards/"):
        bid = int(path.split("/")[2])
        b = SPOR if bid == 1 else DATE
        return ok(
            {
                "board": _board(b),
                "lists": [{"id": bid * 10, "name": "Yapılacak"}],
                "cards": [c for c in CARDS.values() if c["board_id"] == bid],
                "labels": [],
            }
        )
    if path.startswith("/cards/") and path.endswith("/events"):
        return ok([])
    if path.startswith("/cards/"):
        c = CARDS[int(path.split("/")[2])]
        return ok(
            {
                **c,
                "description": "x",
                "checklist": [],
                "notes": [],
                "subtasks": [],
                "depends_on": [],
            }
        )
    if path == "/calendar":
        return ok(
            {
                "items": [
                    {
                        "kind": "event",
                        "title": "Koşu bloğu",
                        "start": "s",
                        "end": "e",
                        "all_day": False,
                        "board_id": 1,
                        "card_id": 11,
                        "card_status": "pending",
                    },
                    {
                        "kind": "event",
                        "title": "Gizli akşam yemeği",
                        "start": "s",
                        "end": "e",
                        "all_day": False,
                        "board_id": 2,
                        "card_id": None,
                        "card_status": None,
                    },
                    {
                        "kind": "deadline",
                        "title": "Gizli date planı",
                        "start": "s",
                        "end": None,
                        "all_day": True,
                        "board_id": None,
                        "card_id": 21,
                        "card_status": "pending",
                    },
                ]
            }
        )
    if path == "/sessions/active":
        return ok({"session": None})
    if path.startswith("/day-plans/"):
        return ok(
            {
                "date": path.split("/")[2],
                "exists": False,
                "items": [],
                "tracked_today_sec": 0,
            }
        )
    if path == "/analytics/summary":
        return ok(
            {
                "totals": {"tracked_min": 90},
                "boards": [
                    {
                        "board_id": 1,
                        "name": "Spor",
                        "tracked_min": 60,
                        "completed_cards": 1,
                        "budget_min": None,
                    },
                    {
                        "board_id": 2,
                        "name": "Date planları",
                        "tracked_min": 30,
                        "completed_cards": 0,
                        "budget_min": None,
                    },
                ],
                "estimate_accuracy": {
                    "mean_ratio": 1.2,
                    "median_ratio": 1.2,
                    "sample_size": 2,
                    "biggest_overruns": [
                        {"card_id": 11, "title": "Koşu", "ratio": 1.5},
                        {"card_id": 21, "title": "Gizli date planı", "ratio": 2.0},
                    ],
                },
                "productive_hours": [0] * 24,
                "weekdays": [0] * 7,
                "most_postponed": [
                    {"card_id": 21, "title": "Gizli date planı", "count": 2}
                ],
                "days": [],
            }
        )
    return httpx.Response(404, json={"success": False, "error": {"message": "yok"}})


@pytest.fixture
def task_api_transport() -> httpx.MockTransport:
    return httpx.MockTransport(fake_task_api)


class FakeProvider:
    """Her stream() cagrisinda siradaki senaryoyu oynatir; aldigi mesajlari saklar."""

    def __init__(self, script: list[list[ChatChunk]], *, is_local: bool = True):
        self.info = ModelInfo(
            id="fake:local" if is_local else "fake:cloud",
            provider="ollama" if is_local else "openai",
            model="fake",
            label="Fake",
            is_local=is_local,
        )
        self.script = list(script)
        self.received: list[list[Msg]] = []
        self.tools_seen: list[list[ToolSpec] | None] = []

    async def stream(self, messages, tools=None, **_) -> AsyncIterator[ChatChunk]:
        self.received.append(list(messages))
        self.tools_seen.append(tools)
        chunks = self.script.pop(0) if self.script else [text("(bitti)")]
        for c in chunks:
            yield c
        yield ChatChunk(type="usage", usage=Usage(10, 5))

    def all_text_sent(self) -> str:
        return json.dumps(
            [[(m.role, m.content) for m in msgs] for msgs in self.received],
            ensure_ascii=False,
        )


def text(t: str) -> ChatChunk:
    return ChatChunk(type="text", text=t)


def call(name: str, **args) -> ChatChunk:
    return ChatChunk(
        type="tool_call", tool_call=ToolCall(id=f"c_{name}", name=name, arguments=args)
    )


@pytest.fixture
async def db_session_maker(tmp_path):
    from app.db.models import Base

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()
