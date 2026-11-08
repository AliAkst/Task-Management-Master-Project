"""Hedefler: kullanicinin hayatinda yapmak istedikleri (Faz 5b)."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.exceptions import NotFoundException
from app.db.entities.goal import GoalEntity, GoalStatus
from app.db.unit_of_work import TaskUnitOfWork
from app.services.activity import ActivityLogger, diff


class GoalCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    why: str | None = Field(None, max_length=5000)
    target_date: date | None = None
    board_id: int | None = None
    root_card_id: int | None = None


class GoalUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    why: str | None = Field(None, max_length=5000)
    target_date: date | None = None
    board_id: int | None = None
    root_card_id: int | None = None
    status: GoalStatus | None = None


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    why: str | None
    target_date: date | None
    board_id: int | None
    root_card_id: int | None
    status: GoalStatus
    created_by: str
    created_at: datetime
    updated_at: datetime


class GoalService:
    def __init__(self, uow: TaskUnitOfWork, actor: str = "user"):
        self.uow = uow
        self.actor = actor
        self.activity = ActivityLogger(uow, actor)

    async def _owned(self, goal_id: int, user_id: int) -> GoalEntity:
        goal = await self.uow.session.get(GoalEntity, goal_id)
        if goal is None or goal.user_id != user_id:
            raise NotFoundException("Goal", goal_id)
        return goal

    async def _check_refs(self, user_id: int, board_id, root_card_id) -> None:
        if (
            board_id is not None
            and await self.uow.boards.get_owned(board_id, user_id) is None
        ):
            raise NotFoundException("Board", board_id)
        if (
            root_card_id is not None
            and await self.uow.tasks.get_owned(root_card_id, user_id) is None
        ):
            raise NotFoundException("Card", root_card_id)

    async def list(
        self, user_id: int, status: GoalStatus | None = None
    ) -> list[GoalResponse]:
        query = select(GoalEntity).where(GoalEntity.user_id == user_id)
        if status is not None:
            query = query.where(GoalEntity.status == status)
        rows = await self.uow.session.scalars(query.order_by(GoalEntity.id))
        return [GoalResponse.model_validate(g) for g in rows]

    async def create(self, user_id: int, data: GoalCreate) -> GoalResponse:
        await self._check_refs(user_id, data.board_id, data.root_card_id)
        goal = GoalEntity(user_id=user_id, created_by=self.actor, **data.model_dump())
        self.uow.session.add(goal)
        await self.uow.flush()
        await self.activity.log(
            user_id,
            "goal",
            goal.id,
            "created",
            board_id=goal.board_id,
            changes={"title": goal.title},
        )
        await self.uow.commit()
        return GoalResponse.model_validate(goal)

    async def update(
        self, goal_id: int, user_id: int, data: GoalUpdate
    ) -> GoalResponse:
        goal = await self._owned(goal_id, user_id)
        update = data.model_dump(exclude_unset=True)
        await self._check_refs(
            user_id, update.get("board_id"), update.get("root_card_id")
        )
        changes = diff(goal, update)
        for key, value in update.items():
            setattr(goal, key, value)
        if changes:
            action = {
                GoalStatus.ACHIEVED.value: "achieved",
                GoalStatus.DROPPED.value: "dropped",
            }.get(changes.get("status", [None, None])[1], "updated")
            await self.activity.log(
                user_id,
                "goal",
                goal.id,
                action,
                board_id=goal.board_id,
                changes=changes,
            )
        await self.uow.commit()
        return GoalResponse.model_validate(goal)

    async def delete(self, goal_id: int, user_id: int) -> None:
        goal = await self._owned(goal_id, user_id)
        await self.uow.session.delete(goal)
        await self.uow.commit()


async def detach_goals(session, *, board_id=None, card_id=None) -> None:
    """Board/kart silinirken hedefi koru, baglantiyi kopar (SQLite FK kapali)."""
    from sqlalchemy import update

    if board_id is not None:
        await session.execute(
            update(GoalEntity)
            .where(GoalEntity.board_id == board_id)
            .values(board_id=None)
        )
    if card_id is not None:
        await session.execute(
            update(GoalEntity)
            .where(GoalEntity.root_card_id == card_id)
            .values(root_card_id=None)
        )
