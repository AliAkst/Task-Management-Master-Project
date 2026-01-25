from datetime import UTC, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

class ErrorDetail(BaseModel):
    code: str
    message: str


class ApiResponse[T](BaseModel):
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

class PaginationParams(BaseModel):
    """Sayfalama Parametreleri"""
    page: int = Field(default=1,ge=1,descriptiption="Sayfa numarasi")
    page_size : int =Field(default=10, ge=1, le=100, description="Sayfa basina kayit")

class PaginatedResponse(BaseModel, Generic[T]):
    """Sayfalama icin response modeli """
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
