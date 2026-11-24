"""Scheduled receipt staging and append-only approval through the batch transaction."""
from collections import Counter
from decimal import Decimal
import hashlib
import json

from pydantic import ValidationError
from sqlalchemy import text

from app.errors import ApiError, ErrorCode
from app.ingest.parsing import FileError, col_letter, parse_file
from app.ingest.pipeline import (FieldMappingOut, FileOut, IssueOut, LocationOut, MappingHoldOut,
                                 PreviewOut, ReceiptRevisionRecordOut, SheetOut)
from app.ingest.validation import normalize_unit
from app.ingest.validation_supply import parse_date
from contracts.interfaces.receipts import ReceiptRevisionInput


ENTITY = 'scheduled_receipt'
FIELDS = ReceiptRevisionInput.model_fields
REQUIRED = {name for name, spec in FIELDS.items() if spec.is_required()}

APPROVED_RECEIPTS = """
    FROM scheduled_receipt_revision AS r
    JOIN import_batch AS b ON b.batch_id = r.batch_id AND b.dataset_id = r.dataset_id
    WHERE r.dataset_id = :dataset_id AND b.entity = 'scheduled_receipt'
          AND b.status = 'APPROVED' AND b.blocking_error_count = 0
          AND b.approved_at IS NOT NULL AND b.result_digest IS NOT NULL
"""


def installed(c) -> bool:
    present = c.execute(text("SELECT to_regclass('scheduled_receipt_revision') IS NOT NULL")).scalar_one()
    revision = c.execute(text('SELECT version_num FROM public.alembic_version')).scalar_one()
    if revision == '0009' and not present:
        return False
    if revision == '0010' and present:
        return True
    raise ApiError(500, ErrorCode.PERSISTENCE_ERROR, 'Scheduled receipt schema is inconsistent.')


def _current(c, dataset_id, rows):
    orders = sorted({r.po_id for r in rows})
    if not orders:
        return []
    return c.execute(text('''
        SELECT DISTINCT ON (r.receipt_key) r.receipt_key, r.po_id, r.po_line_id, r.revision,
            r.material_id, r.unit, r.expected_date, r.effective_date, r.ordered_qty, r.received_qty, r.status
        ''' + APPROVED_RECEIPTS + '''
        AND r.po_id = ANY(CAST(:orders AS text[]))
        ORDER BY r.receipt_key, r.revision DESC
    '''), {'dataset_id': dataset_id, 'orders': orders}).mappings().all()


def revision_issues(rows, current, material_units):
    by_key = {r['receipt_key']: r for r in current}
    keys = Counter(r.receipt_key for r in rows)
    modes = {}
    for r in current:
        modes.setdefault(r['po_id'], set()).add(r['po_line_id'] is not None)
    for r in rows:
        modes.setdefault(r.po_id, set()).add(r.po_line_id is not None)
    for r in rows:
        previous = by_key.get(r.receipt_key)
        if material_units.get(r.material_id) != r.unit:
            yield r, 'RECEIPT_MATERIAL_OR_UNIT_MISMATCH'
        elif keys[r.receipt_key] != 1 or len(modes[r.po_id]) > 1:
            yield r, 'RECEIPT_DUPLICATE_PO'
        elif previous is None and (r.revision != 1 or r.status != 'OPEN'):
            yield r, 'RECEIPT_INITIAL_REVISION_INVALID'
        elif previous is not None and (
            r.revision != previous['revision'] + 1 or r.effective_date < previous['effective_date']
            or r.material_id != previous['material_id'] or r.unit != previous['unit']
            or Decimal(r.received_qty) < previous['received_qty'] or previous['status'] == 'CANCELLED'
            or previous['received_qty'] == previous['ordered_qty']
        ):
            yield r, 'RECEIPT_REVISION_INVALID'


def _issues(tx, dataset_id, records):
    return revision_issues(records, _current(tx.c, dataset_id, records),
                           {m.material_id: m.base_unit for m in tx.list_known_materials()})


def _mapping(sheet, overrides):
    mapping = []
    for field in FIELDS:
        selected = overrides.get(field)
        hits = [h for h in sheet.header if h.name == (field if selected is None else selected)]
        if selected is not None and not hits:
            hits = [h for h in sheet.header if col_letter(h.col) == selected]
        if len(hits) > 1 or (not hits and (selected is not None or field in REQUIRED)):
            return []
        if hits:
            col = hits[0]
            mapping.append(FieldMappingOut(field=field, col=col.col, header=col.display, review_required=False,
                                           method='USER_OVERRIDE' if selected is not None else 'ALIAS_STRONG'))
    return mapping if len({m.col for m in mapping}) == len(mapping) else []


def _record(sheet, row, mapping):
    raw = [cell.value for cell in row.cells]
    source = json.dumps({'sheet': sheet, 'row': row.row, 'cells': raw}, ensure_ascii=False, separators=(',', ':'))
    values = {m.field: row.cells[m.col - 1] for m in mapping if m.col <= len(row.cells)
              and row.cells[m.col - 1].value not in ('', None)}
    data = {field: cell.value for field, cell in values.items()}
    for field in ('expected_date', 'effective_date'):
        if field in values:
            data[field], error = parse_date(values[field])
            if error:
                raise ValueError('Invalid receipt dates')
    if 'unit' in data:
        data['unit'] = normalize_unit(data['unit'])
    return ReceiptRevisionRecordOut(**data, location=LocationOut(sheet=sheet, row=row.row),
                                    source_row_sha256=hashlib.sha256(source.encode()).hexdigest())


def preview(tx, dataset_id, filename, data, default_unit, overrides, sheet_filter):
    if not installed(tx.c):
        raise ApiError(501, ErrorCode.PERSISTENCE_DISABLED, 'Scheduled receipts require schema revision 0010.')
    if default_unit is not None:
        raise ApiError(422, ErrorCode.REQUEST_INVALID, 'Each scheduled receipt must supply its own unit.')
    parsed = parse_file(filename, data)
    sheets = [s for s in parsed.sheets if sheet_filter is None or s.name == sheet_filter]
    if len(sheets) != 1:
        raise FileError('REQUEST_INVALID', 'Select exactly one sheet for a scheduled receipt batch.')
    sheet = sheets[0]
    mapping = _mapping(sheet, overrides or {})
    records, issues = [], []
    if mapping:
        for row in sheet.rows:
            try:
                records.append(_record(sheet.name, row, mapping))
            except (ValidationError, ValueError):
                issues.append(IssueOut(severity='ERROR', code='RECEIPT_ROW_INVALID',
                                       message='Invalid order ID, revision, date, quantity, unit or state.',
                                       location=LocationOut(sheet=sheet.name, row=row.row)))
        issues.extend(IssueOut(severity='ERROR', code=code, message='Receipt conflicts with approved data or scope.',
                               location=record.location) for record, code in _issues(tx, dataset_id, records))
    hold = not mapping or not sheet.rows
    invalid_rows = {i.location.row for i in issues}
    valid_records = [record for record in records if record.location.row not in invalid_rows]
    mapped_columns = {m.col for m in mapping}
    return PreviewOut(entity=ENTITY, file=FileOut(name=parsed.filename, format=parsed.format,
                      size_bytes=parsed.size_bytes, sha256=parsed.sha256, meta=parsed.meta),
                      status='MAPPING_HOLD' if hold else 'HAS_ERRORS' if issues else 'READY_FOR_APPROVAL',
                      master_data_checked=True, blocking_error_count=len(issues), warning_count=0,
                      sheets=[SheetOut(name=sheet.name, status='HOLD' if hold else 'MAPPED',
                                       header_rows=sheet.header_rows, data_rows=len(sheet.rows), mapping=mapping,
                                       unmapped_headers=[h.display for h in sheet.header if h.col not in mapped_columns],
                                       holds=[MappingHoldOut(code='RECEIPT_MAPPING_HOLD',
                                                              message='Use unique receipt template headers or explicit overrides.')] if hold else [],
                                       validated=not hold, error_rows=len(invalid_rows),
                                       valid_records=len(valid_records), records=valid_records, issues=issues)])


def commit(tx, batch_id, actor, records):
    dataset_id = tx.get_batch(batch_id).dataset_id
    for order in sorted({r.po_id for r in records}):
        tx.c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 763002))'),
                     {'key': f'{dataset_id}:{order}'})
    if any(_issues(tx, dataset_id, records)):
        raise ApiError(409, ErrorCode.RESULT_CHANGED, 'Scheduled receipt history changed. Revalidate the batch.')
    tx.mark_approved(batch_id, actor, len(records))
    for record in records:
        tx.c.execute(text('''
            INSERT INTO scheduled_receipt_revision
                (dataset_id, batch_id, po_id, po_line_id, revision, material_id, expected_date, effective_date,
                 ordered_qty, received_qty, unit, supplier_id, status, source_sheet, source_row_no, source_row_sha256)
            VALUES (:dataset_id, :batch_id, :po_id, :po_line_id, :revision, :material_id, :expected_date, :effective_date,
                    :ordered_qty, :received_qty, :unit, :supplier_id, :status, :source_sheet, :source_row_no, :source_row_sha256)
        '''), {**record.model_dump(exclude={'location'}), 'dataset_id': dataset_id, 'batch_id': batch_id,
               'source_sheet': record.location.sheet, 'source_row_no': record.location.row})
    return len(records)
