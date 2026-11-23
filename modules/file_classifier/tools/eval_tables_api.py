"""찾은 표 범위를 백엔드의 표 범위 선택(table_selection)에 그대로 넣었을 때 받아들여지는지, 분류 결과가 어떻게 달라지는지 본다.

    python -X utf8 modules/file_classifier/tools/eval_tables_api.py [--json 결과.json]

더미 엑셀 200개마다 두 번 호출한다 (서버를 띄우지 않고 TestClient 로, 저장 없음, DB 없음).
    1. 범위 없이 POST /classifications/file            지금 화면이 하는 방식
    2. 찾은 첫 표를 table_selection 으로 넣어 같은 API    표 위치 찾기를 붙였을 때

backend 의 의존성(fastapi 등)이 필요하다. 합성 자료이며 실제 기업 파일이 아니다.
"""
from __future__ import annotations

import collections
import hashlib
import io
import json
import pathlib
import sys
from unittest.mock import patch

from openpyxl import load_workbook

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend"), str(ROOT / "modules" / "file_classifier" / "src"), str(ROOT / "modules" / "planning_engine")]

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import app  # noqa: E402
from file_classifier import tables  # noqa: E402

SAMPLES = ROOT / "modules" / "file_classifier" / "samples"


def outcome(response) -> str:
    if response.status_code != 200:
        detail = response.json().get("detail", {})
        return f"거부 {detail.get('code', response.status_code) if isinstance(detail, dict) else response.status_code}"
    body = response.json()
    return f"추천 {body['recommended_entity']}" if not body["hold"] else f"보류 {body.get('hold_kind') or '-'}"


def main() -> None:
    labels = json.loads((SAMPLES / "labels.json").read_text(encoding="utf-8"))["files"]
    plain, selected, accepted, rows = collections.Counter(), collections.Counter(), 0, []
    with patch("app.api.batches.get_settings", return_value=Settings(persistence="disabled")), TestClient(app) as client:
        for label in labels:
            data = (SAMPLES / "inbox" / label["file"]).read_bytes()
            wb = load_workbook(io.BytesIO(data), read_only=True)
            active = wb.active.title
            wb.close()
            found = [t for t in tables.find_tables_in_xlsx(data) if t.sheet == active]
            first = client.post("/classifications/file", files={"file": (label["file"], data)})
            plain[outcome(first)] += 1
            if not found:
                selected["표를 찾지 못함"] += 1
                continue
            t = found[0]
            selection = {"source_sha256": hashlib.sha256(data).hexdigest(), "sheet": t.sheet, "header_row": t.header_row, "data_start_row": t.data_start_row,
                         "data_end_row": t.data_end_row, "first_col": t.first_col, "last_col": t.last_col}
            second = client.post("/classifications/file", files={"file": (label["file"], data)}, data={"table_selection": json.dumps(selection)})
            accepted += second.status_code == 200
            selected[outcome(second)] += 1
            rows.append({"file": label["file"], "category": label["category"], "template": label["template"], "plain": outcome(first), "selected": outcome(second)})
    print(f"파일 {len(labels)}개")
    print("범위 없이      :", dict(plain.most_common()))
    print("찾은 범위를 넣어:", dict(selected.most_common()))
    print(f"찾은 범위를 백엔드가 받아들인 파일: {accepted} / {len(labels)}")
    by = collections.Counter((r["category"], r["selected"]) for r in rows)
    for (cat, out), n in sorted(by.items()):
        print(f"   {cat:<5} {out:<28} {n}")
    if "--json" in sys.argv:
        out = pathlib.Path(sys.argv[sys.argv.index("--json") + 1])
        out.write_text(json.dumps({"version": tables.VERSION, "files": len(labels), "plain": dict(plain), "selected": dict(selected), "accepted": accepted,
                                   "by_category": [{"category": c, "outcome": o, "files": n} for (c, o), n in sorted(by.items())]}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
