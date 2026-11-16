"""
Ingilizce koclugu araclari (Faz 13j2): MCP'ye (Claude) ve yerel koca ortak yazma/okuma.

- Yazma hazirligi (dogrulama + onay ozeti) ve yurutme task-api /english uclarina gider.
- `WriteTools.prepare/execute` bunlara devreder; web sohbet asistaninin WRITE_SPECS'ine
  EKLENMEZ (kucuk modelin arac listesi buyumesin) - yalniz MCP ve web Ingilizce uclari.
- Izin turu `log_english` (varsayilan `auto`, T10).
"""

from typing import Any

from app.agent.english_coach import CATEGORIES
from app.llm.types import ToolSpec
from app.tools.task_api import TaskApiClient

ENGLISH_ACTION = "log_english"
ENGLISH_LABEL = "İngilizce kaydı"
CONTEXT_TOOL = "english_get_context"
WRITE_NAMES: tuple[str, ...] = (
    "english_log_mistakes",
    "english_add_vocab",
    "english_log_session",
)
ENGLISH_TOOL_TO_ACTION = {n: ENGLISH_ACTION for n in WRITE_NAMES}
MAX_ITEMS = 20
CONTEXT_VOCAB = 15
CONTEXT_MISTAKES = 20
PROFILE_KEYS = ("target_level", "current_level", "daily_minutes", "focus", "started_at")

_CAT_ENUM = list(CATEGORIES)

CONTEXT_SPEC = ToolSpec(
    CONTEXT_TOOL,
    "İngilizce koçu verisi: profil, vadesi gelen kelimeler (en çok 15), son 20 hata, "
    "en sık hata kategorileri, son seans özeti. İngilizce pratik seansına başlamadan önce oku.",
)
WRITE_SPECS: list[ToolSpec] = [
    ToolSpec(
        "english_log_mistakes",
        "Pratikte yapılan İngilizce hataları kaydeder (en çok 20). Kategori: "
        + ", ".join(_CAT_ENUM)
        + ".",
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "original": {"type": "string"},
                            "corrected": {"type": "string"},
                            "category": {"type": "string", "enum": _CAT_ENUM},
                            "explanation_tr": {"type": "string"},
                        },
                        "required": ["original", "corrected", "category"],
                    },
                }
            },
            "required": ["items"],
        },
    ),
    ToolSpec(
        "english_add_vocab",
        "Öğrenilen yeni kelimeleri kelime listesine ekler (en çok 20; var olan terim tekrar eklenmez).",
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "term": {"type": "string"},
                            "meaning_tr": {"type": "string"},
                            "example": {"type": "string"},
                        },
                        "required": ["term", "meaning_tr"],
                    },
                }
            },
            "required": ["items"],
        },
    ),
    ToolSpec(
        "english_log_session",
        "Bitirilen derin pratik seansının kısa özetini kaydeder.",
        {
            "type": "object",
            "properties": {
                "minutes": {"type": "integer"},
                "summary": {"type": "string"},
                "new_vocab": {"type": "integer"},
                "mistakes_count": {"type": "integer"},
            },
            "required": ["minutes", "summary"],
        },
    ),
]


# ---------------- dogrulama yardimcilari ----------------
def _text(value: Any, field: str, limit: int, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        if required:
            raise ValueError(f"{field} boş olmayan metin olmalı")
        return None
    value = value.strip()
    if len(value) > limit:
        raise ValueError(f"{field} en çok {limit} karakter olabilir")
    return value


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("items en az 1 öğeli liste olmalı")
    if len(value) > MAX_ITEMS:
        raise ValueError(f"items en çok {MAX_ITEMS} öğe olabilir")
    if not all(isinstance(v, dict) for v in value):
        raise ValueError("items öğeleri nesne olmalı")
    return value


def _int(value: Any, field: str, lo: int, hi: int, default: int | None = None) -> int:
    if value is None and default is not None:
        return default
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ValueError(f"{field} {lo}-{hi} arasında tam sayı olmalı")
    return value


def _clip(text: str, n: int = 50) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def clean_mistake_items(items: Any, source: str) -> list[dict[str, Any]]:
    out = []
    for it in _items(items):
        cat = it.get("category")
        cat = cat.strip().lower() if isinstance(cat, str) else "other"
        row: dict[str, Any] = {
            "original": _text(it.get("original"), "original", 500),
            "corrected": _text(it.get("corrected"), "corrected", 500),
            "category": cat if cat in CATEGORIES else "other",
            "source": source,
        }
        expl = it.get("explanation_tr")
        if isinstance(expl, str) and expl.strip():
            row["explanation_tr"] = expl.strip()[:500]
        out.append(row)
    return out


def mistakes_summary(items: list[dict[str, Any]], extra: str = "") -> str:
    lines = [f"📚 İngilizce: {len(items)} hata kaydedilir{extra}"]
    lines += [f"• {_clip(i['original'])} → {_clip(i['corrected'])}" for i in items[:3]]
    return "\n".join(lines)


def prepare_log_mistakes(
    items: Any, source: str = "claude"
) -> tuple[dict[str, Any], str]:
    rows = clean_mistake_items(items, source)
    return {"kind": "mistakes", "items": rows}, mistakes_summary(rows)


def prepare_add_vocab(items: Any, source: str = "claude") -> tuple[dict[str, Any], str]:
    rows = []
    for it in _items(items):
        row: dict[str, Any] = {
            "term": _text(it.get("term"), "term", 100),
            "meaning_tr": _text(it.get("meaning_tr"), "meaning_tr", 300),
            "source": source,
        }
        ex = _text(it.get("example"), "example", 500, required=False)
        if ex:
            row["example"] = ex
        rows.append(row)
    terms = ", ".join(_clip(r["term"], 30) for r in rows[:5])
    return (
        {"kind": "vocab", "items": rows},
        f"📚 İngilizce: {len(rows)} kelime eklenir ({terms})",
    )


def prepare_log_session(
    minutes: Any,
    summary: Any,
    new_vocab: Any = None,
    mistakes_count: Any = None,
) -> tuple[dict[str, Any], str]:
    row = {
        "kind": "deep",
        "minutes": _int(minutes, "minutes", 1, 240),
        "summary": _text(summary, "summary", 2000),
        "new_vocab": _int(new_vocab, "new_vocab", 0, 32767, default=0),
        "mistakes_count": _int(mistakes_count, "mistakes_count", 0, 32767, default=0),
        "source": "claude",
    }
    return (
        {"kind": "session", "session": row},
        f"📚 İngilizce seansı kaydedilir: {row['minutes']} dk — {_clip(row['summary'], 80)}",
    )


# ---------------- yurutme ----------------
async def execute_english(api: TaskApiClient, args: dict[str, Any]) -> dict[str, Any]:
    kind = args.get("kind")
    out: dict[str, Any] = {}
    if kind == "mistakes":
        await api.write("POST", "/english/mistakes", {"items": args["items"]})
        out["saved"] = len(args["items"])
        if args.get("session"):
            await api.write("POST", "/english/sessions", args["session"])
            out["session_logged"] = True
    elif kind == "vocab":
        res = await api.write("POST", "/english/vocab", {"items": args["items"]})
        rows = res if isinstance(res, list) else [res]
        out["added"] = sum(1 for r in rows if not (r or {}).get("existing"))
        out["existing"] = len(rows) - out["added"]
    elif kind == "session":
        await api.write("POST", "/english/sessions", args["session"])
        out["session_logged"] = True
    else:
        raise ValueError("Bilinmeyen İngilizce işlemi")
    return out


# ---------------- okuma ----------------
async def english_context(api: TaskApiClient) -> dict[str, Any]:
    today = await api.get("/english/today") or {}
    mistakes = await api.get("/english/mistakes", limit=CONTEXT_MISTAKES) or []
    sessions = await api.get("/english/sessions", limit=1) or []
    profile = today.get("profile")
    last = sessions[0].get("summary") if sessions else None
    return {
        "profile": (
            {k: profile[k] for k in PROFILE_KEYS if k in profile} if profile else None
        ),
        "due_vocab": [
            {"term": v["term"], "meaning_tr": v["meaning_tr"]}
            for v in (today.get("due_vocab") or [])[:CONTEXT_VOCAB]
        ],
        "recent_mistakes": [
            {"original": m["original"], "corrected": m["corrected"], "category": m["category"]}
            for m in mistakes[:CONTEXT_MISTAKES]
        ],
        "top_categories": today.get("top_categories") or [],
        "last_session_summary": last,
    }
