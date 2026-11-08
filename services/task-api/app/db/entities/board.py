import enum

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class BoardPrivacy(str, enum.Enum):
    """Board verisinin hangi AI modellerine gidebilecegi."""

    CLOUD_ALLOWED = "cloud_allowed"  # Claude/GPT gibi cloud modeller gorebilir
    LOCAL_ONLY = "local_only"  # sadece local model (Ollama) gorebilir


class BoardEntity(Base, TimestampMixin):
    """
    Hayatin bir alani (Spor, Is, Egitim...).

    scope_description: bu alana hangi islerin ait oldugunu anlatir; AI gelen
    isleri dogru board'a yerlestirirken bunu kullanir ("alanin sinirlari").
    """

    __tablename__ = "boards"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    scope_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(20), default="#64748b")
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    position: Mapped[float] = mapped_column(Float, default=0)
    weekly_time_budget_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    privacy: Mapped[BoardPrivacy] = mapped_column(
        SQLEnum(BoardPrivacy), default=BoardPrivacy.CLOUD_ALLOWED
    )
    # Bu board'da asistanin varsayilan modeli ("ollama:qwen3.5:4b",
    # "anthropic:claude-sonnet-5-5"...). Bos: kullanicinin (local) varsayilani.
    # local_only board'da sadece local model olabilir.
    default_model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    # Sistem board'u: NULL = normal, "inbox" = Gelen Kutusu (silinemez)
    system_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)


class BoardListEntity(Base, TimestampMixin):
    """Kanban kolonu. is_done_list=True olan listeye tasinan kart tamamlanir."""

    __tablename__ = "board_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    board_id: Mapped[int] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    position: Mapped[float] = mapped_column(Float, default=0)
    is_done_list: Mapped[bool] = mapped_column(Boolean, default=False)


class LabelEntity(Base, TimestampMixin):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    board_id: Mapped[int] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(50))
    color: Mapped[str] = mapped_column(String(20), default="#64748b")


class CardLabelEntity(Base):
    """Kart <-> etiket coka-cok iliskisi."""

    __tablename__ = "card_labels"

    card_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    label_id: Mapped[int] = mapped_column(
        ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True
    )
