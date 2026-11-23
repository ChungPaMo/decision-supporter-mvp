"""Bounded XLSX inspection and opt-in parsing of a single original table."""
from contextlib import contextmanager
import hashlib
import io
import os
import re
import zipfile

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.utils.cell import range_boundaries
from openpyxl.xml.functions import fromstring, iterparse

from app.ingest.mapping import norm_header
from app.ingest.parsing import (FileError, HeaderCol, MAX_BYTES, MAX_ROWS, ParsedFile, ParsedSheet,
                                RawRow, _cell_from_openpyxl, _empty)
from contracts.interfaces.xlsx import XlsxLayoutReply, XlsxSheetLayout, XlsxTableSelection


MAX_COLUMNS = 64
MAX_CELLS = 2_000_000
MAX_EXPANDED_BYTES = 50 * 1024 * 1024
SENSITIVE_PREVIEW = re.compile(r'@|(?:\+?[0-9][0-9 ()-]{7,}[0-9])')
WORKSHEET_CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'


def xlsx_identity(filename: str, data: bytes) -> tuple[str, str]:
    name = os.path.basename(filename.replace('\\', '/'))
    if not name.lower().endswith('.xlsx'):
        raise FileError('UNSUPPORTED_TYPE', 'Table range selection requires XLSX.', 415)
    if not data:
        raise FileError('FILE_EMPTY', 'Empty workbook.')
    if len(data) > MAX_BYTES:
        raise FileError('FILE_TOO_LARGE', 'Workbook exceeds 10 MiB.', 413)
    return name, hashlib.sha256(data).hexdigest()


def preflight(data: bytes) -> None:
    # A merge can expand independently of the declared worksheet dimensions.
    # Check the actual worksheet parts before the layout reader expands them.
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(part.file_size for part in archive.infolist()) > MAX_EXPANDED_BYTES:
            raise FileError('ANALYSIS_LIMIT', 'Expanded workbook exceeds 50 MiB.', 413)
        manifest = fromstring(archive.read('[Content_Types].xml'))
        parts = [element.attrib['PartName'].lstrip('/') for element in manifest
                 if element.attrib.get('ContentType') == WORKSHEET_CONTENT_TYPE and 'PartName' in element.attrib]
        if len(parts) > 8:
            raise FileError('ANALYSIS_LIMIT', 'At most eight worksheets.', 413)
        merge_cells = 0
        for part in parts:
            with archive.open(part) as stream:
                for _, elem in iterparse(stream):
                    if elem.tag.endswith('}mergeCell'):
                        c1, r1, c2, r2 = range_boundaries(elem.attrib['ref'])
                        merge_cells += (r2 - r1 + 1) * (c2 - c1 + 1)
                        if c2 > MAX_COLUMNS or r2 > MAX_ROWS or merge_cells > MAX_CELLS:
                            raise FileError('ANALYSIS_LIMIT', 'Merged ranges exceed workbook limits.', 413)
                    elem.clear()
    dimensions = openpyxl.load_workbook(io.BytesIO(data), read_only=True, keep_links=False)
    try:
        check_dimensions(dimensions)
    finally:
        dimensions.close()


def check_dimensions(workbook) -> None:
    dimensions = [(sheet.max_row or 0, sheet.max_column or 0) for sheet in workbook.worksheets]
    if (len(dimensions) > 8 or any(rows > MAX_ROWS or cols > MAX_COLUMNS for rows, cols in dimensions)
            or sum(rows * cols for rows, cols in dimensions) > MAX_CELLS):
        raise FileError('ANALYSIS_LIMIT', 'Workbook exceeds eight sheets, 100000 rows, 64 columns or 2 million cells.', 413)


@contextmanager
def workbook_layout(data: bytes):
    try:
        preflight(data)
        workbook = openpyxl.load_workbook(io.BytesIO(data), data_only=False, keep_links=False)
    except FileError:
        raise
    except Exception:
        raise FileError('XLSX_CORRUPT', 'Cannot read workbook structure.') from None
    try:
        check_dimensions(workbook)
        yield workbook
    finally:
        workbook.close()


def visible_sheet(workbook, name: str):
    if not any(sheet.title == name and sheet.sheet_state == 'visible' for sheet in workbook.worksheets):
        raise FileError('XLSX_SHEET_INVALID', 'Choose an exact visible worksheet name.')
    return workbook[name]


def intersects(span, r1: int, r2: int, c1: int, c2: int) -> bool:
    return span.min_row <= r2 and r1 <= span.max_row and span.min_col <= c2 and c1 <= span.max_col


def preview_cell(cell, row: int, col: int) -> dict:
    if isinstance(cell, MergedCell):
        kind, value = 'merged', None
    elif cell.data_type in ('f', 'e'):
        kind, value = ('formula' if cell.data_type == 'f' else 'error'), None
    else:
        parsed = _cell_from_openpyxl(cell)
        kind, value = parsed.kind, parsed.value
        if value is not None:
            value = '[REDACTED]' if SENSITIVE_PREVIEW.search(value) else value[:80]
    return {'row': row, 'col': col, 'kind': kind, 'value': value}


def inspect_xlsx(filename: str, data: bytes, sheet_name: str | None,
                 row_start: int, row_limit: int, col_start: int, col_limit: int) -> XlsxLayoutReply:
    name, sha = xlsx_identity(filename, data)
    with workbook_layout(data) as workbook:
        sheets = [XlsxSheetLayout(name=sheet.title, visibility=sheet.sheet_state,
                                  max_row=sheet.max_row, max_col=sheet.max_column) for sheet in workbook.worksheets]
        if sheet_name is None:
            return XlsxLayoutReply(filename=name, source_sha256=sha, sheets=sheets)
        sheet = visible_sheet(workbook, sheet_name)
        if row_start > sheet.max_row or col_start > sheet.max_column:
            raise FileError('XLSX_RANGE_INVALID', 'Preview starts outside the worksheet.')
        last_row = min(row_start + row_limit - 1, sheet.max_row)
        last_col = min(col_start + col_limit - 1, sheet.max_column)
        merged = sorted(str(span) for span in sheet.merged_cells.ranges
                        if intersects(span, row_start, last_row, col_start, last_col))
        hidden = {col for dimension in sheet.column_dimensions.values() if dimension.hidden
                  for col in range(max(dimension.min or 1, col_start), min(dimension.max or 1, last_col) + 1)}
        cells = [preview_cell(cell, row, col)
                 for row, strip in enumerate(sheet.iter_rows(min_row=row_start, max_row=last_row, min_col=col_start,
                                                            max_col=last_col), row_start)
                 for col, cell in enumerate(strip, col_start)]
        return XlsxLayoutReply(filename=name, source_sha256=sha, sheets=sheets,
                               window={'sheet': sheet.title, 'first_row': row_start, 'last_row': last_row,
                                       'first_col': col_start, 'last_col': last_col, 'cells': cells,
                                       'hidden_columns': sorted(hidden), 'merged_ranges': merged[:200],
                                       'merges_truncated': len(merged) > 200})


def parse_selected_xlsx(filename: str, data: bytes, selection: XlsxTableSelection) -> ParsedFile:
    name, sha = xlsx_identity(filename, data)
    if sha != selection.source_sha256:
        raise FileError('XLSX_SOURCE_CHANGED', 'The selection belongs to different workbook bytes.', 409)
    c1, c2 = selection.first_col, selection.last_col
    width = c2 - c1 + 1
    if width * (selection.data_end_row - selection.data_start_row + 2) > MAX_CELLS:
        raise FileError('ANALYSIS_LIMIT', 'Selected table exceeds 2 million cells.', 413)

    with workbook_layout(data) as workbook:
        sheet = visible_sheet(workbook, selection.sheet)
        if selection.data_end_row > sheet.max_row or c2 > sheet.max_column:
            raise FileError('XLSX_RANGE_INVALID', 'Selected table extends outside the worksheet.')
        if any(intersects(span, selection.header_row, selection.header_row, c1, c2)
               or intersects(span, selection.data_start_row, selection.data_end_row, c1, c2)
               for span in sheet.merged_cells.ranges):
            raise FileError('XLSX_MERGED_RANGE', 'Select a leaf header and data cells outside merged ranges.')
        header = []
        for col in range(c1, c2 + 1):
            cell = sheet.cell(selection.header_row, col)
            if cell.data_type in ('f', 'e'):
                raise FileError('XLSX_HEADER_INVALID', 'Header cells must not be formulas or spreadsheet errors.')
            header.append(HeaderCol(col, (_cell_from_openpyxl(cell).value or '').strip() or None))
        keys = [norm_header(col.name) for col in header if col.name]
        if not keys or len(keys) != len(set(keys)) or any(not key for key in keys):
            raise FileError('XLSX_HEADER_INVALID', 'Choose a header with unique, nonempty normalized labels.')
        if any(len(col.display) > 200 for col in header):
            raise FileError('ANALYSIS_LIMIT', 'Header labels are limited to 200 characters.', 413)

    try:
        cached = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
        try:
            rows = []
            for row, strip in enumerate(cached[selection.sheet].iter_rows(min_row=selection.data_start_row,
                                       max_row=selection.data_end_row, min_col=c1, max_col=c2), selection.data_start_row):
                cells = [_cell_from_openpyxl(cell) for cell in strip]
                if any(not _empty(cell.value) for cell in cells):
                    rows.append(RawRow(row, cells))
        finally:
            cached.close()
    except Exception:
        raise FileError('XLSX_CORRUPT', 'Cannot read selected cell values.') from None
    if not rows:
        raise FileError('XLSX_RANGE_INVALID', 'Selected table has no nonblank cached data rows.')
    parsed = ParsedSheet(selection.sheet, [selection.header_row], header, rows, width, explicit_range=True)
    return ParsedFile(name, 'xlsx', len(data), sha, [parsed], table_selection=selection)
