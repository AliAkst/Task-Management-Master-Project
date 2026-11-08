"""
Agent dongusu: modeli stream et -> arac cagrisi varsa calistir -> sonucu modele
geri ver -> ... (en fazla N tur). Tum adimlar olay (event) olarak disari akar;
API katmani bunlari SSE'ye, kalicilik katmani mesajlara cevirir.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from app.llm.types import LLMError, LLMProvider, Msg, ToolCall, Usage
from app.tools.read_tools import ToolBox

EventType = Literal["token", "tool_start", "tool_end", "action", "message", "error"]


@dataclass
class AgentEvent:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    # type == "message": kalici olarak saklanacak mesaj
    message: Msg | None = None
    usage: Usage | None = None


FORCE_ANSWER = (
    "Araç kullanma sınırına ulaştın. Elindeki bilgilerle kullanıcıya şimdi kısa bir "
    "cevap ver; eksik kalanı belirt."
)


async def run_agent(
    provider: LLMProvider,
    messages: list[Msg],
    toolbox: ToolBox,
    *,
    max_rounds: int = 6,
) -> AsyncIterator[AgentEvent]:
    """messages: sistem + gecmis + yeni kullanici mesaji (yerinde genisletilir)."""
    specs = toolbox.specs()
    for round_no in range(max_rounds + 1):
        last_round = round_no == max_rounds
        if last_round:
            messages.append(Msg("system", FORCE_ANSWER))
        text = ""
        calls: list[ToolCall] = []
        usage = Usage()
        state = None
        try:
            async for chunk in provider.stream(messages, None if last_round else specs):
                if chunk.type == "text":
                    text += chunk.text
                    yield AgentEvent("token", {"text": chunk.text})
                elif chunk.type == "tool_call" and chunk.tool_call:
                    calls.append(chunk.tool_call)
                elif chunk.type == "usage" and chunk.usage:
                    usage = chunk.usage
                elif chunk.type == "state":
                    state = chunk.state
        except LLMError as e:
            yield AgentEvent("error", {"message": str(e)})
            return

        assistant = Msg(
            "assistant", text, tool_calls=calls or None, provider_state=state
        )
        messages.append(assistant)
        yield AgentEvent("message", message=assistant, usage=usage)
        if not calls:
            return

        for call in calls:
            yield AgentEvent(
                "tool_start",
                {"id": call.id, "name": call.name, "arguments": call.arguments},
            )
            result = await toolbox.execute(call)
            tool_msg = Msg("tool", result.text, tool_call_id=call.id, name=call.name)
            messages.append(tool_msg)
            yield AgentEvent(
                "tool_end", {"id": call.id, "name": call.name, "ok": result.ok}
            )
            if result.action is not None:
                yield AgentEvent("action", result.action)
            yield AgentEvent("message", message=tool_msg)
