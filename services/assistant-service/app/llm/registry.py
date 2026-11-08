"""
Kullanilabilir modellerin listesi ve provider uretimi.

- Ollama: kurulu modeller /api/tags'ten kesfedilir (yeni model indirince kod
  degismeden listede gorunur).
- OpenAI: OPENAI_API_KEY + OPENAI_MODELS tanimliysa.
Faz 5'te kullanici basina provider_configs (sifreli key) buraya eklenecek.
"""

import httpx

from app.config import settings
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_provider import OpenAICompatibleProvider
from app.llm.types import LLMError, LLMProvider, ModelInfo

# Sohbet asistanina uygun olmayan modeller (benchmark sonucu, bkz. README):
# - *coder*: kod modeli
# - deepseek-r1: arac cagirmadan "ekledim" diye yanit uydurdu; her yanita ~3 dk
#   dusunerek basliyor. Yazma araclariyla (Faz 5) tehlikeli.
HIDDEN_OLLAMA = ("coder", "deepseek-r1")


async def list_models() -> list[ModelInfo]:
    models: list[ModelInfo] = []
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            res = await client.get(f"{settings.ollama_url}/api/tags")
            res.raise_for_status()
            for m in res.json().get("models", []):
                name = m["name"]
                if any(h in name for h in HIDDEN_OLLAMA):
                    continue
                size = m.get("details", {}).get("parameter_size", "")
                models.append(
                    ModelInfo(
                        id=f"ollama:{name}",
                        provider="ollama",
                        model=name,
                        label=f"{name} (local{', ' + size if size else ''})",
                        is_local=True,
                    )
                )
    except httpx.HTTPError:
        pass  # Ollama kapali: sadece cloud modeller listelenir
    if settings.openai_api_key:
        for name in settings.openai_models:
            models.append(
                ModelInfo(
                    id=f"openai:{name}",
                    provider="openai",
                    model=name,
                    label=f"{name} (OpenAI)",
                    is_local=False,
                )
            )
    return models


def parse_model_id(model_id: str) -> tuple[str, str]:
    provider, _, name = model_id.partition(":")
    if not name:
        raise LLMError(f"Geçersiz model kimliği: {model_id}")
    return provider, name


def build_provider(model_id: str) -> LLMProvider:
    provider, name = parse_model_id(model_id)
    if provider == "ollama":
        info = ModelInfo(
            id=model_id, provider="ollama", model=name, label=name, is_local=True
        )
        return OllamaProvider(
            info,
            base_url=settings.ollama_url,
            num_ctx=settings.ollama_num_ctx,
            think=settings.ollama_think,
            timeout=settings.llm_timeout_seconds,
        )
    if provider == "openai":
        if not settings.openai_api_key:
            raise LLMError("OpenAI API key tanımlı değil")
        info = ModelInfo(
            id=model_id, provider="openai", model=name, label=name, is_local=False
        )
        return OpenAICompatibleProvider(
            info,
            base_url=None,
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
        )
    raise LLMError(f"Desteklenmeyen sağlayıcı: {provider} (Claude Faz 5'te)")
