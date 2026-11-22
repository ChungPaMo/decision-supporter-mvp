"""SQL-provider orchestration using test doubles; no PostgreSQL execution claim."""
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from app.batches.repository import ApprovedMaterial, ApprovedProduct, ApprovedInventory
from app.errors import ApiError
from app.forecast.runs_schemas import InputBatchSnapshot
from app.integrations import planning as adapter
from app.integrations.planning_receipts import ReceiptLedgerRow, open_receipts
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
            assert parameters['ids'][:2] == [PRODUCT_BATCH, DEMAND_BATCH]
            assert parameters['dataset_id'] == database.dataset_id
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
                                      'target_month': '2027-01', 'horizon_months': 1, 'as_of_date': '2026-12-31', **changes})


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


@pytest.mark.parametrize(('horizon', 'last'), [(1, '2027-11'), (3, '2028-01'), (6, '2028-04'), (12, '2028-10')])
def test_one_snapshot_covers_the_entire_requested_horizon(sources, horizon, last):
    provider, forecast, sql, _ = sources
    periods = [f'2027-{m:02}' for m in (11, 12)] + [f'2028-{m:02}' for m in range(1, 12)]
    row = vars(forecast.result.forecasts[0])
    forecast.result.forecasts = [SimpleNamespace(**{**row, 'target_month': period}) for period in periods]
    request = command(target_month='2027-11', horizon_months=horizon)
    snapshot = provider.load(request)
    assert request.months[-1] == last
    assert [row.target_month for row in snapshot.forecast_rows] == periods[:horizon]
    assert sql.count('SET TRANSACTION READ ONLY') == 1
    assert snapshot.scheduled_receipts is None
    assert 'RECEIPT_SOURCE_UNAVAILABLE' in snapshot.missing_inputs


def test_missing_later_month_is_rejected_before_loading_other_sources(sources):
    provider, _, sql, _ = sources
    with pytest.raises(ApiError) as error:
        provider.load(command(horizon_months=3))
    assert error.value.status == 409
    assert error.value.details == {'reason': 'FORECAST_PRODUCT_MONTH_COVERAGE'}
    assert sql == ['SET TRANSACTION READ ONLY']


def ledger_row(**changes):
    return ReceiptLedgerRow.model_validate({
        'dataset_id': 'TISSUE-LEGACY', 'batch_id': UUID(int=5), 'po_id': 'PO1', 'material_id': 'M',
        'ordered_qty': '7.25', 'received_qty': '2', 'unit': 'kg', 'expected_date': '2026-12-31',
        'status': 'OPEN', **changes,
    })


@pytest.mark.parametrize(('changes', 'period'), [
    ({}, '2027-01'), ({'expected_date': '2027-02-01'}, '2027-02'),
    ({'expected_date': '2027-04-01'}, None), ({'status': 'CANCELLED'}, None),
    ({'received_qty': '7.25'}, None),
])
def test_receipt_ledger_projects_only_the_remaining_applicable_quantity(changes, period):
    request = command(horizon_months=3)
    rows = open_receipts([ledger_row(**changes)], request, {'M': 'kg'})
    if period is None:
        assert rows == []
    else:
        assert rows[0].period(request) == period and rows[0].open_qty == '5.25'


@pytest.mark.parametrize(('changes', 'reason'), [
    ({'dataset_id': 'OTHER'}, 'RECEIPT_DATASET_MISMATCH'),
    ({'received_qty': '8'}, 'RECEIPT_BALANCE_INVALID'),
    ({'unit': 'EA'}, 'RECEIPT_MATERIAL_OR_UNIT_MISMATCH'),
    ({}, 'RECEIPT_DUPLICATE_PO'),
])
def test_receipt_ledger_checks_scope_balance_unit_and_unique_po(changes, reason):
    rows = [ledger_row(**changes)] if changes else [ledger_row(), ledger_row()]
    with pytest.raises(ApiError) as error:
        open_receipts(rows, command(), {'M': 'kg'})
    assert error.value.details == {'reason': reason}


@pytest.mark.parametrize(('entity', 'reason'), [
    ('scheduled_receipt', None), ('inventory', 'RECEIPT_SOURCE_MISMATCH'), (None, 'APPROVED_SOURCE_MISMATCH'),
])
def test_receipt_reader_uses_same_approved_batch_lookup(sources, monkeypatch, entity, reason):
    provider, _, sql, approved = sources
    template = approved[0]
    batch_id = UUID(int=4)
    approved.append({**template, 'batch_id': batch_id, 'entity': 'material'})
    if entity:
        approved.append({**template, 'batch_id': UUID(int=5), 'entity': entity})
    monkeypatch.setattr(adapter.SqlBatchTx, 'list_materials', lambda *args: (
        [ApprovedMaterial('M', 'Synthetic', 'kg', Decimal('0'), 'SYNTHETIC', batch_id)], 1))

    def read_receipts(connection, dataset_id):
        assert sql == ['SET TRANSACTION READ ONLY'] and dataset_id == 'TISSUE-LEGACY'
        return [ledger_row()]

    provider.receipt_reader = read_receipts
    if reason:
        with pytest.raises(ApiError) as error:
            provider.load(command())
        assert error.value.details == {'reason': reason}
    else:
        snapshot = provider.load(command())
        assert snapshot.scheduled_receipts[0].open_qty == '5.25'
        assert snapshot.approved_inputs.sources[-1].entity == 'scheduled_receipt'
