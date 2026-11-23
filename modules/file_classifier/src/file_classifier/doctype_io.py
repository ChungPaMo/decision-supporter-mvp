"""엑셀·CSV 파일 내용(bytes)을 받아 문서 종류를 돌려준다. 서버가 여러 파일을 한꺼번에 분류할 때 쓴다.

파일을 저장하지 않고 외부로 보내지 않는다. 낱말 사전(doctype.py)만 쓰므로 torch 가 필요 없다.
"""
from __future__ import annotations

import csv
import io

from .doctype import UNKNOWN, VERSION, classify_workbook

MAX_ROWS, MAX_COLS, MAX_SHEETS = 60, 60, 20
REVIEW = "확인 필요"


def read_sheets(filename: str, data: bytes) -> list[tuple[str | None, list[list]]]:
    """앞쪽 60행·60열만 읽는다. 분류는 제목·열 이름·항목 이름으로 하므로 그 뒤는 필요 없다."""
    if filename.lower().endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        return [(None, [row[:MAX_COLS] for _, row in zip(range(MAX_ROWS), csv.reader(io.StringIO(text)))])]
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sheets = []
        for ws in wb.worksheets[:MAX_SHEETS]:
            rows = [["" if v is None else str(v) for v in row]
                    for row in ws.iter_rows(min_row=1, max_row=MAX_ROWS, max_col=MAX_COLS, values_only=True)]
            sheets.append((ws.title, rows))
        return sheets
    finally:
        wb.close()


def classify_bytes(filename: str, data: bytes) -> dict:
    """파일 하나의 결과. 읽지 못한 파일은 예외를 던지지 않고 category='확인 필요'와 이유를 돌려준다."""
    try:
        verdict = classify_workbook(read_sheets(filename, data))
    except Exception as exc:  # 깨진 파일, 암호가 걸린 파일, 엑셀이 아닌 파일
        return {"file": filename, "category": REVIEW, "confidence": "낮음", "score": 0.0, "runner_up": None,
                "reason": f"파일을 읽지 못했습니다 ({type(exc).__name__}).", "evidence": [], "readable": False}
    return {"file": filename, "category": REVIEW if verdict.needs_review else verdict.category, "confidence": verdict.confidence,
            "score": round(float(verdict.score), 2), "runner_up": verdict.runner_up, "reason": verdict.reason,
            "evidence": list(verdict.evidence)[:8], "readable": True}


__all__ = ["REVIEW", "UNKNOWN", "VERSION", "classify_bytes", "read_sheets"]
