"""Independent generator outputs are gold. Never import its aggregation implementation."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import runpy
from scripts.benchmark_ingestion import run
from fastapi.testclient import TestClient
from app.main import app
from contracts.interfaces.ingestion import SalesTransformPolicy
import csv
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[2]


def test_over_80000_transactions_exactly_match_generated_monthly_gold(tmp_path):
    module = runpy.run_path(str(ROOT / 'modules/planning_engine/synthetic/generate.py'), run_name='ingestion_gold_generator')
    target = tmp_path / 'synthetic'
    module['main'].__globals__['OUT'] = target
    with redirect_stdout(io.StringIO()):
        module['main']()
    report = run(target, measure_memory=False, write_artifacts=False)['raw_sales']
    assert report['counts']['source_rows'] >= 80_000
    assert report['counts']['error_rows'] == 0
    assert report['counts']['monthly_demand_rows'] == 498
    assert report['monthly_rows_match_rate'] == report['quantity_conservation_rate'] == 1
    # Also exercise ASGI multipart/body limits with all five files, not just the reducer.
    files = [(path.name, path.read_bytes()) for path in sorted((target / 'raw/transactions').glob('판매현황_*.csv'))]
    reply = TestClient(app).post('/ingest/transform-preview', params={'dataset_id': 'CHUNGPAMO-2027'},
        files=[('files', (name, content)) for name, content in files],
        data={'policy': SalesTransformPolicy(dataset_id='CHUNGPAMO-2027', user_confirmed=True).model_dump_json()})
    assert reply.status_code == 200, reply.json()
    body = reply.json()
    assert body['counts'] == report['counts'] and body['status'] == 'TRANSFORMED_PREVIEW'
    with (target / 'upload/05_monthly_demand.csv').open(encoding='utf-8-sig', newline='') as stream:
        expected = list(csv.DictReader(stream))
    assert sorted((r['product_id'], r['period'], Decimal(r['demand_qty']), r['unit']) for r in body['records']) == sorted(
        (r['product_id'], r['period'], Decimal(r['demand_qty']), r['unit']) for r in expected)
    # Continue through the real transformation/batch services, with test-only memory storage.
    # This proves the large-input integration logic, not PostgreSQL persistence or triggers.
    from tests.test_ingestion_history import HistoryMemoryRepository
    from app.batches.repository import ProductInsert
    from app.batches.service import BatchService
    from app.ingest.history import TransformationService
    repository = HistoryMemoryRepository()
    repository.state.products = {row['product_id']: (ProductInsert(row['product_id'], 'Synthetic product', 'EA', None, Decimal(0)), None)
                                 for row in expected}
    service = TransformationService(repository)
    detail, reused = service.create(files, SalesTransformPolicy(dataset_id='CHUNGPAMO-2027', user_confirmed=True),
        body['result_digest'], 'Fresh generated synthetic sales fixture', 'TEST-REVIEWER')
    assert not reused and detail.batch_status == 'READY_FOR_APPROVAL' and detail.preview.total == 498
    assert repository.state.transformation_sources[detail.transformation_id] == files
    assert repository.state.demand == {}
    batch_service = BatchService(repository)
    batch = batch_service.get_batch(detail.batch_id)
    batch_service.approve(batch.batch_id, approved_by='TEST-REVIEWER', expected_result_digest=batch.result_digest)
    assert sorted((pid, period, row.demand_qty, row.unit) for (pid, period), (row, _) in repository.state.demand.items()) == sorted(
        (row['product_id'], row['period'], Decimal(row['demand_qty']), row['unit']) for row in expected)
    assert service.get(detail.transformation_id).batch_status == 'APPROVED'
