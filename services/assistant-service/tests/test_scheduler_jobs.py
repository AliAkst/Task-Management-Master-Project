"""Faz 13f: zamanlayici is icerikleri - sahte task-api + sahte Telegram."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.db.models import (
    NotificationChannelEntity,
    ScheduledRunEntity,
    ServiceCredentialEntity,
)
from app.notify.base import Notification, Notifier
from app.scheduler import Scheduler
from app.security import encrypt
from app.tools.task_api import TaskApiClient

BOT = "123456789:AAFakeTokenForTestsOnly_abcdefghijk"
PAT = "pat_FakePatForTestsOnly_0123456789abcdef"
USER_ID = 7
SECRETS = ["Gizli date planı", "Gizli akşam yemeği", "Gizli kart"]


def utc(y, m, d, hh, mm=0) -> datetime:
    """Istanbul (UTC+3) saatini UTC'ye cevirir."""
    return datetime(y, m, d, hh, mm, tzinfo=UTC) - timedelta(hours=3)


def card(id_, title, board_id, **kw):
    return {
        "id": id_,
        "title": title,
        "status": "pending",
        "board_id": board_id,
        "due_date": None,
        "blocked": False,
        "parent_id": None,
        "is_archived": False,
        **kw,
    }


class FakeApi:
    def __init__(self) -> None:
        self.settings = {"timezone": "Europe/Istanbul"}
        self.plans: dict[str, dict] = {}
        self.templates: dict[str, dict] = {}
        self.calendar: list[dict] = []
        self.cards: dict[int, list[dict]] = {1: [], 2: []}
        self.postponed: list[dict] = []
        self.details: dict[int, dict] = {}
        self.unauthorized = False
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        self.requests.append(path)
        if self.unauthorized:
            return httpx.Response(401, json={"success": False})

        def ok(data):
            return httpx.Response(200, json={"success": True, "data": data})

        if path == "/settings/":
            return ok(self.settings)
        if path == "/boards":
            return ok(
                [
                    {"id": 1, "name": "Spor", "privacy": "cloud_allowed"},
                    {"id": 2, "name": "Date planları", "privacy": "local_only"},
                ]
            )
        if path.startswith("/boards/"):
            bid = int(path.split("/")[2])
            return ok({"board": {"id": bid}, "cards": self.cards[bid]})
        if path.startswith("/day-plans/") and path.endswith("/template"):
            day = path.split("/")[2]
            return ok({"template": self.templates.get(day)})
        if path.startswith("/day-plans/"):
            day = path.split("/")[2]
            return ok(self.plans.get(day, {"date": day, "exists": False, "items": []}))
        if path == "/calendar":
            return ok({"items": self.calendar})
        if path == "/analytics/summary":
            return ok({"most_postponed": self.postponed})
        if path.startswith("/cards/"):
            cid = int(path.split("/")[2])
            return ok(self.details.get(cid, {"id": cid, "depends_on": []}))
        return httpx.Response(404, json={"success": False})


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.fail = False
        self.attempts = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sendMessage"):
            self.attempts += 1
            if self.fail:
                return httpx.Response(
                    403, json={"ok": False, "description": "network down"}
                )
            self.sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {}})

    @property
    def texts(self) -> list[str]:
        return [m["text"] for m in self.sent]


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def tg() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
async def sched(db_session_maker, api, tg):
    async with db_session_maker() as s:
        s.add(
            NotificationChannelEntity(
                user_id=USER_ID,
                kind="telegram",
                is_enabled=True,
                config_encrypted=encrypt(json.dumps({"bot_token": BOT, "chat_id": 1})),
            )
        )
        s.add(
            ServiceCredentialEntity(
                user_id=USER_ID, token_encrypted=encrypt(PAT), token_id=42
            )
        )
        await s.commit()

    async def weekly(user, day):
        return Notification(
            "weekly", "Haftalık değerlendirme", "Haftalık hazır: 2 içgörü"
        )

    scheduler = Scheduler(
        db_session_maker,
        Notifier(db_session_maker, httpx.MockTransport(tg)),
        api_factory=lambda token: TaskApiClient(
            token, transport=httpx.MockTransport(api)
        ),
        weekly_runner=weekly,
    )
    scheduler.db = db_session_maker  # type: ignore[attr-defined]
    return scheduler


async def runs(sched) -> list[ScheduledRunEntity]:
    async with sched.db() as s:
        return list(
            await s.scalars(select(ScheduledRunEntity).order_by(ScheduledRunEntity.id))
        )


def plan(day, items, status="planned"):
    return {
        "date": day,
        "exists": bool(items),
        "status": status,
        "items": [{"was_planned": True, "board_id": None, **i} for i in items],
    }


# ---------------- T3-D2: basarisiz gonderim ----------------
async def test_failed_send_is_retried_after_cooldown_then_sent_once(sched, api, tg):
    tg.fail = True
    await sched.tick(utc(2026, 11, 10, 22, 40))
    assert tg.attempts == 1 and tg.sent == []
    [row] = [r for r in await runs(sched) if r.kind == "night_plan"]
    assert row.status == "failed" and row.detail["attempts"] == 1
    tg.fail = False
    await sched.tick(utc(2026, 11, 10, 22, 42))  # 5 dk dolmadi: yeniden deneme yok
    assert tg.attempts == 1
    await sched.tick(utc(2026, 11, 10, 22, 46))  # bekleme bitti: yeniden gonderir
    assert len(tg.sent) == 1
    [row] = [r for r in await runs(sched) if r.kind == "night_plan"]
    assert row.status == "sent"
    await sched.tick(utc(2026, 11, 10, 22, 55))  # gonderildi: ikinci gonderim yok
    assert len(tg.sent) == 1


async def test_failed_send_stops_after_three_attempts(sched, api, tg):
    tg.fail = True
    for minute in (40, 46, 52, 58):
        await sched.tick(utc(2026, 11, 10, 22, minute))
    assert tg.attempts == 3
    [row] = [r for r in await runs(sched) if r.kind == "night_plan"]
    assert row.status == "failed" and row.detail["attempts"] == 3


async def test_error_inside_job_is_retried(sched, api, tg, monkeypatch):
    real = sched._build
    state = {"down": True}

    async def flaky(*a, **kw):
        if state["down"]:
            raise RuntimeError("boom")
        return await real(*a, **kw)

    monkeypatch.setattr(sched, "_build", flaky)
    await sched.tick(utc(2026, 11, 10, 22, 40))
    [row] = [r for r in await runs(sched) if r.kind == "night_plan"]
    assert row.status == "failed" and row.detail["error"] == "RuntimeError"
    state["down"] = False
    await sched.tick(utc(2026, 11, 10, 22, 47))
    assert len(tg.sent) == 1
    [row] = [r for r in await runs(sched) if r.kind == "night_plan"]
    assert row.status == "sent" and row.detail["attempts"] == 2


async def test_failed_overdue_row_does_not_silence_cards(sched, api, tg):
    api.cards[1] = [card(11, "Vergi", 1, due_date="2026-11-07T10:00:00+03:00")]
    async with sched.db() as s:
        s.add(
            ScheduledRunEntity(
                user_id=USER_ID,
                kind="overdue",
                period_key="2026-11-09",
                status="failed",
                detail={"card_ids": [11], "results": {"telegram": "hata"}},
            )
        )
        await s.commit()
    await sched.tick(utc(2026, 11, 10, 13, 0))
    [text] = [t for t in tg.texts if t.startswith("Dikkat")]
    assert "Vergi" in text


# ---------------- gece plani ----------------
async def test_night_plan_without_plan_sends_notification(sched, api, tg):
    api.templates["2026-11-11"] = {"name": "Hafta içi", "blocks": []}
    await sched.tick(utc(2026, 11, 10, 22, 40))
    assert tg.texts == [
        "Yarının planı yok\nÇarşamba 11 Kasım için plan yapmadın. Şablon: Hafta içi. "
        "Planlamak için Ajanda'yı aç."
    ]
    [run] = [r for r in await runs(sched) if r.kind == "night_plan"]
    assert (run.kind, run.period_key, run.status) == (
        "night_plan",
        "2026-11-11",
        "sent",
    )


async def test_night_plan_with_plan_is_skipped(sched, api, tg):
    api.plans["2026-11-11"] = plan("2026-11-11", [{"title": "Koşu"}])
    await sched.tick(utc(2026, 11, 10, 22, 40))
    assert tg.sent == []
    [run] = [r for r in await runs(sched) if r.kind == "night_plan"]
    assert run.status == "skipped"


async def test_same_period_not_sent_twice_even_after_restart(sched, api, tg):
    now = utc(2026, 11, 10, 22, 40)
    await sched.tick(now)
    await sched.tick(utc(2026, 11, 10, 22, 41))  # sonraki dakika
    assert len(tg.sent) == 1
    assert len([r for r in await runs(sched) if r.kind == "night_plan"]) == 1


async def test_unique_conflict_blocks_second_send(sched, api, tg):
    async with sched.db() as s:
        s.add(
            ScheduledRunEntity(
                user_id=USER_ID,
                kind="night_plan",
                period_key="2026-11-11",
                status="sent",
            )
        )
        await s.commit()
    await sched.tick(utc(2026, 11, 10, 22, 40))
    assert tg.sent == []
    # dogrudan yaris: ayni anahtarla ikinci claim reddedilir
    assert await sched._claim(USER_ID, "night_plan", "2026-11-11") is None


async def test_rollover_changes_night_plan_target(sched, api, tg):
    api.settings = {
        "timezone": "Europe/Istanbul",
        "planning_time": "02:00:00",
        "day_rollover": "04:00:00",
    }
    await sched.tick(utc(2026, 11, 11, 2, 10))
    [run] = [r for r in await runs(sched) if r.kind == "night_plan"]
    assert run.period_key == "2026-11-11"


# ---------------- sabah ----------------
async def test_morning_text(sched, api, tg):
    api.plans["2026-11-10"] = plan(
        "2026-11-10",
        [
            {"title": "Rapor", "planned_start": "2026-11-10T10:30:00+03:00"},
            {"title": "Koşu", "planned_start": "2026-11-10T09:00:00+03:00"},
            {"title": "Kitap", "planned_start": None},
            {
                "title": "Toplantı",
                "planned_start": "2026-11-10T14:00:00+03:00",
                "event_id": 5,
            },
        ],
    )
    api.calendar = [
        {
            "kind": "event",
            "title": "Toplantı",
            "start": "2026-11-10T14:00:00+03:00",
            "all_day": False,
            "event_id": 5,
            "board_id": 1,
        },
        {
            "kind": "event",
            "title": "Diş",
            "start": "2026-11-10T16:00:00+03:00",
            "all_day": False,
            "event_id": 6,
            "board_id": 1,
        },
        {
            "kind": "deadline",
            "title": "Son tarih",
            "start": "2026-11-10T00:00:00+03:00",
            "all_day": True,
        },
    ]
    await sched.tick(utc(2026, 11, 10, 7, 35))
    [text] = [t for t in tg.texts if t.startswith("Günaydın")]
    assert text.splitlines()[0] == "Günaydın — Salı 10 Kasım"
    assert "09:00 Koşu" in text and "10:30 Rapor" in text and "14:00 Toplantı" in text
    assert text.index("09:00 Koşu") < text.index("10:30 Rapor")
    assert "Saatsiz 1 madde" in text
    assert "16:00 Diş" in text
    assert text.count("14:00 Toplantı") == 1  # planda olan etkinlik tekrarlanmaz


async def test_morning_empty_day(sched, api, tg):
    await sched.tick(utc(2026, 11, 10, 7, 35))
    [text] = [t for t in tg.texts if t.startswith("Günaydın")]
    assert text.endswith("Bugün için plan yok.")


async def test_morning_caps_lines(sched, api, tg):
    items = [
        {
            "title": f"İş {i}",
            "planned_start": f"2026-11-10T{8 + i // 2:02d}:{(i % 2) * 30:02d}:00+03:00",
        }
        for i in range(10)
    ]
    api.plans["2026-11-10"] = plan("2026-11-10", items)
    await sched.tick(utc(2026, 11, 10, 7, 35))
    [text] = [t for t in tg.texts if t.startswith("Günaydın")]
    assert "+2 madde" in text and "İş 9" not in text


async def test_morning_earlier_when_template_starts_early(sched, api, tg):
    api.templates["2026-11-10"] = {
        "name": "Erken",
        "blocks": [{"title": "Spor", "start": "06:30", "end": "07:30"}],
    }
    await sched.tick(utc(2026, 11, 10, 6, 20))  # 06:15 kuralı: 06:30-15dk = 06:15
    assert any(t.startswith("Günaydın") for t in tg.texts)


# ---------------- geciken ----------------
async def test_overdue_lists_and_silence(sched, api, tg):
    api.cards[1] = [
        card(11, "Vergi", 1, due_date="2026-11-07T10:00:00+03:00"),
        card(12, "Rapor", 1, due_date="2026-11-09T10:00:00+03:00"),
        card(13, "Gelecek", 1, due_date="2026-11-20T10:00:00+03:00"),
        card(14, "Bitmiş", 1, status="completed", due_date="2026-11-01T10:00:00+03:00"),
        card(15, "Ertelenen", 1),
        card(16, "Başlanabilir", 1),
    ]
    api.postponed = [{"card_id": 15, "title": "Ertelenen", "count": 5}]
    api.details[16] = {
        "id": 16,
        "depends_on": [{"id": 1, "status": "completed"}],
    }
    await sched.tick(utc(2026, 11, 10, 13, 0))
    [text] = [t for t in tg.texts if t.startswith("Dikkat")]
    assert "• Vergi (3 gün gecikti)" in text
    assert "• Rapor (1 gün gecikti)" in text
    assert "• Ertelenen (5 kez ertelendi)" in text
    assert "• Başlanabilir (artık başlayabilirsin)" in text
    assert "Gelecek" not in text and "Bitmiş" not in text
    assert text.index("Vergi") < text.index("Rapor")

    # sonraki 3 gun sessizlik: ayni kartlar tekrar yazilmaz -> bildirim yok
    tg.sent.clear()
    await sched.tick(utc(2026, 11, 11, 13, 0))
    assert tg.sent == []
    rows = [r for r in await runs(sched) if r.kind == "overdue"]
    assert [r.status for r in rows] == ["sent", "skipped"]


async def test_overdue_nothing_is_skipped(sched, api, tg):
    await sched.tick(utc(2026, 11, 10, 13, 0))
    assert not [t for t in tg.texts if t.startswith("Dikkat")]
    [run] = [r for r in await runs(sched) if r.kind == "overdue"]
    assert run.status == "skipped"


# ---------------- haftalik ----------------
async def test_weekly_with_few_reviewed_days(sched, api, tg):
    api.plans["2026-11-09"] = plan("2026-11-09", [{"title": "x"}], status="reviewed")
    await sched.tick(utc(2026, 11, 15, 20, 5))
    [text] = [t for t in tg.texts if t.startswith("Haftalık")]
    assert "Bu hafta yeterli gün değerlendirmesi yok (1/3 gün)." in text
    [run] = [r for r in await runs(sched) if r.kind == "weekly"]
    assert (run.period_key, run.status) == ("2026-W46", "skipped")


async def test_weekly_enough_days_runs_job(sched, api, tg):
    for d in ("2026-11-09", "2026-11-11", "2026-11-13"):
        api.plans[d] = plan(d, [{"title": "x"}], status="reviewed")
    await sched.tick(utc(2026, 11, 15, 20, 5))
    [text] = [t for t in tg.texts if t.startswith("Haftalık")]
    assert "Haftalık hazır: 2 içgörü" in text
    [run] = [r for r in await runs(sched) if r.kind == "weekly"]
    assert run.status == "sent"


# ---------------- gizlilik ----------------
async def test_hidden_board_content_never_in_any_body(sched, api, tg):
    """Dort is turunde de local_only board icerigi bildirim govdesinde yok."""
    api.cards[2] = [
        card(21, "Gizli date planı", 2, due_date="2026-11-01T10:00:00+03:00"),
        card(22, "Gizli kart", 2),
    ]
    api.cards[1] = [card(11, "Vergi", 1, due_date="2026-11-07T10:00:00+03:00")]
    api.postponed = [{"card_id": 21, "title": "Gizli date planı", "count": 6}]
    api.plans["2026-11-10"] = plan(
        "2026-11-10",
        [
            {
                "title": "Gizli kart",
                "board_id": 2,
                "card_id": 22,
                "planned_start": "2026-11-10T09:00:00+03:00",
            },
            {"title": "Gizli date planı", "board_id": 2, "card_id": 21},
            {
                "title": "Koşu",
                "board_id": 1,
                "card_id": 11,
                "planned_start": "2026-11-10T10:00:00+03:00",
            },
        ],
    )
    api.calendar = [
        {
            "kind": "event",
            "title": "Gizli akşam yemeği",
            "start": "2026-11-10T20:00:00+03:00",
            "all_day": False,
            "board_id": 2,
        },
        {
            "kind": "event",
            "title": "Diş",
            "start": "2026-11-10T16:00:00+03:00",
            "all_day": False,
            "board_id": 1,
        },
    ]
    for d in ("2026-11-09", "2026-11-11", "2026-11-13"):
        api.plans[d] = plan(
            d, [{"title": "Gizli date planı", "board_id": 2}], status="reviewed"
        )
    # gizli kart tarafindan okunmayan sablon adi vb. disinda her sey gizli board'a ait
    moments = [
        utc(2026, 11, 10, 7, 35),
        utc(2026, 11, 10, 13, 0),
        utc(2026, 11, 10, 22, 40),
        utc(2026, 11, 15, 20, 5),
    ]
    api.plans["2026-11-11"] = plan("2026-11-11", [], status="reviewed")
    for m in moments:
        await sched.tick(m)
    assert len(tg.sent) >= 3
    blob = "\n".join(tg.texts)
    for secret in SECRETS:
        assert secret not in blob
    assert "Gizli board'da" in blob  # sayi olarak anilir
    assert "Başka bir etkinlik" in blob  # gizli etkinlik basligi gizlenir
    assert "Koşu" in blob and "Diş" in blob and "Vergi" in blob  # acik icerik gelir


# ---------------- kimlik / kanal / tercih ----------------
async def test_unauthorized_sets_last_error_and_retries_later(sched, api, tg):
    api.unauthorized = True
    await sched.tick(utc(2026, 11, 10, 22, 40))
    assert tg.sent == [] and await runs(sched) == []
    async with sched.db() as s:
        row = await s.scalar(select(NotificationChannelEntity))
    assert row.last_error == (
        "Zamanlayıcı anahtarı geçersiz; Ayarlar → Bildirimler'den yeniden aç"
    )
    api.unauthorized = False  # anahtar duzeldi: ayni periyot hala gonderilir
    await sched.tick(utc(2026, 11, 10, 22, 45))
    assert len(tg.sent) == 1


async def test_no_enabled_channel_consumes_no_period(sched, api, tg):
    async with sched.db() as s:
        row = await s.scalar(select(NotificationChannelEntity))
        row.is_enabled = False
        await s.commit()
    await sched.tick(utc(2026, 11, 10, 22, 40))
    assert tg.sent == [] and await runs(sched) == []
    assert api.requests == []  # task-api'ye bile gidilmez


async def test_disabled_kind_is_not_sent(sched, api, tg):
    from app.db.models import NotificationSettingsEntity

    async with sched.db() as s:
        s.add(
            NotificationSettingsEntity(
                user_id=USER_ID,
                kinds={
                    "night_plan": False,
                    "morning": True,
                    "overdue": True,
                    "weekly": True,
                },
            )
        )
        await s.commit()
    await sched.tick(utc(2026, 11, 10, 22, 40))
    # 22:40'ta geciken penceresi de acik: yalniz night_plan hic calismaz
    assert not [r for r in await runs(sched) if r.kind == "night_plan"]
    assert not [t for t in tg.texts if t.startswith("Yarının")]


async def test_no_credentials_means_user_not_processed(db_session_maker, api, tg):
    sched = Scheduler(
        db_session_maker,
        Notifier(db_session_maker, httpx.MockTransport(tg)),
        api_factory=lambda t: TaskApiClient(t, transport=httpx.MockTransport(api)),
    )
    await sched.tick(utc(2026, 11, 10, 22, 40))
    assert api.requests == [] and tg.sent == []


# ---------------- haftalik kilit (G2) ve zamanlayici runner ----------------
async def test_empty_weekly_job_does_not_lock_the_week(monkeypatch, db_session_maker):
    import app.api.chat as chat_module
    import app.api.jobs as jobs_module
    from app.db.models import AiJobEntity

    monkeypatch.setattr(chat_module, "session_maker", db_session_maker)

    async def empty(*a, **kw):
        return {"week_summary": None, "insight_ids": [], "notes": []}

    monkeypatch.setattr(jobs_module, "run_weekly_insights", empty)
    monkeypatch.setattr(
        chat_module,
        "TaskApiClient",
        lambda token: TaskApiClient(token, transport=httpx.MockTransport(FakeApi())),
    )
    monkeypatch.setattr(chat_module, "build_provider", lambda *a, **kw: object())
    day = datetime(2026, 11, 15).date()
    job_id = await jobs_module._weekly_due(USER_ID, day, "ollama:gemma4:26b")
    assert job_id is not None
    # ayni haftada suren is varken ikinci is acilmaz
    assert await jobs_module._weekly_due(USER_ID, day, "ollama:gemma4:26b") is None

    ok = await jobs_module._execute(
        job_id,
        jobs_module.WEEKLY,
        {"id": USER_ID, "token": "t"},
        "ollama:gemma4:26b",
        day,
    )
    assert ok is True
    async with db_session_maker() as s:
        job = await s.get(AiJobEntity, job_id)
    assert job.status == "skipped"
    # bos sonuclu is artik 7 gun kilitlemez: ertesi gun yeni is acilir
    assert await jobs_module._weekly_due(USER_ID, day, "ollama:gemma4:26b") is not None


@pytest.mark.parametrize(
    "status,locks",
    [
        ("queued", True),
        ("running", True),
        ("done", True),
        ("failed", False),
        ("skipped", False),
    ],
)
async def test_weekly_due_lock_statuses(monkeypatch, db_session_maker, status, locks):
    import app.api.chat as chat_module
    import app.api.jobs as jobs_module
    from app.db.models import AiJobEntity

    monkeypatch.setattr(chat_module, "session_maker", db_session_maker)
    async with db_session_maker() as s:
        s.add(
            AiJobEntity(
                user_id=USER_ID,
                kind="weekly_insight",
                target_date="2026-11-08",
                status=status,
                model_id="ollama:gemma4:26b",
            )
        )
        await s.commit()
    got = await jobs_module._weekly_due(USER_ID, datetime(2026, 11, 15).date(), "m")
    assert (got is None) is locks


async def test_run_weekly_for_scheduler_model_off_and_done(
    monkeypatch, db_session_maker
):
    import app.api.chat as chat_module
    import app.api.jobs as jobs_module
    from app.llm.types import ModelInfo

    monkeypatch.setattr(chat_module, "session_maker", db_session_maker)
    user = {"id": USER_ID, "token": "t"}
    day = datetime(2026, 11, 15).date()

    async def no_models():
        return []

    monkeypatch.setattr(chat_module, "list_local_models", no_models)
    note = await jobs_module.run_weekly_for_scheduler(user, day)
    assert note.body == "Haftalık değerlendirme yapılamadı: yerel model kapalı."

    async def installed():
        return [ModelInfo("ollama:gemma4:26b", "ollama", "gemma4:26b", "gemma4", True)]

    async def fake_execute(job_id, kind, u, model_id, d):
        await jobs_module._set(job_id, status="done", result={"insight_ids": [1, 2, 3]})
        return True

    monkeypatch.setattr(chat_module, "list_local_models", installed)
    monkeypatch.setattr(jobs_module, "_execute", fake_execute)
    note = await jobs_module.run_weekly_for_scheduler(user, day)
    assert (
        note.body == "Haftalık değerlendirmen hazır: 3 içgörü — İstatistik sayfasında."
    )
    # ayni hafta ikinci kez: is acilmaz, bildirim yok
    assert await jobs_module.run_weekly_for_scheduler(user, day) is None


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("AUTH_EXPIRED", "Haftalık değerlendirme yapılamadı: zamanlayıcı anahtarı geçersiz."),
        (
            "Ollama bağlantı hatası http://x?key=SIR",
            "Haftalık değerlendirme yapılamadı; ayrıntı İstatistik sayfasında.",
        ),
    ],
)
async def test_weekly_failure_message_is_classified_not_raw(
    monkeypatch, db_session_maker, error, expected
):
    import app.api.chat as chat_module
    import app.api.jobs as jobs_module
    from app.llm.types import ModelInfo

    monkeypatch.setattr(chat_module, "session_maker", db_session_maker)

    async def installed():
        return [ModelInfo("ollama:gemma4:26b", "ollama", "gemma4:26b", "gemma4", True)]

    async def fake_execute(job_id, kind, u, model_id, d):
        await jobs_module._set(job_id, status="failed", error=error)
        return False

    monkeypatch.setattr(chat_module, "list_local_models", installed)
    monkeypatch.setattr(jobs_module, "_execute", fake_execute)
    note = await jobs_module.run_weekly_for_scheduler(
        {"id": USER_ID, "token": "t"}, datetime(2026, 11, 15).date()
    )
    assert note.body == expected
    assert "SIR" not in note.body and "yerel model kapalı" not in note.body


# ---------------- Faz 13g: sabah ozeti kurs satiri ----------------
def _course_row(title, part, board_id, status="active", cid=10):
    return {
        "goal_id": cid,
        "title": title,
        "status": status,
        "root_card": {"id": cid, "title": title, "board_id": board_id},
        "next_part": {"id": cid + 1, "title": part} if part else None,
    }


async def test_morning_course_lines(sched, api, tg, monkeypatch):
    rows = [
        _course_row("Power BI Kursu", "P2 — Veri kalitesi", 1, cid=10),
        _course_row("Fabric", "F1 — Giriş", 1, cid=20),
        _course_row("Üçüncü", "X1", 1, cid=30),
        _course_row("Duraklatıldı", "Y1", 1, status="paused", cid=40),
    ]
    orig = api.__call__

    def with_courses(request):
        if request.url.path.endswith("/learning/courses"):
            api.requests.append("/learning/courses")
            return httpx.Response(200, json={"success": True, "data": rows})
        return orig(request)

    monkeypatch.setattr(FakeApi, "__call__", lambda self, r: with_courses(r))
    await sched.tick(utc(2026, 11, 10, 7, 35))
    [text] = [t for t in tg.texts if t.startswith("Günaydın")]
    lines = [ln for ln in text.splitlines() if ln.startswith("📚")]
    assert lines == [
        "📚 Sıradaki: P2 — Veri kalitesi (Power BI Kursu)",
        "📚 Sıradaki: F1 — Giriş (Fabric)",
    ]  # en cok 2, duraklatilan yok


async def test_morning_course_hidden_board_is_masked(sched, api, tg, monkeypatch):
    rows = [_course_row("Gizli kurs adı", "Gizli parça", 2)]
    orig = FakeApi.__call__

    def patched(self, request):
        if request.url.path.endswith("/learning/courses"):
            return httpx.Response(200, json={"success": True, "data": rows})
        return orig(self, request)

    monkeypatch.setattr(FakeApi, "__call__", patched)
    await sched.tick(utc(2026, 11, 10, 7, 35))
    [text] = [t for t in tg.texts if t.startswith("Günaydın")]
    assert "📚 Sıradaki: gizli board'da kurs parçası" in text
    assert "Gizli kurs adı" not in text and "Gizli parça" not in text


async def test_morning_survives_missing_courses_endpoint(sched, api, tg):
    await sched.tick(utc(2026, 11, 10, 7, 35))  # FakeApi /learning/courses -> 404
    [text] = [t for t in tg.texts if t.startswith("Günaydın")]
    assert text.endswith("Bugün için plan yok.") and "📚" not in text
