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
                "lists": [
                    {"id": bid * 10, "name": "Yapılacak", "is_done_list": False},
                    {"id": bid * 10 + 1, "name": "Tamamlandı", "is_done_list": True},
                ],
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


class FakeTaskApi:
    """Okumalar fake_task_api'den; yazmalari kaydeder (X-Actor dahil), gun planini tutar."""

    def __init__(self) -> None:
        self.writes: list[dict[str, Any]] = []
        self.plans: dict[str, list[dict[str, Any]]] = {}
        self.goals: dict[int, dict[str, Any]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        method = request.method

        def ok(data: Any) -> httpx.Response:
            return httpx.Response(200, json={"success": True, "data": data})

        if method == "GET" and path.startswith("/day-plans/"):
            day = path.split("/")[2]
            items = self.plans.get(day, [])
            return ok(
                {
                    "date": day,
                    "exists": bool(items),
                    "status": "planned" if items else None,
                    "items": [
                        {
                            **i,
                            "id": n,
                            "title": i.get("title") or f"kart {i.get('card_id')}",
                            "was_planned": True,
                            "event_id": i.get("event_id"),
                            "board_id": None,
                            "tracked_sec": 0,
                            "tracked_today_sec": 0,
                            "outcome": None,
                            "reason": None,
                            "planned_minutes": i.get("planned_minutes"),
                        }
                        for n, i in enumerate(items, 1)
                    ],
                    "tracked_today_sec": 0,
                }
            )
        if method == "GET" and path == "/goals":
            goals = list(self.goals.values())
            status = request.url.params.get("status")
            return ok([g for g in goals if not status or g["status"] == status])
        if method == "GET":
            return fake_task_api(request)

        body = json.loads(request.content or b"null")
        self.writes.append(
            {
                "method": method,
                "path": path,
                "body": body,
                "actor": request.headers.get("X-Actor"),
            }
        )
        if method == "POST" and path == "/goals":
            gid = len(self.goals) + 1
            self.goals[gid] = {"id": gid, "status": "active", "board_id": None, **body}
            return ok(self.goals[gid])
        if method == "PATCH" and path.startswith("/goals/"):
            g = self.goals[int(path.split("/")[2])]
            g.update(body)
            return ok(g)
        if method == "POST" and path == "/cards":
            return ok({"id": 100, "title": body["title"]})
        if method == "POST" and path == "/events":
            return ok(
                {"id": 7, "title": body.get("title", "x"), "start_at": body["start_at"]}
            )
        if method == "POST" and path.endswith("/split"):
            return ok(
                {
                    "subtasks": [
                        {"id": 200 + i, "title": f"Parça {i}"}
                        for i in range(body.get("parts", 2))
                    ]
                }
            )
        if method == "POST" and path.endswith("/notes"):
            return ok({"id": 5})
        if method == "PUT" and path.startswith("/day-plans/"):
            self.plans[path.split("/")[2]] = body["items"]
            return ok({"date": path.split("/")[2], "items": body["items"]})
        if method == "POST" and path.endswith("/dependencies"):
            if body["depends_on_id"] == 11 and path.startswith("/cards/11/"):
                return httpx.Response(
                    409, json={"success": False, "error": {"message": "döngü"}}
                )
            return ok(CARDS[11])
        return ok(CARDS.get(11))


@pytest.fixture
def fake_api() -> FakeTaskApi:
    return FakeTaskApi()


@pytest.fixture
def task_api_transport(fake_api) -> httpx.MockTransport:
    return httpx.MockTransport(fake_api)


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


@pytest.fixture(autouse=True)
def _no_memory_extraction(monkeypatch):
    """Varsayilan: hafiza cikarimi kapali (FakeProvider senaryolarini tuketmesin)."""
    from app.config import settings

    monkeypatch.setattr(settings, "memory_extraction", False)


@pytest.fixture(autouse=True)
def test_secret_key(monkeypatch):
    """Testler gercek .secret_key dosyasina dokunmasin: gecici ana anahtar."""
    from cryptography.fernet import Fernet

    import app.security as security
    from app.config import settings

    monkeypatch.setattr(settings, "secret_key", Fernet.generate_key().decode())
    security._fernet.cache_clear()
    yield
    security._fernet.cache_clear()
