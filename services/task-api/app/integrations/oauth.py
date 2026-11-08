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
"""

import base64
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.config import settings
from app.core.logging import get_logger
from app.db.entities import IntegrationAccountEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.integrations.accounts import IntegrationAccountService
from app.integrations.base import IntegrationError

logger = get_logger(__name__)

# Testlerde sahte ag icin degistirilir (httpx.MockTransport)
HTTP_TRANSPORT: httpx.AsyncBaseTransport | None = None
STATE_TTL = timedelta(minutes=10)
REFRESH_MARGIN_SEC = 60


@dataclass(frozen=True)
class OAuthProvider:
    name: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    client_id_setting: str
    client_secret_setting: str
    extra_authorize_params: dict[str, str] = field(default_factory=dict)

    @property
    def client_id(self) -> str | None:
        return getattr(settings, self.client_id_setting)

    @property
    def client_secret(self) -> str | None:
        return getattr(settings, self.client_secret_setting)

    @property
    def redirect_uri(self) -> str:
        base = settings.api_base_url.rstrip("/")
        return f"{base}{settings.api_v1_prefix}/integrations/{self.name}/callback"


PROVIDERS: dict[str, OAuthProvider] = {
    "google": OAuthProvider(
        name="google",
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
        authorize_url="https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
        scopes=("openid", "email", "offline_access", "User.Read", "Tasks.ReadWrite"),
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


def _require_configured(provider: OAuthProvider) -> None:
    if not provider.client_id or not provider.client_secret:
        raise IntegrationError(
            f"{provider.name} için istemci kimliği/sırrı ayarlanmamış "
            f"(services/task-api/.env içinde {provider.client_id_setting.upper()} "
            f"ve {provider.client_secret_setting.upper()}).",
            "OAUTH_NOT_CONFIGURED",
            status_code=422,
        )


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


def connect_url(user_id: int, provider_name: str) -> str:
    provider = get_provider(provider_name)
    _require_configured(provider)
    params = {
        "client_id": provider.client_id,
        "redirect_uri": provider.redirect_uri,
        "response_type": "code",
        "scope": " ".join(provider.scopes),
        "state": make_state(user_id, provider.name),
        **provider.extra_authorize_params,
    }
    return f"{provider.authorize_url}?{urlencode(params)}"


# ---------------- token istekleri ----------------
async def _token_request(provider: OAuthProvider, data: dict[str, str]) -> dict[str, Any]:
    body = {
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        **data,
    }
    try:
        async with httpx.AsyncClient(timeout=20, transport=HTTP_TRANSPORT) as http:
            res = await http.post(provider.token_url, data=body)
    except httpx.HTTPError as e:
        raise IntegrationError(
            f"{provider.name} sunucusuna ulaşılamadı; biraz sonra tekrar dene.",
            "OAUTH_UNREACHABLE",
        ) from e
    try:
        payload = res.json()
    except ValueError:
        payload = {}
    if res.status_code >= 400:
        error = payload.get("error") if isinstance(payload, dict) else None
        raise IntegrationError(
            f"{provider.name} yetkilendirmeyi reddetti ({error or res.status_code}).",
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
    _require_configured(provider)
    user_id = read_state(state, provider.name)
    payload = await _token_request(
        provider,
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
    _require_configured(provider)
    try:
        payload = await _token_request(
            provider,
            {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]},
        )
    except IntegrationError as e:
        if e.error_code == "OAUTH_INVALID_GRANT":
            account.status = "error"
            account.last_error = "Yeniden bağlan: erişim izni geri alınmış ya da süresi dolmuş."
            await uow.commit()
            raise IntegrationError(
                account.last_error, "INTEGRATION_RECONNECT", status_code=409
            ) from e
        raise
    new_tokens = _stored_tokens(payload, tokens.get("refresh_token"))
    from app.core import crypto

    account.tokens_encrypted = crypto.encrypt_json(new_tokens)
    await uow.commit()
    return new_tokens["access_token"]
