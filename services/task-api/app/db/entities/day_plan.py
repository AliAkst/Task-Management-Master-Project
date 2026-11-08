import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UTCDateTime


class DayPlanStatus(str, enum.Enum):
    PLANNED = "planned"
    REVIEWED = "reviewed"


class ItemOutcome(str, enum.Enum):
    DONE = "done"
    PARTIAL = "partial"
    NOT_DONE = "not_done"
    POSTPONED = "postponed"


class DayPlanEntity(Base, TimestampMixin):
    """
    Bir gunun plani + gun sonu degerlendirmesi (ayni satir).
    date: kullanicinin saat dilimindeki takvim gunu.
    """

    __tablename__ = "day_plans"
    __table_args__ = (UniqueConstraint("user_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[DayPlanStatus] = mapped_column(
        SQLEnum(DayPlanStatus), default=DayPlanStatus.PLANNED
    )
    mood: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)  # 1-5
    energy: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)  # 1-5
    reflection: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # Faz 6
    planned_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class DayPlanItemEntity(Base, TimestampMixin):
    """
    Plandaki bir is. Snapshot alanlari (baslik, board, planlanan dakika,
    harcanan sure) sayesinde kart sonradan degisse/silinse de gecmis dogru kalir.
    was_planned=False: plansiz yapilan is (degerlendirmede eklenir).
    """

    __tablename__ = "day_plan_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    day_plan_id: Mapped[int] = mapped_column(
        ForeignKey("day_plans.id", ondelete="CASCADE"), index=True
    )
    card_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    board_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    was_planned: Mapped[bool] = mapped_column(Boolean, default=True)
    planned_start: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    planned_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[float] = mapped_column(Float, default=0)

    outcome: Mapped[ItemOutcome | None] = mapped_column(
        SQLEnum(ItemOutcome), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracked_sec: Mapped[int] = mapped_column(Integer, default=0)
    postponed_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
