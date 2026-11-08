from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskPriority, TaskStatus


# ---------------- Card ----------------
class CardCreate(BaseModel):
    """list_id ya da parent_id verilmeli; alt kart default ust kartin listesine."""

    list_id: int | None = None
    parent_id: int | None = None
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
    parent_id: int | None = None  # null gonderilirse ust karttan ayrilir
    graph_x: float | None = None
    graph_y: float | None = None
    assigned_to: int | None = None


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
    # --- hiyerarsi & bagimlilik (Faz 1b) ---
    parent_id: int | None = None
    assigned_to: int | None = None
    graph_x: float | None = None
    graph_y: float | None = None
    blocked: bool = False  # bitmemis on kosulu var mi
    blocked_by_count: int = 0
    subtask_total: int = 0
    subtask_done: int = 0
    subtask_estimated_minutes: int = 0
    # --- zaman takibi (Faz 3a): bitmis oturumlarin toplami (calisan haric) ---
    tracked_seconds: int = 0
    subtask_tracked_seconds: int = 0


class CardRef(BaseModel):
    """Baska bir karta kisa referans (bagimlilik / ust kart listeleri icin)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: TaskStatus
    board_id: int | None


class DependencyCreate(BaseModel):
    depends_on_id: int


class CardSplit(BaseModel):
    """Karti alt kartlara boler. `titles` ya da `parts` verilmeli."""

    titles: list[str] | None = Field(None, min_length=1, max_length=50)
    parts: int | None = Field(None, ge=1, le=50)
    total_minutes: int | None = Field(None, ge=0, le=100000)
    chain: bool = True  # alt kartlari sirali iple bagla (1 -> 2 -> 3 ...)


class GraphEdge(BaseModel):
    source: int  # on kosul (ya da ust kart)
    target: int  # bagimli kart (ya da alt kart)
    type: str  # "dependency" | "parent"


class BoardGraph(BaseModel):
    """Grafik gorunum: board'un kartlari + baska board'lardan bagli kartlar."""

    nodes: list["CardSummary"]
    edges: list[GraphEdge]


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
    parent: CardRef | None = None
    subtasks: list[CardSummary] = Field(default_factory=list)
    depends_on: list[CardRef] = Field(default_factory=list)
    dependents: list[CardRef] = Field(default_factory=list)


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
