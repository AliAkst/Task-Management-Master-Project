from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserSettingsUpdate(BaseModel):
    """Kismi guncelleme: sadece gonderilen alanlar degisir."""

    timezone: str | None = Field(None, max_length=64)
    planning_time: time | None = None
    review_time: time | None = None
    reminders_enabled: bool | None = None
    week_start: int | None = Field(None, ge=0, le=6)

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
    updated_at: datetime
