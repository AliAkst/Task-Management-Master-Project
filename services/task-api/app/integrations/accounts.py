"""Entegrasyon hesaplari: sifreli saklama, listeleme, kaldirma."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.core import crypto
from app.db.entities import IntegrationAccountEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.integrations.base import IntegrationNotConnected


class IntegrationResponse(BaseModel):
    provider: str
    account_label: str | None
    status: str
    scopes: str | None
    last_synced_at: datetime | None
    last_error: str | None
    # Yalnizca son 4 karakter; gizli degerler arayuze hic donmez
    masked_credentials: dict[str, str]
    settings: dict[str, Any] | None = None
    # Yalniz Microsoft: Calendars.Read izni verilmis mi (Faz 8d)
    calendar_consent: bool | None = None


CALENDAR_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "teams_only": True,
    "board_id": None,
    "weeks_ahead": 2,
}


def has_calendar_scope(scopes: str | None) -> bool:
    """Kayitli kapsam dizgesinde Calendars.Read(Write) var mi ("https://.../X" da olur)."""
    for scope in (scopes or "").split():
        name = scope.rsplit("/", 1)[-1].lower()
        if name in ("calendars.read", "calendars.readwrite"):
            return True
    return False


def _masked(tokens: dict[str, Any]) -> dict[str, str]:
    return {
        k: crypto.mask(v)
        for k, v in tokens.items()
        if isinstance(v, str) and k in {"api_key", "token", "access_token"}
    }


def to_response(account: IntegrationAccountEntity) -> IntegrationResponse:
    try:
        masked = _masked(crypto.decrypt_json(account.tokens_encrypted))
    except crypto.SecretError:
        masked = {}
    settings = account.settings
    consent: bool | None = None
    if account.provider == "microsoft":
        consent = has_calendar_scope(account.scopes)
        settings = {
            **(settings or {}),
            "calendar": {**CALENDAR_DEFAULTS, **((settings or {}).get("calendar") or {})},
        }
    return IntegrationResponse(
        provider=account.provider,
        account_label=account.account_label,
        status=account.status,
        scopes=account.scopes,
        last_synced_at=account.last_synced_at,
        last_error=account.last_error,
        masked_credentials=masked,
        settings=settings,
        calendar_consent=consent,
    )


class IntegrationAccountService:
    def __init__(self, uow: TaskUnitOfWork):
        self.uow = uow

    async def list(self, user_id: int) -> list[IntegrationResponse]:
        accounts = await self.uow.integration_accounts.list_for_user(user_id)
        return [to_response(a) for a in accounts]

    async def get(self, user_id: int, provider: str) -> IntegrationAccountEntity:
        account = await self.uow.integration_accounts.get_for_provider(
            user_id, provider
        )
        if account is None:
            raise IntegrationNotConnected(provider)
        return account

    def tokens(self, account: IntegrationAccountEntity) -> dict[str, Any]:
        """Sifreyi cozer; ana anahtar degismisse SecretError (arayuze 'yeniden bagla')."""
        return crypto.decrypt_json(account.tokens_encrypted)

    async def save(
        self,
        user_id: int,
        provider: str,
        tokens: dict[str, Any],
        *,
        account_label: str | None = None,
        scopes: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> IntegrationAccountEntity:
        """Hesabi olusturur ya da yeniden baglar (token degisir, ayarlar korunur)."""
        account = await self.uow.integration_accounts.get_for_provider(
            user_id, provider
        )
        encrypted = crypto.encrypt_json(tokens)
        if account is None:
            account = IntegrationAccountEntity(
                user_id=user_id,
                provider=provider,
                tokens_encrypted=encrypted,
                account_label=account_label,
                scopes=scopes,
                status="active",
                settings=settings,
            )
            await self.uow.integration_accounts.create(account)
        else:
            account.tokens_encrypted = encrypted
            account.account_label = account_label
            account.scopes = scopes
            account.status = "active"
            account.last_error = None
            if settings is not None:
                account.settings = settings
        # Entegrasyondan gelen isler icin Gelen Kutusu hazir olsun
        from app.services.board import BoardService

        await BoardService(self.uow).get_or_create_inbox(user_id)
        await self.uow.session.commit()
        return account

    async def remove(self, user_id: int, provider: str) -> None:
        """Hesabi ve baglantilari siler; ice aktarilmis kartlar/board'lar kalir."""
        account = await self.get(user_id, provider)
        await self.uow.external_links.delete_for_provider(user_id, provider)
        await self.uow.integration_accounts.delete(account)
        await self.uow.session.commit()
