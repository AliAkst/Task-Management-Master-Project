"""
Hafiza cikarimi: sohbet cevabindan SONRA, son kullanici mesaji uzerinden ayri ve
odakli bir model cagrisi.

Neden ayri? Gercek testte hem qwen3.5:4b hem gemma4:26b, sohbet ederken
remember_fact'i cagirmayip "not aldim" dedi (arac cagrilmadi). Ayni modeller tek
arac + tek gorevli odakli istemlerde ise kusursuz (benchmark: 4/4). Bu yuzden
"kullanici hakkinda kalici bilgi var mi?" isi sohbetten ayrildi.

Cikan oneriler normal izin kapisindan gecer (varsayilan: onay karti).
"""

from collections.abc import AsyncIterator

from app.agent.loop import AgentEvent
from app.db.models import UserFactEntity
from app.llm.types import LLMError, LLMProvider, Msg
from app.tools.read_tools import ToolBox

MEMORY_TOOLS = ("remember_fact", "save_goal")
# Sohbet modelinden gizlenen hafiza araclari: kucuk model planlama isteklerinde
# bile surekli "bilgi kaydet" cagiriyordu (gercek testte ~20 yanlis/tekrar bilgi)
CHAT_HIDDEN_TOOLS = {"remember_fact", "forget_fact"}
MIN_MESSAGE_CHARS = 12

PROMPT = """Görevin SADECE şu: kullanıcının son mesajında, kullanıcının KENDİSİ hakkında
kalıcı ve ileride işe yarayacak bilgi var mı? (rutinler, çalışma saatleri, işi,
tercihleri, sağlığı, ilişkileri, hayat alanları, hedefleri)

- Her ayrı bilgi için remember_fact çağır (tek kısa cümle, üçüncü tekil şahıs:
  "Akşam 20-22 arası en verimli saatleri").
- Kullanıcı bir hedeften bahsediyorsa save_goal çağır.
- Aşağıdaki bilinen bilgileri TEKRAR kaydetme; değiştiyse fact_id ile güncelle.
- Soru, istek, selamlaşma ya da geçici durum ("bugün yorgunum") kalıcı bilgi değildir:
  hiçbir araç çağırma.
- Plan/görev isteğindeki tek bir güne ait ayrıntılar ("salı kuyumcuya uğrayacağım",
  "çarşamba ofisteyim") kalıcı bilgi DEĞİLDİR.
- Kullanıcı hakkında olmayan şeyleri ("kullanıcı eklememiş") asla kaydetme.
- Metin yazma; sadece araç çağır ya da hiçbir şey yapma."""


async def extract_memory(
    provider: LLMProvider,
    toolbox: ToolBox,
    user_text: str,
    facts: list[UserFactEntity],
) -> AsyncIterator[AgentEvent]:
    if len(user_text.strip()) < MIN_MESSAGE_CHARS:
        return
    specs = [s for s in toolbox.write_specs() if s.name in MEMORY_TOOLS]
    if not specs:  # kullanici hafiza islemlerini "asla" yapmis
        return
    known = (
        "\n".join(f"- [{f.id}, {f.category}] {f.content}" for f in facts) or "- (yok)"
    )
    messages = [
        Msg("system", f"{PROMPT}\n\nBilinen bilgiler:\n{known}"),
        Msg("user", user_text),
    ]
    calls = []
    try:
        async for chunk in provider.stream(messages, specs, temperature=0.1):
            if chunk.type == "tool_call" and chunk.tool_call:
                calls.append(chunk.tool_call)
    except LLMError:
        return  # hafiza cikarimi yan islem: hata sohbeti bozmasin
    for call in calls[:5]:
        if call.name not in MEMORY_TOOLS:
            continue
        result = await toolbox.execute(call)
        if result.action is not None:
            yield AgentEvent("action", result.action)
