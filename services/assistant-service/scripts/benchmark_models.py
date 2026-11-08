"""
Local model benchmark'i (Faz 4 basi): ayni Turkce senaryolar her modelde.

Olculenler: model yukleme suresi, ilk token suresi (TTFT), token/sn, arac
cagrisi gecerliligi + otomatik dogruluk kontrolleri. Yanitlar insan puanlamasi
icin rapora yazilir.

Kullanim (assistant-service klasorunden):
    uv run python -m scripts.benchmark_models
    uv run python -m scripts.benchmark_models qwen3.5:4b gemma4:26b

Not: Her modelden sonra VRAM bosaltilir (keep_alive=0) ki bir sonraki adil olcsun.
"""

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.llm.registry import build_provider
from app.llm.types import LLMError, Msg, ToolCall, ToolSpec

DEFAULT_MODELS = ["qwen3.5:4b", "gemma4:26b", "qwen3.8:27b", "deepseek-r1:32b"]
SYSTEM = (
    "Sen kullanıcının kişisel yaşam ve görev planlama asistanısın. Türkçe, samimi ve "
    "kısa cevap ver. Bugün 8 Kasım 2026 Pazar, saat 10:00. Saat dilimi Europe/Istanbul "
    "(+03:00). Bir işlem gerektiğinde verilen araçları kullan; tarihleri ISO 8601 ve "
    "+03:00 ofsetiyle yaz."
)

TOOLS = {
    "create_event": ToolSpec(
        name="create_event",
        description="Takvime etkinlik ekler.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_at": {"type": "string", "description": "ISO 8601, +03:00"},
                "end_at": {"type": "string", "description": "ISO 8601, +03:00"},
                "board_name": {"type": "string", "description": "Board adı, örn. Spor"},
            },
            "required": ["title", "start_at", "end_at"],
        },
    ),
    "search_cards": ToolSpec(
        name="search_cards",
        description="Kartları başlıkta arar; id ve başlık döner.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    ),
    "split_card": ToolSpec(
        name="split_card",
        description="Kartı eşit alt kartlara böler; süreyi dağıtır, istenirse sırayla bağlar.",
        parameters={
            "type": "object",
            "properties": {
                "card_id": {"type": "integer"},
                "parts": {"type": "integer"},
                "total_minutes": {"type": "integer"},
                "chain": {"type": "boolean"},
            },
            "required": ["card_id", "parts"],
        },
    ),
}

STATS = {
    "son_7_gun": {
        "calisilan_dk": 1260,
        "plana_uyum": 0.62,
        "tahmin_orani": 1.35,
        "en_verimli_saatler": ["09-11", "20-22"],
        "en_cok_ertelenen": ["Bacak antrenmanı (3x)", "Fatura ödemeleri (2x)"],
    },
    "acik_kartlar": [
        {"baslik": "Docker kursu — Bölüm 2/5", "tahmin_dk": 240, "board": "Eğitim"},
        {"baslik": "Bacak antrenmanı", "tahmin_dk": 60, "board": "Spor"},
        {"baslik": "Fatura ödemeleri", "tahmin_dk": 20, "board": "Günlük işler"},
        {
            "baslik": "Sprint raporu",
            "tahmin_dk": 90,
            "board": "İş",
            "son_tarih": "yarın",
        },
    ],
    "yarin_takvim": [{"baslik": "İş toplantısı", "saat": "14:00-15:00"}],
}

SCENARIOS = [
    {
        "key": "chat",
        "title": "Serbest sohbet",
        "prompt": "Merhaba! Bu hafta iş çok yoğun ve spora vakit ayıramıyorum. "
        "Haftayı dengelemem için 3 kısa öneri verir misin?",
        "tools": [],
    },
    {
        "key": "single_tool",
        "title": "Tek araç çağrısı",
        "prompt": "Yarın akşam 18:00'de 45 dakikalık koşu ekler misin? Spor board'una.",
        "tools": ["create_event"],
    },
    {
        "key": "chain",
        "title": "Çok adımlı zincir",
        "prompt": "Docker kursu kartımı bul, toplam 20 saat olacak şekilde 5 eşit "
        "parçaya böl ve parçaları sırayla birbirine bağla.",
        "tools": ["search_cards", "split_card"],
    },
    {
        "key": "plan",
        "title": "İstatistikten plan",
        "prompt": "Verilerim aşağıda. Yarın için gerçekçi bir saatlik plan çıkar; "
        "tahminlerimin ne kadar saptığını dikkate al.\n\n"
        + json.dumps(STATS, ensure_ascii=False, indent=1),
        "tools": [],
    },
]


@dataclass
class Run:
    scenario: str
    seconds: float = 0
    ttft: float | None = None
    completion_tokens: int = 0
    text: str = ""
    calls: list[ToolCall] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    error: str | None = None

    @property
    def tok_per_s(self) -> float | None:
        if not self.completion_tokens or self.ttft is None:
            return None
        gen = self.seconds - self.ttft
        return round(self.completion_tokens / gen, 1) if gen > 0 else None


def mock_tool(call: ToolCall) -> str:
    if call.name == "search_cards":
        return json.dumps([{"id": 42, "title": "Docker kursu"}], ensure_ascii=False)
    return json.dumps({"ok": True}, ensure_ascii=False)


async def run_scenario(model_id: str, sc: dict[str, Any]) -> Run:
    provider = build_provider(model_id)
    tools = [TOOLS[t] for t in sc["tools"]]
    messages = [Msg("system", SYSTEM), Msg("user", sc["prompt"])]
    run = Run(scenario=sc["key"])
    start = time.perf_counter()
    try:
        for _round in range(3):  # zincir icin en fazla 3 tur
            calls: list[ToolCall] = []
            text = ""
            async for chunk in provider.stream(
                messages, tools or None, temperature=0.2
            ):
                if run.ttft is None and chunk.type in ("text", "tool_call"):
                    run.ttft = time.perf_counter() - start
                if chunk.type == "text":
                    text += chunk.text
                elif chunk.type == "tool_call" and chunk.tool_call:
                    calls.append(chunk.tool_call)
                elif chunk.type == "usage" and chunk.usage:
                    run.completion_tokens += chunk.usage.completion_tokens
            run.text += text
            run.calls += calls
            if not calls:
                break
            messages.append(Msg("assistant", text, tool_calls=calls))
            for c in calls:
                messages.append(
                    Msg("tool", mock_tool(c), tool_call_id=c.id, name=c.name)
                )
    except LLMError as e:
        run.error = str(e)
    run.seconds = time.perf_counter() - start
    run.checks = check(sc["key"], run)
    return run


def check(key: str, run: Run) -> dict[str, bool]:
    turkish = any(ch in run.text for ch in "çğıöşüÇĞİÖŞÜ")
    calls = {c.name: c for c in run.calls if c.valid}
    if key == "chat":
        return {"türkçe": turkish, "yeterli uzunluk": len(run.text) > 150}
    if key == "single_tool":
        c = calls.get("create_event")
        if not c:
            return {"create_event çağrıldı": False}
        a = c.arguments
        return {
            "create_event çağrıldı": True,
            "başlangıç 9 Kas 18:00": str(a.get("start_at", "")).startswith(
                "2026-11-09T18:00"
            ),
            "bitiş 18:45": str(a.get("end_at", "")).startswith("2026-11-09T18:45"),
            "board Spor": "spor" in str(a.get("board_name", "")).lower(),
        }
    if key == "chain":
        s = calls.get("search_cards")
        p = calls.get("split_card")
        args = p.arguments if p else {}
        return {
            "önce arama": bool(s)
            and "docker" in str(s.arguments.get("query", "")).lower(),
            "doğru kart (42)": args.get("card_id") == 42,
            "5 parça": args.get("parts") == 5,
            "1200 dk": args.get("total_minutes") == 1200,
            "zincir": args.get("chain") is True,
            "geçersiz JSON yok": all(c.valid for c in run.calls),
        }
    if key == "plan":
        mentioned = sum(
            1
            for t in ("Docker", "Bacak", "Fatura", "Sprint")
            if t.lower() in run.text.lower()
        )
        return {
            "türkçe": turkish,
            "kartların ≥3'ü planda": mentioned >= 3,
            "toplantı dikkate alındı": "14:00" in run.text,
        }
    return {}


async def unload(model: str) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(
            f"{settings.ollama_url}/api/generate",
            json={"model": model, "keep_alive": 0},
        )


async def load_time(model_id: str) -> float | str:
    """Modeli bellege yukleyip kisa bir cevap alma suresi (soguk baslangic)."""
    provider = build_provider(model_id)
    start = time.perf_counter()
    try:
        async for _ in provider.stream(
            [Msg("user", "Sadece 'tamam' yaz.")], max_tokens=5
        ):
            pass
    except LLMError as e:
        return f"HATA: {e}"
    return round(time.perf_counter() - start, 1)


async def vram_used() -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{settings.ollama_url}/api/ps")
        out = []
        for m in res.json().get("models", []):
            total, vram = m.get("size", 0), m.get("size_vram", 0)
            pct = round(100 * vram / total) if total else 0
            out.append(f"{m['name']}: {round(total / 1e9, 1)} GB, %{pct} GPU'da")
        return "; ".join(out) or "-"


def fmt(v: float | None, suffix: str = "") -> str:
    return "-" if v is None else f"{v:.1f}{suffix}"


async def main(models: list[str]) -> None:
    out_dir = Path("benchmark_results")
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    report: list[str] = [
        f"# Local model benchmark — {datetime.now():%d.%m.%Y %H:%M}\n",
        f"Ollama native API, düşünme modu kapalı, num_ctx={settings.ollama_num_ctx}, "
        "temperature 0.2.\n",
    ]
    summary: list[str] = [
        "| Model | Yükleme | Bellek | Senaryo | Süre | İlk token | tok/sn | Otomatik kontroller |",
        "|---|---|---|---|---|---|---|---|",
    ]
    details: list[str] = []
    raw: dict[str, Any] = {}

    for model in models:
        model_id = f"ollama:{model}"
        print(f"\n=== {model} ===", flush=True)
        lt = await load_time(model_id)
        mem = await vram_used()
        print(f"  yükleme: {lt} s | {mem}", flush=True)
        raw[model] = {"load_seconds": lt, "memory": mem, "runs": []}
        for sc in SCENARIOS:
            run = await run_scenario(model_id, sc)
            passed = sum(run.checks.values())
            print(
                f"  {sc['key']:<12} {run.seconds:6.1f}s  ttft={fmt(run.ttft)}  "
                f"tok/s={run.tok_per_s}  kontrol {passed}/{len(run.checks)}"
                + (f"  HATA: {run.error}" if run.error else ""),
                flush=True,
            )
            summary.append(
                f"| {model} | {lt} s | {mem.split(': ', 1)[-1]} | {sc['title']} | "
                f"{run.seconds:.0f} s | {fmt(run.ttft, ' s')} | {run.tok_per_s or '-'} | "
                + (f"HATA: {run.error}" if run.error else f"{passed}/{len(run.checks)}")
                + " |"
            )
            calls = "\n".join(
                f"- `{c.name}({json.dumps(c.arguments, ensure_ascii=False) if c.valid else c.raw_arguments})`"
                + ("" if c.valid else " ⚠️ geçersiz JSON")
                for c in run.calls
            )
            checks = ", ".join(
                f"{'✅' if v else '❌'} {k}" for k, v in run.checks.items()
            )
            details.append(
                f"### {model} — {sc['title']}\n\n{checks}\n\n"
                + (f"**Araç çağrıları:**\n{calls}\n\n" if calls else "")
                + "**Yanıt:**\n\n> "
                + (run.text.strip() or "_(metin yok)_").replace("\n", "\n> ")
                + "\n\n**Senin puanın (1–5):** __\n"
            )
            raw[model]["runs"].append(
                {
                    "scenario": sc["key"],
                    "seconds": round(run.seconds, 1),
                    "ttft": run.ttft and round(run.ttft, 1),
                    "tok_per_s": run.tok_per_s,
                    "completion_tokens": run.completion_tokens,
                    "checks": run.checks,
                    "error": run.error,
                }
            )
        await unload(model)

    report += ["## Özet\n", *summary, "\n## Yanıtlar\n", *details]
    md = out_dir / f"benchmark-{stamp}.md"
    md.write_text("\n".join(report), encoding="utf-8")
    (out_dir / f"benchmark-{stamp}.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nRapor: {md.resolve()}", flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or DEFAULT_MODELS))
