"""Entegrasyon endpoint'leri (Faz 7): hesaplar + Trello import."""

from dataclasses import asdict
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.api.dependencies import CurrentUserDep, get_unit_of_work
from app.config import settings
from app.core.exceptions import AppException
from app.db.unit_of_work import TaskUnitOfWork
from app.integrations import oauth
from app.integrations.accounts import (
    IntegrationAccountService,
    IntegrationResponse,
    to_response,
)
from app.integrations.base import IntegrationError
from app.integrations.google_calendar import (
    GoogleCalendarInfo,
    GoogleCalendarService,
    GoogleSettingsUpdate,
    SyncSummary,
)
from app.integrations.microsoft_todo import (
    MicrosoftSettingsUpdate,
    MicrosoftStatus,
    MicrosoftTodoService,
    TodoListInfo,
)
from app.integrations.trello import (
    TrelloBoardInfo,
    TrelloConnect,
    TrelloImportRequest,
    TrelloImportResult,
    TrelloService,
)
from app.models.common import ApiResponse

integrations_router = APIRouter(prefix="/integrations", tags=["Integrations"])


def _accounts(uow: TaskUnitOfWork = Depends(get_unit_of_work)):
    return IntegrationAccountService(uow)


def _trello(uow: TaskUnitOfWork = Depends(get_unit_of_work)):
    return TrelloService(uow)


@integrations_router.get("", response_model=ApiResponse[list[IntegrationResponse]])
async def list_integrations(
    user: CurrentUserDep, accounts: IntegrationAccountService = Depends(_accounts)
):
    """Bagli hesaplar (gizli degerler maskeli)."""
    return ApiResponse(success=True, data=await accounts.list(user.id))


def _google(uow: TaskUnitOfWork = Depends(get_unit_of_work)):
    return GoogleCalendarService(uow)


def _microsoft(uow: TaskUnitOfWork = Depends(get_unit_of_work)):
    return MicrosoftTodoService(uow)


# ---------------- OAuth uygulama kimligi (kurulum sihirbazi) ----------------
@integrations_router.get(
    "/oauth-clients", response_model=ApiResponse[list[oauth.OAuthClientInfo]]
)
async def oauth_clients(
    user: CurrentUserDep, uow: TaskUnitOfWork = Depends(get_unit_of_work)
):
    """Google/Microsoft icin uygulama kimligi girilmis mi + eklenecek yonlendirme adresi."""
    return ApiResponse(
        success=True,
        data=[await oauth.client_info(uow, user.id, p) for p in oauth.PROVIDERS],
    )


@integrations_router.put(
    "/{provider}/oauth-client", response_model=ApiResponse[oauth.OAuthClientInfo]
)
async def save_oauth_client(
    provider: str,
    data: oauth.OAuthClientSave,
    user: CurrentUserDep,
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
):
    """Kurulum sihirbazindan gelen client id/secret (sir sifreli saklanir, geri donmez)."""
    return ApiResponse(
        success=True, data=await oauth.save_client(uow, user.id, provider, data)
    )


@integrations_router.delete(
    "/{provider}/oauth-client", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_oauth_client(
    provider: str, user: CurrentUserDep, uow: TaskUnitOfWork = Depends(get_unit_of_work)
):
    await oauth.delete_client(uow, user.id, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@integrations_router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(
    provider: str,
    user: CurrentUserDep,
    accounts: IntegrationAccountService = Depends(_accounts),
    google: GoogleCalendarService = Depends(_google),
):
    """Baglantiyi kaldirir; ice aktarilmis kartlar kalir (Google etkinlikleri silinir)."""
    if provider == "google":
        await google.disconnect(user.id)
    else:
        await accounts.remove(user.id, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- OAuth (Google; 7c'de Microsoft) ----------------
class ConnectResponse(BaseModel):
    authorize_url: str


@integrations_router.post(
    "/{provider}/connect", response_model=ApiResponse[ConnectResponse]
)
async def oauth_connect(
    provider: str, user: CurrentUserDep, uow: TaskUnitOfWork = Depends(get_unit_of_work)
):
    """Saglayicinin izin ekraninin adresini dondurur (arayuz oraya yonlendirir)."""
    url = await oauth.connect_url(uow, user.id, provider)
    return ApiResponse(success=True, data=ConnectResponse(authorize_url=url))


@integrations_router.get("/{provider}/callback", include_in_schema=False)
async def oauth_callback(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    uow: TaskUnitOfWork = Depends(get_unit_of_work),
):
    """
    Saglayicinin yonlendirdigi adres (auth header YOK; kullaniciyi imzali `state`
    belirler). Sonucu arayuze sorgu parametresiyle bildirir.
    """
    base = f"{settings.web_base_url.rstrip('/')}/settings"
    try:
        if error and error != "access_denied":
            # Ornek: Microsoft AADSTS hatalari (yanlis hesap turu, yonlendirme adresi)
            detail = (error_description or error).splitlines()[0][:300]
            raise IntegrationError(
                f"{provider} bağlantıyı reddetti: {detail}",
                "OAUTH_PROVIDER_ERROR",
                status_code=400,
            )
        if error or not code or not state:
            raise IntegrationError(
                "İzin verilmedi ya da bağlantı iptal edildi.",
                "OAUTH_DENIED",
                status_code=400,
            )
        await oauth.handle_callback(uow, provider, code, state)
    except AppException as e:
        query = urlencode({"connect_error": provider, "message": e.message})
        return RedirectResponse(f"{base}?{query}#baglantilar", status_code=302)
    return RedirectResponse(f"{base}?connected={provider}#baglantilar", status_code=302)


@integrations_router.post(
    "/{provider}/sync", response_model=ApiResponse[SyncSummary]
)
async def sync_now(
    provider: str,
    user: CurrentUserDep,
    google: GoogleCalendarService = Depends(_google),
    microsoft: MicrosoftTodoService = Depends(_microsoft),
):
    """Elle 'Simdi senkronla' (Microsoft'ta once bekleyen geri yazmalar gider)."""
    if provider == "google":
        result = await google.sync(user.id)
    elif provider == "microsoft":
        result = await microsoft.sync(user.id)
    else:
        raise IntegrationError(
            f"'{provider}' için senkron yok", "SYNC_UNSUPPORTED", status_code=404
        )
    return ApiResponse(success=True, data=SyncSummary(**asdict(result)))


# ---------------- Microsoft To Do ----------------
@integrations_router.get(
    "/microsoft/lists", response_model=ApiResponse[list[TodoListInfo]]
)
async def microsoft_lists(
    user: CurrentUserDep, microsoft: MicrosoftTodoService = Depends(_microsoft)
):
    """To Do listeleri (senkronlananlar isaretli)."""
    return ApiResponse(success=True, data=await microsoft.list_lists(user.id))


@integrations_router.put(
    "/microsoft/settings", response_model=ApiResponse[IntegrationResponse]
)
async def microsoft_settings(
    data: MicrosoftSettingsUpdate,
    user: CurrentUserDep,
    microsoft: MicrosoftTodoService = Depends(_microsoft),
):
    """Senkronlanacak listeler (null = hepsi)."""
    return ApiResponse(
        success=True, data=to_response(await microsoft.update_settings(user.id, data))
    )


@integrations_router.get(
    "/microsoft/status", response_model=ApiResponse[MicrosoftStatus]
)
async def microsoft_status(
    user: CurrentUserDep, microsoft: MicrosoftTodoService = Depends(_microsoft)
):
    """Geri yazilmayi bekleyen / hata almis tamamlama sayisi."""
    return ApiResponse(success=True, data=await microsoft.status(user.id))


# ---------------- Google Takvim ----------------
@integrations_router.get(
    "/google/calendars", response_model=ApiResponse[list[GoogleCalendarInfo]]
)
async def google_calendars(
    user: CurrentUserDep, google: GoogleCalendarService = Depends(_google)
):
    """Hesaptaki takvimler (secili olanlar isaretli)."""
    return ApiResponse(success=True, data=await google.list_calendars(user.id))


@integrations_router.put(
    "/google/settings", response_model=ApiResponse[IntegrationResponse]
)
async def google_settings(
    data: GoogleSettingsUpdate,
    user: CurrentUserDep,
    google: GoogleCalendarService = Depends(_google),
):
    """Senkronlanacak takvimler ve (istege bagli) etkinliklerin dustugu board."""
    return ApiResponse(
        success=True, data=to_response(await google.update_settings(user.id, data))
    )


# ---------------- Trello ----------------
@integrations_router.put("/trello", response_model=ApiResponse[IntegrationResponse])
async def connect_trello(
    data: TrelloConnect, user: CurrentUserDep, service: TrelloService = Depends(_trello)
):
    """API key + token'i Trello'ya karsi dogrular, sifreli kaydeder."""
    account = await service.connect(user.id, data)
    return ApiResponse(success=True, data=to_response(account))


@integrations_router.get(
    "/trello/boards", response_model=ApiResponse[list[TrelloBoardInfo]]
)
async def trello_boards(
    user: CurrentUserDep, service: TrelloService = Depends(_trello)
):
    """Trello'daki acik board'lar (zaten ice aktarilanlar isaretli)."""
    return ApiResponse(success=True, data=await service.list_boards(user.id))


@integrations_router.post(
    "/trello/import", response_model=ApiResponse[list[TrelloImportResult]]
)
async def trello_import(
    data: TrelloImportRequest,
    user: CurrentUserDep,
    service: TrelloService = Depends(_trello),
):
    """Secilen board'lari tek seferlik alir; tekrar calistirmak sadece yenileri ekler."""
    return ApiResponse(
        success=True, data=await service.import_boards(user.id, data.board_ids)
    )
