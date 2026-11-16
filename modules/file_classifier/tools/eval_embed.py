"""규칙 + 의미 매칭 조합을 "처음 보는 형태" 기준으로 재는 실험. GPU 권장. torch, transformers, openpyxl 필요.

    python -X utf8 modules/file_classifier/tools/eval_embed.py

규칙은 두 벌로 잰다.
    legacy   더미 v2 를 보기 전의 사전(doctype-0.2.0 수준). v2 파일은 이 규칙에게 처음 보는 형태다.
    current  v2 를 보고 보완한 사전(doctype-0.3.0). v2 에서는 당연히 다 맞힌다.
의미 매칭의 기준 용어(CONCEPTS)는 v2 의 열 이름이 아니라 통용 용어로 골랐지만, v2 를 본 뒤에 쓴 것이라
완전히 독립적이지는 않다. 기준값(TAU 등)은 dev 분할에서 고른 값을 그대로 쓴다.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "modules" / "file_classifier" / "tools"), str(ROOT / "modules" / "file_classifier" / "src"), str(ROOT)]

import sort_folder as sf  # noqa: E402
from file_classifier import doctype, doctype_embed as de  # noqa: E402

SAMPLES = ROOT / "modules" / "file_classifier" / "samples"
LEGACY_WEIGHTS = {("BOM", "level"): 2.5, ("BOM", "레벨"): 2.5, ("MES", "shopfloor"): 4, ("CRP", "workcenter"): 3, ("ERP", "safetystock"): 2,
                  ("ERP", "안전재고"): 2, ("ERP", "allocated"): 1.5, ("ERP", "할당재고"): 1.5}


def legacy_rules():
    """v2 를 보기 전의 사전으로 되돌린 (KEYWORDS, EXACT)."""
    more = {c: {w for w, _ in doctype._MORE.get(c, [])} for c in doctype.CATEGORIES}
    more_exact = {c: {w for w, _ in doctype._MORE_EXACT.get(c, [])} for c in doctype.CATEGORIES}
    keywords = {c: [(w, LEGACY_WEIGHTS.get((c, w), wt)) for w, wt in doctype.KEYWORDS[c] if w not in more[c]] for c in doctype.CATEGORIES}
    for (c, w), wt in LEGACY_WEIGHTS.items():
        if w not in {x for x, _ in keywords[c]}:
            keywords[c].append((w, wt))
    exact = {c: [(w, wt) for w, wt in doctype.EXACT[c] if w not in more_exact[c]] for c in doctype.CATEGORIES}
    return keywords, exact


def outcome(pred: str, truth: str) -> str:
    return "ok" if pred == truth else "review" if pred == de.REVIEW else "missed" if pred == doctype.UNKNOWN else "wrong"


def tally(preds, items) -> str:
    t = collections.Counter(outcome(p, it["category"]) for p, it in zip(preds, items))
    n = len(items)
    return f"정답 {t['ok']:3d} ({t['ok'] / n:5.1%})  확인 필요 {t['review']:3d}  미분류로 놓침 {t['missed']:3d}  오분류 {t['wrong']:3d}"


def main() -> None:
    items = json.loads((SAMPLES / "labels.json").read_text(encoding="utf-8"))["files"]
    sheets = [sf.read_sheets(SAMPLES / "inbox" / it["file"]) for it in items]
    current = [doctype.classify_workbook(s) for s in sheets]
    saved = doctype.KEYWORDS, doctype.EXACT
    doctype.KEYWORDS, doctype.EXACT = legacy_rules()
    legacy = [doctype.classify_workbook(s) for s in sheets]
    doctype.KEYWORDS, doctype.EXACT = saved
    matcher = de.SemanticMatcher()
    semantic = [matcher.classify(s) for s in sheets]

    def rule_only(verdicts):
        return [de.REVIEW if v.needs_review else v.category for v in verdicts]

    rows = [("규칙 legacy 만 (처음 보는 형태)", rule_only(legacy)),
            ("의미 매칭만", [de.REVIEW if s.category is None else s.category for s in semantic]),
            ("규칙 legacy + 의미 매칭", [de.combine(v, s)[0] for v, s in zip(legacy, semantic)]),
            ("규칙 current 만 (v2 를 보고 고친 것)", rule_only(current)),
            ("규칙 current + 의미 매칭", [de.combine(v, s)[0] for v, s in zip(current, semantic)])]
    test = [i for i, it in enumerate(items) if it["split"] == "test"]
    print(f"파일 {len(items)}개 (test {len(test)}), 장치 {matcher.embedder.device}, TAU={de.TAU} MIN_SCORE={de.MIN_SCORE} MIN_MARGIN={de.MIN_MARGIN}")
    for name, preds in rows:
        print(f"\n{name}\n   test: {tally([preds[i] for i in test], [items[i] for i in test])}\n   all : {tally(preds, items)}")
        if name == "규칙 legacy + 의미 매칭":
            miss = collections.Counter((items[i]["category"], items[i]["template"], preds[i]) for i in range(len(items)) if preds[i] != items[i]["category"])
            for k, n in miss.most_common(12):
                print("      ", n, k)


if __name__ == "__main__":
    main()
