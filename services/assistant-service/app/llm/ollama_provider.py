"""
Ollama native adaptoru (/api/chat).

Neden OpenAI-uyumlu /v1 degil? /v1 uc noktasi `num_ctx`'i yok sayiyor; Ollama da
modelin tam baglam penceresi (orn. 262K) icin bellek ayiriyor. 8 GB VRAM'de bu,
4B modelin bile 14 GB yer kaplayip %38'inin GPU'da kalmasi demek (olculdu).
Native API ile num_ctx=16K -> ayni model 3.6 GB, %100 GPU.
"""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.openai_provider import _ThinkFilter
from app.llm.types import ChatChunk, LLMError, ModelInfo, Msg, ToolCall, ToolSpec, Usage


def _to_ollama_messages(messages: list[Msg]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "tool":
            out.append(
                {"role": "tool", "content": m.content or "", "tool_name": m.name}
            )
        elif m.role == "assistant" and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": m.content or "",
                    "tool_calls": [
                        {"function": {"name": tc.name, "arguments": tc.arguments}}
                        for tc in m.tool_calls
                    ],
                }
            )
        else:
            out.append({"role": m.role, "content": m.content or ""})
    return out


def _to_ollama_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


class OllamaProvider:
    def __init__(
        self,
        info: ModelInfo,
        *,
        base_url: str,
        num_ctx: int = 16384,
        think: bool = False,
        keep_alive: str = "30m",
        timeout: float = 300.0,
    ):
        self.info = info
        self.base_url = base_url.rstrip("/")
        self.num_ctx = num_ctx
        self.think = think
        self.keep_alive = keep_alive
        self.timeout = timeout

    async def stream(
        self,
        messages: list[Msg],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        options: dict[str, Any] = {"num_ctx": self.num_ctx, "temperature": temperature}
        if max_tokens:
            options["num_predict"] = max_tokens
        body: dict[str, Any] = {
            "model": self.info.model,
            "messages": _to_ollama_messages(messages),
            "stream": True,
            "think": self.think,
            "keep_alive": self.keep_alive,
            "options": options,
        }
        if tools and self.info.supports_tools:
            body["tools"] = _to_ollama_tools(tools)

        think = _ThinkFilter()
        n_calls = 0
        try:
            async with (
                httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=5)) as c,
                c.stream("POST", f"{self.base_url}/api/chat", json=body) as res,
            ):
                if res.status_code >= 400:
                    detail = (await res.aread()).decode(errors="replace")
                    raise LLMError(f"Ollama hatası ({self.info.label}): {detail[:300]}")
                async for line in res.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise LLMError(
                            f"Ollama hatası ({self.info.label}): {data['error']}"
                        )
                    msg = data.get("message") or {}
                    if msg.get("content"):
                        text = think.feed(msg["content"])
                        if text:
                            yield ChatChunk(type="text", text=text)
                    for tc in msg.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        args = fn.get("arguments")
                        valid = isinstance(args, dict)
                        yield ChatChunk(
                            type="tool_call",
                            tool_call=ToolCall(
                                # Ollama id vermezse benzersiz uret: "call_0" gibi
                                # tekrarlanan id'ler farkli turlarda cakisir
                                id=tc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                                name=fn.get("name", ""),
                                arguments=args if valid else {},
                                raw_arguments=None if valid else json.dumps(args),
                                valid=valid,
                            ),
                        )
                        n_calls += 1
                    if data.get("done"):
                        yield ChatChunk(
                            type="usage",
                            usage=Usage(
                                prompt_tokens=data.get("prompt_eval_count", 0),
                                completion_tokens=data.get("eval_count", 0),
                            ),
                        )
        except httpx.TimeoutException as e:
            raise LLMError(f"Model zaman aşımına uğradı ({self.info.label})") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama'ya bağlanılamadı: {e}") from e

        rest = think.flush()
        if rest:
            yield ChatChunk(type="text", text=rest)
