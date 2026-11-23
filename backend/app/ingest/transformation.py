"""Allowlisted synthetic sales recipe, fused into a bounded streaming reduction.

No SQL, eval, Python expressions, automatic approval or module-owner algorithm imports.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, localcontext
import hashlib
import json
import os
import re

from contracts.interfaces.ingestion import (SalesTransformPolicy, SeparateReturns, SourceLocation, TransformedDemand,
    TransformIssue, TransformOperation, TransformReply, TransformSource)
from contracts.interfaces.xlsx import XlsxTableSelection
from app.contracts import CODE_PATTERN
from app.ingest.mapping import norm_header
from app.ingest.parsing import Cell, FileError, MAX_BYTES, col_letter
from app.ingest.profiling import MAX_COLUMNS, ScopedMaster, check_scope, csv_rows, master_digest, parse_analysis_file
from app.ingest.validation import parse_qty, restore_code

MAX_FILES = 8
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_TOTAL_ROWS = 250_000
MAX_GROUPS = 10_000
MAX_ISSUES = 100
MAX_TRACE = 5
CODE = re.compile(CODE_PATTERN)
DATE_PATTERNS = {'YYYY-MM-DD': r'([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})',
                 'YYYY/MM/DD': r'([0-9]{4})/([0-9]{1,2})/([0-9]{1,2})',
                 'YYYYMMDD': r'([0-9]{4})([0-9]{2})([0-9]{2})'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def decimal_text(value):
    return format(value, 'f').rstrip('0').rstrip('.') if '.' in format(value, 'f') else format(value, 'f')


def compile_recipe(policy):
    return [TransformOperation(operation=op, parameters=params) for op, params in [
        ('SELECT_COLUMNS', {'source_columns': policy.columns.model_dump()}),
        ('RENAME_COLUMNS', {'mapping': policy.columns.model_dump()}),
        ('NORMALIZE_DATE', {'source': 'order_date', 'formats': policy.date_formats, 'granularity': 'MONTH'}),
        ('NORMALIZE_UNIT', {'mapping': policy.unit_mapping, 'factor': policy.unit_factor}),
        ('FILTER_ROWS', {'include': policy.included_status, 'exclude': policy.excluded_status,
                         'separate': policy.separate_status, 'return_handling': policy.return_handling}),
        ('VALIDATE_REFERENCE', {'same_dataset_only': policy.dataset_id, 'when_master_missing': 'UNVERIFIED'}),
        ('GROUP_BY', {'fields': ['product_id', 'period'], 'duplicate_transaction': policy.duplicate_policy}),
        ('SUM_DECIMAL', {'field': 'quantity', 'result': 'demand_qty', 'scale_max': 4}),
    ]]


def resolve_columns(header, policy, first_col=None):
    if len(header) > MAX_COLUMNS or any(len(name) > 200 for name in header):
        raise FileError('ANALYSIS_LIMIT', 'Source header exceeds bounded recipe limits.', 413)
    resolved = {}
    for semantic, reference in policy.columns.model_dump().items():
        hits = ([index for index in range(len(header)) if col_letter(first_col + index) == reference]
                if first_col is not None else [])
        if not hits:
            hits = [index for index, name in enumerate(header) if name == reference]
        if not hits and first_col is None and re.fullmatch(r'[A-Z]{1,2}', reference):
            index = 0
            for char in reference:
                index = index * 26 + ord(char) - ord('A') + 1
            if 0 < index <= len(header):
                hits = [index - 1]
        if len(hits) != 1:
            raise FileError('TRANSFORM_MAPPING_HOLD', 'Required source column is missing or ambiguous: ' + semantic)
        resolved[semantic] = hits[0]
    if len(set(resolved.values())) != len(resolved):
        raise FileError('TRANSFORM_MAPPING_HOLD', 'Source column cannot fulfill two semantic roles.')
    if any(word in norm_header(header[resolved['order_date']]) for word in ('출고', 'ship')):
        raise FileError('TRANSFORM_POLICY_UNSUPPORTED', 'This policy requires order date, not shipping date.')
    if any(word in norm_header(header[resolved['quantity']]) for word in ('금액', '단가', 'price', 'amount', '반품')):
        raise FileError('TRANSFORM_POLICY_UNSUPPORTED', 'Quantity column contradicts synthetic normal-sales policy.')
    if any(word in norm_header(header[resolved['product_id']]) for word in ('자재', 'material')):
        raise FileError('TRANSFORM_POLICY_UNSUPPORTED', 'Product and material code semantics differ.')
    return resolved


def source_rows(filename, data, selection=None):
    if len(data) > MAX_BYTES:
        raise FileError('FILE_TOO_LARGE', 'Each source is limited to 10 MiB.', 413)
    if selection is None and filename.lower().endswith('.csv'):
        if not data:
            raise FileError('FILE_EMPTY', 'Empty source file.')
        rows = iter(csv_rows(data))
        header = next((row for _, row in rows if any(value.strip() for value in row)), None)
        if header is None:
            raise FileError('FILE_EMPTY', 'Source contains no header.')
        def records():
            for line, row in rows:
                if len(row) > MAX_COLUMNS:
                    raise FileError('ANALYSIS_LIMIT', 'At most 64 columns per row.', 413)
                if any(value.strip() for value in row):
                    yield line, [Cell(value, 'text') for value in row]
        yield '', [name.strip() for name in header], records(), None
    else:
        parsed = parse_analysis_file(filename, data, selection)
        for sheet in parsed.sheets:
            yield (sheet.name, [column.display for column in sheet.header],
                   ((row.row, row.cells) for row in sheet.rows), selection.first_col if selection else None)


def month(value, formats):
    for form in formats:
        match = re.fullmatch(DATE_PATTERNS[form], value)
        if match:
            try:
                parsed = date(*map(int, match.groups()))
                if 1990 <= parsed.year <= 2100:
                    return parsed.strftime('%Y-%m')
            except ValueError:
                pass
    return None


@dataclass
class Aggregate:
    quantity: Decimal = Decimal(0)
    count: int = 0
    locations: list[SourceLocation] = field(default_factory=list)


def transform(files: list[tuple[str, bytes]], policy: SalesTransformPolicy, master: ScopedMaster | None = None,
              *, offset=0, limit=500, selections: dict[int, XlsxTableSelection] | None = None) -> TransformReply:
    if not (0 <= offset and 1 <= limit <= 500):
        raise FileError('REQUEST_INVALID', 'Page bounds are offset>=0, limit=1..500.')
    result = transform_complete(files, policy, master, selections=selections)
    return result.model_copy(update={'offset': offset, 'limit': limit,
        'records': result.records[offset:offset + limit], 'returns': result.returns[offset:offset + limit]})


def transform_complete(files: list[tuple[str, bytes]], policy: SalesTransformPolicy,
                       master: ScopedMaster | None = None, *,
                       selections: dict[int, XlsxTableSelection] | None = None) -> TransformReply:
    """Complete bounded computation for persistence; API previews page the same result."""
    check_scope(policy.dataset_id, master)
    if not 1 <= len(files) <= MAX_FILES or sum(len(data) for _, data in files) > MAX_TOTAL_BYTES:
        raise FileError('ANALYSIS_LIMIT', 'At most 8 files / 50 MiB combined per transformation.', 413)
    selections = selections or {}
    if selections.keys() - range(len(files)):
        raise FileError('XLSX_RANGE_INVALID', 'Selection must identify an uploaded source index.')
    hashes = [hashlib.sha256(data).hexdigest() for _, data in files]
    if len(set(hashes)) != len(hashes):
        raise FileError('TRANSFORM_DUPLICATE_SOURCE', 'Identical source files cannot be aggregated twice.')
    groups, returns, sources, issues = {}, defaultdict(Decimal), [], []
    seen, dates = set(), {}
    counts = {'source_rows': 0, 'normal_included': 0, 'cancelled_excluded': 0, 'returns_separate': 0, 'error_rows': 0, 'aggregation_errors': 0}
    totals = {'normal': Decimal(0), 'cancelled': Decimal(0), 'returns': Decimal(0)}
    warnings = set()
    issues_total = 0
    if master is None:
        warnings.add('REFERENCES_UNVERIFIED_NO_APPROVED_MASTER')

    def error(code, location, field_name=None, *, aggregate=False):
        nonlocal issues_total
        counts['aggregation_errors' if aggregate else 'error_rows'] += 1
        issues_total += 1
        if len(issues) < MAX_ISSUES:
            issues.append(TransformIssue(code=code, location=location, field=field_name))

    with localcontext() as context:
        context.prec = 40  # Exact sum of bounded NUMERIC(18,4) inputs, no binary floats.
        for source_index, ((filename, data), sha) in enumerate(zip(files, hashes)):
            file_rows = 0
            selection = selections.get(source_index)
            for sheet_name, header, rows, first_col in source_rows(filename, data, selection):
                columns = resolve_columns(header, policy, first_col)
                source_columns = {key: index + (first_col or 1) for key, index in columns.items()}
                for row_number, cells in rows:
                    counts['source_rows'] += 1
                    file_rows += 1
                    if counts['source_rows'] > MAX_TOTAL_ROWS:
                        raise FileError('ANALYSIS_LIMIT', 'At most 250000 transaction rows per preview.', 413)
                    location = SourceLocation(source_index=source_index, sheet=sheet_name, row=row_number)
                    if len(cells) != len(header):
                        error('ROW_WIDTH_MISMATCH', location)
                        continue
                    values = {key: (cells[col].value or '').strip() for key, col in columns.items()}
                    missing = next((key for key, value in values.items() if not value), None)
                    if missing:
                        error('REQUIRED_VALUE_MISSING', location.model_copy(update={'col': source_columns[missing]}), missing)
                        continue
                    if any(len(value) > 128 for value in values.values()):
                        error('VALUE_TOO_LONG', location)
                        continue
                    status = values['status']
                    if status not in (policy.included_status, policy.excluded_status, policy.separate_status):
                        error('TRANSACTION_STATUS_UNKNOWN', location.model_copy(update={'col': source_columns['status']}), 'status')
                        continue
                    date_key = values['order_date']
                    period = dates.get(date_key) or month(date_key, policy.date_formats)
                    if period is None:
                        error('DATE_INVALID', location.model_copy(update={'col': source_columns['order_date']}), 'order_date')
                        continue
                    if len(dates) < 4096:
                        dates[date_key] = period
                    product, code_warning = restore_code(cells[columns['product_id']], 'product_id')
                    if code_warning:
                        # The user must resolve potentially lost leading zeroes; no silent repair in this recipe.
                        error('NUMERIC_PRODUCT_CODE_REQUIRES_REVIEW', location.model_copy(update={'col': source_columns['product_id']}), 'product_id')
                        continue
                    if not product or not CODE.fullmatch(product):
                        error('PRODUCT_CODE_INVALID', location.model_copy(update={'col': source_columns['product_id']}), 'product_id')
                        continue
                    if values['unit'] not in policy.unit_mapping:
                        error('UNIT_UNSUPPORTED_BY_POLICY', location.model_copy(update={'col': source_columns['unit']}), 'unit')
                        continue
                    if master:
                        known = master.data.products.get(product)
                        if known is None or known.base_unit != 'EA':
                            error('PRODUCT_REFERENCE_OR_UNIT_INVALID', location.model_copy(update={'col': source_columns['product_id']}), 'product_id')
                            continue
                    negative = values['quantity'].startswith('-')
                    qty, qty_error = parse_qty(Cell(values['quantity'].removeprefix('-'), 'text'))
                    if qty_error or (negative and status != policy.separate_status):
                        error(qty_error[0] if qty_error else 'NEGATIVE_NON_RETURN_QUANTITY',
                              location.model_copy(update={'col': source_columns['quantity']}), 'quantity')
                        continue
                    if not re.fullmatch(r'[1-9][0-9]{0,5}', values['line_id']):
                        error('TRANSACTION_LINE_INVALID', location.model_copy(update={'col': source_columns['line_id']}), 'line_id')
                        continue
                    key = (values['order_id'], values['line_id'])
                    if key in seen:
                        error('DUPLICATE_TRANSACTION_KEY', location)
                        continue
                    seen.add(key)
                    group_key = (product, period)
                    if len(groups) + len(returns) >= MAX_GROUPS and group_key not in groups and group_key not in returns:
                        raise FileError('ANALYSIS_LIMIT', 'Too many product/month groups.', 413)
                    if status == policy.included_status:
                        item = groups.setdefault(group_key, Aggregate())
                        item.quantity += qty
                        item.count += 1
                        if len(item.locations) < MAX_TRACE:
                            item.locations.append(location)
                        counts['normal_included'] += 1
                        totals['normal'] += qty
                    elif status == policy.excluded_status:
                        counts['cancelled_excluded'] += 1
                        totals['cancelled'] += qty
                    else:
                        counts['returns_separate'] += 1
                        totals['returns'] += qty
                        returns[group_key] += qty
            sources.append(TransformSource(source_index=source_index, filename=os.path.basename(filename.replace('\\', '/'))[:200],
                                           sha256=sha, row_count=file_rows, table_selection=selection))
        output = [TransformedDemand(product_id=product, period=period, demand_qty=decimal_text(item.quantity),
                   source_row_count=item.count, source_locations=item.locations) for (product, period), item in sorted(groups.items())]
        # The final aggregate must still satisfy the existing storage contract's precision/range.
        for record in output:
            if parse_qty(Cell(record.demand_qty, 'text'))[1]:
                error('MONTHLY_AGGREGATE_OUT_OF_RANGE', record.source_locations[0], 'quantity', aggregate=True)
        output_sum = sum((item.quantity for item in groups.values()), Decimal(0))
        separate = [SeparateReturns(product_id=p, period=m, return_qty=decimal_text(q)) for (p, m), q in sorted(returns.items())]
        reconciliation = {'scope': 'VALID_NORMAL_ROWS_ONLY', 'normal_included_qty': decimal_text(totals['normal']),
            'monthly_output_qty': decimal_text(output_sum), 'normal_quantity_conserved': output_sum == totals['normal'],
            'cancelled_qty_ignored': decimal_text(totals['cancelled']), 'returns_qty_separate': decimal_text(totals['returns']),
            'returns_not_subtracted': True}
    counts['monthly_demand_rows'] = len(output)
    if any(item.count > MAX_TRACE for item in groups.values()):
        warnings.add('SOURCE_LOCATIONS_TRUNCATED_TO_5_PER_GROUP')
    if issues_total > MAX_ISSUES:
        warnings.add('ISSUES_TRUNCATED_TO_100')
    if issues_total:
        warnings.add('ERRORS_BLOCK_REGISTRATION; VALID_SUBSET_IS_NOT_COMPLETE_SOURCE')
    warnings.add('MISSING_MONTHS_NOT_FILLED; NO_IMPLICIT_ZERO_DEMAND')
    if not output:
        warnings.add('NO_NORMAL_DEMAND_ROWS')
    policy_body = policy.model_dump(mode='json')
    policy_hash = digest(policy_body)
    reference_hash = master_digest(master)
    input_identity = {'sources': hashes, 'policy': policy_hash, 'dataset_id': policy.dataset_id, 'master_digest': reference_hash}
    if selections:
        input_identity['table_selections'] = {index: item.model_dump(mode='json') for index, item in selections.items()}
        warnings.add('XLSX_TABLE_SELECTION_PREVIEW_ONLY')
    input_hash = digest(input_identity)
    result_hash = digest({'input': input_hash, 'counts': counts, 'reconciliation': reconciliation,
                          'records': [row.model_dump(mode='json') for row in output],
                          'returns': [row.model_dump(mode='json') for row in separate],
                          'master_digest': reference_hash, 'issues': [issue.model_dump(mode='json') for issue in issues], 'issues_total': issues_total})
    return TransformReply(dataset_id=policy.dataset_id,
        status='HAS_ERRORS' if issues_total else 'TRANSFORMED_PREVIEW' if policy.user_confirmed else 'POLICY_REVIEW_REQUIRED',
        policy=policy, policy_digest=policy_hash, input_digest=input_hash, result_digest=result_hash, sources=sources,
        operations=compile_recipe(policy), master_scope=master.dataset_id if master else None, master_digest=reference_hash, counts=counts,
        quantity_reconciliation=reconciliation, records=output, returns=separate,
        issues=issues, issues_total=issues_total, warnings=sorted(warnings), total=len(output), offset=0, limit=MAX_GROUPS, returns_total=len(separate))
