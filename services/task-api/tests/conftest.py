from collections.abc import AsyncGenerator, Generator
from typing import Any
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings
from app.db.database import get_db_session
from app.db.entities import Base
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_database.db"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Pytest-asyncio için backend belirt"""
    return "asyncio"


@pytest.fixture(scope="function")
async def test_engine():
    """Her test için yeni bir database engine oluşturur."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Tablolar
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(scope="function")
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Her test için yeni bir database session oluşturur."""
    async_session_maker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session


@pytest.fixture(scope="function")
async def client(test_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Test için HTTP client oluştur"""

    # Ana uygulamanın session'ını test session ile değiştir.
    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield test_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        yield async_client

    # Override'ı temizle
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def test_user(client: AsyncClient) -> dict[str, Any]:
    """Test için bir kullanıcı oluşturur ve bilgilerini döner."""
    user_data = {
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User",
    }

    # kullanıcıyı kaydet
    response = await client.post("/api/v1/auth/register", json=user_data)

    return {
        "email": user_data["email"],
        "password": user_data["password"],
        "user": response.json()["data"],
    }


@pytest.fixture(scope="function")
async def auth_headers(
    client: AsyncClient, test_user: dict[str, Any]
) -> dict[str, str]:
    """Test için authentication header'ları döner."""
    # Login yap
    login_data = {"email": test_user["email"], "password": test_user["password"]}
    response = await client.post("/api/v1/auth/login", json=login_data)

    token = response.json()["data"]["access_token"]

    return {"Authorization": f"bearer {token}"}
