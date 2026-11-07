from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskPriority, TaskStatus


# ---------------- Card ----------------
class CardCreate(BaseModel):
    list_id: int
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=20000)
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: datetime | None = None
    start_at: datetime | None = None
    estimated_minutes: int | None = Field(None, ge=0, le=100000)
    label_ids: list[int] = Field(default_factory=list)


class CardUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=20000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: datetime | None = None
    start_at: datetime | None = None
    estimated_minutes: int | None = Field(None, ge=0, le=100000)
    is_archived: bool | None = None
    label_ids: list[int] | None = None


class CardMove(BaseModel):
    """Karti hedef listede verilen sira indeksine (0 tabanli) tasir."""

    list_id: int
    index: int = Field(..., ge=0)


class CardSummary(BaseModel):
    """Kanban'da kart yuzu icin gereken alanlar."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    board_id: int | None
    list_id: int | None
    title: str
    status: TaskStatus
    priority: TaskPriority
    position: float
    due_date: datetime | None
    start_at: datetime | None
    estimated_minutes: int | None
    completed_at: datetime | None
    is_archived: bool
    has_description: bool = False
    label_ids: list[int] = Field(default_factory=list)
    checklist_total: int = 0
    checklist_done: int = 0
    note_count: int = 0


# ---------------- Note ----------------
class NoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=20000)


class NoteUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=20000)


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    card_id: int
    content: str
    created_at: datetime
    updated_at: datetime


# ---------------- Checklist ----------------
class ChecklistItemCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


class ChecklistItemUpdate(BaseModel):
    text: str | None = Field(None, min_length=1, max_length=500)
    is_done: bool | None = None


class ChecklistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    card_id: int
    text: str
    is_done: bool
    position: float


# ---------------- Detail / Activity ----------------
class CardDetail(CardSummary):
    user_id: int
    description: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    notes: list[NoteResponse] = Field(default_factory=list)
    checklist: list[ChecklistItemResponse] = Field(default_factory=list)


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    action: str
    board_id: int | None
    card_id: int | None
    changes: dict[str, Any] | None
    actor: str
    occurred_at: datetime
