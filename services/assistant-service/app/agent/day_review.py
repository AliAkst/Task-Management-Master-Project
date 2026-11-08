"""
Gun sonu dongusu (Faz 6a). Kullanici gunu degerlendirince arka planda:
1. gunun kisa ozeti yazilir (task-api day_plans.ai_summary),
2. ertesi gun icin plan taslagi onerilir (plan_day islemi; izin moduna uyar:
   ask -> onay bekler, auto -> hemen eklenir, never -> onerilmez).

Model sadece SECER ve GEREKCE yazar. Adaylar task-api'nin ertesi gun
onerilerinden gelir; sureleri kisisel tahmin katsayisiyla kod duzeltir; bloke
kartlar, zaten planli olanlar ve (bulut modelde) gizli board'lar elenir.
Boylece kucuk/yavas modelin uydurma is eklemesi ya da gunu sisirmesi engellenir.
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.actions import load_modes
from app.db.models import AiActionEntity
from app.llm.types import LLMProvider, Msg
from app.tools.memory_tools import load_facts
from app.tools.privacy import PrivacyFilter
from app.tools.task_api import TaskApiClient, TaskApiError
from app.tools.write_tools import WriteTools

FACTOR_MIN_SAMPLES = 3  # bundan az olcum varsa katsayi uygulanmaz
FACTOR_BOUNDS = (0.5, 3.0)
MAX_ITEMS = 8
DEFAULT_CAP_MIN = 360  # gecmis veri yoksa yarin icin en fazla ~6 saat
CAP_BOUNDS = (120, 480)

KIND_LABEL = {
    "event": "takvimde, saati sabit",
    "carry_over": "bugünden ertelendi",
    "due": "son günü yarın",
    "overdue": "son günü geçti",
    "in_progress": "devam ediyor",
    "worked": "bugün üzerinde çalışıldı",
}
OUTCOME_LABEL = {
    "done": "yapıldı",
    "partial": "kısmen",
    "not_done": "yapılmadı",
    "postponed": "ertelendi",
    None: "değerlendirilmedi",
}

SYSTEM = """Sen kullanıcının kişisel planlama asistanısın.
Kullanıcı bugünü değerlendirdi.
Görevin:
1) Bugünün kısa özeti: 2-4 cümle, Türkçe. Ne yapıldı, ne kaldı, fark ettiğin bir kalıp
   varsa onu söyle. Dürüst ve destekleyici ol; abartılı övgü ya da suçlama yok.
2) Yarın için gerçekçi bir plan: SADECE aşağıdaki aday listesinden numara seç; listede
   olmayan iş uydurma. Takvimdeki etkinlikleri seç. Son günü gelen/geçen ve ertelenmiş
   işlere öncelik ver. Toplam süre yaklaşık {cap} dakikayı geçmesin; günü doldurma.
   Her seçim için tek cümlelik gerekçe yaz.
Yalnızca şu biçimde JSON döndür, başka hiçbir şey yazma:
{{"summary": "...", "plan": [{{"n": 1, "reason": "..."}}],
 "tip": "yarın için tek cümlelik öneri ya da null"}}"""


@dataclass
class Candidate:
    n: int
    kind: str
    title: str
    card_id: int | None
    event_id: int | None
    board: str | None
    minutes: int | None  # kullanicinin tahmini (ya da planladigi)
    adjusted: int | None  # tahmin katsayisiyla duzeltilmis
    planned_start: str | None
    due_date: str | None

    def line(self) -> str:
        parts = [KIND_LABEL.get(self.kind, self.kind)]
        if self.board:
            parts.append(f"board: {self.board}")
        if self.planned_start:
            parts.append(f"saat {self.planned_start[11:16]}")
        if self.minutes:
            if self.adjusted and self.adjusted != self.minutes:
                parts.append(f"tahmin {self.minutes} dk, gerçekçi {self.adjusted} dk")
            else:
                parts.append(f"{self.minutes} dk")
        if self.due_date:
            parts.append(f"son gün {self.due_date[:10]}")
        return f"[{self.n}] {self.title} ({', '.join(parts)})"


# ---------------- tahmin katsayisi ----------------
def estimate_factor(summary: dict[str, Any] | None) -> float | None:
    """Gercek / tahmin oraninin medyani (yeterli olcum yoksa None)."""
    acc = (summary or {}).get("estimate_accuracy") or {}
    ratio = acc.get("median_ratio")
    if ratio is None or (acc.get("sample_size") or 0) < FACTOR_MIN_SAMPLES:
        return None
    lo, hi = FACTOR_BOUNDS
    return round(min(hi, max(lo, float(ratio))), 2)


def adjust_minutes(minutes: int | None, factor: float | None) -> int | None:
    if minutes is None or not factor:
        return minutes
    return max(5, round(minutes * factor / 5) * 5)


def factor_text(factor: float | None) -> str | None:
    if factor is None:
        return None
    if factor >= 1.05:
        return f"İşlerin genelde tahmininden %{round((factor - 1) * 100)} uzun sürüyor"
    if factor <= 0.95:
        return f"İşlerin genelde tahmininden %{round((1 - factor) * 100)} kısa sürüyor"
    return "Süre tahminlerin genelde isabetli"


def daily_cap(summary: dict[str, Any] | None) -> int:
    """Son haftalarda degerlendirilen gunlerde ortalama calisilan surenin biraz ustu."""
    totals = (summary or {}).get("totals") or {}
    days = totals.get("reviewed_days") or 0
    tracked = totals.get("tracked_min") or 0
    if days < 3 or tracked <= 0:
        return DEFAULT_CAP_MIN
    lo, hi = CAP_BOUNDS
    return int(min(hi, max(lo, round(tracked / days * 1.25 / 30) * 30)))


# ---------------- adaylar ----------------
def build_candidates(
    suggestions: Iterable[dict[str, Any]],
    boards: dict[int, str],
    privacy: PrivacyFilter,
    factor: float | None,
) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[tuple[str, int]] = set()
    for s in suggestions:
        if s.get("blocked") or s.get("already_planned") or not privacy.keep(s):
            continue
        key = (
            ("card", s["card_id"])
            if s.get("card_id")
            else ("event", s["event_id"])
            if s.get("event_id")
            else None
        )
        if key is None or key in seen:
            continue
        seen.add(key)
        minutes = s.get("planned_minutes")
        is_event = s.get("kind") == "event"
        out.append(
            Candidate(
                n=len(out) + 1,
                kind=s.get("kind", ""),
                title=s["title"],
                card_id=s.get("card_id"),
                event_id=s.get("event_id") if not s.get("card_id") else None,
                board=boards.get(s.get("board_id")),  # type: ignore[arg-type]
                minutes=minutes,
                adjusted=minutes if is_event else adjust_minutes(minutes, factor),
                planned_start=s.get("planned_start"),
                due_date=s.get("due_date"),
            )
        )
    return out


def parse_output(text: str) -> dict[str, Any] | None:
    """Modelin JSON cevabi (kod blogu, onunde/arkasinda metin olsa da)."""
    cleaned = re.sub(r"```(?:json)?", "", text or "")
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    summary = data.get("summary")
    plan = data.get("plan")
    tip = data.get("tip")
    return {
        "summary": summary.strip() if isinstance(summary, str) else None,
        "plan": plan if isinstance(plan, list) else [],
        "tip": tip.strip() if isinstance(tip, str) and tip.strip() else None,
    }


def pick(
    candidates: list[Candidate], chosen: list[Any], cap: int
) -> list[tuple[Candidate, str | None]]:
    """Gecerli numaralar, tekrarsiz; etkinlikler her zaman, kartlar kapasiteye kadar."""
    by_n = {c.n: c for c in candidates}
    out: list[tuple[Candidate, str | None]] = []
    used: set[int] = set()
    total = 0
    for item in chosen:
        raw = item.get("n") if isinstance(item, dict) else item
        try:
            n = int(raw)
        except (TypeError, ValueError):
            continue
        c = by_n.get(n)
        if c is None or n in used:
            continue
        reason = item.get("reason") if isinstance(item, dict) else None
        cost = c.adjusted or 0
        if c.kind != "event" and out and total + cost > cap:
            continue
        used.add(n)
        total += cost if c.kind != "event" else 0
        out.append((c, str(reason).strip()[:300] if reason else None))
        if len(out) >= MAX_ITEMS:
            break
    return out


# ---------------- istem ----------------
def render_today(plan: dict[str, Any], privacy: PrivacyFilter, cloud: bool) -> str:
    lines = []
    for i in privacy.filter(plan.get("items") or []):
        tracked = round((i.get("tracked_sec") or 0) / 60)
        bits = [OUTCOME_LABEL.get(i.get("outcome"), "?")]
        if i.get("planned_minutes"):
            bits.append(f"planlanan {i['planned_minutes']} dk")
        if tracked:
            bits.append(f"harcanan {tracked} dk")
        if not i.get("was_planned"):
            bits.append("plan dışı")
        line = f"- {i['title']}: {', '.join(bits)}"
        if i.get("reason"):
            line += f" — neden: {i['reason']}"
        lines.append(line)
    out = ["Bugünün maddeleri:", *(lines or ["- (madde yok)"])]
    if plan.get("mood"):
        out.append(f"Ruh hâli: {plan['mood']}/5")
    if plan.get("energy"):
        out.append(f"Enerji: {plan['energy']}/5")
    # Serbest metin board'a bagli degil; bulut modele yine de gonderilmez
    if plan.get("reflection") and not cloud:
        out.append(f"Kullanıcının notu: {plan['reflection']}")
    return "\n".join(out)


def build_messages(
    *,
    day: date,
    plan: dict[str, Any],
    candidates: list[Candidate],
    cap: int,
    factor: float | None,
    privacy: PrivacyFilter,
    cloud: bool,
    facts: list[str],
    goals: list[str],
    rejected: list[str],
) -> list[Msg]:
    tomorrow = day + timedelta(days=1)
    parts = [
        f"Bugün: {day.isoformat()}. Yarın: {tomorrow.isoformat()}.",
        render_today(plan, privacy, cloud),
        "",
        "Yarın için adaylar:",
        *(c.line() for c in candidates),
    ]
    if not candidates:
        parts.append("(aday yok: plan boş kalabilir)")
    if factor_text(factor):
        parts.append(f"\nTahmin sapması: {factor_text(factor)}.")
    if goals:
        parts += ["\nAktif hedefler:", *(f"- {g}" for g in goals)]
    if facts:
        parts += ["\nKullanıcı hakkında bildiklerin:", *(f"- {f}" for f in facts)]
    if rejected:
        parts += [
            "\nKullanıcının daha önce reddettiği plan önerileri ve nedenleri:",
            *(f"- {r}" for r in rejected),
        ]
    return [
        Msg("system", SYSTEM.format(cap=cap)),
        Msg("user", "\n".join(parts)),
    ]


async def collect_text(provider: LLMProvider, messages: list[Msg]) -> str:
    out: list[str] = []
    async for chunk in provider.stream(
        messages, None, temperature=0.3, max_tokens=1500
    ):
        if chunk.type == "text":
            out.append(chunk.text)
    return "".join(out).strip()


async def _safe(api: TaskApiClient, path: str, **params: Any) -> Any:
    try:
        return await api.get(path, **params)
    except TaskApiError:
        return None


async def _rejected_feedback(session: AsyncSession, user_id: int) -> list[str]:
    rows = await session.scalars(
        select(AiActionEntity)
        .where(
            AiActionEntity.user_id == user_id,
            AiActionEntity.action_type == "plan_day",
            AiActionEntity.status == "rejected",
            AiActionEntity.user_feedback.is_not(None),
        )
        .order_by(AiActionEntity.id.desc())
        .limit(5)
    )
    return [f"{a.summary} → {a.user_feedback}" for a in rows]


# ---------------- ana is ----------------
async def run_day_review(
    api: TaskApiClient,
    provider: LLMProvider,
    session_maker: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    day: date,
    tz: ZoneInfo,
) -> tuple[dict[str, Any], int | None]:
    """Ozeti yazar, plani onerir. Doner: (sonuc, ai_action id'si)."""
    cloud = not provider.info.is_local
    tomorrow = day + timedelta(days=1)
    plan = await api.get(f"/day-plans/{day.isoformat()}")
    if plan.get("status") != "reviewed":
        raise ValueError("Bu gün henüz değerlendirilmedi")

    boards_list = await api.get("/boards")
    hidden = {b["id"] for b in boards_list if b.get("privacy") == "local_only"}
    privacy = PrivacyFilter(active=cloud, hidden_boards=hidden)
    boards = {
        b["id"]: b["name"] for b in boards_list if not privacy.board_hidden(b["id"])
    }

    summary = await _safe(
        api,
        "/analytics/summary",
        start=(day - timedelta(days=27)).isoformat(),
        end=day.isoformat(),
    )
    factor = estimate_factor(summary)
    cap = daily_cap(summary)
    plan_tomorrow = tomorrow >= datetime.now(tz).date()
    sugg = (
        await _safe(api, f"/day-plans/{tomorrow.isoformat()}/suggestions")
        if plan_tomorrow
        else None
    )
    candidates = build_candidates(
        (sugg or {}).get("items", []), boards, privacy, factor
    )
    goals = [
        g["title"]
        for g in (await _safe(api, "/goals", status="active") or [])
        if privacy.keep(g)
    ]
    async with session_maker() as session:
        facts = [
            f.content
            for f in await load_facts(session, user_id, include_private=not cloud)
        ]
        rejected = await _rejected_feedback(session, user_id)
        modes = await load_modes(session, user_id)

    messages = build_messages(
        day=day,
        plan=plan,
        candidates=candidates,
        cap=cap,
        factor=factor,
        privacy=privacy,
        cloud=cloud,
        facts=facts[:15],
        goals=goals[:8],
        rejected=rejected,
    )
    raw = await collect_text(provider, messages)
    parsed = parse_output(raw)
    notes: list[str] = []
    if parsed is None:
        notes.append("Model beklenen biçimde cevap vermedi; plan önerisi çıkarılamadı.")
        parsed = {"summary": raw[:1500] if raw and "{" not in raw else None, "plan": []}
    picks = pick(candidates, parsed["plan"], cap) if plan_tomorrow else []

    if parsed["summary"]:
        await api.write(
            "PUT",
            f"/day-plans/{day.isoformat()}/ai-summary",
            {"ai_summary": parsed["summary"][:4000]},
        )

    action_id: int | None = None
    action_status: str | None = None
    mode = modes.get("plan_day", "ask")
    if not plan_tomorrow:
        notes.append("Geçmiş bir gün değerlendirildi; ertesi gün için plan önerilmedi.")
    elif picks and mode == "never":
        notes.append("Gün planı önerileri Ayarlar'da kapalı.")
        picks = []
    elif picks:
        items = [
            {"card_id": c.card_id} if c.card_id else {"event_id": c.event_id}
            for c, _ in picks
        ]
        for item, (c, _) in zip(items, picks, strict=True):
            if c.card_id and c.adjusted:
                item["planned_minutes"] = c.adjusted
        writer = WriteTools(api, privacy, tz)
        try:
            prepared = await writer.prepare(
                "plan_day", {"date": tomorrow.isoformat(), "items": items}
            )
        except (ValueError, TaskApiError) as e:
            notes.append(f"Plan önerilemedi: {getattr(e, 'message', None) or e}")
        else:
            action = AiActionEntity(
                user_id=user_id,
                conversation_id=None,
                tool_call_id=None,
                action_type=prepared.action_type,
                args=prepared.args,
                summary=prepared.summary,
                status="proposed",
                model_id=provider.info.id,
            )
            if mode == "auto":
                try:
                    action.result = await writer.execute(
                        prepared.action_type, prepared.args
                    )
                    action.status = "executed"
                except TaskApiError as e:
                    action.result = {"error": e.message}
                    action.status = "failed"
                action.decided_at = datetime.now(UTC)
            async with session_maker() as session:
                session.add(action)
                await session.commit()
                action_id, action_status = action.id, action.status
    elif plan_tomorrow:
        notes.append("Yarın için uygun aday bulunamadı.")

    result = {
        "summary": parsed["summary"],
        "tip": parsed.get("tip"),
        "tomorrow": tomorrow.isoformat(),
        "plan": [
            {
                "title": c.title,
                "kind": c.kind,
                "card_id": c.card_id,
                "event_id": c.event_id,
                "minutes": c.minutes,
                "adjusted_minutes": c.adjusted,
                "planned_start": c.planned_start,
                "reason": reason,
            }
            for c, reason in picks
        ],
        "estimate_factor": factor,
        "estimate_text": factor_text(factor),
        "cap_minutes": cap,
        "candidate_count": len(candidates),
        "action_status": action_status,
        "notes": notes,
    }
    return result, action_id
