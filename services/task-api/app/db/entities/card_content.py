from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class CardNoteEntity(Base, TimestampMixin):
    """Kart icindeki not akisi (markdown). Kart aciklamasindan ayri, zaman damgali."""

    __tablename__ = "card_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    card_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)


class ChecklistItemEntity(Base, TimestampMixin):
    """Kart icindeki kucuk adimlar (sure tutulmayan)."""

    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    card_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(String(500))
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[float] = mapped_column(Float, default=0)


class CardDependencyEntity(Base, TimestampMixin):
    """
    Kartlar arasi "ip": card_id, depends_on_id bitmeden baslayamaz.
    Grafik yonlu ve dongusuz (DAG) tutulur; dongu servis katmaninda engellenir.
    """

    __tablename__ = "card_dependencies"
    __table_args__ = (UniqueConstraint("card_id", "depends_on_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    card_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    depends_on_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )


class CardAttachmentEntity(Base, TimestampMixin):
    """
    Karta eklenen dosya (Faz 8c). Icerik diskte (storage_key), satir yalniz meta.
    note_id: dosya bir notun icinden yuklendiyse o not (not silinince NULL olur).
    """

    __tablename__ = "card_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    card_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    note_id: Mapped[int | None] = mapped_column(
        ForeignKey("card_notes.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
