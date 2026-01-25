"""

Authentication endpoint'lerinin integration testleri.


Bu testler gerçek HTTP istekleri yaparak:

- Register flow

- Login flow

- Token refresh flow

- Protected endpoint erişimi

"""

from httpx import AsyncClient


class TestRegister:
    """Post /api/v1/auth/register testleri"""

    async def test_register_success(self, client: AsyncClient):
        """Yeni Kullanici basariyla kaydedilir."""
        user_data = {
            "email": "newuser@example.com",
            "password": "securepassword123",
            "full_name": "New User",
        }

        response = await client.post("/api/v1/auth/register", json=user_data)

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["email"] == "newuser@example.com"
        assert data["data"]["full_name"] == "New User"
        assert "password" not in data["data"]  # sifre response da donuyor mu kontrolu
        assert "hashed_password" not in data["data"]  # hashli sifre icin ayni kontrol

    async def test_register_duplicate_email_fails(self, client: AsyncClient, test_user):
        """Ayni email ile tekrar kayit olunamaz. bunu test ediyor."""
        user_data = {
            "email": test_user["email"],
            "password": "anotherpassword123",
            "full_name": "Another User",
        }

        response = await client.post("/api/v1/auth/register", json=user_data)

        assert response.status_code == 409
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "USER_ALREADY_EXISTS"

    async def test_register_invalid_email_fails(self, client: AsyncClient):
        """Gecersiz e mail ile kayit olunamaz."""
        user_data = {"email": "not-an-email", "password": "normalpassword123"}

        response = await client.post("/api/v1/auth/register", json=user_data)

        assert response.status_code == 422  # Validation Error

    async def test_register_short_password_fails(self, client: AsyncClient):
        """Kisa sifre ile kaydolamaz."""
        user_data = {"email": "user@example.com", "password": "passwd"}

        response = await client.post("/api/v1/auth/register", json=user_data)

        assert response.status_code == 422


class TestLogin:
    """POST /api/v1/auth/login testleri"""

    async def test_login_success(self, client: AsyncClient, test_user):
        """Doğru credentials ile login basarili mi onu test eder"""
        login_data = {"email": test_user["email"], "password": test_user["password"]}

        response = await client.post("/api/v1/auth/login", json=login_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"

    async def test_login_wrong_password_fails(self, client: AsyncClient, test_user):
        """yanlis sifre ile login basarisiz oluyor mu ?"""
        login_data = {"email": test_user["email"], "password": "wrongpassword"}

        response = await client.post("/api/v1/auth/login", json=login_data)

        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "AUTHENTICATION_FAILED"

    async def test_login_nonexistent_user_fails(self, client: AsyncClient):
        """Var olmayan kullanici ile login basarisiz oluyor mu"""
        login_data = {"email": "noneperson@example.com", "password": "nonepassword123"}

        response = await client.post("api/v1/auth/login", json=login_data)

        assert response.status_code == 401


class TestGetMe:
    """GET /api/v1/auth/me testleri"""

    async def test_get_me_with_valid_token(
        self, client: AsyncClient, auth_headers, test_user
    ):
        """Gecerli token ile kullanici bilgisi aliniyor mu"""
        response = await client.get("api/v1/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["email"] == test_user["email"]

    async def test_get_me_without_token_fails(self, client: AsyncClient):
        """Token olmadan erisim engelleniyor mu"""
        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401  # Forbidden (HTTPBearer default)

    async def test_get_me_with_invalid_token_fails(self, client: AsyncClient):
        "Gecersiz token ile erisim engelleniyor mu"
        headers = {"Authorization": "Bearer invalid.token.here"}

        response = await client.get("/api/v1/auth/me", headers=headers)

        assert response.status_code == 401


class TestRefreshToken:
    """POST /api/v1/auth/refresh testleri"""

    async def test_refresh_token_success(self, client: AsyncClient, test_user):
        """Gecerli refresh token ile yeni tokenler alinabiliyor mu"""
        # once login olup daha sonra tokeni test edicez.
        login_data = {"email": test_user["email"], "password": test_user["password"]}

        login_response = await client.post("/api/v1/auth/login", json=login_data)
        refresh_token = login_response.json()["data"]["refresh_token"]

        # refresh token ile yeni token al
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]

    async def test_refresh_token_invalid_token_fails(self, client: AsyncClient):
        """Gecersiz refresh token reddediliyor mu ?"""
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "invalid.refresh.token"}
        )

        assert response.status_code == 401
