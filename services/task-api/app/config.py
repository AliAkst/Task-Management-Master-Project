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
    #RabbitMQ Settings
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "taskuser"
    rabbitmq_password: str = "taskpass" 
    rabbitmq_vhost: str = "taskhost"
    @property
    def rabbitmq_url(self) -> str:
        """RabbitMQ AMQP URL'ini dondurur."""
        return f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"
    # Reddis Settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0 
    redis_password: str |None = None
    cache_ttl_seconds: int = 300 # cache ne kadar yasasin suresi 300 saniye
    #Rate Limiting Settings
    rate_limiting_requests: int= 100
    rate_limit_window_seconds: int = 60
    # Resilience Retry Settings
    retry_max_attempts: int = 3
    retry_min_wait_seconds: float = 1.0
    retry_max_wait_seconds: float = 10.0
    #Circuit Breaker Settings
    circuit_breaker_failure_threshold: int = 5 #kac hata sonrasi acilsin
    circuit_breaker_recovery_timeout: int = 30 #kac saniye acik kalsin
    circuit_breaker_half_open_max_calls: int = 1 #half-open'da kac test istegi
    # Timeout Settings
    db_timeout_seconds:float = 5.0 # Database islemleri icin
    external_api_timeout_seconds: float = 30.0 # Dis API cagrilari icin
    default_timeout_seconds: float = 10.0 # Genel Varsayilan timeout secenegi 
    #Feature Flags
    feature_cache_enabled: bool = True
    feature_ai_suggestions_enabled: bool = True
    feature_notifications_enabled: bool = True

#Global Instance oluşturma(baska bir fonksiyonda cagirirken kullaniyoruz)
settings = Settings()
