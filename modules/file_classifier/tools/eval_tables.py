"""표 위치 찾기(file_classifier.tables)를 더미 엑셀 200개의 정답 위치와 비교한다. openpyxl 이 필요하다.

    python -X utf8 modules/file_classifier/tools/eval_tables.py [--show-misses] [--seeds 7,20270101,424242] [--json 결과.json]

--seeds 를 주면 같은 생성기를 다른 seed 로 돌려 새로 만든 200개씩으로도 잰다 (임시 폴더에 만들고 지운다).

정답은 더미 생성기(samples/make_samples.py)가 알고 있는 표의 머리글과 행 수에서 얻는다. 파일을 다시 만들지 않고,
저장소에 있는 엑셀을 열어 머리글 글자가 놓인 자리를 찾는다. 열었을 때 먼저 보이는 시트(active)의 표만 채점한다.

비교 대상(기준선): "글자가 2칸 이상 있는 첫 행을 머리글로 보고 그 아래 전부를 데이터로 본다".
합성 자료이며 실제 기업 파일이 아니다.
"""
from __future__ import annotations

import collections
import io
import json
import pathlib
import runpy
import sys

from openpyxl import load_workbook

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "modules" / "file_classifier" / "src"), str(ROOT)]

from file_classifier import tables  # noqa: E402

SAMPLES = ROOT / "modules" / "file_classifier" / "samples"


def fold(value) -> str:
    return "".join(str(value if value is not None else "").lower().split())


def gold_tables(ws, blocks) -> list[dict]:
    """생성기가 넣은 표의 실제 자리. 머리글 글자가 그대로 이어진 곳을 위에서부터 찾는다."""
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    out, after = [], 0
    for block in blocks:
        if block["kind"] != "table":
            continue
        want = tuple(fold(h) for h in block["headers"])
        for i in range(after, len(rows)):
            have = tuple(fold(v) for v in rows[i])
            at = next((c for c in range(len(have) - len(want) + 1) if have[c:c + len(want)] == want), None)
            if at is not None:
                out.append({"header_row": i + 1, "data_start_row": i + 2, "data_end_row": i + 1 + len(block["rows"]),
                            "first_col": at + 1, "last_col": at + len(want), "grouped": bool(block["groups"]), "total": bool(block["total"])})
                after = i + 1 + len(block["rows"])
                break
        else:
            raise ValueError(f"머리글을 찾지 못했다: {ws.title} {block['headers']}")
    return out


def baseline(rows) -> list[dict]:
    """글자가 2칸 이상 있는 첫 행을 머리글로 본다. 열은 그 행의 처음부터 끝까지, 데이터는 시트 끝까지."""
    for i, row in enumerate(rows):
        filled = [c for c, v in enumerate(row) if v is not None and str(v).strip()]
        if len(filled) >= 2:
            return [{"header_row": i + 1, "data_start_row": i + 2, "data_end_row": len(rows), "first_col": filled[0] + 1, "last_col": filled[-1] + 1}]
    return []


KEYS = ("header_row", "data_start_row", "data_end_row", "first_col", "last_col")
HEAD = ("header_row", "first_col", "last_col")


def score(gold: list[dict], pred: list[dict]) -> dict:
    exact = sum(any(all(p[k] == g[k] for k in KEYS) for p in pred) for g in gold)
    header = sum(any(all(p[k] == g[k] for k in HEAD) for p in pred) for g in gold)
    extra = sum(not any(all(p[k] == g[k] for k in HEAD) for g in gold) for p in pred)
    return {"gold": len(gold), "header": header, "exact": exact, "extra": extra,
            "file_ok": exact == len(gold) and extra == 0, "first_header_ok": bool(gold) and any(all(p[k] == gold[0][k] for k in HEAD) for p in pred)}


def fresh_samples(seed: int, folder: pathlib.Path):
    """같은 생성기를 다른 seed 로 돌려 임시 폴더에 새 엑셀 200개를 만든다. 저장소의 파일은 건드리지 않는다.

    양식의 종류는 같고 배치(시작 위치, 표 개수, 항목 줄, 꾸밈)와 내용이 달라진다. 새로운 종류의 양식은 아니다.
    """
    import random

    g = runpy.run_path(str(SAMPLES / "make_samples.py"))
    g["build"].__globals__["SEED"] = seed           # run_path 가 돌려주는 dict 는 사본이라, 함수가 보는 전역을 직접 바꾼다
    generated = g["build"]()
    rng = random.Random(seed + 1)
    for item in generated:
        blocks, offset, extra_sheet, sheet_name = item["_write"]
        g["write_workbook"](folder / item["file"], rng, random.Random(f"{seed}-style-{item['file']}"), blocks, offset, extra_sheet, sheet_name, item["source"])
    return [{k: v for k, v in item.items() if k != "_write"} for item in generated], generated


def main() -> None:
    import tempfile

    labels = json.loads((SAMPLES / "labels.json").read_text(encoding="utf-8"))["files"]
    generated = runpy.run_path(str(SAMPLES / "make_samples.py"))["build"]()
    assert [{k: v for k, v in item.items() if k != "_write"} for item in generated] == labels, "생성기와 labels.json 이 다르다"
    print("저장소의 엑셀 200개")
    report = {"version": tables.VERSION, "stored": evaluate(labels, generated, SAMPLES / "inbox"), "fresh": {}}
    seeds = [int(x) for x in sys.argv[sys.argv.index("--seeds") + 1].split(",")] if "--seeds" in sys.argv else []
    for seed in seeds:
        with tempfile.TemporaryDirectory() as tmp:
            fresh_labels, fresh = fresh_samples(seed, pathlib.Path(tmp))
            print(f"seed {seed} 로 새로 만든 엑셀 {len(fresh_labels)}개 (저장하지 않음)")
            report["fresh"][str(seed)] = evaluate(fresh_labels, fresh, pathlib.Path(tmp))
    if "--json" in sys.argv:
        pathlib.Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


def evaluate(labels, generated, folder: pathlib.Path) -> dict:
    totals = {"찾기": collections.Counter(), "기준선": collections.Counter()}
    by_kind = collections.defaultdict(collections.Counter)
    misses = []
    for label, record in zip(labels, generated):
        data = (folder / label["file"]).read_bytes()
        wb = load_workbook(io.BytesIO(data))
        ws = wb.active
        gold = gold_tables(ws, record["_write"][0])
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        found = [t.as_dict() for t in tables.find_tables_in_xlsx(data) if t.sheet == ws.title]
        wb.close()
        results = {"찾기": score(gold, found), "기준선": score(gold, baseline(rows))}
        for name, s in results.items():
            totals[name].update({k: int(v) for k, v in s.items()})
            totals[name]["files"] += 1
        kind = "표 여러 개" if len(gold) > 1 else "묶음 머리글" if any(g["grouped"] for g in gold) else "합계 행" if any(g["total"] for g in gold) else "표 한 개"
        by_kind[kind].update({"files": 1, "ok": int(results["찾기"]["file_ok"]), "base_ok": int(results["기준선"]["file_ok"])})
        if not results["찾기"]["file_ok"]:
            misses.append((label["file"], label["template"], gold, found))
    summary = {"version": tables.VERSION, "files": len(labels), "methods": {n: dict(c) for n, c in totals.items()}, "by_kind": {k: dict(v) for k, v in by_kind.items()}}
    for name, c in totals.items():
        print(f"{name:<4} 표 {c['gold']}개 중 머리글 위치 맞음 {c['header']} ({c['header'] / c['gold']:.1%}), 범위까지 모두 맞음 {c['exact']} ({c['exact'] / c['gold']:.1%}), "
              f"없는 표를 찾음 {c['extra']} | 파일 {c['files']}개 중 전부 맞음 {c['file_ok']} ({c['file_ok'] / c['files']:.1%}), 첫 표 머리글 맞음 {c['first_header_ok']}")
    for kind, c in sorted(by_kind.items()):
        print(f"   {kind:<8} 파일 {c['files']:3d}개: 찾기 {c['ok']:3d}, 기준선 {c['base_ok']:3d}")
    if "--show-misses" in sys.argv:
        for file, template, gold, found in misses[:25]:
            print("\n", file, template)
            print("   정답:", [[g[k] for k in KEYS] for g in gold])
            print("   찾음:", [[f[k] for k in KEYS] for f in found])
    return summary

if __name__ == "__main__":
    main()
