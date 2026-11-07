from datetime import time

from sqlalchemy import ForeignKey, SmallInteger, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class UserSettingsEntity(Base, TimestampMixin):
    """
    Kullanici tercihleri. Kullanici basina tek satir (user_id UNIQUE).

    - timezone: "gun" hesaplari (gun sonu degerlendirmesi, takvim) bu dilime
      gore yapilir
    - planning_time / review_time: kullanicinin sectigi saatler
      (bos ise hatirlatma yok)
    """

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Istanbul")
    planning_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    review_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    reminders_enabled: Mapped[bool] = mapped_column(default=True)
    # 0 = Pazartesi ... 6 = Pazar
    week_start: Mapped[int] = mapped_column(SmallInteger, default=0)
