"""
Gelen Kutusu dagitimi (Faz 7d). Entegrasyonlardan (Trello, To Do...) Gelen Kutusu'na
dusen kartlar icin asistan hangi board'a gitmesi gerektigini onerir.

Model sadece SECER ve GEREKCE yazar (day_review deseni). Kart ve board kimliklerini
KOD dogrular: bilinmeyen id, Gelen Kutusu'nun kendisi, gizli/arsivli board atilir;
liste verilmediyse/gecersizse board'un ilk (bitmemis) listesi kullanilir. Emin
olmadigi karti model onermez. Onerinin tamami tek onay kartidir (`triage_inbox`);
kullanici madde madde cikarabilir.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.actions import load_modes
from app.db.models import AiActionEntity
from app.llm.types import LLMProvider, Msg
from app.tools.privacy import PrivacyFilter
from app.tools.task_api import TaskApiClient, TaskApiError
from app.tools.write_tools import WriteTools

ACTION = "triage_inbox"
MAX_CANDIDATES = 20
MAX_BOARDS = 25
RECENT_DAYS = 14
DESC_CHARS = 200

SYSTEM = """Sen kullanıcının kişisel düzen asistanısın.
Gelen Kutusu'na dış kaynaklardan (Trello, Microsoft To Do...) kartlar düştü.
Görevin: her kartı, aşağıdaki board'lardan kapsamına EN UYGUN olana yönlendirmek.
Kurallar:
- SADECE verilen kart ve board numaralarını kullan; yeni numara uydurma.
- Board'un kapsam açıklamasına ve listelerine bak. Emin değilsen o kartı HİÇ yazma;
  kullanıcı Gelen Kutusu'nda bırakır.
- Liste (list_id) istersen yaz; yazmazsan board'un ilk listesine konur.
- Her seçim için tek cümlelik, Türkçe gerekçe yaz.
Yalnızca şu biçimde JSON döndür, başka hiçbir şey yazma:
{{"moves": [{{"card_id": 12, "board_id": 3, "list_id": 31, "reason": "..."}}]}}"""


@dataclass
class Candidate:
    card_id: int
    title: str
    description: str | None
    due_date: str | None
    priority: str | None

    def line(self) -> str:
        bits = []
        if self.due_date:
            bits.append(f"son gün {self.due_date[:10]}")
        if self.priority and self.priority != "medium":
            bits.append(f"öncelik {self.priority}")
        head = f"[{self.card_id}] {self.title}"
        if bits:
            head += f" ({', '.join(bits)})"
        if self.description:
            head += f" — {self.description}"
        return head


@dataclass
class Target:
    board_id: int
    name: str
    scope: str | None
    lists: list[dict[str, Any]]  # {id, name, is_done_list}

    def first_list(self) -> dict[str, Any] | None:
        return next((x for x in self.lists if not x["is_done_list"]), None) or (
            self.lists[0] if self.lists else None
        )

    def block(self) -> str:
        names = ", ".join(f"{x['name']} (list_id {x['id']})" for x in self.lists)
        out = f"[board {self.board_id}] {self.name}"
        if self.scope:
            out += f" — kapsam: {self.scope[:DESC_CHARS]}"
        return f"{out}\n   listeler: {names}"


def _clean(text: str | None) -> str | None:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:DESC_CHARS] if text else None


def build_candidates(
    cards: list[dict[str, Any]],
    details: dict[int, dict[str, Any]],
    exclude: set[int],
) -> list[Candidate]:
    """Acik, ust duzey, yakinda onerilmemis kartlar; en fazla MAX_CANDIDATES."""
    out: list[Candidate] = []
    for c in sorted(cards, key=lambda c: c["id"]):
        if (
            c.get("status") == "completed"
            or c.get("is_archived")
            or c.get("parent_id")
            or c["id"] in exclude
        ):
            continue
        out.append(
            Candidate(
                card_id=c["id"],
                title=c["title"],
                description=_clean((details.get(c["id"]) or {}).get("description")),
                due_date=c.get("due_date"),
                priority=c.get("priority"),
            )
        )
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def parse_output(text: str) -> list[Any] | None:
    cleaned = re.sub(r"```(?:json)?", "", text or "")
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    moves = data.get("moves") if isinstance(data, dict) else None
    return moves if isinstance(moves, list) else None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def pick(
    candidates: list[Candidate], targets: dict[int, Target], proposed: list[Any]
) -> list[dict[str, Any]]:
    """Gecerli, tekrarsiz hamleler. Gecersiz kart/board atilir; liste yoksa ilk liste."""
    by_id = {c.card_id: c for c in candidates}
    used: set[int] = set()
    out: list[dict[str, Any]] = []
    for item in proposed:
        if not isinstance(item, dict):
            continue
        card_id, board_id = _int(item.get("card_id")), _int(item.get("board_id"))
        card = by_id.get(card_id) if card_id is not None else None
        target = targets.get(board_id) if board_id is not None else None
        if card is None or target is None or card.card_id in used:
            continue
        wanted = _int(item.get("list_id"))
        lst = next((x for x in target.lists if x["id"] == wanted), None)
        lst = lst or target.first_list()
        if lst is None:
            continue
        used.add(card.card_id)
        reason = item.get("reason")
        out.append(
            {
                "card_id": card.card_id,
                "title": card.title,
                "board_id": target.board_id,
                "list_id": lst["id"],
                "reason": str(reason).strip()[:300] if reason else None,
            }
        )
    return out


def build_messages(
    candidates: list[Candidate],
    targets: list[Target],
    facts: list[str],
    rejected: list[str],
) -> list[Msg]:
    parts = ["Gelen Kutusu'ndaki kartlar:", *(c.line() for c in candidates)]
    parts += ["", "Board'lar:", *(t.block() for t in targets)]
    if facts:
        parts += ["", "Kullanıcı hakkında bildiklerin:", *(f"- {f}" for f in facts)]
    if rejected:
        parts += [
            "",
            "Kullanıcının daha önce reddettiği dağıtım önerileri ve nedenleri:",
            *(f"- {r}" for r in rejected),
        ]
    return [Msg("system", SYSTEM), Msg("user", "\n".join(parts))]


async def collect_text(provider: LLMProvider, messages: list[Msg]) -> str:
    out: list[str] = []
    async for chunk in provider.stream(
        messages, None, temperature=0.2, max_tokens=2000
    ):
        if chunk.type == "text":
            out.append(chunk.text)
    return "".join(out).strip()


async def _recent_proposed_cards(
    session: AsyncSession, user_id: int
) -> tuple[set[int], list[str]]:
    """Son 14 gunde bekleyen/reddedilmis onerilerdeki kartlar + ret nedenleri."""
    since = datetime.now(UTC) - timedelta(days=RECENT_DAYS)
    rows = await session.scalars(
        select(AiActionEntity)
        .where(
            AiActionEntity.user_id == user_id,
            AiActionEntity.action_type == ACTION,
            AiActionEntity.status.in_(("proposed", "rejected")),
            AiActionEntity.created_at >= since,
        )
        .order_by(AiActionEntity.id.desc())
    )
    skip: set[int] = set()
    reasons: list[str] = []
    for a in rows:
        skip |= {m["card_id"] for m in (a.args or {}).get("moves", [])}
        if a.status == "rejected" and a.user_feedback and len(reasons) < 5:
            reasons.append(f"{a.summary.splitlines()[0]} → {a.user_feedback}")
    return skip, reasons


def _result(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "moves": [],
        "candidate_count": 0,
        "action_status": None,
        "notes": [],
    }
    return base | kw


async def run_inbox_triage(
    api: TaskApiClient,
    provider: LLMProvider,
    session_maker: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    tz: ZoneInfo,
) -> tuple[dict[str, Any], int | None]:
    """Gelen Kutusu'nu dagitir. Doner: (sonuc, ai_action id'si)."""
    cloud = not provider.info.is_local
    boards = await api.get("/boards")
    inbox = next((b for b in boards if b.get("system_kind") == "inbox"), None)
    if inbox is None:
        return _result(notes=["Gelen Kutusu henüz yok."]), None
    hidden = {b["id"] for b in boards if b.get("privacy") == "local_only"}
    privacy = PrivacyFilter(active=cloud, hidden_boards=hidden)
    if privacy.board_hidden(inbox["id"]):
        return (
            _result(
                notes=[
                    "Gelen Kutusu gizli (yalnız local model görebilir); bulut modelle "
                    "dağıtılamaz. Arka plan modelini local seç."
                ]
            ),
            None,
        )

    async with session_maker() as session:
        skip, rejected = await _recent_proposed_cards(session, user_id)
    detail = await api.get(f"/boards/{inbox['id']}")
    # Aciklama (yonlendirme icin onemli) kart ozetinde yok: aday basina bir istek
    open_cards = [c for c in detail["cards"] if c["id"] not in skip]
    details: dict[int, dict[str, Any]] = {}
    for c in open_cards[:MAX_CANDIDATES]:
        try:
            details[c["id"]] = await api.get(f"/cards/{c['id']}")
        except TaskApiError:
            continue
    candidates = build_candidates(open_cards, details, set())
    if not candidates:
        note = (
            "Gelen Kutusu'nda dağıtılacak yeni kart yok."
            if not skip
            else "Gelen Kutusu'ndaki kartlar için zaten öneri var (bekleyen ya da yakında reddedilmiş)."
        )
        return _result(notes=[note]), None

    targets: dict[int, Target] = {}
    for b in boards:
        if (
            b.get("system_kind")
            or b.get("is_archived")
            or privacy.board_hidden(b["id"])
            or len(targets) >= MAX_BOARDS
        ):
            continue
        try:
            d = await api.get(f"/boards/{b['id']}")
        except TaskApiError:
            continue
        targets[b["id"]] = Target(
            b["id"], b["name"], b.get("scope_description"), d.get("lists", [])
        )
    if not targets:
        return (
            _result(
                candidate_count=len(candidates),
                notes=["Kartların gidebileceği board yok."],
            ),
            None,
        )

    from app.tools.memory_tools import load_facts

    async with session_maker() as session:
        facts = [
            f.content
            for f in await load_facts(session, user_id, include_private=not cloud)
        ]
        modes = await load_modes(session, user_id)

    messages = build_messages(candidates, list(targets.values()), facts[:15], rejected)
    raw = await collect_text(provider, messages)
    proposed = parse_output(raw)
    notes: list[str] = []
    if proposed is None:
        notes.append("Model beklenen biçimde cevap vermedi; öneri çıkarılamadı.")
        proposed = []
    moves = pick(candidates, targets, proposed)
    result = _result(candidate_count=len(candidates), notes=notes)
    if not moves:
        if proposed is not None and not notes:
            notes.append("Asistan hiçbir karttan emin olamadı; hepsi Gelen Kutusu'nda kaldı.")
        return result, None

    mode = modes.get(ACTION, "ask")
    if mode == "never":
        notes.append("Gelen Kutusu dağıtımı Ayarlar'da kapalı.")
        return result, None

    writer = WriteTools(api, privacy, tz)
    try:
        prepared = await writer.prepare(
            ACTION,
            {
                "moves": [
                    {k: m[k] for k in ("card_id", "board_id", "list_id", "reason")}
                    for m in moves
                ]
            },
        )
    except (ValueError, TaskApiError) as e:
        notes.append(f"Öneri hazırlanamadı: {getattr(e, 'message', None) or e}")
        return result, None

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
            action.result = await writer.execute(prepared.action_type, prepared.args)
            action.status = "executed"
        except TaskApiError as e:
            action.result = {"error": e.message}
            action.status = "failed"
        action.decided_at = datetime.now(UTC)
    async with session_maker() as session:
        session.add(action)
        await session.commit()
        action_id, action_status = action.id, action.status

    result["moves"] = [
        {
            "card_id": m["card_id"],
            "title": m["title"],
            "board_id": m["board_id"],
            "board": targets[m["board_id"]].name,
            "list_id": m["list_id"],
            "list": next(x["name"] for x in targets[m["board_id"]].lists if x["id"] == m["list_id"]),
            "reason": m["reason"],
        }
        for m in moves
    ]
    result["action_status"] = action_status
    return result, action_id
