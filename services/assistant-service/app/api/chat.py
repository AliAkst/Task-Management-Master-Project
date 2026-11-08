"""Sohbet API'si: model listesi, konusmalar, SSE ile akan sohbet."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.actions import ActionGate, action_payload, load_modes
from app.agent.context import build_system_prompt, focus_line
from app.agent.day_planner import is_schedule_request, is_tidy_request, plan_day
from app.agent.loop import run_agent
from app.agent.memory_extractor import (
    CHAT_HIDDEN_TOOLS,
    MEMORY_TOOLS,
    extract_memory,
)
from app.api.deps import current_user, ok
from app.api.providers import (
    enabled_cloud_models,
    load_cloud_config,
    user_background_model,
    user_default_model,
)
from app.config import settings
from app.db.models import (
    AiActionEntity,
    ConversationEntity,
    MessageEntity,
    get_session,
    session_maker,
)
from app.llm.registry import (
    build_provider,
    cloud_models,
    is_local_model,
    list_local_models,
    parse_model_id,
)
from app.llm.router import resolve_model
from app.llm.types import LLMError, Msg, ToolCall
from app.tools.memory_tools import MemoryTools, load_facts
from app.tools.read_tools import ToolBox
from app.tools.task_api import TaskApiClient, TaskApiError

router = APIRouter()
HISTORY_LIMIT = 40
DEFAULT_TZ = "Europe/Istanbul"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    conversation_id: int | None = None
    # None: otomatik (acik board'un varsayilani > kullanicinin local varsayilani)
    model_id: str | None = None
    board_id: int | None = None  # kullanicinin o an baktigi board (varsa)
    card_id: int | None = None  # acik kart penceresi ("bu kart")


class TitleUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


# ---------------- yardimcilar ----------------
def to_msg(m: MessageEntity) -> Msg:
    calls = (
        [
            ToolCall(id=c["id"], name=c["name"], arguments=c.get("arguments") or {})
            for c in m.tool_calls
        ]
        if m.tool_calls
        else None
    )
    return Msg(
        m.role,
        m.content,
        tool_calls=calls,
        tool_call_id=m.tool_call_id,
        name=m.tool_name,
    )  # type: ignore[arg-type]


def sanitize(history: list[MessageEntity]) -> list[MessageEntity]:
    """
    Yarim kalmis arac adimlarini at: sonucu kaydedilmemis tool_call'lu asistan
    mesaji ya da cagrisi olmayan tool mesaji saglayicilarda hata verir.
    """
    answered = {m.tool_call_id for m in history if m.role == "tool"}
    called: set[str] = set()
    out = []
    for m in history:
        if m.role == "assistant" and m.tool_calls:
            ids = {c["id"] for c in m.tool_calls}
            if not ids <= answered:
                continue
            called |= ids
        if m.role == "tool" and m.tool_call_id not in called:
            continue
        out.append(m)
    return out


async def owned_conversation(
    session: AsyncSession, conversation_id: int, user_id: int
) -> ConversationEntity:
    conv = await session.get(ConversationEntity, conversation_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(404, "Sohbet bulunamadı")
    return conv


def sse(event: str, data: dict[str, Any]) -> str:
    return (
        f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
    )


# ---------------- uc noktalar ----------------
@router.get("/models")
async def models(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    items = await list_local_models() + cloud_models(
        await enabled_cloud_models(session, user["id"])
    )
    return ok(
        {
            "default": await user_default_model(session, user["id"]),
            "models": [
                {
                    "id": m.id,
                    "label": m.label,
                    "provider": m.provider,
                    "is_local": m.is_local,
                }
                for m in items
            ],
        }
    )


@router.get("/conversations")
async def conversations(
    user: dict = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    rows = await session.scalars(
        select(ConversationEntity)
        .where(ConversationEntity.user_id == user["id"])
        .order_by(ConversationEntity.updated_at.desc())
        .limit(100)
    )
    return ok(
        [{"id": c.id, "title": c.title, "updated_at": c.updated_at} for c in rows]
    )


@router.get("/conversations/{conversation_id}/messages")
async def messages(
    conversation_id: int,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    await owned_conversation(session, conversation_id, user["id"])
    rows = list(
        await session.scalars(
            select(MessageEntity)
            .where(MessageEntity.conversation_id == conversation_id)
            .order_by(MessageEntity.id)
        )
    )
    all_actions = list(
        await session.scalars(
            select(AiActionEntity)
            .where(AiActionEntity.conversation_id == conversation_id)
            .order_by(AiActionEntity.id)
        )
    )
    linked = {c["id"] for m in rows for c in m.tool_calls or []}
    actions = {
        a.tool_call_id: action_payload(a)
        for a in all_actions
        if a.tool_call_id in linked
    }
    # Hafiza cikarimi gibi sohbet mesajina bagli olmayan oneriler: kendisinden
    # once yazilmis son asistan cevabina eklenir (sayfa yenilense de gorunsun)
    extra: dict[int, list[dict]] = {}
    answers = [m for m in rows if m.role == "assistant" and m.content]
    for a in all_actions:
        if a.tool_call_id in linked or not answers:
            continue
        before = [m for m in answers if m.created_at <= a.created_at]
        target = (before or answers)[-1]
        extra.setdefault(target.id, []).append(action_payload(a))
    return ok(
        [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tools": [c["name"] for c in m.tool_calls or []],
                "actions": [
                    actions[c["id"]] for c in m.tool_calls or [] if c["id"] in actions
                ]
                + extra.get(m.id, []),
                "model_id": m.model_id,
                "is_local": m.is_local,
                "created_at": m.created_at,
            }
            for m in rows
            if m.role != "tool"
        ]
    )


@router.patch("/conversations/{conversation_id}")
async def rename(
    conversation_id: int,
    data: TitleUpdate,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    conv = await owned_conversation(session, conversation_id, user["id"])
    conv.title = data.title
    await session.commit()
    return ok({"id": conv.id, "title": conv.title})


@router.delete("/conversations/{conversation_id}", status_code=204)
async def remove(
    conversation_id: int,
    user: dict = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    conv = await owned_conversation(session, conversation_id, user["id"])
    await session.execute(
        delete(MessageEntity).where(MessageEntity.conversation_id == conv.id)
    )
    # SQLite'ta FK kapali: islemler silinmez ama sohbetten kopar; aksi halde ayni
    # numarayi alan yeni sohbete karisiyorlardi
    await session.execute(
        update(AiActionEntity)
        .where(AiActionEntity.conversation_id == conv.id)
        .values(conversation_id=None)
    )
    await session.delete(conv)
    await session.commit()
    return Response(status_code=204)


@router.post("/chat")
async def chat(data: ChatRequest, user: dict = Depends(current_user)):
    """SSE: start, token, tool_start, tool_end, done | error olaylari."""
    async with session_maker() as session:
        default = await user_default_model(session, user["id"])
        api = TaskApiClient(user["token"])
        try:
            route = await resolve_model(
                api,
                requested=data.model_id,
                board_id=data.board_id,
                user_default=default,
            )
        finally:
            await api.close()
        model_id = route.model_id
        try:
            cloud = (
                None
                if is_local_model(model_id)
                else await load_cloud_config(
                    session, user["id"], parse_model_id(model_id)[0]
                )
            )
            provider = build_provider(model_id, cloud)
        except LLMError as e:
            raise HTTPException(422, str(e)) from e

    # Sohbet kaydi akistan ONCE (hata varsa normal HTTP hatasi donsun)
    async with session_maker() as session:
        if data.conversation_id is not None:
            conv = await owned_conversation(session, data.conversation_id, user["id"])
        else:
            conv = ConversationEntity(
                user_id=user["id"], title=data.message.strip()[:60]
            )
            session.add(conv)
            await session.commit()
        conversation_id = conv.id

    return StreamingResponse(
        _stream(
            user,
            conversation_id,
            data.message,
            provider,
            model_id,
            route.source,
            board_id=data.board_id,
            card_id=data.card_id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream(
    user: dict,
    conversation_id: int,
    text: str,
    provider,
    model_id: str,
    model_source: str = "message",
    board_id: int | None = None,
    card_id: int | None = None,
) -> AsyncIterator[str]:
    is_local = provider.info.is_local
    api = TaskApiClient(user["token"])
    try:
        async with session_maker() as session:
            rows = list(
                await session.scalars(
                    select(MessageEntity)
                    .where(MessageEntity.conversation_id == conversation_id)
                    .order_by(MessageEntity.id.desc())
                    .limit(HISTORY_LIMIT)
                )
            )[::-1]
            # Gizlilik: local modelle uretilmis mesajlar bulut modele gitmez
            dropped = 0 if is_local else sum(1 for m in rows if m.is_local)
            history = sanitize([m for m in rows if is_local or not m.is_local])

            settings_data = await api.get("/settings/")
            tz = ZoneInfo(settings_data.get("timezone") or DEFAULT_TZ)
            toolbox = await ToolBox.create(api, cloud=not is_local, tz=tz)
            toolbox.hidden = set(CHAT_HIDDEN_TOOLS)
            toolbox.writer.memory = MemoryTools(
                session_maker, user["id"], cloud=not is_local
            )
            facts = await load_facts(session, user["id"], include_private=is_local)
            toolbox.gate = ActionGate(
                session_maker,
                toolbox.writer,
                user_id=user["id"],
                conversation_id=conversation_id,
                model_id=model_id,
                modes=await load_modes(session, user["id"]),
            )
            focus = await focus_line(api, toolbox, board_id, card_id)
            system = await build_system_prompt(
                api, toolbox, user, tz, provider.info.label, is_local, facts, focus
            )

            user_row = MessageEntity(
                conversation_id=conversation_id,
                role="user",
                content=text,
                model_id=model_id,
                is_local=is_local,
            )
            session.add(user_row)
            await session.commit()
            yield sse(
                "start",
                {
                    "conversation_id": conversation_id,
                    "model_id": model_id,
                    "model_label": provider.info.label,
                    "model_source": model_source,
                    "is_local": is_local,
                    "dropped_local_messages": dropped,
                },
            )

            # "Profilimi/hafizani temizle": model gerekmez, kod adaylari bulur
            if is_tidy_request(text) and toolbox.gate.allowed("forget_fact"):
                result = await toolbox.execute(
                    ToolCall(
                        id=f"tidy-{conversation_id}-{user_row.id}",
                        name="tidy_facts",
                        arguments={},
                    )
                )
                if result.action is not None:
                    yield sse("action", result.action)
                    reply = (
                        "Profilinde temizlenecekleri buldum; onay kartından kontrol et."
                    )
                else:
                    reply = (
                        json.loads(result.text).get("error")
                        or "Temizlenecek bilgi yok."
                    )
                yield sse("token", {"text": reply})
                session.add(
                    MessageEntity(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=reply,
                        model_id=model_id,
                        is_local=is_local,
                    )
                )
                await session.commit()
                yield sse("done", {"conversation_id": conversation_id})
                return

            # Gunu saat saat planlama istegi: odakli planlama adimi (tek arac)
            if is_schedule_request(text) and toolbox.gate.allowed("schedule_day"):
                planner = (
                    provider
                    if model_source == "message"
                    else await _planning_provider(session, user["id"], provider)
                )
                planned = None
                toolbox.gate.model_id = planner.info.id  # oneriyi yapan model
                async for ev in plan_day(planner, toolbox, text):
                    if ev.type == "planned":
                        planned = ev.data
                    elif ev.type != "failed":
                        yield sse(ev.type, ev.data)
                toolbox.gate.model_id = model_id  # normal sohbete donulurse
                if planned is not None:
                    reply = (
                        f"Planı hazırladım ({planner.info.label}). Onay kartından "
                        "saatleri kontrol et: onaylarsan yapılacak işler kart olarak "
                        "açılır, hepsi takvime ve kartlar günün planına eklenir. Bir "
                        "şey yanlışsa nedenini yazarak reddet, düzelteyim."
                    )
                    yield sse("token", {"text": reply})
                    session.add(
                        MessageEntity(
                            conversation_id=conversation_id,
                            role="assistant",
                            content=reply,
                            model_id=planner.info.id,
                            is_local=planner.info.is_local,
                        )
                    )
                    conv = await session.get(ConversationEntity, conversation_id)
                    if conv is not None:
                        conv.updated_at = datetime.now(UTC)
                    await session.commit()
                    yield sse("done", {"conversation_id": conversation_id})
                    return

            msgs = [Msg("system", system), *map(to_msg, history), Msg("user", text)]
            used_memory_tool = False
            used_action_tool = False  # komut turu (kart/plan...) -> hafiza adimi yok
            async for ev in run_agent(
                provider, msgs, toolbox, max_rounds=settings.max_tool_rounds
            ):
                if ev.type == "message" and ev.message is not None:
                    m = ev.message
                    session.add(
                        MessageEntity(
                            conversation_id=conversation_id,
                            role=m.role,
                            content=m.content,
                            tool_calls=[
                                {"id": c.id, "name": c.name, "arguments": c.arguments}
                                for c in m.tool_calls
                            ]
                            if m.tool_calls
                            else None,
                            tool_call_id=m.tool_call_id,
                            tool_name=m.name,
                            model_id=model_id,
                            is_local=is_local,
                            tokens_in=ev.usage.prompt_tokens if ev.usage else None,
                            tokens_out=ev.usage.completion_tokens if ev.usage else None,
                        )
                    )
                    await session.commit()
                elif ev.type == "error":
                    yield sse("error", ev.data)
                    return
                else:
                    if ev.type == "tool_start" and ev.data.get("name") in MEMORY_TOOLS:
                        used_memory_tool = True
                    if ev.type == "action":
                        used_action_tool = True
                    yield sse(ev.type, ev.data)

            # Sohbet modeli hafizaya dokunmadiysa: ayri, odakli hafiza cikarimi
            if (
                settings.memory_extraction
                and not used_memory_tool
                and not used_action_tool
            ):
                async for ev in extract_memory(provider, toolbox, text, facts):
                    yield sse(ev.type, ev.data)

            conv = await session.get(ConversationEntity, conversation_id)
            if conv is not None:
                conv.updated_at = datetime.now(UTC)
                await session.commit()
            yield sse("done", {"conversation_id": conversation_id})
    except TaskApiError as e:
        yield sse("error", {"message": e.message})
    finally:
        await api.close()


async def _planning_provider(session: AsyncSession, user_id: int, fallback):
    """
    Planlama icin arka plan modeli (varsayilan gemma4:26b): yavas ama gunu dogru
    kuruyor. Sadece LOCAL ve kuruluysa; degilse sohbet modeli. Bulut arka plan
    modeli sohbet turunda kendiliginden kullanilmaz (ucret: kullanici secmeli).
    """
    installed = {m.id for m in await list_local_models()}
    model_id = await user_background_model(session, user_id, installed)
    if model_id == fallback.info.id or not is_local_model(model_id):
        return fallback
    if model_id not in installed:
        return fallback
    return build_provider(model_id, None, timeout=settings.background_timeout_seconds)
