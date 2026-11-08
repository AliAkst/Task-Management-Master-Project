"""
Sistem mesaji. Kisa tutulur (local modelin baglami kucuk): kisilik + kurallar +
"simdi"nin ozeti. Ayrintilar ihtiyac halinde araclarla cekilir.
Faz 5: user_facts (seni tanimasi) + hedefler buraya eklenecek.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.tools.read_tools import ToolBox
from app.tools.task_api import TaskApiClient, TaskApiError

PERSONA = """Sen kullanıcının kişisel yaşam ve görev planlama asistanısın. Adın "Asistan".
Kurallar:
- Türkçe, samimi ve kısa konuş. Gereksiz uzatma; madde işaretlerini sade kullan.
- Kullanıcının verisi hakkında bir şey söylemeden önce araçlarla kontrol et; asla uydurma.
- Kart id'si bilmiyorsan search_cards ile bul.
- Plan önerirken kullanıcının tahmin sapmasını (get_stats_summary → estimate_ratio),
  verimli saatlerini ve ertelediği işleri dikkate al; gerçekçi ol, günü doldurma.
- Kart/etkinlik oluşturabilir, güncelleyebilir, bölebilir, bağlayabilir ve gün planına
  madde ekleyebilirsin. Kullanıcı istemeden büyük değişiklik yapma; emin değilsen sor.
- Yazma aracının sonucu "pending_approval" ise işlem YAPILMADI: kullanıcı sohbetteki
  kartla onaylayacak. "Ekledim/yaptım" deme; "önerdim, onaylarsan eklenecek" de.
  Sonuç "done" ise işlem yapıldı. Sonuç "rejected" ise kullanıcı reddetti; nedenine saygı göster.
- Tarih-saatleri ISO 8601 ve kullanıcının saat dilimi ofsetiyle yaz (örn. +03:00).
  "Yarın" gibi göreli ifadeleri aşağıdaki "Şu an" bilgisine göre hesapla.
- Tarihleri kullanıcının saat dilimine göre düşün."""

WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


async def _safe(api: TaskApiClient, path: str) -> Any:
    try:
        return await api.get(path)
    except TaskApiError:
        return None


async def build_system_prompt(
    api: TaskApiClient,
    toolbox: ToolBox,
    user: dict[str, Any],
    tz: ZoneInfo,
    model_label: str,
    is_local: bool,
) -> str:
    now = datetime.now(tz)
    lines = [
        PERSONA,
        "",
        f"Şu an: {now:%Y-%m-%d} {WEEKDAYS[now.weekday()]}, saat {now:%H:%M} ({tz.key}).",
    ]
    if user.get("full_name"):
        lines.append(f"Kullanıcının adı: {user['full_name']}.")

    boards = await toolbox.list_boards()
    if boards:
        lines.append(
            "Board'lar (hayat alanları): "
            + ", ".join(f"{b['name']} (id {b['id']})" for b in boards)
            + "."
        )

    active = await _safe(api, "/sessions/active")
    s = (active or {}).get("session")
    if s and not toolbox.privacy.card_hidden(s.get("card_id")):
        started = datetime.fromisoformat(s["started_at"]).astimezone(tz)
        mins = int((now - started).total_seconds() // 60)
        lines.append(
            f'Kronometre çalışıyor: "{s.get("card_title") or "serbest çalışma"}" '
            f"({mins} dk, {started:%H:%M}'den beri)."
        )

    plan = await _safe(api, f"/day-plans/{now.date().isoformat()}")
    if plan:
        if not plan["exists"]:
            lines.append("Bugün için henüz plan yapılmamış.")
        else:
            items = toolbox.privacy.filter(plan["items"])
            done = sum(1 for i in items if i["outcome"] == "done")
            state = "değerlendirildi" if plan["status"] == "reviewed" else "planlandı"
            lines.append(f"Bugünün planı {state}: {len(items)} madde, {done} yapıldı.")

    if not is_local:
        lines.append(
            "Not: Bulut modelisin; kullanıcının 'sadece local' işaretli board'larının "
            "verisi sana gösterilmiyor."
        )
    lines.append(f"(Model: {model_label})")
    return "\n".join(lines)
