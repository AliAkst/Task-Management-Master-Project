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
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from app.agent.loop import AgentEvent
from app.llm.types import LLMError, LLMProvider, Msg
from app.tools.read_tools import ToolBox
from app.tools.schedule_day import SCHEDULE_SPEC

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
Bugün: {today}. Board'lar: {boards}.

Nasıl:
1. Günün olaylarını GERÇEKLEŞME SIRASIYLA yaz (sabahtan geceye).
2. Kullanıcının saat verdiği maddeye start yaz; bitişini ya da süresini söylediyse end ya da minutes ekle.
3. Süresi söylenen ama saati söylenmeyen maddelere SADECE minutes yaz; araç onları bir öncekinin bitişine ekler. Saati belli maddeden önceki maddeler (örn. işe yol) araç tarafından ona göre yerleştirilir.
4. Kullanıcı saat de süre de söylemediyse start, minutes, end YAZMA (saat uydurma); madde saatsiz olarak gün planına girer.
5. Yol, iş, yemek: card=false. Yapılacak işler (spor, alışveriş, oyun, temizlik):
   card=true ve uygun board. Kartlı ya da kartsız, her madde gün planına eklenir.
6. Kullanıcının verdiği süreleri aynen kullan; birlikte söylediği şeyleri tek blok yap.
7. Boş kalan zamana kullanıcının söylemediği iş ekleme.
8. Kullanıcı var olan bir kartı adıyla anıyorsa ("eğitim board'ındaki P2 kartı") title'a SADECE kartın adını yaz ("P2"), board'a board adını ver; araç var olan açık kartı bulup kullanır, yeni kart açmaz.

Örnek: "Yarın 10-17 dersteyim, okula yol 1 saat. Dersten sonra market 20 dk, eve 1 saat,
sonra 45 dk koşu."
schedule_day({{"day": "yarın", "blocks": [
 {{"title": "Okula yol", "minutes": 60, "card": false}},
 {{"title": "Ders", "start": "10:00", "end": "17:00", "card": false}},
 {{"title": "Market", "minutes": 20, "card": true, "board": "Günlük işler"}},
 {{"title": "Eve yol", "minutes": 60, "card": false}},
 {{"title": "Koşu", "minutes": 45, "card": true, "board": "Spor"}}]}})

Örnek: "Yarın market, kuru temizleme ve kitap iade, planla."
schedule_day({{"day": "yarın", "blocks": [
 {{"title": "Market", "card": true, "board": "Günlük işler"}},
 {{"title": "Kuru temizleme", "card": false}},
 {{"title": "Kitap iade", "card": false}}]}})

Metin yazma; sadece aracı çağır."""


async def plan_day(
    provider: LLMProvider, toolbox: ToolBox, user_text: str
) -> AsyncIterator[AgentEvent]:
    """
    Olaylar: tool_start / tool_end / action ve sonunda "planned" (data: ozet) ya
    da "failed" (normal sohbete devam edilir).
    """
    now = datetime.now(toolbox.tz)
    boards = ", ".join(b["name"] for b in await toolbox.boards()) or "(yok)"
    today = f"{now:%Y-%m-%d} {WEEKDAYS[now.weekday()]}"
    msgs = [
        Msg("system", PROMPT.format(today=today, boards=boards)),
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
        result = await toolbox.execute(call)
        if result.ok and result.action is not None:
            yield AgentEvent("tool_end", {"name": "schedule_day", "ok": True})
            yield AgentEvent("action", result.action)
            yield AgentEvent("planned", {"summary": result.action["summary"]})
            return
        # Hata: modele aynen geri ver, duzeltsin
        msgs += [
            Msg("assistant", None, tool_calls=[call]),
            Msg("tool", result.text, tool_call_id=call.id, name=call.name),
        ]
    yield AgentEvent("tool_end", {"name": "schedule_day", "ok": False})
    yield AgentEvent("failed", {"error": _last_error(msgs)})


def _last_error(msgs: list[Msg]) -> str | None:
    for m in reversed(msgs):
        if m.role == "tool" and m.content:
            try:
                data: Any = json.loads(m.content)
            except json.JSONDecodeError:
                return m.content
            return data.get("error") if isinstance(data, dict) else None
    return None
