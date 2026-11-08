"""
Trello tek seferlik import (Faz 7a).

Katmanlar:
- TrelloClient: ince httpx sarmalayici (API key + token, salt okunur).
- map_board(): Trello JSON'unu agdan bagimsiz, saf bir yapiya cevirir (kolay test).
- TrelloService: baglanti/dogrulama, board listesi, import (idempotent).

Idempotent kural: her nesne external_links'e yazilir; tekrar import mevcutlari
ATLAR (guncellemez), sadece yeni olanlari ekler. Tek transaction / board.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.exceptions import NotFoundException, ValidationException
from app.core.logging import get_logger
from app.db.entities import (
    BoardEntity,
    BoardListEntity,
    CardNoteEntity,
    ChecklistItemEntity,
    ExternalLinkEntity,
    LabelEntity,
    TaskEntity,
)
from app.db.unit_of_work import TaskUnitOfWork
from app.integrations.accounts import IntegrationAccountService
from app.integrations.base import IntegrationError, lock_for
from app.models.task import TaskPriority, TaskStatus
from app.services.activity import ActivityLogger
from app.services.card import CardService
from app.services.ordering import STEP

# Trello key/token sorgu parametresi olarak gider: httpx'in INFO kayitlari URL'yi
# (yani gizli degerleri) yazar. Seviyeyi yukselt.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = get_logger(__name__)

PROVIDER = "trello"
API_BASE = "https://api.trello.com/1"
# Testlerde sahte ag icin degistirilir (httpx.MockTransport)
HTTP_TRANSPORT: httpx.AsyncBaseTransport | None = None

DONE_LIST_NAMES = {
    "done",
    "bitti",
    "bitenler",
    "tamamlandı",
    "tamamlandi",
    "tamamlanan",
    "tamamlananlar",
}
BOARD_PALETTE = [
    "#64748b",
    "#ef4444",
    "#f97316",
    "#eab308",
    "#22c55e",
    "#14b8a6",
    "#3b82f6",
    "#6366f1",
    "#a855f7",
    "#ec4899",
]
TRELLO_BACKGROUNDS = {
    "blue": "#3b82f6",
    "orange": "#f97316",
    "green": "#22c55e",
    "red": "#ef4444",
    "purple": "#a855f7",
    "pink": "#ec4899",
    "lime": "#22c55e",
    "sky": "#3b82f6",
    "grey": "#64748b",
}
LABEL_COLORS = {
    "green": "#22c55e",
    "yellow": "#eab308",
    "orange": "#f97316",
    "red": "#ef4444",
    "purple": "#a855f7",
    "blue": "#3b82f6",
    "sky": "#38bdf8",
    "lime": "#84cc16",
    "pink": "#ec4899",
    "black": "#1e293b",
}


# ====================================================================
# Istemci
# ====================================================================
class TrelloClient:
    def __init__(self, api_key: str, token: str):
        self._auth = {"key": api_key, "token": token}

    async def _get(self, path: str, **params: Any) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=API_BASE, timeout=20, transport=HTTP_TRANSPORT
            ) as http:
                res = await http.get(path, params={**self._auth, **params})
        except httpx.HTTPError as e:
            raise IntegrationError(
                "Trello'ya ulaşılamadı; bağlantını kontrol edip tekrar dene.",
                "TRELLO_UNREACHABLE",
            ) from e
        if res.status_code in (400, 401, 403):
            raise IntegrationError(
                "Trello API anahtarı ya da token geçersiz (ya da yetkisi yok).",
                "TRELLO_AUTH_FAILED",
                status_code=422,
            )
        if res.status_code == 404:
            raise IntegrationError(
                "Trello'da bulunamadı.", "TRELLO_NOT_FOUND", status_code=404
            )
        if res.status_code == 429:
            raise IntegrationError(
                "Trello istek sınırına takıldı; biraz sonra tekrar dene.",
                "TRELLO_RATE_LIMITED",
                status_code=429,
            )
        if res.status_code >= 400:
            raise IntegrationError(f"Trello hata verdi ({res.status_code}).")
        return res.json()

    async def me(self) -> dict[str, Any]:
        return await self._get("/members/me", fields="fullName,username")

    async def open_boards(self) -> list[dict[str, Any]]:
        return await self._get(
            "/members/me/boards", filter="open", fields="name,url,closed"
        )

    async def board_full(self, board_id: str) -> dict[str, Any]:
        return await self._get(
            f"/boards/{board_id}",
            lists="open",
            cards="open",
            card_checklists="all",
            labels="all",
            actions="commentCard",
            actions_limit=1000,
            card_attachments="true",
        )


# ====================================================================
# Esleme (saf fonksiyonlar)
# ====================================================================
@dataclass
class MappedChecklistItem:
    id: str
    text: str
    done: bool
    pos: float


@dataclass
class MappedNote:
    id: str
    content: str
    created_at: datetime | None


@dataclass
class MappedLabel:
    id: str
    name: str
    color: str


@dataclass
class MappedCard:
    id: str
    list_id: str
    title: str
    description: str | None
    due: datetime | None
    due_complete: bool
    pos: float
    url: str | None
    label_ids: list[str] = field(default_factory=list)
    checklist: list[MappedChecklistItem] = field(default_factory=list)
    notes: list[MappedNote] = field(default_factory=list)


@dataclass
class MappedList:
    id: str
    name: str
    pos: float
    is_done: bool


@dataclass
class MappedBoard:
    id: str
    name: str
    description: str | None
    color: str
    url: str | None
    lists: list[MappedList]
    cards: list[MappedCard]
    labels: list[MappedLabel]


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _nearest_palette(hex_color: str) -> str:
    def rgb(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    try:
        r, g, b = rgb(hex_color)
    except (ValueError, IndexError):
        return BOARD_PALETTE[0]
    return min(
        BOARD_PALETTE,
        key=lambda p: sum((a - c) ** 2 for a, c in zip(rgb(p), (r, g, b), strict=True)),
    )


def map_board_color(prefs: dict[str, Any] | None) -> str:
    """Trello rengini (ad ya da hex) uygulamanin paletindeki en yakin renge cevirir."""
    prefs = prefs or {}
    name = prefs.get("background")
    if isinstance(name, str) and name in TRELLO_BACKGROUNDS:
        return TRELLO_BACKGROUNDS[name]
    hex_color = prefs.get("backgroundColor") or (
        name if isinstance(name, str) and name.startswith("#") else None
    )
    if isinstance(hex_color, str) and hex_color.startswith("#") and len(hex_color) == 7:
        return _nearest_palette(hex_color)
    return BOARD_PALETTE[0]


def is_done_list_name(name: str) -> bool:
    return name.strip().casefold() in DONE_LIST_NAMES


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    text = text.strip()
    return text[:limit] if text else None


def map_board(data: dict[str, Any]) -> MappedBoard:
    """Trello board JSON'u -> MappedBoard. Arsivli liste/kart alinmaz."""
    lists = [
        MappedList(
            id=item["id"],
            name=_clip(item.get("name"), 100) or "Liste",
            pos=float(item.get("pos") or 0),
            is_done=is_done_list_name(item.get("name") or ""),
        )
        for item in data.get("lists", [])
        if not item.get("closed")
    ]
    lists.sort(key=lambda x: x.pos)
    list_ids = {item.id for item in lists}

    labels = []
    for item in data.get("labels", []):
        color_name = item.get("color")
        name = _clip(item.get("name"), 50) or (color_name or "")
        if not name:
            continue
        labels.append(
            MappedLabel(
                id=item["id"],
                name=name,
                color=LABEL_COLORS.get(color_name or "", "#64748b"),
            )
        )

    # Yorumlar: kartin id'sine gore grupla, eskiden yeniye
    comments: dict[str, list[MappedNote]] = {}
    for action in data.get("actions", []):
        if action.get("type") != "commentCard":
            continue
        card_id = (action.get("data", {}).get("card") or {}).get("id")
        text = _clip(action.get("data", {}).get("text"), 19000)
        if not card_id or not text:
            continue
        author = (action.get("memberCreator") or {}).get("fullName") or "?"
        created = parse_dt(action.get("date"))
        stamp = created.date().isoformat() if created else ""
        comments.setdefault(card_id, []).append(
            MappedNote(
                id=action["id"],
                content=f"{author}, {stamp}: {text}",
                created_at=created,
            )
        )

    board_level_checklists: dict[str, list[dict[str, Any]]] = {}
    for cl in data.get("checklists", []):
        board_level_checklists.setdefault(cl.get("idCard", ""), []).append(cl)

    cards = []
    for item in data.get("cards", []):
        if item.get("closed") or item["idList"] not in list_ids:
            continue
        description = item.get("desc") or ""
        attachments = [
            a for a in item.get("attachments", []) if a.get("url")
        ]
        if attachments:
            links = "\n".join(
                f"- [{a.get('name') or a['url']}]({a['url']})" for a in attachments
            )
            description = f"{description.rstrip()}\n\n**Ekler**\n{links}".strip()

        checklists = item.get("checklists") or board_level_checklists.get(
            item["id"], []
        )
        multiple = len(checklists) > 1
        checklist_items: list[MappedChecklistItem] = []
        for cl in sorted(checklists, key=lambda c: c.get("pos") or 0):
            for ci in sorted(cl.get("checkItems", []), key=lambda c: c.get("pos") or 0):
                text = _clip(ci.get("name"), 500)
                if not text:
                    continue
                if multiple and cl.get("name"):
                    text = f"{cl['name']}: {text}"[:500]
                checklist_items.append(
                    MappedChecklistItem(
                        id=ci["id"],
                        text=text,
                        done=ci.get("state") == "complete",
                        pos=float(ci.get("pos") or 0),
                    )
                )

        cards.append(
            MappedCard(
                id=item["id"],
                list_id=item["idList"],
                title=_clip(item.get("name"), 200) or "(adsız)",
                description=_clip(description, 20000),
                due=parse_dt(item.get("due")),
                due_complete=bool(item.get("dueComplete")),
                pos=float(item.get("pos") or 0),
                url=item.get("shortUrl") or item.get("url"),
                label_ids=list(item.get("idLabels") or []),
                checklist=checklist_items,
                notes=sorted(
                    comments.get(item["id"], []),
                    key=lambda n: n.created_at or datetime.min.replace(tzinfo=UTC),
                ),
            )
        )

    return MappedBoard(
        id=data["id"],
        name=_clip(data.get("name"), 100) or "Trello board",
        description=_clip(data.get("desc"), 5000),
        color=map_board_color(data.get("prefs")),
        url=data.get("url"),
        lists=lists,
        cards=cards,
        labels=labels,
    )


# ====================================================================
# API modelleri
# ====================================================================
class TrelloConnect(BaseModel):
    api_key: str = Field(..., min_length=8, max_length=200)
    token: str = Field(..., min_length=8, max_length=500)


class TrelloBoardInfo(BaseModel):
    id: str
    name: str
    url: str | None = None
    already_imported: bool = False


class TrelloImportRequest(BaseModel):
    board_ids: list[str] = Field(..., min_length=1, max_length=50)


class TrelloImportResult(BaseModel):
    trello_board_id: str
    name: str
    board_id: int | None = None
    created_board: bool = False
    lists: int = 0
    cards: int = 0
    checklist_items: int = 0
    notes: int = 0
    skipped_cards: int = 0
    error: str | None = None


# ====================================================================
# Servis
# ====================================================================
class TrelloService:
    def __init__(self, uow: TaskUnitOfWork):
        self.uow = uow
        self.accounts = IntegrationAccountService(uow)

    async def _client(self, user_id: int) -> TrelloClient:
        account = await self.accounts.get(user_id, PROVIDER)
        tokens = self.accounts.tokens(account)
        return TrelloClient(tokens["api_key"], tokens["token"])

    async def connect(self, user_id: int, data: TrelloConnect):
        me = await TrelloClient(data.api_key, data.token).me()
        label = me.get("fullName") or me.get("username")
        account = await self.accounts.save(
            user_id,
            PROVIDER,
            {"api_key": data.api_key, "token": data.token},
            account_label=label,
            scopes="read",
        )
        return account

    async def list_boards(self, user_id: int) -> list[TrelloBoardInfo]:
        client = await self._client(user_id)
        remote = await client.open_boards()
        imported = await self._imported_board_ids(user_id)
        return [
            TrelloBoardInfo(
                id=b["id"],
                name=b.get("name") or "",
                url=b.get("url"),
                already_imported=b["id"] in imported,
            )
            for b in remote
            if not b.get("closed")
        ]

    async def _imported_board_ids(self, user_id: int) -> set[str]:
        """Yerelde hala var olan board'larin Trello id'leri."""
        ids = set()
        for ext_id in await self.uow.external_links.external_ids(
            user_id, PROVIDER, "board"
        ):
            link = await self.uow.external_links.get_by_external(
                user_id, PROVIDER, "board", ext_id
            )
            if link and await self.uow.boards.get_owned(link.entity_id, user_id):
                ids.add(ext_id)
        return ids

    async def import_boards(
        self, user_id: int, board_ids: list[str]
    ) -> list[TrelloImportResult]:
        client = await self._client(user_id)
        allowed = {b["id"] for b in await client.open_boards()}
        unknown = [b for b in board_ids if b not in allowed]
        if unknown:
            raise NotFoundException("Trello board", unknown[0])
        if len(set(board_ids)) != len(board_ids):
            raise ValidationException("Aynı board birden fazla kez seçilmiş")

        results = []
        async with lock_for(user_id, PROVIDER):
            for trello_id in board_ids:
                data = await client.board_full(trello_id)
                mapped = map_board(data)
                try:
                    result = await TrelloImporter(self.uow, user_id).import_board(
                        mapped
                    )
                except Exception as e:  # tek board hatasi digerlerini durdurmasin
                    await self.uow.rollback()
                    logger.exception("Trello import failed for board %s", trello_id)
                    result = TrelloImportResult(
                        trello_board_id=trello_id,
                        name=mapped.name,
                        error=f"İçe aktarılamadı: {type(e).__name__}",
                    )
                results.append(result)

            account = await self.accounts.get(user_id, PROVIDER)
            account.last_synced_at = datetime.now(UTC)
            account.last_error = None
            await self.uow.session.commit()
        return results


class TrelloImporter:
    """Tek board'u tek transaction'da yerel veritabanina yazar."""

    def __init__(self, uow: TaskUnitOfWork, user_id: int):
        self.uow = uow
        self.user_id = user_id
        self.activity = ActivityLogger(uow, "integration")
        self.now = datetime.now(UTC)

    async def _link(
        self,
        entity_type: str,
        entity_id: int,
        external_id: str,
        *,
        parent: str | None = None,
        url: str | None = None,
    ) -> None:
        await self.uow.external_links.create(
            ExternalLinkEntity(
                user_id=self.user_id,
                provider=PROVIDER,
                entity_type=entity_type,
                entity_id=entity_id,
                external_id=external_id,
                external_parent_id=parent,
                url=url,
                last_synced_at=self.now,
            )
        )

    async def _existing(
        self, entity_type: str, external_id: str
    ) -> ExternalLinkEntity | None:
        return await self.uow.external_links.get_by_external(
            self.user_id, PROVIDER, entity_type, external_id
        )

    async def import_board(self, mb: MappedBoard) -> TrelloImportResult:
        uid = self.user_id
        result = TrelloImportResult(trello_board_id=mb.id, name=mb.name)

        # ---- board ----
        board: BoardEntity | None = None
        board_link = await self._existing("board", mb.id)
        if board_link is not None:
            board = await self.uow.boards.get_owned(board_link.entity_id, uid)
            if board is None:  # yerelde silinmis: eski baglantilari at, bastan kur
                await self.uow.external_links.delete_children(uid, PROVIDER, mb.id)
                await self.uow.external_links.delete(board_link)
                await self.uow.flush()
        if board is None:
            board = BoardEntity(
                user_id=uid,
                name=mb.name,
                scope_description=mb.description,
                color=mb.color,
                position=await self.uow.boards.max_position(uid) + STEP,
            )
            await self.uow.boards.create(board)
            await self.uow.flush()
            await self._link("board", board.id, mb.id, url=mb.url)
            await self.activity.log(
                uid,
                "board",
                board.id,
                "created",
                board_id=board.id,
                changes={"name": board.name, "source": "trello"},
            )
            result.created_board = True
        result.board_id = board.id

        # ---- listeler ----
        local_lists: dict[str, BoardListEntity] = {}
        existing_lists = await self.uow.lists.list_for_board(board.id)
        next_pos = (existing_lists[-1].position if existing_lists else 0) + STEP
        for ml in mb.lists:
            link = await self._existing("list", ml.id)
            lst = (
                await self.uow.lists.get_owned(link.entity_id, uid) if link else None
            )
            if lst is not None and lst.board_id == board.id:
                local_lists[ml.id] = lst
                continue
            if link is not None:  # yerelde silinmis liste: baglantiyi yenile
                await self.uow.external_links.delete(link)
                await self.uow.flush()
            lst = BoardListEntity(
                user_id=uid,
                board_id=board.id,
                name=ml.name,
                position=next_pos,
                is_done_list=ml.is_done,
            )
            next_pos += STEP
            await self.uow.lists.create(lst)
            await self.uow.flush()
            await self._link("list", lst.id, ml.id, parent=mb.id)
            local_lists[ml.id] = lst
            result.lists += 1

        # ---- etiketler ----
        board_labels = {
            lb.name: lb for lb in await self.uow.labels.list_for_board(board.id)
        }
        local_labels: dict[str, LabelEntity] = {}
        for label in mb.labels:
            lb = board_labels.get(label.name)
            if lb is None:
                lb = LabelEntity(
                    user_id=uid, board_id=board.id, name=label.name, color=label.color
                )
                await self.uow.labels.create(lb)
                await self.uow.flush()
                board_labels[label.name] = lb
            local_labels[label.id] = lb

        # ---- kartlar ----
        list_order = {ml.id: i for i, ml in enumerate(mb.lists)}
        positions: dict[int, float] = {}
        for mc in sorted(mb.cards, key=lambda c: (list_order[c.list_id], c.pos)):
            lst = local_lists[mc.list_id]
            link = await self._existing("card", mc.id)
            card = (
                await self.uow.tasks.get_owned(link.entity_id, uid) if link else None
            )
            if link is not None:
                result.skipped_cards += 1
                if card is None:  # kullanici sildi: tekrar getirme
                    continue
            else:
                if lst.id not in positions:
                    positions[lst.id] = await self.uow.tasks.max_position_in_list(
                        lst.id
                    )
                positions[lst.id] += STEP
                card = TaskEntity(
                    user_id=uid,
                    board_id=board.id,
                    list_id=lst.id,
                    position=positions[lst.id],
                    title=mc.title,
                    description=mc.description,
                    status=TaskStatus.PENDING,
                    priority=TaskPriority.MEDIUM,
                    due_date=mc.due,
                    created_by="integration",
                )
                CardService._set_completion(card, lst.is_done_list or mc.due_complete)
                await self.uow.tasks.create(card)
                await self.uow.flush()
                await self._link("card", card.id, mc.id, parent=mb.id, url=mc.url)
                await self.uow.card_labels.set_for_card(
                    card.id,
                    [local_labels[i].id for i in mc.label_ids if i in local_labels],
                )
                await self.activity.log(
                    uid,
                    "card",
                    card.id,
                    "created",
                    board_id=board.id,
                    card_id=card.id,
                    changes={"title": card.title, "source": "trello"},
                )
                result.cards += 1

            await self._import_children(mb, mc, card, result)

        await self.uow.session.commit()
        return result

    async def _import_children(
        self,
        mb: MappedBoard,
        mc: MappedCard,
        card: TaskEntity,
        result: TrelloImportResult,
    ) -> None:
        """Checklist maddeleri ve yorum-notlar: id'si daha once gorulmeyenler eklenir."""
        uid = self.user_id
        for ci in mc.checklist:
            if await self._existing("checklist_item", ci.id):
                continue
            item = ChecklistItemEntity(
                user_id=uid,
                card_id=card.id,
                text=ci.text,
                is_done=ci.done,
                position=ci.pos or STEP,
            )
            await self.uow.checklist.create(item)
            await self.uow.flush()
            await self._link("checklist_item", item.id, ci.id, parent=mb.id)
            result.checklist_items += 1
        for note in mc.notes:
            if await self._existing("note", note.id):
                continue
            entity = CardNoteEntity(user_id=uid, card_id=card.id, content=note.content)
            if note.created_at:
                entity.created_at = note.created_at
            await self.uow.notes.create(entity)
            await self.uow.flush()
            await self._link("note", entity.id, note.id, parent=mb.id)
            result.notes += 1
