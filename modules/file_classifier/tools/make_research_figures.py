"""표 위치 찾기와 속도 실험의 결과 그림을 만든다. matplotlib, openpyxl 이 필요하다 (모델은 필요 없다).

    python -X utf8 modules/file_classifier/tools/make_research_figures.py

그림에 쓰는 숫자는 아래 도구가 저장한 파일에서 읽는다. 숫자를 바꾸려면 도구를 먼저 다시 돌린다.
    figures/tables_numbers.json       tools/eval_tables.py --seeds 7,20270101,424242 --json …
    figures/tables_api_numbers.json   tools/eval_tables_api.py --json …
    figures/speed_numbers.json        tools/eval_speed.py --json …
만드는 그림
    t1_table_example.png   실제 엑셀 한 개에서 찾은 표 범위
    t2_table_results.png   표 위치를 맞게 찾은 파일 수: 첫 줄을 머리글로 볼 때와 찾기를 쓸 때
    v1_speed.png           파일 하나를 뜻으로 판단하는 시간, 작은 모델의 정확도
합성 자료이며 실제 기업 파일이 아니다.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "modules" / "file_classifier" / "src"), str(ROOT)]

from file_classifier import tables  # noqa: E402

FIG = ROOT / "modules" / "file_classifier" / "figures"
SAMPLES = ROOT / "modules" / "file_classifier" / "samples"
EXAMPLE = "자료 (95).xlsx"
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
BLUE, LIGHT_BLUE, YELLOW, LIGHT_YELLOW, NEUTRAL, LIGHT, CRITICAL = "#2a78d6", "#d9e8fb", "#eda100", "#fbefcf", "#c3c2b7", "#f1f0ea", "#d03b3b"
plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "figure.facecolor": SURF, "axes.facecolor": SURF,
                     "savefig.facecolor": SURF, "text.color": INK, "axes.edgecolor": GRID, "xtick.color": MUTED, "ytick.color": MUTED})


def save(fig, name):
    fig.savefig(FIG / name, dpi=130)
    plt.close(fig)
    print("saved", name)


def fig_example():
    data = (SAMPLES / "inbox" / EXAMPLE).read_bytes()
    wb = load_workbook(io.BytesIO(data))
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    t = next(x for x in tables.find_tables_in_xlsx(data) if x.sheet == ws.title)
    n_rows, n_cols = min(len(rows), t.data_end_row + 1), max(len(r) for r in rows)
    first_filled = next(i for i, r in enumerate(rows) if sum(v is not None for v in r) >= 2) + 1     # 기준선이 머리글로 보는 행
    cw, rh, x0, y_top = 1.8, 0.72, 1.3, 1.5 + n_rows * 0.72
    fig = plt.figure(figsize=(15, 0.36 * (y_top + 3.4)))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 30)
    ax.set_ylim(0, y_top + 3.4)
    ax.axis("off")
    ax.text(0.6, y_top + 2.5, "실제 엑셀에서 표가 어디인지 찾는다", fontsize=21, fontweight="bold", va="center")
    ax.text(0.6, y_top + 1.45, f"파일: {EXAMPLE}   찾은 범위: 머리글 {t.header_row}행, 데이터 {t.data_start_row}~{t.data_end_row}행, {t.first_col}~{t.last_col}열",
            fontsize=12, color=INK2, va="center")
    for i in range(n_rows):
        y = y_top - (i + 1) * rh
        ax.text(x0 - 0.3, y + rh / 2, str(i + 1), fontsize=10, color=MUTED, ha="right", va="center")
        for j in range(n_cols):
            v = rows[i][j] if j < len(rows[i]) else None
            r1, c1 = i + 1, j + 1
            in_cols = t.first_col <= c1 <= t.last_col
            face, color, weight = "white", MUTED, "normal"
            if r1 == t.header_row and in_cols:
                face, color, weight = BLUE, "white", "bold"
            elif t.data_start_row <= r1 <= t.data_end_row and in_cols:
                face, color = LIGHT_BLUE, INK
            ax.add_patch(Rectangle((x0 + j * cw, y), cw, rh, facecolor=face, edgecolor=GRID, linewidth=0.8))
            if v is not None:
                text = str(v)
                text = text[:10] if len(text) > 11 else text
                ax.text(x0 + j * cw + cw / 2, y + rh / 2, text, fontsize=10, color=color, fontweight=weight, ha="center", va="center")
    ax.add_patch(Rectangle((x0, y_top - first_filled * rh), n_cols * cw, rh, facecolor="none", edgecolor=CRITICAL, linewidth=2.2, linestyle=(0, (5, 3))))
    right = x0 + n_cols * cw + 0.6
    notes = [(first_filled, CRITICAL, "첫 줄 방식이 고르는 줄"),
             (t.header_row, BLUE, "찾은 머리글"), ((t.data_start_row + t.data_end_row) / 2, INK2, "찾은 데이터")]
    for row, color, text in notes:
        ax.text(right, y_top - (row - 0.5) * rh, "←  " + text, fontsize=11.5, color=color, va="center", fontweight="bold" if color != INK2 else "normal")
    ax.text(0.6, 0.55, "더미의 실제 파일. 회색 글자는 표 밖(제목, 결재란, 문서번호, 작성일자 줄, 합계 줄)이라 건너뛴다. 빨간 점선: 글자가 있는 첫 줄을 머리글로 볼 때 고르는 줄.",
            fontsize=10, color=MUTED, va="center")
    save(fig, "t1_table_example.png")


def fig_table_results():
    d = json.loads((FIG / "tables_numbers.json").read_text(encoding="utf-8"))
    kinds = ["표 한 개", "합계 행", "묶음 머리글", "표 여러 개"]
    desc = {"표 한 개": "제목·결재란 아래 표 하나", "합계 행": "맨 아래 합계 줄", "묶음 머리글": "머리글이 두 줄 (병합)", "표 여러 개": "한 시트에 표가 여러 개"}
    by = d["stored"]["by_kind"]
    base, mine, files = d["stored"]["methods"]["기준선"], d["stored"]["methods"]["찾기"], d["stored"]["files"]
    fig = plt.figure(figsize=(15, 6.4))
    fig.text(0.04, 0.92, "표 위치를 맞게 찾은 파일 수", fontsize=21, fontweight="bold", va="center")
    fig.text(0.04, 0.855, f"더미 엑셀 {files}개. 한 파일의 표를 모두 정확히 찾고(머리글 행, 데이터 행, 열 범위) 없는 표를 찾지 않았을 때 맞은 것으로 센다.",
             fontsize=11.5, color=INK2, va="center")
    ax = fig.add_axes([0.06, 0.2, 0.3, 0.55])
    vals = [base["file_ok"], mine["file_ok"]]
    bars = ax.bar(["첫 줄을\n머리글로 본다", "표 위치 찾기"], vals, color=[NEUTRAL, BLUE], width=0.56)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 4, f"{v}개", ha="center", fontsize=17, fontweight="bold", color=INK if v == vals[1] else INK2)
    ax.set_ylim(0, files * 1.16)
    ax.set_yticks([0, 50, 100, 150, 200])
    ax.tick_params(length=0, labelsize=12)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax2 = fig.add_axes([0.5, 0.2, 0.46, 0.55])
    for i, k in enumerate(reversed(kinds)):
        n, ok, b_ok = by[k]["files"], by[k].get("ok", 0), by[k].get("base_ok", 0)
        ax2.barh(i + 0.19, b_ok / n, height=0.3, color=NEUTRAL)
        ax2.barh(i - 0.19, ok / n, height=0.3, color=BLUE)
        ax2.text(b_ok / n + 0.015, i + 0.19, f"{b_ok} / {n}", va="center", fontsize=11.5, color=INK2)
        ax2.text(ok / n + 0.015, i - 0.19, f"{ok} / {n}", va="center", fontsize=11.5, fontweight="bold")
    ax2.set_yticks(range(len(kinds)))
    ax2.set_yticklabels([f"{k}\n{desc[k]}" for k in reversed(kinds)], fontsize=11.5, color=INK)
    ax2.set_xlim(0, 1.16)
    ax2.set_xticks([0, 0.5, 1.0])
    ax2.set_xticklabels(["0%", "50%", "100%"])
    ax2.tick_params(length=0)
    ax2.grid(axis="x", color=GRID, linewidth=0.8)
    ax2.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax2.spines[side].set_visible(False)
    ax2.set_title("양식의 모양별 (회색: 첫 줄을 머리글로, 파랑: 찾기)", fontsize=12, color=INK2, loc="left", pad=10)
    fresh = d["fresh"]
    n_files = sum(v["files"] for v in fresh.values())
    n_ok = sum(v["methods"]["찾기"]["file_ok"] for v in fresh.values())
    n_tab = sum(v["methods"]["찾기"]["gold"] for v in fresh.values())
    fig.text(0.04, 0.085, f"같은 생성기를 다른 seed {len(fresh)}개로 돌려 새로 만든 엑셀 {n_files}개(표 {n_tab:,}개)에서도 {n_ok}개를 맞게 찾았다. "
             "양식의 종류는 같고 배치와 내용만 다르다.", fontsize=11.5, color=INK2, va="center")
    fig.text(0.04, 0.035, "찾는 규칙은 이 200개를 보면서 만들었다. 새로운 종류의 양식이나 실제 기업 파일에서의 성능은 재지 않았다. 합성 자료.", fontsize=10, color=MUTED, va="center")
    save(fig, "t2_table_results.png")


def fig_speed():
    path = FIG / "speed_numbers.json"
    if not path.exists():
        print("speed_numbers.json 이 없어 v1_speed.png 는 건너뛴다")
        return
    d = json.loads(path.read_text(encoding="utf-8"))
    runs = d["runs"]

    def pick(label, device, flt=True):
        return next((r for r in runs if r["label"].startswith(label) and r["device"] == device and r["value_filter"] == flt), None)

    bars = [("BGE-M3 · GPU", pick("BGE-M3", "cuda"), BLUE), ("BGE-M3 · CPU\n값 낱말 넣음", pick("BGE-M3", "cpu", False), NEUTRAL), ("BGE-M3 · CPU\n값 낱말 뺌", pick("BGE-M3", "cpu"), BLUE)]
    small = [r for r in runs if r["label"].startswith("multilingual-e5-small")]
    best = max(small, key=lambda r: (r["test"]["ok"] - 3 * r["test"]["wrong"], -r["tau"])) if small else None
    if best:
        bars.append((f"작은 모델 · CPU\n(e5-small, 기준 {best['tau']})", best, YELLOW))
    bars = [b for b in bars if b[1]]
    fig = plt.figure(figsize=(15, 6.6))
    fig.text(0.04, 0.925, "뜻 판단을 서버(CPU)에 올릴 수 있나", fontsize=21, fontweight="bold", va="center")
    fig.text(0.04, 0.86, f"더미 엑셀 200개, 파일마다 낱말을 처음 본다고 치고 잰 값. CPU 스레드 {d['cpu_threads']}개, GPU {d.get('gpu') or '없음'}.", fontsize=11.5, color=INK2, va="center")
    panels = [("파일 하나를 판단하는 시간 (중앙값, ms)", lambda r: r["ms_median"], lambda r: f"{r['ms_median']:.0f}ms\n(95% {r['ms_p95']:.0f})"),
              ("200개를 처리하는 시간 (중앙값으로 환산, 초)", lambda r: r["ms_median"] * 200 / 1000, lambda r: f"{r['ms_median'] * 200 / 1000:.0f}초"),
              ("처음 보는 양식 109개 중 맞음", lambda r: r["test"]["ok"], lambda r: f"{r['test']['ok']}개\n틀림 {r['test']['wrong']}")]
    for k, (title, value, text) in enumerate(panels):
        ax = fig.add_axes([0.05 + k * 0.325, 0.27, 0.27, 0.46])
        vals = [value(r) for _, r, _ in bars]
        rects = ax.bar(range(len(bars)), vals, color=[c for _, _, c in bars], width=0.62)
        top = max(vals) or 1
        for rect, (_, r, _) in zip(rects, bars):
            ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + top * 0.03, text(r), ha="center", va="bottom", fontsize=10.5, linespacing=1.3)
        ax.set_ylim(0, top * 1.32)
        ax.set_xticks(range(len(bars)))
        ax.set_xticklabels([n for n, _, _ in bars], fontsize=9.5, color=INK)
        ax.set_title(title, fontsize=12.5, loc="left", pad=10)
        ax.tick_params(length=0)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
    fig.text(0.04, 0.115, "작은 모델은 유사도 분포가 달라 기준 0.65 를 그대로 쓸 수 없다. 여러 기준 중 가장 나은 값을 골라 그렸으므로 유리하게 나온 수치다. "
             "기준별 결과는 README 표에 모두 있다.", fontsize=11, color=INK2, va="center")
    fig.text(0.04, 0.055, "측정 환경 한 곳의 값이다. 서버의 CPU가 다르면 시간이 달라진다. 합성 자료.", fontsize=10, color=MUTED, va="center")
    save(fig, "v1_speed.png")


if __name__ == "__main__":
    fig_example()
    fig_table_results()
    fig_speed()
