"""
Security Utility fonksiyonlarının unit teslerini yapar.
Bu testler:

- Şifre hashleme ve doğrulama

- JWT token oluşturma ve decode etme

"""

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    """Şifre Hashleme testleri"""

    def test_hash__password_returns_hashed_strings(self):
        """hashed_pasword fonksionu hashlemiş string döner."""
        password = "mysecretpassword"

        hashed = hash_password(password)

        # Hash orijinal şifreden farklı olmalı

        assert hashed != password

        assert hashed.startswith("$2b$")

    def test_hash_password_generates_unique_hashes(self):
        """Aynı şifre için bile farklı hash üretilir."""

        password = "mysecretpassword"

        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Salt farkı olduğu için hash'ler farklı olmalı
        assert hash1 != hash2

    def test_verify_password_with_correct_password(self):
        """doğru şifre verify edilir."""

        password = "mysecretpassword"
        hashed = hash_password(password)
        result = verify_password(password, hashed)

        assert result is True

    def test_verify_password_with_wrong_password(self):
        """Yanlus sifre reddedilir"""

        password = "mysecretpassword"
        wrong_password = "wrongpassword"
        hashed = hash_password(password)

        result = verify_password(wrong_password, hashed)

        assert result is False

    def test_verify_password_with_empty_password(self):
        """Bos sifre reddedilir"""

        password = "mysecretpassword"
        hashed = hash_password(password)

        result = verify_password("", hashed)

        assert result is False


class TestJWTTokens:
    """JWT Token Testleri"""

    def test_create_access_token_returns_string(self):
        """Access token string olarak doner."""

        user_id = 1

        token = create_access_token(user_id)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token_returns_string(self):
        """Refresh token string olarak doner."""

        user_id = 1

        token = create_refresh_token(user_id)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_access_and_refresh_tokens_are_different(self):
        """Access ve refresh token'lar farkli olmali"""

        user_id = 1

        access_token = create_access_token(user_id)
        refresh_token = create_refresh_token(user_id)

        assert access_token != refresh_token

    def test_decode_access_token(self):
        """Access Token basariyla decode edilir."""
        user_id = 123

        token = create_access_token(user_id)

        payload = decode_token(token)

        assert payload is not None
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_decode_refresh_token(self):
        """Refresh Token basariyla decode edilir."""

        user_id = 456

        token = create_refresh_token(user_id)

        payload = decode_token(token)

        assert payload is not None
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"
        assert "exp" in payload

    def test_decode_invalid_token_returns_none(self):
        """Gecersiz token icin none doner."""

        invalid_token = "this.is.invalid"

        payload = decode_token(invalid_token)

        assert payload is None

    def test_decode_empty_token_returns_none(self):
        """Bos token icin none doner."""

        empty_token = ""

        payload = decode_token(empty_token)

        assert payload is None
