from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_SESSION_HOURS = 24


class SessionStart(BaseModel):
    """card_id bos ise karta bagli olmayan "serbest" calisma."""

    card_id: int | None = None
    note: str | None = Field(None, max_length=2000)


class SessionStop(BaseModel):
    note: str | None = Field(None, max_length=2000)


class SessionManualCreate(BaseModel):
    """Unutulan / sonradan girilen calisma suresi."""

    card_id: int | None = None
    started_at: datetime
    ended_at: datetime
    note: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def check(self) -> Self:
        if self.ended_at <= self.started_at:
            raise ValueError("Bitiş zamanı başlangıçtan sonra olmalı")
        if (self.ended_at - self.started_at).total_seconds() > MAX_SESSION_HOURS * 3600:
            raise ValueError(f"Tek oturum en fazla {MAX_SESSION_HOURS} saat olabilir")
        return self


class SessionUpdate(BaseModel):
    """Duzeltme. Calisan oturumda sadece not/kart degisebilir."""

    card_id: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    note: str | None = Field(None, max_length=2000)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    card_id: int | None
    board_id: int | None
    card_title: str | None
    started_at: datetime
    ended_at: datetime | None
    duration_sec: int | None
    note: str | None
    source: str
    is_running: bool = False


class ActiveSession(BaseModel):
    """GET /sessions/active: calisan oturum yoksa session null."""

    session: SessionResponse | None
