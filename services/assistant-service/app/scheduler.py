"""
Sunucu zamanlayicisi (Faz 13f): tarayici kapaliyken de gece plani hatirlatmasi,
sabah ozeti, geciken kart uyarisi ve haftalik degerlendirme bildirimi.

Kural: ne zaman -> app/scheduler_rules.py (saf). Bu dosya: dongu, is icerikleri
(kod derler, model yok - haftalik haric), gizlilik, tekrar onleme.

- Zamanlayici yalniz `service_credentials` olan (bildirimi acmis) kullanicilar icin
  calisir ve task-api'ye okuma kapsamli PAT ile girer.
- Etkin kanali olmayan kullanici icin periyot TUKETILMEZ (sonradan acinca kacmasin).
- Ayni (kullanici, is, periyot) icin once `scheduled_runs` satiri eklenir (unique):
  servis yeniden baslasa da ikinci gonderim olmaz.
- Gizlilik: tum icerik PrivacyFilter(active=True) ile derlenir; local_only board
  verisi bildirim gövdesine (ucuncu tarafa) HICBIR zaman girmez.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import (
    DEFAULT_NOTIFY_KINDS,
    NotificationChannelEntity,
    NotificationSettingsEntity,
    ScheduledRunEntity,
    ServiceCredentialEntity,
)
from app.notify.base import Notification, Notifier, record_error
from app.scheduler_rules import (
    MORNING,
    NIGHT_PLAN,
    OVERDUE,
    WEEKLY,
    SchedCfg,
    due_jobs,
)
from app.security import SecretError, decrypt
from app.tools.privacy import PrivacyFilter
from app.tools.task_api import TaskApiAuthError, TaskApiClient, TaskApiError

log = logging.getLogger(__name__)

DEFAULT_TZ = "Europe/Istanbul"
DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]  # fmt: skip
RUN_HISTORY_DAYS = 14
MORNING_PLAN_LINES = 8
MORNING_EVENT_LINES = 5
OVERDUE_LINES = 6
STARTABLE_MAX = 3
STARTABLE_PROBE = 10  # bagimlilik bakisi icin en cok bu kadar kart ayrintisi
POSTPONE_MIN = 3
POSTPONE_WINDOW_DAYS = 28
SILENCE_RUNS = 3
WEEKLY_MIN_REVIEWED = 3
AUTH_ERROR = "Zamanlayıcı anahtarı geçersiz; Ayarlar → Bildirimler'den yeniden aç"
HIDDEN_EVENT = "Başka bir etkinlik"

# kind -> (periyot, ayar) uzerinden bildirim ureten kod; None = gonderilecek bir sey yok
Built = tuple[Notification | None, dict[str, Any]]
# haftalik is: kuyruga al, bitmesini bekle, sonuc bildirimi (yoksa None)
WeeklyRunner = Callable[[dict[str, Any], date], Awaitable[Notification | None]]


def day_label(d: date) -> str:
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def _parse_time(value: Any) -> time | None:
    if isinstance(value, time):
        return value
    if isinstance(value, str) and value:
        try:
            return time.fromisoformat(value)
        except ValueError:
            return None
    return None


def _parse_dt(value: Any, tz: ZoneInfo) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(tz)


async def build_privacy(api: TaskApiClient) -> PrivacyFilter:
    """ToolBox.create(cloud=True) mantigi: her calismada yeniden hesaplanir."""
    priv = PrivacyFilter(active=True)
    for b in await api.get("/boards", include_archived=True):
        if b.get("privacy") == "local_only":
            priv.hidden_boards.add(b["id"])
            detail = await api.get(f"/boards/{b['id']}")
            priv.hidden_cards.update(c["id"] for c in detail["cards"])
    return priv


# ---------------- is icerikleri ----------------
async def build_night_plan(api: TaskApiClient, target: date) -> Built:
    plan = await api.get(f"/day-plans/{target.isoformat()}")
    if any(i.get("was_planned", True) for i in plan.get("items", [])):
        return None, {}
    tpl = ""
    try:
        data = await api.get(f"/day-plans/{target.isoformat()}/template")
        name = ((data or {}).get("template") or {}).get("name")
        if name:
            tpl = f" Şablon: {name}."
    except TaskApiError:
        pass
    body = f"{day_label(target)} için plan yapmadın.{tpl} Planlamak için Ajanda'yı aç."
    return Notification(NIGHT_PLAN, "Yarının planı yok", body), {}


async def build_morning(
    api: TaskApiClient, today: date, tz: ZoneInfo, priv: PrivacyFilter
) -> Built:
    plan = await api.get(f"/day-plans/{today.isoformat()}")
    timed: list[tuple[datetime, str]] = []
    untimed = 0
    hidden = 0
    plan_event_ids: set[int] = set()
    for it in plan.get("items", []):
        if not it.get("was_planned", True):
            continue
        if it.get("event_id"):
            plan_event_ids.add(it["event_id"])
        if not priv.keep(it):
            hidden += 1
            continue
        start = _parse_dt(it.get("planned_start"), tz)
        if start is None:
            untimed += 1
        else:
            timed.append((start, it.get("title") or "Başlıksız"))
    timed.sort(key=lambda x: x[0])
    lines = [f"{s:%H:%M} {t}" for s, t in timed[:MORNING_PLAN_LINES]]
    if len(timed) > MORNING_PLAN_LINES:
        lines.append(f"+{len(timed) - MORNING_PLAN_LINES} madde")
    if untimed:
        lines.append(f"Saatsiz {untimed} madde")
    if hidden:
        lines.append(f"Gizli board'da {hidden} madde")

    start_dt = datetime.combine(today, time(0, 0), tzinfo=tz)
    cal = await api.get(
        "/calendar",
        start=start_dt.isoformat(),
        end=(start_dt + timedelta(days=1)).isoformat(),
    )
    events: list[tuple[datetime, str]] = []
    for ev in (cal or {}).get("items", []):
        if ev.get("kind") != "event" or ev.get("all_day"):
            continue
        if ev.get("event_id") and ev["event_id"] in plan_event_ids:
            continue
        start = _parse_dt(ev.get("start"), tz)
        if start is None:
            continue
        title = ev.get("title") or "Etkinlik"
        events.append((start, title if priv.keep(ev) else HIDDEN_EVENT))
    events.sort(key=lambda x: x[0])
    if events:
        lines.append("Takvim:")
        lines += [f"{s:%H:%M} {t}" for s, t in events[:MORNING_EVENT_LINES]]
    body = "\n".join(lines) if lines else "Bugün için plan yok."
    return Notification(MORNING, f"Günaydın — {day_label(today)}", body), {}


def _card_line(c: dict[str, Any], note: str) -> str:
    return f"• {c['title']} ({note})"


async def build_overdue(
    api: TaskApiClient,
    today: date,
    tz: ZoneInfo,
    priv: PrivacyFilter,
    silenced: set[int],
) -> Built:
    overdue: list[tuple[int, dict[str, Any]]] = []  # (gecikme gun, kart)
    candidates: list[dict[str, Any]] = []
    open_cards: dict[int, dict[str, Any]] = {}
    for b in await api.get("/boards", include_archived=False):
        detail = await api.get(f"/boards/{b['id']}")
        for c in detail["cards"]:
            if c.get("status") == "completed" or c.get("is_archived"):
                continue
            open_cards[c["id"]] = c
            due = _parse_dt(c.get("due_date"), tz)
            if due is not None and due.date() < today:
                overdue.append(((today - due.date()).days, c))
            elif (
                c.get("status") == "pending"
                and not c.get("blocked")
                and not c.get("parent_id")
            ):
                candidates.append(c)
    overdue.sort(key=lambda x: -x[0])

    postponed: list[dict[str, Any]] = []
    try:
        summary = await api.get(
            "/analytics/summary",
            start=(today - timedelta(days=POSTPONE_WINDOW_DAYS - 1)).isoformat(),
            end=today.isoformat(),
        )
        seen = {c["id"] for _, c in overdue}
        for p in (summary or {}).get("most_postponed", []):
            if p["count"] >= POSTPONE_MIN and p["card_id"] in open_cards:
                if p["card_id"] not in seen:
                    postponed.append(p)
    except TaskApiError:
        pass

    startable: list[dict[str, Any]] = []
    used = {c["id"] for _, c in overdue} | {p["card_id"] for p in postponed}
    for c in candidates[:STARTABLE_PROBE]:
        if c["id"] in used or len(startable) >= STARTABLE_MAX:
            continue
        if priv.card_hidden(c["id"]) or priv.board_hidden(c.get("board_id")):
            continue
        try:
            full = await api.get(f"/cards/{c['id']}")
        except TaskApiError:
            continue
        deps = full.get("depends_on") or []
        if deps and all(d.get("status") == "completed" for d in deps):
            startable.append(c)

    lines: list[str] = []
    ids: list[int] = []
    hidden = 0
    entries: list[tuple[int, str | None]] = []  # (card_id, satir | None=gizli)
    for days, c in overdue:
        hid = priv.card_hidden(c["id"]) or priv.board_hidden(c.get("board_id"))
        entries.append((c["id"], None if hid else _card_line(c, f"{days} gün gecikti")))
    for p in postponed:
        hid = priv.card_hidden(p["card_id"])
        line = f"• {p['title']} ({p['count']} kez ertelendi)"
        entries.append((p["card_id"], None if hid else line))
    for c in startable:
        entries.append((c["id"], _card_line(c, "artık başlayabilirsin")))
    for card_id, line in entries:
        if card_id in silenced:
            continue
        ids.append(card_id)
        if line is None:
            hidden += 1
        elif len(lines) < OVERDUE_LINES - (1 if hidden else 0):
            lines.append(line)
    if hidden:
        lines.append(f"• Gizli board'da {hidden} madde")
    if not ids:
        return None, {"card_ids": []}
    return (
        Notification(OVERDUE, "Dikkat isteyen kartlar", "\n".join(lines)),
        {"card_ids": ids},
    )


# ---------------- zamanlayici ----------------
@dataclass
class Scheduler:
    session_maker: async_sessionmaker[AsyncSession]
    notifier: Notifier
    api_factory: Callable[[str], TaskApiClient] = TaskApiClient
    weekly_runner: WeeklyRunner | None = None

    # -- yardimcilar --
    async def _notify_settings(self, user_id: int) -> NotificationSettingsEntity:
        async with self.session_maker() as session:
            row = await session.scalar(
                select(NotificationSettingsEntity).where(
                    NotificationSettingsEntity.user_id == user_id
                )
            )
            if row is None:
                row = NotificationSettingsEntity(
                    user_id=user_id, kinds=dict(DEFAULT_NOTIFY_KINDS)
                )
                session.add(row)
                await session.commit()
            return row

    async def _has_channel(self, user_id: int) -> bool:
        async with self.session_maker() as session:
            return (
                await session.scalar(
                    select(NotificationChannelEntity.id)
                    .where(
                        NotificationChannelEntity.user_id == user_id,
                        NotificationChannelEntity.is_enabled.is_(True),
                    )
                    .limit(1)
                )
            ) is not None

    async def _recent_runs(self, user_id: int, now: datetime) -> set[tuple[str, str]]:
        async with self.session_maker() as session:
            rows = await session.execute(
                select(ScheduledRunEntity.kind, ScheduledRunEntity.period_key).where(
                    ScheduledRunEntity.user_id == user_id,
                    ScheduledRunEntity.created_at
                    >= now - timedelta(days=RUN_HISTORY_DAYS),
                )
            )
            return {(k, p) for k, p in rows}

    async def _silenced(self, user_id: int) -> set[int]:
        async with self.session_maker() as session:
            rows = await session.scalars(
                select(ScheduledRunEntity)
                .where(
                    ScheduledRunEntity.user_id == user_id,
                    ScheduledRunEntity.kind == OVERDUE,
                )
                .order_by(ScheduledRunEntity.id.desc())
                .limit(SILENCE_RUNS)
            )
            out: set[int] = set()
            for r in rows:
                out.update((r.detail or {}).get("card_ids", []))
            return out

    async def _claim(self, user_id: int, kind: str, key: str) -> int | None:
        """Satiri ekle-dene: unique cakismasi = bu periyot zaten calisti."""
        async with self.session_maker() as session:
            row = ScheduledRunEntity(
                user_id=user_id,
                kind=kind,
                period_key=key,
                status="failed",
                detail={"started": True},
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return None
            return row.id

    async def _finish(self, run_id: int, status: str, detail: dict[str, Any]) -> None:
        async with self.session_maker() as session:
            row = await session.get(ScheduledRunEntity, run_id)
            if row is not None:
                row.status = status
                row.detail = detail
                await session.commit()

    async def _release(self, run_id: int) -> None:
        async with self.session_maker() as session:
            row = await session.get(ScheduledRunEntity, run_id)
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def _template_first_start(self, api: TaskApiClient, day: date) -> time | None:
        try:
            data = await api.get(f"/day-plans/{day.isoformat()}/template")
        except TaskApiError:
            return None
        blocks = ((data or {}).get("template") or {}).get("blocks") or []
        starts = [t for b in blocks if (t := _parse_time(b.get("start")))]
        return min(starts) if starts else None

    async def _build_weekly(
        self, api: TaskApiClient, user: dict[str, Any], today: date
    ) -> Built:
        reviewed = 0
        for back in range(7):
            d = (today - timedelta(days=back)).isoformat()
            try:
                plan = await api.get(f"/day-plans/{d}")
            except TaskApiError:
                continue
            reviewed += 1 if plan.get("status") == "reviewed" else 0
        if reviewed < WEEKLY_MIN_REVIEWED:
            body = (
                "Bu hafta yeterli gün değerlendirmesi yok "
                f"({reviewed}/{WEEKLY_MIN_REVIEWED} gün)."
            )
            return (
                Notification(WEEKLY, "Haftalık değerlendirme", body),
                {"force_status": "skipped"},
            )
        runner = self.weekly_runner or default_weekly_runner
        return await runner(user, today), {}

    # -- calisma --
    async def _build(
        self,
        api: TaskApiClient,
        user: dict[str, Any],
        tz: ZoneInfo,
        now_local: datetime,
        kind: str,
        key: str,
    ) -> Built:
        if kind == NIGHT_PLAN:
            return await build_night_plan(api, date.fromisoformat(key))
        if kind == WEEKLY:
            return await self._build_weekly(api, user, now_local.date())
        priv = await build_privacy(api)
        if kind == MORNING:
            return await build_morning(api, now_local.date(), tz, priv)
        silenced = await self._silenced(user["id"])
        return await build_overdue(api, now_local.date(), tz, priv, silenced)

    async def run_one(
        self,
        api: TaskApiClient,
        user: dict[str, Any],
        tz: ZoneInfo,
        now_local: datetime,
        kind: str,
        key: str,
    ) -> None:
        run_id = await self._claim(user["id"], kind, key)
        if run_id is None:
            return
        try:
            note, detail = await self._build(api, user, tz, now_local, kind, key)
            if note is None:
                await self._finish(run_id, "skipped", detail)
                return
            results = await self.notifier.send(user["id"], note)
            ok = not results or any(v == "ok" for v in results.values())
            forced = detail.pop("force_status", None)
            await self._finish(
                run_id,
                forced or ("sent" if ok else "failed"),
                {**detail, "results": results},
            )
        except TaskApiAuthError:
            await self._release(run_id)  # anahtar duzelince ayni periyot denenebilsin
            raise
        except Exception as e:
            log.exception("scheduler %s/%s failed", kind, key)
            await self._finish(run_id, "failed", {"error": type(e).__name__})

    async def tick_user(self, user_id: int, token: str, now_utc: datetime) -> None:
        if not await self._has_channel(user_id):
            return
        api = self.api_factory(token)
        try:
            st = await api.get("/settings/")
            tz = ZoneInfo(st.get("timezone") or DEFAULT_TZ)
            now_local = now_utc.astimezone(tz)
            ns = await self._notify_settings(user_id)
            kinds = {**DEFAULT_NOTIFY_KINDS, **(ns.kinds or {})}
            cfg = SchedCfg(
                planning_time=_parse_time(st.get("planning_time")),
                morning_time=_parse_time(st.get("morning_time")),
                review_time=_parse_time(st.get("review_time")),
                rollover=_parse_time(st.get("day_rollover")) or time(0, 0),
                kinds=kinds,
            )
            if kinds.get(MORNING) and now_local.hour < 12:
                cfg.template_first_start = await self._template_first_start(
                    api, now_local.date()
                )
            runs = await self._recent_runs(user_id, now_utc)
            user = {"id": user_id, "token": token}
            for kind, key in due_jobs(now_local, cfg, runs):
                await self.run_one(api, user, tz, now_local, kind, key)
        except TaskApiAuthError:
            async with self.session_maker() as session:
                await record_error(session, user_id, AUTH_ERROR)
        except (TaskApiError, httpx.HTTPError):
            log.warning("scheduler: task-api user %s", user_id, exc_info=True)
        finally:
            await api.close()

    async def tick(self, now_utc: datetime | None = None) -> None:
        now_utc = now_utc or datetime.now(UTC)
        async with self.session_maker() as session:
            creds = list(await session.scalars(select(ServiceCredentialEntity)))
        for cred in creds:
            try:
                token = decrypt(cred.token_encrypted)
            except SecretError:
                async with self.session_maker() as session:
                    await record_error(session, cred.user_id, AUTH_ERROR)
                continue
            try:
                await self.tick_user(cred.user_id, token, now_utc)
            except Exception:  # bir kullanicinin hatasi digerlerini/donguyu dusurmesin
                log.exception("scheduler tick user %s", cred.user_id)


async def default_weekly_runner(user: dict[str, Any], day: date) -> Notification | None:
    from app.api.jobs import run_weekly_for_scheduler

    return await run_weekly_for_scheduler(user, day)


async def scheduler_loop(scheduler: Scheduler) -> None:
    await asyncio.sleep(settings.scheduler_first_delay_seconds)
    while True:
        try:
            await scheduler.tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(settings.scheduler_interval_seconds)
