"""
OpenAI-uyumlu adaptor: Ollama (/v1), LM Studio, OpenAI GPT ayni protokolu konusur.
Farklari sadece base_url / api_key / ek parametreler.
"""

import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI

from app.llm.types import ChatChunk, LLMError, ModelInfo, Msg, ToolCall, ToolSpec, Usage

# Bazi modeller dusunme metnini icerige gomer; kullaniciya gostermiyoruz
THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _to_openai_messages(messages: list[Msg]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": m.content or "",
                }
            )
        elif m.role == "assistant" and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": m.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": tc.raw_arguments
                                if not tc.valid
                                else json.dumps(tc.arguments, ensure_ascii=False),
                            },
                        }
                        for tc in m.tool_calls
                    ],
                }
            )
        else:
            out.append({"role": m.role, "content": m.content or ""})
    return out


def _to_openai_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
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


def parse_arguments(raw: str) -> tuple[dict[str, Any], bool]:
    """Arac argumanlari JSON'unu cozer; bos -> {}. (args, gecerli_mi)"""
    if not raw or not raw.strip():
        return {}, True
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}, False
    return (value, True) if isinstance(value, dict) else ({}, False)


class _ThinkFilter:
    """Stream boyunca <think>...</think> bloklarini ayiklar (parcalara bolunse bile)."""

    def __init__(self) -> None:
        self.buf = ""
        self.inside = False

    def feed(self, text: str) -> str:
        self.buf += text
        out = ""
        while True:
            if self.inside:
                end = self.buf.find("</think>")
                if end == -1:
                    # kapanis gelene kadar tut (son 8 karakter kapanis parcasi olabilir)
                    self.buf = self.buf[-8:]
                    return out
                self.buf = self.buf[end + len("</think>") :].lstrip()
                self.inside = False
            else:
                start = self.buf.find("<think>")
                if start == -1:
                    # "<thi" gibi yarim etiket olasiligina karsi kuyrugu tut
                    safe = len(self.buf) - 7
                    if safe > 0:
                        out += self.buf[:safe]
                        self.buf = self.buf[safe:]
                    return out
                out += self.buf[:start]
                self.buf = self.buf[start + len("<think>") :]
                self.inside = True

    def flush(self) -> str:
        rest = "" if self.inside else self.buf
        self.buf = ""
        return rest


class OpenAICompatibleProvider:
    def __init__(
        self,
        info: ModelInfo,
        *,
        base_url: str | None,
        api_key: str,
        extra: dict[str, Any] | None = None,
        timeout: float = 300.0,
    ):
        self.info = info
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        # Ollama icin {"reasoning_effort": "none"}: dusunme modunu kapatir (cok hizli)
        self.extra = extra or {}

    async def stream(
        self,
        messages: list[Msg],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        kwargs: dict[str, Any] = {
            "model": self.info.model,
            "messages": _to_openai_messages(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": temperature,
            **self.extra,
        }
        if tools and self.info.supports_tools:
            kwargs["tools"] = _to_openai_tools(tools)
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        pending: dict[int, dict[str, str]] = {}  # index -> {id, name, args}
        think = _ThinkFilter()
        try:
            stream = await self.client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if chunk.usage:
                    yield ChatChunk(
                        type="usage",
                        usage=Usage(
                            prompt_tokens=chunk.usage.prompt_tokens or 0,
                            completion_tokens=chunk.usage.completion_tokens or 0,
                        ),
                    )
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    text = think.feed(delta.content)
                    if text:
                        yield ChatChunk(type="text", text=text)
                for tc in delta.tool_calls or []:
                    slot = pending.setdefault(
                        tc.index, {"id": "", "name": "", "args": ""}
                    )
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["args"] += tc.function.arguments
        except APITimeoutError as e:
            raise LLMError(f"Model zaman aşımına uğradı ({self.info.label})") from e
        except APIConnectionError as e:
            raise LLMError(f"Modele bağlanılamadı ({self.info.label}): {e}") from e
        except APIError as e:
            raise LLMError(f"Model hatası ({self.info.label}): {e}") from e

        rest = think.flush()
        if rest:
            yield ChatChunk(type="text", text=rest)
        for i, slot in sorted(pending.items()):
            args, valid = parse_arguments(slot["args"])
            yield ChatChunk(
                type="tool_call",
                tool_call=ToolCall(
                    id=slot["id"] or f"call_{uuid.uuid4().hex[:12]}",
                    name=slot["name"],
                    arguments=args,
                    raw_arguments=None if valid else slot["args"],
                    valid=valid,
                ),
            )
