from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """
    Her zaman timezone'lu (UTC) datetime donduren kolon tipi.

    SQLite timezone bilgisini saklamaz; okunan deger "naive" gelir ve API'de
    'Z' olmadan serialize edilince tarayici onu yerel saat sanar (3 saat kayma).
    Bu tip yazarken UTC'ye cevirir, okurken UTC olarak isaretler.
    PostgreSQL'de zaten timezone'lu doner; orada davranis degismez.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(UTC)
        return value

    def process_result_value(self, value: datetime | None, dialect: Dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )
