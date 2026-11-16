"""Faz 13j2: Ingilizce degerlendirme seti ve olcum betigi (sahte saglayici; gercek model yok)."""

import json
from collections import Counter

from app.agent import english_eval
from app.agent.english_coach import CATEGORIES
from app.agent.english_eval import load_set, run_eval


def reply_for(item: dict, *, flag: bool, category: str | None = None) -> str:
    s = item["sentence"]
    if not flag:
        return json.dumps({"results": [{"i": 1, "corrected": s, "mistakes": []}]})
    mistake = {
        "original": "x",
        "corrected": "y",
        "category": category or "other",
        "explanation_tr": "",
    }
    return json.dumps(
        {"results": [{"i": 1, "corrected": s + " (fixed)", "mistakes": [mistake]}]}
    )


class ScriptedProvider:
    """Sirayla onceden hazirlanmis yanitlari verir (set sirasiyla, cumle cumle)."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    async def stream(self, messages, tools=None, **_):
        from app.llm.types import ChatChunk

        self.prompts.append(messages[-1].content)
        yield ChatChunk(type="text", text=self.replies.pop(0))


def test_set_shape_is_fixed():
    items = load_set()
    assert len(items) == 20
    wrong = [i for i in items if i["expected_category"]]
    right = [i for i in items if not i["expected_category"]]
    assert len(wrong) == 10 and len(right) == 10
    assert Counter(i["expected_category"] for i in wrong) == {
        "tense": 3, "preposition": 2, "article": 2, "word_choice": 2, "spelling": 1,
    }  # fmt: skip
    assert all(i["expected_fix"] for i in wrong)
    assert all(c in CATEGORIES for c in {i["expected_category"] for i in wrong})
    assert len({i["sentence"] for i in items}) == 20


async def test_metrics_match_known_replies():
    items = load_set()
    replies = []
    wrong_seen = right_seen = 0
    for it in items:
        if it["expected_category"]:
            wrong_seen += 1
            if wrong_seen <= 8:  # 8/10 yakalandi
                # ilk 6'sinda dogru kategori
                cat = it["expected_category"] if wrong_seen <= 6 else "other"
                replies.append(reply_for(it, flag=True, category=cat))
            else:
                replies.append(reply_for(it, flag=False))
        else:
            right_seen += 1
            replies.append(reply_for(it, flag=right_seen <= 2))  # 2/10 yanlis duzeltme
    ticks = iter(range(1000))
    prov = ScriptedProvider(replies)
    out = await run_eval(prov, items, clock=lambda: next(ticks) * 0.5)
    assert out["catch_rate"] == 0.8
    assert out["wrong_fix_rate"] == 0.2
    assert out["category_accuracy"] == 0.75  # 6 / 8
    assert out["avg_seconds"] == 0.5
    assert out["n"] == 20 and len(prov.prompts) == 20
    assert out["pass"] is False  # yanlis duzeltme > %10


async def test_threshold_pass_and_unparseable_counts_as_miss():
    items = load_set()
    replies = []
    for it in items:
        if it["expected_category"]:
            replies.append(reply_for(it, flag=True, category=it["expected_category"]))
        else:
            replies.append(reply_for(it, flag=False))
    replies[0] = "not json at all"  # yakalanamayan hatali cumle: 9/10
    out = await run_eval(ScriptedProvider(replies), items)
    assert out["catch_rate"] == 0.9 and out["wrong_fix_rate"] == 0.0
    assert out["pass"] is True


async def test_prompt_contains_single_numbered_sentence():
    items = load_set()[:1]
    prov = ScriptedProvider([reply_for(items[0], flag=False)])
    await run_eval(prov, items)
    assert prov.prompts[0].rstrip().endswith("1) " + items[0]["sentence"])


def test_dry_run_cli_writes_report_without_real_model(tmp_path, capsys, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("dry-run gercek saglayici kurmamali")

    monkeypatch.setattr(english_eval, "build_provider", boom)
    code = english_eval.main(
        ["--model", "qwen3.5:4b", "--dry-run", "--out-dir", str(tmp_path)]
    )
    assert code == 0
    files = list(tmp_path.glob("english_qwen3.5-4b_*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["dry_run"] is True and data["n"] == 20
    assert data["catch_rate"] == 1.0 and data["wrong_fix_rate"] == 0.0
    assert "yakalama" in capsys.readouterr().out.lower()
