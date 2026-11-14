"""
JWT imza anahtari (Faz 13a). Sirasiyla:
1. JWT_SECRET_KEY ortam degiskeni / `settings.jwt_secret_key`
2. Servis klasorundeki `.jwt_secret` dosyasi
3. Yoksa uretilir ve dosyaya yazilir (git'e girmez)

Anahtar degisirse mevcut oturumlar dusurulur (herkes yeniden giris yapar).
"""

import secrets
from functools import cache
from pathlib import Path

from app.config import settings

KEY_FILE = Path(__file__).resolve().parent.parent.parent / ".jwt_secret"


@cache
def get_jwt_secret() -> str:
    if settings.jwt_secret_key:
        return settings.jwt_secret_key
    if KEY_FILE.exists():
        value = KEY_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(64)
    KEY_FILE.write_text(value, encoding="utf-8")
    return value
