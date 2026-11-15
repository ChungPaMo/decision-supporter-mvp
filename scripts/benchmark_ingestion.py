"""Reproducible offline ingestion benchmark. Raw/generated output stays ignored."""
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
import argparse
import csv
import io
import json
import runpy
import sys
import tempfile
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]


def mapping_cases():
    from app.ingest.mapping import map_sheet
    from app.ingest.pipeline import run_preview
    from app.ingest.profiling import ScopedMaster, parse_analysis_file
    from app.ingest.recommendation import recommend
    from app.ingest.validation import KnownMaterial, KnownProduct, MasterData
    cases = json.loads((ROOT / 'contracts/examples/ingestion_benchmark_cases.json').read_text(encoding='utf-8'))['cases']
    master = ScopedMaster('CHUNGPAMO-2027', MasterData(
        {'CP-N3-3030': KnownProduct('CP-N3-3030', 'Synthetic product', 'EA')},
        {'MR-N3': KnownMaterial('MR-N3', 'Synthetic material', 'kg')}))
    results = []
    for case in cases:
        data = case['csv'].encode()
        parsed = parse_analysis_file('synthetic.csv', data)
        overrides = case.get('overrides')
        baseline = map_sheet(parsed.sheets[0], overrides, case['entity'])
        proposed = recommend(parsed, case['entity'], master.dataset_id, master, overrides).sheets[0]
        validation = run_preview('synthetic.csv', data, case['entity'], column_overrides=overrides)
        assert validation.status == case['expected_status'], (case['id'], validation.status)
        gold = case['mapping']
        candidates = {(item.col, candidate.target_field) for item in proposed.suggestions for candidate in item.suggestions}
        non_null = {field: col for field, col in gold.items() if col is not None}
        selected = {name: item.col for name, item in baseline.fields.items()}
        wrong = sum(1 for name, col in selected.items() if name in gold and gold[name] != col)
        auto = {name: item.col for name, item in baseline.fields.items() if not item.review_required}
        results.append({'id': case['id'], 'gold_status': case['expected_status'], 'baseline_mapping_status': baseline.status,
            'assisted_mapping_status': proposed.status, 'validation_status': validation.status,
            'required_gold_fields': len(non_null), 'baseline_exact_fields': sum(selected.get(f) == c for f, c in non_null.items()),
            'assisted_selected_exact_fields': sum(proposed.existing_mapping.get(f) == c for f, c in non_null.items()),
            'baseline_topk_hits': sum(selected.get(f) == c for f, c in non_null.items()),
            'assisted_top3_hits': sum((c, f) in candidates for f, c in non_null.items()),
            'baseline_wrong_auto_fields': sum(1 for f, c in auto.items() if f in gold and gold[f] != c),
            'assisted_wrong_auto_fields': wrong if proposed.status == 'MAPPED' else 0,
            'baseline_user_fields': sum(c is None or auto.get(f) != c for f, c in gold.items()),
            'assisted_user_fields': sum(c is None or auto.get(f) != c or 'PROFILE_CONTRADICTION:' + f in proposed.holds
                                        for f, c in gold.items()),
            'baseline_pass': validation.status == 'READY_FOR_APPROVAL',
            'assisted_pass': validation.status == 'READY_FOR_APPROVAL' and proposed.status == 'MAPPED'})
    def metrics(prefix):
        n = len(results)
        good = [r for r in results if r['gold_status'] == 'READY_FOR_APPROVAL']
        bad = [r for r in results if r['gold_status'] != 'READY_FOR_APPROVAL']
        gold_fields = sum(r['required_gold_fields'] for r in results)
        exact_key = 'baseline_exact_fields' if prefix == 'baseline' else 'assisted_selected_exact_fields'
        return {'cases': n, 'required_exact_mapping_rate': sum(r[exact_key] for r in results) / gold_fields,
            'topk_candidate_recall': sum(r['baseline_topk_hits' if prefix == 'baseline' else 'assisted_top3_hits'] for r in results) / gold_fields,
            'wrong_auto_mapping_fields': sum(r[prefix + '_wrong_auto_fields'] for r in results),
            'hold_rate': sum(r[prefix + '_mapping_status'] == 'HOLD' for r in results) / n,
            'user_selection_fields': sum(r[prefix + '_user_fields'] for r in results),
            'bad_material_pass_rate': sum(r[prefix + '_pass'] for r in bad) / len(bad),
            'normal_material_rejection_rate': sum(not r[prefix + '_pass'] for r in good) / len(good)}
    return {'gold_version': 'manual-ingestion-gold-1.0', 'baseline': metrics('baseline'), 'assisted': metrics('assisted'), 'cases': results}


def run(data_root, *, measure_memory=True, write_artifacts=True):
    from app.ingest.transformation import transform
    from contracts.interfaces.ingestion import SalesTransformPolicy
    files = [(path.name, path.read_bytes()) for path in sorted((data_root / 'raw/transactions').glob('판매현황_*.csv'))]
    if not files:
        raise RuntimeError('Synthetic sales files required')
    sources_before = {path: path.read_bytes() for path in [data_root / 'upload/05_monthly_demand.csv']}
    expected = list(csv.DictReader(io.StringIO(sources_before[data_root / 'upload/05_monthly_demand.csv'].decode('utf-8-sig'))))
    policy = SalesTransformPolicy(dataset_id='CHUNGPAMO-2027', user_confirmed=True)
    if measure_memory:
        tracemalloc.start()
    started = time.perf_counter()
    result = transform(files, policy)
    elapsed = time.perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1] if measure_memory else None
    if measure_memory:
        tracemalloc.stop()
    actual_rows = [(r.product_id, r.period, Decimal(r.demand_qty), r.unit) for r in result.records]
    expected_rows = [(r['product_id'], r['period'], Decimal(r['demand_qty']), r['unit']) for r in expected]
    assert len(set((p, m) for p, m, _, _ in actual_rows)) == len(actual_rows)
    assert len(result.records) == result.total == len(expected_rows)
    assert sorted(actual_rows) == sorted(expected_rows), 'Product/month/quantity/unit mismatch'
    assert result.status == 'TRANSFORMED_PREVIEW' and result.issues_total == 0
    assert result.counts['source_rows'] >= 80_000
    assert result.quantity_reconciliation['normal_quantity_conserved']
    for path, content in sources_before.items():
        assert path.read_bytes() == content
    artifact = ROOT / '.artifacts'
    artifact.mkdir(exist_ok=True)
    if write_artifacts:
        with (artifact / 'ingestion_monthly_demand.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['product_id', 'period', 'demand_qty', 'unit'])
            writer.writerows((r.product_id, r.period, r.demand_qty, r.unit) for r in result.records)
    from scripts.verify_synthetic_contracts import verify
    validation = verify(data_root)
    assert validation['normal_contract_passes'] == 9
    error_gold = {'bom_unknown_material.csv': 'HAS_ERRORS', 'demand_missing_qty.csv': 'HAS_ERRORS',
                  'inventory_negative_qty.csv': 'HAS_ERRORS', 'products_unknown_unit.csv': 'HAS_ERRORS',
                  'demand_bad_period_format.csv': 'READY_FOR_APPROVAL', 'demand_duplicate_period.csv': 'READY_FOR_APPROVAL'}
    for case in validation['errors']:
        assert case['status'] == error_gold[case['file']], case['file']
    dirty_file = data_root / 'errors/sales_orders_dirty_sample.csv'
    dirty = transform([(dirty_file.name, dirty_file.read_bytes())], policy)
    assert dirty.status == 'HAS_ERRORS' and dirty.issues_total > 0
    report = {'mapping': mapping_cases(),
        'existing_contract_fixtures': {'normal_uploads_passed': 9, 'error_directory_cases': [
            {'file': row['file'], 'expected_status': error_gold[row['file']], 'actual_status': row['status']} for row in validation['errors']],
            'dirty_sales_status': dirty.status, 'dirty_sales_counts': dirty.counts,
            'scope': 'OFFLINE TEST DOUBLE; not PostgreSQL approval evidence'},
        'raw_sales': {'source_files': len(files), 'source_bytes': sum(len(data) for _, data in files),
        'counts': result.counts, 'monthly_rows_match_rate': 1.0, 'quantity_conservation_rate': 1.0,
        'reconciliation': result.quantity_reconciliation, 'policy_id': policy.policy_id, 'policy_version': policy.version,
        'source_sha256': [source.sha256 for source in result.sources], 'result_digest': result.result_digest,
        'elapsed_seconds': elapsed, 'peak_python_allocated_bytes': peak, 'measurement_includes_input_read': False,
        'memory_method': 'tracemalloc during transform; not process RSS; timing includes tracer overhead' if measure_memory else 'not measured'}}
    if write_artifacts:
        (artifact / 'ingestion_benchmark.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--existing-synthetic', action='store_true', help='Read existing ignored synthetic data without changing it')
    args = parser.parse_args()
    if args.existing_synthetic:
        report = run(ROOT / 'modules/planning_engine/synthetic/data')
    else:
        (ROOT / '.artifacts').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='ingestion-benchmark-', dir=ROOT / '.artifacts') as temporary:
            module = runpy.run_path(str(ROOT / 'modules/planning_engine/synthetic/generate.py'), run_name='ingestion_benchmark_generator')
            module['main'].__globals__['OUT'] = Path(temporary) / 'generated'
            with redirect_stdout(io.StringIO()):
                module['main']()
            report = run(Path(temporary) / 'generated')
    print(json.dumps({key: value for key, value in report.items() if key != 'mapping'}, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in report['mapping'].items() if key != 'cases'}, indent=2))


if __name__ == '__main__':
    main()
