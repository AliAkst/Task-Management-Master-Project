"""Sohbet API'si: model listesi, konusmalar, SSE ile akan sohbet."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.actions import ActionGate, action_payload, load_modes
from app.agent.answers import match_answer
from app.agent.context import build_system_prompt, focus_line
from app.agent.day_mentions import day_mentions
from app.agent.day_planner import (
    GIVE_UP,
    apply_answer,
    is_schedule_request,
    is_tidy_request,
    plan_day,
    question_event,
)
from app.agent.fmt import fmt_day_long
from app.agent.guard import TurnFacts, check_reply
from app.agent.loop import AgentEvent, run_agent
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
from app.tools.placement import day_question
from app.tools.read_tools import ToolBox
from app.tools.task_api import TaskApiAuthError, TaskApiClient, TaskApiError

router = APIRouter()
HISTORY_LIMIT = 40
QUESTION_TTL = timedelta(minutes=30)  # Faz 13d: soru bu sure cevap bekler
SETTLED = ("question", "answered", "expired")  # sohbette kart olarak gosterilmez
DEFAULT_TZ = "Europe/Istanbul"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    conversation_id: int | None = None
    # None: otomatik (acik board'un varsayilani > kullanicinin local varsayilani)
    model_id: str | None = None
    board_id: int | None = None  # kullanicinin o an baktigi board (varsa)
    card_id: int | None = None  # acik kart penceresi ("bu kart")
    # Web AUTH_EXPIRED sonrasi ayni mesaji tekrar gonderir: kullanici satiri cogalmaz
    resend: bool = False


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
        if a.tool_call_id in linked or not answers or a.status in SETTLED:
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
        except TaskApiAuthError as e:
            raise HTTPException(401, "Oturum süresi doldu") from e
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
            resend=data.resend,
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
    resend: bool = False,
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
                session_maker,
                user["id"],
                cloud=not is_local,
                api=api,
                provider=provider if is_local else None,
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

            user_row = None
            if resend:
                # Onceki (AUTH_EXPIRED ile kesilen) tur ayni mesaji zaten kaydettiyse
                # onu kullan; yenisini ekleme
                # (Kesilen turun araci cagiran asistan satiri kullanicinin ardindan
                # kalmis olabilir: tamamlanmis cevap yoksa tur yarim sayilir.)
                last = await session.scalar(
                    select(MessageEntity)
                    .where(
                        MessageEntity.conversation_id == conversation_id,
                        MessageEntity.role == "user",
                    )
                    .order_by(MessageEntity.id.desc())
                    .limit(1)
                )
                if last is not None and last.content == text:
                    later = await session.scalars(
                        select(MessageEntity).where(
                            MessageEntity.conversation_id == conversation_id,
                            MessageEntity.id > last.id,
                            MessageEntity.role == "assistant",
                        )
                    )
                    if not any(not m.tool_calls for m in later):
                        user_row = last
            if user_row is None:
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

            # Faz 13d: bekleyen numarali soruya cevap mi? (model cagrilmaz)
            events = None
            planner = provider
            answering = False  # secenek uygulandi: hata sohbete degil kullaniciya soylenir
            pending = await _pending_question(session, conversation_id)
            if pending is not None:
                opts = pending.args.get("options") or []
                ans = match_answer(text, len(opts))
                pending.status = "answered" if isinstance(ans, int) else "expired"
                await session.commit()
                if ans == "cancel":
                    for out in await _say(
                        session, conversation_id, "Tamam, planı bıraktım.", model_id, is_local
                    ):
                        yield out
                    return
                if isinstance(ans, int):
                    if pending.args.get("kind") == "day":
                        # Q5: secilen gun kodla zorlanir, model yalniz maddeleri cikarir
                        planner = (
                            provider
                            if model_source == "message"
                            else await _planning_provider(session, user["id"], provider)
                        )
                        events = plan_day(
                            planner,
                            toolbox,
                            pending.args.get("user_text") or text,
                            forced_day=date.fromisoformat(opts[ans - 1]["patch"]["day"]),
                        )
                    else:
                        events = apply_answer(toolbox, pending.args, ans - 1)
                        answering = True

            # Gunu saat saat planlama istegi: odakli planlama adimi (tek arac)
            if (
                events is None
                and is_schedule_request(text)
                and toolbox.gate.allowed("schedule_day")
            ):
                planner = (
                    provider
                    if model_source == "message"
                    else await _planning_provider(session, user["id"], provider)
                )
                now_local, rollover = await toolbox.writer._planning()
                days = day_mentions(text, now_local, rollover)
                if len(days) >= 2:  # iki farkli gun: once sor, modeli cagirma
                    events = _single_event(
                        question_event(day_question(days), {"kind": "day"}, text, 0)
                    )
                else:
                    events = plan_day(
                        planner, toolbox, text, forced_day=days[0] if days else None
                    )

            if events is not None:
                planned = None
                question = None
                failure = None
                toolbox.gate.model_id = planner.info.id  # oneriyi yapan model
                async for ev in events:
                    if ev.type == "planned":
                        planned = ev.data
                    elif ev.type == "question":
                        question = ev.data
                    elif ev.type == "failed":
                        failure = ev.data
                    else:
                        yield sse(ev.type, ev.data)
                toolbox.gate.model_id = model_id  # normal sohbete donulurse
                if question is not None:
                    q = question["question"]
                    await _store_question(
                        session, user["id"], conversation_id, question, planner.info.id
                    )
                    for out in await _say(
                        session,
                        conversation_id,
                        q.text,
                        planner.info.id,
                        planner.info.is_local,
                    ):
                        yield out
                    return
                if planned is not None:
                    reply = (
                        f"{_plan_day_prefix(planned)}planını hazırladım "
                        f"({planner.info.label}). Onay kartından "
                        "saatleri kontrol et: onaylarsan özetteki YENİ kartlar açılır, var olan kartlar "
                        "kullanılır; hepsi takvime ve kartlar günün planına eklenir. Bir "
                        "şey yanlışsa nedenini yazarak reddet, düzelteyim."
                    ) + await _rollover_note(toolbox, planned)
                    for out in await _say(
                        session,
                        conversation_id,
                        reply,
                        planner.info.id,
                        planner.info.is_local,
                    ):
                        yield out
                    return
                if answering and failure is not None:
                    err = (failure or {}).get("error")
                    reply = (
                        GIVE_UP
                        if failure.get("final")
                        else f"Planı kuramadım: {err or 'bilinmeyen hata'}"
                    )
                    for out in await _say(
                        session, conversation_id, reply, model_id, is_local
                    ):
                        yield out
                    return

            msgs = [Msg("system", system), *map(to_msg, history), Msg("user", text)]
            used_memory_tool = False
            used_action_tool = False  # komut turu (kart/plan...) -> hafiza adimi yok
            facts_pending = 0  # Faz 13e: bu turdaki onay bekleyen / yapilmis yazmalar
            facts_executed = 0
            last_reply_row: MessageEntity | None = None  # araç çağrısız son asistan metni
            async for ev in run_agent(
                provider, msgs, toolbox, max_rounds=settings.max_tool_rounds
            ):
                if ev.type == "message" and ev.message is not None:
                    m = ev.message
                    row = MessageEntity(
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
                    session.add(row)
                    if m.role == "assistant" and not m.tool_calls:
                        last_reply_row = row
                    await session.commit()
                elif ev.type == "error":
                    yield sse("error", ev.data)
                    return
                elif ev.type == "question":
                    # T2-D2: normal yolda da soru saklanir (cevap model cagirmadan uygulanir)
                    await _store_question(
                        session,
                        user["id"],
                        conversation_id,
                        question_event(
                            ev.data["question"], ev.data.get("state") or {}, text, 0
                        ).data,
                        model_id,
                    )
                else:
                    if ev.type == "tool_start" and ev.data.get("name") in MEMORY_TOOLS:
                        used_memory_tool = True
                    if ev.type == "action":
                        used_action_tool = True
                        if ev.data.get("status") == "proposed":
                            facts_pending += 1
                        elif ev.data.get("status") == "executed":
                            facts_executed += 1
                    yield sse(ev.type, ev.data)

            # Faz 13e: "ekledim/yaptim" iddiasi gercekle celisiyorsa balonun altina uyari
            if last_reply_row is not None:
                warning = check_reply(
                    last_reply_row.content or "",
                    TurnFacts(facts_pending, facts_executed),
                )
                if warning:
                    last_reply_row.content = f"{last_reply_row.content}\n\n{warning}"
                    await session.commit()
                    yield sse("guard", {"text": warning})

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
    except TaskApiAuthError:
        # Arac sonucu modele/kayda yazilmadi; web yeniler ve (uygunsa) tek tekrar yapar
        yield sse(
            "error",
            {
                "code": "AUTH_EXPIRED",
                "message": "Oturum süresi doldu",
                "conversation_id": conversation_id,
            },
        )
    except TaskApiError as e:
        yield sse("error", {"message": e.message})
    finally:
        await api.close()


def _plan_day_prefix(planned: dict[str, Any]) -> str:
    """'Cumartesi 14 Kasım ' (tarih bilinmiyorsa 'Günün ') — cümle başı."""
    try:
        d = date.fromisoformat((planned.get("args") or {})["date"])
    except (KeyError, ValueError, TypeError):
        return "Günün "
    return f"{fmt_day_long(d)} "


async def _rollover_note(toolbox: ToolBox, planned: dict[str, Any]) -> str:
    args = planned.get("args") or {}
    if not args.get("day_rolled"):
        return ""
    now_local, _ = await toolbox.writer._planning()
    raw = str(args.get("day_raw") or "yarın").strip()
    day = fmt_day_long(date.fromisoformat(args["date"]))
    return f' (Saat {now_local:%H:%M}; "{raw}"ı {day} olarak aldım.)'


async def _single_event(ev: AgentEvent) -> AsyncIterator[AgentEvent]:
    yield ev


async def _store_question(
    session: AsyncSession,
    user_id: int,
    conversation_id: int,
    question: dict[str, Any],
    model_id: str,
) -> None:
    """Bekleyen tek soruyu `ai_actions status='question'` olarak yazar (eskiler expired)."""
    await _expire_questions(session, conversation_id)
    session.add(
        AiActionEntity(
            user_id=user_id,
            conversation_id=conversation_id,
            action_type="schedule_day",
            args=question["state"],
            summary=question["question"].text,
            status="question",
            model_id=model_id,
        )
    )
    await session.commit()


async def _expire_questions(session: AsyncSession, conversation_id: int) -> None:
    await session.execute(
        update(AiActionEntity)
        .where(
            AiActionEntity.conversation_id == conversation_id,
            AiActionEntity.status == "question",
        )
        .values(status="expired")
    )


async def _pending_question(
    session: AsyncSession, conversation_id: int
) -> AiActionEntity | None:
    """Bu konusmada cevap bekleyen son soru (TTL icinde); eskiler kapatilir."""
    row = await session.scalar(
        select(AiActionEntity)
        .where(
            AiActionEntity.conversation_id == conversation_id,
            AiActionEntity.status == "question",
        )
        .order_by(AiActionEntity.id.desc())
        .limit(1)
    )
    if row is None:
        return None
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if datetime.now(UTC) - created > QUESTION_TTL:
        await _expire_questions(session, conversation_id)
        await session.commit()
        return None
    return row


async def _say(
    session: AsyncSession,
    conversation_id: int,
    reply: str,
    model_id: str,
    is_local: bool,
) -> list[str]:
    """Kod yazimli cevap: SSE token + asistan mesaji + done."""
    session.add(
        MessageEntity(
            conversation_id=conversation_id,
            role="assistant",
            content=reply,
            model_id=model_id,
            is_local=is_local,
        )
    )
    conv = await session.get(ConversationEntity, conversation_id)
    if conv is not None:
        conv.updated_at = datetime.now(UTC)
    await session.commit()
    return [
        sse("token", {"text": reply}),
        sse("done", {"conversation_id": conversation_id}),
    ]


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
