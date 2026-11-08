"""
Google Takvim tek yonlu senkron (Faz 7b).

- Yalnizca okuma (calendar.readonly). Gelen etkinlikler `created_by="integration"`
  ve external_links ile isaretlidir; EventService bunlari duzenletmez/silmez.
- Ilk senkron: takvim basina `timeMin=simdi-30g, timeMax=simdi+180g`, sonra
  `syncToken`. 410 -> tam yeniden senkron (pencerede gorunmeyenler silinir).
- Tekrarlayan Google etkinlikleri `singleEvents=true` ile ornek ornek satir olur.
- Idempotent: etag ayniysa atlanir; kullanici board'u silince etkinlik yeniden gelir.
- Etkinlik olusumu/degisimi activity_log'a yazilmaz (dis takvim gurultusu,
  "planlanan vs gerceklesen" istatistigini bozmasin).
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field

from app.core.exceptions import ValidationException
from app.core.logging import get_logger
from app.db.entities import IntegrationAccountEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.integrations import calendar_common, oauth
from app.integrations.accounts import IntegrationAccountService
from app.integrations.base import IntegrationError, SyncResult, lock_for
from app.integrations.calendar_common import MappedEvent
from app.services.board import BoardService
from app.services.timeutil import day_bounds, user_tz

logger = get_logger(__name__)

PROVIDER = "google"
API_BASE = "https://www.googleapis.com/calendar/v3"
# Testlerde sahte ag icin degistirilir (httpx.MockTransport)
HTTP_TRANSPORT: httpx.AsyncBaseTransport | None = None

PAST_WINDOW = timedelta(days=30)
FUTURE_WINDOW = timedelta(days=180)
PAGE_SIZE = 250
MAX_PAGES = 40  # 10.000 etkinlikte dur (sonsuz dongu korumasi)


class GoogleCalendarInfo(BaseModel):
    id: str
    summary: str
    primary: bool = False
    color: str | None = None
    selected: bool = False


class GoogleSettingsUpdate(BaseModel):
    calendar_ids: list[str] = Field(default_factory=list, max_length=50)
    board_id: int | None = None


class SyncSummary(BaseModel):
    created: int
    updated: int
    removed: int
    errors: list[str]


class _SyncTokenExpired(Exception):
    """Google 410: syncToken gecersiz, tam senkron gerek."""


# ====================================================================
# HTTP istemcisi
# ====================================================================
class GoogleCalendarClient:
    def __init__(self, access_token: str):
        self._headers = {"Authorization": f"Bearer {access_token}"}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=API_BASE, timeout=20, transport=HTTP_TRANSPORT
            ) as http:
                res = await http.get(path, params=params, headers=self._headers)
        except httpx.HTTPError as e:
            raise IntegrationError(
                "Google Takvim'e ulaşılamadı; bağlantını kontrol edip tekrar dene.",
                "GOOGLE_UNREACHABLE",
            ) from e
        if res.status_code == 410:
            raise _SyncTokenExpired
        if res.status_code == 401:
            raise IntegrationError(
                "Google erişimi reddetti; bağlantıyı yeniden kur.",
                "INTEGRATION_RECONNECT",
                status_code=409,
            )
        if res.status_code == 403:
            raise IntegrationError(
                "Google Takvim bu takvim için izin vermedi (ya da Calendar API kapalı).",
                "GOOGLE_FORBIDDEN",
                status_code=403,
            )
        if res.status_code == 404:
            raise IntegrationError(
                "Google'da takvim bulunamadı.", "GOOGLE_NOT_FOUND", status_code=404
            )
        if res.status_code == 429:
            raise IntegrationError(
                "Google istek sınırına takıldı; biraz sonra tekrar dene.",
                "GOOGLE_RATE_LIMITED",
                status_code=429,
            )
        if res.status_code >= 400:
            raise IntegrationError(f"Google hata verdi ({res.status_code}).")
        return res.json()

    async def calendar_list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        for _ in range(MAX_PAGES):
            params: dict[str, Any] = {"maxResults": 250}
            if page_token:
                params["pageToken"] = page_token
            data = await self._get("/users/me/calendarList", params)
            items.extend(data.get("items", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return items

    async def events_page(
        self, calendar_id: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        # calendar_id '@' ve '#' icerebilir; httpx yol parcasini kodlar
        from urllib.parse import quote

        return await self._get(
            f"/calendars/{quote(calendar_id, safe='')}/events", params
        )


# ====================================================================
# Esleme (saf fonksiyonlar)
# ====================================================================
def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_datetime(value: str, fallback_tz: ZoneInfo) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=fallback_tz)
    return dt.astimezone(UTC)


def map_event(item: dict[str, Any], tz: ZoneInfo) -> MappedEvent | None:
    """Google etkinligini yerel alanlara cevirir; baslangici olmayani (None) atlar."""
    start = item.get("start") or {}
    end = item.get("end") or {}
    try:
        if "date" in start:  # tum gun; end.date haric (exclusive)
            first = _parse_date(start["date"])
            last = _parse_date(end["date"]) if "date" in end else first + timedelta(days=1)
            if last <= first:
                last = first + timedelta(days=1)
            start_at = day_bounds(first, tz)[0]
            end_at = day_bounds(last, tz)[0]
            all_day = True
        elif "dateTime" in start:
            event_tz = ZoneInfo(start["timeZone"]) if start.get("timeZone") else tz
            start_at = _parse_datetime(start["dateTime"], event_tz)
            end_at = (
                _parse_datetime(end["dateTime"], event_tz)
                if "dateTime" in end
                else start_at + timedelta(hours=1)
            )
            if end_at <= start_at:  # sifir sureli etkinlikler
                end_at = start_at + timedelta(minutes=30)
            all_day = False
        else:
            return None
    except (ValueError, KeyError):
        return None

    title = (item.get("summary") or "").strip() or "(Başlıksız)"
    location = (item.get("location") or "").strip() or None
    notes = (item.get("description") or "").strip() or None
    return MappedEvent(
        title=title[:200],
        start_at=start_at,
        end_at=end_at,
        all_day=all_day,
        location=location[:200] if location else None,
        notes=notes[:20000] if notes else None,
        url=item.get("htmlLink"),
    )


def external_id(calendar_id: str, event_id: str) -> str:
    return f"{calendar_id}|{event_id}"


def _utc_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ====================================================================
# Servis
# ====================================================================
class GoogleCalendarService:
    def __init__(self, uow: TaskUnitOfWork):
        self.uow = uow
        self.accounts = IntegrationAccountService(uow)

    async def _client(self, account: IntegrationAccountEntity) -> GoogleCalendarClient:
        return GoogleCalendarClient(await oauth.ensure_fresh_token(self.uow, account))

    @staticmethod
    def _settings(account: IntegrationAccountEntity) -> dict[str, Any]:
        return dict(account.settings or {})

    # ---------------- ayarlar ----------------
    async def list_calendars(self, user_id: int) -> list[GoogleCalendarInfo]:
        account = await self.accounts.get(user_id, PROVIDER)
        client = await self._client(account)
        selected = set(self._settings(account).get("calendar_ids", []))
        try:
            raw = await client.calendar_list()
        except _SyncTokenExpired as e:  # calendarList'te beklenmez
            raise IntegrationError("Google beklenmeyen bir yanıt verdi.") from e
        calendars = [
            GoogleCalendarInfo(
                id=c["id"],
                summary=c.get("summaryOverride") or c.get("summary") or c["id"],
                primary=bool(c.get("primary")),
                color=c.get("backgroundColor"),
                selected=c["id"] in selected,
            )
            for c in raw
        ]
        calendars.sort(key=lambda c: (not c.primary, c.summary.lower()))
        return calendars

    async def update_settings(
        self, user_id: int, data: GoogleSettingsUpdate
    ) -> IntegrationAccountEntity:
        account = await self.accounts.get(user_id, PROVIDER)
        if data.board_id is not None:
            await BoardService(self.uow).get_owned_board(data.board_id, user_id)
        settings = self._settings(account)
        old_ids = set(settings.get("calendar_ids", []))
        new_ids = list(dict.fromkeys(data.calendar_ids))

        # Secimden cikarilan takvimlerin etkinlikleri ve sync token'i temizlenir
        tokens = dict(settings.get("sync_tokens", {}))
        for cal_id in old_ids - set(new_ids):
            await self._purge_calendar(user_id, cal_id)
            tokens.pop(cal_id, None)
        # Hedef board degistiyse mevcut etkinlikler yeni board'a tasinsin
        if settings.get("board_id") != data.board_id:
            await self._rehome(user_id, new_ids, data.board_id)

        settings.update(
            {"calendar_ids": new_ids, "board_id": data.board_id, "sync_tokens": tokens}
        )
        account.settings = settings
        await self.uow.commit()
        return account

    async def disconnect(self, user_id: int) -> None:
        """Baglantiyi keser; Google'dan gelen (salt okunur) etkinlikler de silinir."""
        await calendar_common.purge_events(self.uow, user_id, PROVIDER)
        await self.accounts.remove(user_id, PROVIDER)

    async def _purge_calendar(self, user_id: int, calendar_id: str) -> int:
        return await calendar_common.purge_events(
            self.uow, user_id, PROVIDER, calendar_id
        )

    async def _rehome(
        self, user_id: int, calendar_ids: list[str], board_id: int | None
    ) -> None:
        await calendar_common.rehome_events(
            self.uow, user_id, PROVIDER, board_id, calendar_ids
        )

    # ---------------- senkron ----------------
    async def sync(self, user_id: int) -> SyncResult:
        """Secili takvimleri senkronlar. Ayni kullanici icin ayni anda tek senkron."""
        async with lock_for(user_id, PROVIDER):
            account = await self.accounts.get(user_id, PROVIDER)
            if account.status == "error":
                raise IntegrationError(
                    account.last_error or "Yeniden bağlan",
                    "INTEGRATION_RECONNECT",
                    status_code=409,
                )
            settings = self._settings(account)
            calendar_ids: list[str] = settings.get("calendar_ids", [])
            result = SyncResult()
            if not calendar_ids:
                raise ValidationException("Önce senkronlanacak takvim(ler)i seç")

            client = await self._client(account)
            tz = await user_tz(self.uow, user_id)
            for cal_id in calendar_ids:
                try:
                    next_token = await self._sync_calendar(
                        user_id, client, tz, cal_id, settings.get("board_id"), result
                    )
                    await self._save_sync_token(user_id, cal_id, next_token)
                    await self.uow.commit()
                except IntegrationError as e:
                    await self.uow.session.rollback()
                    result.errors.append(f"{cal_id}: {e.message}")
                    if e.error_code == "INTEGRATION_RECONNECT":
                        await self._mark_error(user_id, e.message)
                        raise
                except Exception as e:  # noqa: BLE001 - bir takvim digerini durdurmasin
                    await self.uow.session.rollback()
                    logger.exception("Google takvim senkron hatasi")
                    result.errors.append(f"{cal_id}: beklenmeyen hata ({type(e).__name__})")
            await self._finish(user_id, result)
            return result

    async def _save_sync_token(
        self, user_id: int, calendar_id: str, token: str | None
    ) -> None:
        if token is None:
            return
        account = await self.accounts.get(user_id, PROVIDER)
        settings = self._settings(account)
        tokens = dict(settings.get("sync_tokens", {}))
        tokens[calendar_id] = token
        settings["sync_tokens"] = tokens
        account.settings = settings  # yeni nesne: JSON degisikligi algilansin

    async def _mark_error(self, user_id: int, message: str) -> None:
        account = await self.accounts.get(user_id, PROVIDER)
        account.status = "error"
        account.last_error = message
        await self.uow.commit()

    async def _finish(self, user_id: int, result: SyncResult) -> None:
        account = await self.accounts.get(user_id, PROVIDER)
        account.last_synced_at = datetime.now(UTC)
        account.last_error = "; ".join(result.errors)[:1000] if result.errors else None
        await self.uow.commit()

    async def _sync_calendar(
        self,
        user_id: int,
        client: GoogleCalendarClient,
        tz: ZoneInfo,
        calendar_id: str,
        board_id: int | None,
        result: SyncResult,
    ) -> str | None:
        """Takvimi senkronlar; kaydedilecek yeni nextSyncToken'i dondurur."""
        account = await self.accounts.get(user_id, PROVIDER)
        sync_token = (self._settings(account).get("sync_tokens") or {}).get(calendar_id)
        if board_id is not None and await self.uow.boards.get_owned(board_id, user_id) is None:
            board_id = None  # hedef board silinmis

        try:
            return await self._run_pages(
                user_id, client, tz, calendar_id, board_id, sync_token, result
            )
        except _SyncTokenExpired:
            if sync_token is None:
                raise IntegrationError("Google senkron anahtarı yenilenemedi.")
            # 410 -> sync token'i at, tam yeniden senkron
            return await self._run_pages(
                user_id, client, tz, calendar_id, board_id, None, result
            )

    async def _run_pages(
        self,
        user_id: int,
        client: GoogleCalendarClient,
        tz: ZoneInfo,
        calendar_id: str,
        board_id: int | None,
        sync_token: str | None,
        result: SyncResult,
    ) -> str | None:
        full = sync_token is None
        base: dict[str, Any] = {"singleEvents": "true", "maxResults": PAGE_SIZE}
        if full:
            now = datetime.now(UTC)
            base["timeMin"] = _utc_z(now - PAST_WINDOW)
            base["timeMax"] = _utc_z(now + FUTURE_WINDOW)
        else:
            base["syncToken"] = sync_token

        seen: set[str] = set()
        page_token: str | None = None
        next_sync: str | None = None
        for _ in range(MAX_PAGES):
            params = dict(base)
            if page_token:
                params["pageToken"] = page_token
            page = await client.events_page(calendar_id, params)
            for item in page.get("items", []):
                ext = external_id(calendar_id, item["id"])
                seen.add(ext)
                await self._apply_item(user_id, tz, calendar_id, board_id, item, ext, result)
            page_token = page.get("nextPageToken")
            if not page_token:
                next_sync = page.get("nextSyncToken")
                break

        if full:
            # Tam senkron: pencerede artik gorunmeyen (Google'da silinmis) etkinlikler
            await calendar_common.delete_unseen_in_window(
                self.uow,
                user_id=user_id,
                provider=PROVIDER,
                parent_id=calendar_id,
                seen=seen,
                result=result,
            )
        return next_sync

    async def _apply_item(
        self,
        user_id: int,
        tz: ZoneInfo,
        calendar_id: str,
        board_id: int | None,
        item: dict[str, Any],
        ext: str,
        result: SyncResult,
    ) -> None:
        link = await self.uow.external_links.get_by_external(
            user_id, PROVIDER, "event", ext
        )
        if item.get("status") == "cancelled":
            if link is not None:
                await calendar_common.delete_linked_event(self.uow, link)
                result.removed += 1
            return

        mapped = map_event(item, tz)
        if mapped is None:
            return
        await calendar_common.upsert_external_event(
            self.uow,
            user_id=user_id,
            provider=PROVIDER,
            parent_id=calendar_id,
            ext=ext,
            board_id=board_id,
            mapped=mapped,
            etag=item.get("etag"),
            result=result,
            link=link,
        )


async def sync_all_accounts() -> None:
    """Zamanlayici icin: tum aktif Google hesaplari, her biri kendi oturumunda."""
    from app.db.database import async_session_maker

    async with async_session_maker() as session:
        accounts = await TaskUnitOfWork(session).integration_accounts.list_by_provider(
            PROVIDER
        )
        user_ids = [a.user_id for a in accounts]
    for user_id in user_ids:
        try:
            async with async_session_maker() as session:
                service = GoogleCalendarService(TaskUnitOfWork(session))
                result = await service.sync(user_id)
            if result.created or result.updated or result.removed:
                logger.info(
                    f"Google senkron (kullanici {user_id}): +{result.created} "
                    f"~{result.updated} -{result.removed}"
                )
        except Exception as e:  # noqa: BLE001 - biri digerlerini durdurmasin
            logger.warning(f"Google senkron basarisiz (kullanici {user_id}): {e}")
