from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.entities.board import BoardPrivacy
from app.models.card import CardSummary

HEX_COLOR = r"^#[0-9a-fA-F]{6}$"
MODEL_ID = r"^[a-z_]+:[\w.\-:/@]{1,150}$"
LOCAL_MODEL_PREFIX = "ollama:"


def is_local_model(model_id: str | None) -> bool:
    return model_id is None or model_id.startswith(LOCAL_MODEL_PREFIX)


# ---------------- Board ----------------
class BoardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scope_description: str | None = Field(None, max_length=5000)
    color: str = Field("#64748b", pattern=HEX_COLOR)
    icon: str | None = Field(None, max_length=50)
    weekly_time_budget_min: int | None = Field(None, ge=0, le=10080)
    privacy: BoardPrivacy = BoardPrivacy.CLOUD_ALLOWED
    default_model_id: str | None = Field(None, pattern=MODEL_ID)
    # Bos birakilirsa varsayilan listeler: Yapilacak, Yapiliyor, Tamamlandi
    lists: list[str] | None = Field(None, max_length=20)


class BoardUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    scope_description: str | None = Field(None, max_length=5000)
    color: str | None = Field(None, pattern=HEX_COLOR)
    icon: str | None = Field(None, max_length=50)
    weekly_time_budget_min: int | None = Field(None, ge=0, le=10080)
    privacy: BoardPrivacy | None = None
    default_model_id: str | None = Field(None, pattern=MODEL_ID)
    is_archived: bool | None = None
    position: float | None = None


class BoardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    scope_description: str | None
    color: str
    icon: str | None
    position: float
    weekly_time_budget_min: int | None
    privacy: BoardPrivacy
    default_model_id: str | None = None
    system_kind: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class BoardWithCounts(BoardResponse):
    open_card_count: int = 0


# ---------------- List ----------------
class ListCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    is_done_list: bool = False


class ListUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    is_done_list: bool | None = None


class ListMove(BaseModel):
    """Listeyi board icinde verilen sira indeksine (0 tabanli) tasir."""

    index: int = Field(..., ge=0)


class ListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    board_id: int
    name: str
    position: float
    is_done_list: bool


# ---------------- Label ----------------
class LabelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    # Verilmezse servis board'da kullanilmayan ilk palet rengini secer
    color: str | None = Field(None, pattern=HEX_COLOR)


class LabelUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    color: str | None = Field(None, pattern=HEX_COLOR)


class LabelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    board_id: int
    name: str
    color: str


# ---------------- Kanban gorunumu ----------------
class BoardDetail(BaseModel):
    """Kanban ekrani icin tek istekte board + listeler + kartlar + etiketler."""

    board: BoardResponse
    lists: list[ListResponse]
    cards: list[CardSummary]
    labels: list[LabelResponse]
