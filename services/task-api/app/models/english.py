"""Ingilizce kocu semalari (Faz 13j1)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Level = Literal["A1", "A2", "B1", "B2", "C1", "C2"]
FocusArea = Literal["speaking", "writing", "vocab", "grammar"]
Source = Literal["local", "claude", "self"]
MistakeCategory = Literal[
    "grammar", "tense", "preposition", "article", "word_choice", "spelling", "other"
]
SessionKind = Literal["daily", "deep", "speaking"]
MAX_BATCH = 20


def _clean(v: str | None) -> str | None:
    if v is None:
        return v
    v = v.strip()
    if not v:
        raise ValueError("Boş olamaz")
    return v


# ---------------- profil ----------------
class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_level: Level
    current_level: Level | None = None
    daily_minutes: int = Field(ge=5, le=120)
    focus: list[FocusArea] = Field(min_length=1)

    @field_validator("focus")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("Odak alanları tekrarsız olmalı")
        return v


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_level: str
    current_level: str | None
    daily_minutes: int
    focus: list[str]
    started_at: date
    created_at: datetime
    updated_at: datetime


# ---------------- kelime ----------------
class VocabItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str = Field(min_length=1, max_length=100)
    meaning_tr: str = Field(min_length=1, max_length=300)
    example: str | None = Field(default=None, max_length=500)
    source: Source | None = None

    @field_validator("term", "meaning_tr")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _clean(v)  # type: ignore[return-value]


class VocabBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[VocabItem] = Field(min_length=1, max_length=MAX_BATCH)


class VocabUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str | None = Field(default=None, min_length=1, max_length=100)
    meaning_tr: str | None = Field(default=None, min_length=1, max_length=300)
    example: str | None = Field(default=None, max_length=500)

    @field_validator("term", "meaning_tr")
    @classmethod
    def _not_blank(cls, v: str | None) -> str | None:
        return _clean(v)


class VocabReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: int = Field(ge=0, le=5)


class VocabResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    term: str
    meaning_tr: str
    example: str | None
    source: str
    ease: float
    interval_days: int
    reps: int
    lapses: int
    due_on: date
    last_reviewed_at: datetime | None
    created_at: datetime
    existing: bool = False  # POST: terim zaten vardi (yeni kayit acilmadi)


# ---------------- hata gunlugu ----------------
class MistakeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Source | None = None
    original: str = Field(min_length=1, max_length=500)
    corrected: str = Field(min_length=1, max_length=500)
    category: MistakeCategory
    explanation_tr: str | None = Field(default=None, max_length=500)


class MistakeBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MistakeItem] = Field(min_length=1, max_length=MAX_BATCH)


class MistakeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    original: str
    corrected: str
    category: str
    explanation_tr: str | None
    review_count: int
    created_at: datetime


# ---------------- seanslar ----------------
class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SessionKind
    started_at: datetime | None = None
    minutes: int = Field(ge=1, le=240)
    summary: str | None = Field(default=None, max_length=2000)
    new_vocab: int = Field(default=0, ge=0, le=32767)
    mistakes_count: int = Field(default=0, ge=0, le=32767)
    source: Source | None = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    started_at: datetime
    minutes: int
    summary: str | None
    new_vocab: int
    mistakes_count: int
    source: str
    created_at: datetime


# ---------------- bugun / ilerleme ----------------
class CategoryCount(BaseModel):
    category: str
    count: int


class TodayResponse(BaseModel):
    profile: ProfileResponse | None
    due_vocab: list[VocabResponse]
    top_categories: list[CategoryCount]
    practiced_today: bool
    task: str | None


class WeekMinutes(BaseModel):
    week: str
    minutes: int


class VocabStats(BaseModel):
    total: int
    due: int
    mature: int


class WeekCategoryCount(BaseModel):
    week: str
    category: str
    count: int


class ProgressResponse(BaseModel):
    streak_days: int
    weekly_minutes: list[WeekMinutes]
    vocab_stats: VocabStats
    mistakes_by_category: list[WeekCategoryCount]
