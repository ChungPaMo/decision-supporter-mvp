"""README 에 쓰는 설명 그림을 만든다 (전체 흐름, 모델이 하는 일, 합치는 규칙, 고치는 순서).

    python -X utf8 modules/file_classifier/tools/make_readme_figures.py            # r2 의 유사도는 저장된 값을 쓴다
    python -X utf8 modules/file_classifier/tools/make_readme_figures.py --compute  # BGE-M3 로 유사도를 다시 계산 (torch, transformers 필요)

그림은 modules/file_classifier/figures/ 에, r2 에 쓴 유사도는 figures/readme_numbers.json 에 저장한다.
    r1_pipeline.png   엑셀이 들어와서 분류 결과가 나올 때까지
    r2_model.png      모델(BGE-M3)이 하는 일: 낱말을 숫자로 바꿔 뜻이 가까운 정도를 잰다 (실제 계산값)
    r3_combine.png    사전의 답과 뜻 판단의 답을 합치는 규칙 (doctype_embed.combine 과 같다)
    r4_update.png     새 양식을 만났을 때 고치는 순서

r1, r3, r4 는 코드의 기준값을 읽어 그리는 설명 그림이고 측정값이 아니다.
"""
from __future__ import annotations

import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "modules" / "file_classifier" / "src"), str(ROOT)]

from file_classifier import doctype  # noqa: E402

FIG = ROOT / "modules" / "file_classifier" / "figures"
NUMBERS = FIG / "readme_numbers.json"
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
BLUE, LIGHT_BLUE, YELLOW, LIGHT_YELLOW, NEUTRAL, LIGHT = "#2a78d6", "#d9e8fb", "#eda100", "#fbefcf", "#c3c2b7", "#f1f0ea"
# doctype_embed 를 import 하면 torch 없이도 되지만, 값이 바뀌면 그림도 바뀌도록 코드에서 읽는다
from file_classifier import doctype_embed as de  # noqa: E402

plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "figure.facecolor": SURF, "axes.facecolor": SURF,
                     "savefig.facecolor": SURF, "text.color": INK})
# r2 에 보여 줄 낱말. 행은 예시 파일(자료 (95).xlsx)에 실제로 있는 낱말, 열은 기준 용어(괄호는 그 용어가 속한 묶음)
WORDS = ["불량원인", "작업인원", "주간 생산현황표", "정품수량", "결재"]
REFS = [("불량 사유", "MES"), ("작업자", "MES"), ("생산 실적", "MES"), ("수량", "공통"), ("순소요량", "MRP"), ("모품목", "BOM"), ("단가", "ERP"), ("부서", "미분류")]


def canvas(w, h):
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w * 2)
    ax.set_ylim(0, h * 2)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, face=LIGHT, edge=None, lw=1.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.22", facecolor=face, edgecolor=edge or face, linewidth=lw))


def arrow(ax, x1, y1, x2, y2, color=INK2, style="-|>", rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=16, color=color, linewidth=1.6,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=0, shrinkB=0))


def save(fig, name):
    fig.savefig(FIG / name, dpi=130)
    plt.close(fig)
    print("saved", name)


def fig_pipeline():
    fig, ax = canvas(15, 7.4)
    ax.text(0.6, 14.0, "엑셀이 들어와서 분류 결과가 나올 때까지", fontsize=21, fontweight="bold", va="center")

    def step(x, y, w, h, num, title, lines, face=LIGHT, edge=None):
        box(ax, x, y, w, h, face, edge)
        ax.text(x + 0.35, y + h - 0.55, f"{num} {title}", fontsize=13.5, fontweight="bold", va="center")
        for i, line in enumerate(lines):
            ax.text(x + 0.35, y + h - 1.3 - i * 0.62, line, fontsize=10.8, color=INK2, va="center")

    step(0.6, 6.6, 4.4, 4.2, "", "엑셀 파일", [".xlsx · .xlsm · .csv", "여러 개를 한꺼번에", "종류 표시 없음"], face="#ffffff", edge=NEUTRAL)
    step(5.9, 6.6, 4.6, 4.2, "①", "읽기", ["앞쪽 60행 × 60열만", "시트는 20개까지", "파일명은 보지 않는다", "원본은 고치지 않는다"])
    step(11.4, 6.6, 4.6, 4.2, "②", "낱말 뽑기", ["제목, 열 이름, 항목 이름", "숫자·날짜 칸은 뺀다", "파일당 최대 90개"])
    step(17.0, 9.0, 5.6, 3.9, "③", "낱말 사전", ["낱말마다 정해 둔 점수를 더한다",
                                             f"1등 {doctype.MIN_SCORE:g}점 이상,", f"2등과 {doctype.MIN_MARGIN:g}점 이상 차이"], face=LIGHT_BLUE)
    step(17.0, 4.3, 5.6, 3.9, "④", "뜻 판단 (BGE-M3)", [f"기준 용어와 {de.TAU:g} 이상 닮은 낱말만",
                                                    f"1등 {de.MIN_SCORE:g}점 이상,", f"2등과 {de.MIN_MARGIN:g}점 이상 차이"], face=LIGHT_BLUE)
    step(23.6, 6.6, 5.6, 4.2, "⑤", "두 답을 합친다", ["같으면 그대로 분류", "한쪽만 답하면 그 답", "서로 다르면 확인 필요"], face=LIGHT_YELLOW)
    for x1, x2 in ((5.0, 5.9), (10.5, 11.4)):
        arrow(ax, x1, 8.7, x2, 8.7)
    arrow(ax, 16.0, 9.3, 17.0, 10.6)
    arrow(ax, 16.0, 8.1, 17.0, 6.6)
    arrow(ax, 22.6, 10.6, 23.6, 9.3)
    arrow(ax, 22.6, 6.6, 23.6, 8.1)
    arrow(ax, 26.4, 6.6, 26.4, 3.4)
    # 결과
    ax.text(0.6, 2.75, "결과", fontsize=13.5, fontweight="bold", va="center")
    x = 2.2
    for name in doctype.CATEGORIES:
        box(ax, x, 2.2, 2.25, 1.1, BLUE)
        ax.text(x + 1.125, 2.75, name, fontsize=12.5, color="white", fontweight="bold", ha="center", va="center")
        x += 2.5
    box(ax, x, 2.2, 2.6, 1.1, NEUTRAL)
    ax.text(x + 1.3, 2.75, "미분류", fontsize=12.5, fontweight="bold", ha="center", va="center")
    x += 2.85
    box(ax, x, 2.2, 3.3, 1.1, LIGHT_YELLOW, YELLOW, 1.8)
    ax.text(x + 1.65, 2.75, "확인 필요", fontsize=12.5, fontweight="bold", ha="center", va="center")
    ax.text(2.2, 1.35, "결과마다 근거 낱말과 확신 정도(높음·보통·낮음)를 함께 돌려준다. 점수는 확률이 아니다.", fontsize=11, color=INK2, va="center")
    ax.text(17.0, 13.45, "화면(서버)은 ③만 쓴다. 폴더 도구에 --embed 를 주면 ③ + ④ 를 모두 쓴다.", fontsize=11, color=INK2, va="center")
    ax.text(0.6, 0.5, "설명 그림. 기준값은 코드(doctype.py, doctype_embed.py)에서 읽었다.", fontsize=9.5, color=MUTED, va="center")
    save(fig, "r1_pipeline.png")


def similarities(compute: bool) -> list[list[float]]:
    if compute:
        emb = de.Embedder()
        sims = [[round(float(v), 3) for v in row] for row in emb.encode(WORDS) @ emb.encode([r for r, _ in REFS]).T]
        NUMBERS.write_text(json.dumps({"model": de.MODEL, "words": WORDS, "refs": [list(r) for r in REFS], "similarity": sims}, ensure_ascii=False, indent=1), encoding="utf-8")
        return sims
    saved = json.loads(NUMBERS.read_text(encoding="utf-8"))
    assert saved["words"] == WORDS and [tuple(r) for r in saved["refs"]] == REFS, "낱말이 바뀌었다. --compute 로 다시 계산해야 한다."
    return saved["similarity"]


def fig_model(sims):
    fig, ax = canvas(15, 8.2)
    ax.text(0.6, 15.6, "모델이 하는 일: 낱말을 숫자로 바꿔, 뜻이 가까운 정도를 잰다", fontsize=21, fontweight="bold", va="center")
    # 위: 개념
    box(ax, 0.6, 11.4, 4.2, 2.6, "#ffffff", NEUTRAL)
    ax.text(2.7, 13.1, "엑셀의 낱말", fontsize=11, color=INK2, ha="center", va="center")
    ax.text(2.7, 12.2, "작업인원", fontsize=17, fontweight="bold", ha="center", va="center")
    box(ax, 0.6, 8.2, 4.2, 2.6, "#ffffff", NEUTRAL)
    ax.text(2.7, 9.9, "기준 용어", fontsize=11, color=INK2, ha="center", va="center")
    ax.text(2.7, 9.0, "작업자", fontsize=17, fontweight="bold", ha="center", va="center")
    box(ax, 6.2, 8.2, 5.4, 5.8, LIGHT_BLUE)
    ax.text(8.9, 12.6, "BGE-M3", fontsize=19, fontweight="bold", ha="center", va="center")
    for i, line in enumerate(["공개된 다국어 임베딩 모델", "(BAAI/bge-m3)", "추가 학습 없이 그대로 사용", "내 컴퓨터 안에서만 실행"]):
        ax.text(8.9, 11.5 - i * 0.72, line, fontsize=11.5, color=INK2, ha="center", va="center")
    box(ax, 13.0, 11.4, 6.6, 2.6, LIGHT)
    ax.text(16.3, 13.1, "숫자 1,024개 (모양만 표시)", fontsize=11, color=INK2, ha="center", va="center")
    ax.text(16.3, 12.2, "[ 0.03, -0.01, 0.07, … ]", fontsize=14, ha="center", va="center")
    box(ax, 13.0, 8.2, 6.6, 2.6, LIGHT)
    ax.text(16.3, 9.9, "숫자 1,024개 (모양만 표시)", fontsize=11, color=INK2, ha="center", va="center")
    ax.text(16.3, 9.0, "[ 0.04, -0.02, 0.06, … ]", fontsize=14, ha="center", va="center")
    box(ax, 21.2, 9.3, 8.2, 3.6, LIGHT_YELLOW)
    ax.text(25.3, 12.05, "두 숫자 묶음이 가리키는 방향이", fontsize=12, color=INK2, ha="center", va="center")
    ax.text(25.3, 11.35, "얼마나 같은가 (코사인 유사도)", fontsize=12, color=INK2, ha="center", va="center")
    ax.text(25.3, 10.2, f"{sims[WORDS.index('작업인원')][[r for r, _ in REFS].index('작업자')]:.2f}", fontsize=26, fontweight="bold", ha="center", va="center")
    for y in (12.7, 9.5):
        arrow(ax, 4.8, y, 6.2, y)
        arrow(ax, 11.6, y, 13.0, y)
    arrow(ax, 19.6, 12.4, 21.2, 11.6)
    arrow(ax, 19.6, 9.8, 21.2, 10.6)
    ax.text(21.2, 8.6, "1 에 가까울수록 같은 뜻. 글자가 달라도 뜻이 가까우면 높다.", fontsize=10.5, color=INK2, va="center")
    # 아래: 실제 유사도 표
    ax.text(0.6, 6.9, f"실제로 잰 값   (파란 칸: {de.TAU:g} 이상이라 단서 후보가 되는 연결)", fontsize=13.5, fontweight="bold", va="center")
    x0, y0, cw, rh, lw = 6.2, 5.1, 2.9, 0.86, 5.4
    for j, (ref, group) in enumerate(REFS):
        ax.text(x0 + j * cw + cw / 2, y0 + 0.82, ref, fontsize=12, fontweight="bold", ha="center", va="center")
        ax.text(x0 + j * cw + cw / 2, y0 + 0.28, group, fontsize=10, color=MUTED, ha="center", va="center")
    for i, word in enumerate(WORDS):
        y = y0 - (i + 1) * rh
        ax.text(x0 - 0.3, y + rh / 2, word, fontsize=12.5, ha="right", va="center")
        best = max(range(len(REFS)), key=lambda j: sims[i][j])
        for j in range(len(REFS)):
            v = sims[i][j]
            keep = v >= de.TAU
            box(ax, x0 + j * cw + 0.06, y + 0.06, cw - 0.12, rh - 0.12, BLUE if keep else LIGHT, lw=0)
            ax.text(x0 + j * cw + cw / 2, y + rh / 2, f"{v:.2f}", fontsize=12.5, ha="center", va="center", color="white" if keep else INK2,
                    fontweight="bold" if j == best else "normal")
    ax.text(0.6, 0.35, "굵은 숫자는 그 낱말과 가장 가까운 용어(이 표 안에서). '정품수량'처럼 공통 낱말에 가장 가까우면 단서로 세지 않는다. "
            "'결재'처럼 어디에도 가깝지 않으면 버린다.", fontsize=10.5, color=MUTED, va="center")
    save(fig, "r2_model.png")


def fig_combine():
    fig, ax = canvas(13, 6.2)
    ax.text(0.6, 11.6, "두 답을 합치는 규칙", fontsize=21, fontweight="bold", va="center")
    cols = ["뜻 판단이 종류를 정함", "뜻 판단이 미분류", "뜻 판단이 정하지 못함\n(1등과 2등이 비슷)"]
    rows = ["사전이\n종류를 정함", "사전이\n단서 부족 (미분류)", "사전이\n확인 필요"]
    cells = [[("같은 종류면 그 종류\n다른 종류면 확인 필요", "mix"), ("사전의 종류", "ok"), ("사전의 종류", "ok")],
             [("뜻 판단의 종류", "ok"), ("미분류", "none"), ("확인 필요", "warn")],
             [("뜻 판단의 종류", "ok"), ("확인 필요", "warn"), ("확인 필요", "warn")]]
    x0, y0, cw, rh, lw = 6.4, 8.6, 6.2, 2.25, 5.6
    ax.text(x0 + 1.5 * cw, 10.55, "뜻 판단의 답 →", fontsize=11.5, color=MUTED, ha="center", va="center")
    for j, c in enumerate(cols):
        ax.text(x0 + j * cw + cw / 2, y0 + 0.75, c, fontsize=12.5, fontweight="bold", ha="center", va="center", linespacing=1.3)
    for i, r in enumerate(rows):
        y = y0 - (i + 1) * rh
        ax.text(x0 - 0.4, y + rh / 2, r, fontsize=12.5, fontweight="bold", ha="right", va="center", linespacing=1.3)
        for j, (text, kind) in enumerate(cells[i]):
            face = {"ok": BLUE, "none": NEUTRAL, "warn": LIGHT_YELLOW, "mix": LIGHT_BLUE}[kind]
            box(ax, x0 + j * cw + 0.1, y + 0.1, cw - 0.2, rh - 0.2, face, YELLOW if kind == "warn" else face, 1.8)
            ax.text(x0 + j * cw + cw / 2, y + rh / 2, text, fontsize=13, ha="center", va="center",
                    color="white" if kind == "ok" else INK, fontweight="bold", linespacing=1.4)
    ax.text(0.6, 0.55, "설명 그림. doctype_embed.combine() 의 규칙을 그대로 옮겼다. 측정값은 '두 방법이 서로를 확인해 준다' 그림에 있다.",
            fontsize=9.5, color=MUTED, va="center")
    save(fig, "r3_combine.png")


def fig_update():
    fig, ax = canvas(15, 6.6)
    ax.text(0.6, 12.4, "새 양식을 만났을 때 고치는 순서", fontsize=21, fontweight="bold", va="center")
    steps = [("1", "새 파일을 돌린다", ["sort_folder.py --embed", "결과 엑셀에 분류와 근거"], LIGHT),
             ("2", "빠진 파일을 본다", ["미분류 · 확인 필요 · 틀린 것", "어떤 낱말을 몰랐는지 확인"], LIGHT),
             ("3", "낱말 목록을 고친다", ["사전 / 기준 용어 / 공통 묶음", "(아래 표에서 고른다)"], LIGHT_BLUE),
             ("4", "다시 잰다", ["pytest 로 기존 답 유지 확인", "eval_embed.py 로 수치 비교"], LIGHT),
             ("5", "기록한다", ["버전 번호를 올린다", "그림과 README 수치 갱신"], LIGHT)]
    x, w, gap = 0.6, 5.1, 0.72
    for i, (num, title, lines, face) in enumerate(steps):
        box(ax, x, 7.2, w, 3.6, face)
        ax.text(x + 0.35, 10.15, f"{num}  {title}", fontsize=14, fontweight="bold", va="center")
        for k, line in enumerate(lines):
            ax.text(x + 0.35, 9.2 - k * 0.7, line, fontsize=10.8, color=INK2, va="center")
        if i < len(steps) - 1:
            arrow(ax, x + w + 0.08, 9.0, x + w + gap - 0.08, 9.0)
        x += w + gap
    arrow(ax, 20.4, 7.1, 14.7, 7.1, color=MUTED, rad=-0.45)
    ax.text(17.55, 5.25, "수치가 나빠졌으면 3으로 돌아간다", fontsize=10.8, color=MUTED, ha="center", va="center")
    table = [("회사가 쓰는 표기가 사전에 없다", "사전에 낱말과 점수 추가", "doctype.py 의 KEYWORDS · EXACT"),
             ("뜻은 같은데 표기가 여러 가지다", "기준 용어 추가 (통용 용어로)", "doctype_embed.py 의 CONCEPTS"),
             ("흔한 낱말 때문에 엉뚱한 종류로 간다", "공통 묶음에 추가", "doctype_embed.py 의 CONCEPTS[공통]")]
    for j, (head, cx) in enumerate((("이런 문제일 때", 0.9), ("이렇게 고친다", 11.6), ("고치는 곳", 20.4))):
        ax.text(cx, 3.95, head, fontsize=11, color=MUTED, va="center")
    for i, row in enumerate(table):
        y = 3.2 - i * 0.82
        box(ax, 0.6, y - 0.36, 28.6, 0.72, LIGHT if i % 2 == 0 else SURF, lw=0)
        for text, cx, bold in zip(row, (0.9, 11.6, 20.4), (False, True, False)):
            ax.text(cx, y, text, fontsize=11.8, va="center", fontweight="bold" if bold else "normal", color=INK if bold else INK2)
    ax.text(0.6, 0.4, "모델(BGE-M3)은 다시 학습하지 않는다. 고치는 것은 낱말 목록뿐이라, 고친 뒤 바로 다시 돌릴 수 있다.", fontsize=11, color=INK2, va="center")
    save(fig, "r4_update.png")


def main() -> None:
    fig_pipeline()
    fig_model(similarities("--compute" in sys.argv))
    fig_combine()
    fig_update()


if __name__ == "__main__":
    main()
