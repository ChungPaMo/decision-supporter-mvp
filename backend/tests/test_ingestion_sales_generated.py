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
