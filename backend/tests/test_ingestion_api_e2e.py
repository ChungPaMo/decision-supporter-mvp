"""Real TestClient workflow. Official gold for success; small derived negative fixtures only."""
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import pytest
from contracts.interfaces.capacity import CapacityRegistrationDraft
from contracts.interfaces.ingestion import MappingReply, ProfileReply, SalesTransformPolicy, TransformReply
from contracts.interfaces.ingestion_history import TransformationDetail
from tests.ingestion_e2e_support import DATASET, ROOT, approve, memory_api, official_sources, upload
from scripts.verify_synthetic_contracts import FILES

PARAMS = {'dataset_id': DATASET}


def seed_masters(client, sources, all_inputs=False):
    batches = {}
    for name, entity in FILES:
        if name == '05_monthly_demand.csv' or (not all_inputs and entity not in ('product', 'material')):
            continue  # Gold demand is an oracle, not a duplicate input to raw-sales registration.
        response = upload(client, name, sources['upload/' + name], entity)
        assert response.status_code == 201, response.text
        batch = response.json()
        assert batch['status'] == 'READY_FOR_APPROVAL', batch
        response = approve(client, batch)
        assert response.status_code == 200 and response.json()['status'] == 'APPROVED', response.text
        batches[name] = response.json()
    return batches


def demand_rows(rows):
    return sorted((r['product_id'], r['period'], Decimal(r['demand_qty']), r['unit']) for r in rows)


def verify_official_journey():
    """Called once by the preserved large-source regression, replacing its separate benchmark run."""
    target, manifest, sources = official_sources()
    sales = [(Path(name).name, content) for name, content in sources.items() if name.startswith('raw/')]
    with memory_api() as (client, repositories):
        masters = seed_masters(client, sources, all_inputs=True)
        for endpoint, expected in [('/products', 9), ('/materials', 9), ('/boms', 9), ('/inventory', 18), ('/capacity', 27), ('/routings', 27)]:
            response = client.get(endpoint, params=PARAMS)
            assert response.status_code == 200 and response.json()['total'] == expected, (endpoint, response.text)
        assert client.get('/demand/monthly', params=PARAMS).json()['total'] == 0
        repo = repositories[DATASET]
        draft = CapacityRegistrationDraft(**{s: [r['payload'] for r in repo.state.capacity[s]] for s in repo.state.capacity})
        draft.check_approved_products(set(repo.state.products))
        assert (len(draft.resources), len(draft.quantity_limits), len(draft.hours_budgets), len(draft.routing_steps)) == (6, 3, 18, 27)
        assert len({s.product_id for s in draft.routing_steps if s.resource_id == 'SAW1'}) == 9
        assert sum(any(r.resource_id == 'LB1' and r.time_basis == 'PERSON_HOUR' for r in s.resource_requirements) for s in draft.routing_steps) == 9
        name, content = sales[0]
        classified = client.post('/classifications/file', files={'file': (name, content)}).json()
        assert classified['hold'] and classified['recommended_entity'] is None and classified['module_version']
        assert any('monthly_demand' in reason for reason in classified['reasons'])
        response = client.post('/ingest/profile', params=PARAMS, files={'file': (name, content)}, data={'use_approved_master': 'true'})
        assert response.status_code == 200, response.text
        measured = ProfileReply.model_validate(response.json())
        assert measured.master_scope == DATASET and not measured.samples_included
        assert measured.source_sha256 == hashlib.sha256(content).hexdigest()
        assert all(not col.example_values for s in measured.sheets for col in s.columns)
        response = client.post('/ingest/mapping-suggestions', params=PARAMS, files={'file': (name, content)},
            data={'entity': 'monthly_demand', 'use_approved_master': 'true'})
        assert response.status_code == 200, response.text
        mapping = MappingReply.model_validate(response.json())
        assert mapping.sheets[0].status == 'HOLD'  # Transactions are not already monthly demand.
        assert all(len(c.suggestions) <= 3 for c in mapping.sheets[0].suggestions)
        assert all(c.requires_review for col in mapping.sheets[0].suggestions for c in col.suggestions)
        # policy.columns is the confirmed transaction mapping, distinct from monthly column_overrides.
        policy = SalesTransformPolicy(dataset_id=DATASET, user_confirmed=True)
        response = client.post('/ingest/transform-preview', params=PARAMS, files=[('files', item) for item in sales],
            data={'policy': policy.model_dump_json(), 'use_approved_master': 'true'})
        assert response.status_code == 200, response.text
        result = TransformReply.model_validate(response.json())
        assert result.status == 'TRANSFORMED_PREVIEW' and result.counts == manifest['counts']
        assert result.total == len(result.records) == 498
        reconciliation = result.quantity_reconciliation
        assert reconciliation['normal_quantity_conserved'] is True
        assert reconciliation['normal_included_qty'] == reconciliation['monthly_output_qty'] == manifest['normal_quantity']
        assert reconciliation['cancelled_qty_ignored'] == manifest['cancelled_quantity']
        assert reconciliation['returns_qty_separate'] == manifest['separate_returns_quantity']
        assert reconciliation['returns_not_subtracted'] is True
        assert [r.sha256 for r in result.sources] == [hashlib.sha256(data).hexdigest() for _, data in sales]
        assert all(len(d) == 64 for d in (result.policy_digest, result.input_digest, result.result_digest))
        gold = list(csv.DictReader(io.StringIO(sources['upload/05_monthly_demand.csv'].decode('utf-8-sig'))))
        assert demand_rows(result.model_dump()['records']) == demand_rows(gold)
        assert not result.persisted and not result.auto_approve and len(repo.state.batches) == 8
        response = client.post('/ingest/transformations', params=PARAMS, files=[('files', item) for item in sales], data={
            'policy': policy.model_dump_json(), 'use_approved_master': 'true', 'expected_result_digest': result.result_digest,
            'created_by': 'INGEST-E2E', 'source_note': 'Lee CHUNGPAMO-2027 official generator; TEST-DOUBLE-ONLY'})
        assert response.status_code == 201, response.text
        detail = TransformationDetail.model_validate(response.json())
        assert detail.dataset_id == DATASET and detail.preview.policy == policy
        assert detail.preview.result_digest == result.result_digest and detail.preview.input_digest == result.input_digest
        assert detail.persisted and not detail.preview.persisted and not detail.auto_approve
        assert detail.batch_status == 'READY_FOR_APPROVAL' and not repo.state.demand
        history_page = client.get('/ingest/transformations', params=PARAMS).json()
        assert history_page['total'] == 1 and history_page['items'][0]['batch_id'] == str(detail.batch_id)
        batch = client.get('/batches/' + str(detail.batch_id), params=PARAMS).json()
        assert batch['dataset_id'] == DATASET and batch['entity'] == 'monthly_demand'
        assert batch['approved_at'] is None and batch['approved_by'] is None and batch['approved_record_count'] is None
        assert client.get('/demand/monthly', params=PARAMS).json()['total'] == 0
        assert approve(client, batch, expected_result_digest=detail.result_digest).status_code == 409
        assert client.get('/ingest/transformations/' + str(detail.transformation_id)).status_code == 404
        approved = approve(client, batch)
        assert approved.status_code == 200 and approved.json()['approved_record_count'] == 498, approved.text
        final = client.get('/ingest/transformations/' + str(detail.transformation_id), params=PARAMS)
        assert final.status_code == 200 and final.json()['batch_status'] == 'APPROVED'
        assert final.json()['result_digest'] == detail.result_digest
        page = client.get('/demand/monthly', params={**PARAMS, 'limit': 1000}).json()
        assert page['total'] == 498 and demand_rows(page['items']) == demand_rows(gold)
        assert {r['batch_id'] for r in page['items']} == {str(detail.batch_id)}
        assert approve(client, approved.json()).status_code == 409
        assert upload(client, 'transformed_monthly_demand.csv', repo.state.files[detail.batch_id], 'monthly_demand').status_code == 409
        assert len(repo.state.batches) == 9 and repo.state.transformation_sources[detail.transformation_id] == sales
        assert all(hashlib.sha256((target / p).read_bytes()).hexdigest() == sha for p, sha in manifest['files'].items())
        report = {'scope': 'TEST-DOUBLE-ONLY / NO SQL / NO DATABASE APPROVAL', 'dataset_id': DATASET,
            'official_source_hashes_verified': len(sources), 'standard_master_batches': len(masters),
            'counts': result.counts, 'quantity_reconciliation': reconciliation, 'gold_rows_equal': True,
            'staged_batch_status': detail.batch_status, 'final_batch_status': final.json()['batch_status'],
            'history_link_verified': True, 'source_bytes_unchanged': True, 'automatic_approval': False,
            'input_digest': result.input_digest, 'result_digest': result.result_digest}
        (ROOT / '.artifacts/ingestion_api_e2e.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report


@pytest.fixture(scope='module')
def sources():
    return official_sources()[2]


@pytest.mark.parametrize('filename,entity', FILES)
def test_official_upload_classification_has_no_persistence_side_effect(sources, filename, entity):
    with memory_api() as (client, repositories):
        response = client.post('/classifications/file', files={'file': (filename, sources['upload/' + filename])})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['module_version'] and body['reasons']
        if entity in ('capacity', 'routing'):
            assert body['hold'] and body['recommended_entity'] is None
        else:
            assert body['recommended_entity'] == entity and not body['hold']
        assert not repositories[DATASET].state.batches


@pytest.mark.parametrize('name,content,code', [('empty.csv', b'', 'FILE_EMPTY'), ('corrupt.xlsx', b'not-a-workbook', 'XLSX_CORRUPT')])
def test_corrupt_files_fail_instead_of_mock_success(name, content, code):
    with memory_api() as (client, repositories):
        for path in ('/classifications/file', '/ingest/profile'):
            response = client.post(path, params=PARAMS, files={'file': (name, content)})
            assert response.status_code == 422 and response.json()['detail']['code'] == code
        assert not repositories[DATASET].state.batches


def test_manual_mapping_recovery_is_explicit_and_bad_choice_is_validation_error(sources):
    # Small negative fixture derived from GOLD, not a replacement representative dataset.
    first = next(csv.DictReader(io.StringIO(sources['upload/05_monthly_demand.csv'].decode('utf-8-sig'))))
    data = ('제품코드,기준월,수량,주문수량,단위\n' + f"{first['product_id']},{first['period']},{first['demand_qty']},999,EA\n").encode()
    with memory_api() as (client, repositories):
        seed_masters(client, sources)
        suggested = client.post('/ingest/mapping-suggestions', params=PARAMS, files={'file': ('negative-ambiguous.csv', data)}).json()
        assert suggested['sheets'][0]['status'] == 'HOLD'
        assert any(len(c['suggestions']) > 1 for c in suggested['sheets'][0]['suggestions'])
        batch = upload(client, 'negative-ambiguous.csv', data, 'monthly_demand').json()
        assert batch['status'] == 'MAPPING_HOLD' and approve(client, batch).status_code == 409
        path = '/batches/' + batch['batch_id'] + '/revalidate'
        bad = client.post(path, params=PARAMS, json={'expected_version': batch['version'], 'column_overrides': {'demand_qty': 'E'}})
        assert bad.status_code == 200 and bad.json()['status'] == 'HAS_ERRORS'
        assert any(r['code'] == 'QTY_INVALID' and r['location']['row'] == 2 for s in bad.json()['validation']['sheets'] for r in s['issues'])
        assert approve(client, bad.json()).status_code == 409
        good = client.post(path, params=PARAMS, json={'expected_version': bad.json()['version'], 'column_overrides': {'demand_qty': 'C'}})
        assert good.status_code == 200 and good.json()['status'] == 'READY_FOR_APPROVAL'
        assert not repositories[DATASET].state.demand
        assert approve(client, good.json()).status_code == 200


def verify_manual_mapping_journey(client, sources):
    from contracts.interfaces.ingestion import SalesColumns

    original = next(content for path, content in sources.items() if path.startswith('raw/transactions'))
    row = next(row for row in csv.DictReader(io.StringIO(original.decode('utf-8-sig'))) if row['구분'] == '정상')
    row['거래확정팩수'] = row.pop('수량')
    row['월수요金額'] = '999999'
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    content = stream.getvalue().encode()
    original_file = ('synthetic-ambiguous-quantity.csv', content)
    seed_masters(client, sources)
    suggested = client.post('/ingest/mapping-suggestions', params=PARAMS, files={'file': original_file},
                            data={'use_approved_master': 'true'})
    assert suggested.status_code == 200
    sheet = suggested.json()['sheets'][0]
    assert sheet['status'] == 'HOLD' and 'demand_qty' not in sheet['existing_mapping']
    money = next(column for column in sheet['suggestions'] if column['source_column'] == '월수요金額')
    assert not any(candidate['target_field'] == 'demand_qty' for candidate in money['suggestions'])

    columns = SalesColumns(quantity='거래확정팩수')
    policy = SalesTransformPolicy(dataset_id=DATASET, columns=columns)
    files = {'files': original_file}
    form = {'policy': policy.model_dump_json(), 'use_approved_master': 'true'}
    unconfirmed = client.post('/ingest/transform-preview', params=PARAMS, files=files, data=form)
    assert unconfirmed.json()['status'] == 'POLICY_REVIEW_REQUIRED'
    form['policy'] = policy.model_copy(update={'user_confirmed': True}).model_dump_json()
    preview_response = client.post('/ingest/transform-preview', params=PARAMS, files=files, data=form)
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview['status'] == 'TRANSFORMED_PREVIEW'
    assert Decimal(preview['records'][0]['demand_qty']) == Decimal(row['거래확정팩수'])
    assert preview['persisted'] is False and preview['auto_approve'] is False
    response = client.post('/ingest/transformations', params=PARAMS, files=files,
                           data={**form, 'expected_result_digest': preview['result_digest'], 'created_by': 'INGEST-E2E',
                                 'source_note': 'Synthetic manual mapping regression'})
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['batch_status'] == 'READY_FOR_APPROVAL' and saved['auto_approve'] is False
    return saved


def test_unknown_order_quantity_requires_explicit_selection_before_staging(sources):
    with memory_api() as (client, repositories):
        verify_manual_mapping_journey(client, sources)
        assert not repositories[DATASET].state.demand


def test_cross_dataset_master_and_batch_ownership_do_not_fallback(sources):
    with memory_api() as (client, repositories):
        seed_masters(client, sources)
        data = ('\n'.join(sources['upload/05_monthly_demand.csv'].decode('utf-8-sig').splitlines()[:2]) + '\n').encode()
        response = upload(client, 'negative-cross-dataset.csv', data, 'monthly_demand', dataset='TISSUE-LEGACY')
        assert response.status_code == 201 and response.json()['status'] == 'HAS_ERRORS'
        assert approve(client, response.json(), dataset='TISSUE-LEGACY').status_code == 409
        assert client.get('/batches/' + response.json()['batch_id'], params=PARAMS).status_code == 404
        assert not repositories['TISSUE-LEGACY'].state.demand


@pytest.mark.parametrize('failure', ['partial_errors', 'unconfirmed', 'source_changed', 'policy_changed', 'wrong_digest'])
def test_transform_errors_confirmation_and_stale_evidence_never_stage(sources, failure):
    with memory_api() as (client, repositories):
        seed_masters(client, sources)
        if failure == 'partial_errors':
            data = (official_sources()[0] / 'errors/sales_orders_dirty_sample.csv').read_bytes()
        else:
            data = ('\n'.join(sources['raw/transactions/판매현황_2022.csv'].decode('utf-8-sig').splitlines()[:2]) + '\n').encode()
        policy = SalesTransformPolicy(dataset_id=DATASET, user_confirmed=failure != 'unconfirmed')
        response = client.post('/ingest/transform-preview', params=PARAMS, files=[('files', ('negative-sales.csv', data))],
            data={'policy': policy.model_dump_json(), 'use_approved_master': 'true'})
        assert response.status_code == 200, response.text
        body = response.json()
        if failure == 'partial_errors':
            assert body['status'] == 'HAS_ERRORS' and body['issues_total'] > 0 and body['records']
            assert body['issues'][0]['location']['row'] >= 2 and body['issues'][0]['code']
        if failure == 'unconfirmed':
            assert body['status'] == 'POLICY_REVIEW_REQUIRED'
        if failure == 'source_changed':
            data += b'\n'
        if failure == 'policy_changed':
            policy = policy.model_copy(update={'date_formats': ['YYYY-MM-DD']})
        response = client.post('/ingest/transformations', params=PARAMS, files=[('files', ('negative-sales.csv', data))], data={
            'policy': policy.model_dump_json(), 'use_approved_master': 'true', 'created_by': 'INGEST-E2E',
            'expected_result_digest': '0' * 64 if failure == 'wrong_digest' else body['result_digest'],
            'source_note': 'Small negative fixture derived from official sources; TEST-DOUBLE-ONLY'})
        assert response.status_code == 409, response.text
        assert response.json()['detail']['code'] == ('TRANSFORM_BLOCKED' if failure in ('partial_errors', 'unconfirmed') else 'RESULT_CHANGED')
        repo = repositories[DATASET]
        assert not repo.state.transformations and not repo.state.demand and len(repo.state.batches) == 2


def test_persistence_disabled_is_not_reported_as_saved_or_approved():
    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        for path in ('/batches', '/ingest/transformations'):
            response = client.get(path, params=PARAMS)
            assert response.status_code == 501 and response.json()['detail']['code'] == 'PERSISTENCE_DISABLED'


def test_product_material_ambiguity_requires_explicit_entity_choice(sources):
    rows = list(csv.reader(io.StringIO(sources['upload/01_products.csv'].decode('utf-8-sig'))))
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['품목코드', '품목명', '단위'])
    writer.writerow(rows[1][:3])  # Small ambiguous-header fixture, official product values unchanged.
    data = stream.getvalue().encode()
    with memory_api() as (client, repositories):
        held = client.post('/ingest/classified-mapping', params=PARAMS, files={'file': ('negative-entity-ambiguity.csv', data)})
        assert held.status_code == 200, held.text
        assert held.json()['classification']['hold'] and held.json()['mapping'] is None
        selected = client.post('/ingest/classified-mapping', params=PARAMS,
            files={'file': ('negative-entity-ambiguity.csv', data)}, data={'entity': 'product'})
        assert selected.status_code == 200 and selected.json()['selection_method'] == 'USER_SELECTION'
        assert selected.json()['mapping']['entity'] == 'product' and not selected.json()['persisted']
        assert not repositories[DATASET].state.batches


@pytest.mark.parametrize('problem,code', [('date', 'PERIOD_INVALID'), ('quantity', 'QTY_INVALID'), ('unit', 'UNIT_UNKNOWN'), ('missing_column', 'REQUIRED_FIELD_MISSING')])
def test_small_gold_derived_validation_errors_never_approve(sources, problem, code):
    rows = list(csv.reader(io.StringIO(sources['upload/05_monthly_demand.csv'].decode('utf-8-sig'))))[:2]
    if problem == 'missing_column':
        rows = [[value for index, value in enumerate(row) if index != 2] for row in rows]
    else:
        index, value = {'date': (1, '2026-13'), 'quantity': (2, 'not-a-quantity'), 'unit': (3, 'BOX')}[problem]
        rows[1][index] = value
    stream = io.StringIO(newline='')
    csv.writer(stream).writerows(rows)
    with memory_api() as (client, repositories):
        seed_masters(client, sources)
        response = upload(client, 'negative-' + problem + '.csv', stream.getvalue().encode(), 'monthly_demand')
        assert response.status_code == 201, response.text
        batch = response.json()
        assert batch['status'] in ('MAPPING_HOLD', 'HAS_ERRORS')
        details = [row for sheet in batch['validation']['sheets'] for row in sheet['holds' if problem == 'missing_column' else 'issues']]
        assert any(row['code'] == code for row in details)
        assert approve(client, batch).status_code == 409 and not repositories[DATASET].state.demand


def test_repeated_transform_request_reuses_evidence_without_approving(sources):
    data = ('\n'.join(sources['raw/transactions/판매현황_2022.csv'].decode('utf-8-sig').splitlines()[:2]) + '\n').encode()
    with memory_api() as (client, repositories):
        seed_masters(client, sources)
        policy = SalesTransformPolicy(dataset_id=DATASET, user_confirmed=True)
        preview = client.post('/ingest/transform-preview', params=PARAMS, files=[('files', ('negative-retry.csv', data))],
            data={'policy': policy.model_dump_json(), 'use_approved_master': 'true'}).json()
        settings = {'policy': policy.model_dump_json(), 'use_approved_master': 'true', 'expected_result_digest': preview['result_digest'],
            'source_note': 'Duplicate-request negative fixture derived from official source', 'created_by': 'INGEST-E2E'}
        first = client.post('/ingest/transformations', params=PARAMS, files=[('files', ('negative-retry.csv', data))], data=settings)
        second = client.post('/ingest/transformations', params=PARAMS, files=[('files', ('negative-retry.csv', data))], data=settings)
        assert first.status_code == 201 and second.status_code == 200
        assert first.json()['transformation_id'] == second.json()['transformation_id']
        assert first.json()['batch_id'] == second.json()['batch_id'] and second.json()['batch_status'] == 'READY_FOR_APPROVAL'
        assert not repositories[DATASET].state.demand
