"""Faz 13d — tek soru akışı, metinden gün ipucu, şablon/yerleşim yürütmesi, gün dönümü."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.api.chat as chat_module
from app.api.deps import current_user
from app.db.models import AiActionEntity
from app.main import app
from app.tools.privacy import PrivacyFilter
from app.tools.schedule_day import resolve_day_ex
from app.tools.task_api import TaskApiClient
from app.tools.write_tools import WriteTools
from tests.conftest import FakeProvider, call, text
from tests.test_chat_api import USER, parse_sse

API = "/api/v1/assistant"
TZ = ZoneInfo("Europe/Istanbul")
ROLLOVER = time(4, 0)

HOME_TEMPLATE = {
    "id": 1,
    "name": "Ev günü",
    "weekdays": [],
    "blocks": [
        {"title": "Mesai", "start": "09:00", "end": "12:00", "kind": "mesai"},
        {"title": "Öğle arası", "start": "12:00", "end": "13:00", "kind": "yemek"},
        {"title": "Mesai", "start": "13:00", "end": "18:00", "kind": "mesai"},
    ],
    "day_start": "08:00:00",
    "day_end": "23:00:00",
    "buffer_min": 0,
}


def tomorrow() -> date:
    now = datetime.now(TZ)
    return resolve_day_ex("yarın", now.date(), now_local=now, rollover=ROLLOVER)[0]


@pytest.fixture
async def client(monkeypatch, db_session_maker, task_api_transport):
    providers: dict[str, FakeProvider] = {}

    async def no_models():
        return []

    monkeypatch.setattr(chat_module, "list_local_models", no_models)
    monkeypatch.setattr(
        chat_module, "build_provider", lambda mid, cloud=None, **_: providers[mid]
    )
    monkeypatch.setattr(chat_module, "session_maker", db_session_maker)
    monkeypatch.setattr(
        chat_module,
        "TaskApiClient",
        lambda token: TaskApiClient(token, transport=task_api_transport),
    )

    async def fake_session():
        async with db_session_maker() as s:
            yield s

    app.dependency_overrides[current_user] = lambda: USER
    app.dependency_overrides[chat_module.get_session] = fake_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.providers = providers  # type: ignore[attr-defined]
        c.db = db_session_maker  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


async def say(client, message, conversation_id=None):
    body = {"message": message, "model_id": "fake:local"}
    if conversation_id:
        body["conversation_id"] = conversation_id
    res = await client.post(f"{API}/chat", json=body)
    events = parse_sse(res.text)
    conv = next(d["conversation_id"] for e, d in events if e == "start")
    return events, conv


def tokens(events) -> str:
    return "\n".join(d["text"] for e, d in events if e == "token")


async def actions(client):
    async with client.db() as s:
        return list(await s.scalars(select(AiActionEntity).order_by(AiActionEntity.id)))


def meeting(day: date, start="10:00", end="11:00"):
    return {
        "kind": "event",
        "title": "Toplantı",
        "start": f"{day.isoformat()}T{start}:00+03:00",
        "end": f"{day.isoformat()}T{end}:00+03:00",
        "all_day": False,
        "board_id": None,
        "card_id": None,
    }


def conflict_call(day="yarın"):
    return call(
        "schedule_day",
        day=day,
        items=[{"title": "İş", "start": "10:30", "minutes": 60, "card": False}],
    )


# ---------------------------------------------------------------- soru -> cevap
async def test_conflict_becomes_numbered_question_not_error(client, fake_api):
    fake_api.calendar_items = [meeting(tomorrow())]
    provider = FakeProvider([[conflict_call()]])
    client.providers["fake:local"] = provider
    events, conv = await say(client, "Yarın günümü planla")
    reply = tokens(events)
    assert "«İş» 10:30–11:30, takvimdeki «Toplantı» 10:00–11:00 ile çakışıyor." in reply
    assert "1) «İş» → 11:00 sonrasına" in reply
    assert 'Numarayla cevap ver (ör. 1) ya da "vazgeç" yaz.' in reply
    assert not [d for e, d in events if e == "action"]
    assert fake_api.writes == []
    (row,) = await actions(client)
    assert row.status == "question" and row.action_type == "schedule_day"
    assert row.args["kind"] == "place" and len(row.args["options"]) == 3
    assert row.args["day_raw"] == "yarın" and row.args["chain"] == 0
    assert row.args["user_text"] == "Yarın günümü planla"
    # soru satırı sohbette işlem kartı olarak görünmez
    res = await client.get(f"{API}/conversations/{conv}/messages")
    assert all(not m["actions"] for m in res.json()["data"])


async def test_numeric_answer_applies_option_without_calling_the_model(client, fake_api):
    fake_api.calendar_items = [meeting(tomorrow())]
    provider = FakeProvider([[conflict_call()]])
    client.providers["fake:local"] = provider
    _, conv = await say(client, "Yarın günümü planla")
    events, _ = await say(client, "2", conv)  # «İş» → ilk boş saate
    assert len(provider.received) == 1  # model ikinci kez çağrılmadı
    (card,) = [d for e, d in events if e == "action"]
    assert card["action_type"] == "schedule_day" and card["status"] == "proposed"
    assert "08:00–09:00 İş (etkinlik)" in card["summary"]
    rows = await actions(client)
    assert [r.status for r in rows] == ["answered", "proposed"]
    proposed = rows[1]
    now = datetime.now(TZ)
    _, rolled = resolve_day_ex("yarın", now.date(), now_local=now, rollover=ROLLOVER)
    assert proposed.args["day_raw"] == "yarın" and proposed.args["day_rolled"] is rolled
    assert proposed.args["date"] == tomorrow().isoformat()


async def test_cancel_expires_question(client, fake_api):
    fake_api.calendar_items = [meeting(tomorrow())]
    provider = FakeProvider([[conflict_call()]])
    client.providers["fake:local"] = provider
    _, conv = await say(client, "Yarın günümü planla")
    events, _ = await say(client, "vazgeç", conv)
    assert tokens(events) == "Tamam, planı bıraktım."
    assert len(provider.received) == 1
    assert [r.status for r in await actions(client)] == ["expired"]


async def test_unrelated_text_expires_question_and_continues_normally(client, fake_api):
    fake_api.calendar_items = [meeting(tomorrow())]
    provider = FakeProvider([[conflict_call()], [text("Merhaba!")]])
    client.providers["fake:local"] = provider
    _, conv = await say(client, "Yarın günümü planla")
    events, _ = await say(client, "Merhaba nasılsın", conv)
    assert "Merhaba!" in tokens(events)
    assert [r.status for r in await actions(client)] == ["expired"]


async def test_answer_out_of_range_is_not_an_answer(client, fake_api):
    fake_api.calendar_items = [meeting(tomorrow())]
    provider = FakeProvider([[conflict_call()], [text("Tamam")]])
    client.providers["fake:local"] = provider
    _, conv = await say(client, "Yarın günümü planla")
    await say(client, "7", conv)  # 3 seçenek var
    assert [r.status for r in await actions(client)] == ["expired"]


async def test_question_chain_stops_after_three(client, fake_api):
    items = [
        {"title": t, "start": "10:00", "minutes": 60, "card": False} for t in "ABCDE"
    ]
    provider = FakeProvider([[call("schedule_day", day="yarın", items=items)]])
    client.providers["fake:local"] = provider
    events, conv = await say(client, "Yarın günümü planla")
    assert "ile çakışıyor" in tokens(events)
    for _ in range(3):  # 1., 2., 3. cevap yeni soru üretir
        events, _ = await say(client, "1", conv)
        assert "ile çakışıyor" in tokens(events)
    events, _ = await say(client, "1", conv)  # 4. cevap: zincir sınırı
    assert tokens(events) == (
        "Planı netleştiremedim; saatleri tek mesajda yazıp tekrar dener misin?"
    )
    rows = await actions(client)
    assert len(rows) == 4 and all(r.status == "answered" for r in rows)
    assert [r.args["chain"] for r in rows] == [0, 1, 2, 3]
    assert len(provider.received) == 1


# ---------------------------------------------------------------- gün ipucu
async def test_two_days_in_text_ask_which_day_before_calling_model(client, fake_api):
    provider = FakeProvider(
        [
            [
                call(
                    "schedule_day",
                    day="salı",
                    items=[{"title": "Spor", "minutes": 30, "card": False}],
                )
            ]
        ]
    )
    client.providers["fake:local"] = provider
    events, conv = await say(client, "Cumartesi ve salı günlerini planla")
    assert provider.received == []  # model çağrılmadı
    assert "Hangi gün için planlayayım?" in tokens(events)
    (row,) = await actions(client)
    assert row.args["kind"] == "day" and len(row.args["options"]) == 2
    later = row.args["options"][1]["patch"]["day"]

    events, _ = await say(client, "2", conv)
    assert len(provider.received) == 1
    assert "Gün KESİN" in provider.all_text_sent()
    (card,) = [d for e, d in events if e == "action"]
    assert card["action_type"] == "schedule_day"
    proposed = (await actions(client))[-1]
    assert proposed.args["date"] == later


async def test_single_day_in_text_overrides_models_day(client, fake_api):
    provider = FakeProvider(
        [
            [
                call(
                    "schedule_day",
                    day="cumartesi",  # model yanlış gün verdi
                    items=[{"title": "Spor", "minutes": 30, "card": False}],
                )
            ]
        ]
    )
    client.providers["fake:local"] = provider
    events, _ = await say(client, "Yarın günümü planla")
    assert [d["action_type"] for e, d in events if e == "action"] == ["schedule_day"]
    (row,) = await actions(client)
    assert row.args["date"] == tomorrow().isoformat()
    assert row.args["day_raw"] == "cumartesi"
    assert "Gün KESİN" in provider.all_text_sent()


# ---------------------------------------------------------------- yazma katmanı
def make_writer(task_api_transport, now=None):
    w = WriteTools(
        TaskApiClient("t", transport=task_api_transport), PrivacyFilter(), TZ
    )
    if now:
        w.now_fn = lambda: now
    return w


async def test_template_is_applied_once_and_plan_is_time_sorted(
    fake_api, task_api_transport
):
    day = (datetime.now(TZ) + timedelta(days=3)).date()
    fake_api.templates[day.isoformat()] = HOME_TEMPLATE
    writer = make_writer(task_api_transport)
    prepared = await writer.prepare(
        "schedule_day",
        {
            "day": day.isoformat(),
            "items": [
                {"title": "Faruk abi", "minutes": 60, "board": "spor"},
                {"title": "P2", "board": "spor"},
                {"title": "Koşu", "minutes": 45, "window": "akşam", "board": "spor"},
            ],
        },
    )
    s = prepared.summary.splitlines()
    assert s[1] == "📋 Şablon: Ev günü (3 blok plana eklenecek)"
    assert any(x.startswith("08:00–09:00 Faruk abi") for x in s)
    assert any(x.startswith("18:00–18:45 Koşu") for x in s)
    assert any(x.startswith("saatsiz · P2") for x in s)
    assert prepared.args["template"] == {
        "id": 1, "name": "Ev günü", "blocks": 3, "apply": True,
    }  # fmt: skip
    assert fake_api.writes == []  # hazırlık yazmaz

    result = await writer.execute(prepared.action_type, prepared.args)
    paths = [(w["method"], w["path"]) for w in fake_api.writes]
    assert paths[0] == ("POST", f"/day-plans/{day}/apply-template")
    assert paths[-1] == ("PUT", f"/day-plans/{day}")
    assert paths.count(("POST", f"/day-plans/{day}/apply-template")) == 1
    assert result["template_added"] == 3
    body = fake_api.writes[-1]["body"]["items"]
    e1, e2 = (c["event_id"] for c in result["created"] if c["event_id"])
    shape = [
        i.get("title") or ("ev1" if i.get("event_id") == e1 else "ev2" if i.get("event_id") == e2 else "kart")
        for i in body
    ]
    assert shape == ["ev1", "Mesai", "Öğle arası", "Mesai", "ev2", "kart"]


async def test_template_already_applied_is_not_applied_again(fake_api, task_api_transport):
    day = (datetime.now(TZ) + timedelta(days=3)).date()
    fake_api.templates[day.isoformat()] = HOME_TEMPLATE
    fake_api.template_applied[day.isoformat()] = "x"
    writer = make_writer(task_api_transport)
    prepared = await writer.prepare(
        "schedule_day",
        {"day": day.isoformat(), "items": [{"title": "Okuma", "minutes": 30, "card": False}]},
    )
    assert prepared.args["template"]["apply"] is False
    assert "planda zaten var" in prepared.summary
    await writer.execute(prepared.action_type, prepared.args)
    assert not [w for w in fake_api.writes if w["path"].endswith("apply-template")]


async def test_unfit_carry_goes_to_next_days_plan(fake_api, task_api_transport):
    day = (datetime.now(TZ) + timedelta(days=3)).date()
    writer = make_writer(task_api_transport)
    items = [
        {"title": "Uzun", "minutes": 880, "card": False},
        {"title": "Sığmaz", "minutes": 60, "card": False},
    ]
    prepared = await writer.prepare(
        "schedule_day", {"day": day.isoformat(), "items": items, "_unfit": "carry"}
    )
    assert "→ yarına: Sığmaz" in prepared.summary
    assert prepared.args["carry"] == {
        "date": (day + timedelta(days=1)).isoformat(),
        "items": [{"title": "Sığmaz"}],
    }
    result = await writer.execute(prepared.action_type, prepared.args)
    assert result["carried"] == 1
    last = fake_api.writes[-1]
    assert last["path"] == f"/day-plans/{day + timedelta(days=1)}"
    assert last["body"]["items"] == [{"title": "Sığmaz"}]


async def test_blocks_alias_and_items_precedence(fake_api, task_api_transport):
    day = (datetime.now(TZ) + timedelta(days=3)).date()
    writer = make_writer(task_api_transport)
    via_blocks = await writer.prepare(
        "schedule_day",
        {"day": day.isoformat(), "blocks": [{"title": "A", "minutes": 30, "card": False}]},
    )
    assert "08:00–08:30 A" in via_blocks.summary
    both = await writer.prepare(
        "schedule_day",
        {
            "day": day.isoformat(),
            "items": [{"title": "Yeni", "minutes": 30, "card": False}],
            "blocks": [{"title": "Eski", "minutes": 30, "card": False}],
        },
    )
    assert "Yeni" in both.summary and "Eski" not in both.summary


async def test_moved_block_is_marked_in_summary(fake_api, task_api_transport):
    day = (datetime.now(TZ) + timedelta(days=3)).date()
    writer = make_writer(task_api_transport)
    prepared = await writer.prepare(
        "schedule_day",
        {
            "day": day.isoformat(),
            "items": [
                {"title": "İş", "start": "09:00", "end": "12:00", "card": False},
                {"title": "Kavramlar", "minutes": 90},
                {"title": "İş 2", "start": "13:00", "end": "18:00", "card": False},
            ],
        },
    )
    assert "18:00–19:30 Kavramlar" in prepared.summary
    assert "(boşluğa kaydırıldı)" in prepared.summary


async def test_rollover_resolves_tomorrow_to_calendar_today(fake_api, task_api_transport):
    sat_0030 = datetime(2026, 11, 14, 0, 30, tzinfo=TZ)
    writer = make_writer(task_api_transport, sat_0030)
    item = [{"title": "Spor", "minutes": 30, "card": False}]
    p = await writer.prepare("schedule_day", {"day": "yarın", "items": item})
    assert p.args["date"] == "2026-11-14"
    assert p.args["day_rolled"] is True and p.args["day_raw"] == "yarın"
    iso = await writer.prepare("schedule_day", {"day": "2026-11-14", "items": item})
    assert iso.args["date"] == "2026-11-14" and iso.args["day_rolled"] is False


async def test_rollover_setting_is_read_from_settings(fake_api, task_api_transport):
    fake_api.settings_extra = {"day_rollover": "02:00:00"}
    sat_0300 = datetime(2026, 11, 14, 3, 0, tzinfo=TZ)  # 02:00'den sonra: dönüm yok
    writer = make_writer(task_api_transport, sat_0300)
    p = await writer.prepare(
        "schedule_day",
        {"day": "yarın", "items": [{"title": "Spor", "minutes": 30, "card": False}]},
    )
    assert p.args["date"] == "2026-11-15" and p.args["day_rolled"] is False


async def test_past_day_still_rejected_with_calendar_today(fake_api, task_api_transport):
    writer = make_writer(task_api_transport, datetime(2026, 11, 14, 12, 0, tzinfo=TZ))
    with pytest.raises(ValueError, match="geçmişte kaldı"):
        await writer.prepare(
            "schedule_day",
            {"day": "2026-11-13", "items": [{"title": "A", "minutes": 30, "card": False}]},
        )


async def test_plan_day_warns_when_total_exceeds_free_time(fake_api, task_api_transport):
    day = (datetime.now(TZ) + timedelta(days=2)).date()
    writer = make_writer(task_api_transport)
    p = await writer.prepare(
        "plan_day",
        {"date": day.isoformat(), "items": [{"title": "Dev iş", "planned_minutes": 1000}]},
    )
    assert "⚠ Toplam 16 sa 40 dk iş; boş zaman 15 sa." in p.summary
    ok = await writer.prepare(
        "plan_day",
        {"date": day.isoformat(), "items": [{"title": "Küçük iş", "planned_minutes": 60}]},
    )
    assert "⚠" not in ok.summary
