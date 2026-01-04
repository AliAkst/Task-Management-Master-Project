from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Uygulama Field'ları
    app_name: str = "Task Management API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./task_management.db"

    # Yapılandırma (ConfigDict)
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    # JWT Settings
    jwt_secret_key: str = "super-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7


# Instance oluşturma (Dışarıya servis edilecek olan 'zarf')
settings = Settings()
