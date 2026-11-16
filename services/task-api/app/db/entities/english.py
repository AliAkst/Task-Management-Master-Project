from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UTCDateTime


class EnglishProfileEntity(Base, TimestampMixin):
    """Ingilizce kocu profili (Faz 13j1): kullanici basina tek."""

    __tablename__ = "english_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    target_level: Mapped[str] = mapped_column(String(2))
    current_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    daily_minutes: Mapped[int] = mapped_column(SmallInteger)
    focus: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[date] = mapped_column(Date)


class EnglishMistakeEntity(Base):
    __tablename__ = "english_mistakes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(10))
    original: Mapped[str] = mapped_column(Text)
    corrected: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(20))
    explanation_tr: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)


class EnglishVocabEntity(Base):
    """Kelime karti (SM-2). Kullanici basina term_key tekil."""

    __tablename__ = "english_vocab"
    __table_args__ = (UniqueConstraint("user_id", "term_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    term: Mapped[str] = mapped_column(String(100))
    term_key: Mapped[str] = mapped_column(String(100))
    meaning_tr: Mapped[str] = mapped_column(String(300))
    example: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(10))
    ease: Mapped[float] = mapped_column(Float, default=2.5, server_default="2.5")
    interval_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reps: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lapses: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    due_on: Mapped[date] = mapped_column(Date, index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


class EnglishSessionEntity(Base):
    __tablename__ = "english_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    minutes: Mapped[int] = mapped_column(SmallInteger)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_vocab: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    mistakes_count: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0"
    )
    source: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
