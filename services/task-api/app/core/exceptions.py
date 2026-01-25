class AppException(Exception):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
    ):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        super().__init__(self.message)


class TaskNotFoundException(AppException):
    def __init__(self, task_id: int):
        super().__init__(
            status_code=404,
            error_code="TASK_NOT_FOUND",
            message=f"Task with id {task_id} not found",
        )


class TaskBadRequestException(AppException):
    def __init__(self, message: str):
        super().__init__(
            status_code=400, error_code="TASK_BAD_REQUEST", message=message
        )


class ValidationException(AppException):
    def __init__(self, message: str):
        super().__init__(
            status_code=422, error_code="VALIDATION_ERROR", message=message
        )


"""
Kimlik doğrulama ve kullanıcı işlemleriyle ilgili özel hata sınıflarını içerir.
Bu hatalar, API katmanında yakalanarak uygun HTTP statü kodlarına dönüştürülür.
"""


class AuthenticationException(AppException):
    """
    Genel kimlik dogrulama hatalari icin temel sinif.
    Status Code: 401(Unauthorized)
    """

    def __init__(self, message: str = "Autentication failed"):
        super().__init__(
            status_code=401, error_code="AUTHENTICATION_FAILED", message=message
        )


class InvalidCredentialsException(AuthenticationException):
    """Hatali e-posta veya sifre girislerinde firlatilir."""

    def __init__(self):
        super().__init__(message="Invalid email or password")


class InvalidTokenException(AuthenticationException):
    """
    Jwt Token'in gecersiz, bozulmus veya
    suresinin dolmus olmasi durumunda firlatilir
    """

    def __init__(self):
        super().__init__(message="Invalid or expired Token")


class UserAlreadyExistException(AppException):
    """Kullanici zaten var oldugunda bu hata firlatilir."""

    def __init__(self, email: str):
        super().__init__(
            status_code=409,
            error_code="USER_ALREADY_EXISTS",
            message=f"User with email {email} already exists",
        )


class ForbiddenException(AppException):
    """Kullanici yetkisi yok."""

    def __init__(
        self, message: str = "You don't have permission to perform this action"
    ):
        super().__init__(status_code=403, error_code="FORBIDDEN", message=message)

