"""Ogrenme koçu: kurs ilerleme / ETA modelleri (Faz 13g)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.db.entities.goal import GoalStatus


class CourseRootCard(BaseModel):
    id: int
    title: str
    board_id: int | None = None


class CoursePart(BaseModel):
    id: int
    title: str
    estimated_minutes: int | None = None


class CourseResponse(BaseModel):
    goal_id: int
    title: str
    status: GoalStatus
    root_card: CourseRootCard
    parts_total: int
    parts_done: int
    next_part: CoursePart | None = None
    velocity_per_week: float | None = None
    remaining_minutes: int
    eta_date: date | None = None
    eta_reason: Literal["ok", "no_velocity", "done"]


class CourseCreate(BaseModel):
    root_card_id: int = Field(..., ge=1)
