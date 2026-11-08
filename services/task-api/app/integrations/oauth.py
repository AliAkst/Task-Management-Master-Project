"""
Saglayicidan bagimsiz OAuth 2.0 (Faz 7b; 7c Microsoft'u ayni yoldan kullanir).

Akis:
1. connect_url(): arayuz POST /integrations/{provider}/connect -> authorize_url.
   `state` = 10 dk gecerli, imzali JWT (user_id + provider). Callback'te auth
   header yoktur; kullaniciyi yalnizca state belirler, bu yuzden sahteciligi
   (imza, sure, saglayici eslesmesi) reddedilir.
2. handle_callback(): code -> token degisimi, sifreli kayit.
3. ensure_fresh_token(): bitise <60 sn kala yeniler; `invalid_grant` -> hesap
   `error` durumuna alinir ("Yeniden bagla").

Uygulama kimligi (client id/secret) kullanici basinadir: once arayuzdeki kurulum
sihirbazindan girilen (`oauth_clients`, sir sifreli), yoksa `.env`'deki
GOOGLE_/MICROSOFT_CLIENT_ID/SECRET.
"""

import base64
import json
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from pydantic import BaseModel, Field

from app.config import settings
from app.core import crypto
from app.core.exceptions import ValidationException
from app.core.logging import get_logger
from app.db.entities import IntegrationAccountEntity, OAuthClientEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.integrations.accounts import IntegrationAccountService, has_calendar_scope
from app.integrations.base import IntegrationError

logger = get_logger(__name__)

# Testlerde sahte ag icin degistirilir (httpx.MockTransport)
HTTP_TRANSPORT: httpx.AsyncBaseTransport | None = None
STATE_TTL = timedelta(minutes=10)
REFRESH_MARGIN_SEC = 60


@dataclass(frozen=True)
class OAuthProvider:
    name: str
    label: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    client_id_setting: str
    client_secret_setting: str
    extra_authorize_params: dict[str, str] = field(default_factory=dict)

    @property
    def env_client_id(self) -> str | None:
        return getattr(settings, self.client_id_setting) or None

    @property
    def env_client_secret(self) -> str | None:
        return getattr(settings, self.client_secret_setting) or None

    @property
    def redirect_uri(self) -> str:
        base = settings.api_base_url.rstrip("/")
        return f"{base}{settings.api_v1_prefix}/integrations/{self.name}/callback"


PROVIDERS: dict[str, OAuthProvider] = {
    "google": OAuthProvider(
        name="google",
        label="Google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=(
            "openid",
            "email",
            "https://www.googleapis.com/auth/calendar.readonly",
        ),
        client_id_setting="google_client_id",
        client_secret_setting="google_client_secret",
        # offline + consent: her baglanista refresh token verilsin
        extra_authorize_params={"access_type": "offline", "prompt": "consent"},
    ),
    # Faz 7c: kisisel Microsoft hesaplari (Samsung Reminder -> To Do)
    "microsoft": OAuthProvider(
        name="microsoft",
        label="Microsoft",
        authorize_url="https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
        scopes=(
            "openid",
            "email",
            "offline_access",
            "User.Read",
            "Tasks.ReadWrite",
            "Calendars.Read",  # Faz 8d: Teams/Outlook toplantilari
        ),
        client_id_setting="microsoft_client_id",
        client_secret_setting="microsoft_client_secret",
        extra_authorize_params={"response_mode": "query"},
    ),
}


def get_provider(name: str) -> OAuthProvider:
    provider = PROVIDERS.get(name)
    if provider is None:
        raise IntegrationError(
            f"'{name}' için OAuth bağlantısı yok",
            "OAUTH_PROVIDER_UNKNOWN",
            status_code=404,
        )
    return provider


# ---------------- uygulama kimligi (client id / secret) ----------------
@dataclass(frozen=True)
class OAuthClient:
    client_id: str
    client_secret: str
    source: str  # "app" (arayuzden girildi) | "env" (.env)


class OAuthClientInfo(BaseModel):
    """Arayuzdeki kurulum sihirbazi icin; sir hicbir zaman donmez."""

    provider: str
    configured: bool
    source: str | None  # app / env / None
    client_id: str | None
    redirect_uri: str


class OAuthClientSave(BaseModel):
    client_id: str = Field(min_length=1, max_length=300)
    client_secret: str = Field(min_length=1, max_length=500)


_GUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def validate_client(provider: str, client_id: str, client_secret: str) -> tuple[str, str]:
    """Bicim denetimi + sik yapilan kopyalama hatalarina yol gosteren mesajlar."""
    client_id, client_secret = client_id.strip(), client_secret.strip()
    if not client_id or not client_secret:
        raise ValidationException("İstemci kimliği ve sırrı boş olamaz")
    if any(c.isspace() for c in client_id + client_secret):
        raise ValidationException(
            "Kimlik ya da sırda boşluk var; değeri eksiksiz ve tek parça kopyala"
        )
    if provider == "google":
        if not client_id.endswith(".apps.googleusercontent.com"):
            raise ValidationException(
                "Google istemci kimliği “….apps.googleusercontent.com” ile biter; "
                "Google Cloud → Clients sayfasındaki “Client ID”yi kopyala"
            )
        if client_secret.endswith(".apps.googleusercontent.com"):
            raise ValidationException(
                "Sır alanına istemci kimliği yapıştırılmış; “Client secret”ı kopyala"
            )
    elif provider == "microsoft":
        if not _GUID.match(client_id):
            raise ValidationException(
                "Microsoft istemci kimliği 8-4-4-4-12 biçiminde bir GUID’dir; uygulamanın "
                "Overview sayfasındaki “Application (client) ID”yi kopyala"
            )
        if _GUID.match(client_secret):
            raise ValidationException(
                "Bu “Secret ID” gibi görünüyor. Certificates & secrets sayfasında "
                "“Value” sütunundaki değeri kopyala (yalnızca oluşturulduğu an görünür)"
            )
    return client_id, client_secret


async def resolve_client(
    uow: TaskUnitOfWork, user_id: int, provider: OAuthProvider
) -> OAuthClient | None:
    saved = await uow.oauth_clients.get_for_provider(user_id, provider.name)
    if saved is not None:
        try:
            secret = crypto.decrypt(saved.client_secret_encrypted)
        except crypto.SecretError:
            secret = None  # ana anahtar degismis: yeniden girilmeli
        if secret:
            return OAuthClient(saved.client_id, secret, "app")
    if provider.env_client_id and provider.env_client_secret:
        return OAuthClient(provider.env_client_id, provider.env_client_secret, "env")
    return None


async def require_client(
    uow: TaskUnitOfWork, user_id: int, provider: OAuthProvider
) -> OAuthClient:
    client = await resolve_client(uow, user_id, provider)
    if client is None:
        raise IntegrationError(
            f"{provider.label} bağlantısı için önce uygulama kimliğini gir: "
            f"Ayarlar → Bağlantılar → {provider.label} → “Kurulumu başlat”.",
            "OAUTH_NOT_CONFIGURED",
            status_code=422,
        )
    return client


async def client_info(
    uow: TaskUnitOfWork, user_id: int, provider_name: str
) -> OAuthClientInfo:
    provider = get_provider(provider_name)
    client = await resolve_client(uow, user_id, provider)
    return OAuthClientInfo(
        provider=provider.name,
        configured=client is not None,
        source=client.source if client else None,
        client_id=client.client_id if client else None,
        redirect_uri=provider.redirect_uri,
    )


async def save_client(
    uow: TaskUnitOfWork, user_id: int, provider_name: str, data: OAuthClientSave
) -> OAuthClientInfo:
    provider = get_provider(provider_name)
    client_id, secret = validate_client(provider.name, data.client_id, data.client_secret)
    saved = await uow.oauth_clients.get_for_provider(user_id, provider.name)
    if saved is None:
        await uow.oauth_clients.create(
            OAuthClientEntity(
                user_id=user_id,
                provider=provider.name,
                client_id=client_id,
                client_secret_encrypted=crypto.encrypt(secret),
            )
        )
    else:
        saved.client_id = client_id
        saved.client_secret_encrypted = crypto.encrypt(secret)
    await uow.commit()
    return await client_info(uow, user_id, provider.name)


async def delete_client(uow: TaskUnitOfWork, user_id: int, provider_name: str) -> None:
    """Arayuzden girilen kimligi siler (varsa .env'deki yine kullanilir)."""
    provider = get_provider(provider_name)
    saved = await uow.oauth_clients.get_for_provider(user_id, provider.name)
    if saved is not None:
        await uow.oauth_clients.delete(saved)
        await uow.commit()


# ---------------- state ----------------
def make_state(user_id: int, provider: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "provider": provider,
            "purpose": "oauth_state",
            "exp": now + STATE_TTL,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def read_state(state: str, provider: str) -> int:
    """State'i dogrular, user_id dondurur. Gecersiz/suresi dolmus/yanlis saglayici -> hata."""
    try:
        payload = jwt.decode(
            state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("purpose") != "oauth_state" or payload.get("provider") != provider:
            raise ValueError("state uyumsuz")
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as e:
        raise IntegrationError(
            "Bağlantı isteği geçersiz ya da süresi dolmuş; tekrar dene.",
            "OAUTH_STATE_INVALID",
            status_code=400,
        ) from e


async def connect_url(uow: TaskUnitOfWork, user_id: int, provider_name: str) -> str:
    provider = get_provider(provider_name)
    client = await require_client(uow, user_id, provider)
    params = {
        "client_id": client.client_id,
        "redirect_uri": provider.redirect_uri,
        "response_type": "code",
        "scope": " ".join(provider.scopes),
        "state": make_state(user_id, provider.name),
        **provider.extra_authorize_params,
    }
    # Zaten bagli ama takvim izni olmayan Microsoft hesabi: yeni kapsam icin
    # onay ekrani zorlanir (aksi halde izin verilmis sayilip atlanabilir)
    if provider.name == "microsoft":
        existing = await uow.integration_accounts.get_for_provider(
            user_id, provider.name
        )
        if existing is not None and not has_calendar_scope(existing.scopes):
            params["prompt"] = "consent"
    return f"{provider.authorize_url}?{urlencode(params)}"


# ---------------- token istekleri ----------------
async def _token_request(
    provider: OAuthProvider, client: OAuthClient, data: dict[str, str]
) -> dict[str, Any]:
    body = {
        "client_id": client.client_id,
        "client_secret": client.client_secret,
        **data,
    }
    try:
        async with httpx.AsyncClient(timeout=20, transport=HTTP_TRANSPORT) as http:
            res = await http.post(provider.token_url, data=body)
    except httpx.HTTPError as e:
        raise IntegrationError(
            f"{provider.label} sunucusuna ulaşılamadı; biraz sonra tekrar dene.",
            "OAUTH_UNREACHABLE",
        ) from e
    try:
        payload = res.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if res.status_code >= 400:
        error = payload.get("error")
        if error in ("invalid_client", "unauthorized_client"):
            raise IntegrationError(
                f"{provider.label} uygulama kimliğini ya da sırrını kabul etmedi. "
                "Ayarlar → Bağlantılar → “Kimlik bilgilerini değiştir” ile kontrol et "
                "(Microsoft’ta sırrın “Value” değeri olmalı ve süresi dolmamış olmalı).",
                "OAUTH_INVALID_CLIENT",
                status_code=400,
            )
        if error == "redirect_uri_mismatch":
            raise IntegrationError(
                f"Yönlendirme adresi eşleşmiyor. {provider.label} uygulamasına tam olarak "
                f"şunu ekle: {provider.redirect_uri}",
                "OAUTH_REDIRECT_MISMATCH",
                status_code=400,
            )
        description = payload.get("error_description")
        detail = (
            f": {str(description).splitlines()[0][:200]}"
            if description and error != "invalid_grant"
            else ""
        )
        raise IntegrationError(
            f"{provider.label} yetkilendirmeyi reddetti ({error or res.status_code}){detail}.",
            "OAUTH_INVALID_GRANT" if error == "invalid_grant" else "OAUTH_FAILED",
            status_code=400 if error == "invalid_grant" else 502,
        )
    return payload


def _email_from_id_token(id_token: str | None) -> str | None:
    """Token dogrudan saglayicidan TLS ile geldigi icin imza dogrulanmaz; sadece etiket."""
    if not id_token:
        return None
    try:
        payload_b64 = id_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        # Google: email; kisisel Microsoft hesabi: genelde preferred_username
        return payload.get("email") or payload.get("preferred_username")
    except (IndexError, ValueError):
        return None


def _stored_tokens(payload: dict[str, Any], old_refresh: str | None = None) -> dict:
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token") or old_refresh,
        "expires_at": time.time() + int(payload.get("expires_in", 3600)),
    }


async def handle_callback(
    uow: TaskUnitOfWork, provider_name: str, code: str, state: str
) -> IntegrationAccountEntity:
    provider = get_provider(provider_name)
    user_id = read_state(state, provider.name)
    client = await require_client(uow, user_id, provider)
    payload = await _token_request(
        provider,
        client,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": provider.redirect_uri,
        },
    )
    accounts = IntegrationAccountService(uow)
    old_refresh = None
    existing = await uow.integration_accounts.get_for_provider(user_id, provider.name)
    if existing is not None:
        try:
            old_refresh = accounts.tokens(existing).get("refresh_token")
        except Exception:  # noqa: BLE001 - eski anahtar cozulemiyorsa yeni token yeter
            old_refresh = None
    tokens = _stored_tokens(payload, old_refresh)
    if not tokens["refresh_token"]:
        raise IntegrationError(
            "Yenileme anahtarı alınamadı; bağlantıyı yeniden kurmayı dene.",
            "OAUTH_NO_REFRESH_TOKEN",
        )
    return await accounts.save(
        user_id,
        provider.name,
        tokens,
        account_label=_email_from_id_token(payload.get("id_token")),
        scopes=payload.get("scope") or " ".join(provider.scopes),
    )


async def ensure_fresh_token(uow: TaskUnitOfWork, account: IntegrationAccountEntity) -> str:
    """Gecerli access token dondurur; gerekirse yeniler ve sifreli kaydeder."""
    accounts = IntegrationAccountService(uow)
    tokens = accounts.tokens(account)
    if tokens.get("expires_at", 0) - time.time() > REFRESH_MARGIN_SEC:
        return tokens["access_token"]

    provider = get_provider(account.provider)
    client = await require_client(uow, account.user_id, provider)
    try:
        payload = await _token_request(
            provider,
            client,
            {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]},
        )
    except IntegrationError as e:
        if e.error_code in ("OAUTH_INVALID_GRANT", "OAUTH_INVALID_CLIENT"):
            account.status = "error"
            account.last_error = (
                "Yeniden bağlan: erişim izni geri alınmış ya da süresi dolmuş."
                if e.error_code == "OAUTH_INVALID_GRANT"
                # Kimlik degistiyse eski refresh token yeni istemciyle calismaz
                else "Yeniden bağlan: uygulama kimliği değişmiş ya da sırrın süresi dolmuş."
            )
            await uow.commit()
            raise IntegrationError(
                account.last_error, "INTEGRATION_RECONNECT", status_code=409
            ) from e
        raise
    new_tokens = _stored_tokens(payload, tokens.get("refresh_token"))
    account.tokens_encrypted = crypto.encrypt_json(new_tokens)
    await uow.commit()
    return new_tokens["access_token"]
