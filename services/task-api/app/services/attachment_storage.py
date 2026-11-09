"""
Kart ekleri icin yerel dosya deposu + imzali indirme token'i (Faz 8c).

Guvenlik:
- Diskteki yol yalniz sunucunun urettigi `storage_key`'den (`<user_id>/<uuid4 hex>`)
  kurulur; kullanici girdisi (dosya adi) yolda yer almaz -> yol gecisi yok.
- Okurken/silerken yol `resolve()` edilip kok altinda mi diye kontrol edilir.
"""

import asyncio
import hashlib
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt

from app.config import settings
from app.core.exceptions import AppException, AuthenticationException
from app.core.logging import get_logger

logger = get_logger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MB
TOKEN_TTL = timedelta(minutes=60)
TOKEN_PURPOSE = "attachment"
_KEY_RE = re.compile(r"^\d+/[0-9a-f]{32}$")


class AttachmentTooLargeException(AppException):
    def __init__(self, max_mb: int):
        super().__init__(
            status_code=413,
            error_code="ATTACHMENT_TOO_LARGE",
            message=f"Dosya {max_mb} MB sınırını aşıyor",
        )


class AttachmentTypeBlockedException(AppException):
    def __init__(self, ext: str):
        super().__init__(
            status_code=422,
            error_code="ATTACHMENT_TYPE_BLOCKED",
            message=f"'{ext}' dosyaları yüklenemez",
        )


def default_root() -> Path:
    # services/task-api/data/attachments (app/services/<bu dosya> -> 2 ust = task-api)
    return Path(__file__).resolve().parents[2] / "data" / "attachments"


class LocalAttachmentStorage:
    def __init__(self, root: Path):
        self.root = Path(root)

    # ---------------- yol ----------------
    def path(self, key: str) -> Path:
        if not _KEY_RE.match(key):
            raise ValueError("gecersiz storage_key")
        root = self.root.resolve()
        full = (root / key).resolve()
        if not full.is_relative_to(root):
            raise ValueError("yol kok disina cikiyor")
        return full

    # ---------------- yazma ----------------
    async def save(
        self, user_id: int, chunks: AsyncIterator[bytes], max_bytes: int
    ) -> tuple[str, int, str]:
        """Parcalari diske yazar -> (storage_key, boyut, sha256). Sinir asilirsa siler."""
        key = f"{user_id}/{uuid.uuid4().hex}"
        final = self.path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = final.parent / f".tmp-{uuid.uuid4().hex}"
        digest = hashlib.sha256()
        size = 0
        try:
            with tmp.open("wb") as fh:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise AttachmentTooLargeException(
                            max(1, max_bytes // (1024 * 1024))
                        )
                    digest.update(chunk)
                    await asyncio.to_thread(fh.write, chunk)
            tmp.replace(final)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return key, size, digest.hexdigest()

    # ---------------- silme ----------------
    def delete(self, key: str) -> None:
        try:
            self.path(key).unlink(missing_ok=True)
        except Exception as e:  # akisi bozma: logla
            logger.warning(f"Ek dosyasi silinemedi ({key}): {e}")

    def delete_many(self, keys: list[str]) -> None:
        for key in keys:
            self.delete(key)

    def sweep_orphans(self, known_keys: set[str], older_than: timedelta) -> int:
        """DB'de satiri olmayan, `older_than`'dan eski dosyalari (.tmp artiklari dahil) siler."""
        if not self.root.is_dir():
            return 0
        cutoff = datetime.now(UTC).timestamp() - older_than.total_seconds()
        removed = 0
        for user_dir in self.root.iterdir():
            if not user_dir.is_dir():
                continue
            for f in user_dir.iterdir():
                if not f.is_file():
                    continue
                key = f"{user_dir.name}/{f.name}"
                try:
                    if key not in known_keys and f.stat().st_mtime < cutoff:
                        f.unlink()
                        removed += 1
                except OSError as e:
                    logger.warning(f"Yetim ek temizlenemedi ({key}): {e}")
        return removed


def get_storage() -> LocalAttachmentStorage:
    """Her cagrida ayardan kurulur (testler `attachments_dir`'i degistirebilir)."""
    root = (
        Path(settings.attachments_dir) if settings.attachments_dir else default_root()
    )
    return LocalAttachmentStorage(root)


# ---------------- imzali URL token'i ----------------
def make_attachment_token(user_id: int, attachment_id: int) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "aid": attachment_id,
            "purpose": TOKEN_PURPOSE,
            "exp": datetime.now(UTC) + TOKEN_TTL,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def read_attachment_token(token: str) -> tuple[int, int]:
    """Token'i dogrular -> (user_id, attachment_id). Gecersiz/suresi dolmus -> 401."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("purpose") != TOKEN_PURPOSE:
            raise ValueError("purpose uyumsuz")
        return int(payload["sub"]), int(payload["aid"])
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as e:
        raise AuthenticationException("Invalid or expired attachment link") from e
