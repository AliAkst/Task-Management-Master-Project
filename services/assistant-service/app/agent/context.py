"""
Sistem mesaji. Kisa tutulur (local modelin baglami kucuk): kisilik + kurallar +
"simdi"nin ozeti. Ayrintilar ihtiyac halinde araclarla cekilir.
Faz 5: user_facts (seni tanimasi) + hedefler buraya eklenecek.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.db.models import UserFactEntity
from app.tools.memory_tools import CATEGORIES
from app.tools.read_tools import ToolBox
from app.tools.task_api import TaskApiClient, TaskApiError

PERSONA = """Sen kullanıcının kişisel yaşam ve görev planlama asistanısın. Adın "Asistan".
Kurallar:
- Türkçe, samimi ve kısa konuş. Gereksiz uzatma; madde işaretlerini sade kullan.
- Kullanıcının verisi hakkında bir şey söylemeden önce araçlarla kontrol et; asla uydurma.
- Var olan bir kartla iş: takvime koy/planla → schedule_card; gününü/tarihini değiştir, ertele, öne çek → reschedule_card; başka board'a ya da listeye al → move_card; diğer alanlar → update_card. Bu araçlara kartın başlığını yazman yeterli, id bulmana gerek yok; "bu kart" deniyorsa card="bu kart" ver.
- create_card yalnız kullanıcı YENİ bir iş söylediğinde. Araç "zaten var" derse var olan kartla devam et.
- Araç "birden çok kart eşleşti" derse adayları kullanıcıya sor.
- Plan önerirken kullanıcının tahmin sapmasını (get_stats_summary → estimate_ratio),
  verimli saatlerini ve ertelediği işleri dikkate al; gerçekçi ol, günü doldurma.
- Kart/etkinlik oluşturabilir, güncelleyebilir, bölebilir, bağlayabilir ve gün planına
  madde ekleyebilirsin. Kullanıcı istemeden büyük değişiklik yapma; emin değilsen sor.
- Yazma aracının sonucu "pending_approval" ise işlem YAPILMADI: kullanıcı sohbetteki
  kartla onaylayacak. "Ekledim/yaptım" deme; "önerdim, onaylarsan eklenecek" de.
  Sonuç "done" ise işlem yapıldı. Sonuç "rejected" ise kullanıcı reddetti; nedenine saygı göster.
- Kullanıcı bir günü saat saat planlamanı isterse (iş, yol, spor, ayak işleri...) schedule_day aracını TEK çağrıyla kullan: blokları sırayla ver, kullanıcının saat verdiğine start, süre verdiğine minutes yaz; saat/süre söylenmeyen maddeyi saatsiz bırak (gün planına yine girer); saat hesaplamayı araca bırak. Yol/iş/yemek card=false, yapılacak işler card=true (aynı adlı açık kart varsa araç onu kullanır). Önce metinle plan yazıp onay isteme: araç zaten kullanıcıya onay kartı olarak gider; planı doğrudan araçla öner.
- Kart silme isteğinde delete_cards (titles / board / all), bir günün planını iptal etme isteğinde cancel_day kullan; silinecekleri araç bulur ve onaya sunar. "Yetkim yok" deme.
- Checklist ya da etiket değişikliği için önce get_card ile id'leri al; maddeyi metinle değil item_id ile işaretle. Kartın checklist'ine madde eklemek için add_checklist_items, etiket için set_card_labels kullan.
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
    facts: list[UserFactEntity] | None = None,
    focus: str | None = None,
) -> str:
    now = datetime.now(tz)
    lines = [
        PERSONA,
        "",
        f"Şu an: {now:%Y-%m-%d} {WEEKDAYS[now.weekday()]}, saat {now:%H:%M} ({tz.key}).",
    ]
    if user.get("full_name"):
        lines.append(f"Kullanıcının adı: {user['full_name']}.")

    if focus:
        lines.append(focus)

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

    lines += _memory_lines(facts or [])
    goals = await _safe_goals(toolbox)
    if goals:
        lines.append("")
        lines.append(
            "Kullanıcının aktif hedefleri (planlarken bunlara hizmet eden işleri öne çıkar):"
        )
        lines += [
            f"- [hedef {g['id']}] {g['title']}"
            + (f" (hedef tarih {g['target_date']})" if g.get("target_date") else "")
            + (f" — neden: {g['why']}" if g.get("why") else "")
            for g in goals
        ]

    if not is_local:
        lines.append(
            "Not: Bulut modelisin; kullanıcının 'sadece local' işaretli board'larının "
            "verisi sana gösterilmiyor."
        )
    lines.append(f"(Model: {model_label})")
    return "\n".join(lines)


async def focus_line(
    api: TaskApiClient,
    toolbox: ToolBox,
    board_id: int | None,
    card_id: int | None,
) -> str | None:
    """"Bu kart / bu board" baglami. Kullanicinin kendi JWT'siyle okunur (sahiplik);
    bulut modelde gizli (local_only) board/kart icin hicbir sey eklenmez."""
    privacy = toolbox.privacy
    card = None
    if card_id is not None and not privacy.card_hidden(card_id):
        card = await _safe(api, f"/cards/{card_id}")
        if card and privacy.board_hidden(card.get("board_id")):
            card = None
    bid = card["board_id"] if card else board_id
    board = None
    if bid is not None and not privacy.board_hidden(bid):
        detail = await _safe(api, f"/boards/{bid}")
        board = detail["board"]["name"] if detail else None
    if card and board:
        toolbox.writer.focus_card_id = card["id"]  # "bu kart" -> resolve_card
        return (
            f"Kullanıcı şu an «{board}» board'unda, #{card['id']} «{card['title']}» "
            "kartını açık tutuyor; 'bu kart' dediğinde bunu kastediyor."
        )
    if board:
        return (
            f"Kullanıcı şu an «{board}» board'unda (id {bid}); "
            "'bu board' dediğinde bunu kastediyor."
        )
    return None


MIN_FACTS_FOR_ACQUAINTED = 3


def _memory_lines(facts: list[UserFactEntity]) -> list[str]:
    """Bilinenler + bilinmeyen kategoriler (dogal sorular icin) + tanisma talimati."""
    lines: list[str] = [""]
    if facts:
        lines.append(
            "Kullanıcı hakkında bildiklerin (güncellemek/silmek için id'yi kullan):"
        )
        lines += [f"- [{f.id}, {f.category}] {f.content}" for f in facts]
    known = {f.category for f in facts}
    missing = [CATEGORIES[c] for c in CATEGORIES if c not in known and c != "other"]
    if len(facts) < MIN_FACTS_FOR_ACQUAINTED:
        lines.append(
            "Kullanıcıyı henüz yeterince tanımıyorsun. Uygun bir anda kısa bir tanışma yap: "
            "her seferinde TEK soru sor (hayat alanları, hedefleri, günlük rutini, çalışma "
            "saatleri, enerjisinin yüksek olduğu zamanlar)."
        )
    elif missing:
        lines.append(
            "Henüz bilmediğin konular: " + ", ".join(missing) + ". Sohbet doğal olarak "
            "elverdiğinde (sorguya çekmeden) bunları öğren."
        )
    lines.append(
        "Kullanıcının kendisi hakkında söylediği kalıcı bilgiler, cevabından sonra ayrıca "
        "hafızaya kaydedilmek üzere önerilir. Bu yüzden 'not aldım/kaydettim' DEME; "
        "sohbete doğal biçimde devam et. Kullanıcı açıkça bir bilgiyi silmeni ya da "
        "düzeltmeni isterse forget_fact / remember_fact(fact_id) kullan."
    )
    return lines


async def _safe_goals(toolbox: ToolBox) -> list[dict[str, Any]]:
    try:
        goals = await toolbox.api.get("/goals", status="active")
    except TaskApiError:
        return []
    return [g for g in goals if not toolbox.privacy.board_hidden(g.get("board_id"))]
