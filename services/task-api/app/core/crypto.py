"""
Entegrasyon token'larinin sifrelenmesi (Fernet: AES-128-CBC + HMAC).
assistant-service `app/security.py` ile ayni mantik.

Ana anahtar sirasiyla:
1. TASK_API_SECRET_KEY / SECRET_KEY ortam degiskeni (`settings.secret_key`)
2. Servis klasorundeki `.secret_key` dosyasi (gelistirme; yoksa uretilir, git'e girmez)

Ana anahtar kaybolursa kayitli token'lar cozulemez; kullanici yeniden baglanir.
"""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

KEY_FILE = Path(__file__).resolve().parent.parent.parent / ".secret_key"


class SecretError(Exception):
    """Sifreli deger cozulemedi (ana anahtar degismis olabilir)."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.secret_key or os.environ.get("TASK_API_SECRET_KEY")
    if not key:
        if KEY_FILE.exists():
            key = KEY_FILE.read_text(encoding="utf-8").strip()
        else:
            key = Fernet.generate_key().decode()
            KEY_FILE.write_text(key, encoding="utf-8")
    return Fernet(key.encode())


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise SecretError(
            "Kayıtlı bağlantı bilgisi çözülemedi (ana anahtar değişmiş olabilir); "
            "bağlantıyı yeniden kurun."
        ) from e


def encrypt_json(data: dict[str, Any]) -> str:
    return encrypt(json.dumps(data))


def decrypt_json(token: str) -> dict[str, Any]:
    return json.loads(decrypt(token))


def mask(plain: str) -> str:
    """Arayuzde gosterim: sadece son 4 karakter."""
    return f"…{plain[-4:]}" if len(plain) >= 8 else "…"
