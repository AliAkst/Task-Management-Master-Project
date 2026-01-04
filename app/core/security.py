from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import settings

# ---  SIFRE ISLEMLERI (BCRYPT) ---


def hash_password(password: str) -> str:
    """Sifreyi guvenli bir sekilde hash'ler"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode(), salt)
    return hashed.decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Girilen sifre ile hash'lenmis sifreyi karsilastirir"""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


# --- TOKEN ISLEMLERI (JWT) ---


def create_access_token(user_id: int) -> str:
    """Kisa sureli erisim token'i olusturur"""
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_refresh_token(user_id: int) -> str:
    """Uzun Sureli erisim icin yenileme token'i olusturur"""
    expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_token(token: str) -> dict | None:
    """Token'i dogrular ve icindeki veriyi (payload) cozer"""
    try:
        decoded_payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return decoded_payload
    except (jwt.PyJWTError, Exception):
        # Token Gecersiz, suresi dolmus veya bozulmussa
        return None
