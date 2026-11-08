"""
Kart hiyerarsisi ve bagimliliklari (Faz 1b).

- Bagimlilik: (card_id, depends_on_id) -> card, depends_on bitmeden baslayamaz.
  Grafik DAG tutulur; donguye yol acacak ip 409 DEPENDENCY_CYCLE ile reddedilir.
- Bir kart tamamlaninca butun on kosullari tamamlanan bagimli kartlar
  'unblocked' olur: activity_log kaydi + card.unblocked event'i.
- split: karti N alt karta boler, sureyi dagitir, istenirse sirali iple baglar.
"""

from collections import deque
from typing import TYPE_CHECKING

from app.core.events import domain_event_publisher
from app.core.exceptions import ConflictException, ValidationException
from app.db.entities import CardDependencyEntity, TaskEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.models.card import BoardGraph, CardSplit, GraphEdge
from app.models.task import TaskStatus
from app.services.activity import ActivityLogger
from app.services.ordering import STEP

if TYPE_CHECKING:
    from app.services.card import CardService


def _reachable(edges: list[tuple[int, int]], start: int, goal: int) -> bool:
    """`start`'tan on kosul yonunde ilerleyerek `goal`'a varilabiliyor mu?"""
    graph: dict[int, list[int]] = {}
    for card_id, dep_id in edges:
        graph.setdefault(card_id, []).append(dep_id)
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node == goal:
            return True
        for nxt in graph.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


class CardGraphService:
    def __init__(self, uow: TaskUnitOfWork, cards: "CardService", actor: str = "user"):
        self.uow = uow
        self.cards = cards
        self.actor = actor
        self.activity = ActivityLogger(uow, actor)

    # ---------------- ust kart ----------------
    async def validate_parent(
        self, card: TaskEntity | None, parent_id: int, user_id: int
    ) -> TaskEntity:
        """Ust kart kullaniciya ait mi, dongu olusuyor mu?"""
        parent = await self.cards.get_owned_card(parent_id, user_id)
        if card is not None:
            node: TaskEntity | None = parent
            depth = 0
            while node is not None and depth < 100:
                if node.id == card.id:
                    raise ValidationException("Kart kendisinin alt kartı olamaz")
                node = (
                    await self.uow.tasks.get_by_id(node.parent_id)
                    if node.parent_id
                    else None
                )
                depth += 1
        return parent

    # ---------------- bagimlilik ----------------
    async def add_dependency(
        self, card_id: int, user_id: int, depends_on_id: int
    ) -> None:
        card = await self.cards.get_owned_card(card_id, user_id)
        dep = await self.cards.get_owned_card(depends_on_id, user_id)
        if card.id == dep.id:
            raise ValidationException("Kart kendisine bağımlı olamaz")
        if await self.uow.dependencies.get_edge(card.id, dep.id):
            return  # zaten var (idempotent)
        edges = await self.uow.dependencies.edges_for_user(user_id)
        # dep -> ... -> card yolu varsa card -> dep eklemek dongu yaratir
        if _reachable(edges, dep.id, card.id):
            raise ConflictException(
                "DEPENDENCY_CYCLE",
                f"'{dep.title}' zaten '{card.title}' kartına bağlı; döngü oluşur.",
            )
        await self.uow.dependencies.create(
            CardDependencyEntity(user_id=user_id, card_id=card.id, depends_on_id=dep.id)
        )
        await self.activity.log(
            user_id,
            "card",
            card.id,
            "dependency_added",
            board_id=card.board_id,
            card_id=card.id,
            changes={"depends_on_id": dep.id, "depends_on_title": dep.title},
        )
        await self.uow.commit()

    async def remove_dependency(
        self, card_id: int, user_id: int, depends_on_id: int
    ) -> None:
        card = await self.cards.get_owned_card(card_id, user_id)
        edge = await self.uow.dependencies.get_edge(card.id, depends_on_id)
        if edge is None:
            return
        prereq = await self.uow.tasks.get_by_id(depends_on_id)
        was_blocking = prereq is not None and prereq.status != TaskStatus.COMPLETED
        await self.uow.dependencies.delete(edge)
        await self.activity.log(
            user_id,
            "card",
            card.id,
            "dependency_removed",
            board_id=card.board_id,
            card_id=card.id,
            changes={"depends_on_id": depends_on_id},
        )
        await self.uow.commit()
        # Sadece gercekten engelleyen (bitmemis) ip kalktiysa kart acilmis olabilir;
        # zaten tamamlanmis on kosulun ipini silmek yeni bir "unblocked" degildir.
        if was_blocking:
            await self._publish_unblocked(user_id, [card.id])

    async def handle_completion(self, user_id: int, completed: TaskEntity) -> list[int]:
        """Tamamlanan kartin acabilecegi bagimli kartlari bulur ve bildirir."""
        edges = await self.uow.dependencies.edges_touching([completed.id])
        dependents = [c for c, d in edges if d == completed.id]
        return await self._publish_unblocked(user_id, dependents)

    async def _publish_unblocked(self, user_id: int, card_ids: list[int]) -> list[int]:
        if not card_ids:
            return []
        edges = await self.uow.dependencies.edges_touching(card_ids)
        prereq_ids = {d for c, d in edges if c in card_ids}
        prereqs = {t.id: t for t in await self.uow.tasks.get_many(list(prereq_ids))}
        unblocked: list[TaskEntity] = []
        for card in await self.uow.tasks.get_many(card_ids):
            if card.status == TaskStatus.COMPLETED or card.is_archived:
                continue
            mine = [d for c, d in edges if c == card.id]
            if all(
                prereqs[d].status == TaskStatus.COMPLETED for d in mine if d in prereqs
            ):
                unblocked.append(card)
        for card in unblocked:
            await self.activity.log(
                user_id,
                "card",
                card.id,
                "unblocked",
                board_id=card.board_id,
                card_id=card.id,
            )
        if unblocked:
            await self.uow.commit()
        for card in unblocked:
            await domain_event_publisher.publish(
                "card.unblocked",
                {
                    "card_id": card.id,
                    "user_id": user_id,
                    "board_id": card.board_id,
                    "title": card.title,
                    "actor": self.actor,
                },
            )
        return [c.id for c in unblocked]

    # ---------------- bolme ----------------
    async def split(self, card_id: int, user_id: int, data: CardSplit) -> None:
        parent = await self.cards.get_owned_card(card_id, user_id)
        if data.titles:
            titles = [t.strip()[:200] for t in data.titles if t.strip()]
        elif data.parts:
            n = data.parts
            titles = [f"{parent.title} — Bölüm {i}/{n}"[:200] for i in range(1, n + 1)]
        else:
            raise ValidationException("'titles' ya da 'parts' verilmeli")
        if not titles:
            raise ValidationException("En az bir alt kart başlığı gerekli")

        total = (
            data.total_minutes
            if data.total_minutes is not None
            else parent.estimated_minutes
        )
        minutes: list[int | None] = [None] * len(titles)
        if total:
            base, extra = divmod(total, len(titles))
            minutes = [base + (1 if i < extra else 0) for i in range(len(titles))]

        position = (
            await self.uow.tasks.max_position_in_list(parent.list_id)
            if parent.list_id
            else 0.0
        )
        created: list[TaskEntity] = []
        for title, mins in zip(titles, minutes, strict=True):
            position += STEP
            child = TaskEntity(
                user_id=user_id,
                board_id=parent.board_id,
                list_id=parent.list_id,
                parent_id=parent.id,
                position=position,
                title=title,
                status=TaskStatus.PENDING,
                priority=parent.priority,
                estimated_minutes=mins,
                created_by=self.actor,
            )
            await self.uow.tasks.create(child)
            created.append(child)
        await self.uow.flush()
        # Her alt kartin kendi gecmisi "created" ile baslasin (istatistikler
        # kart bazli lead time'i activity_log'dan okur)
        for child in created:
            await self.activity.log(
                user_id,
                "card",
                child.id,
                "created",
                board_id=child.board_id,
                card_id=child.id,
                changes={
                    "title": child.title,
                    "parent_id": parent.id,
                    "estimated_minutes": child.estimated_minutes,
                    "via": "split",
                },
            )

        if data.chain:
            for prev, nxt in zip(created, created[1:], strict=False):
                await self.uow.dependencies.create(
                    CardDependencyEntity(
                        user_id=user_id, card_id=nxt.id, depends_on_id=prev.id
                    )
                )
        if total and parent.estimated_minutes is None:
            parent.estimated_minutes = total
        await self.activity.log(
            user_id,
            "card",
            parent.id,
            "split",
            board_id=parent.board_id,
            card_id=parent.id,
            changes={
                "parts": len(created),
                "chain": data.chain,
                "subtask_ids": [c.id for c in created],
            },
        )
        await self.uow.commit()

    # ---------------- grafik ----------------
    async def board_graph(self, board_id: int, user_id: int) -> BoardGraph:
        board = await self.cards.boards.get_owned_board(board_id, user_id)
        cards = await self.uow.tasks.list_for_board(board.id)
        ids = {c.id for c in cards}
        edges = await self.uow.dependencies.edges_touching(list(ids))
        # Baska board'lardaki bagli kartlar da dugum olarak gelsin
        external_ids = {x for e in edges for x in e} - ids
        external = [
            c
            for c in await self.uow.tasks.get_many(list(external_ids))
            if c.user_id == user_id and not c.is_archived
        ]
        all_cards = cards + external
        node_ids = {c.id for c in all_cards}
        graph_edges = [
            GraphEdge(source=dep, target=card, type="dependency")
            for card, dep in edges
            if card in node_ids and dep in node_ids
        ]
        graph_edges += [
            GraphEdge(source=c.parent_id, target=c.id, type="parent")
            for c in all_cards
            if c.parent_id in node_ids
        ]
        return BoardGraph(
            nodes=await self.cards.summaries(all_cards), edges=graph_edges
        )
