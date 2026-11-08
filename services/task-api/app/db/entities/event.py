from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UTCDateTime


class EventEntity(Base, TimestampMixin):
    """
    Takvim etkinligi = "ne zaman". Karta bagliysa o kart icin ayrilmis zaman
    blogudur (orn. "Bolum 2'yi Sali 19-21'de calis"); bagli degilse bagimsiz
    etkinliktir (orn. date, toplanti).

    Tum gun etkinlikleri kullanicinin yerel gece yarisindan baslayip ertesi
    gece yarisinda biter (end_at haric / exclusive), UTC olarak saklanir.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    board_id: Mapped[int | None] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"), nullable=True, index=True
    )
    card_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # RRULE (Faz 6c): tek satir; takvim tekrarlari sorgu aninda acar
    recurrence_rule: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str] = mapped_column(String(20), default="user")
