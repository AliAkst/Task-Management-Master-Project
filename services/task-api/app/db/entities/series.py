from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class CardSeriesEntity(Base, TimestampMixin):
    """
    Ayni isin tekrarlari (Faz 6c): "Kosu" serisinin her tamamlanmasi ayri bir
    karttir (tasks.series_id + series_index). Kart tamamlaninca kural aktifse
    bir sonraki kart acilir. Kural durdurulsa da seri istatistik icin kalir.
    """

    __tablename__ = "card_series"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    board_id: Mapped[int | None] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    recurrence_rule: Mapped[str] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
