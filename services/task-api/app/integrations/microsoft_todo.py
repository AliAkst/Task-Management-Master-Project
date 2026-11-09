"""
Microsoft To Do iki yonlu tamamlama (Faz 7c; Samsung Reminder -> To Do -> Gelen Kutusu).

Iceri: liste basina `/me/todo/lists/{id}/tasks/delta` (deltaLink hesap ayarlarinda).
  - Yeni acik gorev -> Gelen Kutusu'nda kart (CardService, actor="integration").
    Zaten tamamlanmis yeni gorevler alinmaz (eski gecmis kartlari bogmasin).
  - Guncel gorev -> baslik/aciklama/tarih/oncelik, SADECE uzak icerik gercekten
    degistiyse (parmak izi); boylece kendi geri yazmamizin yankisi yerel
    duzenlemeleri ezmez.
  - Uzakta tamamlandi -> kart CardService yoluyla tamamlanir (unblock/seri calisir);
    uzakta yeniden acildi -> kart yeniden acilir. `@removed` -> kart arsivlenir.
Disari (outbox): yerel tamamlama/yeniden acma `external_links.pending_push` ile
  isaretlenir; hemen (arka planda) ve her senkron turunda `PATCH` edilir. Her turda
  once bekleyen push'lar gider, sonra delta cekilir (yerel tamamlama kaybolmaz).
  Entegrasyonun kendi degisiklikleri (actor="integration") geri yazilmaz (dongu yok).
"""

import asyncio
import hashlib
import html
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel

from app.core.exceptions import ValidationException
from app.core.logging import get_logger
from app.db.entities import ExternalLinkEntity, IntegrationAccountEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.integrations import oauth
from app.integrations.accounts import IntegrationAccountService
from app.integrations.base import IntegrationError, SyncResult, lock_for
from app.models.card import CardCreate, CardUpdate
from app.models.task import TaskPriority, TaskStatus
from app.services.board import BoardService
from app.services.card import CardService
from app.services.timeutil import user_tz

logger = get_logger(__name__)

PROVIDER = "microsoft"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TODO_URL = "https://to-do.live.com/tasks/"
# Testlerde sahte ag icin degistirilir (httpx.MockTransport)
HTTP_TRANSPORT: httpx.AsyncBaseTransport | None = None

MAX_PAGES = 100  # sonsuz dongu korumasi
PAGE_SIZE = 100


class TodoListInfo(BaseModel):
    id: str
    name: str
    selected: bool = True


class MicrosoftSettingsUpdate(BaseModel):
    # None = tum listeler
    list_ids: list[str] | None = None


class MicrosoftStatus(BaseModel):
    pending_push: int  # geri yazilmayi bekleyen
    failed_push: int  # bekleyen ve en az bir kez hata almis


class _DeltaExpired(Exception):
    """Graph 410: deltaLink gecersiz, tam senkron gerek."""


# ====================================================================
# HTTP istemcisi
# ====================================================================
class GraphClient:
    def __init__(self, access_token: str):
        self._headers = {"Authorization": f"Bearer {access_token}"}

    async def _request(
        self,
        method: str,
        target: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        url = target if target.startswith("http") else f"{GRAPH_BASE}{target}"
        try:
            async with httpx.AsyncClient(timeout=20, transport=HTTP_TRANSPORT) as http:
                res = await http.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers={**self._headers, **(headers or {})},
                )
        except httpx.HTTPError as e:
            raise IntegrationError(
                "Microsoft'a ulaşılamadı; bağlantını kontrol edip tekrar dene.",
                "MS_UNREACHABLE",
            ) from e
        if res.status_code == 410:
            raise _DeltaExpired
        if res.status_code == 401:
            raise IntegrationError(
                "Microsoft erişimi reddetti; bağlantıyı yeniden kur.",
                "INTEGRATION_RECONNECT",
                status_code=409,
            )
        if res.status_code == 403:
            raise IntegrationError(
                "Microsoft To Do bu işlem için izin vermedi.",
                "MS_FORBIDDEN",
                status_code=403,
            )
        if res.status_code == 404:
            raise IntegrationError(
                "Microsoft To Do'da bulunamadı.", "MS_NOT_FOUND", status_code=404
            )
        if res.status_code == 429:
            raise IntegrationError(
                "Microsoft istek sınırına takıldı; biraz sonra tekrar dene.",
                "MS_RATE_LIMITED",
                status_code=429,
            )
        if res.status_code >= 400:
            raise IntegrationError(f"Microsoft hata verdi ({res.status_code}).")
        if not res.content:
            return {}
        return res.json()

    async def lists(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        target: str | None = "/me/todo/lists"
        for _ in range(MAX_PAGES):
            if target is None:
                break
            data = await self._request("GET", target)
            items.extend(data.get("value", []))
            target = data.get("@odata.nextLink")
        return items

    async def get_all(
        self,
        target: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Sayfali GET: `@odata.nextLink` takip edilir (parametreler yalniz ilk istekte)."""
        items: list[dict[str, Any]] = []
        next_target: str | None = target
        for _ in range(MAX_PAGES):
            if next_target is None:
                break
            data = await self._request(
                "GET", next_target, params=params, headers=headers
            )
            items.extend(data.get("value", []))
            next_target = data.get("@odata.nextLink")
            params = None
        return items

    async def delta_page(self, target: str) -> dict[str, Any]:
        return await self._request(
            "GET", target, headers={"Prefer": f"odata.maxpagesize={PAGE_SIZE}"}
        )

    async def patch_task(
        self, list_id: str, task_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "PATCH", f"/me/todo/lists/{list_id}/tasks/{task_id}", json=body
        )


# ====================================================================
# Esleme (saf fonksiyonlar)
# ====================================================================
@dataclass
class MappedTask:
    title: str
    description: str | None
    due_date: datetime | None
    priority: TaskPriority
    completed: bool

    def fingerprint(self) -> str:
        """Icerik parmak izi (tamamlanma haric): yerel duzenlemeyi ezmemek icin."""
        raw = "\x1f".join(
            [
                self.title,
                self.description or "",
                self.due_date.isoformat() if self.due_date else "",
                self.priority.value,
            ]
        )
        return hashlib.sha1(raw.encode()).hexdigest()[:10]  # noqa: S324


_TAG = re.compile(r"<[^>]+>")
_FRACTION = re.compile(r"(\.\d{6})\d+")


def _body_text(body: dict[str, Any] | None) -> str | None:
    if not body:
        return None
    content = body.get("content") or ""
    if (body.get("contentType") or "").lower() == "html":
        content = html.unescape(_TAG.sub("", re.sub(r"<br\s*/?>", "\n", content)))
    content = content.strip()
    return content[:20000] or None


def _parse_graph_dt(value: dict[str, Any] | None) -> datetime | None:
    """`{dateTime, timeZone}` -> naive olmayan datetime (bilinmeyen dilim UTC)."""
    if not value or not value.get("dateTime"):
        return None
    raw = _FRACTION.sub(r"\1", value["dateTime"])
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        try:
            zone = ZoneInfo(value.get("timeZone") or "UTC")
        except Exception:  # noqa: BLE001 - Windows dilim adlari ("Turkey Standard Time")
            zone = ZoneInfo("UTC")
        dt = dt.replace(tzinfo=zone)
    return dt


def _due(item: dict[str, Any], tz: ZoneInfo) -> datetime | None:
    """
    Bitis tarihi: To Do'nun dueDateTime'i aslinda tarihtir -> kullanicinin yerel
    gununde 23:59 (arayuzdeki tarih secicisiyle ayni kural). Yoksa hatirlatici
    zamani (gercek an) kullanilir.
    """
    due = _parse_graph_dt(item.get("dueDateTime"))
    if due is not None:
        day = date(due.year, due.month, due.day)
        return datetime.combine(day, time(23, 59), tzinfo=tz).astimezone(UTC)
    reminder = _parse_graph_dt(item.get("reminderDateTime"))
    return reminder.astimezone(UTC) if reminder is not None else None


def map_task(item: dict[str, Any], tz: ZoneInfo) -> MappedTask:
    importance = (item.get("importance") or "normal").lower()
    priority = {
        "high": TaskPriority.HIGH,
        "low": TaskPriority.LOW,
    }.get(importance, TaskPriority.MEDIUM)
    return MappedTask(
        title=((item.get("title") or "").strip() or "(Başlıksız)")[:200],
        description=_body_text(item.get("body")),
        due_date=_due(item, tz),
        priority=priority,
        completed=item.get("status") == "completed",
    )


def _version(item: dict[str, Any]) -> str:
    return str(item.get("@odata.etag") or item.get("lastModifiedDateTime") or "")


def _pack(version: str, fingerprint: str) -> str:
    return f"{version}|{fingerprint}"[:200]


def _unpack(etag: str | None) -> tuple[str, str]:
    version, _, fp = (etag or "").rpartition("|")
    return version, fp


# ====================================================================
# Servis
# ====================================================================
class MicrosoftTodoService:
    def __init__(self, uow: TaskUnitOfWork):
        self.uow = uow
        self.accounts = IntegrationAccountService(uow)

    async def _client(self, account: IntegrationAccountEntity) -> GraphClient:
        return GraphClient(await oauth.ensure_fresh_token(self.uow, account))

    @staticmethod
    def _settings(account: IntegrationAccountEntity) -> dict[str, Any]:
        return dict(account.settings or {})

    # ---------------- ayarlar ----------------
    async def list_lists(self, user_id: int) -> list[TodoListInfo]:
        account = await self.accounts.get(user_id, PROVIDER)
        client = await self._client(account)
        chosen = self._settings(account).get("list_ids")
        return [
            TodoListInfo(
                id=lst["id"],
                name=lst.get("displayName") or lst["id"],
                selected=chosen is None or lst["id"] in chosen,
            )
            for lst in await client.lists()
        ]

    async def update_settings(
        self, user_id: int, data: MicrosoftSettingsUpdate
    ) -> IntegrationAccountEntity:
        account = await self.accounts.get(user_id, PROVIDER)
        settings = self._settings(account)
        deltas = dict(settings.get("delta_links", {}))
        new_ids = (
            None if data.list_ids is None else list(dict.fromkeys(data.list_ids))
        )
        previous = settings.get("list_ids")
        old_ids = set(previous) if previous is not None else set(deltas)
        # Secimden cikan listenin baglantilari ve delta'si silinir; kartlar KALIR
        # (artik senin isin; sadece To Do ile bag kopar).
        if new_ids is not None:
            for list_id in old_ids - set(new_ids):
                await self.uow.external_links.delete_children(
                    user_id, PROVIDER, list_id
                )
                deltas.pop(list_id, None)
        settings.update({"list_ids": new_ids, "delta_links": deltas})
        account.settings = settings
        await self.uow.commit()
        return account

    async def status(self, user_id: int) -> MicrosoftStatus:
        links = await self.uow.external_links.list_pending_push(user_id, PROVIDER)
        return MicrosoftStatus(
            pending_push=len(links),
            failed_push=sum(1 for link in links if link.push_error),
        )

    # ---------------- disari (outbox) ----------------
    async def push_now(self, user_id: int) -> None:
        """Bekleyen geri yazmalari hemen gonderir (yerel tamamlamadan sonra)."""
        async with lock_for(user_id, PROVIDER):
            account = await self.uow.integration_accounts.get_for_provider(
                user_id, PROVIDER
            )
            if account is None or account.status == "error":
                return
            if not await self.uow.external_links.list_pending_push(user_id, PROVIDER):
                return
            client = await self._client(account)
            await self._push_pending(user_id, client, SyncResult())
            await self.uow.commit()

    async def _push_pending(
        self, user_id: int, client: GraphClient, result: SyncResult
    ) -> None:
        now = datetime.now(UTC)
        for link in await self.uow.external_links.list_pending_push(user_id, PROVIDER):
            card = await self.uow.tasks.get_by_id(link.entity_id)
            if card is None or not link.external_parent_id:
                link.pending_push = False  # kart silinmis: gonderilecek bir sey yok
                continue
            status = "completed" if card.status == TaskStatus.COMPLETED else "notStarted"
            try:
                await client.patch_task(
                    link.external_parent_id, link.external_id, {"status": status}
                )
            except IntegrationError as e:
                if e.error_code == "INTEGRATION_RECONNECT":
                    await self._mark_error(user_id, e.message)
                    raise
                if e.error_code == "MS_NOT_FOUND":  # To Do'da silinmis: tekrar denenmez
                    link.pending_push = False
                    link.push_error = "To Do'da görev bulunamadı (silinmiş olabilir)."
                else:
                    link.push_error = e.message[:500]
                    result.errors.append(f"geri yazma ({card.title[:40]}): {e.message}")
                continue
            link.pending_push = False
            link.push_error = None
            link.last_synced_at = now

    # ---------------- iceri (delta) ----------------
    async def sync(self, user_id: int) -> SyncResult:
        """Once bekleyen geri yazmalar, sonra delta. Ayni kullanici icin tek senkron."""
        async with lock_for(user_id, PROVIDER):
            account = await self.accounts.get(user_id, PROVIDER)
            if account.status == "error":
                raise IntegrationError(
                    account.last_error or "Yeniden bağlan",
                    "INTEGRATION_RECONNECT",
                    status_code=409,
                )
            settings = self._settings(account)
            chosen: list[str] | None = settings.get("list_ids")
            if chosen is not None and not chosen:
                raise ValidationException("Önce senkronlanacak liste(ler)i seç")

            result = SyncResult()
            client = await self._client(account)
            try:
                await self._push_pending(user_id, client, result)
                await self.uow.commit()
            except IntegrationError as e:
                await self.uow.session.rollback()
                if e.error_code == "INTEGRATION_RECONNECT":
                    raise
                result.errors.append(e.message)

            tz = await user_tz(self.uow, user_id)
            _, inbox_list = await BoardService(self.uow).get_or_create_inbox(user_id)
            inbox_list_id = inbox_list.id
            await self.uow.commit()
            cards = CardService(self.uow, actor="integration")

            for lst in await client.lists():
                if chosen is not None and lst["id"] not in chosen:
                    continue
                name = lst.get("displayName") or lst["id"]
                try:
                    delta_link = await self._sync_list(
                        user_id, client, cards, tz, lst["id"], inbox_list_id, result
                    )
                    await self._save_delta(user_id, lst["id"], delta_link)
                    await self.uow.commit()
                except IntegrationError as e:
                    await self.uow.session.rollback()
                    result.errors.append(f"{name}: {e.message}")
                    if e.error_code == "INTEGRATION_RECONNECT":
                        await self._mark_error(user_id, e.message)
                        raise
                except Exception as e:  # noqa: BLE001 - bir liste digerini durdurmasin
                    await self.uow.session.rollback()
                    logger.exception("Microsoft To Do senkron hatasi")
                    result.errors.append(f"{name}: beklenmeyen hata ({type(e).__name__})")
            await self._finish(user_id, result)
            return result

    async def _save_delta(
        self, user_id: int, list_id: str, delta_link: str | None
    ) -> None:
        if delta_link is None:
            return
        account = await self.accounts.get(user_id, PROVIDER)
        settings = self._settings(account)
        deltas = dict(settings.get("delta_links", {}))
        deltas[list_id] = delta_link
        settings["delta_links"] = deltas
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

    async def _sync_list(
        self,
        user_id: int,
        client: GraphClient,
        cards: CardService,
        tz: ZoneInfo,
        list_id: str,
        inbox_list_id: int,
        result: SyncResult,
    ) -> str | None:
        account = await self.accounts.get(user_id, PROVIDER)
        delta_link = (self._settings(account).get("delta_links") or {}).get(list_id)
        try:
            return await self._run_pages(
                user_id, client, cards, tz, list_id, inbox_list_id, delta_link, result
            )
        except _DeltaExpired:
            if delta_link is None:
                raise IntegrationError("Microsoft senkron anahtarı yenilenemedi.")
            return await self._run_pages(  # 410 -> tam yeniden senkron
                user_id, client, cards, tz, list_id, inbox_list_id, None, result
            )

    async def _run_pages(
        self,
        user_id: int,
        client: GraphClient,
        cards: CardService,
        tz: ZoneInfo,
        list_id: str,
        inbox_list_id: int,
        delta_link: str | None,
        result: SyncResult,
    ) -> str | None:
        full = delta_link is None
        target = delta_link or f"/me/todo/lists/{list_id}/tasks/delta"
        seen: set[str] = set()
        next_delta: str | None = None
        for _ in range(MAX_PAGES):
            page = await client.delta_page(target)
            for item in page.get("value", []):
                seen.add(item["id"])
                await self._apply_item(
                    user_id, cards, tz, list_id, inbox_list_id, item, result
                )
            if page.get("@odata.nextLink"):
                target = page["@odata.nextLink"]
                continue
            next_delta = page.get("@odata.deltaLink")
            break

        if full:
            # Tam senkron: uzakta artik olmayan gorevlerin kartlari arsivlenir
            for link in await self.uow.external_links.for_parent(
                user_id, PROVIDER, "card", list_id
            ):
                if link.external_id not in seen:
                    await self._archive_linked(cards, user_id, link, result)
        return next_delta

    async def _archive_linked(
        self,
        cards: CardService,
        user_id: int,
        link: ExternalLinkEntity,
        result: SyncResult,
    ) -> None:
        card = await self.uow.tasks.get_by_id(link.entity_id)
        if card is not None and not card.is_archived:
            await cards.update(card.id, user_id, CardUpdate(is_archived=True))
            result.removed += 1

    async def _apply_item(
        self,
        user_id: int,
        cards: CardService,
        tz: ZoneInfo,
        list_id: str,
        inbox_list_id: int,
        item: dict[str, Any],
        result: SyncResult,
    ) -> None:
        link = await self.uow.external_links.get_by_external(
            user_id, PROVIDER, "card", item["id"]
        )
        if "@removed" in item:
            if link is not None:
                await self._archive_linked(cards, user_id, link, result)
            return

        mapped = map_task(item, tz)
        version = _version(item)
        fingerprint = mapped.fingerprint()
        now = datetime.now(UTC)

        if link is None:
            if mapped.completed:  # tamamlanmis eski gorevler alinmaz
                return
            detail = await cards.create(
                user_id,
                CardCreate(
                    list_id=inbox_list_id,
                    title=mapped.title,
                    description=mapped.description,
                    priority=mapped.priority,
                    due_date=mapped.due_date,
                ),
            )
            await self.uow.external_links.create(
                ExternalLinkEntity(
                    user_id=user_id,
                    provider=PROVIDER,
                    entity_type="card",
                    entity_id=detail.id,
                    external_id=item["id"],
                    external_parent_id=list_id,
                    etag=_pack(version, fingerprint),
                    url=TODO_URL,
                    last_synced_at=now,
                )
            )
            result.created += 1
            return

        card = await self.uow.tasks.get_by_id(link.entity_id)
        if card is None:
            return  # yerelde silinmis: tekrar getirilmez
        stored_version, stored_fp = _unpack(link.etag)
        if stored_version == version and stored_fp:
            link.last_synced_at = now
            return

        changes: dict[str, Any] = {}
        if fingerprint != stored_fp:  # uzakta icerik degisti
            if card.title != mapped.title:
                changes["title"] = mapped.title
            if (card.description or None) != mapped.description:
                changes["description"] = mapped.description
            if card.due_date != mapped.due_date:
                changes["due_date"] = mapped.due_date
            if card.priority != mapped.priority:
                changes["priority"] = mapped.priority
        # Bekleyen yerel tamamlama/yeniden acma varsa uzak durum yerel olani ezmez
        if not link.pending_push:
            done = card.status == TaskStatus.COMPLETED
            if mapped.completed and not done:
                changes["status"] = TaskStatus.COMPLETED
            elif not mapped.completed and done:
                changes["status"] = TaskStatus.PENDING
        if changes:
            await cards.update(card.id, user_id, CardUpdate(**changes))
            result.updated += 1
        link.etag = _pack(version, fingerprint)
        link.last_synced_at = now


# ====================================================================
# Arka plan
# ====================================================================
_background: set[asyncio.Task] = set()


def schedule_push(user_id: int) -> None:
    """Yerel tamamlamadan sonra bekleyen geri yazmayi arka planda hemen dener."""
    try:
        task = asyncio.get_running_loop().create_task(_push_for_user(user_id))
    except RuntimeError:  # calisan olay dongusu yok
        return
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _push_for_user(user_id: int) -> None:
    from app.db.database import async_session_maker

    try:
        async with async_session_maker() as session:
            await MicrosoftTodoService(TaskUnitOfWork(session)).push_now(user_id)
    except Exception as e:  # noqa: BLE001 - sonraki senkron turu tekrar dener
        logger.warning(f"Microsoft To Do geri yazma basarisiz (kullanici {user_id}): {e}")


async def sync_all_accounts() -> None:
    """Zamanlayici icin: tum aktif Microsoft hesaplari, her biri kendi oturumunda."""
    from app.db.database import async_session_maker

    async with async_session_maker() as session:
        accounts = await TaskUnitOfWork(session).integration_accounts.list_by_provider(
            PROVIDER
        )
        user_ids = [a.user_id for a in accounts]
    for user_id in user_ids:
        try:
            async with async_session_maker() as session:
                service = MicrosoftTodoService(TaskUnitOfWork(session))
                result = await service.sync(user_id)
            if result.created or result.updated or result.removed:
                logger.info(
                    f"Microsoft To Do senkron (kullanici {user_id}): +{result.created} "
                    f"~{result.updated} -{result.removed}"
                )
        except Exception as e:  # noqa: BLE001 - biri digerlerini durdurmasin
            logger.warning(f"Microsoft To Do senkron basarisiz (kullanici {user_id}): {e}")
