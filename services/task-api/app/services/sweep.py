"""
Eski kart süpürme (Faz 13h1): aday grupları + eşleştiriciler.

Yalnız okur; kartları değiştiren toplu işlem `CardService.bulk`'tadır. Gruplar
sırayla değerlendirilir ve bir kart yalnız ilk eşleştiği grupta görünür.
"""

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db.entities import ActivityLogEntity, TaskEntity
from app.db.entities.day_plan import DayPlanItemEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.models.sweep import DoneListHint, SweepCandidates, SweepCard, SweepGroup
from app.models.task import TaskStatus
from app.services.board import BoardService
from app.services.nl_when import fold

GROUP_LIMIT = 500
OVERDUE_DAYS = 14
STALE_DAYS = 30

_OLD_LIST = re.compile(r"\b(old|eski|arsiv|archive|archived)\b")
_DONE_LIST = re.compile(
    r"\b(completed|complete|done|tamamlanan|tamamlandi|bitti|biten)\b"
)
_EDGES = re.compile(r"^[\W_]+|[\W_]+$")
_SPACES = re.compile(r"\s+")
_PREFIX_ONLY = re.compile(r"^(p|f)\s*-?\s*(\d+)$")


def is_old_list(name: str) -> bool:
    return _OLD_LIST.search(fold(name)) is not None


def is_done_list_hint(name: str) -> bool:
    return _DONE_LIST.search(fold(name)) is not None


def norm_title(title: str) -> str:
    """Katla, baştaki/sondaki noktalama ve emojiyi sil, boşlukları teklə."""
    text = _EDGES.sub("", fold(title).strip())
    return _SPACES.sub(" ", text).strip()


def is_duplicate(a: str, b: str) -> bool:
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    for short, long_ in ((na, nb), (nb, na)):
        m = _PREFIX_ONLY.match(short)
        if m and re.match(rf"^{m.group(1)}\s*-?\s*{m.group(2)}\b", long_):
            return True
    return False


GROUPS = (
    ("old_lists", "Eski listeler"),
    ("overdue", f"Son tarihi {OVERDUE_DAYS}+ gün geçmiş"),
    ("duplicates", "Mükerrer"),
    ("stale", f"{STALE_DAYS} gündür dokunulmamış"),
)


class SweepService:
    def __init__(self, uow: TaskUnitOfWork):
        self.uow = uow
        self.boards = BoardService(uow)

    async def candidates(self, board_id: int, user_id: int) -> SweepCandidates:
        await self.boards.get_owned_board(board_id, user_id)
        lists = await self.uow.lists.list_for_board(board_id)
        list_name = {lst.id: lst.name for lst in lists}
        # arşivlenmemiş kartlar (tamamlananlar mükerrer ikiz kontrolü için lazım)
        cards = await self.uow.tasks.list_for_board(board_id)
        open_cards = [c for c in cards if c.status != TaskStatus.COMPLETED]

        now = datetime.now(UTC)
        picked: dict[str, list[SweepCard]] = {k: [] for k, _ in GROUPS}
        taken: set[int] = set()

        def add(key: str, card: TaskEntity, reason: str) -> None:
            if card.id in taken:
                return
            taken.add(card.id)
            picked[key].append(
                SweepCard(
                    id=card.id,
                    title=card.title,
                    list_name=list_name.get(card.list_id or -1, ""),
                    due_date=card.due_date,
                    reason=reason,
                )
            )

        # 1) eski listeler
        for c in open_cards:
            name = list_name.get(c.list_id or -1, "")
            if name and is_old_list(name):
                add("old_lists", c, f"Liste: «{name}»")
        # 2) son tarihi 14+ gün geçmiş
        limit = now - timedelta(days=OVERDUE_DAYS)
        for c in open_cards:
            if c.due_date is not None and c.due_date < limit:
                days = (now - c.due_date).days
                add("overdue", c, f"Son tarih {days} gün önce")
        # 3) mükerrer
        for c in open_cards:
            twin = self._duplicate_twin(c, cards)
            if twin is not None:
                add("duplicates", c, f"«{twin.title}» (#{twin.id}) ile aynı")
        # 4) bayat
        await self._add_stale(open_cards, now, add)

        groups = [
            SweepGroup(key=k, label=label, cards=picked[k][:GROUP_LIMIT])
            for k, label in GROUPS
            if picked[k]
        ]
        hints = [
            DoneListHint(list_id=lst.id, name=lst.name)
            for lst in lists
            if not lst.is_done_list and is_done_list_hint(lst.name)
        ]
        return SweepCandidates(groups=groups, done_list_hints=hints)

    @staticmethod
    def _duplicate_twin(card: TaskEntity, cards: list[TaskEntity]) -> TaskEntity | None:
        """(a) tamamlanmış ikiz varsa o; (b) açık ikizlerden id'si küçük olan."""
        twins = [
            o for o in cards if o.id != card.id and is_duplicate(card.title, o.title)
        ]
        done = [o for o in twins if o.status == TaskStatus.COMPLETED]
        if done:
            return min(done, key=lambda o: o.id)
        smaller = [o for o in twins if o.id < card.id]
        return min(smaller, key=lambda o: o.id) if smaller else None

    async def _add_stale(self, open_cards: list[TaskEntity], now: datetime, add) -> None:
        limit = now - timedelta(days=STALE_DAYS)
        old_enough = [c for c in open_cards if c.created_at < limit]
        if not old_enough:
            return
        ids = [c.id for c in old_enough]
        last_activity: dict[int, datetime] = {}
        planned: set[int] = set()
        for i in range(0, len(ids), 500):
            chunk = ids[i : i + 500]
            rows = await self.uow.session.execute(
                select(ActivityLogEntity.card_id, func.max(ActivityLogEntity.occurred_at))
                .where(ActivityLogEntity.card_id.in_(chunk))
                .group_by(ActivityLogEntity.card_id)
            )
            for card_id, ts in rows.all():
                last_activity[card_id] = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
            rows = await self.uow.session.execute(
                select(DayPlanItemEntity.card_id)
                .where(DayPlanItemEntity.card_id.in_(chunk))
                .distinct()
            )
            planned.update(r[0] for r in rows.all())
        for c in old_enough:
            seen = last_activity.get(c.id, c.created_at)
            if seen < limit and c.id not in planned:
                add("stale", c, f"Son hareket {(now - seen).days} gün önce")
