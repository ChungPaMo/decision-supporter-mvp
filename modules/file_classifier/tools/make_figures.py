"""README 에 넣는 결과 그림을 만든다. GPU 권장. torch, transformers, openpyxl, matplotlib 필요.

    python -X utf8 modules/file_classifier/tools/make_figures.py

그림은 modules/file_classifier/figures/ 에, 그림에 쓴 숫자는 figures/numbers.json 에 저장한다.
모든 숫자는 더미 v2 의 test 분할(규칙을 고칠 때 보지 않은 109개) 기준이고, "이전"은 v2 를 보기 전의 낱말 사전(legacy)이다.
즉 "분류기가 처음 보는 형태의 엑셀"에서의 결과다. 합성 자료이며 실제 기업 파일로 잰 값이 아니다.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

import matplotlib

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
BLUE, YELLOW, NEUTRAL, CRITICAL = "#2a78d6", "#eda100", "#c3c2b7", "#d03b3b"
OUTCOMES = [("ok", "맞게 분류", BLUE), ("review", "사람에게 확인 요청", YELLOW), ("missed", "모르겠다고 넘김", NEUTRAL), ("wrong", "틀리게 분류", CRITICAL)]
# 예전에 시험했다가 뺀 방식의 test 분할 정답률 (코드는 지웠고 값만 남겼다)
DROPPED = {"파일을 통째로 비교": 28 / 109, "정답 예시 파일과 비교": 5 / 109}
plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "figure.facecolor": SURF, "axes.facecolor": SURF,
                     "savefig.facecolor": SURF, "text.color": INK, "axes.edgecolor": GRID, "xtick.color": MUTED, "ytick.color": MUTED})


def measure():
    items = json.loads((ee.SAMPLES / "labels.json").read_text(encoding="utf-8"))["files"]
    sheets = [sf.read_sheets(ee.SAMPLES / "inbox" / it["file"]) for it in items]
    saved = doctype.KEYWORDS, doctype.EXACT
    doctype.KEYWORDS, doctype.EXACT = ee.legacy_rules()
    legacy = [doctype.classify_workbook(s) for s in sheets]
    doctype.KEYWORDS, doctype.EXACT = saved
    matcher = de.SemanticMatcher()
    semantic = [matcher.classify(s) for s in sheets]
    preds = {"before": [de.REVIEW if v.needs_review else v.category for v in legacy],
             "semantic": [de.REVIEW if s.category is None else s.category for s in semantic],
             "after": [de.combine(v, s)[0] for v, s in zip(legacy, semantic)]}
    test = [i for i, it in enumerate(items) if it["split"] == "test"]
    out = {"n": len(test), "by_category": {}}
    for name, p in preds.items():
        out[name] = dict(collections.Counter(ee.outcome(p[i], items[i]["category"]) for i in test))
        for k, _, _ in OUTCOMES:
            out[name].setdefault(k, 0)
    for cat in list(doctype.CATEGORIES) + [doctype.UNKNOWN]:
        idx = [i for i in test if items[i]["category"] == cat]
        out["by_category"][cat] = {"n": len(idx), "before": sum(preds["before"][i] == cat for i in idx), "after": sum(preds["after"][i] == cat for i in idx)}
    return out


def per_hundred(counts: dict, n: int) -> dict:
    """합이 100 이 되도록 반올림한다 (나머지가 큰 순서로 1씩 더한다)."""
    raw = {k: counts[k] * 100 / n for k, _, _ in OUTCOMES}
    base = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - base[k], reverse=True)[:100 - sum(base.values())]:
        base[k] += 1
    return base


def fig_waffle(m):
    fig, axes = plt.subplots(1, 2, figsize=(13, 7.4))
    for ax, key, title in zip(axes, ("before", "after"), ("이전: 낱말 사전만", "지금: 사전 + 뜻으로 판단")):
        cells = per_hundred(m[key], m["n"])
        colors = [c for k, _, c in OUTCOMES for _ in range(cells[k])]
        for i, color in enumerate(colors):
            x, y = i % 10, 9 - i // 10
            ax.add_patch(FancyBboxPatch((x + 0.08, y + 0.08), 0.84, 0.84, boxstyle="round,pad=0,rounding_size=0.16", linewidth=0, facecolor=color))
        ax.set_xlim(0, 10)
        ax.set_ylim(-0.2, 12.6)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.text(0, 12.1, title, fontsize=17, color=INK2, va="center")
        ax.text(0, 10.9, f"{cells['ok']}", fontsize=58, fontweight="bold", color=INK, va="center")
        ax.text(2.55 if cells["ok"] >= 10 else 1.4, 10.75, "개를 맞게 분류", fontsize=20, color=INK, va="center")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in OUTCOMES]
    fig.legend(handles, [name for _, name, _ in OUTCOMES], loc="lower center", ncol=4, frameon=False, fontsize=14, bbox_to_anchor=(0.5, 0.045))
    fig.suptitle("처음 보는 엑셀 100개를 넣으면", x=0.5, y=0.975, fontsize=24, fontweight="bold")
    fig.text(0.5, 0.012, f"네모 1개 = 파일 1개. 분류기가 본 적 없는 형태의 합성 엑셀 {m['n']}개 결과를 100개 기준으로 환산. 실제 기업 파일로 잰 값은 아님.",
             ha="center", fontsize=10.5, color=MUTED)
    fig.subplots_adjust(left=0.05, right=0.95, top=0.93, bottom=0.11, wspace=0.12)
    fig.savefig(FIG / "1_waffle.png", dpi=150)
    plt.close(fig)


def fig_tiles(m):
    b, a, n = m["before"], m["after"], m["n"]
    tiles = [("맞게 분류한 비율", f"{b['ok'] / n:.0%}", f"{a['ok'] / n:.0%}", "높을수록 좋음", BLUE),
             ("모르겠다고 넘긴 파일", f"{b['missed']}건", f"{a['missed']}건", "적을수록 좋음", INK2),
             ("틀리게 분류한 파일", f"{b['wrong']}건", f"{a['wrong']}건", "적을수록 좋음", CRITICAL)]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.3))
    for ax, (title, before, after, hint, color) in zip(axes, tiles):
        ax.axis("off")
        ax.add_patch(FancyBboxPatch((0.02, 0.04), 0.96, 0.92, boxstyle="round,pad=0,rounding_size=0.05", linewidth=1.2, edgecolor=GRID, facecolor="white",
                                    transform=ax.transAxes))
        ax.text(0.5, 0.83, title, ha="center", va="center", fontsize=17, color=INK2, transform=ax.transAxes)
        ax.text(0.24, 0.47, before, ha="center", va="center", fontsize=34, color=MUTED, transform=ax.transAxes)
        ax.text(0.47, 0.47, "→", ha="center", va="center", fontsize=30, color=MUTED, transform=ax.transAxes)
        ax.text(0.74, 0.47, after, ha="center", va="center", fontsize=50, fontweight="bold", color=color, transform=ax.transAxes)
        ax.text(0.24, 0.2, "이전", ha="center", fontsize=12, color=MUTED, transform=ax.transAxes)
        ax.text(0.74, 0.2, "지금", ha="center", fontsize=12, color=INK2, transform=ax.transAxes)
        ax.text(0.5, 0.09, hint, ha="center", fontsize=10.5, color=MUTED, transform=ax.transAxes)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.97, bottom=0.03, wspace=0.06)
    fig.savefig(FIG / "2_before_after.png", dpi=150)
    plt.close(fig)


def fig_by_category(m):
    cats = list(m["by_category"])
    before = [m["by_category"][c]["before"] / m["by_category"][c]["n"] for c in cats]
    after = [m["by_category"][c]["after"] / m["by_category"][c]["n"] for c in cats]
    order = sorted(range(len(cats)), key=lambda i: after[i] - before[i])
    fig, ax = plt.subplots(figsize=(13, 5.6))
    for row, i in enumerate(order):
        ax.plot([before[i], after[i]], [row, row], color=GRID, linewidth=5, solid_capstyle="round", zorder=1)
        ax.scatter([before[i]], [row], s=170, color=NEUTRAL, edgecolors=SURF, linewidths=2, zorder=2)
        ax.scatter([after[i]], [row], s=230, color=BLUE, edgecolors=SURF, linewidths=2, zorder=3)
        gain = after[i] - before[i]
        ax.text(1.06, row, f"{before[i]:.0%} → {after[i]:.0%}" + (f"  (+{gain * 100:.0f}%p)" if gain > 0.005 else ""), va="center", fontsize=13,
                color=INK if gain > 0.005 else MUTED)
    ax.set_yticks(range(len(order)), [f"{cats[i]}  ({m['by_category'][cats[i]]['n']}개)" for i in order], fontsize=14, color=INK)
    ax.set_xlim(-0.03, 1.42)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0], ["0%", "25%", "50%", "75%", "100%"], fontsize=11)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.scatter([], [], s=120, color=NEUTRAL, label="이전: 낱말 사전만")
    ax.scatter([], [], s=150, color=BLUE, label="지금: 사전 + 뜻으로 판단")
    handles, names = ax.get_legend_handles_labels()
    fig.legend(handles, names, loc="lower right", ncol=2, frameon=False, fontsize=12.5, bbox_to_anchor=(0.985, 0.0))
    ax.set_title("문서 종류별로 맞게 분류한 비율: 약하던 종류가 가장 많이 올랐다", loc="left", fontsize=17, fontweight="bold", pad=14)
    fig.text(0.012, 0.012, "처음 보는 형태의 합성 엑셀(test 분할) 기준. 종류별 파일 수가 적어 값 하나하나는 크게 흔들릴 수 있음.", fontsize=10.5, color=MUTED)
    fig.subplots_adjust(left=0.13, right=0.98, top=0.88, bottom=0.12)
    fig.savefig(FIG / "3_by_category.png", dpi=150)
    plt.close(fig)


def fig_methods(m):
    n = m["n"]
    rows = [("정답 예시 파일과 비교", DROPPED["정답 예시 파일과 비교"], NEUTRAL, "효과 없음"), ("파일을 통째로 비교", DROPPED["파일을 통째로 비교"], NEUTRAL, "효과 없음"),
            ("낱말 사전만 (이전)", m["before"]["ok"] / n, NEUTRAL, ""), ("낱말의 뜻만", m["semantic"]["ok"] / n, "#9ec5f4", ""),
            ("사전 + 낱말의 뜻 (지금)", m["after"]["ok"] / n, BLUE, "채택")]
    fig, ax = plt.subplots(figsize=(13, 4.8))
    for y, (name, value, color, note) in enumerate(rows):
        ax.barh(y, value, height=0.62, color=color, edgecolor=SURF, linewidth=2)
        ax.text(value + 0.012, y, f"{value:.0%}" + (f"   {note}" if note else ""), va="center", fontsize=15, fontweight="bold" if color == BLUE else "normal",
                color=INK if color != NEUTRAL or not note else MUTED)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows], fontsize=14, color=INK)
    ax.set_xlim(0, 1.12)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0], ["0%", "25%", "50%", "75%", "100%"], fontsize=11)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("시도한 방식별로 맞게 분류한 비율", loc="left", fontsize=17, fontweight="bold", pad=14)
    fig.text(0.012, 0.012, "처음 보는 형태의 합성 엑셀(test 분할) 기준.", fontsize=10.5, color=MUTED)
    fig.subplots_adjust(left=0.2, right=0.98, top=0.87, bottom=0.13)
    fig.savefig(FIG / "4_methods.png", dpi=150)
    plt.close(fig)


def main() -> None:
    FIG.mkdir(exist_ok=True)
    m = measure()
    (FIG / "numbers.json").write_text(json.dumps({**m, "dropped_methods": DROPPED}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    fig_waffle(m), fig_tiles(m), fig_by_category(m), fig_methods(m)
    print(json.dumps(m, ensure_ascii=False))


if __name__ == "__main__":
    main()
