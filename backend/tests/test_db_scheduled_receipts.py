"""Opt-in SQL E2E after 0010. This fixture never migrates or resets a schema."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os

import pytest
from sqlalchemy import create_engine, text

from app.dataset_schema_v3 import CORE_TABLES, schema_for
from app.datasets import get_dataset_engine
from app.integrations.planning_receipts import read_approved_receipts
from contracts.interfaces.planning import PlanCommand
from scripts.postgresql_preservation import docker_identity
from scripts.verify_test_db import DATABASE, ROLE, SENTINEL, TOKEN, validate_test_url
from tests.test_db_dataset_e2e import seeded_api


DATASET = 'CHUNGPAMO-2027'
SCHEMA = schema_for(DATASET)
TABLES = set(CORE_TABLES) - {'unit'}
HEADER = 'po_id,revision,material_id,expected_date,effective_date,ordered_qty,received_qty,unit,supplier_id,status\n'


def receipt(revision=1, received=0, unit='kg', material='MR-N3', status='OPEN'):
    return (HEADER + f'PO-2701-001,{revision},{material},2027-01-20,2026-12-31,10000,{received},{unit},SUP-PULP-A,{status}\n').encode()


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


def test_actual_approved_receipts_and_parent_what_if(receipt_api):
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

    forecast = post('/forecasts', {'trained_until': '2026-12-31', 'horizon_months': 3})
    assert forecast.status_code == 201, forecast.json()
    command = {**scope, 'forecast_execution_id': forecast.json()['execution']['execution_id'],
               'product_ids': [r['product_id'] for r in client.get('/products', params=scope).json()['items']],
               'target_month': '2027-01', 'horizon_months': 3, 'as_of_date': '2026-12-31'}
    batch = stage(receipt())
    assert batch['status'] == 'READY_FOR_APPROVAL'
    empty_reply = post('/plans', command)
    assert empty_reply.status_code == 200
    empty = empty_reply.json()['result']
    assert 'RECEIPT_SOURCE_UNAVAILABLE' not in {i['code'] for i in empty['unverified']}
    assert january(empty) == {plan: (82100, Decimal(shortage)) for plan, shortage in
                              [('BASELINE', '4028.4006'), ('STABLE', '7135.1947'), ('COST_SAVING', '1827.2391')]}
    assert approve(batch).status_code == 200
    assert approve(batch).status_code == 409
    stored = post('/plan-executions', command)
    assert stored.status_code == 201, stored.json()
    parent = stored.json()['execution']
    original = parent['input_snapshot']['scheduled_receipts']
    assert len(original) == 1 and original[0]['batch_id'] == batch['batch_id']
    assert any(s['batch_id'] == batch['batch_id'] for s in parent['input_snapshot']['approved_inputs']['sources'])
    assert january(parent['result_snapshot']) == {p: (92100, 0) for p in january(empty)}
    with get_dataset_engine('TISSUE-LEGACY').connect() as c:
        c.exec_driver_sql('SET TRANSACTION READ ONLY')
        assert read_approved_receipts(c, PlanCommand.model_validate({**command, 'dataset_id': 'TISSUE-LEGACY'})) == []
    assert {p['plan_type']: p['feasibility'] for p in parent['result_snapshot']['plans']} == {
        'BASELINE': 'UNVERIFIED', 'STABLE': 'INFEASIBLE', 'COST_SAVING': 'INFEASIBLE'}
    for qty, available in [('5000', 87100), ('0', 82100)]:
        adjusted = post('/plan-executions', {**command, 'scenario': 'WHAT_IF', 'base_plan_execution_id': parent['execution_id'],
                        'overrides': {'receipt_qty.PO-2701-001': qty}})
        assert adjusted.status_code == 201, adjusted.json()
        child = adjusted.json()['execution']
        assert child['input_snapshot']['scheduled_receipts'] == original
        assert all(row[0] == available for row in january(child['result_snapshot']).values())
    path = '/plan-executions/' + parent['execution_id']
    assert client.get(path, params=scope).json() == parent
    assert january(post('/plans', command).json()['result']) == january(parent['result_snapshot'])

    for data in (receipt(received=10001), receipt(unit='EA'), receipt(material='UNKNOWN-MAT'),
                 receipt(revision=1, received=1)):
        denied = stage(data)
        assert denied['status'] == 'HAS_ERRORS' and approve(denied).status_code == 409
    contenders = [stage(receipt(revision=2, received=n)) for n in (1000, 2000)]
    assert all(r['status'] == 'READY_FOR_APPROVAL' for r in contenders)
    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(approve, contenders))
    assert sorted(r.status_code for r in decisions) == [200, 409]
    winning_received = 1000 if decisions[0].status_code == 200 else 2000
    assert all(row[0] == 92100-winning_received for row in january(post('/plans', command).json()['result']).values())
    assert approve(stage(receipt(revision=3, received=winning_received, status='CANCELLED'))).status_code == 200
    assert stage(receipt(revision=4, received=winning_received))['status'] == 'HAS_ERRORS'
    assert january(post('/plans', command).json()['result']) == january(empty)
    assert client.get(path, params=scope).json() == parent
