"""
Ogrenme koçu (Faz 13g): kurs = root_card_id dolu bir `goals` satiri; kokun
cocuk kartlari kursun parcalaridir. Ilerleme, siradaki parca, haftalik hiz ve
tahmini bitis her istekte ham veriden hesaplanir.
"""

import math
import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.db.entities import TaskEntity, TimeSessionEntity
from app.db.entities.goal import GoalEntity, GoalStatus
from app.db.unit_of_work import TaskUnitOfWork
from app.models.learning import (
    CourseCreate,
    CoursePart,
    CourseResponse,
    CourseRootCard,
)
from app.models.task import TaskStatus
from app.services.analytics import AnalyticsService
from app.services.nl_when import fold
from app.services.timeutil import local_today, user_tz

MAX_ACTIVE_COURSES = 2
VELOCITY_DAYS = 28
DEFAULT_PART_MINUTES = 60
CALIBRATION_MIN_SAMPLES = 3
CALIBRATION_BOUNDS = (0.5, 3.0)
CALIBRATION_WINDOW_DAYS = 365

_PART_RE = re.compile(r"^\s*([a-z]{1,3})\s*-?\s*(\d{1,3})(?!\d)")


def _now() -> datetime:
    return datetime.now(UTC)


def course_sort_key(title: str, position: float):
    """
    Parca sirasi: (grup, anahtar, position).
    Grup 0: "P1", "F-12", "pbi101" gibi onekli+sayili basliklar (onek, sayi);
    grup 1: oneksiz basliklar (position); grup 2: "opsiyonel" gecenler (sonda).
    """
    folded = fold(title)
    if "opsiyonel" in folded:
        return (2, position, position)
    m = _PART_RE.match(folded)
    if m:
        return (0, (m.group(1), int(m.group(2))), position)
    return (1, position, position)


class LearningService:
    def __init__(self, uow: TaskUnitOfWork, actor: str = "user"):
        self.uow = uow
        self.actor = actor

    # ---------------- yardimcilar ----------------
    async def _children(self, root_ids: list[int]) -> dict[int, list[TaskEntity]]:
        if not root_ids:
            return {}
        rows = await self.uow.session.scalars(
            select(TaskEntity).where(
                TaskEntity.parent_id.in_(root_ids),
                TaskEntity.is_archived.is_(False),
            )
        )
        out: dict[int, list[TaskEntity]] = {r: [] for r in root_ids}
        for c in rows:
            out[c.parent_id].append(c)  # type: ignore[index]
        for parts in out.values():
            parts.sort(key=lambda c: course_sort_key(c.title, c.position))
        return out

    async def active_count(
        self, user_id: int, exclude_goal_id: int | None = None
    ) -> int:
        query = (
            select(func.count())
            .select_from(GoalEntity)
            .where(
                GoalEntity.user_id == user_id,
                GoalEntity.root_card_id.is_not(None),
                GoalEntity.status == GoalStatus.ACTIVE,
            )
        )
        if exclude_goal_id is not None:
            query = query.where(GoalEntity.id != exclude_goal_id)
        return int(await self.uow.session.scalar(query) or 0)

    async def ensure_can_activate(
        self, user_id: int, exclude_goal_id: int | None = None
    ) -> None:
        """Ucuncu aktif kurs: 409 (hem olusturma hem PATCH yolu cagirir)."""
        if await self.active_count(user_id, exclude_goal_id) >= MAX_ACTIVE_COURSES:
            raise ConflictException(
                "TOO_MANY_ACTIVE_COURSES",
                "En fazla 2 aktif kurs olabilir; önce birini duraklat",
            )

    @staticmethod
    def _factor(calibration: dict[int, tuple[int, float]], board_id) -> float:
        samples, ratio = calibration.get(board_id, (0, 1.0))
        if samples < CALIBRATION_MIN_SAMPLES:
            return 1.0
        lo, hi = CALIBRATION_BOUNDS
        return min(hi, max(lo, ratio))

    # ---------------- okuma ----------------
    async def list_courses(
        self, user_id: int, include: str = "active"
    ) -> list[CourseResponse]:
        query = select(GoalEntity).where(
            GoalEntity.user_id == user_id, GoalEntity.root_card_id.is_not(None)
        )
        if include != "all":
            query = query.where(
                GoalEntity.status.in_([GoalStatus.ACTIVE, GoalStatus.PAUSED])
            )
        goals = list(await self.uow.session.scalars(query.order_by(GoalEntity.id)))
        if not goals:
            return []

        roots = {
            c.id: c
            for c in await self.uow.tasks.get_many([g.root_card_id for g in goals])  # type: ignore[misc]
        }
        children = await self._children(list(roots))

        now = _now()
        tz = await user_tz(self.uow, user_id)
        today = local_today(tz, now)
        calibration = {
            e.board_id: (e.samples, e.median_ratio)
            for e in await AnalyticsService(self.uow).calibration(
                user_id, today - timedelta(days=CALIBRATION_WINDOW_DAYS), today
            )
        }
        since = now - timedelta(days=VELOCITY_DAYS)

        out: list[CourseResponse] = []
        for g in goals:
            root = roots.get(g.root_card_id)  # type: ignore[arg-type]
            if root is None:
                continue
            parts = children.get(root.id, [])
            out.append(
                await self._build(g, root, parts, user_id, today, since, calibration)
            )
        return out

    async def _build(
        self, g, root, parts, user_id, today: date, since: datetime, calibration
    ) -> CourseResponse:
        done = [p for p in parts if p.status == TaskStatus.COMPLETED]
        remaining = [p for p in parts if p.status != TaskStatus.COMPLETED]
        next_part = remaining[0] if remaining else None

        recent = sum(
            1 for p in done if p.completed_at is not None and p.completed_at >= since
        )
        velocity = round(recent / (VELOCITY_DAYS / 7), 2) if recent else None

        estimates = sorted(p.estimated_minutes for p in parts if p.estimated_minutes)
        fallback = estimates[len(estimates) // 2] if estimates else DEFAULT_PART_MINUTES
        raw = sum(p.estimated_minutes or fallback for p in remaining)
        remaining_minutes = int(round(raw * self._factor(calibration, root.board_id)))

        eta_date: date | None = None
        if parts and not remaining:
            reason = "done"
        else:
            budget = await self._weekly_budget(root, parts, user_id, since)
            if budget > 0 and remaining_minutes > 0:
                days = math.ceil(remaining_minutes / budget * 7)
                eta_date = today + timedelta(days=days)
                reason = "ok"
            else:
                reason = "no_velocity"

        return CourseResponse(
            goal_id=g.id,
            title=g.title,
            status=g.status,
            root_card=CourseRootCard(
                id=root.id, title=root.title, board_id=root.board_id
            ),
            parts_total=len(parts),
            parts_done=len(done),
            next_part=CoursePart(
                id=next_part.id,
                title=next_part.title,
                estimated_minutes=next_part.estimated_minutes,
            )
            if next_part
            else None,
            velocity_per_week=velocity,
            remaining_minutes=remaining_minutes,
            eta_date=eta_date,
            eta_reason=reason,  # type: ignore[arg-type]
        )

    async def _weekly_budget(self, root, parts, user_id, since: datetime) -> float:
        """Board haftalik butcesi; yoksa son 4 haftada parcalara harcanan dk / 4."""
        if root.board_id is not None:
            board = await self.uow.boards.get_owned(root.board_id, user_id)
            if board is not None and board.weekly_time_budget_min:
                return float(board.weekly_time_budget_min)
        ids = [p.id for p in parts]
        if not ids:
            return 0.0
        total = await self.uow.session.scalar(
            select(func.sum(TimeSessionEntity.duration_sec)).where(
                TimeSessionEntity.user_id == user_id,
                TimeSessionEntity.card_id.in_(ids),
                TimeSessionEntity.ended_at.is_not(None),
                TimeSessionEntity.started_at >= since,
            )
        )
        return (total or 0) / 60 / (VELOCITY_DAYS / 7)

    async def active_next_parts(self, user_id: int) -> list[tuple[str, TaskEntity]]:
        """Aktif kurslarin (kurs basligi, siradaki parca) cifti (oneri kancasi)."""
        goals = list(
            await self.uow.session.scalars(
                select(GoalEntity)
                .where(
                    GoalEntity.user_id == user_id,
                    GoalEntity.root_card_id.is_not(None),
                    GoalEntity.status == GoalStatus.ACTIVE,
                )
                .order_by(GoalEntity.id)
            )
        )
        children = await self._children([g.root_card_id for g in goals])  # type: ignore[misc]
        out: list[tuple[str, TaskEntity]] = []
        for g in goals:
            for p in children.get(g.root_card_id, []):  # type: ignore[arg-type]
                if p.status != TaskStatus.COMPLETED:
                    out.append((g.title, p))
                    break
        return out

    # ---------------- yazma ----------------
    async def create(self, user_id: int, data: CourseCreate) -> CourseResponse:
        root = await self.uow.tasks.get_owned(data.root_card_id, user_id)
        if root is None:
            raise NotFoundException("Card", data.root_card_id)
        children = await self._children([root.id])
        if not children.get(root.id):
            raise ValidationException("Bu kartın alt parçası yok")
        exists = await self.uow.session.scalar(
            select(func.count())
            .select_from(GoalEntity)
            .where(GoalEntity.user_id == user_id, GoalEntity.root_card_id == root.id)
        )
        if exists:
            raise ConflictException(
                "COURSE_EXISTS", "Bu kart zaten bir kurs olarak takip ediliyor"
            )
        status = (
            GoalStatus.ACTIVE
            if await self.active_count(user_id) < MAX_ACTIVE_COURSES
            else GoalStatus.PAUSED
        )
        goal = GoalEntity(
            user_id=user_id,
            board_id=root.board_id,
            root_card_id=root.id,
            title=root.title,
            status=status,
            created_by=self.actor,
        )
        self.uow.session.add(goal)
        await self.uow.commit()
        courses = await self.list_courses(user_id, "all")
        return next(c for c in courses if c.goal_id == goal.id)
