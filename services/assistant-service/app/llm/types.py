"""
Saglayicidan bagimsiz (notr) LLM tipleri.

Uygulamanin geri kalani SADECE bu tipleri gorur. Ollama / OpenAI / Anthropic
formatina donusum yalnizca adaptorlerde (app/llm/*_provider.py) yapilir; boylece
model degistirmek baska hicbir kodu etkilemez.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    # Model gecersiz JSON urettiyse ham metin burada; arac calistirilmaz
    raw_arguments: str | None = None
    valid: bool = True


@dataclass
class Msg:
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None  # role=assistant
    tool_call_id: str | None = None  # role=tool
    name: str | None = None  # role=tool: arac adi
    # Saglayiciya ozel, opak icerik (orn. Claude'un dusunme bloklari). Sadece ayni
    # agent turu icinde ayni saglayiciya aynen geri verilir; veritabanina YAZILMAZ.
    provider_state: Any = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class ChatChunk:
    """Stream olayi: metin parcasi, tamamlanmis arac cagrisi ya da kullanim bilgisi."""

    type: Literal["text", "tool_call", "usage", "state"]
    text: str = ""
    tool_call: ToolCall | None = None
    usage: Usage | None = None
    state: Any = None  # type == "state": asistan mesajinin provider_state'i


@dataclass(frozen=True)
class ModelInfo:
    id: str  # "ollama:qwen3.5:4b", "openai:gpt-..."
    provider: Literal["ollama", "openai", "anthropic", "gemini"]
    model: str  # saglayicinin model adi
    label: str
    is_local: bool
    supports_tools: bool = True


class LLMProvider(Protocol):
    info: ModelInfo

    def stream(
        self,
        messages: list[Msg],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]: ...


class LLMError(Exception):
    """Saglayici hatasi (baglanti, model bulunamadi, zaman asimi...)."""
