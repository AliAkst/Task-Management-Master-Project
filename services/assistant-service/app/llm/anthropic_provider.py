"""
Claude adaptoru (resmi `anthropic` SDK'si, Messages API + streaming).

Notr tiplerden farklari:
- Sistem mesaji ust duzey `system` alaninda; arac sonuclari `user` rolunde
  `tool_result` bloklari (ardisik sonuclar TEK mesajda birlesir).
- Claude 5.x modellerinde dusunme her zaman acik (kapatilamaz; derinligi
  `output_config.effort` belirler). Arac dongusunde asistan mesaji dusunme
  bloklariyla AYNEN geri verilmeli -> `provider_state` ile tur icinde tasinir.
  Turlar arasinda tasinmaz: sistem mesajimiz her turda yeniden kuruldugu icin
  eski bloklari geri vermek "gecmis degisti" hatasina (400) yol acabilir.
- `temperature` gonderilmez (guncel API surumunde kaldirildi).
"""

import re
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from app.llm.types import ChatChunk, LLMError, ModelInfo, Msg, ToolCall, ToolSpec, Usage

# Sunucu tarafi "refusal" yedeklemesini destekleyen modeller (fallbacks="default")
FALLBACK_MODELS = {
    "claude-opus-5-5",
    "claude-sonnet-5-5",
    "claude-fable-5-1",
    "claude-opus-5",
}
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# output_config.effort kabul eden modeller (eski Sonnet/Haiku 4.5'te hata verir)
EFFORT_RE = re.compile(
    r"^claude-((opus|sonnet|haiku|fable|mythos)-5|opus-4-[5-8]|sonnet-4-6)"
)

REFUSAL_NOTICE = "Claude bu isteği güvenlik politikası nedeniyle yanıtlamadı."
TRUNCATED_NOTICE = (
    "Yanıt uzunluk sınırına takıldı; araç çağrısı yarım kaldığı için çalıştırılmadı."
)


def to_anthropic_messages(messages: list[Msg]) -> tuple[str, list[dict[str, Any]]]:
    """Notr mesajlar -> (system, messages). Sondaki sistem talimatlari son
    kullanici mesajina metin blogu olarak eklenir (tum modellerde gecerli)."""
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []

    def user_blocks() -> list[dict[str, Any]]:
        if out and out[-1]["role"] == "user":
            return out[-1]["content"]
        out.append({"role": "user", "content": []})
        return out[-1]["content"]

    for m in messages:
        if m.role == "system":
            if not out:
                system_parts.append(m.content or "")
            else:
                user_blocks().append({"type": "text", "text": m.content or ""})
        elif m.role == "user":
            user_blocks().append({"type": "text", "text": m.content or ""})
        elif m.role == "tool":
            user_blocks().append(
                {
                    "type": "tool_result",
                    "tool_use_id": m.tool_call_id,
                    "content": m.content or "",
                }
            )
        elif m.role == "assistant":
            if m.provider_state:
                content = list(m.provider_state)
            else:
                content = []
                if m.content:
                    content.append({"type": "text", "text": m.content})
                for tc in m.tool_calls or []:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
            if content:  # bos asistan mesaji API'de hata verir
                out.append({"role": "assistant", "content": content})
    return "\n\n".join(p for p in system_parts if p), out


def to_anthropic_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    # eager_input_streaming bilerek kapali: arac girdilerimiz kucuk, sunucunun
    # girdiyi dogrulamasi (varsayilan) yarim/bozuk JSON riskini ortadan kaldirir.
    return [
        {"name": t.name, "description": t.description, "input_schema": t.parameters}
        for t in tools
    ]


def _echo_block(block: Any) -> dict[str, Any]:
    """Yanit blogunu bir sonraki istege aynen geri verilecek param bicimine cevirir."""
    t = block.type
    if t == "text":
        return {"type": "text", "text": block.text}
    if t == "thinking":
        return {
            "type": "thinking",
            "thinking": block.thinking,
            "signature": block.signature,
        }
    if t == "redacted_thinking":
        return {"type": "redacted_thinking", "data": block.data}
    if t == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    return block.to_dict(exclude_none=True)


def echo_content(content: list[Any]) -> list[dict[str, Any]]:
    """
    Yedek modele gecis (fallback) olduysa son `fallback` blogundan ONCEKI
    dusunme/arac bloklari geri verilmez; metin bloklari ve sonrasi aynen gider.
    """
    last_fb = max(
        (i for i, b in enumerate(content) if b.type == "fallback"), default=-1
    )
    out = []
    for i, b in enumerate(content):
        if i < last_fb and b.type != "text":
            continue
        out.append(_echo_block(b))
    return out


class AnthropicProvider:
    def __init__(
        self,
        info: ModelInfo,
        *,
        api_key: str,
        base_url: str | None = None,
        effort: str = "medium",
        max_tokens: int = 16000,
        timeout: float = 300.0,
        client: Any = None,  # testler icin sahte istemci
    ):
        self.info = info
        self.effort = effort
        self.max_tokens = max_tokens
        # Son turda (FORCE_ANSWER) arac verilmez ama gecmiste tool_use bloklari
        # varsa API arac tanimlarini ister -> son tanimlar + tool_choice=none
        self._last_tools: list[ToolSpec] | None = None
        self.client = client or anthropic.AsyncAnthropic(
            api_key=api_key, base_url=base_url, timeout=timeout
        )

    def request_kwargs(
        self, messages: list[Msg], tools: list[ToolSpec] | None, max_tokens: int | None
    ) -> dict[str, Any]:
        system, msgs = to_anthropic_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.info.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": msgs,
            # Arac dongusunde onek ayni kalir -> sonraki turlar onbellekten okunur
            "cache_control": {"type": "ephemeral"},
        }
        if system:
            kwargs["system"] = system
        if tools and self.info.supports_tools:
            self._last_tools = tools
            kwargs["tools"] = to_anthropic_tools(tools)
        elif self._last_tools and any(m.tool_calls for m in messages):
            kwargs["tools"] = to_anthropic_tools(self._last_tools)
            kwargs["tool_choice"] = {"type": "none"}
        if EFFORT_RE.match(self.info.model):
            kwargs["output_config"] = {"effort": self.effort}
        if self.info.model in FALLBACK_MODELS:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        return kwargs

    async def stream(
        self,
        messages: list[Msg],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.4,  # Claude'a gonderilmez (bkz. modul notu)
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        kwargs = self.request_kwargs(messages, tools, max_tokens)
        label = self.info.label
        try:
            async with self.client.beta.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "text" and event.text:
                        yield ChatChunk(type="text", text=event.text)
                final = await stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise LLMError(f"Claude API anahtarı geçersiz ({label})") from e
        except anthropic.PermissionDeniedError as e:
            raise LLMError(f"Bu API anahtarının {label} modeline erişimi yok") from e
        except anthropic.NotFoundError as e:
            raise LLMError(f"Model bulunamadı: {self.info.model}") from e
        except anthropic.RateLimitError as e:
            raise LLMError(
                f"Claude istek sınırına ulaşıldı ({label}); biraz bekleyin"
            ) from e
        except anthropic.APITimeoutError as e:
            raise LLMError(f"Model zaman aşımına uğradı ({label})") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"Claude'a bağlanılamadı ({label})") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude hatası ({label}): {e.message}") from e

        u = final.usage
        yield ChatChunk(
            type="usage",
            usage=Usage(
                prompt_tokens=(u.input_tokens or 0)
                + (u.cache_read_input_tokens or 0)
                + (u.cache_creation_input_tokens or 0),
                completion_tokens=u.output_tokens or 0,
            ),
        )
        if final.stop_reason == "refusal":
            yield ChatChunk(type="text", text=REFUSAL_NOTICE)
            return
        tool_uses = [b for b in final.content if b.type == "tool_use"]
        if tool_uses and final.stop_reason == "max_tokens":
            yield ChatChunk(type="text", text=TRUNCATED_NOTICE)
            return
        for b in tool_uses:
            valid = isinstance(b.input, dict)
            yield ChatChunk(
                type="tool_call",
                tool_call=ToolCall(
                    id=b.id,
                    name=b.name,
                    arguments=b.input if valid else {},
                    raw_arguments=None if valid else str(b.input),
                    valid=valid,
                ),
            )
        yield ChatChunk(type="state", state=echo_content(final.content))
