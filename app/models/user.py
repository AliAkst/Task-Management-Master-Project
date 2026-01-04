from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Kullanici kayit (register) sirasinda beklenen bilgiler"""

    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str | None = None


class UserLogin(BaseModel):
    """Giris(Login) sirasinda beklenen veriler."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """API'den disariya donecek kullanici bilgileri."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """Giris Basarili oldugunda donecek token paketi"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """JWT Token'in sifrelenmis icerigi(Payload)."""

    sub: str  # User ID (Subject)
    exp: datetime
    type: str  # "Access" veya "Refresh"
