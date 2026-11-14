"""Faz 12b: gunu planlatinca HER madde (kartli/kartsiz/saatsiz) gun planina yazilir."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.tools.privacy import PrivacyFilter
from app.tools.schedule_day import build_timeline
from app.tools.task_api import TaskApiClient
from app.tools.write_tools import WriteTools

TZ = ZoneInfo("Europe/Istanbul")


def _tomorrow():
    return (datetime.now(TZ) + timedelta(days=1)).date()


def _writer(transport):
    return WriteTools(TaskApiClient("t", transport=transport), PrivacyFilter(), TZ)


# ---- build_timeline ----
def test_timeline_untimed_only():
    blocks = build_timeline([{"title": "Market"}, {"title": "Fatura"}])
    assert [b.title for b in blocks] == ["Market", "Fatura"]
    assert all(b.start is None and b.end is None for b in blocks)


def test_timeline_mixed_order():
    blocks = build_timeline(
        [
            {"title": "Market"},
            {"title": "Ders", "start": "10:00", "end": "12:00"},
            {"title": "Kitap"},
            {"title": "Koşu", "minutes": 45},
        ]
    )
    assert [b.title for b in blocks] == ["Market", "Ders", "Kitap", "Koşu"]
    assert blocks[0].start is None and blocks[2].start is None
    assert (blocks[1].start, blocks[1].end) == (600, 720)
    assert (blocks[3].start, blocks[3].end) == (720, 765)


def test_timeline_lead_in_skips_untimed():
    blocks = build_timeline(
        [
            {"title": "Yol", "minutes": 60},
            {"title": "Not"},
            {"title": "İş", "start": "09:00", "end": "17:00"},
        ]
    )
    assert (blocks[0].start, blocks[0].end) == (8 * 60, 9 * 60)
    assert blocks[1].start is None
    assert blocks[2].start == 9 * 60


def test_timeline_start_only_defaults_30():
    (blk,) = build_timeline([{"title": "Fatura", "start": "10:00"}])
    assert blk.defaulted is True
    assert blk.end - blk.start == 30


# ---- schedule_day ----
async def test_schedule_free_only_writes_plan(fake_api, task_api_transport):
    day = _tomorrow()
    writer = _writer(task_api_transport)
    prepared = await writer.prepare(
        "schedule_day",
        {
            "day": day.isoformat(),
            "blocks": [
                {"title": "Fatura öde", "start": "10:00", "minutes": 15, "card": False},
                {"title": "Annemi ara", "minutes": 20, "card": False},
            ],
        },
    )
    assert "gün planına 2 madde" in prepared.summary
    result = await writer.execute(prepared.action_type, prepared.args)
    paths = [(w["method"], w["path"]) for w in fake_api.writes]
    assert paths == [
        ("POST", "/events"),
        ("POST", "/events"),
        ("PUT", f"/day-plans/{day}"),
    ]
    a, b = (c["event_id"] for c in result["created"])
    assert a != b
    assert fake_api.writes[2]["body"]["items"] == [{"event_id": a}, {"event_id": b}]
    assert result["added_to_plan"] is True


async def test_schedule_untimed_free_no_event(fake_api, task_api_transport):
    day = _tomorrow()
    writer = _writer(task_api_transport)
    prepared = await writer.prepare(
        "schedule_day",
        {
            "day": day.isoformat(),
            "blocks": [
                {"title": "Market", "card": False},
                {"title": "Kuru temizleme", "card": False},
                {"title": "Kitap iade", "card": False},
            ],
        },
    )
    assert "saatsiz · Market (plan maddesi)" in prepared.summary
    await writer.execute(prepared.action_type, prepared.args)
    assert [(w["method"], w["path"]) for w in fake_api.writes] == [
        ("PUT", f"/day-plans/{day}")
    ]
    assert fake_api.writes[0]["body"]["items"] == [
        {"title": "Market"},
        {"title": "Kuru temizleme"},
        {"title": "Kitap iade"},
    ]


async def test_schedule_untimed_card(fake_api, task_api_transport):
    day = _tomorrow()
    writer = _writer(task_api_transport)
    prepared = await writer.prepare(
        "schedule_day",
        {
            "day": day.isoformat(),
            "blocks": [{"title": "Rapor hazırla", "board": "spor"}],
        },
    )
    await writer.execute(prepared.action_type, prepared.args)
    assert [(w["method"], w["path"]) for w in fake_api.writes] == [
        ("POST", "/cards"),
        ("PUT", f"/day-plans/{day}"),
    ]
    assert "estimated_minutes" not in fake_api.writes[0]["body"]
    assert fake_api.writes[1]["body"]["items"] == [{"card_id": 100}]


async def test_schedule_existing_card_and_plan(fake_api, task_api_transport):
    day = _tomorrow()
    fake_api.plans[day.isoformat()] = [{"card_id": 11}]
    writer = _writer(task_api_transport)
    prepared = await writer.prepare(
        "schedule_day",
        {
            "day": day.isoformat(),
            "blocks": [{"title": "Koşu", "start": "14:00", "minutes": 30}],
        },
    )
    assert prepared.args["blocks"][0]["card_id"] == 11
    result = await writer.execute(prepared.action_type, prepared.args)
    e = result["created"][0]["event_id"]
    body = fake_api.writes[-1]["body"]["items"]
    assert body == [{"id": 1, "card_id": 11}, {"event_id": e, "card_id": 11}]


async def test_schedule_conflict_ignores_untimed(fake_api):
    day = _tomorrow()
    items = [
        {
            "kind": "event",
            "title": "Toplantı",
            "start": f"{day.isoformat()}T09:00:00+03:00",
            "end": f"{day.isoformat()}T18:00:00+03:00",
            "all_day": False,
            "board_id": None,
            "card_id": None,
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/calendar"):
            return httpx.Response(200, json={"success": True, "data": {"items": items}})
        return fake_api(request)

    writer = _writer(httpx.MockTransport(handler))
    prepared = await writer.prepare(
        "schedule_day",
        {"day": day.isoformat(), "blocks": [{"title": "Market", "card": False}]},
    )
    assert prepared.action_type == "schedule_day"


async def test_schedule_reviewed_day_keeps_calendar(fake_api):
    day = _tomorrow()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT" and "/day-plans/" in request.url.path:
            return httpx.Response(
                409, json={"success": False, "error": {"message": "değerlendirildi"}}
            )
        return fake_api(request)

    writer = _writer(httpx.MockTransport(handler))
    prepared = await writer.prepare(
        "schedule_day",
        {
            "day": day.isoformat(),
            "blocks": [{"title": "Fatura", "start": "10:00", "minutes": 15, "card": False}],
        },
    )
    result = await writer.execute(prepared.action_type, prepared.args)
    assert result["added_to_plan"] is False
    assert len(result["created"]) == 1
    assert any(w["path"] == "/events" for w in fake_api.writes)


# ---- plan_day ----
async def test_plan_day_merge_carries_ids_and_dedupes_titles(
    fake_api, task_api_transport
):
    day = _tomorrow()
    fake_api.plans[day.isoformat()] = [{"title": "Annemi ara"}]
    writer = _writer(task_api_transport)
    prepared = await writer.prepare(
        "plan_day",
        {
            "date": day.isoformat(),
            "items": [{"title": "annemi ara"}, {"title": "Su iç"}, {"title": "su iç"}],
        },
    )
    await writer.execute(prepared.action_type, prepared.args)
    assert fake_api.writes[-1]["body"]["items"] == [
        {"id": 1, "title": "Annemi ara"},
        {"title": "Su iç"},
    ]


def _match(day, **kw):
    return {
        "spans": [[0, 5]],
        "phrase": "15'te",
        "due_date": f"{day.isoformat()}T15:00:00+03:00",
        "has_time": True,
        "estimated_minutes": None,
        "label": "x",
        "clean_title": "Annemi ara",
        "strong": True,
        **kw,
    }


async def test_plan_day_strong_time_applied(fake_api, task_api_transport):
    day = _tomorrow()
    fake_api.parse_result = _match(day)
    prepared = await _writer(task_api_transport).prepare(
        "plan_day",
        {"date": day.isoformat(), "items": [{"title": "Annemi ara 15'te"}]},
    )
    assert prepared.args["items"][0] == {
        "title": "Annemi ara",
        "planned_start": f"{day.isoformat()}T15:00:00+03:00",
    }
    assert "Annemi ara 15:00" in prepared.summary


async def test_plan_day_weak_or_other_day_ignored(fake_api, task_api_transport):
    day = _tomorrow()
    writer = _writer(task_api_transport)
    fake_api.parse_result = _match(day, strong=False)
    p = await writer.prepare(
        "plan_day", {"date": day.isoformat(), "items": [{"title": "Annemi ara 15'te"}]}
    )
    assert p.args["items"][0] == {"title": "Annemi ara 15'te"}

    fake_api.parse_result = _match(day + timedelta(days=1))
    p = await writer.prepare(
        "plan_day", {"date": day.isoformat(), "items": [{"title": "Annemi ara 15'te"}]}
    )
    assert p.args["items"][0] == {"title": "Annemi ara 15'te"}
