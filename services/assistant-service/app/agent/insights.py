"""
Haftalik analiz (Faz 6b): kullanicinin kaliplarini gozlem olarak onerir.

Kod, son 4 haftanin istatistiginden olculebilir SINYALLER cikarir (hangi gun
planlar daha az bitiyor, surekli ertelenen kartlar, haftalik hedefin gerisinde
kalan board'lar, tahmin sapmasi, verimli saatler, enerji etkisi). Model sadece
bunlari dogal bir cumleye cevirir ve haftayi kisaca ozetler; boylece kalip
uyduramaz ve her gozlemin arkasinda veri (evidence) durur.

Gozlemler ai_insights'a "new" olarak yazilir. Kullanici onaylarsa kalici
bilgiye (user_facts) donusur; reddedilen ayni gozlem 4 hafta onerilmez.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.day_review import estimate_factor
from app.db.models import AiInsightEntity
from app.llm.types import LLMProvider, Msg
from app.tools.privacy import PrivacyFilter
from app.tools.task_api import TaskApiClient, TaskApiError

WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
WINDOW_DAYS = 28
REPEAT_AFTER = timedelta(days=28)  # reddedilen/bekleyen gozlem bu sure tekrarlanmaz
MAX_INSIGHTS = 4


@dataclass
class Signal:
    key: str
    category: str
    text: str  # modelin yazamadigi durumda kullanilan hazir cumle
    evidence: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0  # sira: once en belirgin


def _pct(x: float) -> int:
    return round(x * 100)


def _rate(d: dict[str, Any]) -> float | None:
    planned = d.get("planned") or 0
    if planned <= 0:
        return None
    return min(1.0, ((d.get("done") or 0) + 0.5 * (d.get("partial") or 0)) / planned)


# ---------------- sinyaller (saf fonksiyonlar) ----------------
def weekday_signal(days: list[dict[str, Any]]) -> Signal | None:
    scored = [
        (date.fromisoformat(str(d["date"])).weekday(), r)
        for d in days
        if d.get("reviewed") and (r := _rate(d)) is not None
    ]
    if len(scored) < 5:
        return None
    overall = sum(r for _, r in scored) / len(scored)
    by_day: dict[int, list[float]] = {}
    for wd, r in scored:
        by_day.setdefault(wd, []).append(r)
    worst = min(
        ((wd, sum(rs) / len(rs), len(rs)) for wd, rs in by_day.items() if len(rs) >= 2),
        key=lambda x: x[1],
        default=None,
    )
    if worst is None or worst[1] > overall - 0.25:
        return None
    wd, rate, n = worst
    return Signal(
        f"weekday_low:{wd}",
        "routine",
        f"{WEEKDAYS[wd]} günleri planladıklarının %{_pct(rate)}'ini bitirebiliyorsun; "
        f"genel ortalaman %{_pct(overall)}.",
        {
            "weekday": WEEKDAYS[wd],
            "rate": round(rate, 2),
            "overall": round(overall, 2),
            "days": n,
        },
        weight=overall - rate,
    )


def energy_signal(days: list[dict[str, Any]]) -> Signal | None:
    low = [
        r for d in days if (d.get("energy") or 3) <= 2 and (r := _rate(d)) is not None
    ]
    high = [
        r for d in days if (d.get("energy") or 0) >= 4 and (r := _rate(d)) is not None
    ]
    if len(low) < 2 or len(high) < 2:
        return None
    lo, hi = sum(low) / len(low), sum(high) / len(high)
    if hi - lo < 0.3:
        return None
    return Signal(
        "energy_effect",
        "routine",
        f"Enerjinin düşük olduğu günlerde planının %{_pct(lo)}'ini, yüksek olduğu "
        f"günlerde %{_pct(hi)}'ini bitiriyorsun.",
        {
            "low_rate": round(lo, 2),
            "high_rate": round(hi, 2),
            "low_days": len(low),
            "high_days": len(high),
        },
        weight=hi - lo,
    )


def postponed_signals(items: list[dict[str, Any]]) -> list[Signal]:
    return [
        Signal(
            f"postponed:{p['card_id']}",
            "work",
            f"'{p['title']}' son 4 haftada {p['count']} kez ertelendi.",
            {"card_id": p["card_id"], "title": p["title"], "count": p["count"]},
            weight=0.1 * p["count"],
        )
        for p in items
        if (p.get("count") or 0) >= 3
    ][:2]


def budget_signals(
    boards: list[dict[str, Any]], privacy: PrivacyFilter
) -> list[Signal]:
    out = []
    for b in boards:
        budget, tracked = b.get("budget_min"), b.get("tracked_min") or 0
        if (
            not budget
            or b.get("board_id") is None
            or privacy.board_hidden(b["board_id"])
        ):
            continue
        share = tracked / budget
        if share >= 0.6:
            continue
        out.append(
            Signal(
                f"budget_low:{b['board_id']}",
                "routine",
                f"Bu hafta {b['name']} için ayırmak istediğin sürenin "
                f"%{_pct(share)}'ine ulaştın ({tracked} / {budget} dk).",
                {"board": b["name"], "tracked_min": tracked, "budget_min": budget},
                weight=1 - share,
            )
        )
    return out


def estimate_signal(summary: dict[str, Any]) -> Signal | None:
    f = estimate_factor(summary)
    if f is None or 0.8 < f < 1.25:
        return None
    longer = f >= 1.25
    pct = _pct(f - 1) if longer else _pct(1 - f)
    return Signal(
        "estimate",
        "work",
        f"İşlerin genelde tahmin ettiğinden %{pct} "
        f"{'uzun' if longer else 'kısa'} sürüyor.",
        {"median_ratio": f, "samples": summary["estimate_accuracy"].get("sample_size")},
        weight=abs(f - 1),
    )


def peak_hours_signal(hours: list[int]) -> Signal | None:
    total = sum(hours)
    if total < 300 or len(hours) != 24:
        return None
    best = max(range(23), key=lambda h: hours[h] + hours[h + 1])
    share = (hours[best] + hours[best + 1]) / total
    if share < 0.25:
        return None
    return Signal(
        f"peak_hours:{best}",
        "routine",
        f"En çok {best:02d}:00–{best + 2:02d}:00 arasında çalışıyorsun "
        f"(toplam sürenin %{_pct(share)}'i).",
        {"start_hour": best, "share": round(share, 2), "total_min": total},
        weight=share,
    )


def compute_signals(
    month: dict[str, Any], week: dict[str, Any] | None, privacy: PrivacyFilter
) -> list[Signal]:
    days = month.get("days") or []
    found: list[Signal | None] = [
        weekday_signal(days),
        energy_signal(days),
        estimate_signal(month),
        peak_hours_signal(month.get("productive_hours") or []),
    ]
    signals = [s for s in found if s is not None]
    signals += budget_signals((week or {}).get("boards") or [], privacy)
    # Ertelenen kartin board'u ozette yok: bulut modelde guvenli tarafta kal
    if not privacy.active:
        signals += postponed_signals(month.get("most_postponed") or [])
    return sorted(signals, key=lambda s: s.weight, reverse=True)


async def fresh_signals(
    session: AsyncSession, user_id: int, signals: list[Signal], now: datetime
) -> list[Signal]:
    """Onaylanmis (zaten bilgi) ya da son 4 haftada onerilmis gozlemleri ele."""
    rows = await session.scalars(
        select(AiInsightEntity).where(
            AiInsightEntity.user_id == user_id,
            AiInsightEntity.key.in_([s.key for s in signals]),
        )
    )
    blocked = {
        r.key
        for r in rows
        if r.status == "confirmed" or r.created_at >= now - REPEAT_AFTER
    }
    return [s for s in signals if s.key not in blocked][:MAX_INSIGHTS]


# ---------------- model ----------------
SYSTEM = """Sen kullanıcının kişisel planlama asistanısın. Son haftalarının verisinden
çıkarılmış gözlemler aşağıda. Görevin:
1) Her gözlemi kullanıcıya hitap eden, tek cümlelik, sade ve yargılamayan bir Türkçe
   cümleye çevir. Sayıları DEĞİŞTİRME, yeni bilgi ekleme.
2) Haftayı 1-2 cümleyle özetle.
Yalnızca şu biçimde JSON döndür:
{"week_summary": "...", "insights": [{"id": "s1", "text": "..."}]}"""


def build_messages(signals: list[Signal], week: dict[str, Any] | None) -> list[Msg]:
    totals = (week or {}).get("totals") or {}
    lines = [
        f"Bu hafta: {totals.get('tracked_min', 0)} dk çalışma, "
        f"{totals.get('done_items', 0)}/{totals.get('planned_items', 0)} "
        "plan maddesi bitti, "
        f"{totals.get('reviewed_days', 0)} gün değerlendirildi.",
        "",
        "Gözlemler:",
        *(f"[s{i}] {s.text}" for i, s in enumerate(signals, 1)),
    ]
    return [Msg("system", SYSTEM), Msg("user", "\n".join(lines))]


def parse_reply(text: str, n: int) -> tuple[str | None, dict[int, str]]:
    cleaned = re.sub(r"```(?:json)?", "", text or "")
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None, {}
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None, {}
    if not isinstance(data, dict):
        return None, {}
    texts: dict[int, str] = {}
    for item in data.get("insights") or []:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        m = re.fullmatch(r"s?(\d+)", str(item.get("id", "")).strip())
        if m and 1 <= int(m.group(1)) <= n and item["text"].strip():
            texts[int(m.group(1))] = item["text"].strip()[:400]
    summary = data.get("week_summary")
    return (
        summary.strip()[:800] if isinstance(summary, str) and summary.strip() else None
    ), texts


async def _safe(api: TaskApiClient, path: str, **params: Any) -> Any:
    try:
        return await api.get(path, **params)
    except TaskApiError:
        return None


async def run_weekly_insights(
    api: TaskApiClient,
    provider: LLMProvider,
    session_maker: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    end: date,
    job_id: int | None = None,
) -> dict[str, Any]:
    cloud = not provider.info.is_local
    boards = await api.get("/boards")
    privacy = PrivacyFilter(
        active=cloud,
        hidden_boards={b["id"] for b in boards if b.get("privacy") == "local_only"},
    )
    month = await api.get(
        "/analytics/summary",
        start=(end - timedelta(days=WINDOW_DAYS - 1)).isoformat(),
        end=end.isoformat(),
    )
    week = await _safe(
        api,
        "/analytics/summary",
        start=(end - timedelta(days=6)).isoformat(),
        end=end.isoformat(),
    )
    now = datetime.now(UTC)
    async with session_maker() as session:
        signals = await fresh_signals(
            session, user_id, compute_signals(month, week, privacy), now
        )

    week_summary: str | None = None
    texts: dict[int, str] = {}
    notes: list[str] = []
    if signals:
        out: list[str] = []
        async for chunk in provider.stream(
            build_messages(signals, week), None, temperature=0.3, max_tokens=1200
        ):
            if chunk.type == "text":
                out.append(chunk.text)
        week_summary, texts = parse_reply("".join(out), len(signals))
        if not texts:
            notes.append(
                "Model cümleleri yazamadı; gözlemler verideki haliyle kaydedildi."
            )
    else:
        notes.append("Yeni bir kalıp bulunamadı ya da henüz yeterli veri yok.")

    created: list[int] = []
    async with session_maker() as session:
        for i, s in enumerate(signals, 1):
            row = AiInsightEntity(
                user_id=user_id,
                key=s.key,
                category=s.category,
                observation=texts.get(i, s.text),
                evidence={**s.evidence, "data_text": s.text},
                status="new",
                job_id=job_id,
            )
            session.add(row)
            await session.flush()
            created.append(row.id)
        await session.commit()
    return {
        "week_summary": week_summary,
        "insight_ids": created,
        "period_start": (end - timedelta(days=WINDOW_DAYS - 1)).isoformat(),
        "period_end": end.isoformat(),
        "notes": notes,
    }
