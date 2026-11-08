"""
Dis takvim saglayicilarinin (Google, Microsoft) ortak mantigi (Faz 8d).

Saglayiciya ozgu olan (HTTP, sync token/pencere, esleme) kendi modullerinde kalir;
burada yalnizca `events` + `external_links` uzerindeki ortak islemler vardir:
olustur/guncelle/etag ayniysa atla, silme, toplu silme, board'a tasima.
Fonksiyonlar `provider` parametrelidir ve oturumu (`uow`) disaridan alir.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.entities import EventEntity, ExternalLinkEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.integrations.base import SyncResult


@dataclass
class MappedEvent:
    title: str
    start_at: datetime
    end_at: datetime
    all_day: bool
    location: str | None
    notes: str | None
    url: str | None
    meeting_url: str | None = None


def fill_event(event: EventEntity, mapped: MappedEvent, board_id: int | None) -> None:
    event.title = mapped.title
    event.start_at = mapped.start_at
    event.end_at = mapped.end_at
    event.all_day = mapped.all_day
    event.location = mapped.location
    event.notes = mapped.notes
    event.meeting_url = mapped.meeting_url
    event.board_id = board_id
    event.card_id = None
    event.recurrence_rule = None


async def delete_linked_event(uow: TaskUnitOfWork, link: ExternalLinkEntity) -> None:
    event = await uow.events.get_by_id(link.entity_id)
    if event is not None:
        await uow.day_plan_items.detach_event(event.id)
        await uow.events.delete(event)
    await uow.external_links.delete(link)


async def purge_events(
    uow: TaskUnitOfWork, user_id: int, provider: str, parent_id: str | None = None
) -> int:
    """Saglayicidan gelen etkinlikleri siler (parent_id verilirse yalniz o takvimin)."""
    if parent_id is None:
        links = await uow.external_links.list_for_provider(user_id, provider, "event")
    else:
        links = await uow.external_links.for_parent(
            user_id, provider, "event", parent_id
        )
    for link in links:
        await delete_linked_event(uow, link)
    return len(links)


async def rehome_events(
    uow: TaskUnitOfWork,
    user_id: int,
    provider: str,
    board_id: int | None,
    parent_ids: list[str] | None = None,
) -> None:
    """Etkinlikleri yeni hedef board'a tasir (parent_ids None: saglayicinin hepsi)."""
    if parent_ids is None:
        links = await uow.external_links.list_for_provider(user_id, provider, "event")
    else:
        links = []
        for parent_id in parent_ids:
            links.extend(
                await uow.external_links.for_parent(
                    user_id, provider, "event", parent_id
                )
            )
    for link in links:
        event = await uow.events.get_by_id(link.entity_id)
        if event is not None:
            event.board_id = board_id


async def upsert_external_event(
    uow: TaskUnitOfWork,
    *,
    user_id: int,
    provider: str,
    parent_id: str,
    ext: str,
    board_id: int | None,
    mapped: MappedEvent,
    etag: str | None,
    result: SyncResult,
    link: ExternalLinkEntity | None = None,
) -> None:
    """Dis etkinligi olusturur/gunceller; etag ve board ayniysa atlar (idempotent)."""
    if link is None:
        link = await uow.external_links.get_by_external(user_id, provider, "event", ext)
    now = datetime.now(UTC)

    event = await uow.events.get_by_id(link.entity_id) if link else None
    if event is not None and link is not None:
        if link.etag == etag and event.board_id == board_id:
            link.last_synced_at = now
            return
        fill_event(event, mapped, board_id)
        link.etag = etag
        link.url = mapped.url
        link.last_synced_at = now
        result.updated += 1
        return

    event = EventEntity(user_id=user_id, created_by="integration")
    fill_event(event, mapped, board_id)
    await uow.events.create(event)
    await uow.flush()
    if link is None:
        await uow.external_links.create(
            ExternalLinkEntity(
                user_id=user_id,
                provider=provider,
                entity_type="event",
                entity_id=event.id,
                external_id=ext,
                external_parent_id=parent_id,
                etag=etag,
                url=mapped.url,
                last_synced_at=now,
            )
        )
    else:  # yerelde silinmis (ornegin board silindi): baglanti yeni etkinlige
        link.entity_id = event.id
        link.etag = etag
        link.url = mapped.url
        link.last_synced_at = now
    result.created += 1


async def delete_unseen_in_window(
    uow: TaskUnitOfWork,
    *,
    user_id: int,
    provider: str,
    parent_id: str,
    seen: set[str],
    result: SyncResult,
    window_start: datetime | None = None,
) -> None:
    """
    Tam senkronda gorunmeyen etkinlikleri siler. `window_start` verilirse
    ondan once baslayan (gecmis) etkinliklere dokunulmaz.
    """
    for link in await uow.external_links.for_parent(
        user_id, provider, "event", parent_id
    ):
        if link.external_id in seen:
            continue
        if window_start is not None:
            event = await uow.events.get_by_id(link.entity_id)
            if event is not None and event.start_at < window_start:
                continue
        await delete_linked_event(uow, link)
        result.removed += 1
