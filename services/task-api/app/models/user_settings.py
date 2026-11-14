from datetime import datetime, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserSettingsUpdate(BaseModel):
    """Kismi guncelleme: sadece gonderilen alanlar degisir."""

    timezone: str | None = Field(None, max_length=64)
    planning_time: time | None = None
    review_time: time | None = None
    reminders_enabled: bool | None = None
    week_start: int | None = Field(None, ge=0, le=6)
    theme: Literal["system", "light", "dark"] | None = None
    background: Literal["kagit", "krem", "adacayi", "lavanta", "gri"] | None = None
    day_rollover: time | None = None  # 00:00-06:00 (Faz 13c)
    morning_time: time | None = None

    @field_validator("day_rollover")
    @classmethod
    def check_rollover(cls, v: time | None) -> time | None:
        if v is None:
            raise ValueError("day_rollover bos olamaz")
        if not (time(0, 0) <= v <= time(6, 0)):
            raise ValueError("day_rollover 00:00-06:00 arasinda olmali")
        return v

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"Gecersiz saat dilimi: {v}") from e
        return v


class UserSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timezone: str
    planning_time: time | None
    review_time: time | None
    reminders_enabled: bool
    week_start: int
    theme: str
    background: str
    day_rollover: time
    morning_time: time | None
    updated_at: datetime
