"""Local deterministic assistance, safety boundaries and unchanged approval behavior."""
import asyncio
import csv
import hashlib
import io
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.ingest_assistance import load_master
from app.ingest.mapping import map_sheet
from app.ingest.parsing import FileError
from app.ingest.profiling import MAX_DISTINCT, ScopedMaster, parse_analysis_file, profile
from app.ingest.recommendation import recommend
from app.ingest.transformation import transform
from app.ingest.validation import KnownProduct, KnownMaterial, MasterData
from contracts.interfaces.ingestion import SalesColumns, SalesTransformPolicy

ROOT = Path(__file__).resolve().parents[2]
DATASET = 'CHUNGPAMO-2027'
HEADER = ['주문일자', '제품코드', '수량', '단위', '구분', '주문번호', '행번호']


def sales(rows, header=HEADER):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue().encode()


def policy(**changes):
    return SalesTransformPolicy(dataset_id=DATASET, **changes)


def masters(dataset=DATASET):
    return ScopedMaster(dataset, MasterData({'P1': KnownProduct('P1', 'Synthetic product', 'EA')},
                                          {'M1': KnownMaterial('M1', 'Synthetic material', 'kg')}))


def test_measured_profile_and_no_samples_by_default():
    data = b'code,qty,day,unit\nP1,1,2026-01-01,EA\nP1,,2026/01/02,EA\nM1,3,invalid,kg\n'
    parsed = parse_analysis_file('profile.csv', data)
    result = profile(parsed, DATASET, masters())
    code, qty, day, unit = result.sheets[0].columns
    assert code.distinct_count == 2 and code.known_product_match_ratio == 2 / 3 and code.known_material_match_ratio == 1 / 3
    assert qty.empty_count == 1 and qty.non_null_ratio == 2 / 3 and 'DECIMAL' in qty.type_candidates
    assert day.date_formats == {'ISO_DATE': 1, 'SLASH_DATE': 1} and 'MIXED_FORMATS' in day.uncertainty_reasons
    assert unit.unit_candidates == ['EA', 'kg']
    assert all(not col.example_values for col in result.sheets[0].columns)
    assert result.source_sha256 == hashlib.sha256(data).hexdigest()
    assert result.master_scope == DATASET and len(result.master_digest) == 64


def test_profile_bounded_samples_distinct_count_and_redaction():
    rows = ['text,code', 'test@example.invalid,P1'] + [f'Synthetic-{i},P1' for i in range(MAX_DISTINCT + 5)]
    result = profile(parse_analysis_file('p.csv', '\n'.join(rows).encode()), DATASET, include_samples=True)
    text = result.sheets[0].columns[0]
    assert not text.distinct_count_is_exact and text.distinct_count == MAX_DISTINCT
    assert len(text.example_values) <= 3 and text.example_values[0].value == '[REDACTED]'
    assert 'test@example.invalid' not in result.model_dump_json()


@pytest.mark.parametrize('field,header', [('product_id', '자재코드'), ('material_id', '제품코드'),
    ('demand_qty', '판매금액'), ('demand_qty', '반품수량'), ('demand_qty', '생산한도'), ('demand_qty', '설비시간'),
    ('demand_qty', '작업인시'), ('period', '출고일자'), ('on_hand_qty', '가용재고'), ('available_qty', '현재고'),
    ('demand_qty', '월수요金額'), ('on_hand_qty', 'on_hand_value'), ('demand_qty', '출고량'),
    ('available_qty', '기준/가용수량')])
def test_semantic_contradictions_are_not_candidates(field, header):
    from app.ingest.recommendation import compatible
    col = profile(parse_analysis_file('p.csv', f'{header},other\n1,x\n'.encode()), DATASET).sheets[0].columns[0]
    assert not compatible(field, header, col)[0]


def test_mapping_preserves_overrides_and_holds_and_only_suggests_fuzzy():
    data = b'product_id,period,demand_qt,unit\nP1,2026-01,10,EA\n'
    parsed = parse_analysis_file('p.csv', data)
    assert 'demand_qty' not in map_sheet(parsed.sheets[0]).fields
    result = recommend(parsed, 'monthly_demand', DATASET, masters()).sheets[0]
    assert result.status == 'HOLD' and 'demand_qty' not in result.existing_mapping
    candidate = next(c for c in result.suggestions[2].suggestions if c.target_field == 'demand_qty')
    assert candidate.method == 'LEXICAL_SIMILARITY' and candidate.requires_review
    assert not hasattr(candidate, 'confidence')
    chosen = recommend(parsed, 'monthly_demand', DATASET, masters(), {'demand_qty': 'C'}).sheets[0]
    assert chosen.status == 'MAPPED' and chosen.suggestions[2].suggestions[0].method == 'USER_OVERRIDE'
    ambiguous = parse_analysis_file('p.csv', '제품코드,기준월,수량,주문수량\nP1,2026-01,10,11\n'.encode())
    assert recommend(ambiguous, 'monthly_demand', DATASET).sheets[0].status == 'HOLD'
    assert map_sheet(ambiguous.sheets[0]).status == 'HOLD'


def test_product_and_material_master_namespaces_and_scope_are_distinct():
    parsed = parse_analysis_file('p.csv', '상품번호,기준월,수요량,단위\nP1,2026-01,1,EA\n'.encode())
    row = recommend(parsed, 'monthly_demand', DATASET, masters()).sheets[0]
    assert row.status == 'HOLD' and any(c.target_field == 'product_id' for c in row.suggestions[0].suggestions)
    with pytest.raises(FileError, match='another dataset'):
        profile(parsed, 'TISSUE-LEGACY', masters())
    with pytest.raises(FileError, match='another dataset'):
        transform([('p.csv', sales([['2026-01-01', 'P1', 1, '팩', '정상', 'O1', 1]]))], policy(), masters('TISSUE-LEGACY'))


def test_decimal_sales_cancel_returns_policy_counts_and_reproducibility():
    data = sales([['2026-01-01', 'P1', '0.1', '팩', '정상', 'O1', 1],
                  ['2026/01/02', 'P1', '0.2', 'EA', '정상', 'O2', 1],
                  ['20260103', 'P1', '100', '팩', '취소', 'O3', 1],
                  ['2026-02-01', 'P1', '-0.05', '팩', '반품', 'R1', 1]])
    before = data
    unconfirmed = transform([('sales.csv', data)], policy(), masters())
    result = transform([('sales.csv', data)], policy(user_confirmed=True), masters())
    assert unconfirmed.status == 'POLICY_REVIEW_REQUIRED' and not unconfirmed.persisted
    assert result.status == 'TRANSFORMED_PREVIEW' and result.approval_required and result.auto_approve is False
    assert result.records[0].demand_qty == '0.3' and result.returns[0].return_qty == '0.05'
    assert result.counts == {'source_rows': 4, 'normal_included': 2, 'cancelled_excluded': 1, 'returns_separate': 1,
                             'error_rows': 0, 'aggregation_errors': 0, 'monthly_demand_rows': 1}
    assert result.quantity_reconciliation['normal_quantity_conserved'] is True
    assert result.sources[0].sha256 == hashlib.sha256(data).hexdigest()
    assert result == transform([('sales.csv', data)], policy(user_confirmed=True), masters())
    assert data == before and result.policy_digest != unconfirmed.policy_digest
    assert {op.operation for op in result.operations} == {'SELECT_COLUMNS', 'RENAME_COLUMNS', 'NORMALIZE_DATE',
        'NORMALIZE_UNIT', 'FILTER_ROWS', 'GROUP_BY', 'SUM_DECIMAL', 'VALIDATE_REFERENCE'}


@pytest.mark.parametrize('field,value,code', [('order_date', '2026-02-30', 'DATE_INVALID'), ('quantity', '10팩', 'QTY_INVALID'),
    ('quantity', '-1', 'NEGATIVE_NON_RETURN_QUANTITY'), ('unit', 'BOX', 'UNIT_UNSUPPORTED_BY_POLICY'),
    ('product_id', 'M1', 'PRODUCT_REFERENCE_OR_UNIT_INVALID'), ('status', 'unknown', 'TRANSACTION_STATUS_UNKNOWN')])
def test_transform_bad_rows_have_positions_and_block_success(field, value, code):
    values = dict(zip(SalesColumns.model_fields, ['2026-01-01', 'P1', '10', '팩', '정상', 'O1', '1']))
    values[field] = value
    result = transform([('p.csv', sales([list(values.values())]))], policy(user_confirmed=True), masters())
    assert result.status == 'HAS_ERRORS' and result.counts['error_rows'] == 1
    assert result.issues[0].code == code and result.issues[0].location.row == 2 and result.issues[0].location.col
    assert 'raw_value' not in result.issues[0].model_dump()


def test_duplicates_range_and_bounded_trace_and_pagination():
    rows = [['2026-01-01', 'P1', '1', '팩', '정상', f'O{i}', '1'] for i in range(110)]
    data = sales(rows)
    result = transform([('p.csv', data)], policy())
    assert result.records[0].demand_qty == '110' and result.records[0].source_row_count == 110
    assert len(result.records[0].source_locations) == 5
    assert transform([('p.csv', data)], policy(), offset=1).result_digest == result.result_digest
    assert transform([('p.csv', data)], policy(), offset=1).records == []
    with pytest.raises(FileError, match='Identical source'):
        transform([('a.csv', data), ('b.csv', data)], policy())
    duplicate = transform([('p.csv', sales(rows + [rows[0]] * 110))], policy())
    assert duplicate.status == 'HAS_ERRORS' and duplicate.issues_total == 110 and len(duplicate.issues) == 100
    huge = transform([('p.csv', sales([['2026-01-01', 'P1', '99999999999999.9999', '팩', '정상', 'O1', '1'],
                                      ['2026-01-02', 'P1', '1', '팩', '정상', 'O2', '1']]))], policy())
    assert huge.status == 'HAS_ERRORS' and huge.counts['aggregation_errors'] == 1 and huge.counts['error_rows'] == 0


def test_xlsx_dates_and_numeric_codes_need_review():
    from datetime import date
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.append(HEADER)
    ws.append([date(2026, 1, 2), 'P1', 1, '팩', '정상', 'O1', 1])
    stream = io.BytesIO(); wb.save(stream); wb.close()
    assert transform([('p.xlsx', stream.getvalue())], policy()).records[0].period == '2026-01'
    wb = Workbook(); ws = wb.active; ws.append(HEADER)
    ws.append([date(2026, 1, 2), 1, 1, '팩', '정상', 'O1', 1])
    stream = io.BytesIO(); wb.save(stream); wb.close()
    result = transform([('p.xlsx', stream.getvalue())], policy())
    assert result.issues[0].code == 'NUMERIC_PRODUCT_CODE_REQUIRES_REVIEW'


def test_api_safety_master_gate_confirmation_and_policy_rejection():
    client = TestClient(app)
    data = sales([['2026-01-01', 'P1', '1', '팩', '정상', 'O1', 1]])
    args = {'files': [('files', ('s.csv', data))], 'params': {'dataset_id': DATASET}}
    response = client.post('/ingest/transform-preview', **args, data={'policy': policy().model_dump_json()})
    assert response.status_code == 200 and response.json()['status'] == 'POLICY_REVIEW_REQUIRED'
    assert response.json()['persisted'] is False
    assert client.post('/ingest/transform-preview', **args, data={'policy': policy().model_copy(update={'dataset_id': 'TISSUE-LEGACY'}).model_dump_json()}).status_code == 409
    for extra in ({'sql': 'DROP TABLE product'}, {'unit_factor': '12'}, {'policy_id': 'ALL_COMPANIES'}, {'user_confirmed': 'yes'}):
        body = {**policy().model_dump(), **extra}
        assert client.post('/ingest/transform-preview', **args, data={'policy': json.dumps(body)}).status_code == 422
    assert client.post('/ingest/profile', files={'file': ('p.csv', b'code,qty\nP1,1\n')}, data={'use_approved_master': 'true'}).status_code == 501
    with pytest.MonkeyPatch.context():
        app.dependency_overrides[load_master] = lambda: masters()
        try:
            result = client.post('/ingest/profile?dataset_id=TISSUE-LEGACY', files={'file': ('p.csv', b'code,qty\nP1,1\n')})
            assert result.status_code == 409
        finally:
            app.dependency_overrides.pop(load_master, None)


def test_profile_api_bounds_and_duplicate_json_keys():
    client = TestClient(app)
    assert client.post('/ingest/profile', files={'file': ('p.csv', (','.join('c' + str(i) for i in range(65)) + '\n').encode())}).status_code == 413
    result = client.post('/ingest/mapping-suggestions', files={'file': ('p.csv', b'a,b\n1,2\n')},
                         data={'column_overrides': '{"period":"A","period":"B"}'})
    assert result.status_code == 422
    result = client.post('/ingest/mapping-suggestions', files={'file': ('p.csv', b'a,b\n1,2\n')}, data={'column_overrides': '{"unknown":"B"}'})
    assert result.status_code == 422


def test_chunked_request_body_limit_precedes_parser():
    from app.ingest.limits import AssistanceBodyLimit
    called, messages = [], []
    async def forbidden(scope, receive, send):
        called.append(True)
    chunks = iter([{'type': 'http.request', 'body': b'x' * 8, 'more_body': True},
                   {'type': 'http.request', 'body': b'x' * 8, 'more_body': False}])
    async def receive(): return next(chunks)
    async def send(message): messages.append(message)
    asyncio.run(AssistanceBodyLimit(forbidden, limit=10)({'type': 'http', 'path': '/ingest/profile', 'headers': []}, receive, send))
    assert not called and messages[0]['status'] == 413


def test_manual_gold_benchmark_and_generated_schema_sync():
    from scripts.benchmark_ingestion import mapping_cases
    result = mapping_cases()
    assert result['baseline']['cases'] == result['assisted']['cases'] == 16
    assert result['assisted']['bad_material_pass_rate'] == 0
    assert result['assisted']['wrong_auto_mapping_fields'] == 0
    assert result['assisted']['topk_candidate_recall'] > result['baseline']['topk_candidate_recall']
    from export_contract_schema import build_ingestion
    assert (ROOT / 'contracts/schemas/ingestion_assistance_v1.json').read_text(encoding='utf-8') == build_ingestion()
