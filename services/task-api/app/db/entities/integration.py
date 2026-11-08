from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UTCDateTime


class IntegrationAccountEntity(Base, TimestampMixin):
    """
    Disa bagli hesap (Faz 7): kullanici basina saglayici basina tek kayit.
    tokens_encrypted: Fernet ile sifreli JSON (Trello: key/token; OAuth: access/refresh).
    settings: secili takvim/liste id'leri, senkron/delta token'lari.
    """

    __tablename__ = "integration_accounts"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20))  # trello / google / microsoft
    account_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tokens_encrypted: Mapped[str] = mapped_column(Text)
    scopes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/error
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExternalLinkEntity(Base, TimestampMixin):
    """
    Yerel kayit <-> dis sistemdeki kayit baglantisi. Her tabloya kolon eklemek
    yerine genel tablo. pending_push: yerel degisiklik dis sisteme henuz yazilmadi.
    """

    __tablename__ = "external_links"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "entity_type", "external_id"),
        Index("ix_external_links_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20))
    # board / list / card / event / note / checklist_item
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[int] = mapped_column()
    external_id: Mapped[str] = mapped_column(String(200))
    external_parent_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    etag: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    pending_push: Mapped[bool] = mapped_column(Boolean, default=False)
    push_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
