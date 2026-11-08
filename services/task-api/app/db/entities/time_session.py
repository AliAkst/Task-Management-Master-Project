from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UTCDateTime


class TimeSessionEntity(Base, TimestampMixin):
    """
    Kronometre / elle girilen calisma suresi.

    - ended_at NULL = calisan oturum. Kullanici basina en fazla bir tane
      (partial unique index; servis de yenisini baslatirken eskisini durdurur).
    - Kart silinirse oturum silinmez (card_id NULL olur); board_id ve
      card_title snapshot'lari sayesinde istatistikler bozulmaz.
    """

    __tablename__ = "time_sessions"
    __table_args__ = (
        Index(
            "uq_time_sessions_one_active_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("ended_at IS NULL"),
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    card_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Snapshot'lar (FK degil): kart silinse / tasinsa da gecmis dogru kalir
    board_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    card_title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="timer")  # timer|manual
