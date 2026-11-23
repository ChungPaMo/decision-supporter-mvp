"""Bounded local profiling. No model calls, approval, persistent files or raw row output."""
from collections import Counter
from dataclasses import dataclass
from datetime import date
import csv
import hashlib
import io
import json
import re
import zipfile

from contracts.interfaces.ingestion import ColumnProfile, ProfileReply, ProfileSheet, ValueExample
from contracts.interfaces.xlsx import XlsxTableSelection
from app.ingest.mapping import norm_header
from app.ingest.parsing import Cell, FileError, MAX_BYTES, ParsedFile, detect_delimiter, detect_encoding, parse_file
from app.ingest.validation import MasterData, normalize_unit, parse_qty
from app.ingest.xlsx_layout import MAX_CELLS, MAX_COLUMNS, parse_selected_xlsx

MAX_DISTINCT = 2048
MAX_EXAMPLES = 3
CODE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$')
SENSITIVE = re.compile(r'@|(?:\+?[0-9][0-9 ()-]{7,}[0-9])|(?:[0-9]{6}-?[0-9]{7})')


@dataclass(frozen=True)
class ScopedMaster:
    dataset_id: str
    data: MasterData


def check_scope(dataset_id: str, master: ScopedMaster | None):
    if master is not None and master.dataset_id != dataset_id:
        raise FileError('DATASET_MISMATCH', 'Reference master belongs to another dataset.', 409)


def master_digest(master):
    if master is None:
        return None
    body = {'dataset_id': master.dataset_id,
            'products': sorted((key, item.base_unit) for key, item in master.data.products.items()),
            'materials': sorted((key, item.base_unit) for key, item in master.data.materials.items())}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def csv_rows(data: bytes):
    """Yield original physical record start lines; do not keep all CSV rows in memory."""
    encoding = detect_encoding(data)
    with io.TextIOWrapper(io.BytesIO(data), encoding=encoding, newline='') as stream:
        first = next((line for line in stream if line.strip()), '')
        delimiter = detect_delimiter(first)
        stream.seek(0)
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        previous = 0
        try:
            for row in reader:
                start = previous + 1
                previous = reader.line_num
                yield start, row
        except csv.Error:
            raise FileError('CSV_MALFORMED', 'Malformed CSV; repair quoting and row structure.') from None


def parse_analysis_file(filename: str, data: bytes, selection: XlsxTableSelection | None = None) -> ParsedFile:
    if selection is not None:
        return parse_selected_xlsx(filename, data, selection)
    # Preflight limits before the existing materializing parser allocates cells.
    if len(data) > MAX_BYTES:
        raise FileError('FILE_TOO_LARGE', 'Analysis file exceeds 10 MiB.', 413)
    if filename.lower().endswith('.csv') and data:
        cells = 0
        header_seen = False
        for _, row in csv_rows(data):
            if not header_seen and any(value.strip() for value in row):
                header_seen = True
                if any(len(value) > 200 for value in row):
                    raise FileError('ANALYSIS_LIMIT', 'Header labels are limited to 200 characters.', 413)
            cells += len(row)
            if len(row) > MAX_COLUMNS or cells > MAX_CELLS:
                raise FileError('ANALYSIS_LIMIT', 'At most 64 columns and 2 million cells per analysis file.', 413)
    elif filename.lower().endswith('.xlsx') and zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 50 * 1024 * 1024:
                raise FileError('ANALYSIS_LIMIT', 'Expanded workbook exceeds analysis limit.', 413)
        import openpyxl
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            try:
                if len(workbook.worksheets) > 8 or any((sheet.max_column or 0) > MAX_COLUMNS for sheet in workbook.worksheets) or sum(
                        (sheet.max_row or 0) * (sheet.max_column or 0) for sheet in workbook.worksheets) > MAX_CELLS:
                    raise FileError('ANALYSIS_LIMIT', 'Workbook dimensions exceed analysis limits.', 413)
            finally:
                workbook.close()
        except FileError:
            raise
        except Exception:
            raise FileError('XLSX_CORRUPT', 'Cannot read workbook metadata.') from None
    parsed = parse_file(filename, data)
    if any(len(header.display) > 200 for sheet in parsed.sheets for header in sheet.header):
        raise FileError('ANALYSIS_LIMIT', 'Header labels are limited to 200 characters.', 413)
    return parsed


def value_formats(value: str) -> tuple[bool, bool, str | None, str | None]:
    numeric = parse_qty(Cell(value.removeprefix('-'), 'text'))[0] is not None
    code = CODE.fullmatch(value) is not None
    date_format = None
    for pattern, label in ((r'([0-9]{4})-([0-9]{1,2})(?:-([0-9]{1,2}))?', 'ISO'),
                           (r'([0-9]{4})/([0-9]{1,2})(?:/([0-9]{1,2}))?', 'SLASH'),
                           (r'([0-9]{4})([0-9]{2})([0-9]{2})?', 'COMPACT')):
        match = re.fullmatch(pattern, value)
        if match:
            year, month, day = match.groups()
            try:
                date(int(year), int(month), int(day or '1'))
            except ValueError:
                continue
            date_format = label + ('_DATE' if day else '_MONTH')
            break
    unit = normalize_unit(value) or ('팩 (policy required)' if value == '팩' else None)
    return numeric, code, date_format, unit


def profile(parsed: ParsedFile, dataset_id: str, master: ScopedMaster | None = None, *, include_samples=False) -> ProfileReply:
    check_scope(dataset_id, master)
    sheets = []
    for sheet in parsed.sheets:
        columns = []
        for index, header in enumerate(sheet.header):
            counts, previews, formats, date_formats, units = Counter(), {}, Counter(), Counter(), set()
            format_cache = {}
            empty = product_matches = material_matches = 0
            distinct_exact = True
            anomalies = set()
            for row in sheet.rows:
                cell = row.cells[index] if index < len(row.cells) else Cell(None, 'empty')
                value = (cell.value or '').strip()
                if len(row.cells) != len(sheet.header):
                    anomalies.add('ROW_WIDTH_MISMATCH')
                if not value:
                    empty += 1
                    continue
                # Hash keys bound retained string sizes, with exactness explicitly reported at saturation.
                key = hashlib.sha256(value.encode()).hexdigest()
                if key in counts or len(counts) < MAX_DISTINCT:
                    counts[key] += 1
                    if include_samples and key not in previews:
                        previews[key] = '[REDACTED]' if SENSITIVE.search(value) else value[:48]
                else:
                    distinct_exact = False
                if len(value) > 128:
                    anomalies.add('LONG_VALUE')
                if value.startswith(('=', '#REF!', '#VALUE!', '#DIV/0!')):
                    anomalies.add('FORMULA_OR_SPREADSHEET_ERROR')
                match = format_cache.get(value)
                if match is None:
                    match = value_formats(value) if len(value) <= 128 else (False, False, None, None)
                    if len(format_cache) < 4096 and len(value) <= 128:
                        format_cache[value] = match
                numeric, code, date_format, unit = match
                formats['DECIMAL'] += numeric
                formats['CODE'] += code
                formats['DATE'] += date_format is not None
                formats['STRING'] += True
                if date_format:
                    date_formats[date_format] += 1
                if unit and len(units) < 8:
                    units.add(unit)
                if master:
                    product_matches += value in master.data.products
                    material_matches += value in master.data.materials
            n = len(sheet.rows)
            non_null = n - empty
            types = [key for key in ('DECIMAL', 'CODE', 'DATE') if non_null and formats[key] == non_null] + ['STRING']
            reasons = []
            if not master:
                reasons.append('APPROVED_MASTER_NOT_PROVIDED')
            if not non_null:
                reasons.append('EMPTY_COLUMN')
            if non_null and any(0 < formats[key] < non_null for key in ('DECIMAL', 'DATE')):
                reasons.append('MIXED_FORMATS')
            if 'CODE' in types and 'DECIMAL' in types:
                reasons.append('NUMERIC_CODE_AMBIGUITY')
            if not distinct_exact:
                reasons.append('DISTINCT_COUNT_IS_LOWER_BOUND')
            if len(types) == 1:
                reasons.append('SEMANTIC_ROLE_UNRESOLVED')
            columns.append(ColumnProfile(col=header.col, column=header.display[:200], normalized_column=norm_header(header.display)[:200],
                total_rows=n, empty_count=empty, empty_ratio=empty / n if n else 0, non_null_ratio=non_null / n if n else 0,
                distinct_count=len(counts), distinct_count_is_exact=distinct_exact,
                example_values=[ValueExample(value=previews[key], count=count) for key, count in counts.most_common(MAX_EXAMPLES)] if include_samples else [],
                type_candidates=types, format_match_rates={key: formats[key] / non_null if non_null else 0 for key in ('DECIMAL', 'CODE', 'DATE', 'STRING')},
                known_product_match_ratio=product_matches / non_null if master and non_null else (0 if master else None),
                known_material_match_ratio=material_matches / non_null if master and non_null else (0 if master else None),
                date_formats=dict(sorted(date_formats.items())), unit_candidates=sorted(units), anomalies=sorted(anomalies), uncertainty_reasons=reasons))
        sheets.append(ProfileSheet(sheet=sheet.name, row_count=len(sheet.rows), columns=columns))
    return ProfileReply(dataset_id=dataset_id, source_sha256=parsed.sha256, master_scope=master.dataset_id if master else None,
                        master_digest=master_digest(master), samples_included=include_samples, sheets=sheets,
                        table_selection=parsed.table_selection)
