"""Claude adaptoru: mesaj donusumu, istek parametreleri, stream ayristirma (API'siz)."""

from types import SimpleNamespace as NS

from app.llm.anthropic_provider import (
    REFUSAL_NOTICE,
    TRUNCATED_NOTICE,
    AnthropicProvider,
    echo_content,
    to_anthropic_messages,
)
from app.llm.types import ModelInfo, Msg, ToolCall, ToolSpec


def _info(model: str = "claude-sonnet-5-5") -> ModelInfo:
    return ModelInfo(
        id=f"anthropic:{model}",
        provider="anthropic",
        model=model,
        label=model,
        is_local=False,
    )


class Block(NS):
    def to_dict(self, **_):
        return {k: v for k, v in vars(self).items()}


def final(content, stop="end_turn"):
    return NS(
        content=content,
        stop_reason=stop,
        usage=NS(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=3,
            cache_creation_input_tokens=None,
        ),
    )


class FakeStream:
    def __init__(self, events, message):
        self.events, self.message = events, message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        async def gen():
            for e in self.events:
                yield e

        return gen()

    async def get_final_message(self):
        return self.message


class FakeClient:
    def __init__(self, *turns):
        self.turns = list(turns)
        self.calls: list[dict] = []
        self.beta = NS(messages=NS(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(*self.turns.pop(0))


def provider(client, model="claude-sonnet-5-5"):
    return AnthropicProvider(_info(model), api_key="k", client=client)


async def collect(p, messages, tools=None):
    return [c async for c in p.stream(messages, tools)]


TOOL = ToolSpec("list_boards", "Board'lari listeler")


# ---------------- donusum ----------------
def test_message_conversion():
    msgs = [
        Msg("system", "Sen asistansın"),
        Msg("user", "Board'larım?"),
        Msg(
            "assistant",
            "",
            tool_calls=[
                ToolCall("t1", "list_boards", {}),
                ToolCall("t2", "get_day_plan", {"d": 1}),
            ],
        ),
        Msg("tool", "[spor]", tool_call_id="t1", name="list_boards"),
        Msg("tool", "{}", tool_call_id="t2", name="get_day_plan"),
        Msg("system", "Şimdi cevap ver"),
        Msg("assistant", ""),  # bos asistan atlanir
    ]
    system, out = to_anthropic_messages(msgs)
    assert system == "Sen asistansın"
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert out[1]["content"] == [
        {"type": "tool_use", "id": "t1", "name": "list_boards", "input": {}},
        {"type": "tool_use", "id": "t2", "name": "get_day_plan", "input": {"d": 1}},
    ]
    # iki arac sonucu TEK kullanici mesajinda; sondaki talimat metin blogu olarak
    assert [b["type"] for b in out[2]["content"]] == [
        "tool_result",
        "tool_result",
        "text",
    ]
    assert out[2]["content"][0]["tool_use_id"] == "t1"
    assert out[2]["content"][2]["text"] == "Şimdi cevap ver"


def test_provider_state_is_replayed_verbatim():
    state = [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "tool_use", "id": "t1", "name": "x", "input": {}},
    ]
    msgs = [
        Msg("user", "a"),
        Msg(
            "assistant", "", tool_calls=[ToolCall("t1", "x", {})], provider_state=state
        ),
    ]
    _, out = to_anthropic_messages(msgs)
    assert out[1]["content"] == state


def test_request_kwargs_no_temperature_effort_and_fallbacks():
    p = provider(FakeClient(), "claude-opus-5-5")
    kw = p.request_kwargs([Msg("system", "s"), Msg("user", "u")], [TOOL], None)
    assert "temperature" not in kw
    assert kw["output_config"] == {"effort": "medium"}
    assert kw["fallbacks"] == "default"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert kw["tools"][0]["input_schema"] == TOOL.parameters
    assert kw["system"] == "s" and kw["max_tokens"] == 16000

    haiku = provider(FakeClient(), "claude-haiku-5-5")
    kw = haiku.request_kwargs([Msg("user", "u")], None, 500)
    assert "fallbacks" not in kw and "system" not in kw and "tools" not in kw
    assert kw["max_tokens"] == 500 and kw["output_config"] == {"effort": "medium"}
    old = provider(FakeClient(), "claude-haiku-4-5")
    assert "output_config" not in old.request_kwargs([Msg("user", "u")], None, None)


# ---------------- stream ----------------
async def test_stream_text_tool_call_and_state():
    thinking = Block(type="thinking", thinking="", signature="sig")
    use = Block(type="tool_use", id="toolu_1", name="list_boards", input={"q": 1})
    client = FakeClient(
        (
            [NS(type="text", text="Bakıyorum")],
            final([thinking, Block(type="text", text="Bakıyorum"), use], "tool_use"),
        )
    )
    chunks = await collect(provider(client), [Msg("user", "x")], [TOOL])
    kinds = [c.type for c in chunks]
    assert kinds == ["text", "usage", "tool_call", "state"]
    assert chunks[1].usage.prompt_tokens == 13
    assert chunks[2].tool_call.id == "toolu_1"
    assert chunks[2].tool_call.arguments == {"q": 1}
    assert chunks[3].state == [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "Bakıyorum"},
        {"type": "tool_use", "id": "toolu_1", "name": "list_boards", "input": {"q": 1}},
    ]


async def test_refusal_and_truncated_tool_call_do_not_run_tools():
    use = Block(type="tool_use", id="t", name="list_boards", input={})
    client = FakeClient(([], final([use], "refusal")), ([], final([use], "max_tokens")))
    p = provider(client)
    refused = await collect(p, [Msg("user", "x")], [TOOL])
    assert [c.type for c in refused] == ["usage", "text"]
    assert refused[-1].text == REFUSAL_NOTICE
    cut = await collect(p, [Msg("user", "x")], [TOOL])
    assert cut[-1].text == TRUNCATED_NOTICE
    assert not any(c.type == "tool_call" for c in cut)


def test_fallback_echo_drops_blocks_before_boundary():
    content = [
        Block(type="thinking", thinking="", signature="a"),
        Block(type="text", text="önce"),
        Block(type="tool_use", id="x", name="n", input={}),
        Block(type="fallback", reason="refusal"),
        Block(type="thinking", thinking="", signature="b"),
        Block(type="text", text="sonra"),
    ]
    out = echo_content(content)
    assert [b["type"] for b in out] == ["text", "fallback", "thinking", "text"]
    assert out[2]["signature"] == "b"


async def test_last_round_keeps_tool_definitions_with_tool_choice_none():
    client = FakeClient(([], final([], "end_turn")), ([], final([], "end_turn")))
    p = provider(client)
    await collect(p, [Msg("user", "x")], [TOOL])
    history = [
        Msg("user", "x"),
        Msg("assistant", "", tool_calls=[ToolCall("t", "list_boards", {})]),
        Msg("tool", "[]", tool_call_id="t", name="list_boards"),
    ]
    await collect(p, history, None)
    assert client.calls[1]["tool_choice"] == {"type": "none"}
    assert client.calls[1]["tools"][0]["name"] == "list_boards"
