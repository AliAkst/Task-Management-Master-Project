from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    app_name: str = "Assistant Service"
    database_url: str = "sqlite+aiosqlite:///./assistant.db"
    # AI veriye SADECE task-api uzerinden, kullanicinin JWT'siyle erisir
    task_api_url: str = "http://localhost:8000/api/v1"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- Local model (Ollama) ---
    ollama_url: str = "http://localhost:11434"
    # Sohbette dusunme modu kapali: cok daha hizli (olculdu: 72 sn vs 158 sn)
    ollama_think: bool = False
    # Baglam penceresi. Varsayilan (262K) 8 GB VRAM'i tasirir; 16K'da 4B model
    # tamamen GPU'ya sigar (14.3 GB/%38 GPU -> 3.6 GB/%100 GPU, olculdu)
    ollama_num_ctx: int = 16384

    # --- Cloud modeller: kullanici basina provider_configs (sifreli key) ---
    # API anahtarlarini sifreleyen Fernet ana anahtari (bos: .secret_key dosyasi)
    secret_key: str | None = Field(None, validation_alias="ASSISTANT_SECRET_KEY")
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    # Claude: sohbet icin dusunme derinligi (low|medium|high|xhigh|max)
    anthropic_effort: str = "medium"
    anthropic_max_tokens: int = 16000

    # Varsayilan HER ZAMAN local model (kullanici Ayarlar'dan baska bir local secebilir)
    default_model: str = "ollama:qwen3.5:4b"
    # Arka plan isleri (gun sonu ozeti + ertesi gun plani, haftalik analiz): yavas
    # ama daha iyi planlayan buyuk local model. Kurulu degilse sohbet modeli
    background_model: str = "ollama:gemma4:26b"
    background_timeout_seconds: float = 1800.0
    max_tool_rounds: int = 6
    # Sohbetten sonra ayri, odakli hafiza cikarimi (bkz. app/agent/memory_extractor.py)
    memory_extraction: bool = True
    llm_timeout_seconds: float = 300.0


settings = Settings()
