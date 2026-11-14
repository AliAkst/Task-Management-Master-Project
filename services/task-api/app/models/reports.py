"""İş özeti (Faz 13h1) yanıt modelleri."""

from datetime import date as date_type

from pydantic import BaseModel


class WorkLine(BaseModel):
    title: str
    minutes: int = 0


class NotDoneLine(BaseModel):
    title: str
    reason: str | None = None
    postponed_to: date_type | None = None


class TomorrowLine(BaseModel):
    title: str


class WorkSections(BaseModel):
    completed: list[WorkLine]
    worked: list[WorkLine]
    not_done: list[NotDoneLine]
    tomorrow: list[TomorrowLine]


class WorkSummary(BaseModel):
    date: date_type
    sections: WorkSections
    text: str
