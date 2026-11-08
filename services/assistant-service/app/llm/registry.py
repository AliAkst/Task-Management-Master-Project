"""
Kullanilabilir modellerin listesi ve provider uretimi.

- Ollama (local): kurulu modeller /api/tags'ten kesfedilir.
- Bulut (Claude / GPT / Gemini): kullanicinin Ayarlar'da bagladigi
  provider_configs kayitlari (sifreli API anahtari + secilen model adlari).
Model kimligi "<saglayici>:<model>" (orn. "anthropic:claude-sonnet-5-5").
"""

from dataclasses import dataclass

import httpx

from app.config import settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_provider import OpenAICompatibleProvider
from app.llm.types import LLMError, LLMProvider, ModelInfo

# Sohbet asistanina uygun olmayan modeller (benchmark sonucu, bkz. README):
# - *coder*: kod modeli
# - deepseek-r1: arac cagirmadan "ekledim" diye yanit uydurdu; her yanita ~3 dk
#   dusunerek basliyor. Yazma araclariyla (Faz 5) tehlikeli.
HIDDEN_OLLAMA = ("coder", "deepseek-r1")


@dataclass(frozen=True)
class CloudProvider:
    id: str
    label: str
    key_url: str  # kullanicinin anahtar alacagi sayfa
    suggested: tuple[str, ...] = ()


CLOUD_PROVIDERS: dict[str, CloudProvider] = {
    p.id: p
    for p in (
        CloudProvider(
            "anthropic",
            "Claude (Anthropic)",
            "https://platform.claude.com/settings/keys",
            ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"),
        ),
        CloudProvider("openai", "GPT (OpenAI)", "https://platform.openai.com/api-keys"),
        CloudProvider(
            "gemini", "Gemini (Google)", "https://aistudio.google.com/apikey"
        ),
    )
}

CLAUDE_NAMES = {
    "claude-opus-5-5": "Claude Opus 5.5",
    "claude-sonnet-5-5": "Claude Sonnet 5.5",
    "claude-haiku-5-5": "Claude Haiku 5.5",
    "claude-fable-5-1": "Claude Fable 5.1",
}


@dataclass
class CloudConfig:
    """Cozulmus (anahtari acilmis) saglayici ayari; sadece istek suresince bellekte."""

    provider: str
    api_key: str
    models: list[str]
    base_url: str | None = None


def is_local_model(model_id: str) -> bool:
    return model_id.startswith("ollama:")


def parse_model_id(model_id: str) -> tuple[str, str]:
    provider, _, name = model_id.partition(":")
    if not name:
        raise LLMError(f"Geçersiz model kimliği: {model_id}")
    return provider, name


def cloud_label(provider: str, model: str) -> str:
    name = CLAUDE_NAMES.get(model, model)
    company = CLOUD_PROVIDERS[provider].label.split(" (")[1].rstrip(")")
    return f"{name} ({company}, ücretli)"  # "Claude Sonnet 5.5 (Anthropic, ücretli)"


async def list_local_models() -> list[ModelInfo]:
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
        pass  # Ollama kapali: sadece bulut modeller listelenir
    return models


def cloud_models(configs: list[tuple[str, list[str]]]) -> list[ModelInfo]:
    """configs: (saglayici, model adlari) - sadece etkin kayitlar."""
    out: list[ModelInfo] = []
    for provider, names in configs:
        if provider not in CLOUD_PROVIDERS:
            continue
        for name in names:
            out.append(
                ModelInfo(
                    id=f"{provider}:{name}",
                    provider=provider,  # type: ignore[arg-type]
                    model=name,
                    label=cloud_label(provider, name),
                    is_local=False,
                )
            )
    return out


def build_provider(
    model_id: str, cloud: CloudConfig | None = None, *, timeout: float | None = None
) -> LLMProvider:
    provider, name = parse_model_id(model_id)
    timeout = timeout or settings.llm_timeout_seconds
    if provider == "ollama":
        info = ModelInfo(
            id=model_id, provider="ollama", model=name, label=name, is_local=True
        )
        return OllamaProvider(
            info,
            base_url=settings.ollama_url,
            num_ctx=settings.ollama_num_ctx,
            think=settings.ollama_think,
            timeout=timeout,
        )
    if provider not in CLOUD_PROVIDERS:
        raise LLMError(f"Desteklenmeyen sağlayıcı: {provider}")
    if cloud is None or cloud.provider != provider:
        raise LLMError(
            f"{CLOUD_PROVIDERS[provider].label} bağlı değil; "
            "Ayarlar → Model sağlayıcıları"
        )
    if name not in cloud.models:
        raise LLMError(f"{name} bu sağlayıcıda etkin değil; Ayarlar'dan ekleyin")
    info = ModelInfo(
        id=model_id,
        provider=provider,  # type: ignore[arg-type]
        model=name,
        label=cloud_label(provider, name),
        is_local=False,
    )
    if provider == "anthropic":
        return AnthropicProvider(
            info,
            api_key=cloud.api_key,
            base_url=cloud.base_url,
            effort=settings.anthropic_effort,
            max_tokens=settings.anthropic_max_tokens,
            timeout=timeout,
        )
    base_url = cloud.base_url or (
        settings.gemini_base_url if provider == "gemini" else None
    )
    return OpenAICompatibleProvider(
        info, base_url=base_url, api_key=cloud.api_key, timeout=timeout
    )


async def probe_provider(
    provider: str, api_key: str, base_url: str | None
) -> list[str]:
    """
    Anahtari dogrular: saglayicinin model listesi uc noktasini cagirir (token
    harcamaz, ucretsiz). Sadece kullanici "Bağlantıyı test et"e basinca calisir.
    """
    import anthropic
    import openai

    try:
        if provider == "anthropic":
            client = anthropic.AsyncAnthropic(
                api_key=api_key, base_url=base_url, timeout=15
            )
            return [m.id async for m in client.models.list(limit=100)]
        url = base_url or (settings.gemini_base_url if provider == "gemini" else None)
        oclient = openai.AsyncOpenAI(api_key=api_key, base_url=url, timeout=15)
        page = await oclient.models.list()
        return sorted(m.id.removeprefix("models/") for m in page.data)
    except (anthropic.AuthenticationError, openai.AuthenticationError) as e:
        raise LLMError("API anahtarı geçersiz") from e
    except (anthropic.APIError, openai.APIError) as e:
        raise LLMError(f"Sağlayıcıya ulaşılamadı: {e}") from e
