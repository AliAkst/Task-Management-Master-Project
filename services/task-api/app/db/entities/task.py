from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.task import TaskPriority, TaskStatus

from .base import Base, TimestampMixin, UTCDateTime


class TaskEntity(Base, TimestampMixin):
    """
    Kart (gorev). Tablo adi geriye uyumluluk icin "tasks" olarak kaldi;
    eski /tasks API'si ve yeni /cards API'si ayni tabloyu kullanir.
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(SQLEnum(TaskStatus))
    priority: Mapped[TaskPriority] = mapped_column(SQLEnum(TaskPriority))
    due_date: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )

    # --- Kanban alanlari (Faz 1a) ---
    board_id: Mapped[int | None] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"), nullable=True, index=True
    )
    list_id: Mapped[int | None] = mapped_column(
        ForeignKey("board_lists.id", ondelete="SET NULL"), nullable=True, index=True
    )
    position: Mapped[float] = mapped_column(Float, default=0)
    start_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(20), default="user")
