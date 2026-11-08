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

    # --- Cloud (opsiyonel; Faz 5'te kullanici basina sifreli key'e tasinacak) ---
    openai_api_key: str | None = None
    openai_models: list[str] = []  # orn. ["gpt-4.1-mini"]; key + liste varsa gorunur

    default_model: str = "ollama:qwen3.5:4b"
    max_tool_rounds: int = 6
    # Sohbetten sonra ayri, odakli hafiza cikarimi (bkz. app/agent/memory_extractor.py)
    memory_extraction: bool = True
    llm_timeout_seconds: float = 300.0


settings = Settings()
