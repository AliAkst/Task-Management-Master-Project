"""Kart ekleri is mantigi (Faz 8c): yukleme, listeleme, indirme, silme."""

import mimetypes
import re
from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import Protocol

from app.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.db.entities import CardAttachmentEntity
from app.db.unit_of_work import TaskUnitOfWork
from app.models.card import AttachmentResponse
from app.services.activity import ActivityLogger
from app.services.attachment_storage import (
    CHUNK_SIZE,
    AttachmentTypeBlockedException,
    get_storage,
    make_attachment_token,
)

BLOCKED_EXTENSIONS = frozenset(
    {
        ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".psm1", ".vbs",
        ".vbe", ".wsf", ".jar", ".lnk", ".dll", ".sys", ".reg", ".hta", ".cpl",
    }
)  # fmt: skip
# Tarayicida "inline" gosterilebilen tek turler; digerleri hep indirme
INLINE_MIME_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}
)
IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
MAX_NAME = 200


class Readable(Protocol):
    async def read(self, size: int = -1, /) -> bytes: ...


def sanitize_filename(name: str | None) -> str:
    """Yol parcalarini (/ ve ters bolu) atar, kontrol karakterlerini siler, 200'e keser."""
    raw = (name or "").replace("\\", "/")
    base = PurePosixPath(raw).name
    base = _CONTROL_CHARS.sub("", base).strip().rstrip(". ")
    if base in ("", ".", ".."):
        return "dosya"
    if len(base) > MAX_NAME:
        stem, dot, ext = base.rpartition(".")
        if dot and 0 < len(ext) <= 20:
            base = stem[: MAX_NAME - len(ext) - 1] + "." + ext
        else:
            base = base[:MAX_NAME]
    return base


def extension_of(name: str) -> str:
    return PurePosixPath(name).suffix.lower()


def guess_mime(name: str) -> str:
    """MIME istemciden alinmaz: yalniz uzantidan."""
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


async def iter_chunks(file: Readable) -> AsyncIterator[bytes]:
    while chunk := await file.read(CHUNK_SIZE):
        yield chunk


def to_response(a: CardAttachmentEntity) -> AttachmentResponse:
    token = make_attachment_token(a.user_id, a.id)
    return AttachmentResponse(
        id=a.id,
        card_id=a.card_id,
        note_id=a.note_id,
        filename=a.filename,
        mime_type=a.mime_type,
        size_bytes=a.size_bytes,
        is_image=a.mime_type in IMAGE_MIME_TYPES,
        created_at=a.created_at,
        url=f"{settings.api_v1_prefix}/attachments/{a.id}/download?token={token}",
    )


class AttachmentService:
    def __init__(self, uow: TaskUnitOfWork, actor: str = "user"):
        self.uow = uow
        self.actor = actor
        self.activity = ActivityLogger(uow, actor)

    async def _owned_card(self, card_id: int, user_id: int):
        card = await self.uow.tasks.get_owned(card_id, user_id)
        if card is None:
            raise NotFoundException("Card", card_id)
        return card

    async def _owned(self, attachment_id: int, user_id: int) -> CardAttachmentEntity:
        a = await self.uow.attachments.get_owned(attachment_id, user_id)
        if a is None:
            raise NotFoundException("Attachment", attachment_id)
        return a

    async def upload(
        self,
        card_id: int,
        user_id: int,
        filename: str | None,
        file: Readable,
        note_id: int | None = None,
    ) -> AttachmentResponse:
        card = await self._owned_card(card_id, user_id)
        if note_id is not None:
            note = await self.uow.notes.get_owned(note_id, user_id)
            if note is None or note.card_id != card.id:
                raise ValidationException("Not bu karta ait değil")
        name = sanitize_filename(filename)
        ext = extension_of(name)
        if ext in BLOCKED_EXTENSIONS:
            raise AttachmentTypeBlockedException(ext)

        storage = get_storage()
        key, size, sha = await storage.save(
            user_id, iter_chunks(file), settings.attachments_max_mb * 1024 * 1024
        )
        try:
            att = CardAttachmentEntity(
                user_id=user_id,
                card_id=card.id,
                note_id=note_id,
                filename=name,
                mime_type=guess_mime(name),
                size_bytes=size,
                storage_key=key,
                sha256=sha,
            )
            await self.uow.attachments.create(att)
            await self.uow.flush()
            await self.activity.log(
                user_id,
                "attachment",
                att.id,
                "created",
                board_id=card.board_id,
                card_id=card.id,
                changes={"filename": name, "size_bytes": size},
            )
            await self.uow.commit()
        except BaseException:
            await self.uow.rollback()
            storage.delete(key)
            raise
        return to_response(att)

    async def list_for_card(self, card_id: int, user_id: int) -> list[AttachmentResponse]:
        await self._owned_card(card_id, user_id)
        rows = await self.uow.attachments.list_for_card(card_id)
        return [to_response(a) for a in rows]

    async def get_for_download(
        self, attachment_id: int, user_id: int
    ) -> CardAttachmentEntity:
        return await self._owned(attachment_id, user_id)

    async def delete(self, attachment_id: int, user_id: int) -> None:
        a = await self._owned(attachment_id, user_id)
        card = await self.uow.tasks.get_by_id(a.card_id)
        key = a.storage_key
        await self.activity.log(
            user_id,
            "attachment",
            a.id,
            "deleted",
            board_id=card.board_id if card else None,
            card_id=a.card_id,
            changes={"filename": a.filename},
        )
        await self.uow.attachments.delete(a)
        await self.uow.commit()
        get_storage().delete(key)  # commit sonrasi; hata loglanir
