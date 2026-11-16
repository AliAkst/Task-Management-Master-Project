"""
Yerel Ingilizce koc degerlendirme betigi (Faz 13j2, K13).

    uv run python -m app.agent.english_eval --model qwen3.5:4b [--dry-run]

Sabit 20 cumlelik set (10 hatali + 10 dogru) `correct` istemiyle TEK TEK modele sorulur.
Olculer:
- yanlis duzeltme orani = dogru cumlelerden `mistakes` dolu donenlerin orani
- yakalama orani        = hatali cumlelerden en az bir hata donenlerin orani
- kategori isabeti      = yakalananlarda ilk hata kategorisi beklenenle ayni olanlarin orani
- ortalama sure / cumle
Esik (K13a): yanlis duzeltme <= %10 VE yakalama >= %70 -> yerel `correct` acik kalir.
`--dry-run` sahte saglayici kullanir (gercek model yok); gercek olcum kullanicida (kabul.md).
"""

import argparse
import asyncio
import json
import re
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from app.agent.english_coach import correction_prompt, parse_correction
from app.config import settings
from app.llm.registry import build_provider
from app.llm.types import ChatChunk, LLMError, Msg

SET_PATH = Path(__file__).with_name("english_eval_set.json")
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "benchmark_results"
MAX_WRONG_FIX = 0.10
MIN_CATCH = 0.70


def load_set() -> list[dict[str, Any]]:
    return json.loads(SET_PATH.read_text(encoding="utf-8"))


def _ratio(num: int, den: int) -> float:
    return num / den if den else 0.0


async def _ask(provider: Any, prompt: str) -> str:
    parts: list[str] = []
    async for chunk in provider.stream([Msg("user", prompt)], None, temperature=0):
        if chunk.type == "text":
            parts.append(chunk.text)
    return "".join(parts)


async def run_eval(
    provider: Any,
    items: list[dict[str, Any]],
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    wrong = [i for i in items if i.get("expected_category")]
    right = [i for i in items if not i.get("expected_category")]
    caught = cat_hits = wrong_fix = 0
    total_seconds = 0.0
    rows: list[dict[str, Any]] = []
    for item in items:
        sentence = item["sentence"]
        started = clock()
        try:
            raw = await _ask(provider, correction_prompt([sentence]))
        except LLMError:
            raw = ""
        total_seconds += clock() - started
        parsed = parse_correction(raw, [sentence])
        mistakes = parsed[0].mistakes if parsed else []
        row = {"sentence": sentence, "parsed": parsed is not None, "mistakes": len(mistakes)}
        if item.get("expected_category"):
            if mistakes:
                caught += 1
                hit = mistakes[0]["category"] == item["expected_category"]
                cat_hits += hit
                row["category_hit"] = hit
        elif mistakes:
            wrong_fix += 1
        rows.append(row)
    out = {
        "n": len(items),
        "n_wrong": len(wrong),
        "n_right": len(right),
        "catch_rate": _ratio(caught, len(wrong)),
        "wrong_fix_rate": _ratio(wrong_fix, len(right)),
        "category_accuracy": _ratio(cat_hits, caught),
        "avg_seconds": _ratio(total_seconds, len(items)) if items else 0.0,
        "rows": rows,
    }
    out["pass"] = out["wrong_fix_rate"] <= MAX_WRONG_FIX and out["catch_rate"] >= MIN_CATCH
    return out


class DryRunProvider:
    """Gercek model yok: setteki beklenen cevabi dondurur (olcum hattini denemek icin)."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.by_sentence = {i["sentence"]: i for i in items}

    async def stream(self, messages, tools=None, **_):
        match = re.search(r"^1\) (.*)$", messages[-1].content, re.M)
        sentence = match.group(1) if match else ""
        item = self.by_sentence.get(sentence, {})
        if item.get("expected_category"):
            result = {
                "i": 1,
                "corrected": item["expected_fix"],
                "mistakes": [
                    {
                        "original": sentence,
                        "corrected": item["expected_fix"],
                        "category": item["expected_category"],
                        "explanation_tr": "",
                    }
                ],
            }
        else:
            result = {"i": 1, "corrected": sentence, "mistakes": []}
        yield ChatChunk(type="text", text=json.dumps({"results": [result]}))


def _summary(model: str, r: dict[str, Any], dry: bool) -> str:
    verdict = "GEÇTİ" if r["pass"] else "GEÇMEDİ"
    return "\n".join(
        [
            f"İngilizce koç değerlendirmesi — {model}{' (dry-run)' if dry else ''}",
            f"Yanlış düzeltme oranı: %{r['wrong_fix_rate'] * 100:.0f} (eşik ≤ %10)",
            f"Yakalama oranı: %{r['catch_rate'] * 100:.0f} (eşik ≥ %70)",
            f"Kategori isabeti: %{r['category_accuracy'] * 100:.0f}",
            f"Ortalama süre/cümle: {r['avg_seconds']:.2f} sn",
            f"Sonuç: {verdict}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Yerel İngilizce koç değerlendirmesi")
    ap.add_argument("--model", required=True, help="örn. qwen3.5:4b")
    ap.add_argument("--dry-run", action="store_true", help="sahte sağlayıcı (gerçek model yok)")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # Windows cp1254 konsolu "≤" gibi karakterleri yazamaz
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    items = load_set()
    if args.dry_run:
        provider: Any = DryRunProvider(items)
    else:
        model_id = args.model if args.model.startswith("ollama:") else f"ollama:{args.model}"
        provider = build_provider(model_id, None, timeout=settings.background_timeout_seconds)
    result = asyncio.run(run_eval(provider, items))
    result.update(model=args.model, dry_run=args.dry_run)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", args.model)
    tag = "_dry" if args.dry_run else ""
    path = args.out_dir / f"english_{safe}{tag}_{datetime.now():%Y%m%d}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(_summary(args.model, result, args.dry_run))
    print(f"Rapor: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
