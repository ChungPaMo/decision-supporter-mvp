"""SQL-provider orchestration using test doubles; no PostgreSQL execution claim."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from app.batches.repository import ApprovedProduct, ApprovedInventory
from app.errors import ApiError
from app.integrations import planning as adapter
from contracts.interfaces.modules import PlanCommand

PRODUCT_BATCH = UUID(int=2)


@pytest.fixture
def sources(monkeypatch):
    seen = []
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
            assert parameters['ids'] == [PRODUCT_BATCH]
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: [
                {'batch_id': PRODUCT_BATCH, 'batch_version': 1, 'entity': 'product', 'source_sha256': 'a'*64,
                 'result_digest': 'b'*64, 'approved_at': '2026-12-31T00:00:00Z'}]))
    class Database:
        def connect(self): return Connection()
    class Tx:
        def __init__(self, connection): pass
        def list_products(self, *args): return [ApprovedProduct('TP-10R', 'Synthetic', 'EA', None, Decimal('1000'), 'SYNTHETIC', PRODUCT_BATCH)], 1
        def list_materials(self, *args): return [], 0
        def list_boms(self, *args): return [], 0
        def list_inventory(self, *args):
            return [ApprovedInventory('PRODUCT', 'TP-10R', date(2027, 1, 1), Decimal(1), Decimal(0), 'EA', 'SYNTHETIC', PRODUCT_BATCH)], 1
    forecast = SimpleNamespace(status='PARTIAL', input_digest='sha256:'+'c'*64,
        result=SimpleNamespace(forecasts=[SimpleNamespace(product_id='TP-10R', target_month='2027-01', p50='10000', p80='12000', p90='13500')]))
    monkeypatch.setattr(adapter, 'SqlBatchTx', Tx)
    monkeypatch.setattr(adapter.ForecastRuns, '_detail', lambda c, id: forecast)
    monkeypatch.setattr(adapter, 'planning_snapshot', lambda c, cmd: (None,None,set(),['CAPACITY_NOT_REGISTERED','ROUTING_NOT_REGISTERED','POLICY_NOT_CONFIRMED']))
    return adapter.SqlPlanningSourceProvider(Database()), forecast, seen


def command(**changes):
    return PlanCommand.model_validate({'forecast_execution_id': str(UUID(int=1)), 'product_ids': ['TP-10R'],
                                      'target_month': '2027-01', 'as_of_date': '2026-12-31', **changes})


def test_approved_snapshot_is_read_only_and_missing_inventory_is_not_zero(sources):
    provider, _, sql = sources
    snapshot = provider.load(command())
    assert sql[0] == 'SET TRANSACTION READ ONLY'
    assert snapshot.approved_inputs.products[0].safety_stock_qty == '1000'
    assert snapshot.approved_inputs.inventory == []
    assert 'INVENTORY_COVERAGE' in snapshot.missing_inputs
    assert 'CAPACITY_NOT_REGISTERED' in snapshot.missing_inputs


@pytest.mark.parametrize('failure', ['failed', 'missing_product', 'missing_month'])
def test_unusable_saved_forecast_never_becomes_zero_demand(sources, failure):
    provider, forecast, _ = sources
    if failure == 'failed': forecast.status = 'FAILED'
    if failure == 'missing_product': forecast.result.forecasts[0].product_id = 'OTHER'
    with pytest.raises(ApiError) as error:
        provider.load(command(target_month='2027-02') if failure == 'missing_month' else command())
    assert error.value.status == 409


def test_pagination_reads_every_page_and_refuses_truncated_input():
    assert len(adapter._all_pages(lambda limit, offset: (list(range(min(limit, 201-offset))), 201))) == 201
    with pytest.raises(ApiError): adapter._all_pages(lambda l, o: ([], 5))
