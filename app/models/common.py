from pydantic import BaseModel, Field
from typing import Generic, TypeVar, Optional
from datetime import datetime, timezone

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None
    error: ErrorDetail | None = None

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
