"""
Kart is mantigi: olusturma, guncelleme, tasima, notlar, checklist.

Durum senkronu kurallari:
- Kart 'tamamlandi' listesine (is_done_list) girerse -> status=completed,
  completed_at=simdi
- Oradan cikarsa -> status=pending, completed_at=None
- status=completed olarak guncellenirse ve board'da tamamlandi listesi varsa kart
  oraya tasinir; tekrar acilirsa ilk normal listeye doner.
"""

from datetime import UTC, datetime
from typing import Any

from app.core.cache import redis_cache
from app.core.cache_keys import get_task_user_pattern
from app.core.events import domain_event_publisher
from app.core.exceptions import NotFoundException, ValidationException
from app.core.logging import get_logger
from app.db.entities import (
    BoardListEntity,
    CardNoteEntity,
    ChecklistItemEntity,
    TaskEntity,
)
from app.db.unit_of_work import TaskUnitOfWork
from app.models.card import (
    ActivityResponse,
    CardCreate,
    CardDetail,
    CardRef,
    CardSummary,
    CardUpdate,
    ChecklistItemCreate,
    ChecklistItemResponse,
    ChecklistItemUpdate,
    NoteCreate,
    NoteResponse,
    NoteUpdate,
)
from app.models.task import TaskStatus
from app.services.activity import ActivityLogger, diff
from app.services.board import BoardService
from app.services.ordering import STEP, place_at

logger = get_logger(__name__)


class CardService:
    def __init__(self, uow: TaskUnitOfWork, actor: str = "user"):
        self.uow = uow
        self.actor = actor
        self.activity = ActivityLogger(uow, actor)
        self.boards = BoardService(uow)

    @property
    def graph(self):
        from app.services.card_graph import CardGraphService

        return CardGraphService(self.uow, self, self.actor)

    # ---------------- yardimcilar ----------------
    async def get_owned_card(self, card_id: int, user_id: int) -> TaskEntity:
        card = await self.uow.tasks.get_owned(card_id, user_id)
        if card is None:
            raise NotFoundException("Card", card_id)
        return card

    @staticmethod
    def _set_completion(card: TaskEntity, done: bool) -> None:
        if done:
            card.status = TaskStatus.COMPLETED
            if card.completed_at is None:
                card.completed_at = datetime.now(UTC)
        else:
            if card.status == TaskStatus.COMPLETED:
                card.status = TaskStatus.PENDING
            card.completed_at = None

    async def _validate_labels(
        self, board_id: int | None, label_ids: list[int]
    ) -> None:
        if not label_ids:
            return
        labels = await self.uow.labels.get_many(label_ids)
        if len(labels) != len(set(label_ids)) or any(
            lb.board_id != board_id for lb in labels
        ):
            raise ValidationException("Etiketler kartın board'una ait olmalı")

    async def _after_change(self, user_id: int, event: str, card: TaskEntity) -> None:
        """Commit sonrasi: eski /tasks cache'ini temizle + event yayinla."""
        await redis_cache.delete_pattern(get_task_user_pattern(user_id))
        await domain_event_publisher.publish(
            event,
            {
                "card_id": card.id,
                "user_id": user_id,
                "board_id": card.board_id,
                "list_id": card.list_id,
                "status": card.status.value,
                "actor": self.actor,
            },
        )
        if event == "card.completed":
            await self.graph.handle_completion(user_id, card)

    async def summaries(self, cards: list[TaskEntity]) -> list[CardSummary]:
        ids = [c.id for c in cards]
        labels = await self.uow.card_labels.label_ids_for_cards(ids)
        progress = await self.uow.checklist.progress_for_cards(ids)
        notes = await self.uow.notes.counts_for_cards(ids)

        # Bagimliliklar: bitmemis on kosulu olan kart 'blocked'
        edges = await self.uow.dependencies.edges_touching(ids)
        prereq_ids = {d for c, d in edges}
        prereq_status = {
            t.id: t.status for t in await self.uow.tasks.get_many(list(prereq_ids))
        }
        open_prereqs: dict[int, int] = {}
        for card_id, dep_id in edges:
            if prereq_status.get(dep_id, TaskStatus.COMPLETED) != TaskStatus.COMPLETED:
                open_prereqs[card_id] = open_prereqs.get(card_id, 0) + 1

        # Alt kart roll-up
        rollup: dict[int, list[int]] = {}  # parent -> [toplam, biten, dakika]
        children = await self.uow.tasks.children_of(ids)
        tracked = await self.uow.time_sessions.totals_for_cards(
            ids + [ch.id for ch in children]
        )
        sub_tracked: dict[int, int] = {}
        for child in children:
            sub_tracked[child.parent_id] = sub_tracked.get(  # type: ignore[index]
                child.parent_id,
                0,  # type: ignore[arg-type]
            ) + tracked.get(child.id, 0)
        for child in children:
            r = rollup.setdefault(child.parent_id, [0, 0, 0])  # type: ignore[arg-type]
            r[0] += 1
            r[1] += child.status == TaskStatus.COMPLETED
            r[2] += child.estimated_minutes or 0

        result = []
        for c in cards:
            total, done = progress.get(c.id, (0, 0))
            sub_total, sub_done, sub_minutes = rollup.get(c.id, [0, 0, 0])
            result.append(
                CardSummary.model_validate(c).model_copy(
                    update={
                        "has_description": bool(c.description),
                        "label_ids": labels.get(c.id, []),
                        "checklist_total": total,
                        "checklist_done": done,
                        "note_count": notes.get(c.id, 0),
                        "blocked": open_prereqs.get(c.id, 0) > 0
                        and c.status != TaskStatus.COMPLETED,
                        "blocked_by_count": open_prereqs.get(c.id, 0),
                        "tracked_seconds": tracked.get(c.id, 0),
                        "subtask_tracked_seconds": sub_tracked.get(c.id, 0),
                        "subtask_total": sub_total,
                        "subtask_done": sub_done,
                        "subtask_estimated_minutes": sub_minutes,
                    }
                )
            )
        return result

    async def _move_into(
        self, card: TaskEntity, target: BoardListEntity, index: int | None
    ) -> None:
        """Karti hedef listeye (index None ise sona) yerlestirir, durumu senkronlar."""
        siblings = [
            c for c in await self.uow.tasks.list_in_list(target.id) if c.id != card.id
        ]
        card.list_id = target.id
        card.board_id = target.board_id
        place_at(siblings, card, len(siblings) if index is None else index)
        self._set_completion(card, target.is_done_list)

    # ---------------- kart ----------------
    async def create(self, user_id: int, data: CardCreate) -> CardDetail:
        parent = None
        if data.parent_id is not None:
            parent = await self.graph.validate_parent(None, data.parent_id, user_id)
        list_id = (
            data.list_id
            if data.list_id is not None
            else (parent.list_id if parent else None)
        )
        if list_id is None:
            raise ValidationException(
                "list_id ya da listesi olan bir parent_id gerekli"
            )
        lst = await self.boards.get_owned_list(list_id, user_id)
        await self._validate_labels(lst.board_id, data.label_ids)

        card = TaskEntity(
            user_id=user_id,
            board_id=lst.board_id,
            list_id=lst.id,
            position=await self.uow.tasks.max_position_in_list(lst.id) + STEP,
            status=TaskStatus.PENDING,
            created_by=self.actor,
            **data.model_dump(exclude={"list_id", "label_ids"}),
        )
        self._set_completion(card, lst.is_done_list)
        await self.uow.tasks.create(card)
        await self.uow.flush()
        await self.uow.card_labels.set_for_card(card.id, data.label_ids)
        await self.activity.log(
            user_id,
            "card",
            card.id,
            "created",
            board_id=card.board_id,
            card_id=card.id,
            changes={
                "title": card.title,
                "list_id": lst.id,
                "estimated_minutes": card.estimated_minutes,
            },
        )
        await self.uow.commit()
        await self._after_change(user_id, "card.created", card)
        return await self.get_detail(card.id, user_id)

    async def get_detail(self, card_id: int, user_id: int) -> CardDetail:
        card = await self.get_owned_card(card_id, user_id)
        summary = (await self.summaries([card]))[0]
        notes = await self.uow.notes.list_for_card(card.id)
        checklist = await self.uow.checklist.list_for_card(card.id)
        parent = (
            await self.uow.tasks.get_by_id(card.parent_id) if card.parent_id else None
        )
        subtasks = await self.uow.tasks.children_of([card.id])
        edges = await self.uow.dependencies.edges_touching([card.id])
        related = {
            t.id: t
            for t in await self.uow.tasks.get_many([x for e in edges for x in e])
        }
        depends_on = [related[d] for c, d in edges if c == card.id and d in related]
        dependents = [related[c] for c, d in edges if d == card.id and c in related]
        return CardDetail(
            **summary.model_dump(),
            user_id=card.user_id,
            description=card.description,
            created_by=card.created_by,
            created_at=card.created_at,
            updated_at=card.updated_at,
            notes=[NoteResponse.model_validate(n) for n in notes],
            checklist=[ChecklistItemResponse.model_validate(i) for i in checklist],
            parent=CardRef.model_validate(parent) if parent else None,
            subtasks=await self.summaries(subtasks),
            depends_on=[CardRef.model_validate(t) for t in depends_on],
            dependents=[CardRef.model_validate(t) for t in dependents],
        )

    @staticmethod
    def _action_for(changes: dict[str, Any]) -> str:
        """Degisikliklerden en anlamli eylem adini secer (istatistik icin)."""
        if "status" in changes:
            new = changes["status"][1]
            if new == TaskStatus.COMPLETED.value:
                return "completed"
            if changes["status"][0] == TaskStatus.COMPLETED.value:
                return "reopened"
        if "is_archived" in changes:
            return "archived" if changes["is_archived"][1] else "unarchived"
        if "due_date" in changes or "start_at" in changes:
            return "rescheduled"
        if "estimated_minutes" in changes:
            return "estimate_changed"
        return "updated"

    async def update(self, card_id: int, user_id: int, data: CardUpdate) -> CardDetail:
        card = await self.get_owned_card(card_id, user_id)
        update = data.model_dump(exclude_unset=True)
        label_ids = update.pop("label_ids", None)
        new_status = update.pop("status", None)

        if update.get("parent_id") is not None:
            await self.graph.validate_parent(card, update["parent_id"], user_id)
        if update.get("assigned_to") not in (None, user_id):
            raise ValidationException("Kart şimdilik sadece kendine atanabilir")
        # Grafik konumu degisikligi gecmise yazilmaya degmez
        layout_only = set(update) <= {"graph_x", "graph_y"} and not label_ids

        changes = diff(card, update)
        for key, value in update.items():
            setattr(card, key, value)

        if new_status is not None and new_status != card.status:
            changes["status"] = [card.status.value, new_status.value]
            await self._apply_status(card, new_status)

        if label_ids is not None:
            await self._validate_labels(card.board_id, label_ids)
            await self.uow.card_labels.set_for_card(card.id, label_ids)
            changes["label_ids"] = [None, label_ids]

        if changes and not layout_only:
            await self.activity.log(
                user_id,
                "card",
                card.id,
                self._action_for(changes),
                board_id=card.board_id,
                card_id=card.id,
                changes=changes,
            )
        await self.uow.commit()
        event = (
            "card.completed"
            if self._action_for(changes) == "completed"
            else "card.updated"
        )
        await self._after_change(user_id, event, card)
        return await self.get_detail(card.id, user_id)

    async def _apply_status(self, card: TaskEntity, status: TaskStatus) -> None:
        """status alanini degistirir; gerekirse karti done/normal listeye tasir."""
        lists = (
            await self.uow.lists.list_for_board(card.board_id) if card.board_id else []
        )
        current = next((lst for lst in lists if lst.id == card.list_id), None)
        if status == TaskStatus.COMPLETED:
            target = next((lst for lst in lists if lst.is_done_list), None)
            if target and (current is None or not current.is_done_list):
                await self._move_into(card, target, None)
            self._set_completion(card, True)
        else:
            if current is not None and current.is_done_list:
                target = next((lst for lst in lists if not lst.is_done_list), None)
                if target:
                    await self._move_into(card, target, None)
            self._set_completion(card, False)
            card.status = status

    async def move(
        self, card_id: int, user_id: int, list_id: int, index: int
    ) -> CardDetail:
        card = await self.get_owned_card(card_id, user_id)
        target = await self.boards.get_owned_list(list_id, user_id)

        def snapshot() -> dict[str, Any]:
            return {
                "list_id": card.list_id,
                "board_id": card.board_id,
                "status": card.status.value,
            }

        before = snapshot()
        if target.board_id != card.board_id:
            # Etiketler board'a ozel; baska board'a tasinan kartin etiketleri dusur
            await self.uow.card_labels.set_for_card(card.id, [])
        await self._move_into(card, target, index)
        after = snapshot()

        changes = {k: [before[k], after[k]] for k in before if before[k] != after[k]}
        action = self._action_for(changes) if "status" in changes else "moved"
        if changes:
            await self.activity.log(
                user_id,
                "card",
                card.id,
                action,
                board_id=card.board_id,
                card_id=card.id,
                changes=changes,
            )
        await self.uow.commit()
        await self._after_change(
            user_id, "card.completed" if action == "completed" else "card.moved", card
        )
        return await self.get_detail(card.id, user_id)

    async def delete(self, card_id: int, user_id: int) -> None:
        card = await self.get_owned_card(card_id, user_id)
        await self.activity.log(
            user_id,
            "card",
            card.id,
            "deleted",
            board_id=card.board_id,
            card_id=card.id,
            changes={"title": card.title},
        )
        await self.uow.card_labels.set_for_card(card.id, [])
        await self.uow.notes.delete_for_card(card.id)
        await self.uow.checklist.delete_for_card(card.id)
        await self.uow.dependencies.delete_for_card(card.id)
        await self.uow.day_plan_items.detach_card(card.id)
        await self.uow.events.delete_for_card(card.id)
        await self.uow.time_sessions.detach_card(card.id)
        await self.uow.tasks.detach_children(card.id)
        await self.uow.tasks.delete(card)
        await self.uow.commit()
        await redis_cache.delete_pattern(get_task_user_pattern(user_id))
        await domain_event_publisher.publish(
            "card.deleted",
            {"card_id": card_id, "user_id": user_id, "actor": self.actor},
        )

    async def activity_for(self, card_id: int, user_id: int) -> list[ActivityResponse]:
        # Silinmis kartin gecmisi de okunabilsin diye sahiplik activity kaydindan
        rows = await self.uow.activity.for_card(user_id, card_id)
        if not rows:
            await self.get_owned_card(card_id, user_id)  # yoksa 404
        return [ActivityResponse.model_validate(r) for r in rows]

    # ---------------- not ----------------
    async def add_note(
        self, card_id: int, user_id: int, data: NoteCreate
    ) -> NoteResponse:
        card = await self.get_owned_card(card_id, user_id)
        note = CardNoteEntity(user_id=user_id, card_id=card.id, content=data.content)
        await self.uow.notes.create(note)
        await self.uow.flush()
        await self.activity.log(
            user_id, "note", note.id, "created", board_id=card.board_id, card_id=card.id
        )
        await self.uow.commit()
        return NoteResponse.model_validate(note)

    async def _owned_note(self, note_id: int, user_id: int) -> CardNoteEntity:
        note = await self.uow.notes.get_owned(note_id, user_id)
        if note is None:
            raise NotFoundException("Note", note_id)
        return note

    async def update_note(
        self, note_id: int, user_id: int, data: NoteUpdate
    ) -> NoteResponse:
        note = await self._owned_note(note_id, user_id)
        note.content = data.content
        await self.uow.commit()
        return NoteResponse.model_validate(note)

    async def delete_note(self, note_id: int, user_id: int) -> None:
        note = await self._owned_note(note_id, user_id)
        await self.uow.notes.delete(note)
        await self.uow.commit()

    # ---------------- checklist ----------------
    async def add_checklist_item(
        self, card_id: int, user_id: int, data: ChecklistItemCreate
    ) -> ChecklistItemResponse:
        card = await self.get_owned_card(card_id, user_id)
        item = ChecklistItemEntity(
            user_id=user_id,
            card_id=card.id,
            text=data.text,
            position=await self.uow.checklist.max_position(card.id) + STEP,
        )
        await self.uow.checklist.create(item)
        await self.uow.commit()
        return ChecklistItemResponse.model_validate(item)

    async def _owned_item(self, item_id: int, user_id: int) -> ChecklistItemEntity:
        item = await self.uow.checklist.get_owned(item_id, user_id)
        if item is None:
            raise NotFoundException("ChecklistItem", item_id)
        return item

    async def update_checklist_item(
        self, item_id: int, user_id: int, data: ChecklistItemUpdate
    ) -> ChecklistItemResponse:
        item = await self._owned_item(item_id, user_id)
        update = data.model_dump(exclude_unset=True)
        toggled = "is_done" in update and update["is_done"] != item.is_done
        for key, value in update.items():
            setattr(item, key, value)
        if toggled:
            card = await self.get_owned_card(item.card_id, user_id)
            await self.activity.log(
                user_id,
                "checklist_item",
                item.id,
                "checked" if item.is_done else "unchecked",
                board_id=card.board_id,
                card_id=card.id,
            )
        await self.uow.commit()
        return ChecklistItemResponse.model_validate(item)

    async def delete_checklist_item(self, item_id: int, user_id: int) -> None:
        item = await self._owned_item(item_id, user_id)
        await self.uow.checklist.delete(item)
        await self.uow.commit()
