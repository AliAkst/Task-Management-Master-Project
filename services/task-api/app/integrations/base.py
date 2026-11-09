"""Entegrasyonlar icin ortak tipler (Faz 7)."""

import asyncio
from dataclasses import dataclass, field

from app.core.exceptions import AppException


class IntegrationError(AppException):
    """Dis servis hatasi (ulasilamadi, yetki reddedildi...)."""

    def __init__(
        self, message: str, error_code: str = "INTEGRATION_ERROR", status_code: int = 502
    ):
        super().__init__(status_code=status_code, error_code=error_code, message=message)


class IntegrationNotConnected(AppException):
    def __init__(self, provider: str):
        super().__init__(
            status_code=404,
            error_code="INTEGRATION_NOT_CONNECTED",
            message=f"{provider} bağlı değil",
        )


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)


# Ayni kullanici/saglayici icin ayni anda tek senkron/import
_locks: dict[tuple[int, str], asyncio.Lock] = {}


def lock_for(user_id: int, provider: str) -> asyncio.Lock:
    return _locks.setdefault((user_id, provider), asyncio.Lock())
