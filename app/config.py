from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Uygulama Configlerini tanımlar"""

    # Uygulama Fieldları
    app_name: str = "Task Management API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Yapılandırma
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )


# Instance
settings = Settings()
