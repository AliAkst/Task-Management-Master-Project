"""Faz 9d: var olan karti basliktan bulma, schedule_card / reschedule_card / move_card,
create_card mukerrer korumasi, schedule_day eslesmesi, search_cards, get_calendar."""

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.agent.actions import ActionGate
from app.agent.context import focus_line
from app.tools.card_lookup import (
    fold,
    free_slot,
    query_tokens,
    resolve_card,
    tokens,
)
from app.tools.privacy import PrivacyFilter
from app.tools.read_tools import ToolBox
from app.tools.task_api import TaskApiClient
from app.tools.write_tools import WriteTools
from tests.conftest import CARDS, _card, call

TZ = ZoneInfo("Europe/Istanbul")


def api_for(transport, cloud=False):
    privacy = PrivacyFilter(
        active=cloud,
        hidden_boards={2} if cloud else set(),
        hidden_cards={21, 32} if cloud else set(),
    )
    return TaskApiClient("t", transport=transport), privacy


def writer(transport, cloud=False):
    api, privacy = api_for(transport, cloud)
    return WriteTools(api, privacy, TZ)


def future_day(n: int = 3) -> date:
    return datetime.now(TZ).date() + timedelta(days=n)


@pytest.fixture
def cards(monkeypatch):
    """Spor'da 'Python Eğitimi' (31) + tamamlanmis 'Eski rapor' (33)."""
    egitim = {**_card(31, "Python Eğitimi", 1), "estimated_minutes": 90}
    eski = {**_card(33, "Eski rapor", 1), "status": "completed"}
    monkeypatch.setitem(CARDS, 31, egitim)
    monkeypatch.setitem(CARDS, 33, eski)


@pytest.fixture
def two_trainings(cards, monkeypatch):
    monkeypatch.setitem(CARDS, 32, _card(32, "Eğitim videosu", 2))


# ---------------- katlama / token ----------------
def test_fold_and_tokens():
    assert fold("İngilizce") == "ingilizce"
    assert fold("IŞIK") == "isik"
    assert fold("Eğitimi") == "egitimi"
    assert tokens("Python Eğitimi!") == ["python", "egitimi"]
    # dolgu kelimeleri atilir; hepsi dolguysa orijinal kalir
    assert query_tokens("eğitim kartını") == ["egitim"]
    assert query_tokens("bu kart") == ["bu", "kart"]


# ---------------- resolve_card ----------------
class TestResolve:
    async def test_by_id_and_by_title(self, cards, task_api_transport):
        api, privacy = api_for(task_api_transport)
        by_id = await resolve_card(api, privacy, "31")
        assert by_id["title"] == "Python Eğitimi" and by_id["board_name"] == "Spor"
        assert by_id["list_name"] == "Yapılacak"
        by_title = await resolve_card(api, privacy, "eğitim kartını")
        assert by_title["id"] == 31 and by_title["board_name"] == "Spor"

    async def test_ambiguous_lists_both_ids(self, two_trainings, task_api_transport):
        api, privacy = api_for(task_api_transport)
        with pytest.raises(ValueError, match="Birden çok kart") as e:
            await resolve_card(api, privacy, "eğitim")
        assert "#31" in str(e.value) and "#32" in str(e.value)

    async def test_exact_title_wins(self, cards, monkeypatch, task_api_transport):
        monkeypatch.setitem(CARDS, 34, _card(34, "Eğitim", 1))
        api, privacy = api_for(task_api_transport)
        assert (await resolve_card(api, privacy, "eğitim"))["id"] == 34

    async def test_completed_excluded_by_default(self, cards, task_api_transport):
        api, privacy = api_for(task_api_transport)
        with pytest.raises(ValueError, match="tamamlanmış") as e:
            await resolve_card(api, privacy, "eski rapor")
        assert "#33" in str(e.value)
        got = await resolve_card(api, privacy, "eski rapor", include_completed=True)
        assert got["id"] == 33

    async def test_not_found_and_similar(self, cards, task_api_transport):
        api, privacy = api_for(task_api_transport)
        with pytest.raises(ValueError, match="Benzerler") as e:
            await resolve_card(api, privacy, "python kursu")
        assert "#31" in str(e.value)
        with pytest.raises(ValueError, match="bulunamadı; search_cards"):
            await resolve_card(api, privacy, "zzzqqq")

    async def test_this_card_uses_focus(self, cards, task_api_transport):
        api, privacy = api_for(task_api_transport)
        got = await resolve_card(api, privacy, "bu kart", focus_card_id=31)
        assert got["id"] == 31
        with pytest.raises(ValueError, match="Hangi kart"):
            await resolve_card(api, privacy, "Bu kartı")

    async def test_cloud_does_not_leak_private_titles(
        self, two_trainings, task_api_transport
    ):
        api, privacy = api_for(task_api_transport, cloud=True)
        # local_only board'daki "Eğitim videosu" eslesmez
        assert (await resolve_card(api, privacy, "eğitim"))["id"] == 31
        with pytest.raises(ValueError) as e:
            await resolve_card(api, privacy, "gizli date")
        assert "Gizli date planı" not in str(e.value)
        with pytest.raises(ValueError, match="gizli"):
            await resolve_card(api, privacy, "32")


# ---------------- free_slot ----------------
class TestFreeSlot:
    day = date(2030, 1, 14)
    long_ago = datetime(2020, 1, 1, tzinfo=TZ)

    def at(self, h, m=0):
        return datetime(2030, 1, 14, h, m, tzinfo=TZ)

    def test_empty_day_starts_at_nine(self):
        assert free_slot([], self.day, 60, TZ, self.long_ago) == self.at(9)

    def test_after_busy(self):
        busy = [(self.at(9), self.at(10, 30))]
        assert free_slot(busy, self.day, 60, TZ, self.long_ago) == self.at(10, 30)

    def test_today_rounds_up_to_quarter(self):
        now = datetime(2030, 1, 14, 13, 7, tzinfo=TZ)
        assert free_slot([], self.day, 30, TZ, now) == self.at(13, 15)

    def test_no_room(self):
        busy = [(self.at(9), self.at(21))]
        assert free_slot(busy, self.day, 30, TZ, self.long_ago) is None
        assert free_slot([], self.day, 13 * 60, TZ, self.long_ago) is None


# ---------------- schedule_card ----------------
class TestScheduleCard:
    async def test_by_title_creates_event_args(self, cards, task_api_transport):
        day = future_day()
        p = await writer(task_api_transport).prepare(
            "schedule_card", {"card": "eğitim kartı", "day": day.isoformat(), "start": "10"}
        )
        assert p.action_type == "create_event"
        assert p.args["card_id"] == 31
        assert p.args["start_at"].startswith(f"{day}T10:00:00")
        # sure: kartin tahmini (90 dk)
        assert p.args["end_at"].startswith(f"{day}T11:30:00")
        assert "#31" in p.summary and "Python Eğitimi" in p.summary
        assert "Spor" in p.summary and "takvim bloğu" in p.summary

    async def test_minutes_beat_estimate_and_default_is_60(
        self, cards, task_api_transport
    ):
        w = writer(task_api_transport)
        day = future_day().isoformat()
        p = await w.prepare(
            "schedule_card", {"card": "31", "day": day, "start": "10:00", "minutes": 20}
        )
        assert p.args["end_at"].startswith(f"{day}T10:20")
        # Koşu: tahmin 30 dk
        p = await w.prepare("schedule_card", {"card": "koşu", "day": day, "start": "10"})
        assert p.args["end_at"].startswith(f"{day}T10:30")
        # tahmini olmayan kart -> 60
        CARDS[31]["estimated_minutes"] = None
        p = await w.prepare("schedule_card", {"card": "31", "day": day, "start": "10"})
        assert p.args["end_at"].startswith(f"{day}T11:00")

    async def test_suggests_free_slot(self, cards, fake_api, task_api_transport):
        day = future_day()
        fake_api.calendar_items = [
            {
                "kind": "event",
                "title": "Toplantı",
                "start": f"{day}T09:00:00+03:00",
                "end": f"{day}T10:00:00+03:00",
                "all_day": False,
                "board_id": 1,
                "card_id": None,
            },
            {  # gun boyu ve son tarih bos yer sayilmaz
                "kind": "deadline",
                "title": "Son gün",
                "start": f"{day}T00:00:00+03:00",
                "end": None,
                "all_day": True,
                "board_id": 1,
                "card_id": 5,
            },
        ]
        p = await writer(task_api_transport).prepare(
            "schedule_card", {"card": "31", "day": day.isoformat()}
        )
        assert p.args["start_at"].startswith(f"{day}T10:00:00")
        assert "boş aralık önerildi" in p.summary

    async def test_no_free_slot_errors(self, cards, fake_api, task_api_transport):
        day = future_day()
        fake_api.calendar_items = [
            {
                "kind": "event",
                "title": "Konferans",
                "start": f"{day}T08:00:00+03:00",
                "end": f"{day}T22:00:00+03:00",
                "all_day": False,
                "board_id": 1,
                "card_id": None,
            }
        ]
        with pytest.raises(ValueError, match="boş yer yok"):
            await writer(task_api_transport).prepare(
                "schedule_card", {"card": "31", "day": day.isoformat()}
            )

    async def test_explicit_time_conflict_warns(
        self, cards, fake_api, task_api_transport
    ):
        day = future_day()
        fake_api.calendar_items = [
            {
                "kind": "event",
                "title": "Gizli akşam yemeği",
                "start": f"{day}T10:30:00+03:00",
                "end": f"{day}T11:30:00+03:00",
                "all_day": False,
                "board_id": 2,
                "card_id": None,
            }
        ]
        p = await writer(task_api_transport).prepare(
            "schedule_card", {"card": "31", "day": day.isoformat(), "start": "10:00"}
        )
        assert "⚠ çakışıyor: «Gizli akşam yemeği»" in p.summary
        # bulutta gizli board'un etkinlik adi yazilmaz
        p = await writer(task_api_transport, cloud=True).prepare(
            "schedule_card", {"card": "31", "day": day.isoformat(), "start": "10:00"}
        )
        assert "Gizli akşam yemeği" not in p.summary
        assert "başka bir etkinlik" in p.summary

    async def test_past_day_errors(self, cards, task_api_transport):
        with pytest.raises(ValueError, match="geçmişte"):
            await writer(task_api_transport).prepare(
                "schedule_card", {"card": "31", "day": "2020-01-01"}
            )

    async def test_execute_posts_event_with_card_id(
        self, cards, fake_api, task_api_transport
    ):
        w = writer(task_api_transport)
        p = await w.prepare(
            "schedule_card", {"card": "31", "day": future_day().isoformat(), "start": "9"}
        )
        await w.execute(p.action_type, p.args)
        post = next(x for x in fake_api.writes if x["path"] == "/events")
        assert post["body"]["card_id"] == 31 and post["actor"] == "ai"
        assert not any(x["path"] == "/cards" for x in fake_api.writes)


# ---------------- reschedule_card ----------------
def event(id_, start, end, external=None):
    return {
        "id": id_,
        "start_at": start,
        "end_at": end,
        "all_day": False,
        "external": external,
    }


class TestRescheduleCard:
    @pytest.fixture
    def planned(self, cards, fake_api):
        base = future_day(2)
        fake_api.card_extra[31] = {"due_date": f"{base}T20:59:00Z"}  # 23:59 yerel
        fake_api.card_events[31] = [
            event(70, f"{base - timedelta(days=9)}T08:00:00+03:00", f"{base - timedelta(days=9)}T09:00:00+03:00"),
            event(71, f"{base}T14:00:00+03:00", f"{base}T15:30:00+03:00"),
            event(72, f"{base}T09:00:00+03:00", f"{base}T10:00:00+03:00", {"provider": "google"}),
        ]
        return base

    async def test_moves_due_and_earliest_future_block(
        self, planned, task_api_transport
    ):
        target = future_day(5)
        p = await writer(task_api_transport).prepare(
            "reschedule_card", {"card": "python eğitimi", "day": target.isoformat()}
        )
        assert p.action_type == "update_card"
        assert p.args["card_id"] == 31 and p.args["move_to"] is None
        assert p.args["patch"]["due_date"] == f"{target}T23:59:00+03:00"
        (ev,) = p.args["events"]
        assert ev["id"] == 71  # gecmis ve dis etkinlik atlanir
        assert ev["start_at"].startswith(f"{target}T14:00:00")
        assert ev["end_at"].startswith(f"{target}T15:30:00")  # sure korunur
        assert "dış takvimdeki etkinlik taşınmaz" in p.summary
        assert "son tarih" in p.summary and "blok" in p.summary

    async def test_explicit_start_changes_block_time(
        self, planned, task_api_transport
    ):
        target = future_day(5)
        p = await writer(task_api_transport).prepare(
            "reschedule_card",
            {"card": "31", "day": target.isoformat(), "start": "09:30"},
        )
        ev = p.args["events"][0]
        assert ev["start_at"].startswith(f"{target}T09:30:00")
        assert ev["end_at"].startswith(f"{target}T11:00:00")

    async def test_without_block_only_due_date(self, cards, task_api_transport):
        target = future_day(5)
        p = await writer(task_api_transport).prepare(
            "reschedule_card", {"card": "31", "day": target.isoformat()}
        )
        assert p.args["events"] == []
        assert "blok" not in p.summary and "son tarih yok" in p.summary
        assert p.args["patch"]["due_date"] == f"{target}T23:59:00+03:00"

    async def test_execute_skips_read_only_event(
        self, planned, fake_api, task_api_transport
    ):
        fake_api.event_patch_status[71] = 409
        w = writer(task_api_transport)
        p = await w.prepare(
            "reschedule_card", {"card": "31", "day": future_day(5).isoformat()}
        )
        r = await w.execute(p.action_type, p.args)
        assert r["skipped_events"] == [71]
        paths = [x["path"] for x in fake_api.writes]
        assert "/cards/31" in paths and "/events/71" in paths

    async def test_execute_patches_event(self, planned, fake_api, task_api_transport):
        w = writer(task_api_transport)
        p = await w.prepare(
            "reschedule_card", {"card": "31", "day": future_day(5).isoformat()}
        )
        r = await w.execute(p.action_type, p.args)
        assert "skipped_events" not in r
        patch = next(x for x in fake_api.writes if x["path"] == "/events/71")
        assert patch["method"] == "PATCH" and patch["actor"] == "ai"


# ---------------- move_card ----------------
class TestMoveCard:
    async def test_cross_board(self, cards, task_api_transport):
        p = await writer(task_api_transport).prepare(
            "move_card", {"card": "python eğitimi", "board": "date planları"}
        )
        assert p.action_type == "update_card"
        assert p.args == {"card_id": 31, "patch": {}, "move_to": 20}
        assert "Spor › Yapılacak → Date planları › Yapılacak" in p.summary

    async def test_labels_drop_note(self, cards, fake_api, task_api_transport):
        fake_api.card_extra[31] = {"label_ids": [5]}
        p = await writer(task_api_transport).prepare(
            "move_card", {"card": "31", "board": "2"}
        )
        assert "etiketler board'a özel olduğu için düşer" in p.summary

    async def test_list_name_and_unknown_list(self, cards, task_api_transport):
        w = writer(task_api_transport)
        p = await w.prepare(
            "move_card", {"card": "31", "board": "Date planları", "list_name": "tamamlandı"}
        )
        assert p.args["move_to"] == 21
        with pytest.raises(ValueError, match="Mevcut listeler"):
            await w.prepare(
                "move_card", {"card": "31", "board": "Date planları", "list_name": "Yok"}
            )

    async def test_same_list_errors(self, cards, task_api_transport):
        with pytest.raises(ValueError, match="zaten orada"):
            await writer(task_api_transport).prepare(
                "move_card", {"card": "31", "board": "Spor"}
            )

    async def test_hidden_target_board_not_found(self, cards, task_api_transport):
        with pytest.raises(ValueError, match="Board bulunamadı") as e:
            await writer(task_api_transport, cloud=True).prepare(
                "move_card", {"card": "31", "board": "Date planları"}
            )
        assert "Date planları" not in str(e.value)

    async def test_execute_posts_move(self, cards, fake_api, task_api_transport):
        w = writer(task_api_transport)
        p = await w.prepare("move_card", {"card": "31", "board": "Date planları"})
        await w.execute(p.action_type, p.args)
        writes = [(x["method"], x["path"]) for x in fake_api.writes]
        assert writes == [("POST", "/cards/31/move")]  # bos patch ile PATCH atilmaz
        assert fake_api.writes[0]["body"]["list_id"] == 20


# ---------------- update_card: baslikla ----------------
class TestUpdateCard:
    async def test_title_ref_and_legacy_card_id(self, cards, task_api_transport):
        w = writer(task_api_transport)
        p = await w.prepare("update_card", {"card": "eğitim", "priority": "high"})
        assert p.args["card_id"] == 31
        p = await w.prepare("update_card", {"card_id": 11, "priority": "high"})
        assert p.args["card_id"] == 11
        with pytest.raises(ValueError, match="card gerekli"):
            await w.prepare("update_card", {"priority": "high"})


# ---------------- create_card mukerrer korumasi ----------------
class TestCreateCardDuplicate:
    async def test_duplicate_blocked_with_hint(self, cards, task_api_transport):
        with pytest.raises(ValueError, match="zaten var") as e:
            await writer(task_api_transport).prepare(
                "create_card", {"board_id": 1, "title": "python eğitimi"}
            )
        msg = str(e.value)
        assert "#31" in msg and "schedule_card" in msg and "force_new" in msg

    async def test_force_new_passes(self, cards, task_api_transport):
        p = await writer(task_api_transport).prepare(
            "create_card", {"board_id": 1, "title": "Python Eğitimi", "force_new": True}
        )
        assert p.args["title"] == "Python Eğitimi" and "force_new" not in p.args

    async def test_completed_same_title_does_not_block(self, cards, task_api_transport):
        p = await writer(task_api_transport).prepare(
            "create_card", {"board_id": 1, "title": "Eski rapor"}
        )
        assert p.action_type == "create_card"

    async def test_partial_match_does_not_block(self, cards, task_api_transport):
        p = await writer(task_api_transport).prepare(
            "create_card", {"board_id": 1, "title": "Python"}
        )
        assert p.action_type == "create_card"


# ---------------- schedule_day: var olan kart ----------------
async def test_schedule_day_reuses_existing_card(cards, fake_api, task_api_transport):
    w = writer(task_api_transport)
    day = future_day().isoformat()
    p = await w.prepare(
        "schedule_day",
        {"day": day, "blocks": [{"title": "Python Eğitimi", "start": "10:00", "minutes": 60, "board": "Spor"}]},
    )
    assert p.args["blocks"][0]["card_id"] == 31
    assert "var olan kart #31" in p.summary
    r = await w.execute(p.action_type, p.args)
    assert not any(x["path"] == "/cards" for x in fake_api.writes)
    event_post = next(x for x in fake_api.writes if x["path"] == "/events")
    assert event_post["body"]["card_id"] == 31
    assert r["created"][0]["card_id"] == 31 and r["added_to_plan"] is True
    plan = next(x for x in fake_api.writes if x["method"] == "PUT")
    assert plan["body"]["items"] == [{"card_id": 31}]


# ---------------- search_cards / get_calendar ----------------
async def make_box(transport, cloud=False):
    box = await ToolBox.create(
        TaskApiClient("t", transport=transport), cloud=cloud, tz=TZ
    )
    return box


class TestReadTools:
    async def test_search_turkish_and_multi_word(self, two_trainings, task_api_transport):
        box = await make_box(task_api_transport)
        res = await box.search_cards("EĞİTİM kartını")
        assert [r["id"] for r in res] == [31, 32]
        assert res[0]["board"] == "Spor" and res[1]["board"] == "Date planları"
        res = await box.search_cards("python eğitim")
        assert [r["id"] for r in res] == [31]
        assert (await box.search_cards("yokböyle")) == {"result": "Eşleşen kart yok"}

    async def test_search_exact_first_and_completed(
        self, cards, monkeypatch, task_api_transport
    ):
        monkeypatch.setitem(CARDS, 34, _card(34, "Eğitim", 2))
        box = await make_box(task_api_transport)
        assert [r["id"] for r in await box.search_cards("eğitim")] == [34, 31]
        assert (await box.search_cards("eski rapor")) == {"result": "Eşleşen kart yok"}
        res = await box.search_cards("eski rapor", include_completed=True)
        assert res[0]["id"] == 33

    async def test_search_hides_private_in_cloud(self, two_trainings, task_api_transport):
        box = await make_box(task_api_transport, cloud=True)
        assert [r["id"] for r in await box.search_cards("eğitim")] == [31]

    async def test_get_calendar_event_id_and_read_only(
        self, fake_api, task_api_transport
    ):
        fake_api.calendar_items = [
            {
                "kind": "event",
                "title": "Teams toplantısı",
                "start": "s",
                "end": "e",
                "all_day": False,
                "board_id": 1,
                "card_id": None,
                "event_id": 9,
                "external": {"provider": "microsoft", "url": None},
            },
            {
                "kind": "event",
                "title": "Koşu bloğu",
                "start": "s",
                "end": "e",
                "all_day": False,
                "board_id": 1,
                "card_id": 11,
                "event_id": 10,
                "external": None,
            },
        ]
        box = await make_box(task_api_transport)
        out = await box.get_calendar("2030-01-01", "2030-01-02")
        assert out[0]["event_id"] == 9 and out[0]["read_only"] is True
        assert out[1]["event_id"] == 10 and "read_only" not in out[1]


# ---------------- izinler / sohbet baglami ----------------
async def gate_box(transport, db_session_maker, modes):
    box = await make_box(transport)
    box.gate = ActionGate(
        db_session_maker,
        box.writer,
        user_id=7,
        conversation_id=None,
        model_id="m",
        modes={
            "create_card": "ask",
            "update_card": "ask",
            "create_event": "ask",
            **modes,
        },
    )
    return box


async def test_permissions_map_to_existing_actions(
    task_api_transport, db_session_maker
):
    box = await gate_box(task_api_transport, db_session_maker, {"update_card": "never"})
    names = {s.name for s in box.specs()}
    assert "update_card" not in names
    assert "reschedule_card" not in names and "move_card" not in names
    assert "schedule_card" in names
    box = await gate_box(task_api_transport, db_session_maker, {"create_event": "never"})
    names = {s.name for s in box.specs()}
    assert "schedule_card" not in names and "reschedule_card" in names


async def test_create_event_schema_has_no_card_id():
    from app.tools.write_tools import WRITE_SPECS

    spec = next(s for s in WRITE_SPECS if s.name == "create_event")
    assert "card_id" not in json.dumps(spec.parameters)
    upd = next(s for s in WRITE_SPECS if s.name == "update_card")
    assert "card" in upd.parameters["properties"]
    assert "card_id" not in upd.parameters["properties"]


async def test_schedule_card_via_toolbox_creates_proposal(
    cards, fake_api, task_api_transport, db_session_maker
):
    box = await gate_box(task_api_transport, db_session_maker, {})
    r = await box.execute(
        call(
            "schedule_card", card="eğitim kartı", day=future_day().isoformat(), start="10"
        ).tool_call
    )
    assert r.ok and r.action["status"] == "proposed"
    assert fake_api.writes == []


async def test_focus_line_sets_focus_card(task_api_transport):
    api, _ = api_for(task_api_transport)
    box = await make_box(task_api_transport)
    line = await focus_line(api, box, 1, 11)
    assert "'bu kart' dediğinde" in line
    assert box.writer.focus_card_id == 11
    # yalniz board odagi: kart odagi ayarlanmaz
    box2 = await make_box(task_api_transport)
    await focus_line(api, box2, 1, None)
    assert box2.writer.focus_card_id is None
    # bulutta gizli kart odak olmaz
    box3 = await make_box(task_api_transport, cloud=True)
    await focus_line(api, box3, 2, 21)
    assert box3.writer.focus_card_id is None
