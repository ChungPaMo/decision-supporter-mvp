"""Single-product synthetic scenario through service approval and real forecast.

Uses a fake repository only: this does not prove PostgreSQL constraints/persistence.
"""
from pathlib import Path
from app.batches.service import BatchService
from engine.forecast import run
from tests.fakes import InMemoryBatchRepository


def test_tissue_files_approve_in_reference_order_and_feed_real_engine():
    root = Path(__file__).resolve().parents[2]
    service = BatchService(InMemoryBatchRepository())
    for entity, suffix in [('product', 'products'), ('material', 'materials'), ('bom', 'bom'), ('inventory', 'inventory'), ('monthly_demand', 'demand')]:
        path = root / 'contracts/examples' / f'tissue_{suffix}.csv'
        batch = service.create_batch(path.name, path.read_bytes(), entity=entity, source_type='SYNTHETIC', source_note='synthetic tissue scenario')
        assert batch.status == 'READY_FOR_APPROVAL', batch.validation_result
        approved = service.approve(batch.batch_id, approved_by='REVIEWER-01', expected_result_digest=batch.result_digest)
        assert approved.status == 'APPROVED'
    rows, total = service.list_approved_demand('TP-10R', None, None, 100, 0)
    assert total == 24
    result = run({'contract_version': 'forecast-input-0.1-draft', 'request_id': 'TISSUE-SYNTHETIC',
                  'trained_until': '2026-12-31', 'horizon_months': 1,
                  'rows': [{'product_id': r.product_id, 'period': r.period, 'demand_qty': str(r.demand_qty),
                            'unit': r.unit, 'source_type': 'SYNTHETIC', 'batch_id': str(r.batch_id)} for r in rows]})
    assert result['status'] in ('OK', 'PARTIAL')
    assert len(result['forecasts']) == 1
    assert result['forecasts'][0]['product_id'] == 'TP-10R'
    assert result['forecasts'][0]['target_month'] == '2027-01'
