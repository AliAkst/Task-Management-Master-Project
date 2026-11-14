from datetime import time

from sqlalchemy import JSON, ForeignKey, SmallInteger, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class DayTemplateEntity(Base, TimestampMixin):
    """
    Gun sablonu (Faz 13c): "Ofis gunu / Ev gunu" iskeleti.
    weekdays: 0=Pzt..6=Paz; blocks: [{title, start, end, kind}] (saate gore sirali).
    """

    __tablename__ = "day_templates"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    weekdays: Mapped[list] = mapped_column(JSON, default=list)
    blocks: Mapped[list] = mapped_column(JSON, default=list)
    day_start: Mapped[time] = mapped_column(
        Time, default=time(8, 0), server_default="08:00:00"
    )
    day_end: Mapped[time] = mapped_column(
        Time, default=time(23, 0), server_default="23:00:00"
    )
    buffer_min: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0"
    )
