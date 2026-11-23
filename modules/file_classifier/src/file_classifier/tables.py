"""엑셀 시트에서 표가 어디에 있는지 찾는다 (머리글 행, 데이터 행 범위, 열 범위).

실제 사무실 엑셀은 1행이 머리글이 아니다. 위에 제목, 결재란, "작성일자: …" 같은 항목이 있고, 한 시트에 표가 여러 개
있기도 하다. 여기서는 모델 없이 칸의 모양(글자인가 숫자인가, 비었는가, 병합됐는가)만 보고 표 범위를 제안한다.

결과 좌표는 원본 시트 기준 1부터 시작하고 끝을 포함한다. 백엔드의 표 범위 선택(contracts.interfaces.xlsx.XlsxTableSelection)과
같은 뜻이므로 그대로 옮겨 쓸 수 있다. 제안일 뿐이며 사람이 확인해야 한다.

찾는 방법
    1. 머리글 후보: 비지 않은 칸이 2개 이상 이어지고 첫 칸이 글자인 행. 가로로 병합된 칸이 있으면 머리글이 아니다.
       바로 아래 행에 더 긴 줄이 있으면 그 행이 머리글이고, 지금 행은 표 위의 항목 줄이나 묶음 머리글이다.
    2. 바로 아래 행에 같은 열 범위의 값이 있어야 한다. (결재란은 아래가 비어 있어서 걸러진다)
    3. 데이터는 그 아래로, 열 범위 안이 모두 빈 행을 만날 때까지다.
    4. 마지막 행이 '합계', '계', 'Total' 로 시작하면 합계 행으로 보고 데이터에서 뺀다.
    5. 데이터가 2행 이상이어야 표로 본다. 열이 2개뿐이면 3행 이상이어야 한다. ("부서: 생산1팀" 같은 항목 줄을 표로 보지 않기 위해서다)
    6. 데이터를 따라 내려가다 더 긴 줄을 만나면, 지금까지는 표 위의 항목 줄들이었다고 보고 버린다.
"""
from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import asdict, dataclass

VERSION = "tables-0.1.0"
MAX_ROWS, MAX_COLS = 2000, 64
_NUMBER = re.compile(r"^[+-]?[\d,]*\.?\d+%?$")
_DATE = re.compile(r"^\d{4}[-./]\d{1,2}[-./]\d{1,2}")
_TOTAL = {"합계", "계", "총계", "소계", "total", "sum", "subtotal", "grandtotal"}


@dataclass(frozen=True)
class TableRange:
    sheet: str | None
    header_row: int
    data_start_row: int
    data_end_row: int
    first_col: int
    last_col: int
    total_row: int | None = None        # 합계 행이 있으면 그 행 번호 (데이터 범위에는 넣지 않는다)

    def as_dict(self) -> dict:
        return asdict(self)


def _kind(value) -> str:
    """칸의 모양: 'empty', 'text', 'value'(숫자·날짜·참거짓·수식)."""
    if value is None:
        return "empty"
    if isinstance(value, (bool, int, float, dt.date, dt.time)):
        return "value"
    text = str(value).strip()
    if not text:
        return "empty"
    if text.startswith("=") or _NUMBER.match(text) or _DATE.match(text):
        return "value"
    return "text"


def _runs(kinds: list[str]) -> list[tuple[int, int]]:
    """비지 않은 칸이 이어진 구간들 (0부터 시작, 끝 포함)."""
    out, start = [], None
    for i, k in enumerate(kinds + ["empty"]):
        if k != "empty" and start is None:
            start = i
        elif k == "empty" and start is not None:
            out.append((start, i - 1))
            start = None
    return out


def find_tables(rows: list[list], sheet: str | None = None, merged: set[tuple[int, int]] | None = None) -> list[TableRange]:
    """rows: 시트의 값 격자(위에서부터, 행마다 칸 목록). merged: 가로로 병합된 영역이 덮는 (행, 열) 좌표(1부터 시작).

    위에서 아래로 훑으며 표를 찾는다. 한 시트에 표가 여러 개면 모두 돌려준다.
    """
    merged = merged or set()
    grid = [[_kind(v) for v in list(row)[:MAX_COLS]] for row in rows[:MAX_ROWS]]
    width = max((len(r) for r in grid), default=0)
    grid = [r + ["empty"] * (width - len(r)) for r in grid]
    found: list[TableRange] = []
    taken = 0                                           # 이 행 번호(0부터)까지는 이미 표에 들어갔다
    for r in range(len(grid) - 1):
        if r < taken:
            continue
        for c1, c2 in _runs(grid[r]):
            if c2 - c1 < 1 or grid[r][c1] != "text":
                continue                                # 머리글의 첫 칸은 글자다. 뒤 칸은 '1, 2, 3'(기간 번호)처럼 숫자일 수 있다
            if any((r + 1, c + 1) in merged for c in range(c1, c2 + 1)):
                continue
            # 바로 아래 행에 더 긴 줄이 걸쳐 있으면 지금 행은 표 위의 항목 줄이나 묶음 머리글이고, 아래가 진짜 머리글이다
            if any(b - a > c2 - c1 for a, b in _runs(grid[r + 1]) if a <= c2 and b >= c1):
                continue
            span = range(c1, c2 + 1)
            # 지금 행에 날짜·숫자가 섞여 있고 바로 아래 행이 같은 폭의 글자뿐인 줄이면, 아래가 머리글이다 ("작성일자 2026-12-02 부서 …" 줄)
            if any(grid[r][c] != "text" for c in span) and any(
                    b - a >= c2 - c1 and all(grid[r + 1][c] == "text" for c in range(a, b + 1)) for a, b in _runs(grid[r + 1]) if a <= c2 and b >= c1):
                continue
            if not any(grid[r + 1][c] != "empty" for c in span):
                continue                                # 아래가 비어 있다 (결재란, 제목 줄)
            look = range(r + 1, min(r + 4, len(grid)))  # 첫 데이터 행이 듬성듬성할 수 있어 세 행까지 본다
            if max(sum(grid[i][c] != "empty" for c in span) for i in look) < max(2, (len(span) + 1) // 2):
                continue
            end, preamble = r + 1, False
            while end + 1 < len(grid) and any(grid[end + 1][c] != "empty" for c in span):
                if any(b - a > c2 - c1 for a, b in _runs(grid[end + 1]) if a <= c2 and b >= c1):
                    preamble = True                     # 아래에 더 긴 줄이 나왔다: 여기까지는 표 위의 항목 줄들이었다
                    break
                end += 1
            if preamble:
                continue
            total = None
            first_text = str(rows[end][c1]).strip().lower().replace(" ", "") if c1 < len(rows[end]) and rows[end][c1] is not None else ""
            if first_text in _TOTAL and end > r + 1:
                total, end = end + 1, end - 1
            n_rows, n_cols = end - r, c2 - c1 + 1
            if n_rows < 2 or (n_cols == 2 and n_rows < 3):
                continue                                # 데이터가 한 행뿐이면 표 위의 "항목 값" 두 줄과 구분할 수 없어 표로 보지 않는다
            found.append(TableRange(sheet, r + 1, r + 2, end + 1, c1 + 1, c2 + 1, total))
            taken = (total or end + 1)
            break
    return found


def find_tables_in_xlsx(data: bytes) -> list[TableRange]:
    """엑셀 파일 내용에서 보이는 시트의 표를 모두 찾는다. openpyxl 이 필요하다. 파일을 저장하거나 외부로 보내지 않는다."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), data_only=False)
    try:
        out: list[TableRange] = []
        for ws in wb.worksheets:
            if ws.sheet_state != "visible":
                continue
            rows = [list(row) for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, MAX_ROWS), max_col=min(ws.max_column, MAX_COLS), values_only=True)]
            merged = {(r, c) for span in ws.merged_cells.ranges if span.max_col > span.min_col
                      for r in range(span.min_row, span.max_row + 1) for c in range(span.min_col, span.max_col + 1)}
            out.extend(find_tables(rows, ws.title, merged))
        return out
    finally:
        wb.close()


__all__ = ["VERSION", "TableRange", "find_tables", "find_tables_in_xlsx"]
