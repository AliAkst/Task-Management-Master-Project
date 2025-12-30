from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Uygulama Field'ları
    app_name: str = "Task Management API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Yapılandırma (ConfigDict)
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )


# Instance oluşturma (Dışarıya servis edilecek olan 'zarf')
settings = Settings()
