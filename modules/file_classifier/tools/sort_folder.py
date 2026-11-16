"""폴더에 든 엑셀·CSV 를 문서 종류별로 분류해 결과 엑셀을 만든다. openpyxl 이 필요하다.

    python -X utf8 modules/file_classifier/tools/sort_folder.py <폴더> [--out 결과.xlsx] [--labels labels.json]

--labels 를 주면 정답과 비교해 채점 시트를 추가하고 요약을 출력한다.
원본 파일은 읽기만 하며 옮기거나 고치지 않는다. 외부로 보내는 것도 없다.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib
import sys
import time

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "modules" / "file_classifier" / "src"), str(ROOT)]

from file_classifier.doctype import CATEGORIES, UNKNOWN, VERSION, Verdict, classify_workbook  # noqa: E402

MAX_ROWS, MAX_COLS = 60, 60
REVIEW = "확인 필요"


def read_sheets(path: pathlib.Path) -> list[tuple[str | None, list[list]]]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            return [(None, [row[:MAX_COLS] for _, row in zip(range(MAX_ROWS), csv.reader(f))])]
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = []
        for ws in wb.worksheets[:20]:
            rows = [["" if v is None else str(v) for v in row] for row in ws.iter_rows(min_row=1, max_row=MAX_ROWS, max_col=MAX_COLS, values_only=True)]
            sheets.append((ws.title, rows))
        return sheets
    finally:
        wb.close()


def classify_file(path: pathlib.Path) -> tuple[Verdict | None, str, float]:
    start = time.perf_counter()
    try:
        verdict, error = classify_workbook(read_sheets(path)), ""
    except Exception as exc:  # 깨진 파일·암호 걸린 파일 등은 건너뛰고 이유를 남긴다
        verdict, error = None, f"{type(exc).__name__}: 파일을 읽지 못했습니다"
    return verdict, error, (time.perf_counter() - start) * 1000


def shown_category(verdict: Verdict | None) -> str:
    """결과 표에 적는 분류. 확신이 부족하면 범주 대신 '확인 필요'로 적는다."""
    if verdict is None or verdict.needs_review:
        return REVIEW
    return verdict.category


def run(folder: pathlib.Path) -> list[dict]:
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".xlsx", ".xlsm", ".csv") and not p.name.startswith("~$"))
    results = []
    for path in files:
        verdict, error, ms = classify_file(path)
        results.append({"file": path.name, "verdict": verdict, "error": error, "ms": ms, "shown": shown_category(verdict)})
    return results


def score(results: list[dict], labels: dict[str, dict]) -> dict:
    rows = [(labels[r["file"]], r) for r in results if r["file"] in labels]
    n = len(rows)
    correct = sum(1 for lab, r in rows if r["shown"] == lab["category"])
    review = sum(1 for _, r in rows if r["shown"] == REVIEW)
    wrong = n - correct - review
    matrix = collections.Counter((lab["category"], r["shown"]) for lab, r in rows)
    return {"n": n, "correct": correct, "review": review, "wrong": wrong, "matrix": matrix}


def write_result(results: list[dict], out: pathlib.Path, labels: dict[str, dict] | None) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "분류결과"
    header = ["파일명", "분류", "세부", "확신", "점수", "2순위", "2순위 점수", "근거", "단서 낱말"] + (["정답", "채점"] if labels else [])
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    fills = {REVIEW: PatternFill("solid", start_color="FFF2CC"), "오분류": PatternFill("solid", start_color="F8CBAD")}
    for r in results:
        v = r["verdict"]
        row = [r["file"], r["shown"], v.detail if v else "", v.confidence if v else "", v.score if v else "", (v.runner_up or "") if v else "",
               v.runner_up_score if v else "", (v.reason if v else r["error"]), ", ".join(v.evidence[:8]) if v else ""]
        if labels:
            truth = labels.get(r["file"], {}).get("category", "")
            row += [truth, "" if not truth else "정답" if r["shown"] == truth else REVIEW if r["shown"] == REVIEW else "오분류"]
        ws.append(row)
        mark = row[-1] if labels and row[-1] == "오분류" else r["shown"]
        if mark in fills:
            for cell in ws[ws.max_row]:
                cell.fill = fills[mark]
    for col, width in zip("ABCDEFGHI", (38, 12, 14, 8, 8, 10, 12, 60, 50)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"

    summary = wb.create_sheet("요약")
    summary.append(["분류", "파일 수"])
    counts = collections.Counter(r["shown"] for r in results)
    for cat in list(CATEGORIES) + [UNKNOWN, REVIEW]:
        summary.append([cat, counts.get(cat, 0)])
    summary.append(["합계", len(results)])
    summary.append([])
    summary.append(["분류기 버전", VERSION])
    summary.append(["점수는 단서 낱말 가중치의 합이며 확률이 아닙니다."])

    if labels:
        s = score(results, labels)
        sheet = wb.create_sheet("채점")
        cols = list(CATEGORIES) + [UNKNOWN, REVIEW]
        sheet.append(["정답 \\ 분류"] + cols + ["합계", "정답률"])
        for truth in list(CATEGORIES) + [UNKNOWN]:
            row = [s["matrix"].get((truth, c), 0) for c in cols]
            total = sum(row)
            sheet.append([truth] + row + [total, round(s["matrix"].get((truth, truth), 0) / total, 3) if total else ""])
        sheet.append([])
        sheet.append(["전체", s["n"], "정답", s["correct"], "확인 필요", s["review"], "오분류", s["wrong"]])
    wb.save(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="엑셀 폴더를 문서 종류별로 분류한다.")
    parser.add_argument("folder", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path, default=None)
    parser.add_argument("--labels", type=pathlib.Path, default=None)
    parser.add_argument("--split", choices=["dev", "test"], default=None, help="채점 출력에서 이 분할만 본다")
    parser.add_argument("--show-misses", action="store_true")
    args = parser.parse_args()
    labels = None
    if args.labels:
        labels = {item["file"]: item for item in json.loads(args.labels.read_text(encoding="utf-8"))["files"]}
    results = run(args.folder)
    out = args.out or args.folder.parent / "분류결과.xlsx"
    write_result(results, out, labels)
    counts = collections.Counter(r["shown"] for r in results)
    times = sorted(r["ms"] for r in results)
    print(f"파일 {len(results)}개 -> {out}")
    print("분류:", {k: counts[k] for k in list(CATEGORIES) + [UNKNOWN, REVIEW] if counts.get(k)})
    if times:
        print(f"파일당 처리시간 중앙값 {times[len(times) // 2]:.1f}ms, 최대 {times[-1]:.1f}ms")
    if labels:
        for name in ([args.split] if args.split else ["dev", "test", None]):
            subset = [r for r in results if name is None or labels.get(r["file"], {}).get("split") == name]
            s = score(subset, labels)
            if s["n"]:
                print(f"[{name or 'all'}] n={s['n']} 정답 {s['correct']} ({s['correct'] / s['n']:.1%}) / 확인 필요 {s['review']} ({s['review'] / s['n']:.1%})"
                      f" / 오분류 {s['wrong']} ({s['wrong'] / s['n']:.1%})")
        if args.show_misses:
            for r in results:
                lab = labels.get(r["file"])
                if lab and r["shown"] != lab["category"] and (args.split is None or lab["split"] == args.split):
                    v = r["verdict"]
                    print(f"  {lab['split']:4s} {lab['category']:5s} {lab.get('template', ''):30s} -> {r['shown']:6s} src={lab.get('source', ''):15s} "
                          f"scores={ {k: s2 for k, s2 in (v.scores.items() if v else []) if s2} } {r['file']}")

if __name__ == "__main__":
    main()
