"""SQL-provider orchestration using test doubles; no PostgreSQL execution claim."""
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from app.batches.repository import ApprovedProduct, ApprovedInventory
from app.errors import ApiError
from app.forecast.runs_schemas import InputBatchSnapshot
from app.integrations import planning as adapter
from app.main import app
from contracts.interfaces.modules import PlanCommand

PRODUCT_BATCH = UUID(int=2)
DEMAND_BATCH = UUID(int=3)


@pytest.fixture
def sources(monkeypatch):
    seen = []
    approved_at = datetime(2026, 12, 31, tzinfo=timezone.utc)
    product_source = {'batch_id': PRODUCT_BATCH, 'batch_version': 1, 'entity': 'product',
                      'source_sha256': 'a'*64, 'result_digest': 'b'*64, 'approved_at': approved_at}
    demand_source = {**product_source, 'batch_id': DEMAND_BATCH, 'entity': 'monthly_demand'}
    approved = [product_source, demand_source]
    class Connection:
        def execution_options(self, **options):
            assert options == {'isolation_level': 'REPEATABLE READ'}
            return self
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, query, parameters=None):
            sql = str(query); seen.append(sql)
            if sql.startswith('SET'): return None
            assert "status='APPROVED'" in sql and 'blocking_error_count=0' in sql
            assert parameters == {'ids': [PRODUCT_BATCH, DEMAND_BATCH], 'dataset_id': database.dataset_id}
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: approved))
    class Database:
        dataset_id = 'TISSUE-LEGACY'
        def connect(self): return Connection()
    database = Database()
    class Tx:
        def __init__(self, connection): pass
        def list_products(self, *args): return [ApprovedProduct('TP-10R', 'Synthetic', 'EA', None, Decimal('1000'), 'SYNTHETIC', PRODUCT_BATCH)], 1
        def list_materials(self, *args): return [], 0
        def list_boms(self, *args): return [], 0
        def list_inventory(self, *args):
            return [ApprovedInventory('PRODUCT', 'TP-10R', date(2027, 1, 1), Decimal(1), Decimal(0), 'EA', 'SYNTHETIC', PRODUCT_BATCH)], 1
    forecast = SimpleNamespace(status='PARTIAL', dataset_id=database.dataset_id, input_digest='sha256:'+'c'*64,
        input_batches=[InputBatchSnapshot.model_validate(demand_source)],
        result=SimpleNamespace(forecasts=[SimpleNamespace(product_id='TP-10R', target_month='2027-01', p50='10000', p80='12000', p90='13500')]))
    monkeypatch.setattr(adapter, 'SqlBatchTx', Tx)
    monkeypatch.setattr(adapter.ForecastRuns, '_detail', lambda c, id: forecast)
    monkeypatch.setattr(adapter, 'planning_snapshot', lambda c, cmd: (None,None,set(),['CAPACITY_NOT_REGISTERED','ROUTING_NOT_REGISTERED','POLICY_NOT_CONFIRMED']))
    return adapter.SqlPlanningSourceProvider(database), forecast, seen, approved


def command(**changes):
    return PlanCommand.model_validate({'forecast_execution_id': str(UUID(int=1)), 'product_ids': ['TP-10R'],
                                      'target_month': '2027-01', 'as_of_date': '2026-12-31', **changes})


def test_approved_snapshot_is_read_only_and_missing_inventory_is_not_zero(sources):
    provider, _, sql, _ = sources
    snapshot = provider.load(command())
    assert sql[0] == 'SET TRANSACTION READ ONLY'
    assert snapshot.approved_inputs.products[0].safety_stock_qty == '1000'
    assert snapshot.approved_inputs.inventory == []
    assert 'INVENTORY_COVERAGE' in snapshot.missing_inputs
    assert 'CAPACITY_NOT_REGISTERED' in snapshot.missing_inputs
    assert [row.batch_id for row in snapshot.approved_inputs.sources] == [PRODUCT_BATCH]


@pytest.mark.parametrize('failure', ['failed', 'missing_product', 'missing_month'])
def test_unusable_saved_forecast_never_becomes_zero_demand(sources, failure):
    provider, forecast, _, _ = sources
    if failure == 'failed': forecast.status = 'FAILED'
    if failure == 'missing_product': forecast.result.forecasts[0].product_id = 'OTHER'
    with pytest.raises(ApiError) as error:
        provider.load(command(target_month='2027-02') if failure == 'missing_month' else command())
    assert error.value.status == 409


def test_scoped_provider_includes_the_verified_demand_batch_for_non_legacy(sources):
    provider, forecast, _, _ = sources
    forecast.dataset_id = provider.database.dataset_id = 'CHUNGPAMO-2027'
    snapshot = provider.load(command(dataset_id='CHUNGPAMO-2027'))
    assert [row.batch_id for row in snapshot.approved_inputs.sources] == [PRODUCT_BATCH, DEMAND_BATCH]


def test_foreign_forecast_is_hidden_before_approved_rows_are_read(sources):
    provider, forecast, seen, _ = sources
    forecast.dataset_id = 'OTHER'
    with pytest.raises(ApiError) as error:
        provider.load(command())
    assert (error.value.status, error.value.code.value) == (404, 'FORECAST_NOT_FOUND')
    assert seen == ['SET TRANSACTION READ ONLY']


def test_diagnostics_use_the_read_only_provider_and_hide_foreign_forecasts(sources, monkeypatch):
    provider, forecast, sql, _ = sources
    monkeypatch.setattr(adapter, 'get_source_provider', lambda: provider)
    with TestClient(app) as client:
        response = client.post('/planning-inputs/preview', json=command().model_dump(mode='json'))
        assert response.status_code == 200 and response.json()['persisted'] is False
        forecast.dataset_id = 'OTHER'
        response = client.post('/planning-inputs/preview', json=command().model_dump(mode='json'))
        assert response.status_code == 404 and response.json()['detail']['code'] == 'FORECAST_NOT_FOUND'
    assert len(sql) == 3 and sql[0] == sql[-1] == 'SET TRANSACTION READ ONLY'
    assert sql[1].startswith('SELECT')


@pytest.mark.parametrize('change', [{'batch_version': 2}, {'source_sha256': 'd'*64}, {'result_digest': 'd'*64},
                                    {'approved_at': datetime(2026, 12, 30, tzinfo=timezone.utc)},
                                    {'entity': 'inventory'}, None])
def test_stale_tampered_or_unapproved_forecast_source_is_rejected(sources, change):
    provider, _, _, approved = sources
    if change is None:
        approved.pop()  # SQL's APPROVED/scoped WHERE condition did not return this batch.
    else:
        approved[-1].update(change)
    with pytest.raises(ApiError) as error:
        provider.load(command())
    assert error.value.status == 409
    assert error.value.details['reason'] == ('APPROVED_SOURCE_MISMATCH' if change is None else 'FORECAST_SOURCE_MISMATCH')


def test_pagination_reads_every_page_and_refuses_truncated_input():
    assert len(adapter._all_pages(lambda limit, offset: (list(range(min(limit, 201-offset))), 201))) == 201
    with pytest.raises(ApiError): adapter._all_pages(lambda l, o: ([], 5))
