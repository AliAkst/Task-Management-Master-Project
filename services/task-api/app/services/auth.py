"""
Kimlik doğrulama işlemlerini (Kayıt, Giriş, Token Yenileme)
yöneten servis katmanı.
Bu modül, iş kurallarını uygular
ve repository ile güvenlik araçları arasında köprü kurar.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InvalidCredentialsException,
    InvalidTokenException,
    UserAlreadyExistException,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.entities import UserEntity
from app.db.repositories.user import UserRepository
from app.models.user import TokenResponse, UserCreate, UserLogin, UserResponse

# auth loglari tutmak icin
logger = get_logger(__name__)


class AuthService:
    """Kullanici kimlik dogrulama mantigini kapsayan servis sinifi."""

    def __init__(self, session: AsyncSession):
        """
        AuthService baslatilirken bir veritabani oturumunu alir
        ve UserRepository'yi kurar
        """
        self.repo = UserRepository(session)

    async def register(self, user_in: UserCreate) -> UserResponse:
        """
        Yeni bir kullanici kaydi olusturur

        Args:
            user_in(UserCreate): Kullanici kayit verileri (email,password,vb.)
        Returns:
            UserResponse: Kaydedilen kullanicinin bilgilerini iceren nesne.
        Raises:
            UserAlreadyExistsException: E-posta adresi zaten sistemde kayitliysa.
        """
        logger.info(f"Registering user:{user_in.email}")

        # e-mail kontrolu
        existing_user = await self.repo.get_by_email(user_in.email)
        if existing_user:
            raise UserAlreadyExistException(email=user_in.email)

        hashed_password = hash_password(user_in.password)
        new_user = UserEntity(
            email=user_in.email,
            hashed_password=hashed_password,
            full_name=user_in.full_name,
        )

        # kaydet ve don

        created_user = await self.repo.create(new_user)
        return UserResponse.model_validate(created_user)

    async def login(self, user_in: UserLogin) -> TokenResponse:
        """
        Kullanici bilgilerini dogrular ve oturum tokenlerini olusturur.

        args:
        :param user_in: Giris denemesi verileri (email,password)
        :type user_in: UserLogin
        :return: TokenResponse: Access ve Refresh token iceren nesne.
        :rtype: UserResponse
        raises:
            InvalidCredentialsException: Email Bulunamazsa veya sifre yanlissa.
        """
        logger.info(f"Login attempt:{user_in.email}")

        # kullaniciyi bul
        user = await self.repo.get_by_email(user_in.email)
        if not user:
            raise InvalidCredentialsException()

        # sifreyi dogrula
        if not verify_password(user_in.password, user.hashed_password):
            raise InvalidCredentialsException()

        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """
        Gecerli bir refresh token kullanarak yeni bir token cifti uretir

        Args:
            refresh_token (str) : Kullanicinin elindeki yenileme token'i.
        Raises:
            InvalidTokenException: Token gecersizse veya tipi yanlissa.
        """
        # Token'i coz ve dogrula.
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise InvalidTokenException()

        # Yeni Tokenleri bass

        user_id = int(payload["sub"])
        return TokenResponse(
            access_token=create_access_token(user_id),
            refresh_token=create_refresh_token(user_id),
        )
