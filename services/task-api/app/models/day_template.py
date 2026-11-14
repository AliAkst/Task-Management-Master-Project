"""Gun sablonlari (Faz 13c)."""

import re
from datetime import datetime, time
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
BlockKind = Literal["yol", "mesai", "yemek", "rutin", "diger"]
TemplateSource = Literal["off", "override", "weekday"]


def hhmm_to_min(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


class TemplateBlock(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    start: str
    end: str  # "24:00" kabul edilir (gece yarisi gecisi yok)
    kind: BlockKind = "diger"

    @field_validator("start")
    @classmethod
    def _start(cls, v: str) -> str:
        if not _HHMM.match(v):
            raise ValueError("Saat HH:MM biçiminde olmalı")
        return v

    @field_validator("end")
    @classmethod
    def _end(cls, v: str) -> str:
        if v != "24:00" and not _HHMM.match(v):
            raise ValueError("Saat HH:MM biçiminde olmalı")
        return v

    @model_validator(mode="after")
    def _order(self) -> Self:
        if hhmm_to_min(self.end) <= hhmm_to_min(self.start):
            raise ValueError(f"Blok bitişi başlangıçtan sonra olmalı: {self.title}")
        return self


def _check_blocks(blocks: list[TemplateBlock]) -> list[TemplateBlock]:
    ordered = sorted(blocks, key=lambda b: hhmm_to_min(b.start))
    for a, b in zip(ordered, ordered[1:], strict=False):
        if hhmm_to_min(b.start) < hhmm_to_min(a.end):
            raise ValueError(f"Bloklar çakışıyor: {a.title}, {b.title}")
    return ordered


def _check_weekdays(days: list[int]) -> list[int]:
    if any(d < 0 or d > 6 for d in days):
        raise ValueError("Hafta günü 0-6 olmalı")
    if len(set(days)) != len(days):
        raise ValueError("Hafta günleri tekrarsız olmalı")
    return sorted(days)


class DayTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    blocks: list[TemplateBlock] = Field(min_length=1, max_length=12)
    day_start: time = time(8, 0)
    day_end: time = time(23, 0)
    buffer_min: Literal[0, 5, 10, 15] = 0

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Ad boş olamaz")
        return v

    @field_validator("weekdays")
    @classmethod
    def _weekdays(cls, v: list[int]) -> list[int]:
        return _check_weekdays(v)

    @field_validator("blocks")
    @classmethod
    def _blocks(cls, v: list[TemplateBlock]) -> list[TemplateBlock]:
        return _check_blocks(v)

    @model_validator(mode="after")
    def _range(self) -> Self:
        if self.day_start >= self.day_end:
            raise ValueError("Gün başlangıcı bitişten önce olmalı")
        return self


class DayTemplateUpdate(BaseModel):
    """Kismi guncelleme; birlesik sonuc servis tarafinda DayTemplateCreate ile dogrulanir."""

    name: str | None = Field(None, min_length=1, max_length=60)
    weekdays: list[int] | None = Field(None, max_length=7)
    blocks: list[TemplateBlock] | None = Field(None, min_length=1, max_length=12)
    day_start: time | None = None
    day_end: time | None = None
    buffer_min: Literal[0, 5, 10, 15] | None = None

    @field_validator("weekdays")
    @classmethod
    def _weekdays(cls, v: list[int] | None) -> list[int] | None:
        return None if v is None else _check_weekdays(v)

    @field_validator("blocks")
    @classmethod
    def _blocks(cls, v: list[TemplateBlock] | None) -> list[TemplateBlock] | None:
        return None if v is None else _check_blocks(v)

    @model_validator(mode="after")
    def _not_null(self) -> Self:
        for f in self.model_fields_set:
            if getattr(self, f) is None:
                raise ValueError(f"{f} boş olamaz")
        return self


class DayTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    weekdays: list[int]
    blocks: list[TemplateBlock]
    day_start: time
    day_end: time
    buffer_min: int
    created_at: datetime
    updated_at: datetime


class DayTemplateForDay(BaseModel):
    template: DayTemplateResponse | None = None
    source: TemplateSource | None = None
    applied_at: datetime | None = None


class TemplateModeInput(BaseModel):
    mode: Literal["auto", "off", "template"]
    template_id: int | None = None

    @model_validator(mode="after")
    def _need_id(self) -> Self:
        if self.mode == "template" and self.template_id is None:
            raise ValueError("template_id gerekli")
        return self


class ApplyTemplateInput(BaseModel):
    force: bool = False


class ApplyTemplateResult(BaseModel):
    added: int
    reason: Literal["applied", "no_template", "already_applied"]
