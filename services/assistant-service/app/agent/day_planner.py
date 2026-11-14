"""
Gun planlama adimi: "sali gunu icin ... planla" gibi isteklerde sohbet modeli
yerine calisan, TEK gorevli ve TEK aracli (schedule_day) odakli cagri.

Neden: gercek testte qwen3.5:4b bu istekte araci hic cagirmadi, metinle yanlis
gun ve tutarsiz saatlerle plan yazip onay istedi; ayni model odakli istem + ornek
+ hata geri bildirimiyle gecerli cizelge uretiyor. Anlamca en iyi sonucu
gemma4:26b verdigi icin varsayilan olarak arka plan modeli kullanilir.
"""

import json
import re
import secrets
from collections.abc import AsyncIterator
from datetime import date, datetime, time
from typing import Any

from app.agent.loop import AgentEvent
from app.llm.types import LLMError, LLMProvider, Msg, ToolCall
from app.tools.placement import Question, apply_patch, day_label
from app.tools.read_tools import ToolBox
from app.tools.schedule_day import SCHEDULE_SPEC, resolve_day_ex

MAX_ATTEMPTS = 3
WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

_DAY = re.compile(
    r"\b(bugün|bugun|yarın|yarin|öbür gün|pazartesi|salı|sali|çarşamba|carsamba|"
    r"perşembe|persembe|cuma|cumartesi|pazar|\d{1,2}\s+(ocak|şubat|mart|nisan|mayıs|"
    r"haziran|temmuz|ağustos|eylül|ekim|kasım|aralık))",
)
_PLAN = re.compile(
    r"(planla|plan yap|plan çıkar|programla|program yap|saat saat|takvime)"
)
_QUESTION = re.compile(r"(\?\s*$|\bneler\b|\bne var\b|göster|listele|nasıl geçti)")


_TIDY = re.compile(
    r"(profil|hafıza|hafiza|bilgi|hakkımda)\w*.{0,40}(temizle|düzelt|toparla|sadeleştir)"
    r"|(temizle|toparla)\w*.{0,40}(profil|hafıza|hafiza|bilgi)"
)


def is_tidy_request(text: str) -> bool:
    """'Profilimi temizle', 'hafızanı toparla' gibi istekler."""
    return bool(_TIDY.search(text.casefold()))


def is_schedule_request(text: str) -> bool:
    """Bir gunu saat saat planlama istegi mi? (soru/listeleme degil)"""
    t = text.casefold()
    return bool(_DAY.search(t) and _PLAN.search(t) and not _QUESTION.search(t))


PROMPT = """Görevin SADECE: kullanıcının anlattığı günü schedule_day aracıyla planlamak.
Bugün: {today}. Board'lar: {boards}.{day_line}

Nasıl:
1. İşleri kullanıcının SÖYLEDİĞİ SIRAYLA items listesine yaz.
2. Kullanıcı saat verdiyse start yaz; bitiş ya da süre söylediyse end ya da minutes ekle.
3. Yalnız süre söylendiyse SADECE minutes yaz. Saat hesaplama: kod boş zamana yerleştirir.
4. "Sabah", "öğlen", "akşam" dendiyse window yaz.
5. Saat de süre de söylenmediyse start, minutes, end YAZMA.
6. Yol, iş, mesai, öğle arası gibi şeyleri YAZMA; gün şablonundan kod ekler. Şablonda olmayan bir sabit şey söylendiyse card=false.
7. Yapılacak işler (spor, alışveriş, eğitim): card=true ve uygun board.
8. Var olan kartı adıyla anıyorsa title'a SADECE kartın adını, board'a board adını yaz.
9. Boş zamana kullanıcının söylemediği iş ekleme.

Örnek: "Yarın evden çalışıyorum. Faruk abinin kavramlarına 1 saat, Power BI P2, akşam 45 dk koşu."
schedule_day({{"day": "yarın", "items": [
 {{"title": "Faruk abi — kavramlar", "minutes": 60, "card": true, "board": "İş"}},
 {{"title": "P2", "card": true, "board": "Eğitimler"}},
 {{"title": "Koşu", "minutes": 45, "window": "akşam", "card": true, "board": "Spor"}}]}})

Örnek: "Cumartesi 10'da kuyumcu, sonra market 30 dk."
schedule_day({{"day": "cumartesi", "items": [
 {{"title": "Kuyumcu", "start": "10:00", "card": true, "board": "Günlük işler"}},
 {{"title": "Market", "minutes": 30, "card": true, "board": "Günlük işler"}}]}})

Metin yazma; sadece aracı çağır."""

MAX_CHAIN = 3  # art arda en fazla bu kadar soru; sonra kullanicidan tek mesaj istenir
GIVE_UP = "Planı netleştiremedim; saatleri tek mesajda yazıp tekrar dener misin?"


def _day_line(forced_day: date | None, now: datetime, rollover: time) -> str:
    if forced_day is not None:
        return f"\nGün KESİN: {day_label(forced_day)} (day alanına bunu yaz)."
    if now.time() < rollover:
        tomorrow = resolve_day_ex(
            "yarın", now.date(), now_local=now, rollover=rollover
        )[0]
        return f"\nSaat {now:%H:%M}: 'yarın' = {day_label(tomorrow)}."
    return ""


def question_event(
    question: Question,
    state: dict[str, Any],
    user_text: str,
    chain: int = 0,
) -> AgentEvent:
    """Soru + saklanacak durum (ai_actions.args, status='question')."""
    data = {
        **state,
        "text": question.text,
        "options": [{"label": o.label, "patch": o.patch} for o in question.options],
        "chain": chain,
        "user_text": user_text,
    }
    return AgentEvent("question", {"question": question, "state": data})


async def plan_day(
    provider: LLMProvider,
    toolbox: ToolBox,
    user_text: str,
    forced_day: date | None = None,
) -> AsyncIterator[AgentEvent]:
    """
    Olaylar: tool_start / tool_end / action ve sonunda "planned" (data: ozet),
    "question" (kullaniciya tek numarali soru) ya da "failed" (normal sohbete
    devam edilir). `forced_day`: gun kodla belirlendi, modelin day'i yok sayilir.
    """
    now, rollover = await toolbox.writer._planning()
    boards = ", ".join(b["name"] for b in await toolbox.boards()) or "(yok)"
    today = f"{now:%Y-%m-%d} {WEEKDAYS[now.weekday()]}"
    msgs = [
        Msg(
            "system",
            PROMPT.format(
                today=today,
                boards=boards,
                day_line=_day_line(forced_day, now, rollover),
            ),
        ),
        Msg("user", user_text),
    ]
    yield AgentEvent("tool_start", {"name": "schedule_day"})
    for _ in range(MAX_ATTEMPTS):
        calls = []
        try:
            async for chunk in provider.stream(msgs, [SCHEDULE_SPEC], temperature=0.1):
                if chunk.type == "tool_call" and chunk.tool_call:
                    calls.append(chunk.tool_call)
        except LLMError as e:
            yield AgentEvent("tool_end", {"name": "schedule_day", "ok": False})
            yield AgentEvent("failed", {"error": str(e)})
            return
        call = next((c for c in calls if c.name == "schedule_day"), None)
        if call is None:
            break
        if call.valid:
            # _day_raw: modelin verdigi gun dizesi (kayit icin); forced ise kod yazar
            call.arguments = {
                **call.arguments,
                "_day_raw": call.arguments.get("day"),
                **({"day": forced_day.isoformat()} if forced_day else {}),
            }
        result = await toolbox.execute(call)
        done = False
        async for ev in _outcome(result, user_text, 0):
            yield ev
            done = done or ev.type in ("planned", "question")
        if done:
            return
        # Hata: modele aynen geri ver, duzeltsin
        msgs += [
            Msg("assistant", None, tool_calls=[call]),
            Msg("tool", result.text, tool_call_id=call.id, name=call.name),
        ]
    yield AgentEvent("tool_end", {"name": "schedule_day", "ok": False})
    yield AgentEvent("failed", {"error": _last_error(msgs)})


async def _outcome(
    result: Any, user_text: str, chain: int
) -> AsyncIterator[AgentEvent]:
    """Arac sonucu -> olaylar (planned | question); hata ise hicbir sey uretmez."""
    if result.question is not None:
        yield AgentEvent("tool_end", {"name": "schedule_day", "ok": True})
        yield question_event(result.question, result.state or {}, user_text, chain)
    elif result.ok and result.action is not None:
        yield AgentEvent("tool_end", {"name": "schedule_day", "ok": True})
        yield AgentEvent("action", result.action)
        yield AgentEvent("planned", {"summary": result.action["summary"]})


async def apply_answer(
    toolbox: ToolBox, pending: dict[str, Any], index: int
) -> AsyncIterator[AgentEvent]:
    """
    Kullanici soruya numarayla cevap verdi: secenegin patch'i uygulanir, plan MODEL
    CAGRILMADAN yeniden kurulur (onay karti ya da yeni soru).
    """
    state = apply_patch(pending, pending["options"][index]["patch"])
    args: dict[str, Any] = {
        "day": state["day"],
        "items": state["items"],
        "_day_raw": state.get("day_raw"),
    }
    if state.get("template_off"):
        args["_template"] = "off"
    if state.get("unfit"):
        args["_unfit"] = state["unfit"]
    call = ToolCall(
        id=f"answer-{secrets.token_hex(4)}", name="schedule_day", arguments=args
    )
    yield AgentEvent("tool_start", {"name": "schedule_day"})
    chain = int(pending.get("chain", 0)) + 1
    result = await toolbox.execute(call)
    if result.question is not None and chain > MAX_CHAIN:
        yield AgentEvent("tool_end", {"name": "schedule_day", "ok": False})
        yield AgentEvent("failed", {"error": GIVE_UP, "final": True})
        return
    produced = False
    async for ev in _outcome(result, pending.get("user_text", ""), chain):
        produced = True
        yield ev
    if not produced:
        yield AgentEvent("tool_end", {"name": "schedule_day", "ok": False})
        yield AgentEvent("failed", {"error": _last_error([Msg("tool", result.text)])})


def _last_error(msgs: list[Msg]) -> str | None:
    for m in reversed(msgs):
        if m.role == "tool" and m.content:
            try:
                data: Any = json.loads(m.content)
            except json.JSONDecodeError:
                return m.content
            return data.get("error") if isinstance(data, dict) else None
    return None
