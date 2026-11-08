from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.config import settings


class UTCDateTime(TypeDecorator[datetime]):
    """SQLite timezone'u kaybeder; okurken UTC olarak isaretle (task-api ile ayni)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect):
        return value.astimezone(UTC) if value is not None and value.tzinfo else value

    def process_result_value(self, value: datetime | None, dialect: Dialect):
        return (
            value.replace(tzinfo=UTC)
            if value is not None and value.tzinfo is None
            else value
        )


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ConversationEntity(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    # task-api'deki kullanici id'si (FK yok: ayri servis / ayri veritabani)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(200), default="Yeni sohbet")
    summary: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # uzun sohbet ozeti (ileride)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_now, index=True
    )


class MessageEntity(Base):
    """
    Saglayicidan bagimsiz mesaj. Arac cagrilari ve sonuclari da saklanir ki
    gecmis modele aynen tekrar verilebilsin.
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user|assistant|tool
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Gizlilik: local modelle uretilen mesajlar (local_only veri icerebilir)
    # bulut modele asla gonderilmez.
    is_local: Mapped[bool] = mapped_column(Boolean, default=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class AiActionEntity(Base):
    """
    AI'in yazma islemi (oneri ya da yapilmis). Onay akisinin ve denetim kaydinin
    temeli; ret nedenleri AI'in tercihlerini ogrenmesi icin sinyal (Faz 6).
    status: proposed | executed | rejected | failed
    """

    __tablename__ = "ai_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tool_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action_type: Mapped[str] = mapped_column(String(50))
    # task-api'ye gidecek, onceden cozulmus/dogrulanmis argumanlar
    args: Mapped[dict[str, Any]] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(Text)  # kullaniciya gosterilen ozet
    status: Mapped[str] = mapped_column(String(20), default="proposed", index=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    user_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AiPermissionEntity(Base):
    """Islem turu basina kullanicinin secimi: ask | auto | never (varsayilan ask)."""

    __tablename__ = "ai_permissions"
    __table_args__ = (UniqueConstraint("user_id", "action_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    action_type: Mapped[str] = mapped_column(String(50))
    mode: Mapped[str] = mapped_column(String(10), default="ask")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class UserFactEntity(Base):
    """
    Asistanin kullanici hakkinda bildikleri (seni tanimasi). Kullanici profil
    ekraninda gorur, duzeltir, siler. is_private: bulut modellere gonderilmez
    (saglik ve iliski kategorilerinde varsayilan).
    source: ai_learned | user_entered
    """

    __tablename__ = "user_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="ai_learned")
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class ProviderConfigEntity(Base):
    """
    Kullanicinin bagladigi bulut saglayicisi (kullanici basina saglayici basina tek).
    provider: anthropic | openai | gemini. API anahtari Fernet ile sifreli
    (app/security.py); API yanitlarinda asla geri donmez.
    models: kullanicinin bu saglayicida kullanmak istedigi model adlari.
    """

    __tablename__ = "provider_configs"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    provider: Mapped[str] = mapped_column(String(30))
    api_key_encrypted: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(10))  # "…ab12"
    base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    models: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class ModelPrefEntity(Base):
    """
    Kullanicinin model tercihleri (gorev bazli yonlendirme).
    default_model_id: sohbet varsayilani, SADECE local olabilir.
    background_model_id: arka plan isleri (gun sonu plani, haftalik analiz);
    None = config'teki buyuk local model. Bulut secilebilir (kullanici uyarilir).
    """

    __tablename__ = "model_prefs"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    default_model_id: Mapped[str] = mapped_column(String(200))
    background_model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class AiJobEntity(Base):
    """
    Arka plan isi (Faz 6). kind: day_review (gun ozeti + ertesi gun plan onerisi).
    status: queued -> running -> done | failed. result: uretilen ozet, plan
    maddeleri ve gerekceleri; onerilen plan ai_actions'ta (action_id).
    """

    __tablename__ = "ai_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(30))
    target_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    status: Mapped[str] = mapped_column(String(20), default="queued")
    model_id: Mapped[str] = mapped_column(String(200))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


engine = create_async_engine(settings.database_url)
session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    async with session_maker() as session:
        yield session
