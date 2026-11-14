from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[Literal["read", "write"]] = Field(min_length=1)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    token_hint: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None


class ApiTokenCreated(BaseModel):
    """Olusturma yaniti: duz metin jeton yalniz burada, bir kez doner."""

    id: int
    name: str
    token: str
    token_hint: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None = None
