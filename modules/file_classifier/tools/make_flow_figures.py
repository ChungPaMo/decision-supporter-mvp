"""엑셀 여러 개가 분류되는 과정을 실제 파일 그림으로 보여 주는 단계별 이미지를 만든다 (발표용, 16:9).

    python -X utf8 modules/file_classifier/tools/make_flow_figures.py

GPU 권장. torch, transformers, openpyxl, matplotlib 필요. 그림은 modules/file_classifier/figures/flow/ 에 저장한다.
    f1_pile.png      종류 표시 없이 섞여 있는 엑셀 200개
    f2_sheet.png     그중 실제 파일 한 개 (엑셀 화면처럼 그림)
    f3_read.png      분류기가 읽는 칸
    f4_dict.png      사전이 아는 낱말과 모르는 낱말
    f5_meaning.png   모르는 낱말을 뜻이 가까운 용어에 연결
    f6_score.png     종류별 점수와 결정
    f7_sorted.png    200개가 나뉜 결과

모든 내용은 더미 v2 의 실제 파일과 실제 계산값이다. f4 의 사전은 이 양식을 보기 전의 사전(legacy)이다.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import random
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "modules" / "file_classifier" / "tools"), str(ROOT / "modules" / "file_classifier" / "src"), str(ROOT)]

import eval_embed as ee  # noqa: E402
import make_principle_figures as mp  # noqa: E402
from file_classifier import doctype, doctype_embed as de  # noqa: E402

OUT = ROOT / "modules" / "file_classifier" / "figures" / "flow"
INK, INK2, MUTED, GRID, SURF = "#1B2A4A", "#3D4A63", "#8A93A6", "#D6DCE8", "#FDFDFC"
TEAL, TEAL_SOFT, AMBER, AMBER_SOFT, GRAY, HEAD = "#2456A6", "#DCE7F7", "#C2410C", "#FCE6CF", "#C8CFDB", "#EEF2F8"
plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "figure.facecolor": SURF, "savefig.facecolor": SURF, "text.color": INK})
N_ROWS, N_COLS, CW, RH = 10, 9, 2.05, 1.14


def canvas():
    fig = plt.figure(figsize=(16, 7.6))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 32)
    ax.set_ylim(0, 15.2)
    ax.axis("off")
    return fig, ax


def save(fig, name):
    fig.savefig(OUT / name, dpi=120)
    plt.close(fig)


def load_grid(path):
    """실제 엑셀에서 표가 있는 시트의 왼쪽 위 N_ROWS x N_COLS 칸을 읽는다."""
    wb = load_workbook(path)
    ws = max(wb.worksheets, key=lambda s: s.max_row * s.max_column if s.max_row > 1 else 0)
    r0, c0 = ws.min_row, ws.min_column
    grid = {}
    for r in range(N_ROWS):
        for c in range(N_COLS):
            v = ws.cell(row=r0 + r, column=c0 + c).value
            if isinstance(v, (dt.datetime, dt.date)):
                v = v.strftime("%Y-%m-%d")
            grid[(r, c)] = "" if v is None else str(v)
    return grid, r0, c0


def draw_sheet(ax, grid, r0, c0, x0, y_top, style):
    """엑셀 화면처럼 그린다. style(r, c, value) -> (칸 색, 글자 색, 테두리 색, 굵게)."""
    for c in range(N_COLS):
        ax.add_patch(Rectangle((x0 + 0.9 + c * CW, y_top), CW, 0.62, facecolor=HEAD, edgecolor=GRID, linewidth=0.8))
        ax.text(x0 + 0.9 + c * CW + CW / 2, y_top + 0.31, chr(ord("A") + c0 - 1 + c), ha="center", va="center", fontsize=10, color=MUTED)
    for r in range(N_ROWS):
        y = y_top - (r + 1) * RH
        ax.add_patch(Rectangle((x0, y), 0.9, RH, facecolor=HEAD, edgecolor=GRID, linewidth=0.8))
        ax.text(x0 + 0.45, y + RH / 2, str(r0 + r), ha="center", va="center", fontsize=10, color=MUTED)
        for c in range(N_COLS):
            value = grid[(r, c)]
            face, color, edge, bold = style(r, c, value)
            ax.add_patch(Rectangle((x0 + 0.9 + c * CW, y), CW, RH, facecolor=face, edgecolor=edge, linewidth=1.6 if edge != GRID else 0.8,
                                   zorder=3 if edge != GRID else 2))
            shown = value if mp.text_width(value) <= 9.5 else value[:8] + "…"
            ax.text(x0 + 0.9 + c * CW + CW / 2, y + RH / 2, shown, ha="center", va="center", fontsize=11, color=color,
                    fontweight="bold" if bold else "normal", zorder=4)


def chip(ax, x, y, text, face, color, edge=None, size=13, bold=False, w=None):
    w = w or mp.text_width(text) * 0.4 * size / 13 + 0.9
    ax.add_patch(FancyBboxPatch((x, y - 0.42), w, 0.84, boxstyle="round,pad=0,rounding_size=0.2", facecolor=face, edgecolor=edge or face, linewidth=1.4, zorder=5))
    ax.text(x + w / 2, y, text, ha="center", va="center", fontsize=size, color=color, fontweight="bold" if bold else "normal", zorder=6)
    return w


def fig_pile(names):
    fig, ax = canvas()
    rng = random.Random(3)
    cols, rows = 25, 8
    tiles = []
    for k in range(200):
        x = 1.0 + (k % cols) * 1.2 + rng.uniform(-0.08, 0.08)
        y = 12.6 - (k // cols) * 1.25 + rng.uniform(-0.08, 0.08)
        tiles.append((x, y))
        ax.add_patch(FancyBboxPatch((x, y), 0.86, 0.98, boxstyle="round,pad=0,rounding_size=0.1", facecolor=GRAY, edgecolor=SURF, linewidth=1.2))
        ax.plot([x + 0.18, x + 0.68], [y + 0.66, y + 0.66], color=SURF, linewidth=1.4)
        ax.plot([x + 0.18, x + 0.68], [y + 0.46, y + 0.46], color=SURF, linewidth=1.4)
        ax.plot([x + 0.18, x + 0.5], [y + 0.26, y + 0.26], color=SURF, linewidth=1.4)
    x = 1.0
    for name in names[:9]:
        w = chip(ax, x, 1.7, name, "white", INK, edge=GRID, size=13)
        x += w + 0.35
    ax.text(1.0, 2.75, "실제 파일명 예시", fontsize=12.5, color=MUTED)
    ax.text(31.0, 1.7, "… 총 200건", fontsize=14, color=MUTED, ha="right", va="center")
    save(fig, "f1_pile.png")


def fig_sheet(grid, r0, c0, name):
    fig, ax = canvas()
    draw_sheet(ax, grid, r0, c0, 6.2, 12.6, lambda r, c, v: ("white", INK, GRID, False))
    chip(ax, 6.2, 14.2, name, "white", INK, edge=GRID, size=14, bold=True)
    save(fig, "f2_sheet.png")


def fig_read(grid, r0, c0, terms):
    fig, ax = canvas()

    def style(r, c, v):
        if v and v in terms:
            return AMBER_SOFT, INK, AMBER, True
        return "white", GRAY, GRID, False

    draw_sheet(ax, grid, r0, c0, 6.2, 12.6, style)
    chip(ax, 6.2, 14.2, "주황 칸 = 판독 대상 (제목 · 열 이름 · 항목 이름)", AMBER_SOFT, INK, edge=AMBER, size=13.5, bold=True)
    chip(ax, 19.6, 14.2, "흐린 칸 = 판독 제외 (숫자 · 값)", "white", MUTED, edge=GRID, size=13.5)
    save(fig, "f3_read.png")


def fig_dict(grid, r0, c0, terms, hits, verdict):
    fig, ax = canvas()
    known = {t for t, h in zip(terms, hits) if h}

    def style(r, c, v):
        if v and v in known:
            return TEAL, "white", TEAL, True
        if v and v in terms:
            return "white", INK2, AMBER, False
        return "white", GRAY, GRID, False

    draw_sheet(ax, grid, r0, c0, 1.0, 12.6, style)
    chip(ax, 1.0, 14.2, f"파란 칸 = 사전 등록 낱말 ({len(known)}개)", TEAL, "white", size=13.5, bold=True)
    chip(ax, 9.0, 14.2, "주황 테두리 = 사전 미등록 낱말", "white", INK2, edge=AMBER, size=13.5)
    # 점수 게이지
    gx, gy, gw = 22.6, 8.4, 8.2
    need = doctype.MIN_SCORE
    scale = gw / (need * 1.35)
    ax.text(gx, gy + 2.5, "사전 단서 점수", fontsize=15, color=INK2)
    ax.add_patch(FancyBboxPatch((gx, gy), gw, 1.1, boxstyle="round,pad=0,rounding_size=0.25", facecolor=HEAD, edgecolor=HEAD))
    ax.add_patch(FancyBboxPatch((gx, gy), verdict.score * scale, 1.1, boxstyle="round,pad=0,rounding_size=0.25", facecolor=TEAL, edgecolor=TEAL))
    ax.plot([gx + need * scale] * 2, [gy - 0.35, gy + 1.45], color=INK, linewidth=2, linestyle="--")
    ax.text(gx + verdict.score * scale / 2, gy + 0.55, f"{verdict.score:.1f}점", ha="center", va="center", fontsize=15, color="white", fontweight="bold")
    ax.text(gx + need * scale, gy - 0.8, f"기준 점수 {need:.1f}", ha="center", fontsize=12.5, color=INK)
    ax.text(gx, gy - 3.0, "기준 점수 미달", fontsize=22, fontweight="bold", color=AMBER)
    ax.text(gx, gy - 4.2, "사전 단독으로는 판정 불가", fontsize=16, color=INK2)
    save(fig, "f4_dict.png")


def fig_meaning(links):
    fig, ax = canvas()
    rows = sorted({(t, c, cat, s) for t, c, cat, s in links if len(t) <= 12}, key=lambda r: -r[3])
    keep = [r for r in rows if r[3] >= de.TAU and r[2] != doctype.UNKNOWN][:7] + [r for r in rows if r[3] < de.TAU][:3]
    ax.text(3.0, 14.2, "엑셀 내 낱말", fontsize=16, color=INK2, fontweight="bold")
    ax.text(18.4, 14.2, "의미가 가장 가까운 기준 용어", fontsize=16, color=INK2, fontweight="bold")
    ax.text(27.6, 14.2, "분류", fontsize=16, color=INK2, fontweight="bold")
    for i, (term, concept, cat, sim) in enumerate(keep):
        y = 12.7 - i * 1.2
        ok = sim >= de.TAU
        w1 = chip(ax, 3.0, y, term, AMBER_SOFT if ok else "white", INK if ok else MUTED, edge=AMBER if ok else GRID, size=15, bold=ok, w=5.2)
        chip(ax, 18.4, y, concept, TEAL_SOFT if ok else "white", INK if ok else MUTED, edge=TEAL if ok else GRID, size=15, bold=ok, w=6.6)
        ax.add_patch(FancyArrowPatch((3.0 + w1 + 0.2, y), (18.2, y), arrowstyle="-|>", mutation_scale=20, linewidth=1.5 + 4.5 * max(sim - 0.6, 0),
                                     color=TEAL if ok else GRAY, linestyle="-" if ok else (0, (4, 4)), zorder=4))
        ax.text(13.3, y + 0.33, f"유사도 {sim:.2f}", ha="center", fontsize=12.5, color=INK if ok else MUTED, fontweight="bold" if ok else "normal")
        if ok and cat == de.COMMON:
            chip(ax, 27.6, y, "공통 · 세지 않음", "white", MUTED, edge=GRID, size=12.5, w=3.9)
        elif ok:
            chip(ax, 27.6, y, cat, TEAL, "white", size=15, bold=True, w=2.6)
        else:
            ax.text(27.6, y, "제외", fontsize=14, color=MUTED, va="center")
    ax.text(3.0, 0.55, f"유사도 {de.TAU} 이상만 채택 (점선: 기준 미달로 제외). 어느 문서에나 나오는 공통 낱말에 가장 가까우면 단서로 세지 않는다.", fontsize=13, color=MUTED)
    save(fig, "f5_meaning.png")


def fig_score(sem, name):
    fig, ax = canvas()
    labels = list(doctype.CATEGORIES) + [doctype.UNKNOWN]
    scores = {k: sem.scores.get(k, 0.0) for k in labels}
    order = sorted(labels, key=lambda k: -scores[k])
    top = order[0]
    scale = 13.0 / max(scores.values())
    for i, k in enumerate(order):
        y = 13.0 - i * 1.35
        ax.text(4.6, y, k, ha="right", va="center", fontsize=16, color=INK, fontweight="bold" if k == top else "normal")
        if scores[k] > 0:
            ax.add_patch(FancyBboxPatch((5.0, y - 0.42), scores[k] * scale, 0.84, boxstyle="round,pad=0,rounding_size=0.18", facecolor=TEAL if k == top else GRAY,
                                        edgecolor=SURF))
        ax.text(5.0 + scores[k] * scale + 0.3, y, f"{scores[k]:.1f}", va="center", fontsize=15, color=INK if k == top else MUTED,
                fontweight="bold" if k == top else "normal")
    x_need = 5.0 + de.MIN_SCORE * scale
    ax.plot([x_need, x_need], [2.6, 13.8], color=INK, linewidth=1.8, linestyle="--")
    ax.text(x_need, 2.0, f"기준 점수 {de.MIN_SCORE}", ha="center", fontsize=12.5, color=INK)
    # 결정
    ax.add_patch(FancyArrowPatch((20.4, 13.0), (23.4, 9.2), arrowstyle="-|>", mutation_scale=30, linewidth=3, color=TEAL, connectionstyle="arc3,rad=-0.25"))
    ax.add_patch(FancyBboxPatch((23.2, 4.6), 7.4, 4.4, boxstyle="round,pad=0,rounding_size=0.5", facecolor=TEAL, edgecolor=TEAL))
    ax.text(26.9, 7.6, name, ha="center", va="center", fontsize=14, color="#CFE0F7")
    ax.text(26.9, 6.3, f"→ {top}", ha="center", va="center", fontsize=40, color="white", fontweight="bold")
    ax.text(26.9, 5.2, "현장 실적 문서로 분류", ha="center", va="center", fontsize=14, color="#E6EEFB")
    save(fig, "f6_score.png")


def fig_sorted(shown):
    fig, ax = canvas()
    order = list(doctype.CATEGORIES) + [doctype.UNKNOWN, de.REVIEW]
    counts = collections.Counter(shown)
    for i, k in enumerate(order):
        x = 1.0 + i * 3.4
        color = AMBER if k == de.REVIEW else GRAY if k == doctype.UNKNOWN else TEAL
        ax.add_patch(FancyBboxPatch((x, 1.0), 3.0, 12.9, boxstyle="round,pad=0,rounding_size=0.3", facecolor="white", edgecolor=color, linewidth=2))
        ax.text(x + 1.5, 13.05, k, ha="center", va="center", fontsize=16, fontweight="bold", color=INK if k != de.REVIEW else AMBER)
        ax.text(x + 1.5, 12.0, f"{counts[k]}건", ha="center", va="center", fontsize=22, fontweight="bold", color=color if k != doctype.UNKNOWN else INK2)
        for n in range(counts[k]):
            tx = x + 0.3 + (n % 4) * 0.62
            ty = 9.9 - (n // 4) * 1.3
            ax.add_patch(FancyBboxPatch((tx, ty), 0.5, 1.08, boxstyle="round,pad=0,rounding_size=0.09", facecolor=color, edgecolor="white", linewidth=0.8))
    save(fig, "f7_sorted.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d = mp.compute()
    i = mp.pick_example(d)
    item = d["items"][i]
    grid, r0, c0 = load_grid(ee.SAMPLES / "inbox" / item["file"])
    terms = set(d["terms"][i])
    current = [doctype.classify_workbook(s) for s in d["sheets"]]
    shown = [de.combine(v, s)[0] for v, s in zip(current, d["semantic"])]
    names = [it["file"] for it in d["items"] if it["name_kind"] == "neutral"]
    random.Random(5).shuffle(names)
    fig_pile(names)
    fig_sheet(grid, r0, c0, item["file"])
    fig_read(grid, r0, c0, terms)
    fig_dict(grid, r0, c0, d["terms"][i], d["hits"][i], d["legacy"][i])
    fig_meaning(d["links"][i])
    fig_score(d["semantic"][i], item["file"])
    fig_sorted(shown)
    print(item["file"], dict(collections.Counter(shown)))


if __name__ == "__main__":
    main()
