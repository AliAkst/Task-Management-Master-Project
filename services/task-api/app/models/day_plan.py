from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.entities.day_plan import DayPlanStatus, ItemOutcome
from app.models.task import TaskStatus

Day = date  # ItemMove.date alani tip adini golgeler


# ---------------- planlama ----------------
class PlanItemInput(BaseModel):
    """Karta, takvim etkinligine ya da sadece basliga dayali plan maddesi."""

    id: int | None = None  # var olan plan maddesi (yerinde guncellenir)
    card_id: int | None = None
    event_id: int | None = None
    title: str | None = Field(None, min_length=1, max_length=200)
    planned_minutes: int | None = Field(None, ge=0, le=1440)
    planned_start: datetime | None = None  # yalniz etkinliksiz maddede

    @model_validator(mode="after")
    def check(self) -> Self:
        if (
            self.id is None
            and self.card_id is None
            and self.event_id is None
            and not self.title
        ):
            raise ValueError("id, card_id, event_id ya da title gerekli")
        return self


class DayPlanItemPatch(BaseModel):
    """Tek plan maddesini gunceller; verilmeyen alan degismez."""

    done: bool | None = None
    title: str | None = Field(None, min_length=1, max_length=200)
    planned_minutes: int | None = Field(None, ge=0, le=1440)
    planned_start: datetime | None = None

    @model_validator(mode="after")
    def check(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("En az bir alan gerekli")
        return self


class ItemToCard(BaseModel):
    """Plan maddesini karta donusturur (list_id ya da board_id)."""

    board_id: int | None = None
    list_id: int | None = None


class ItemMove(BaseModel):
    """Plan maddesini baska bir gune tasir (bos ise ertesi gun)."""

    date: Day | None = None


class DayPlanSave(BaseModel):
    """Gunun planli maddelerini (yeniden) yazar."""

    items: list[PlanItemInput] = Field(default_factory=list, max_length=100)


# ---------------- degerlendirme ----------------
class ItemReview(BaseModel):
    id: int
    outcome: ItemOutcome
    reason: str | None = Field(None, max_length=2000)
    postponed_to: date | None = None  # bos ise ertesi gun


class UnplannedInput(BaseModel):
    """Plan disi yapilan is."""

    card_id: int | None = None
    title: str | None = Field(None, min_length=1, max_length=200)
    outcome: ItemOutcome = ItemOutcome.DONE
    reason: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def check(self) -> Self:
        if self.card_id is None and not self.title:
            raise ValueError("card_id ya da title gerekli")
        return self


class DayReview(BaseModel):
    mood: int | None = Field(None, ge=1, le=5)
    energy: int | None = Field(None, ge=1, le=5)
    reflection: str | None = Field(None, max_length=10000)
    items: list[ItemReview] = Field(default_factory=list, max_length=100)
    unplanned: list[UnplannedInput] = Field(default_factory=list, max_length=50)


class AiSummaryInput(BaseModel):
    """Asistanin yazdigi gun ozeti; None ozeti siler."""

    ai_summary: str | None = Field(None, max_length=4000)


# ---------------- yanitlar ----------------
class DayPlanItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    card_id: int | None
    event_id: int | None
    title: str
    board_id: int | None
    was_planned: bool
    planned_start: datetime | None
    planned_minutes: int | None
    outcome: ItemOutcome | None
    reason: str | None
    tracked_sec: int
    postponed_to: date | None
    # canli bilgiler (snapshot degil)
    card_status: TaskStatus | None = None
    tracked_today_sec: int = 0


class DayPlanResponse(BaseModel):
    date: date
    exists: bool
    status: DayPlanStatus | None = None
    mood: int | None = None
    energy: int | None = None
    reflection: str | None = None
    planned_at: datetime | None = None
    reviewed_at: datetime | None = None
    ai_summary: str | None = None  # asistanin gun ozeti (Faz 6)
    items: list[DayPlanItemResponse] = Field(default_factory=list)
    tracked_today_sec: int = 0  # o gun toplam (plansiz dahil)


SuggestionKind = Literal[
    "event",
    "carry_over",
    "due",
    "overdue",
    "in_progress",
    "next_in_chain",
    "worked",
]


class PlanSuggestion(BaseModel):
    kind: SuggestionKind
    card_id: int | None = None
    event_id: int | None = None
    title: str
    board_id: int | None = None
    planned_start: datetime | None = None
    planned_minutes: int | None = None
    due_date: datetime | None = None
    tracked_sec: int = 0  # o gun bu karta harcanan
    blocked: bool = False
    already_planned: bool = False


class DaySuggestions(BaseModel):
    date: date
    items: list[PlanSuggestion]
