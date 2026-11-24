"""Upstage contracts exercised exclusively through a recording MockTransport."""
import json
from hashlib import sha256
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.api.ingest_ai import get_upstage_client
from app.config import Settings, get_settings
from app.ingest.ai_documents import ExtractionEvidence, extract_document
from app.integrations.upstage import ApprovedSource, ProviderError, UpstageClient
from app.main import app
from contracts.mapping_review import decode_mapping
from export_contract_schema import AI_INGESTION_OUT, build_ai_ingestion


DATASET = 'SYNTHETIC-REVIEW'
CSV = b'product_id,forecast allocation odd label,line comment opaque\nP-001,17,left\nP-002,19,right\n'
PDF = b'%PDF-1.7\nsynthetic fixture'
KEY = 'fixture-placeholder'
POINTS = [{'x': x, 'y': y} for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]]


def source(data):
    return ApprovedSource(DATASET, sha256(data).hexdigest())


class Tracker:
    def __init__(self):
        self.reserved = []
        self.completed = []

    def reserve(self, request):
        self.reserved.append(request)
        return True

    def complete(self, request, usage, outcome):
        self.completed.append((request, usage, outcome))


@pytest.fixture
def config(monkeypatch):
    for name in Settings.model_fields:
        if name.startswith(('ai_', 'upstage_', 'document_', 'information_')):
            monkeypatch.delenv(name.upper(), raising=False)
    return Settings(_env_file=None, upstage_api_key=KEY, upstage_api_enabled=True, ai_external_data_allowed=True,
                    ai_external_synthetic_sources={DATASET: {source(CSV).source_sha256, source(PDF).source_sha256}},
                    ai_mapping_strategy='direct', ai_mapping_enabled=True, ai_embedding_enabled=True,
                    document_parse_enabled=True, information_extract_enabled=True,
                    document_classify_enabled=True, document_ocr_enabled=True)


@pytest.fixture
def harness():
    original = app.dependency_overrides.copy()

    def setup(settings, handler, *, metered=True):
        requests = []
        tracker = Tracker() if metered else None

        def transport(request):
            requests.append(request)
            assert request.url.host == 'api.upstage.ai' and request.url.scheme == 'https'
            assert request.headers['authorization'] == f'Bearer {KEY}'
            assert len(request.headers['x-request-id']) == 32
            return handler(request)

        provider = UpstageClient(settings, tracker, transport=httpx.MockTransport(transport))
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_upstage_client] = lambda: provider
        return TestClient(app), requests, tracker, provider

    yield setup
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original)


def solar(values, *, model='solar-mini4-260922', finish='stop'):
    return {'model': model, 'usage': {'prompt_tokens': 17, 'completion_tokens': 9}, 'choices': [
        {'finish_reason': finish, 'message': {'content': json.dumps(values) if isinstance(values, dict) else values}}]}


def reply(body):
    return lambda request: httpx.Response(200, json=body)


def review(client, data=CSV, *, dataset=DATASET, extra=None, path='ai-mapping-review'):
    return client.post(f'/ingest/{path}', params={'dataset_id': dataset},
        files={'file': ('fixture.csv', data, 'text/csv')},
        data={'entity': 'monthly_demand', **({'external_review': 'true'} if extra is None else extra)})


@pytest.mark.parametrize(('update', 'extra', 'dataset', 'expected'), [
    ({'upstage_api_enabled': False}, None, DATASET, 'AI_DISABLED'),
    ({'ai_mapping_enabled': False}, None, DATASET, 'AI_DISABLED'),
    ({'ai_external_data_allowed': False}, None, DATASET, 'EXTERNAL_TRANSFER_NOT_APPROVED'),
    ({}, {}, DATASET, 'EXTERNAL_TRANSFER_NOT_APPROVED'),
    ({'upstage_api_key': None}, None, DATASET, 'UPSTAGE_KEY_MISSING'),
    ({}, None, 'SYNTHETIC-OTHER', 'SOURCE_NOT_APPROVED'),
])
def test_external_gate_returns_unchanged_baseline(config, harness, update, extra, dataset, expected):
    client, requests, tracker, _ = harness(config.model_copy(update=update), None)
    result = review(client, dataset=dataset, extra=extra)
    baseline = review(client, dataset=dataset, extra={}, path='mapping-suggestions')
    assert result.status_code == baseline.status_code == 200
    assert result.json()['baseline'] == baseline.json()
    assert result.json()['issue'] == expected
    assert result.json()['columns'] == []
    assert not requests and not tracker.reserved


def test_missing_meter_and_unlisted_sha_fail_before_http(config, harness):
    client, requests, _, _ = harness(config, None, metered=False)
    assert review(client).json()['issue'] == 'COST_POLICY_REQUIRED'
    assert review(client, CSV + b'P-003,12,up\n').json()['issue'] == 'SOURCE_NOT_APPROVED'
    assert not requests


def test_cost_tracking_failure_returns_unavailable(config, harness, monkeypatch):
    client, requests, tracker, _ = harness(config, reply(solar({'1': 'product_id', '2': 'demand_qty', '3': 'HOLD'})))

    def fail(*args):
        raise RuntimeError('private metering detail')

    monkeypatch.setattr(tracker, 'reserve', fail)
    assert review(client).json()['issue'] == 'COST_POLICY_UNAVAILABLE' and not requests
    monkeypatch.setattr(tracker, 'reserve', lambda entry: tracker.reserved.append(entry) is None)
    monkeypatch.setattr(tracker, 'complete', fail)
    result = review(client).json()
    assert result['issue'] == 'COST_POLICY_UNAVAILABLE' and result['run'] is None
    assert len(requests) == len(tracker.reserved) == 1


def test_oversize_and_ambiguous_opt_in_fail_before_transport(config, harness):
    body = b'product_id,' + b'x' * 199 + b'\nP-001,17\n'
    settings = config.model_copy(update={'ai_mapping_strategy': 'business', 'ai_mapping_max_input_bytes': 1024,
                                         'ai_external_synthetic_sources': {DATASET: {source(body).source_sha256}}})
    client, requests, tracker, _ = harness(settings, None)
    assert review(client, body).json()['issue'] == 'UPSTAGE_INPUT_LIMIT'
    duplicate = client.post('/ingest/ai-mapping-review', params={'dataset_id': DATASET},
        files=[('file', ('x.csv', body)), ('entity', (None, 'monthly_demand')),
               ('external_review', (None, 'false')), ('external_review', (None, 'true'))])
    assert duplicate.status_code == 422
    assert not requests and not tracker.reserved


def test_valid_solar_run_and_protected_local_values(config, harness, caplog):
    values = {'1': 'unit', '2': 'demand_qty', '3': 'product_id'}
    client, requests, tracker, _ = harness(config, reply(solar(values)))
    with caplog.at_level('INFO'):
        response = review(client, extra={'external_review': 'true', 'column_overrides': '{"product_id":"A"}'})
    assert response.status_code == 200
    result = response.json()
    a, b, c = result['columns']
    assert (a['source'], a['target_field'], a['validation'], a['conflict']) == ('USER_CONFIRMED', 'product_id', 'PRESERVED', True)
    assert (b['source'], b['target_field'], b['validation']) == ('AI_SOLAR', 'demand_qty', 'REVIEWABLE')
    assert c['hold_reason'] == 'EXISTING_MAPPING_CONFLICT'
    assert all(row['requires_user_confirmation'] for row in result['columns'])
    assert result['persisted'] is result['auto_approve'] is False
    assert result['baseline']['sheets'][0]['status'] == 'HOLD'
    payload = json.loads(requests[0].content)
    wire = json.loads(payload['messages'][1]['content'])
    assert requests[0].url.path == '/v1/chat/completions'
    assert wire['requested_column_ids'] == ['1', '2', '3']
    assert payload['response_format']['json_schema']['schema']['additionalProperties'] is False
    assert DATASET not in requests[0].content.decode() and b'P-001' not in requests[0].content
    assert result['run']['request_id'] == requests[0].headers['x-request-id']
    assert result['run']['snapshot'] == 'solar-mini4-260922'
    assert result['run']['usage'] == {'input_tokens': 17, 'output_tokens': 9, 'pages': None,
                                     'standard_pages': None, 'enhanced_pages': None}
    assert tracker.completed[0][0] == tracker.reserved[0] and tracker.completed[0][2] == 'RECEIVED'
    assert KEY not in caplog.text and 'P-001' not in caplog.text
    assert KEY not in repr(config) and 'upstage_api_key' not in config.model_dump()


@pytest.mark.parametrize(('wire', 'finish', 'status', 'issue', 'reviewable'), [
    ('{', 'stop', 'HOLD', 'INVALID_JSON_OR_PROVIDER_SCHEMA', False),
    ('{"1":"product_id","2":"demand_qty","2":"HOLD"}', 'stop', 'HOLD', 'DUPLICATE_JSON_KEY', False),
    ({'1': 'product_id', '2': 'demand_qty'}, 'length', 'HOLD', 'OUTPUT_LIMIT', False),
    ({'1': 'product_id', '2': 'demand_qty'}, 'stop', 'PARTIAL', 'RESPONSE_VALIDATION', True),
    ({'1': 'product_id', '2': 'demand_qty', '3': 'salary', '400': 'HOLD'}, 'stop', 'PARTIAL', 'RESPONSE_VALIDATION', True),
    ({'1': 'product_id', '2': 'demand_qty', '3': 'demand_qty'}, 'stop', 'PARTIAL', 'RESPONSE_VALIDATION', False),
    ({'1': 'product_id', '2': 'HOLD', '3': 'HOLD'}, 'stop', 'HOLD', None, False),
])
def test_contract_failure_and_usable_subset(config, harness, wire, finish, status, issue, reviewable):
    client, _, _, _ = harness(config, reply(solar(wire, finish=finish)))
    result = review(client).json()
    assert (result['status'], result['issue']) == (status, issue)
    assert (result['columns'][1]['validation'] == 'REVIEWABLE') == reviewable
    assert result['columns'][0]['target_field'] == 'product_id'


def test_array_duplicate_id_is_excluded_without_losing_unrelated_row():
    raw = {'mapping': [{'id': '1', 'field': 'x'}, {'id': '1', 'field': 'HOLD'}, {'id': '2', 'field': 'y'}]}
    decoded = decode_mapping(solar(json.dumps(raw)), '/chat/completions',
                            {'1': {'x'}, '2': {'y'}}, {'x': 'x', 'y': 'y', 'HOLD': None}, keyed=False)
    assert decoded.rejected == {'1': 'DUPLICATE_ID'}
    assert decoded.values == {'2': 'y'}


def test_semantic_and_type_holds_remain_local(config, harness):
    data = b'order date outside,purchase orders expected,mystery glyph\n2027-01-12,32,name\n'
    settings = config.model_copy(update={'ai_external_synthetic_sources': {DATASET: {source(data).source_sha256}}})
    client, _, _, _ = harness(settings, reply(solar({'1': 'period', '2': 'demand_qty', '3': 'unit'})))
    result = review(client, data).json()
    assert [item['hold_reason'] for item in result['columns']] == ['NEEDS_TRANSFORM', 'NEEDS_TRANSFORM', 'TYPE_INCOMPATIBLE']


def test_hold_strategy_skips_all_existing_candidates(config, harness):
    settings = config.model_copy(update={'ai_mapping_strategy': 'hold_review'})
    client, requests, _, _ = harness(settings, reply(solar({'2': 'demand_qty', '3': 'HOLD'})))
    result = review(client).json()
    data = json.loads(json.loads(requests[0].content)['messages'][1]['content'])
    assert data['requested_column_ids'] == ['2', '3']
    assert data['protected_mappings'] == {'1': 'product_id'}
    assert result['columns'][0]['source'] == 'EXACT'
    assert result['columns'][1]['validation'] == 'REVIEWABLE'


def test_prompt_strategy_and_model_can_change_independently(config, harness):
    first, _, _, _ = harness(config, reply(solar({'1': 'product_id', '2': 'demand_qty', '3': 'HOLD'})))
    original_run = review(first).json()['run']
    updates = {'ai_mapping_model': 'solar-pro4', 'ai_mapping_prompt_version': 'mapping-v2', 'ai_mapping_strategy': 'concept'}
    second, wire, _, _ = harness(config.model_copy(update=updates), reply(solar(
        {'1': 'concept_01', '2': 'concept_04', '3': 'NEEDS_TRANSFORM'}, model='solar-pro4-260922')))
    result = review(second).json()
    assert result['run']['model'] == 'solar-pro4-260922'
    assert json.loads(wire[0].content)['model'] == 'solar-pro4'
    assert result['run']['prompt_sha256'] != original_run['prompt_sha256']
    assert result['run']['knowledge_sha256'] == original_run['knowledge_sha256']
    assert result['columns'][1]['business_concept'] == 'concept_04'
    assert result['columns'][2]['hold_reason'] == 'NEEDS_TRANSFORM'
    unknown, wire, _, _ = harness(config.model_copy(update={'ai_mapping_prompt_version': 'missing'}), None)
    assert review(unknown).json()['issue'] == 'UNSUPPORTED_REVIEW_VERSION'
    assert not wire


def test_preview_uses_responses_and_keeps_provider_storage_off(config, harness):
    settings = config.model_copy(update={'ai_mapping_model': 'solar-mini-4-5-preview'})
    response = {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': '{"1":"product_id","2":"demand_qty","3":"HOLD"}'}]}]}
    client, requests, _, _ = harness(settings, reply(response))
    assert review(client).json()['status'] == 'REVIEW'
    assert requests[0].url.path == '/v1/responses'
    assert json.loads(requests[0].content)['store'] is False


@pytest.mark.parametrize(('status', 'code'), [(400, 'UPSTAGE_BAD_REQUEST'), (401, 'UPSTAGE_AUTHENTICATION'),
                                              (429, 'UPSTAGE_RATE_LIMIT'), (500, 'UPSTAGE_HTTP_ERROR')])
def test_provider_errors_do_not_retry_or_expose_response(config, harness, status, code):
    client, requests, tracker, _ = harness(config, lambda request: httpx.Response(status,
        headers={'retry-after': '13'}, text='upstream-private-response'))
    result = review(client).json()
    assert result['status'] == 'UNAVAILABLE' and result['issue'] == code
    assert result['retry_after_seconds'] == (13 if status == 429 else None)
    assert len(requests) == len(tracker.reserved) == len(tracker.completed) == 1
    assert result['error_request_id'] == tracker.reserved[0].request_id
    assert tracker.completed[0][1:] == (None, code)
    assert 'upstream-private-response' not in json.dumps(result)


class LargeStream(httpx.SyncByteStream):
    def __iter__(self):
        yield b'x' * 600
        yield b'x' * 600


@pytest.mark.parametrize(('handler', 'code'), [
    (lambda r: httpx.Response(200, stream=LargeStream()), 'UPSTAGE_RESPONSE_LIMIT'),
    (lambda r: httpx.Response(200, content=b'invalid json'), 'UPSTAGE_RESPONSE_FORMAT'),
    (lambda r: httpx.Response(302, headers={'location': 'https://other.invalid/'}), 'UPSTAGE_HTTP_ERROR'),
    (reply(solar({'1': 'product_id'}, model='solar-pro4-260922')), 'UPSTAGE_MODEL_MISMATCH'),
])
def test_transport_bounds_and_provider_identity(config, harness, handler, code):
    client, requests, _, _ = harness(config.model_copy(update={'upstage_max_response_bytes': 1024}), handler)
    assert review(client).json()['issue'] == code
    assert len(requests) == 1


@pytest.mark.parametrize(('error', 'code'), [(httpx.ReadTimeout, 'UPSTAGE_TIMEOUT'), (httpx.ConnectError, 'UPSTAGE_NETWORK')])
def test_transport_keeps_unverified_cost_reservation(config, harness, error, code):
    def fail(_):
        raise error('private transport detail')

    client, requests, tracker, _ = harness(config, fail)
    assert review(client).json()['issue'] == code
    assert len(requests) == len(tracker.reserved) == 1
    assert tracker.completed[0][1:] == (None, code)


def workbook_bytes(shape):
    book = Workbook()
    sheet = book.active
    sheet.title = 'Data'
    sheet.append(['Report'])
    sheet.append([None, 'Forecast bucket', 'Forecast total'])
    sheet.append([None, '2027-01', 17])
    if shape == 'repeat':
        sheet.append([None, 'Forecast bucket', 'Forecast total'])
    if shape == 'multisheet':
        book.create_sheet('Notes').append(['Notes'])
    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()


def workbook_selection(data):
    return {'source_sha256': source(data).source_sha256, 'sheet': 'Data', 'header_row': 2, 'first_col': 2,
            'last_col': 3, 'data_start_row': 3, 'data_end_row': 3}


@pytest.mark.parametrize(('shape', 'reason', 'status'), [('single', 'USER_HEADER_AND_ROW_COUNT_MATCH', 'REVIEW'),
    ('repeat', 'AMBIGUOUS_HEADER', 'HOLD'), ('multisheet', 'AMBIGUOUS_WORKSHEETS', 'HOLD')])
def test_document_alignment_uses_original_xlsx_not_provider_values(config, harness, shape, reason, status):
    data = workbook_bytes(shape)
    settings = config.model_copy(update={'ai_external_synthetic_sources': {DATASET: {source(data).source_sha256}},
                                         'upstage_document_parse_mode': 'auto'})
    html = '<table><tr><th>Forecast bucket</th><th>Forecast total</th></tr><tr><td>2027-01</td><td>999999</td></tr></table>'
    provider_reply = {'model': 'document-parse-260930', 'usage': {'pages': 1, 'standard': [1], 'enhanced': []}, 'elements': [
        {'id': 0, 'page': 1, 'category': 'table', 'coordinates': POINTS,
         'content': {'html': html, 'markdown': 'upstream text', 'text': 'upstream text'}}]}
    client, requests, tracker, _ = harness(settings, reply(provider_reply))
    result = client.post('/ingest/ai-document-analysis', params={'dataset_id': DATASET},
        data={'external_review': 'true', 'table_selection': json.dumps(workbook_selection(data))},
        files={'file': ('fixture.xlsx', data)}).json()
    assert (result['status'], result['tables'][0]['reason']) == (status, reason)
    assert result['source_sha256'] == source(data).source_sha256 and result['mode'] == 'auto'
    assert result['user_selection_required'] and result['run']['usage']['pages'] == 1
    assert result['run']['usage']['standard_pages'] == 1
    assert result['tables'][0]['source_first_col'] == (2 if shape == 'single' else None)
    assert '999999' not in json.dumps(result) and 'upstream text' not in json.dumps(result)
    assert b'filename="synthetic.xlsx"' in requests[0].content and b'\r\n\r\nauto\r\n' in requests[0].content
    assert tracker.reserved[0].max_pages == 100


def test_selected_mapping_uses_physical_ids_and_checks_sha_before_http(config, harness):
    data = workbook_bytes('single')
    settings = config.model_copy(update={'ai_external_synthetic_sources': {DATASET: {source(data).source_sha256}}})
    client, requests, _, _ = harness(settings, reply(solar({'2': 'period', '3': 'demand_qty'})))
    exercise = {'external_review': 'true', 'entity': 'monthly_demand'}
    selection = workbook_selection(data)
    params = {'dataset_id': DATASET}
    good = client.post('/ingest/ai-mapping-review', params=params, files={'file': ('fixture.xlsx', data)},
                       data={**exercise, 'table_selection': json.dumps(selection)})
    wrong = client.post('/ingest/ai-mapping-review', params=params, files={'file': ('fixture.xlsx', data)},
                        data={**exercise, 'table_selection': json.dumps({**selection, 'source_sha256': '0' * 64})})
    assert good.status_code == 200
    assert good.json()['baseline']['table_selection'] == selection
    assert [(col['source_id'], col['target_field']) for col in good.json()['columns']] == [('2', 'period'), ('3', 'demand_qty')]
    assert wrong.status_code == 409 and len(requests) == 1


def test_parse_mode_mismatch_and_model_capability_are_explicit(config, harness):
    upstream = {'model': 'document-parse-260930', 'usage': {'pages': 1, 'standard': [], 'enhanced': [1]}, 'elements': []}
    client, requests, _, _ = harness(config, reply(upstream))
    result = client.post('/ingest/ai-document-analysis', params={'dataset_id': DATASET},
        data={'external_review': 'true'}, files={'file': ('fixture.pdf', PDF)}).json()
    assert result['issue'] == 'UPSTAGE_RESPONSE_FORMAT' and len(requests) == 1
    settings = config.model_copy(update={'upstage_document_parse_model': 'document-parse-251229',
                                         'upstage_document_parse_mode': 'enhanced'})
    client, requests, _, _ = harness(settings, None)
    result = client.post('/ingest/ai-document-analysis', params={'dataset_id': DATASET},
        data={'external_review': 'true'}, files={'file': ('fixture.pdf', PDF)}).json()
    assert result['issue'] == 'UNSUPPORTED_MODE' and not requests


FIELDS = {'product_id': {'type': 'string'}, 'product_name': {'type': 'string'}}
EXTRACT_SCHEMA = {'type': 'object', 'properties': {'rows': {'type': 'array', 'items': {
    'type': 'object', 'properties': FIELDS, 'required': list(FIELDS)}}}}
ROW = {'product_id': 'P-001', 'product_name': 'Test product'}


@pytest.mark.parametrize(('rows', 'location', 'issue'), [
    ([ROW], True, None), ([{'product_id': 'P-001'}], True, 'MISSING_FIELD'),
    ([{**ROW, 'product_name': 17}], True, 'VALUE_OR_TYPE_MISMATCH'),
    ([{**ROW, 'product_name': 'invented'}], True, 'VALUE_OR_TYPE_MISMATCH'),
    ([{**ROW, 'bad_field': 'invented'}], True, 'ADDITIONAL_FIELD_OR_INVALID_ROW'),
    ([{**ROW, 'product_id': 'P-002'}], True, 'EXTRA_OR_DUPLICATE_ROW'),
    ([ROW, ROW], True, 'EXTRA_OR_DUPLICATE_ROW'),
    ([ROW], False, 'LOCATION_EVIDENCE_MISSING'),
    ([], False, 'MISSING_ROW'),
])
def test_extract_rows_require_local_ground_truth(config, harness, rows, location, issue):
    upstream = solar({'rows': rows}, model='information-extract-261113')
    upstream['choices'][0]['message']['tool_calls'] = [{'function': {'name': 'additional_values', 'arguments': json.dumps({
        'rows': [{field: {'_value': original, 'page': 1, 'coordinates': POINTS}
                  for field, original in ROW.items()}] if location else []})}}]
    _, requests, _, provider = harness(config, reply(upstream))
    evidence = ExtractionEvidence(DATASET, source(PDF).source_sha256, 'product', {'P-001': ROW}, 'product_id')
    result = extract_document(provider, source(PDF), requested=True, data=PDF, kind='pdf', entity='product',
                              schema=EXTRACT_SCHEMA, evidence=evidence)
    assert result['status'] == ('REVIEW' if issue is None else 'HOLD')
    assert result['verified_row_keys'] == (['P-001'] if issue is None else [])
    assert issue is None or issue in result['issues']
    assert result['persisted'] is False
    assert requests[0].url.path == '/v1/information-extraction'
    assert json.loads(requests[0].content)['location_granularity'] == 'element'


def test_extract_rejects_wrong_type_and_unsupported_schema_before_http(config, harness):
    _, requests, _, provider = harness(config, None)
    evidence = ExtractionEvidence(DATASET, source(PDF).source_sha256, 'material', {'P-001': ROW}, 'product_id')
    with pytest.raises(ProviderError, match='DOCUMENT_TYPE_OR_SCOPE_UNVERIFIED'):
        extract_document(provider, source(PDF), requested=True, data=PDF, kind='pdf', entity='product',
                         schema=EXTRACT_SCHEMA, evidence=evidence)
    with pytest.raises(ProviderError, match='UNSUPPORTED_SCHEMA'):
        provider.extract(source(PDF), requested=True, data=PDF, kind='pdf', schema={'type': 'array'})
    with pytest.raises(ProviderError, match='SOURCE_NOT_APPROVED'):
        provider.parse(source(PDF), requested=True, data=PDF + b'changed', kind='pdf')
    assert requests == []


def test_embedding_classify_and_ocr_wire_contracts(config, harness):
    fixtures = {
        '/v1/embeddings': {'model': 'solar-embedding-2-query', 'data': [{'index': 0, 'embedding': [0.1] * 1024}]},
        '/v1/document-classification': solar('"UNKNOWN"', model='document-classify-261113'),
        '/v1/document-digitization': {'model': 'ocr', 'metadata': {'pages': 1}, 'pages': [{'words': [{'text': 'Test'}]}]},
    }
    _, requests, tracker, provider = harness(config, lambda r: httpx.Response(200, json=fixtures[r.url.path]))
    vectors, _ = provider.embedding(source(PDF), requested=True, model='solar-embedding-2-query', inputs=['synthetic example'])
    category, _ = provider.classify(source(PDF), requested=True, data=PDF, kind='pdf',
                                    classes={'UNKNOWN': 'Outside current registered types'})
    ocr = provider.ocr(source(PDF), requested=True, data=PDF, kind='pdf')
    assert len(vectors) == 1 and len(vectors[0]) == 1024
    assert category == 'UNKNOWN' and ocr.run.usage.pages == 1
    with pytest.raises(ProviderError, match='UNSUPPORTED_MODEL'):
        provider.embedding(source(PDF), requested=True, model='unknown-model', inputs=['synthetic'])
    assert len(requests) == len(tracker.completed) == 3


def test_default_flags_and_generated_review_contract():
    settings = Settings(_env_file=None)
    assert not any(getattr(settings, name) for name in (
        'upstage_api_enabled', 'ai_external_data_allowed', 'ai_mapping_enabled', 'ai_embedding_enabled',
        'document_parse_enabled', 'information_extract_enabled', 'document_classify_enabled', 'document_ocr_enabled'))
    assert settings.ai_mapping_strategy == 'hold_review'
    assert AI_INGESTION_OUT.read_text(encoding='utf-8') == build_ai_ingestion()
    spec = app.openapi()
    for slug, model in [('ai-mapping-review', 'AIMappingReply'), ('ai-document-analysis', 'AIDocumentReply')]:
        route = spec['paths']['/ingest/' + slug]['post']
        component = route['requestBody']['content']['multipart/form-data']['schema']['$ref'].split('/')[-1]
        assert spec['components']['schemas'][component]['properties']['external_review']['default'] is False
        assert route['responses']['200']['content']['application/json']['schema']['$ref'].endswith('/' + model)
