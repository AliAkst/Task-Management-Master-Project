from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.task import TaskPriority, TaskStatus

from .base import Base, TimestampMixin


class TaskEntity(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(SQLEnum(TaskStatus))
    priority: Mapped[TaskPriority] = mapped_column(SQLEnum(TaskPriority))
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
