"""분류 원리를 실제 데이터로 설명하는 그림을 만든다. GPU 권장. torch, transformers, openpyxl, matplotlib 필요.

    python -X utf8 modules/file_classifier/tools/make_principle_figures.py

그림은 modules/file_classifier/figures/ 에, 그림에 쓴 값은 figures/principle_numbers.json 에 저장한다.
    p1_walkthrough.png   실제 엑셀 한 개가 분류되는 과정 (파일 → 낱말 → 사전 대조 → 뜻 연결 → 점수 → 결정)
    p2_why_terms.png     같은 파일을 통째로 비교했을 때와 낱말 단위로 비교했을 때
    p3_threshold.png     낱말과 기준 용어의 유사도 분포와 기준 0.65
    p4_why_combine.png   사전과 뜻이 같은 답일 때, 한쪽만 답할 때, 서로 다를 때의 정답 여부

모든 값은 더미 v2 의 test 분할(109개)에서 실제로 계산한 것이다. "사전"은 이 더미를 보기 전의 사전(legacy)이다.
합성 자료이며 실제 기업 파일이 아니다.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "modules" / "file_classifier" / "tools"), str(ROOT / "modules" / "file_classifier" / "src"), str(ROOT)]

import eval_embed as ee  # noqa: E402
import sort_folder as sf  # noqa: E402
from file_classifier import doctype, doctype_embed as de  # noqa: E402

FIG = ROOT / "modules" / "file_classifier" / "figures"
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
BLUE, LIGHT_BLUE, YELLOW, NEUTRAL, CRITICAL = "#2a78d6", "#d9e8fb", "#eda100", "#c3c2b7", "#d03b3b"
LABELS = list(doctype.CATEGORIES) + [doctype.UNKNOWN]
# 파일 전체를 한 문장으로 비교하는 방식(채택하지 않음)에서 쓰던 범주 설명
DESCRIPTIONS = {
    "BOM": "자재명세서 BOM. 제품을 만드는 데 필요한 구성품, 부품, 원자재와 소요량. 모품목, 자품목, 레벨, 소요량, 단위, 손실률",
    "MPS": "주생산계획, 기준생산계획 MPS. 완제품별 주차·월별 생산 계획 수량, 수요예측, 고객주문, 예상재고, 납기약속가능수량",
    "MRP": "자재소요계획 MRP, 소요량 전개. 자재별 총소요량, 예정입고, 현재고, 순소요량, 계획발주, 리드타임, 로트",
    "RCCP": "개략능력계획 RCCP. 주생산계획 기준으로 주요 설비·병목 자원의 월별 필요시간과 가용시간, 부하율을 개략 검토",
    "CRP": "능력소요계획 CRP. 작업장·공정·작업지시별 준비시간, 가공시간, 부하와 가용능력을 주·일 단위로 상세 계산",
    "MES": "제조실행 MES, 현장 실적. 생산일지, 작업일보, 양품·불량 수량, 작업자, 설비 가동·정지 시간, 가동률, LOT 추적, 검사 결과",
    "ERP": "ERP 기준정보와 거래 내역. 품목 마스터, 거래처, 공급사, 수주, 발주, 입고, 재고 현황, 단가, 금액",
    doctype.UNKNOWN: "제조 계획과 무관한 문서. 인사 명부, 근태, 회의록, 설문, 교육 일정, 차량 운행, 에너지 사용, 연락망, 안전 점검, 사무용품",
}
plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "figure.facecolor": SURF, "axes.facecolor": SURF,
                     "savefig.facecolor": SURF, "text.color": INK, "axes.edgecolor": GRID, "xtick.color": MUTED, "ytick.color": MUTED})


def clean(ax, grid_axis="x"):
    for side in ("top", "right", "left" if grid_axis == "x" else "top"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def compute():
    items = json.loads((ee.SAMPLES / "labels.json").read_text(encoding="utf-8"))["files"]
    sheets = [sf.read_sheets(ee.SAMPLES / "inbox" / it["file"]) for it in items]
    saved = doctype.KEYWORDS, doctype.EXACT
    doctype.KEYWORDS, doctype.EXACT = ee.legacy_rules()
    legacy = [doctype.classify_workbook(s) for s in sheets]
    term_cache: dict[str, str] = {}

    def dict_hit(term: str) -> str:
        """이 낱말 하나가 (이전) 사전에서 어느 종류의 단서로 잡히는가. 없으면 빈 문자열."""
        if term not in term_cache:
            scores, _ = doctype.score_texts([term])
            best = max(scores.items(), key=lambda kv: kv[1])
            term_cache[term] = best[0] if best[1] > 0 else ""
        return term_cache[term]

    terms = [de.workbook_terms(s) for s in sheets]
    hits = [[dict_hit(t) for t in ts] for ts in terms]
    doctype.KEYWORDS, doctype.EXACT = saved

    matcher = de.SemanticMatcher()
    semantic = [matcher.classify(s) for s in sheets]
    links = []                                             # 파일별 [(낱말, 가장 가까운 기준 용어, 그 종류, 유사도)]
    for ts in terms:
        row = []
        for t, v in zip(ts, matcher._vectors(ts)):
            sims = matcher.concept_vectors @ v
            j = int(sims.argmax())
            row.append((t, matcher.concepts[j][1], matcher.concepts[j][0], float(sims[j])))
        links.append(row)
    desc_vectors = matcher.embedder.encode([DESCRIPTIONS[label] for label in LABELS])
    whole = matcher.embedder.encode([" | ".join(ts) for ts in terms]) @ desc_vectors.T
    return {"items": items, "sheets": sheets, "legacy": legacy, "semantic": semantic, "terms": terms, "hits": hits, "links": links, "whole": whole}


def pick_example(d) -> int:
    """사전은 모르겠다고 넘겼지만 뜻으로는 맞힌 실제 파일 하나 (국내 생산 현장 서식을 먼저 찾는다)."""
    def ok(i, templates):
        it, v, s = d["items"][i], d["legacy"][i], d["semantic"][i]
        return it["split"] == "test" and it["template"] in templates and not v.needs_review and v.category == doctype.UNKNOWN and s.category == it["category"]
    for templates in (("mes_kr_weekly_status",), ("mes_kr_defects", "mes_kr_daily_log"), tuple({it["template"] for it in d["items"]})):
        for i in range(len(d["items"])):
            if ok(i, templates):
                return i
    raise SystemExit("예시로 쓸 파일을 찾지 못했다")


def snapshot(sheets, max_rows=8, max_cols=8):
    name, rows = max(sheets, key=lambda s: sum(1 for r in s[1] for c in r if str(c).strip()))
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    first = min((j for r in rows for j, c in enumerate(r) if str(c).strip()), default=0)
    out = []
    for r in rows[:max_rows]:
        cells = [str(c).strip() for c in r[first:first + max_cols]]
        out.append([(c[:10] + "…") if len(c) > 11 else c for c in cells] + [""] * (max_cols - len(cells)))
    return name, out


def text_width(s: str) -> float:
    return sum(1.0 if ord(ch) > 0x2E80 else 0.56 for ch in s)


def fig_walkthrough(d, i):
    it, verdict, sem = d["items"][i], d["legacy"][i], d["semantic"][i]
    fig = plt.figure(figsize=(15, 12.2))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.05], hspace=0.3, wspace=0.24, left=0.085, right=0.975, top=0.9, bottom=0.085)

    # ① 실제 엑셀
    ax = fig.add_subplot(gs[0, 0])
    ax.axis("off")
    ax.set_title("① 실제 엑셀 파일 (앞부분)", loc="left", fontsize=15, fontweight="bold", pad=10)
    _, cells = snapshot(d["sheets"][i])
    t = ax.table(cellText=cells, loc="upper center", cellLoc="center", bbox=[0, 0.08, 1, 0.9])
    t.auto_set_font_size(False)
    t.set_fontsize(9.5)
    for cell in t.get_celld().values():
        cell.set_edgecolor(GRID)
        cell.set_facecolor("white")
    ax.text(0, 0.0, f"파일명: {it['file']}   (파일명은 판단에 쓰지 않는다)", fontsize=10.5, color=MUTED, transform=ax.transAxes)

    # ② 낱말 뽑기 + 사전 대조
    ax = fig.add_subplot(gs[0, 1])
    ax.axis("off")
    ax.set_xlim(0, 60)
    ax.set_ylim(0, 20)
    ax.set_title("② 낱말을 뽑아 사전과 대조", loc="left", fontsize=15, fontweight="bold", pad=10)
    x, y = 0.0, 18.2
    shown = [(t_, h) for t_, h in zip(d["terms"][i], d["hits"][i]) if len(t_) <= 14][:26]
    for term, hit in shown:
        w = text_width(term) * 1.52 + 2.2
        if x + w > 60:
            x, y = 0.0, y - 2.5
        ax.text(x + w / 2, y, term, ha="center", va="center", fontsize=11, color="white" if hit else INK2,
                bbox={"boxstyle": "round,pad=0.38", "facecolor": BLUE if hit else "white", "edgecolor": BLUE if hit else NEUTRAL, "linewidth": 1.1})
        x += w + 1.2
    n_hit = sum(1 for _, h in shown if h)
    ax.text(0, 4.4, f"파란 칸 = 사전에 있는 낱말 ({n_hit}개)      흰 칸 = 사전에 없는 낱말 ({len(shown) - n_hit}개)", fontsize=11.5, color=INK2)
    top_cat = max(verdict.scores, key=verdict.scores.get) if verdict.score else "없음"
    ax.text(0, 2.2, f"사전이 찾은 단서: {top_cat} {verdict.score:.1f}점  <  필요한 점수 {doctype.MIN_SCORE:.1f}점", fontsize=13, color=INK)
    ax.text(0, 0.2, "→ 사전만으로는 \"모르겠다\"고 넘긴다", fontsize=13.5, fontweight="bold", color=CRITICAL)

    # ③ 뜻이 가까운 기준 용어 찾기
    ax = fig.add_subplot(gs[1, 0])
    rows = sorted({(t_, c, cat, s) for t_, c, cat, s in d["links"][i] if len(t_) <= 14}, key=lambda r: -r[3])
    keep = [r for r in rows if r[3] >= de.TAU][:8] + [r for r in rows if r[3] < de.TAU][:4]
    keep = keep[::-1]
    for row, (term, concept, cat, sim) in enumerate(keep):
        passed = sim >= de.TAU
        ax.barh(row, sim, height=0.62, color=BLUE if passed else NEUTRAL, edgecolor=SURF, linewidth=2)
        ax.text(sim + 0.012, row, f"{sim:.2f}", va="center", fontsize=11, color=INK if passed else MUTED)
        kind = "일반 사무 용어" if cat == doctype.UNKNOWN else cat
        ax.text(0.012, row, f"→ {concept}  ({kind})", va="center", fontsize=10.5, color="white" if passed else INK2)
    ax.set_yticks(range(len(keep)), [r[0] for r in keep], fontsize=12, color=INK)
    ax.axvline(de.TAU, color=INK, linewidth=1.4, linestyle="--")
    ax.text(de.TAU + 0.012, -0.72, f"기준 {de.TAU}: 이보다 낮으면 버린다", fontsize=10.5, color=INK, va="center")
    ax.set_ylim(-1.15, len(keep) - 0.45)
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("뜻이 가까운 정도 (1에 가까울수록 같은 뜻)", fontsize=11, color=INK2)
    clean(ax)
    ax.set_title("③ 사전에 없는 낱말도 뜻이 가까운 용어에 연결한다", loc="left", fontsize=15, fontweight="bold", pad=10)

    # ④ 점수 합산과 결정
    ax = fig.add_subplot(gs[1, 1])
    scores = [sem.scores.get(label, 0.0) for label in LABELS]
    order = sorted(range(len(LABELS)), key=lambda k: scores[k])
    top = max(range(len(LABELS)), key=lambda k: scores[k])
    for row, k in enumerate(order):
        ax.barh(row, scores[k], height=0.62, color=BLUE if k == top else NEUTRAL, edgecolor=SURF, linewidth=2)
        ax.text(scores[k] + 0.04, row, f"{scores[k]:.1f}", va="center", fontsize=12, fontweight="bold" if k == top else "normal", color=INK if k == top else MUTED)
    ax.set_yticks(range(len(order)), [LABELS[k] for k in order], fontsize=12.5, color=INK)
    ax.axvline(de.MIN_SCORE, color=INK, linewidth=1.4, linestyle="--")
    ax.text(de.MIN_SCORE + 0.06, -0.72, f"필요한 점수 {de.MIN_SCORE}", fontsize=10.5, color=INK, va="center")
    ax.set_ylim(-1.15, len(order) - 0.45)
    ax.set_xlim(0, max(scores) * 1.25 + 0.5)
    ax.set_xlabel("종류별 점수 (기준을 넘긴 낱말들의 유사도 합)", fontsize=11, color=INK2)
    clean(ax)
    ax.set_title(f"④ 종류별로 점수를 더한다  →  {LABELS[top]} 로 분류 (정답)", loc="left", fontsize=15, fontweight="bold", pad=10)

    fig.suptitle("실제 엑셀 한 개가 분류되는 과정", x=0.085, y=0.965, ha="left", fontsize=22, fontweight="bold")
    fig.text(0.085, 0.012, "더미 v2 의 실제 파일과 실제 계산값. ②의 사전은 이 양식을 보기 전의 사전이다. 합성 자료이며 실제 기업 파일이 아니다.", fontsize=10.5, color=MUTED)
    fig.savefig(FIG / "p1_walkthrough.png", dpi=140)
    plt.close(fig)
    return {"file": it["file"], "category": it["category"], "template": it["template"], "rule_score": verdict.score, "semantic_scores": sem.scores,
            "links_shown": [(a, b, c, round(s, 3)) for a, b, c, s in keep[::-1]]}


def fig_why_terms(d, i):
    it, sem = d["items"][i], d["semantic"][i]
    whole = d["whole"][i]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.6))
    for ax, values, title, fmt in ((axes[0], list(whole), "파일을 통째로 한 문장으로 비교하면", "{:.2f}"),
                                   (axes[1], [sem.scores.get(label, 0.0) for label in LABELS], "낱말 하나하나를 따로 비교하면", "{:.1f}")):
        order = sorted(range(len(LABELS)), key=lambda k: values[k])
        top, second = order[-1], order[-2]
        for row, k in enumerate(order):
            ax.barh(row, values[k], height=0.62, color=BLUE if k == top else NEUTRAL, edgecolor=SURF, linewidth=2)
            ax.text(values[k] + max(values) * 0.015, row, fmt.format(values[k]), va="center", fontsize=12, color=INK if k == top else MUTED,
                    fontweight="bold" if k == top else "normal")
        ax.set_yticks(range(len(order)), [LABELS[k] + ("  ← 정답" if LABELS[k] == it["category"] else "") for k in order], fontsize=12.5, color=INK)
        ax.set_xlim(0, max(values) * 1.2)
        clean(ax)
        gap = values[top] - values[second]
        ratio = gap / values[top] if values[top] else 0.0
        ax.set_title(f"{title}\n1등과 2등의 차이가 1등 점수의 {ratio:.0%}", loc="left", fontsize=14.5, fontweight="bold", pad=10)
    axes[0].set_xlabel("범주 설명 문장과의 유사도", fontsize=11, color=INK2)
    axes[1].set_xlabel("종류별 점수", fontsize=11, color=INK2)
    fig.suptitle("왜 낱말 단위인가: 같은 파일을 두 방식으로 비교", x=0.03, y=0.985, ha="left", fontsize=19, fontweight="bold")
    fig.text(0.03, 0.012, f"그림 1 과 같은 파일({it['file']}). 통째로 비교하면 모든 종류와 비슷하게 닮아 보여 고를 수 없고, 낱말 단위로 보면 한 종류가 뚜렷이 올라온다.",
             fontsize=10.5, color=MUTED)
    fig.subplots_adjust(left=0.1, right=0.97, top=0.78, bottom=0.14, wspace=0.34)
    fig.savefig(FIG / "p2_why_terms.png", dpi=140)
    plt.close(fig)
    # 전체 test 분할에서의 차이
    test = [k for k, x in enumerate(d["items"]) if x["split"] == "test"]

    def ratios(matrix):
        out = []
        for row in matrix:
            s = sorted(row, reverse=True)
            out.append((s[0] - s[1]) / s[0] if s[0] > 0 else 0.0)
        return out

    whole_ratio = ratios([list(d["whole"][k]) for k in test])
    term_ratio = ratios([[d["semantic"][k].scores.get(label, 0.0) for label in LABELS] for k in test])
    whole_top1 = sum(LABELS[int(np.argmax(d["whole"][k]))] == d["items"][k]["category"] for k in test)
    return {"whole_gap_ratio_median": float(np.median(whole_ratio)), "term_gap_ratio_median": float(np.median(term_ratio)),
            "whole_top1_correct": int(whole_top1), "n_test": len(test)}


def fig_threshold(d):
    test = [k for k, x in enumerate(d["items"]) if x["split"] == "test"]
    right, wrong = [], []
    for k in test:
        truth = d["items"][k]["category"]
        for _, _, cat, sim in set(d["links"][k]):
            (right if cat == truth else wrong).append(sim)
    bins = np.linspace(0.3, 1.0, 36)
    fig, ax = plt.subplots(figsize=(15, 5.4))
    ax.hist(wrong, bins=bins, color=NEUTRAL, alpha=0.9, label=f"틀린 종류의 기준 용어에 연결됨 ({len(wrong):,}개)", edgecolor=SURF, linewidth=1)
    ax.hist(right, bins=bins, color=BLUE, alpha=0.78, label=f"맞는 종류의 기준 용어에 연결됨 ({len(right):,}개)", edgecolor=SURF, linewidth=1)
    ax.axvline(de.TAU, color=INK, linewidth=1.6, linestyle="--")
    r_keep, w_keep = sum(s >= de.TAU for s in right), sum(s >= de.TAU for s in wrong)
    top = ax.get_ylim()[1]
    ax.text(de.TAU + 0.008, top * 0.97, f"기준 {de.TAU} 이상만 단서로 쓴다", fontsize=12.5, color=INK, va="top", fontweight="bold")
    ax.text(de.TAU + 0.008, top * 0.87, f"남는 연결 {r_keep + w_keep:,}개 중 {r_keep / (r_keep + w_keep):.0%} 가 맞는 종류", fontsize=12.5, color=INK, va="top")
    ax.text(0.305, top * 0.97, f"기준보다 낮은 연결 {len(right) + len(wrong) - r_keep - w_keep:,}개 중\n{(len(wrong) - w_keep) / (len(right) + len(wrong) - r_keep - w_keep):.0%} 가 엉뚱한 종류 → 버린다",
            fontsize=12.5, color=INK2, va="top", ha="left")
    ax.set_xlabel("낱말과 가장 가까운 기준 용어의 유사도", fontsize=11.5, color=INK2)
    ax.set_ylabel("낱말 수", fontsize=11.5, color=INK2)
    ax.legend(loc="center right", frameon=False, fontsize=12)
    clean(ax, "y")
    ax.set_title("왜 기준이 0.65 인가: 그보다 덜 닮은 낱말은 대부분 엉뚱한 종류에 연결된다", loc="left", fontsize=17, fontweight="bold", pad=12)
    fig.text(0.03, 0.012, "파일 109개의 모든 낱말. 기준을 넘어도 낱말 하나만으로는 절반쯤 틀린다. 그래서 낱말 하나로 정하지 않고 여러 낱말의 점수를 더한 뒤 1등과 2등의 차이를 본다.",
             fontsize=10.5, color=MUTED)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.88, bottom=0.15)
    fig.savefig(FIG / "p3_threshold.png", dpi=140)
    plt.close(fig)
    return {"right_total": len(right), "wrong_total": len(wrong), "right_kept": r_keep, "wrong_kept": w_keep}


def fig_why_combine(d):
    test = [k for k, x in enumerate(d["items"]) if x["split"] == "test"]
    undecided = (doctype.UNKNOWN, de.REVIEW)
    groups = collections.OrderedDict((name, collections.Counter()) for name in ("둘이 같은 답", "사전만 답함", "뜻만 답함", "둘이 다른 답"))
    for k in test:
        truth = d["items"][k]["category"]
        v, s = d["legacy"][k], d["semantic"][k]
        rule = de.REVIEW if v.needs_review else v.category
        sem = de.REVIEW if s.category is None else s.category
        if truth == doctype.UNKNOWN:
            continue                                        # 일곱 종류 중 하나가 정답인 파일만 본다
        r_dec, s_dec = rule not in undecided, sem not in undecided
        if r_dec and s_dec and rule == sem:
            groups["둘이 같은 답"]["맞음" if rule == truth else "틀림"] += 1
        elif r_dec and s_dec:
            groups["둘이 다른 답"]["사전이 맞음" if rule == truth else "뜻이 맞음" if sem == truth else "둘 다 틀림"] += 1
        elif r_dec:
            groups["사전만 답함"]["맞음" if rule == truth else "틀림"] += 1
        elif s_dec:
            groups["뜻만 답함"]["맞음" if sem == truth else "틀림"] += 1
    fig, ax = plt.subplots(figsize=(15, 5.2))
    colors = {"맞음": BLUE, "틀림": CRITICAL, "사전이 맞음": YELLOW, "뜻이 맞음": "#f6cf73", "둘 다 틀림": CRITICAL}
    notes = {"둘이 같은 답": "그대로 분류", "사전만 답함": "사전의 답으로 분류", "뜻만 답함": "뜻의 답으로 분류", "둘이 다른 답": "어느 쪽이 맞는지 알 수 없다 → 사람에게 확인 요청"}
    names = list(groups)[::-1]
    for row, name in enumerate(names):
        left = 0
        for key in ("맞음", "사전이 맞음", "뜻이 맞음", "틀림", "둘 다 틀림"):
            n = groups[name].get(key, 0)
            if not n:
                continue
            ax.barh(row, n, left=left, height=0.6, color=colors[key], edgecolor=SURF, linewidth=2)
            if n >= 6:
                ax.text(left + n / 2, row, f"{key} {n}", ha="center", va="center", fontsize=11.5, color="white" if colors[key] in (BLUE, CRITICAL) else INK)
            left += n
        total = sum(groups[name].values())
        detail = ", ".join(f"{key} {n}" for key, n in groups[name].items())
        ax.text(left + 1, row, f"{total}개 ({detail})   {notes[name]}", va="center", fontsize=12.5, color=INK)
    ax.set_yticks(range(len(names)), names, fontsize=13.5, color=INK)
    ax.set_xlim(0, max(sum(g.values()) for g in groups.values()) * 1.9)
    ax.set_xlabel("파일 수", fontsize=11.5, color=INK2)
    clean(ax)
    ax.set_title("왜 두 방법을 합치는가: 둘이 같은 답을 내면 전부 맞았고, 다른 답을 내면 한쪽은 반드시 틀렸다", loc="left", fontsize=17, fontweight="bold", pad=12)
    fig.text(0.03, 0.012, "test 분할에서 일곱 종류 중 하나가 정답인 파일. 사전은 이 양식을 보기 전의 사전. 두 방법 모두 답하지 못한 파일은 뺐다.", fontsize=10.5, color=MUTED)
    fig.subplots_adjust(left=0.1, right=0.98, top=0.87, bottom=0.16)
    fig.savefig(FIG / "p4_why_combine.png", dpi=140)
    plt.close(fig)
    return {name: dict(c) for name, c in groups.items()}


def main() -> None:
    FIG.mkdir(exist_ok=True)
    d = compute()
    i = pick_example(d)
    numbers = {"example": fig_walkthrough(d, i), "why_terms": fig_why_terms(d, i), "threshold": fig_threshold(d), "combine": fig_why_combine(d)}
    (FIG / "principle_numbers.json").write_text(json.dumps(numbers, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(numbers, ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main()
