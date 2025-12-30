from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str


class ApiResponse[T](BaseModel):
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
