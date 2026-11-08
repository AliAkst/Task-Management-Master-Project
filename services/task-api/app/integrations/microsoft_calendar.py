"""
Microsoft (Outlook/Teams) takvim tek yonlu senkron (Faz 8d).

- Yalnizca okuma (Calendars.Read). Etkinlikler `created_by="integration"` ve
  external_links (provider "microsoft", entity "event") ile isaretli, salt okunur.
- Kaynak: `GET /me/calendarView` (tekrarlari orneklere acar). Delta yok: her tur
  "bu haftanin basi -> weeks_ahead + 1 hafta" penceresinin tamami cekilir (idempotent).
- Teams filtresi (varsayilan): yalnizca Teams/Skype cevrimici toplantilari.
- Silme: iptal edilen, pencerede artik donmeyen etkinlik silinir; pencereden once
  baslayan (gecmis) etkinliklere dokunulmaz.
- To Do ile ayni kilidi (kullanici, "microsoft") paylasir; ayarlar
  `account.settings["calendar"]` altindadir (To Do anahtarlarina dokunulmaz).
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.core.exceptions import ValidationException
from app.core.logging import get_logger
from app.db.entities import IntegrationAccountEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.integrations import calendar_common, oauth
from app.integrations.accounts import (
    CALENDAR_DEFAULTS,
    IntegrationAccountService,
    has_calendar_scope,
)
from app.integrations.base import IntegrationError, SyncResult, lock_for
from app.integrations.calendar_common import MappedEvent
from app.integrations.microsoft_todo import GraphClient, _parse_graph_dt
from app.services.board import BoardService
from app.services.timeutil import day_bounds, user_tz

logger = get_logger(__name__)

PROVIDER = "microsoft"
PARENT_ID = "calendar"
PAGE_SIZE = 100
SELECT = (
    "id,subject,start,end,isAllDay,isCancelled,isOnlineMeeting,"
    "onlineMeetingProvider,onlineMeeting,webLink,location,changeKey"
)
TEAMS_PROVIDERS = {"teamsforbusiness", "skypeforconsumer", "skypeforbusiness"}
TEAMS_HOSTS = ("teams.live.com", "teams.microsoft.com")
UNTITLED = "(Başlıksız toplantı)"


class MicrosoftCalendarUpdate(BaseModel):
    enabled: bool
    teams_only: bool = True
    board_id: int | None = None
    weeks_ahead: int = Field(2, ge=1, le=8)


def consent_required() -> IntegrationError:
    return IntegrationError(
        "Teams toplantıları için Calendars.Read izni gerekiyor: Ayarlar → Bağlantılar → "
        "Microsoft → “Teams toplantıları için izin ver”.",
        "CALENDAR_CONSENT_REQUIRED",
        status_code=409,
    )


# ====================================================================
# Saf fonksiyonlar
# ====================================================================
def week_window(
    now: datetime, tz: ZoneInfo, week_start: int, weeks_ahead: int
) -> tuple[datetime, datetime]:
    """
    [bu haftanin basi 00:00 (yerel), + (weeks_ahead + 1) x 7 gun) -> UTC.
    `week_start`: 0 = Pazartesi ... 6 = Pazar (user_settings ile ayni).
    """
    today = now.astimezone(tz).date()
    first = today - timedelta(days=(today.weekday() - week_start) % 7)
    last = first + timedelta(days=(weeks_ahead + 1) * 7)
    return day_bounds(first, tz)[0], day_bounds(last, tz)[0]


def _join_url(item: dict[str, Any]) -> str | None:
    meeting = item.get("onlineMeeting") or {}
    url = meeting.get("joinUrl") if isinstance(meeting, dict) else None
    return url.strip()[:1000] if isinstance(url, str) and url.strip() else None


def is_teams(item: dict[str, Any]) -> bool:
    """Teams (ya da Skype) cevrimici toplantisi mi."""
    if not item.get("isOnlineMeeting"):
        return False
    provider = str(item.get("onlineMeetingProvider") or "").lower()
    join_url = (_join_url(item) or "").lower()
    return provider in TEAMS_PROVIDERS or any(h in join_url for h in TEAMS_HOSTS)


def _utc(value: dict[str, Any] | None) -> datetime | None:
    dt = _parse_graph_dt(value)
    return dt.astimezone(UTC) if dt is not None else None


def _raw_date(value: dict[str, Any] | None) -> date | None:
    raw = (value or {}).get("dateTime")
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def map_event(item: dict[str, Any], tz: ZoneInfo) -> MappedEvent | None:
    """Graph etkinligini yerel alanlara cevirir; baslangici olmayani (None) atlar."""
    if item.get("isAllDay"):
        # Tum gun: tarih kismi alinir (yerel gece yarisi, bitis haric) - Google kuralı
        first = _raw_date(item.get("start"))
        if first is None:
            return None
        last = _raw_date(item.get("end"))
        if last is None or last <= first:
            last = first + timedelta(days=1)
        start_at, end_at, all_day = day_bounds(first, tz)[0], day_bounds(last, tz)[0], True
    else:
        start_at = _utc(item.get("start"))
        if start_at is None:
            return None
        end_at = _utc(item.get("end")) or start_at + timedelta(hours=1)
        if end_at <= start_at:  # sifir sureli etkinlikler
            end_at = start_at + timedelta(minutes=30)
        all_day = False

    title = (item.get("subject") or "").strip() or UNTITLED
    location = ((item.get("location") or {}).get("displayName") or "").strip() or None
    return MappedEvent(
        title=title[:200],
        start_at=start_at,
        end_at=end_at,
        all_day=all_day,
        location=location[:200] if location else None,
        notes=None,
        url=item.get("webLink"),
        meeting_url=_join_url(item),
    )


def _utc_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ====================================================================
# Servis
# ====================================================================
class MicrosoftCalendarService:
    def __init__(self, uow: TaskUnitOfWork):
        self.uow = uow
        self.accounts = IntegrationAccountService(uow)

    @staticmethod
    def calendar_settings(account: IntegrationAccountEntity) -> dict[str, Any]:
        return {**CALENDAR_DEFAULTS, **((account.settings or {}).get("calendar") or {})}

    def _store(self, account: IntegrationAccountEntity, calendar: dict[str, Any]) -> None:
        settings = dict(account.settings or {})
        settings["calendar"] = calendar
        account.settings = settings  # yeni nesne: JSON degisikligi algilansin

    # ---------------- ayarlar ----------------
    async def update_settings(
        self, user_id: int, data: MicrosoftCalendarUpdate
    ) -> IntegrationAccountEntity:
        account = await self.accounts.get(user_id, PROVIDER)
        if data.enabled and not has_calendar_scope(account.scopes):
            raise consent_required()
        if data.board_id is not None:
            await BoardService(self.uow).get_owned_board(data.board_id, user_id)

        current = self.calendar_settings(account)
        new = {**current, **data.model_dump()}
        if not data.enabled:
            # Kapatinca Microsoft etkinlikleri silinir (To Do kartlari kalir)
            await calendar_common.purge_events(self.uow, user_id, PROVIDER, PARENT_ID)
        elif current.get("board_id") != data.board_id:
            await calendar_common.rehome_events(
                self.uow, user_id, PROVIDER, data.board_id, [PARENT_ID]
            )
        self._store(account, new)
        await self.uow.commit()
        return account

    async def disconnect(self, user_id: int) -> None:
        """Baglantiyi keser; takvim etkinlikleri silinir, To Do kartlari kalir."""
        await self.accounts.get(user_id, PROVIDER)
        await calendar_common.purge_events(self.uow, user_id, PROVIDER)
        await self.accounts.remove(user_id, PROVIDER)

    # ---------------- senkron ----------------
    async def sync(self, user_id: int) -> SyncResult:
        """Pencereyi ceker. Ayni kullanici icin (To Do ile birlikte) tek senkron."""
        async with lock_for(user_id, PROVIDER):
            account = await self.accounts.get(user_id, PROVIDER)
            if account.status == "error":
                raise IntegrationError(
                    account.last_error or "Yeniden bağlan",
                    "INTEGRATION_RECONNECT",
                    status_code=409,
                )
            if not has_calendar_scope(account.scopes):
                raise consent_required()  # hesap error'a alinmaz, To Do surer
            cfg = self.calendar_settings(account)
            if not cfg["enabled"]:
                raise ValidationException("Önce Teams toplantılarını aç")

            result = SyncResult()
            tz = await user_tz(self.uow, user_id)
            us = await self.uow.user_settings.get_by_user_id(user_id)
            window_start, window_end = week_window(
                datetime.now(UTC), tz, us.week_start if us else 0, int(cfg["weeks_ahead"])
            )
            board_id = cfg.get("board_id")
            if board_id is not None and await self.uow.boards.get_owned(board_id, user_id) is None:
                board_id = None  # hedef board silinmis

            try:
                client = GraphClient(await oauth.ensure_fresh_token(self.uow, account))
                items = await client.get_all(
                    "/me/calendarView",
                    params={
                        "startDateTime": _utc_z(window_start),
                        "endDateTime": _utc_z(window_end),
                        "$top": PAGE_SIZE,
                        "$select": SELECT,
                    },
                    headers={"Prefer": 'outlook.timezone="UTC"'},
                )
                await self._apply(
                    user_id,
                    tz,
                    board_id,
                    bool(cfg["teams_only"]),
                    items,
                    window_start,
                    result,
                )
                await self.uow.commit()
            except IntegrationError as e:
                await self.uow.session.rollback()
                if e.error_code == "INTEGRATION_RECONNECT":
                    await self._mark_error(user_id, e.message)
                    raise
                if e.error_code == "MS_FORBIDDEN":  # izin Graph'ta reddedildi
                    raise consent_required() from e
                result.errors.append(e.message)
            except Exception as e:  # noqa: BLE001
                await self.uow.session.rollback()
                logger.exception("Microsoft takvim senkron hatasi")
                result.errors.append(f"Beklenmeyen hata ({type(e).__name__})")
            await self._finish(user_id, result)
            return result

    async def _apply(
        self,
        user_id: int,
        tz: ZoneInfo,
        board_id: int | None,
        teams_only: bool,
        items: list[dict[str, Any]],
        window_start: datetime,
        result: SyncResult,
    ) -> None:
        seen: set[str] = set()
        seen_providers: set[str] = set()
        for item in items:
            if item.get("onlineMeetingProvider"):
                seen_providers.add(str(item["onlineMeetingProvider"]))
            if item.get("isCancelled"):
                link = await self.uow.external_links.get_by_external(
                    user_id, PROVIDER, "event", str(item.get("id"))
                )
                if link is not None:
                    await calendar_common.delete_linked_event(self.uow, link)
                    result.removed += 1
                continue
            if teams_only and not is_teams(item):
                continue
            mapped = map_event(item, tz)
            if mapped is None or not item.get("id"):
                continue
            seen.add(item["id"])
            await calendar_common.upsert_external_event(
                self.uow,
                user_id=user_id,
                provider=PROVIDER,
                parent_id=PARENT_ID,
                ext=item["id"],
                board_id=board_id,
                mapped=mapped,
                etag=item.get("changeKey"),
                result=result,
            )
        logger.debug(
            f"Microsoft takvim: {len(items)} oge, onlineMeetingProvider degerleri: "
            f"{sorted(seen_providers)}"
        )
        await calendar_common.delete_unseen_in_window(
            self.uow,
            user_id=user_id,
            provider=PROVIDER,
            parent_id=PARENT_ID,
            seen=seen,
            result=result,
            window_start=window_start,
        )

    async def _mark_error(self, user_id: int, message: str) -> None:
        account = await self.accounts.get(user_id, PROVIDER)
        account.status = "error"
        account.last_error = message
        await self.uow.commit()

    async def _finish(self, user_id: int, result: SyncResult) -> None:
        """Takvimin kendi durumu ayarlarda tutulur (To Do'nun last_error'una karismaz)."""
        account = await self.accounts.get(user_id, PROVIDER)
        cfg = self.calendar_settings(account)
        cfg["last_synced_at"] = datetime.now(UTC).isoformat()
        cfg["last_error"] = "; ".join(result.errors)[:1000] if result.errors else None
        self._store(account, cfg)
        await self.uow.commit()


async def sync_all_accounts() -> None:
    """Zamanlayici icin: takvimi acik Microsoft hesaplari, her biri kendi oturumunda."""
    from app.db.database import async_session_maker

    async with async_session_maker() as session:
        accounts = await TaskUnitOfWork(session).integration_accounts.list_by_provider(
            PROVIDER
        )
        user_ids = [
            a.user_id
            for a in accounts
            if a.status != "error"
            and has_calendar_scope(a.scopes)
            and MicrosoftCalendarService.calendar_settings(a)["enabled"]
        ]
    for user_id in user_ids:
        try:
            async with async_session_maker() as session:
                result = await MicrosoftCalendarService(TaskUnitOfWork(session)).sync(
                    user_id
                )
            if result.created or result.updated or result.removed:
                logger.info(
                    f"Microsoft takvim senkron (kullanici {user_id}): +{result.created} "
                    f"~{result.updated} -{result.removed}"
                )
        except Exception as e:  # noqa: BLE001 - biri digerlerini durdurmasin
            logger.warning(f"Microsoft takvim senkron basarisiz (kullanici {user_id}): {e}")
