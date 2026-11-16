"""
Yerel Ingilizce kocu (Faz 13j2): odakli tek gorevli istem + KATI dogrulayici.

Model yalniz cumleyi duzeltir; veri kaydi, izin ve kurallar kodda. Model JSON'u bozuk
verebilir (G1): `parse_correction` hicbir girdide patlamaz, gecersizse None doner.
Bu modul yalniz YEREL modelle kullanilir (bulut asla - cagiran taraf zorlar).
"""

import json
from dataclasses import dataclass, field
from typing import Any

from app.llm.types import LLMError, LLMProvider, Msg

CATEGORIES = (
    "grammar",
    "tense",
    "preposition",
    "article",
    "word_choice",
    "spelling",
    "other",
)
MAX_SENTENCES = 5
MAX_SENTENCE_CHARS = 300
MAX_CORRECTED = 400
MAX_MISTAKE_TEXT = 200
MAX_EXPLANATION = 300
MAX_REPLY = 1000
MAX_HISTORY = 10

CORRECT_PROMPT = """You are an English teacher for a Turkish learner. For EACH numbered sentence return JSON only:
{{"results":[{{"i":1,"corrected":"...","mistakes":[{{"original":"...","corrected":"...","category":"grammar|tense|preposition|article|word_choice|spelling|other","explanation_tr":"kısa Türkçe açıklama"}}]}}]}}
Rules: if a sentence is already correct, return it unchanged with "mistakes": []. Do not rewrite style. Keep meaning.
Sentences:
{sentences}"""

DIALOG_PROMPT = """You are a friendly English conversation partner for a Turkish learner. Reply to the learner in 1-2 short, simple English sentences and ask one follow-up question. Also check the learner's LAST message for mistakes. Return JSON only:
{"reply":"...","corrections":[{"original":"...","corrected":"...","category":"grammar|tense|preposition|article|word_choice|spelling|other","explanation_tr":"kısa Türkçe açıklama"}]}
If the last message has no mistakes, "corrections" is []. Do not rewrite style."""


def correction_prompt(sentences: list[str]) -> str:
    numbered = "\n".join(f"{i}) {s}" for i, s in enumerate(sentences, 1))
    return CORRECT_PROMPT.format(sentences=numbered)


def example_prompt(terms: list[str]) -> str:
    """Model YOK: kullaniciya gosterilecek pratik metni kodla uretilir."""
    return "Şu kelimelerle 2 cümle kur: " + ", ".join(terms)


# ---------------- dogrulayici ----------------
@dataclass
class Result:
    original: str
    corrected: str
    ok: bool | None  # True: dogru, False: duzeltildi, None: degerlendirilemedi
    mistakes: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "corrected": self.corrected,
            "ok": self.ok,
            "mistakes": self.mistakes,
        }


def _extract_object(raw: str) -> Any:
    """Ilk `{` ile son `}` arasi; gecersiz JSON -> None. (Kod citi, onsoz/sonsoz atilir.)"""
    if not isinstance(raw, str):
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except ValueError:
        return None


def _index(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def clean_mistakes(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for m in value:
        if not isinstance(m, dict):
            continue
        orig, corr = m.get("original"), m.get("corrected")
        if not (isinstance(orig, str) and isinstance(corr, str)):
            continue
        orig, corr = orig.strip(), corr.strip()
        if not orig or not corr:
            continue
        if len(orig) > MAX_MISTAKE_TEXT or len(corr) > MAX_MISTAKE_TEXT:
            continue
        cat = m.get("category")
        cat = cat.strip().lower() if isinstance(cat, str) else "other"
        if cat not in CATEGORIES:
            cat = "other"
        expl = m.get("explanation_tr")
        if not isinstance(expl, str) or len(expl) > MAX_EXPLANATION:
            expl = ""
        out.append(
            {"original": orig, "corrected": corr, "category": cat, "explanation_tr": expl}
        )
    return out


def parse_correction(raw: str, sentences: list[str]) -> list[Result] | None:
    """Ham model yaniti -> cumle basina sonuc; kullanilamaz bicimde None."""
    data = _extract_object(raw)
    if not isinstance(data, dict):
        return None
    rows = data.get("results")
    if not isinstance(rows, list):
        return None
    n = len(sentences)
    found: dict[int, dict[str, Any]] = {}
    for pos, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        idx = _index(row["i"]) if "i" in row else pos
        if idx is None or not 1 <= idx <= n or idx in found:
            continue
        found[idx] = row
    out: list[Result] = []
    for i, original in enumerate(sentences, 1):
        row = found.get(i)
        if row is None:
            out.append(Result(original, original, None))
            continue
        corrected = row.get("corrected", original)
        if not isinstance(corrected, str) or not corrected.strip() or len(corrected) > MAX_CORRECTED:
            out.append(Result(original, original, None))
            continue
        corrected = corrected.strip()
        mistakes = clean_mistakes(row.get("mistakes"))
        if corrected == original.strip():
            out.append(Result(original, original, True))
        else:
            out.append(Result(original, corrected, False, mistakes))
    return out


def parse_dialog(raw: str) -> tuple[str, list[dict[str, str]]] | None:
    data = _extract_object(raw)
    if not isinstance(data, dict):
        return None
    reply = data.get("reply")
    if not isinstance(reply, str) or not reply.strip() or len(reply) > MAX_REPLY:
        return None
    return reply.strip(), clean_mistakes(data.get("corrections"))


# ---------------- model cagrisi ----------------
async def ask_model(provider: LLMProvider, msgs: list[Msg]) -> str:
    parts: list[str] = []
    async for chunk in provider.stream(msgs, None, temperature=0):
        if chunk.type == "text":
            parts.append(chunk.text)
    return "".join(parts)


async def correct_sentences(
    provider: LLMProvider, sentences: list[str], attempts: int = 2
) -> list[Result] | None:
    """Gecersiz yanitta bir kez daha dener; yine olmuyorsa None. LLMError yukari."""
    prompt = correction_prompt(sentences)
    for _ in range(attempts):
        parsed = parse_correction(await ask_model(provider, [Msg("user", prompt)]), sentences)
        if parsed is not None:
            return parsed
    return None


async def dialog_turn(
    provider: LLMProvider,
    history: list[dict[str, str]],
    user_text: str,
    attempts: int = 2,
) -> tuple[str, list[dict[str, str]]] | None:
    msgs = [Msg("system", DIALOG_PROMPT)]
    for turn in history[-MAX_HISTORY:]:
        role = "user" if turn["role"] == "user" else "assistant"
        msgs.append(Msg(role, turn["text"]))
    msgs.append(Msg("user", user_text))
    for _ in range(attempts):
        parsed = parse_dialog(await ask_model(provider, msgs))
        if parsed is not None:
            return parsed
    return None


__all__ = ["LLMError", "Result", "correct_sentences", "dialog_turn", "parse_correction"]
