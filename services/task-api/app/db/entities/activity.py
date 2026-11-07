from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UTCDateTime


class ActivityLogEntity(Base):
    """
    Her degisikligin kaydi (append-only). Istatistiklerin ve AI'in kullanicinin
    davranislarini ogrenmesinin ham verisi.

    card_id / board_id bilerek FK DEGIL: kart/board silinse de gecmis kalir.
    """

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(30))  # card, board, list, ...
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(30))  # created, moved, completed, ...
    board_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    card_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # {"alan": [eski, yeni]} formatinda degisiklikler ya da ek baglam
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    actor: Mapped[str] = mapped_column(
        String(20), default="user"
    )  # user|ai|integration
    occurred_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), index=True
    )
