from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UTCDateTime


class ApiTokenEntity(Base):
    """
    Kisisel erisim jetonu (PAT, Faz 13b). Duz metin saklanmaz: yalniz sha256
    ozeti (token_hash) ve gosterim icin kisa ipucu (token_hint) tutulur.
    """

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_hint: Mapped[str] = mapped_column(String(16))
    scopes: Mapped[list[Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
