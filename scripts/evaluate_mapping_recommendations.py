"""Small offline column-candidate comparison. No DB, network, models or threshold search."""
import argparse
from contextlib import nullcontext
import csv
from difflib import SequenceMatcher
import hashlib
import io
import json
from pathlib import Path
import platform
import statistics
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]

from app.ingest.mapping import map_sheet
from app.ingest.profiling import parse_analysis_file
from app.ingest import recommendation

CASES = ROOT / 'contracts/examples/mapping_recommendation_cases_v1.json'


def sequence_similarity(labels, aliases):
    return max((SequenceMatcher(None, label, alias, autojunk=False).ratio()
                for label in labels for alias in aliases), default=0.0)


def parsed_case(case):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow([case['header'], 'unrelated_note'])
    writer.writerow([case['value'], 'Synthetic only'])
    return parse_analysis_file('synthetic.csv', stream.getvalue().encode())


def candidates(parsed, entity, method):
    if method == 'exact_alias':
        mapped = map_sheet(parsed.sheets[0], entity=entity)
        return [field for field, item in mapped.fields.items() if item.col == 1]
    context = patch.object(recommendation, 'lexical_similarity', sequence_similarity) if method == 'sequence' else nullcontext()
    with context:
        result = recommendation.recommend(parsed, entity, 'TISSUE-LEGACY')
    return [candidate.target_field for candidate in result.sheets[0].suggestions[0].suggestions]


def run(repeats=3):
    """Three repetitions measure noise only; the cutoff/scorer are never optimized on gold."""
    if not 1 <= repeats <= 5:
        raise ValueError('Use one to five small timing repetitions, not a parameter sweep')
    content = CASES.read_bytes()
    dataset = json.loads(content)
    cases = dataset['cases']
    parsed = [parsed_case(case) for case in cases]
    methods = ('exact_alias', 'sequence', 'rapidfuzz')
    results = {}
    for method in methods:
        rows = []
        for case, source in zip(cases, parsed):
            options = candidates(source, case['entity'], method)
            first = options[0] if options else None
            rows.append({'id': case['id'], 'kind': case['kind'], 'header': case['header'],
                'expected': case['expected'], 'top1': first, 'top3': options,
                'correct_mapping': case['expected'] is not None and first == case['expected'],
                'wrong_recommendation': first is not None and first != case['expected'],
                'candidate_hold': first is None,
                'top3_hit': case['expected'] is not None and case['expected'] in options})
        elapsed = []
        for _ in range(repeats):
            started = time.perf_counter()
            for case, source in zip(cases, parsed):
                candidates(source, case['entity'], method)
            elapsed.append((time.perf_counter() - started) * 1000)
        positives = sum(case['expected'] is not None for case in cases)
        results[method] = {'cases': len(cases), 'mappable_cases': positives,
            'correct_mapping_count': sum(row['correct_mapping'] for row in rows),
            'correct_mapping_rate': sum(row['correct_mapping'] for row in rows) / positives,
            'wrong_recommendation_count': sum(row['wrong_recommendation'] for row in rows),
            'wrong_recommendation_rate': sum(row['wrong_recommendation'] for row in rows) / len(cases),
            'candidate_hold_count': sum(row['candidate_hold'] for row in rows),
            'candidate_hold_rate': sum(row['candidate_hold'] for row in rows) / len(cases),
            'top3_hits': sum(row['top3_hit'] for row in rows),
            'top3_recall': sum(row['top3_hit'] for row in rows) / positives,
            'median_ms_per_column': statistics.median(elapsed) / len(cases), 'cases_detail': rows}
    import rapidfuzz
    return {'dataset_version': dataset['version'], 'dataset_sha256': hashlib.sha256(content).hexdigest(),
        'scope': 'SYNTHETIC_ONLY; column candidates, not automatic mappings or approval accuracy',
        'timing_scope': 'warm imports; parsed inputs; recommendation includes profile; no file I/O/DB/model; median of three small runs by default',
        'shared_guards': 'SequenceMatcher and RapidFuzz use the same production semantic/profile guards.',
        'python': platform.python_version(), 'rapidfuzz': rapidfuzz.__version__,
        'cutoff': recommendation.LEXICAL_CUTOFF, 'timing_repeats': repeats, 'methods': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.artifacts/mapping_recommendations_v1.json')
    parser.add_argument('--summary-output', type=Path, help='Optional compact, synthetic-only report for review')
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = {**{key: value for key, value in report.items() if key != 'methods'},
        'methods': {name: {key: value for key, value in row.items() if key != 'cases_detail'}
                    for name, row in report['methods'].items()},
        'wrong_examples': [{key: row[key] for key in ('id', 'header', 'expected', 'top1', 'top3')}
                           for row in report['methods']['rapidfuzz']['cases_detail'] if row['wrong_recommendation']],
        'missed_examples': [{key: row[key] for key in ('id', 'header', 'expected')}
                            for row in report['methods']['rapidfuzz']['cases_detail'] if row['expected'] and not row['top3_hit']]}
    if args.summary_output:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in summary.items() if key not in ('wrong_examples', 'missed_examples')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
