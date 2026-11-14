"""Süpürme adayları ve toplu kart işlemi (Faz 13h1) modelleri."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

BulkOp = Literal["archive", "unarchive", "complete", "move"]


class SweepCard(BaseModel):
    id: int
    title: str
    list_name: str
    due_date: datetime | None = None
    reason: str


class SweepGroup(BaseModel):
    key: str
    label: str
    cards: list[SweepCard]


class DoneListHint(BaseModel):
    list_id: int
    name: str


class SweepCandidates(BaseModel):
    groups: list[SweepGroup]
    done_list_hints: list[DoneListHint]


class BulkCards(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=200)
    op: BulkOp
    target_list_id: int | None = None

    @model_validator(mode="after")
    def check(self) -> Self:
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("ids tekil olmalı")
        if self.op == "move" and self.target_list_id is None:
            raise ValueError("move için target_list_id gerekli")
        return self


class BulkResult(BaseModel):
    updated: int
