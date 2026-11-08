"""Kart ekleri endpoint'leri (Faz 8c)."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.dependencies import AttachmentServiceDep, CurrentUserDep
from app.config import settings
from app.core.exceptions import (
    AuthenticationException,
    InvalidTokenException,
    NotFoundException,
)
from app.core.security import decode_token
from app.models.card import AttachmentResponse
from app.models.common import ApiResponse
from app.services.attachment import INLINE_MIME_TYPES
from app.services.attachment_storage import (
    AttachmentTooLargeException,
    get_storage,
    read_attachment_token,
)

attachments_router = APIRouter(tags=["Attachments"])
_optional_bearer = HTTPBearer(auto_error=False)

# Indirilen dosya hicbir zaman calistirilmasin / sayfa gibi yorumlanmasin
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    ),
    "Cache-Control": "private, max-age=3600",
}


def content_disposition(filename: str, inline: bool) -> str:
    """RFC 5987/6266: ASCII yedek ad + filename*=UTF-8''...(yuzde kodlu)."""
    ascii_name = filename.encode("ascii", "replace").decode().replace("?", "_")
    ascii_name = ascii_name.replace('"', "_").replace("\\", "_")
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


@attachments_router.post(
    "/cards/{card_id}/attachments",
    response_model=ApiResponse[AttachmentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    card_id: int,
    request: Request,
    service: AttachmentServiceDep,
    user: CurrentUserDep,
    file: Annotated[UploadFile, File()],
    note_id: Annotated[int | None, Form()] = None,
):
    """Karta dosya ekler (multipart `file`, istege bagli `note_id`)."""
    limit = settings.attachments_max_mb * 1024 * 1024
    declared = request.headers.get("content-length")
    # Govde cok buyukse (form alanlari icin 1 MB pay) parcalamadan reddet
    if declared and declared.isdigit() and int(declared) > limit + 1024 * 1024:
        raise AttachmentTooLargeException(settings.attachments_max_mb)
    data = await service.upload(card_id, user.id, file.filename, file, note_id)
    return ApiResponse(success=True, data=data)


@attachments_router.get(
    "/cards/{card_id}/attachments",
    response_model=ApiResponse[list[AttachmentResponse]],
)
async def list_attachments(
    card_id: int, service: AttachmentServiceDep, user: CurrentUserDep
):
    return ApiResponse(
        success=True, data=await service.list_for_card(card_id, user.id)
    )


@attachments_router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    service: AttachmentServiceDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_optional_bearer)
    ] = None,
    token: Annotated[str | None, Query()] = None,
    download: Annotated[int, Query()] = 0,
):
    """
    Dosya icerigi. Yetki: imzali `token` (<img src> / yeni sekme icin) ya da
    Authorization basligi. Baskasinin eki 404.
    """
    if credentials is not None:
        payload = decode_token(credentials.credentials)
        if (
            not payload
            or payload.get("type") != "access"
            or payload.get("sub") is None
        ):
            raise InvalidTokenException()
        user_id = int(payload["sub"])
    elif token:
        user_id, aid = read_attachment_token(token)
        if aid != attachment_id:
            raise NotFoundException("Attachment", attachment_id)
    else:
        raise AuthenticationException("Authentication required")

    att = await service.get_for_download(attachment_id, user_id)
    path = get_storage().path(att.storage_key)
    if not path.is_file():
        raise NotFoundException("Attachment", attachment_id)
    inline = att.mime_type in INLINE_MIME_TYPES and not download
    return FileResponse(
        path,
        media_type=att.mime_type,
        headers={
            **SECURITY_HEADERS,
            "Content-Disposition": content_disposition(att.filename, inline),
        },
    )


@attachments_router.delete(
    "/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_attachment(
    attachment_id: int, service: AttachmentServiceDep, user: CurrentUserDep
):
    await service.delete(attachment_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
