"""Official 14-file journey through real SQL, plus real constraint failure/concurrency.

Uses only the separately approved regression DB; no production service/persistence double.
"""
from concurrent.futures import ThreadPoolExecutor
import csv
from decimal import Decimal
import hashlib
import io
import json
from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from app.main import app
from app.config import Settings
from app.datasets import get_dataset_engine
from app.dataset_schema_v2 import schema_for
from app.ingest.history_repository import SqlTransformationTx
from contracts.interfaces.ingestion import SalesTransformPolicy
from scripts.verify_synthetic_contracts import FILES
from scripts.verify_test_db import assert_destructive_engine, DATABASE, ROLE
from tests.ingestion_e2e_support import official_sources
from tests.test_ingestion_api_e2e import demand_rows

DATASET = 'CHUNGPAMO-2027'
PARAMS = {'dataset_id': DATASET}


@pytest.fixture(scope='module')
def official_db(test_engine):
    from app import db
    from app.api import batches, forecasts, ingest_history
    assert_destructive_engine(test_engine)
    target, manifest, sources = official_sources()
    settings = Settings(_env_file=None, persistence='postgres', database_url=test_engine.url.render_as_string(hide_password=False))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(db, 'get_engine', lambda: test_engine)
        for module in (batches, forecasts, ingest_history):
            patch.setattr(module, 'get_settings', lambda: settings)
        client = TestClient(app)
        assert not app.dependency_overrides
        try:
            for name, entity in FILES:
                if entity == 'monthly_demand':
                    continue  # Independent gold only. Demand comes from the five raw sources.
                response = client.post('/batches', params=PARAMS, files={'file': (name, sources['upload/' + name])},
                    data={'entity': entity, 'source_type': 'SYNTHETIC', 'source_note': 'Official CHUNGPAMO-2027 PostgreSQL regression'})
                assert response.status_code == 201, response.text
                batch = response.json()
                response = client.post('/batches/' + batch['batch_id'] + '/approve', params=PARAMS,
                    json={'approved_by': 'DB-E2E-REVIEWER', 'expected_result_digest': batch['result_digest']})
                assert response.status_code == 200, response.text
            yield client, test_engine, target, manifest, sources
        finally:
            assert_destructive_engine(test_engine)
            with test_engine.begin() as c:
                assert tuple(c.execute(text('SELECT current_database(),current_user')).one()) == (DATABASE, ROLE)
                c.execute(text('TRUNCATE "' + schema_for(DATASET) + '".forecast_run,"' + schema_for(DATASET) + '".import_batch CASCADE'))


def submission(client, sources):
    sales = [(name.rsplit('/', 1)[-1], content) for name, content in sources.items() if name.startswith('raw/')]
    policy = SalesTransformPolicy(dataset_id=DATASET, user_confirmed=True)
    response = client.post('/ingest/transform-preview', params=PARAMS, files=[('files', item) for item in sales],
        data={'policy': policy.model_dump_json(), 'use_approved_master': 'true'})
    assert response.status_code == 200, response.text
    return sales, policy, response.json()


def test_official_sql_journey_concurrent_staging_replay_approval_forecast(official_db):
    client, engine, target, manifest, sources = official_db
    sales, policy, preview = submission(client, sources)
    gold = list(csv.DictReader(io.StringIO(sources['upload/05_monthly_demand.csv'].decode('utf-8-sig'))))
    assert len(sources) == 14 and preview['counts'] == manifest['counts']
    assert demand_rows(preview['records']) == demand_rows(gold)
    assert client.get('/demand/monthly', params=PARAMS).json()['total'] == 0
    classified = client.post('/classifications/file', files={'file': sales[0]}).json()
    assert classified['hold'] and classified['recommended_entity'] is None
    mapping = client.post('/ingest/mapping-suggestions', params=PARAMS, files={'file': sales[0]},
        data={'entity': 'monthly_demand', 'use_approved_master': 'true'})
    assert mapping.status_code == 200 and mapping.json()['sheets'][0]['status'] == 'HOLD'
    form = {'policy': policy.model_dump_json(), 'expected_result_digest': preview['result_digest'],
            'use_approved_master': 'true', 'created_by': 'DB-E2E-REVIEWER', 'source_note': 'Official 14-file PostgreSQL E2E'}
    def create():
        return TestClient(app).post('/ingest/transformations', params=PARAMS, files=[('files', item) for item in sales], data=form)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 201], [r.text for r in responses]
    first, second = [r.json() for r in responses]
    assert first['transformation_id'] == second['transformation_id'] and first['batch_id'] == second['batch_id']
    assert first['persisted'] and first['batch_status'] == 'READY_FOR_APPROVAL'
    assert not first['preview']['persisted'] and not first['auto_approve']
    tid, bid = first['transformation_id'], first['batch_id']
    scoped = get_dataset_engine(DATASET)
    with scoped.connect() as c:
        stored = c.execute(text('SELECT filename,content,sha256,size_bytes FROM ingestion_transform_source ORDER BY source_index')).all()
        assert len(stored) == 5
        for (name, content), row in zip(sales, stored):
            assert row.filename == name and bytes(row.content) == content and row.size_bytes == len(content)
            assert row.sha256 == hashlib.sha256(content).hexdigest()
        evidence = c.execute(text('SELECT manifest FROM ingestion_transformation')).scalar_one()
        assert evidence['result']['policy'] == policy.model_dump(mode='json')
    batch = client.get('/batches/' + bid, params=PARAMS).json()
    assert batch['approved_at'] is None and client.get('/demand/monthly', params=PARAMS).json()['total'] == 0
    assert client.post('/batches/' + bid + '/approve', params=PARAMS,
        json={'approved_by': 'DB-E2E-REVIEWER', 'expected_result_digest': first['result_digest']}).status_code == 409
    approved = client.post('/batches/' + bid + '/approve', params=PARAMS,
        json={'approved_by': 'DB-E2E-REVIEWER', 'expected_result_digest': batch['result_digest']})
    assert approved.status_code == 200 and approved.json()['approved_record_count'] == 498, approved.text
    # New client/connection re-reads committed DB evidence, not an in-memory response cache.
    detail = TestClient(app).get('/ingest/transformations/' + tid, params=PARAMS)
    assert detail.status_code == 200 and detail.json()['batch_status'] == 'APPROVED', detail.text
    assert client.get('/ingest/transformations/' + tid, params={'dataset_id': 'TISSUE-LEGACY'}).status_code == 404
    actual = client.get('/demand/monthly', params={**PARAMS, 'limit': 1000}).json()
    assert actual['total'] == 498 and demand_rows(actual['items']) == demand_rows(gold)
    # Derived negative probe: unapproved row must never leak into the forecast snapshot.
    pending_data = ('product_id,period,demand_qty,unit\n' + gold[0]['product_id'] + ',2026-01,999,EA\n').encode()
    pending = client.post('/batches', params=PARAMS, files={'file': ('negative-unapproved.csv', pending_data)},
        data={'entity': 'monthly_demand', 'source_type': 'SYNTHETIC', 'source_note': 'Unapproved isolation probe derived from official gold'}).json()
    forecast = client.post('/forecasts', params=PARAMS, json={'trained_until': '2026-12-31', 'horizon_months': 3, 'p50_method': 'MA12'})
    assert forecast.status_code == 201, forecast.text
    execution = forecast.json()['execution']
    assert {r['batch_id'] for r in execution['input_batches']} == {bid}
    assert pending['batch_id'] not in {r['batch_id'] for r in execution['input_batches']}
    with scoped.connect() as c:
        snapshot = c.execute(text('SELECT input_snapshot FROM forecast_run WHERE execution_id=:e'), {'e': UUID(execution['execution_id'])}).scalar_one()
        assert len(snapshot['rows']) == 498
        assert demand_rows(snapshot['rows']) == demand_rows(gold)
    assert all(Decimal(r['p50']) <= Decimal(r['p80']) <= Decimal(r['p90']) for r in execution['result']['forecasts'])
    assert client.get('/forecasts/' + execution['execution_id'], params=PARAMS).json()['execution_id'] == execution['execution_id']
    assert all(hashlib.sha256((target / name).read_bytes()).hexdigest() == sha for name, sha in manifest['files'].items())
    report = {'scope': 'ACTUAL POSTGRESQL / regression DB only', 'source_hashes_verified': 14, 'counts': preview['counts'],
        'transformation_id': tid, 'batch_id': bid, 'forecast_execution_id': execution['execution_id'],
        'forecast_status': execution['status'], 'forecast_rows': len(execution['result']['forecasts']),
        'concurrent_http': sorted(r.status_code for r in responses), 'source_bytes_equal': True, 'gold_rows_equal': True}
    from pathlib import Path
    out = Path(__file__).resolve().parents[2] / '.artifacts/postgresql-ingestion-20261117/official-e2e.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')


def test_real_database_failure_rolls_back_all_transformation_writes(official_db, monkeypatch):
    client, engine, target, manifest, sources = official_db
    # A small negative input derived from the official row, not a replacement success dataset.
    name, data = next((n, b) for n, b in sources.items() if n.startswith('raw/'))
    reader = csv.reader(io.StringIO(data.decode('utf-8-sig')))
    header, row = next(reader), next(reader)
    stream = io.StringIO(newline=''); writer = csv.writer(stream); writer.writerow(header); writer.writerow(row)
    files = [('negative-atomic.csv', stream.getvalue().encode())]
    policy = SalesTransformPolicy(dataset_id=DATASET, user_confirmed=True)
    preview = client.post('/ingest/transform-preview', params=PARAMS, files=[('files', item) for item in files],
        data={'policy': policy.model_dump_json(), 'use_approved_master': 'true'}).json()
    scoped = get_dataset_engine(DATASET)
    tables = ('import_batch', 'batch_source_file', 'ingestion_transformation', 'ingestion_transform_source')
    def counts():
        with scoped.connect() as c:
            return tuple(c.execute(text('SELECT count(*) FROM ' + t)).scalar_one() for t in tables)
    before = counts()
    insert = SqlTransformationTx.insert_transformation
    def violate(tx, record, contents):
        insert(tx, record, contents)
        tx.c.execute(text('''INSERT INTO ingestion_transform_source SELECT * FROM ingestion_transform_source
            WHERE transformation_id=:id AND source_index=0'''), {'id': record['transformation_id']})
    monkeypatch.setattr(SqlTransformationTx, 'insert_transformation', violate)
    response = client.post('/ingest/transformations', params=PARAMS, files=[('files', item) for item in files],
        data={'policy': policy.model_dump_json(), 'expected_result_digest': preview['result_digest'], 'use_approved_master': 'true',
              'source_note': 'Real unique-constraint failure after all inserts', 'created_by': 'DB-E2E-REVIEWER'})
    assert response.status_code == 500 and response.json()['detail']['code'] == 'PERSISTENCE_ERROR', response.text
    assert counts() == before


def test_committed_evidence_is_immutable_and_extra_sources_fail_at_commit(official_db):
    client, engine, *_ = official_db
    scoped = get_dataset_engine(DATASET)
    tid = UUID(client.get('/ingest/transformations', params=PARAMS).json()['items'][0]['transformation_id'])
    for table in ('ingestion_transformation', 'ingestion_transform_source'):
        with pytest.raises(IntegrityError):
            with scoped.begin() as c:
                c.execute(text('UPDATE ' + table + ' SET transformation_id=transformation_id WHERE transformation_id=:t'), {'t': tid})
    content = b'SYNTHETIC unrecorded source'
    with pytest.raises(DBAPIError, match='sources incomplete'):
        with scoped.begin() as c:
            c.execute(text('''INSERT INTO ingestion_transform_source(transformation_id,source_index,filename,sha256,content,size_bytes)
                VALUES(:t,5,'negative-extra.csv',:sha,:content,:size)'''),
                {'t': tid, 'sha': hashlib.sha256(content).hexdigest(), 'content': content, 'size': len(content)})
    with scoped.connect() as c:
        assert c.execute(text('SELECT count(*) FROM ingestion_transform_source WHERE transformation_id=:t'), {'t': tid}).scalar_one() == 5
