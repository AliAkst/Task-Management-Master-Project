from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.task import TaskStatus


def _check_range(start: datetime | None, end: datetime | None) -> None:
    if start is not None and end is not None and end <= start:
        raise ValueError("Bitiş zamanı başlangıçtan sonra olmalı")


class EventCreate(BaseModel):
    """
    card_id verilirse etkinlik o karta ayrilmis zaman blogudur; board'u ve
    (title verilmezse) basligi karttan alir.
    """

    title: str | None = Field(None, min_length=1, max_length=200)
    start_at: datetime
    end_at: datetime
    all_day: bool = False
    board_id: int | None = None
    card_id: int | None = None
    location: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=20000)
    # RRULE, orn. "FREQ=WEEKLY;BYDAY=MO,WE,FR" (bos: tekrarlanmaz)
    recurrence_rule: str | None = Field(None, max_length=500)
    # Faz 12d: etkinlik o gunun planina da eklensin (kaydedilmez; varsayilan kapali)
    add_to_plan: bool = False

    @model_validator(mode="after")
    def check(self) -> Self:
        _check_range(self.start_at, self.end_at)
        if self.title is None and self.card_id is None:
            raise ValueError("title ya da card_id gerekli")
        return self


class EventUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool | None = None
    board_id: int | None = None
    location: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=20000)
    recurrence_rule: str | None = Field(None, max_length=500)  # null: tekrari kaldir

    @model_validator(mode="after")
    def check(self) -> Self:
        _check_range(self.start_at, self.end_at)
        return self


class ExternalRef(BaseModel):
    """Etkinligin geldigi dis sistem; varsa etkinlik salt okunurdur."""

    provider: str
    url: str | None = None


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    board_id: int | None
    card_id: int | None
    title: str
    start_at: datetime
    end_at: datetime
    all_day: bool
    location: str | None
    notes: str | None
    meeting_url: str | None = None
    recurrence_rule: str | None = None
    external: ExternalRef | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime


class CalendarItem(BaseModel):
    """
    Takvimde gosterilen tek oge. Iki tur:
    - event: zaman blogu / bagimsiz etkinlik (EventEntity)
    - deadline: kartin son tarihi (tum gun isareti)
    """

    kind: Literal["event", "deadline"]
    id: str  # "event-12" / "deadline-34" (takvimde benzersiz)
    title: str
    start: datetime
    end: datetime | None
    all_day: bool
    board_id: int | None
    color: str
    event_id: int | None = None
    card_id: int | None = None
    card_status: TaskStatus | None = None
    location: str | None = None
    meeting_url: str | None = None
    # Tekrarlayan etkinligin bir tekrari: start/end bu tekrarin zamanidir;
    # duzenleme butun seriye uygulanir (event_id)
    recurrence_rule: str | None = None
    # Dis takvimden gelen etkinlik: salt okunur (surukleme/duzenleme kapali)
    external: ExternalRef | None = None


class CalendarResponse(BaseModel):
    items: list[CalendarItem]
