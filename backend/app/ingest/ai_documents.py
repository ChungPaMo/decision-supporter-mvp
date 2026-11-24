"""Document review adapters. Page coordinates and original cells remain distinct."""
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import re

from pydantic import TypeAdapter, ValidationError

from app.ingest.mapping import ENTITY_FIELDS, norm_header
from app.ingest.xlsx_layout import intersects, workbook_layout
from app.integrations.upstage import ProviderError, check_permission, extraction_fields
from contracts.interfaces.ai_ingestion import AIDocumentReply, DocumentTable, PagePoint
from contracts.mapping_review import finished_text, strict_json


COORDINATES = TypeAdapter(list[PagePoint])
CONTENT_KEYS = ('html', 'markdown', 'text')
MAX_TABLE_ROWS = 1000


def text_content(value):
    if not isinstance(value, dict) or any(key in value and not isinstance(value[key], str) for key in CONTENT_KEYS):
        raise ValueError
    content = {key: value[key] for key in CONTENT_KEYS if key in value}
    for text in content.values():
        text.encode('utf-8')  # Reject unpaired JSON surrogates before creating a response.
    return content


class TableMarkup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.cell_tag = None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            if self.table is not None:
                raise ValueError
            self.table = []
        elif tag == 'tr' and self.table is not None:
            if self.row is not None or len(self.table) >= MAX_TABLE_ROWS:
                raise ValueError
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            if self.cell is not None or len(self.row) >= 64:
                raise ValueError
            attributes = dict(attrs)
            sizes = [attributes.get(key, '1') for key in ('rowspan', 'colspan')]
            if any(not isinstance(v, str) or not re.fullmatch(r'[1-9][0-9]?', v) or int(v) > 64 for v in sizes):
                raise ValueError
            self.cell = ([], *map(int, sizes))
            self.cell_tag = tag
        elif tag == 'br' and self.cell is not None:
            self.cell[0].append(' ')

    def handle_data(self, data):
        if self.cell is not None:
            self.cell[0].append(data)

    def handle_endtag(self, tag):
        if tag == self.cell_tag and self.cell is not None:
            chunks, height, width = self.cell
            self.row.append((tag, ' '.join(''.join(chunks).split())[:200], height, width))
            self.cell = self.cell_tag = None
        elif tag == 'tr' and self.row is not None:
            if not self.row or self.cell is not None:
                raise ValueError
            self.table.append(self.row)
            self.row = None
        elif tag == 'table' and self.table is not None:
            if self.row is not None or not self.table or len(self.tables) >= 100:
                raise ValueError
            self.tables.append(self.table)
            self.table = None


def grid_summary(table):
    grid = {}
    head_depth = 0
    for row, cells in enumerate(table):
        if row == head_depth and all(tag == 'th' for tag, *_ in cells):
            head_depth += 1
        column = 0
        for _, value, height, width in cells:
            while (row, column) in grid:
                column += 1
            if column + width > 64 or row + height > len(table):
                raise ValueError
            for y in range(row, row + height):
                for x in range(column, column + width):
                    if (y, x) in grid:
                        raise ValueError
                    grid[y, x] = value if (y, x) == (row, column) else ''
            column += width
    width = 1 + max(x for _, x in grid)
    headers = [grid.get((max(0, head_depth - 1), x), '') for x in range(width)]
    return headers, len(table), width, head_depth


def table_shapes(reply):
    body = reply.body
    if 'content' in body:
        text_content(body['content'])
    elements = body.get('elements')
    if not isinstance(elements, list) or len(elements) > 3000:
        raise ValueError
    seen, shapes = set(), []
    for element in elements:
        if not isinstance(element, dict):
            raise ValueError
        identifier, page, category = element.get('id'), element.get('page'), element.get('category')
        if (type(identifier) is not int or identifier < 0 or identifier in seen or type(page) is not int
                or not 1 <= page <= (reply.run.usage.pages or 100) or not isinstance(category, str) or not category):
            raise ValueError
        seen.add(identifier)
        content = text_content(element.get('content', {}))
        raw_coordinates = element.get('coordinates', [])
        if not isinstance(raw_coordinates, list):
            raise ValueError
        coordinates = COORDINATES.validate_python(raw_coordinates)
        if len(coordinates) not in (0, 4):
            raise ValueError
        if category != 'table':
            continue
        parser = TableMarkup()
        parser.feed(content.get('html', ''))
        parser.close()
        if parser.table is not None or not parser.tables or len(shapes) + len(parser.tables) > 100:
            raise ValueError
        for table in parser.tables:
            headers, rows, columns, depth = grid_summary(table)
            shapes.append((DocumentTable(element_id=identifier, page=page, coordinates=coordinates, headers=headers,
                            row_count=rows, column_count=columns, reason='USER_RANGE_REQUIRED'), depth))
    return len(elements), shapes


def align_tables(data, shapes, selection):
    with workbook_layout(data) as workbook:
        sheets = [ws for ws in workbook if ws.sheet_state == 'visible']
        results = []
        for table, depth in shapes:
            signature = tuple(norm_header(value) for value in table.headers)
            reason = 'USER_RANGE_REQUIRED'
            matches = []
            if len(sheets) != 1:
                reason = 'AMBIGUOUS_WORKSHEETS'
            elif depth > 1 or not all(signature) or len(set(signature)) != len(signature):
                reason = 'AMBIGUOUS_HEADER'
            else:
                ws = sheets[0]
                for rownum, row in enumerate(ws.iter_rows(values_only=True), 1):
                    values = [norm_header(cell) if isinstance(cell, str) else '' for cell in row]
                    for start in range(len(values) - len(signature) + 1):
                        if tuple(values[start:start + len(signature)]) == signature:
                            matches.append((ws.title, rownum, start + 1))
                    if len(matches) > 1:
                        break
                if len(matches) != 1:
                    reason = 'AMBIGUOUS_HEADER' if matches else 'HEADER_NOT_FOUND'
                elif not table.coordinates:
                    reason = 'LOCATION_EVIDENCE_MISSING'
                else:
                    sheet, rownum, first_col = matches[0]
                    last_col = first_col + len(signature) - 1
                    if ((ws.row_dimensions.get(rownum) and ws.row_dimensions[rownum].hidden)
                            or any(intersects(span, rownum, rownum, first_col, last_col) for span in ws.merged_cells.ranges)):
                        results.append(table.model_copy(update={'reason': 'AMBIGUOUS_HEADER'}))
                        continue
                    if selection and (sheet, rownum, first_col, last_col) == (
                            selection.sheet, selection.header_row, selection.first_col, selection.last_col):
                        if table.row_count - 1 == selection.data_end_row - selection.data_start_row + 1:
                            results.append(table.model_copy(update={'range_status': 'USER_RANGE_MATCH', 'reason': 'USER_HEADER_AND_ROW_COUNT_MATCH',
                                'source_sheet': sheet, 'source_header_row': rownum, 'source_first_col': first_col}))
                            continue
                        reason = 'ROW_COUNT_MISMATCH'
                    results.append(table.model_copy(update={'reason': reason, 'source_sheet': sheet, 'source_header_row': rownum,
                                                            'source_first_col': first_col}))
                    continue
            results.append(table.model_copy(update={'reason': reason}))
        return results


def parse_document(settings, provider, source, data, kind, selection, *, requested):
    base = AIDocumentReply(dataset_id=source.dataset_id, source_sha256=source.source_sha256, status='DISABLED',
                           mode=settings.upstage_document_parse_mode, table_selection=selection)
    upstream = None
    try:
        check_permission(settings, 'parse', source, requested=requested)
        if kind == 'xlsx' and selection is None:
            with workbook_layout(data):
                pass
        upstream = provider.parse(source, requested=requested, data=data, kind=kind)
        count, shapes = table_shapes(upstream)
        tables = (align_tables(data, shapes, selection) if kind == 'xlsx' else
                  [table.model_copy(update={'reason': 'PAGE_COORDINATES_ONLY'}) for table, _ in shapes])
        status = 'REVIEW' if any(table.range_status == 'USER_RANGE_MATCH' for table in tables) else 'HOLD'
        return base.model_copy(update={'status': status, 'tables': tables, 'element_count': count, 'run': upstream.run})
    except ProviderError as exc:
        status = {'AI_DISABLED': 'DISABLED', 'SOURCE_NOT_APPROVED': 'BLOCKED', 'EXTERNAL_TRANSFER_NOT_APPROVED': 'BLOCKED'}.get(
            exc.code, 'UNAVAILABLE')
        return base.model_copy(update={'status': status, 'issue': exc.code, 'error_request_id': exc.request_id,
                                       'retry_after_seconds': exc.retry_after})
    except (ValueError, RecursionError):
        return base.model_copy(update={'status': 'HOLD', 'issue': 'UPSTAGE_RESPONSE_FORMAT', 'run': upstream.run if upstream else None})


@dataclass(frozen=True)
class ExtractionEvidence:
    """Trusted local output from source parsing and document-type confirmation."""
    dataset_id: str
    source_sha256: str
    detected_entity: str
    rows: dict[str, dict[str, str]]
    key_field: str


def equivalent(value, raw, kind):
    if kind == 'string':
        return isinstance(value, str) and value == raw
    if kind == 'boolean':
        return type(value) is bool and raw.casefold() in ({'true', '1'} if value else {'false', '0'})
    if type(value) not in ((int,) if kind == 'integer' else (int, float)):
        return False
    try:
        original = Decimal(raw)
        return original.is_finite() and original == Decimal(str(value))
    except InvalidOperation:
        return False


def validate_extraction(upstream, fields, required, evidence):
    raw, unfinished = finished_text(upstream.body, upstream.endpoint)
    obj = strict_json(raw) if not unfinished else None
    if (not isinstance(obj, dict) or set(obj) != {'rows'} or not isinstance(obj['rows'], list)
            or len(obj['rows']) > MAX_TABLE_ROWS):
        raise ValueError
    # Upstage returns optional per-field locations via the additional_values tool.
    message = upstream.body['choices'][0]['message']
    locations = []
    for call in message.get('tool_calls') or []:
        function = call.get('function', {})
        if function.get('name') == 'additional_values':
            payload = function.get('arguments')
            payload = strict_json(payload) if isinstance(payload, str) else payload
            if isinstance(payload, dict) and isinstance(payload.get('rows'), list):
                locations = payload['rows']
                break
    issues = Counter()
    row_counts = Counter(row.get(evidence.key_field) for row in obj['rows']
                         if isinstance(row, dict) and isinstance(row.get(evidence.key_field), str))
    verified = []
    for index, row in enumerate(obj['rows']):
        if not isinstance(row, dict) or row.keys() - fields.keys():
            issues['ADDITIONAL_FIELD_OR_INVALID_ROW'] += 1
            continue
        key = row.get(evidence.key_field)
        if not isinstance(key, str) or row_counts.get(key) != 1 or key not in evidence.rows:
            issues['EXTRA_OR_DUPLICATE_ROW'] += 1
            continue
        if required - row.keys() or any(row[field] in (None, '') for field in required):
            issues['MISSING_FIELD'] += 1
            continue
        expected = evidence.rows[key]
        missing = {field for field in expected if expected[field]} - row.keys()
        if missing or any(field not in expected or not equivalent(value, expected[field], fields[field]) for field, value in row.items()):
            issues['VALUE_OR_TYPE_MISMATCH'] += 1
            continue
        points = locations[index] if index < len(locations) else None
        if not isinstance(points, dict) or not all(
            valid_location(points.get(field), expected[field], fields[field], upstream.run.usage.pages) for field in row
        ):
            issues['LOCATION_EVIDENCE_MISSING'] += 1
            continue
        verified.append(key)
    if set(evidence.rows) - row_counts.keys():
        issues['MISSING_ROW'] += len(set(evidence.rows) - row_counts.keys())
    return {'status': 'HOLD' if issues else 'REVIEW', 'issues': dict(issues), 'verified_row_keys': verified,
            'run': upstream.run, 'persisted': False}


def valid_location(value, original, kind, reported_pages):
    if (not isinstance(value, dict) or type(value.get('page')) is not int or not 1 <= value['page'] <= (reported_pages or 100)
            or not equivalent(value.get('_value'), original, kind)):
        return False
    try:
        return len(COORDINATES.validate_python(value.get('coordinates'))) == 4
    except ValidationError:
        return False


def extract_document(provider, source, *, requested, data, kind, entity, schema, evidence: ExtractionEvidence):
    fields, required = extraction_fields(schema)
    if (entity not in ENTITY_FIELDS or entity != evidence.detected_entity or evidence.dataset_id != source.dataset_id
            or evidence.source_sha256 != source.source_sha256):
        raise ProviderError('DOCUMENT_TYPE_OR_SCOPE_UNVERIFIED')
    if (fields.keys() - ENTITY_FIELDS[entity].keys() or fields.get(evidence.key_field) != 'string'
            or evidence.key_field not in required or not 1 <= len(evidence.rows) <= MAX_TABLE_ROWS):
        raise ProviderError('UNSUPPORTED_SCHEMA')
    result = provider.extract(source, requested=requested, data=data, kind=kind, schema=schema)
    try:
        return validate_extraction(result, fields, required, evidence)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError):
        raise ProviderError('UPSTAGE_RESPONSE_FORMAT', request_id=result.run.request_id) from None
