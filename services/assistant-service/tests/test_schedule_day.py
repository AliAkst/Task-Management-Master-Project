"""Gunu saat saat planlama araci: gun/saat hesabi kodda, tek onayla kart + takvim."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.tools.privacy import PrivacyFilter
from app.tools.schedule_day import build_timeline, find_board, parse_clock, resolve_day
from app.tools.task_api import TaskApiClient
from app.tools.write_tools import WriteTools

TZ = ZoneInfo("Europe/Istanbul")
SUNDAY = date(2026, 11, 8)


def test_resolve_day():
    assert resolve_day("salı", SUNDAY) == date(2026, 11, 10)
    assert resolve_day("Salı günü", SUNDAY) == date(2026, 11, 10)
    assert resolve_day("pazar", SUNDAY) == SUNDAY  # bugunse bugun
    assert resolve_day("yarın", SUNDAY) == date(2026, 11, 9)
    assert resolve_day("2026-11-12", SUNDAY) == date(2026, 11, 12)
    assert resolve_day("cumartesi", SUNDAY) == date(2026, 11, 14)
    with pytest.raises(ValueError):
        resolve_day("bir ara", SUNDAY)
    with pytest.raises(ValueError):
        resolve_day("pazartesiyi", SUNDAY)  # kelime devam ediyor -> belirsiz


def test_parse_clock():
    assert parse_clock("07:30", "x") == 450
    assert parse_clock("7.05", "x") == 425
    assert parse_clock("19", "x") == 1140
    for bad in ("25:00", "7:60", "yedi"):
        with pytest.raises(ValueError):
            parse_clock(bad, "x")


def test_timeline_from_user_story():
    """Kullanicinin gercek istegi: yol 2 sa, is 9-18, kuyumcu, donus 2,5 sa..."""
    blocks = build_timeline(
        [
            {"title": "Ofise yol", "start": "07:00", "minutes": 120, "card": False},
            {"title": "İş", "start": "09:00", "end": "18:00", "card": False},
            {"title": "Kuyumcu", "minutes": 30},
            {"title": "Eve dönüş", "minutes": 150, "card": False},
            {"title": "Yemek + spor + duş", "minutes": 120, "board": "Spor"},
            {"title": "Oyun", "minutes": 60},
            {"title": "Oda topla", "minutes": 30},
        ]
    )
    times = [
        (b.title, b.start // 60, b.start % 60, b.end // 60, b.end % 60) for b in blocks
    ]
    assert times == [
        ("Ofise yol", 7, 0, 9, 0),
        ("İş", 9, 0, 18, 0),
        ("Kuyumcu", 18, 0, 18, 30),
        ("Eve dönüş", 18, 30, 21, 0),
        ("Yemek + spor + duş", 21, 0, 23, 0),
        ("Oyun", 23, 0, 24, 0),
        ("Oda topla", 24, 0, 24, 30),  # gece yarisini gecer: ertesi gun 00:30
    ]
    assert [b.card for b in blocks] == [False, False, True, False, True, True, True]


def test_timeline_errors_are_actionable():
    with pytest.raises(ValueError, match="başlangıç saati"):
        build_timeline([{"title": "A", "minutes": 10}])
    with pytest.raises(ValueError, match="önceki blok 'A' 10:00"):
        build_timeline(
            [
                {"title": "A", "start": "08:00", "end": "10:00"},
                {"title": "B", "start": "09:30", "minutes": 30},
            ]
        )
    with pytest.raises(ValueError, match="süre"):
        build_timeline([{"title": "A", "start": "08:00"}])
    # gece yarisindan sonra acik saat: ertesi gun
    late = build_timeline(
        [
            {"title": "Film", "start": "22:00", "minutes": 120},
            {"title": "Uyku", "start": "00:30", "minutes": 30},
        ]
    )
    assert late[1].start == 24 * 60 + 30


def test_find_board():
    boards = [{"id": 1, "name": "Spor"}, {"id": 2, "name": "Date planları"}]
    assert find_board(boards, "spor")["id"] == 1
    assert find_board(boards, "Date")["id"] == 2
    assert find_board(boards, 2)["id"] == 2
    assert find_board(boards, "iş") is None


async def test_prepare_and_execute(fake_api, task_api_transport):
    writer = WriteTools(
        TaskApiClient("t", transport=task_api_transport), PrivacyFilter(), TZ
    )
    tomorrow = (datetime.now(TZ) + timedelta(days=1)).date()
    prepared = await writer.prepare(
        "schedule_day",
        {
            "day": tomorrow.isoformat(),
            "blocks": [
                {"title": "Ofise yol", "start": "07:00", "minutes": 120, "card": False},
                {"title": "Koşu", "minutes": 45, "board": "spor"},
            ],
        },
    )
    assert prepared.action_type == "schedule_day"
    assert "07:00–09:00 Ofise yol (etkinlik)" in prepared.summary
    assert "09:00–09:45 Koşu (kart, Spor)" in prepared.summary
    run, card = prepared.args["blocks"]
    assert card["list_id"] == 10 and card["minutes"] == 45 and run["card"] is False
    assert fake_api.writes == []  # hazirlik yazmaz

    result = await writer.execute(prepared.action_type, prepared.args)
    paths = [(w["method"], w["path"]) for w in fake_api.writes]
    assert paths == [
        ("POST", "/events"),
        ("POST", "/cards"),
        ("POST", "/events"),
        ("PUT", f"/day-plans/{tomorrow}"),
    ]
    assert fake_api.writes[1]["body"]["estimated_minutes"] == 45
    assert fake_api.writes[2]["body"]["card_id"] == 100  # kartin zaman blogu
    assert all(w["actor"] == "ai" for w in fake_api.writes)
    assert result["added_to_plan"] is True and len(result["created"]) == 2


async def test_cloud_cannot_schedule_into_private_board(task_api_transport):
    privacy = PrivacyFilter(active=True, hidden_boards={2})
    writer = WriteTools(TaskApiClient("t", transport=task_api_transport), privacy, TZ)
    with pytest.raises(ValueError, match="bulunamadı"):
        await writer.prepare(
            "schedule_day",
            {
                "day": "yarın",
                "blocks": [
                    {
                        "title": "X",
                        "start": "10:00",
                        "minutes": 30,
                        "board": "Date planları",
                    }
                ],
            },
        )
