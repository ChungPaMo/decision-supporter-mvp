"""Opt-in SQL E2E after 0010. This fixture never migrates or resets a schema."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.batches import receipts
from app.dataset_schema_v3 import CORE_TABLES, schema_for
from app.datasets import get_dataset_engine
from app.integrations import planning
from app.integrations.planning_receipts import read_approved_receipts
from contracts.interfaces.planning import PlanCommand
from scripts.postgresql_preservation import docker_identity
from scripts.verify_test_db import DATABASE, ROLE, SENTINEL, TOKEN, validate_test_url
from tests.test_db_dataset_e2e import seeded_api


DATASET = 'CHUNGPAMO-2027'
SCHEMA = schema_for(DATASET)
TABLES = set(CORE_TABLES) - {'unit'}
HEADER = 'po_id,revision,material_id,expected_date,effective_date,ordered_qty,received_qty,unit,supplier_id,status\n'


def receipt(revision=1, received=0, unit='kg', material='MR-N3', status='OPEN', *,
            po='PO-2701-001', expected='2027-01-20', effective='2026-12-31', ordered=10000):
    return (HEADER + f'{po},{revision},{material},{expected},{effective},{ordered},{received},{unit},SUP-PULP-A,{status}\n').encode()


def identify(c):
    assert tuple(c.execute(text('SELECT current_database(), current_user, session_user')).one()) == (DATABASE, ROLE, ROLE)
    assert c.execute(text('SELECT version_num FROM public.alembic_version')).scalar_one() == '0010'
    assert c.execute(text('SELECT purpose FROM public.regression_test_sentinel')).scalars().all() == [SENTINEL]


def assert_seed_only(c):
    for schema in ('public', SCHEMA):
        names = set(c.execute(text('SELECT tablename FROM pg_tables WHERE schemaname=:schema'),
                              {'schema': schema}).scalars())
        extra = {'dataset', 'alembic_version', 'regression_test_sentinel'} if schema == 'public' else set()
        assert names == set(CORE_TABLES) | extra
        assert c.exec_driver_sql(f'SELECT count(*) FROM "{schema}".unit').scalar_one() == 6
        assert all(c.exec_driver_sql(f'SELECT count(*) FROM "{schema}"."{table}"').scalar_one() == 0
                   for table in TABLES)


@pytest.fixture
def receipt_api(request, tmp_path_factory):
    if request.config.getoption('--no-db') or os.environ.get('CHUNGPAMO_ALLOW_RECEIPT_SQL_TEST') != TOKEN:
        pytest.skip('Explicit scheduled-receipt SQL test approval is required')
    url = validate_test_url()
    docker_identity()
    read = create_engine(url, connect_args={'connect_timeout': 3, 'options': '-c default_transaction_read_only=on'})
    try:
        with read.connect() as c:
            identify(c)
            assert c.exec_driver_sql('SHOW transaction_read_only').scalar_one() == 'on'
            assert not c.execute(text("SELECT has_database_privilege(current_user,'chungpamo','CONNECT')")).scalar_one()
            assert c.execute(text('SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()')).scalar_one() == 0
            schemas = set(c.execute(text("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema'")).scalars())
            assert schemas == {'public', SCHEMA}
            assert c.execute(text('SELECT dataset_id, schema_name, source_type, status FROM public.dataset ORDER BY dataset_id')).all() == [
                (DATASET, SCHEMA, 'SYNTHETIC', 'ACTIVE'), ('TISSUE-LEGACY', 'public', 'SYNTHETIC', 'ACTIVE')]
            assert_seed_only(c)
            dependents = c.execute(text('''
                WITH RECURSIVE dep(oid) AS (
                  SELECT unnest(ARRAY[to_regclass(:batch)::oid,to_regclass(:forecast)::oid])
                  UNION SELECT k.conrelid FROM pg_constraint k JOIN dep ON k.confrelid=dep.oid WHERE k.contype='f'
                ) SELECT n.nspname, r.relname FROM dep JOIN pg_class r ON r.oid=dep.oid
                  JOIN pg_namespace n ON n.oid=r.relnamespace
            '''), {'batch': f'{SCHEMA}.import_batch', 'forecast': f'{SCHEMA}.forecast_run'}).all()
            assert len(TABLES) == 29 and {tuple(row) for row in dependents} == {(SCHEMA, table) for table in TABLES}
    finally:
        read.dispose()
    engine = create_engine(url, connect_args={'connect_timeout': 3})
    try:
        with seeded_api(engine, tmp_path_factory, seed_legacy=False) as api:
            yield api
    finally:
        try:
            with engine.begin() as c:
                identify(c)
                assert not c.exec_driver_sql(f"""SELECT EXISTS(
                    SELECT 1 FROM "{SCHEMA}".import_batch WHERE source_type <> 'SYNTHETIC' OR
                      source_note NOT IN ('Fresh isolated regression synthetic fixture','C02 isolated synthetic test')
                      OR source_note IS NULL)""").scalar_one()
                tables = ','.join(f'"{SCHEMA}"."{table}"' for table in sorted(TABLES))
                c.exec_driver_sql(f'TRUNCATE {tables} RESTRICT')
                assert_seed_only(c)
        finally:
            engine.dispose()


def test_actual_approved_receipts_and_parent_what_if(receipt_api, monkeypatch, record_property):
    client, _ = receipt_api
    scope = {'dataset_id': DATASET}

    def stage(data):
        response = client.post('/batches', params=scope, files={'file': ('receipt.csv', data)},
                               data={'entity': 'scheduled_receipt', 'source_type': 'SYNTHETIC',
                                     'source_note': 'C02 isolated synthetic test'})
        assert response.status_code == 201, response.json()
        return response.json()

    def approve(batch):
        return client.post('/batches/' + batch['batch_id'] + '/approve', params=scope,
                           json={'approved_by': 'TEST-REVIEWER', 'expected_result_digest': batch['result_digest']})

    def post(path, body):
        return client.post(path, params=scope, json=body)

    def january(output):
        return {r['plan_id']: (Decimal(r['available_qty']), Decimal(r['shortage_qty']))
                for r in output['material_requirements'] if r['material_id'] == 'MR-N3' and r['period'] == '2027-01'}

    def ledger():
        with get_dataset_engine(DATASET).connect() as connection:
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            return connection.exec_driver_sql('''
                SELECT receipt_key, revision, batch_id::text, ordered_qty, received_qty,
                       source_sheet, source_row_no, source_row_sha256
                FROM scheduled_receipt_revision ORDER BY receipt_key, revision
            ''').all()

    def what_if(parent, overrides):
        return {**command, 'scenario': 'WHAT_IF', 'base_plan_execution_id': parent['execution_id'], 'overrides': overrides}

    forecast = post('/forecasts', {'trained_until': '2026-12-31', 'horizon_months': 3})
    assert forecast.status_code == 201, forecast.json()
    command = {**scope, 'forecast_execution_id': forecast.json()['execution']['execution_id'],
               'product_ids': [r['product_id'] for r in client.get('/products', params=scope).json()['items']],
               'target_month': '2027-01', 'horizon_months': 3, 'as_of_date': '2026-12-31'}
    batch = stage(receipt())
    assert batch['status'] == 'READY_FOR_APPROVAL'
    checked = client.post('/batches/' + batch['batch_id'] + '/revalidate', params=scope,
                          json={'expected_version': batch['version'], 'column_overrides': {}})
    assert checked.status_code == 200
    review = checked.json()
    assert review['version'] == batch['version'] + 1 and review['status'] == 'READY_FOR_APPROVAL'
    assert review['result_digest'] == batch['result_digest']
    batch = review
    source_row = batch['validation']['sheets'][0]['records'][0]
    diagnostic = post('/planning-inputs/preview', command)
    assert diagnostic.status_code == 200
    assert diagnostic.json()['inputs']['scheduled_receipts'] == {'ready': True, 'row_count': 0}
    assert not ledger()
    empty_reply = post('/plans', command)
    assert empty_reply.status_code == 200
    empty = empty_reply.json()['result']
    assert 'RECEIPT_SOURCE_UNAVAILABLE' not in {i['code'] for i in empty['unverified']}
    assert january(empty) == {plan: (82100, Decimal(shortage)) for plan, shortage in
                              [('BASELINE', '4028.4006'), ('STABLE', '7135.1947'), ('COST_SAVING', '1827.2391')]}
    with monkeypatch.context() as patch:
        # Store a real execution using the 0009 supply boundary, without a downgrade.
        patch.setattr(planning, 'read_approved_receipts', lambda *_: None)
        legacy = post('/plan-executions', command)
        assert legacy.status_code == 201, legacy.json()
        null_parent = legacy.json()['execution']
        assert null_parent['input_snapshot']['scheduled_receipts'] is None
        assert {'code': 'RECEIPT_SOURCE_UNAVAILABLE'} in [
            {'code': i['code']} for i in null_parent['result_snapshot']['unverified']]
    unavailable = post('/plans/what-if', what_if(null_parent, {'receipt_qty.PO-2701-001': '0'}))
    assert unavailable.status_code == 422 and unavailable.json()['detail']['code'] == 'PLAN_OVERRIDE_UNSUPPORTED'

    approval = approve(batch)
    assert approval.status_code == 200, approval.json()
    approved = approval.json()
    assert approved['status'] == 'APPROVED' and approved['approved_record_count'] == 1
    assert approve(batch).status_code == 409
    original_ledger = ledger()
    assert [tuple(row) for row in original_ledger] == [
        ('PO-2701-001', 1, batch['batch_id'], Decimal(10000), Decimal(0), 'CSV', source_row['location']['row'],
         source_row['source_row_sha256'])]
    ready = post('/planning-inputs/preview', command)
    assert ready.status_code == 200
    assert ready.json()['inputs']['scheduled_receipts'] == {'ready': True, 'row_count': 1}
    assert 'RECEIPT_SOURCE_UNAVAILABLE' not in ready.json()['missing_inputs']
    stored = post('/plan-executions', command)
    assert stored.status_code == 201, stored.json()
    parent = stored.json()['execution']
    original = parent['input_snapshot']['scheduled_receipts']
    assert len(original) == 1 and original[0]['batch_id'] == batch['batch_id']
    assert 'RECEIPT_SOURCE_UNAVAILABLE' not in {i['code'] for i in parent['result_snapshot']['unverified']}
    source = next(s for s in parent['input_snapshot']['approved_inputs']['sources'] if s['batch_id'] == batch['batch_id'])
    assert (source['source_sha256'], source['result_digest'], source['batch_version']) == (
        approved['file']['sha256'], approved['result_digest'], approved['version'])
    assert january(parent['result_snapshot']) == {p: (92100, 0) for p in january(empty)}
    with get_dataset_engine('TISSUE-LEGACY').connect() as c:
        c.exec_driver_sql('SET TRANSACTION READ ONLY')
        assert read_approved_receipts(c, PlanCommand.model_validate({**command, 'dataset_id': 'TISSUE-LEGACY'})) == []
    plans = parent['result_snapshot']['plans']
    assert {p['plan_type']: p['feasibility'] for p in plans} == {
        'BASELINE': 'UNVERIFIED', 'STABLE': 'INFEASIBLE', 'COST_SAVING': 'INFEASIBLE'}
    totals = {p['plan_type']: sum(int(r['production_qty']) for r in p['production']) for p in plans}
    assert totals == {'BASELINE': 93481, 'STABLE': 96583, 'COST_SAVING': 88225}
    assert any('STOCKOUT' in r['reason_codes'] for r in parent['result_snapshot']['constraint_evaluations'])
    assert any('PROCUREMENT_REQUIRED' in r['reason_codes'] for r in parent['result_snapshot']['constraint_evaluations'])
    record_property('production_ea', json.dumps(totals, sort_keys=True))
    record_property('mr_n3_january', '82100 -> 92100 kg; 4028.4006 / 7135.1947 / 1827.2391 -> 0 kg')
    what_if_values = {}
    for qty, available in [('5000', 87100), ('0', 82100)]:
        request = what_if(parent, {'receipt_qty.PO-2701-001': qty})
        preview = post('/plans/what-if', request)
        assert preview.status_code == 200 and preview.json()['persisted'] is False
        adjusted = post('/plan-executions', request)
        assert adjusted.status_code == 201, adjusted.json()
        child = adjusted.json()['execution']
        assert child['input_snapshot']['base_plan_snapshot']['input_digest'] == parent['input_digest']
        assert child['input_snapshot']['base_plan_snapshot']['result_digest'] == parent['result_digest']
        assert child['input_snapshot']['scheduled_receipts'] == original
        assert child['input_snapshot']['command']['overrides'] == request['overrides']
        assert child['input_digest'] == preview.json()['input_digest'] and child['result_snapshot'] == preview.json()['result']
        assert all(row[0] == available for row in january(child['result_snapshot']).values())
        retry = post('/plan-executions', request)
        assert retry.status_code == 200 and retry.json() == {'execution': child, 'reused': True}
        detail = client.get('/plan-executions/' + child['execution_id'], params=scope)
        assert detail.status_code == 200 and detail.json() == child
        what_if_values[qty] = available
    record_property('receipt_what_if_kg', json.dumps(what_if_values, sort_keys=True))
    combined = post('/plans/what-if', what_if(parent, {
        'receipt_qty.PO-2701-001': '5000', 'overtime_hours_limit.SAW1.2027-02': '80'}))
    assert combined.status_code == 200
    result = combined.json()['result']
    stable = next(p for p in result['plans'] if p['plan_type'] == 'STABLE')
    assert sum(int(row['production_qty']) for row in stable['production']) == 97791
    assert all(row[0] == 87100 for row in january(result).values())
    unknown = post('/plans/what-if', what_if(parent, {'receipt_qty.UNKNOWN-PO': '0'}))
    assert unknown.status_code == 422 and unknown.json()['detail']['code'] == 'PLAN_OVERRIDE_UNSUPPORTED'
    foreign = {'dataset_id': 'TISSUE-LEGACY'}
    foreign_request = {**what_if(parent, {'receipt_qty.PO-2701-001': '0'}), **foreign}
    for route in ('/plans/what-if', '/plan-executions'):
        response = client.post(route, params=foreign, json=foreign_request)
        assert response.status_code == 404 and response.json()['detail']['code'] == 'PLAN_NOT_FOUND'
    path = '/plan-executions/' + parent['execution_id']
    assert client.get(path, params=scope).json() == parent
    assert january(post('/plans', command).json()['result']) == january(parent['result_snapshot'])
    assert ledger() == original_ledger

    def failed_read(connection, _):
        connection.exec_driver_sql('SELECT 1 / 0')
    with monkeypatch.context() as patch:
        patch.setattr(planning, 'read_approved_receipts', failed_read)
        failure = post('/planning-inputs/preview', command)
        assert failure.status_code == 500 and failure.json()['detail']['code'] == 'PERSISTENCE_ERROR'

    for statement in ("UPDATE scheduled_receipt_revision SET received_qty=1 WHERE receipt_key='PO-2701-001'",
                      "DELETE FROM scheduled_receipt_revision WHERE receipt_key='PO-2701-001'"):
        with pytest.raises(IntegrityError):
            with get_dataset_engine(DATASET).begin() as c:
                c.exec_driver_sql(statement)
                raise AssertionError('Approved ledger unexpectedly allowed a mutation; transaction rolled back')
    assert ledger() == original_ledger

    pending = stage(receipt(po='PO-ROLLBACK'))
    actual_commit = receipts.commit

    def fail_after_insert(tx, *args):
        actual_commit(tx, *args)
        tx.c.exec_driver_sql('SELECT 1 / 0')
    with monkeypatch.context() as patch:
        patch.setattr(receipts, 'commit', fail_after_insert)
        failed = approve(pending)
        assert failed.status_code == 500 and failed.json()['detail']['code'] == 'PERSISTENCE_ERROR'
    still_staged = client.get('/batches/' + pending['batch_id'], params=scope).json()
    assert still_staged['status'] == 'READY_FOR_APPROVAL' and still_staged['version'] == pending['version']
    assert ledger() == original_ledger

    for data in (receipt(received=10001), receipt(unit='EA'), receipt(material='UNKNOWN-MAT'),
                 receipt(revision=1, received=1), receipt(expected='2027-02-30'),
                 receipt(revision=3), receipt(revision=2, effective='2026-12-30')):
        denied = stage(data)
        assert denied['status'] == 'HAS_ERRORS' and approve(denied).status_code == 409
    contenders = [stage(receipt(revision=2, received=n)) for n in (1000, 2000)]
    assert all(r['status'] == 'READY_FOR_APPROVAL' for r in contenders)
    assert january(post('/plans', command).json()['result']) == january(parent['result_snapshot'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(approve, contenders))
    assert sorted(r.status_code for r in decisions) == [200, 409]
    winning_received = 1000 if decisions[0].status_code == 200 else 2000
    assert all(row[0] == 92100-winning_received for row in january(post('/plans', command).json()['result']).values())
    assert stage(receipt(revision=3, received=winning_received-1))['status'] == 'HAS_ERRORS'
    assert stage(receipt(revision=1, expected='2027-02-01'))['status'] == 'HAS_ERRORS'
    assert approve(stage(receipt(revision=3, received=winning_received, status='CANCELLED'))).status_code == 200
    assert stage(receipt(revision=4, received=winning_received))['status'] == 'HAS_ERRORS'
    assert january(post('/plans', command).json()['result']) == january(empty)
    assert client.get(path, params=scope).json() == parent

    # New POs isolate the date, completion, and overdue cases from the official scenario above.
    for data in (receipt(po='PO-FULL', received=10000), receipt(po='PO-OUTSIDE', expected='2027-04-01'),
                 receipt(po='PO-FUTURE', effective='2027-01-03'),
                 receipt(po='PO-OVERDUE', ordered=200, expected='2026-12-31')):
        assert approve(stage(data)).status_code == 200
    options = get_dataset_engine(DATASET)
    with options.connect() as c:
        c.exec_driver_sql('SET TRANSACTION READ ONLY')
        selected = read_approved_receipts(c, PlanCommand.model_validate(command))
        assert {r.po_id for r in selected} >= {'PO-FULL', 'PO-OUTSIDE', 'PO-OVERDUE'}
        assert 'PO-FUTURE' not in {r.po_id for r in selected}
    overdue = post('/plans', command)
    assert overdue.status_code == 200 and any(i['code'] == 'RECEIPT_OVERDUE' for i in overdue.json()['result']['warnings'])
    assert all(row[0] == 82300 for row in january(overdue.json()['result']).values())
    assert post('/planning-inputs/preview', command).json()['inputs']['scheduled_receipts']['row_count'] == 1
    next_day = post('/planning-inputs/preview', {**command, 'as_of_date': '2027-01-03'})
    assert next_day.status_code == 200 and next_day.json()['inputs']['scheduled_receipts']['row_count'] == 2
