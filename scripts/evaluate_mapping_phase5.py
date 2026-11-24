"""Phase 5 offline research runner. No provider credentials, clients or network path."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from evaluate_mapping_research import bootstrapped_difference, metrics, timing, write
from mapping_phase5_audit import compact, historical, settlement, transition
from mapping_phase5_data import OUT, read_panel, write_frozen
from mapping_phase5_evidence import knowledge, version_manifest
from mapping_phase5_local import (Examples, decisions, example_effect, fit_verifier, phase5_payload, prepare_local, score)
from mapping_research_data import load_frozen, sha
from mapping_research_features import CATALOG, Lexicon
from mapping_research_phase3 import CONFIRM_DIR, DATA
from mapping_research_remote import SHARED_CACHE


BASE = 'exact_rapid'
CONFIGS = {
    'legacy_profile': ('model', 'legacy', 'local'),
    'improved_profile': ('model', 'format', 'local'),
    'hierarchical_rules': ('rules', 'hard', 'local'),
    'local_verifier': ('model', 'hard', 'local'),
    'structural_relations': ('relations', 'hard', 'local'),
    'contrastive_retrieval': ('contrast', 'hard', 'local'),
    'bm25_retrieval': ('bm25', 'hard', 'local'),
    'independent': ('relations', 'hard', 'independent'),
    'greedy': ('relations', 'hard', 'greedy'),
    'hungarian': ('relations', 'hard', 'hungarian'),
}
THRESHOLDS = (.25, .35, .45, .55, .65, .72, .78, .83, .88, .92, .95, .97, .98, .99)
MARGINS = (.00, .05, .12, .20)


def runtime_digest():
    base = Path(__file__).parent
    names = ('evaluate_mapping_phase5.py', 'mapping_phase5_data.py', 'mapping_phase5_evidence.py',
             'mapping_phase5_local.py', 'mapping_phase5_audit.py')
    return sha({name: sha256((base / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for name in names})


def train_model(output, data, lexicon):
    from threadpoolctl import threadpool_limits

    original, original_sha = load_frozen(data, 'train')
    extra, extra_sha = read_panel(output, 'train_extra')
    train = original + extra
    start = perf_counter()
    prepared = [prepare_local(doc, lexicon) for doc in train]
    with threadpool_limits(limits=2):
        model = fit_verifier(train, prepared)
    return model, Examples(train), {'training_documents': len(train), 'base_train_sha256': original_sha,
        'extra_train_sha256': extra_sha, 'training_ms': (perf_counter() - start) * 1000}


def available_scores(docs, lexicon, model, examples, *, retrieve=('contrast', 'bm25')):
    prepared, elapsed = [], []
    for doc in docs:
        start = perf_counter()
        prepared.append(prepare_local(doc, lexicon))
        elapsed.append((perf_counter() - start) * 1000)
    local_scores, prediction_ms = [], []
    for item in prepared:
        start = perf_counter()
        local_scores.append(score(model, [item])[0])
        prediction_ms.append((perf_counter() - start) * 1000)
    scores = {'model': local_scores, 'rules': [], 'relations': [], 'contrast': [], 'bm25': []}
    for item, values in zip(prepared, local_scores, strict=True):
        feat = item.features
        rule = .48 * feat[:, :, 2] + .24 * feat[:, :, 3] + .18 * feat[:, :, 5] + .12 * item.role
        scores['rules'].append(np.clip(np.maximum(rule, feat[:, :, 1] * .99), 0, 1))
        scores['relations'].append(np.clip(values + .14 * item.relations, 0, 1))
        for method, count in (('contrast', 4), ('bm25', 2)):
            if method in retrieve:
                evidence = example_effect(item, examples, method, count)[0]
                scores[method].append(np.clip(values + .08 * evidence, 0, 1))
    return prepared, scores, {'profile_and_features': timing(elapsed), 'local_verifier': timing(prediction_ms)}


def baseline(item):
    previous = item.baseline.sheets[0]
    locked = {pos: field for field, pos in previous.existing_mapping.items()}
    rows = []
    for column in previous.suggestions:
        ranked = [cand.target_field for cand in column.suggestions]
        exact = locked.get(column.col)
        best = exact if exact in ranked else (ranked[0] if ranked else None)
        rows.append({'prediction': best, 'top3': ranked, 'ranking': None})
    return rows


def evaluate(prepared, scores, name, threshold, margin):
    source, evidence, assignment = CONFIGS[name]
    return [decisions(item, matrix, threshold, margin, assignment, evidence=evidence)
            for item, matrix in zip(prepared, scores[source], strict=True)]


def risk_count(docs, predictions):
    correct = wrong = negative_pred = negatives = 0
    for doc, rows in zip(docs, predictions, strict=True):
        for col, row in zip(doc['columns'], rows, strict=True):
            actual, result = col['expected'], row['prediction']
            negatives += actual is None
            if result is not None:
                correct += actual == result
                wrong += actual != result
                negative_pred += actual is None
    return {'correct': correct, 'wrong': wrong, 'precision': correct / max(1, correct + wrong),
            'hold_recall': 1 - (negative_pred / max(1, negatives))}


def calibration(docs, prepared, scores):
    records = []
    n = sum(len(doc['columns']) for doc in docs)
    for name in CONFIGS:
        for threshold in THRESHOLDS:
            for margin in MARGINS:
                measured = risk_count(docs, evaluate(prepared, scores, name, threshold, margin))
                records.append({'strategy': name, 'threshold': threshold, 'margin': margin,
                                'wrong_rate': measured['wrong'] / n, **measured})
    # Pick maximal coverage satisfying all risk constraints. If unavailable, keep the failure explicit.
    viable = [item for item in records if item['correct'] and item['precision'] >= .98 and item['wrong_rate'] <= .01
              and item['hold_recall'] >= .98 and item['strategy'] not in ('legacy_profile', 'independent')]
    nonzero = [item for item in records if item['correct'] and item['strategy'] not in ('legacy_profile', 'independent')]
    if not nonzero:
        raise ValueError('No recommendation-producing Phase 5 policy')
    if viable:
        selected = max(viable, key=lambda item: (item['correct'], -item['wrong'], item['precision']))
    else:
        selected = max(nonzero, key=lambda item: (item['correct'] - 5 * item['wrong'], item['precision']))
    curves = {}
    for precision in (.95, .98, .99):
        subset = [row for row in records if row['correct'] and row['precision'] >= precision]
        curves[str(precision)] = max(subset, key=lambda row: (row['correct'], -row['wrong'])) if subset else None
    return selected, bool(viable), curves


def example_grid(docs, prepared, model_scores, pool, policy):
    results = {}
    for method in ('fixed', 'domain', 'rapidfuzz', 'tfidf', 'bm25', 'contrast'):
        for count in (0, 2, 4, 8, 12):
            features, sizes = zip(*(example_effect(item, pool, method, count) for item in prepared), strict=True)
            prediction = [decisions(item, np.clip(matrix + .08 * signal, 0, 1), policy['threshold'],
                         policy['margin'], 'local') for item, matrix, signal in zip(prepared, model_scores, features, strict=True)]
            results[f'{method}/{count}'] = {**risk_count(docs, prediction), 'example_utf8_bytes': sum(sizes)}
    return results


def compare(docs, prepared, scores, selected, *, all_models):
    base = [baseline(item) for item in prepared]
    baseline_full = metrics(docs, base)
    names = list(CONFIGS) if all_models else [selected['strategy']]
    predictions = {name: evaluate(prepared, scores, name, selected['threshold'], selected['margin']) for name in names}
    reference = predictions[selected['strategy']]
    selected_stats = metrics(docs, reference)
    families = {doc['id']: doc['family'] for doc in docs}
    first, last = [[(families[doc], correct, wrong, n) for doc, correct, wrong, n in result['case_counts']]
                   for result in (baseline_full, selected_stats)]
    return {BASE: compact(baseline_full), 'strategies': {name: compact(metrics(docs, values))
             for name, values in predictions.items()}, 'selected': selected['strategy'],
            'selected_minus_baseline': transition(base, reference, docs), 'paired_family_bootstrap': bootstrapped_difference(first, last)}


def local_research(args):
    lexicon = Lexicon(CATALOG)
    model, pool, training = train_model(args.output, args.data, lexicon)
    cal, cal_sha = read_panel(args.output, 'calibration')
    policy_path = args.output / 'frozen-policy.json'
    provenance = {**version_manifest(), 'code_sha256': runtime_digest(), 'calibration_sha256': cal_sha,
                  'training': {key: value for key, value in training.items() if key != 'training_ms'}}
    if args.action == 'holdout':
        frozen = json.loads(policy_path.read_bytes())
        if frozen['provenance'] != provenance or frozen['sha256'] != sha({k: v for k, v in frozen.items() if k != 'sha256'}):
            raise ValueError('A held-out run requires the already frozen policy and unchanged inputs and source files')
        selection = frozen['selection']
        docs, digest = read_panel(args.output, 'holdout')
        prepared, scores, times = available_scores(docs, lexicon, model, pool, retrieve=(CONFIGS[selection['strategy']][0],))
        report = {'data_sha256': digest, 'policy_sha256': frozen['sha256'], 'timings': times,
                  **compare(docs, prepared, scores, selection, all_models=False)}
        write(args.output / 'holdout-results.json', report)
        return
    prepared, scores, times = available_scores(cal, lexicon, model, pool)
    selected, viable, curves = calibration(cal, prepared, scores)
    frozen = {'provenance': provenance, 'selection': selected, 'calibration_risk_targets_met': viable, 'risk_curves': curves}
    frozen['sha256'] = sha(frozen)
    write_frozen(policy_path, frozen)
    write_frozen(args.output / 'knowledge.json', knowledge())
    write_frozen(args.output / 'prompt-example.json', phase5_payload(prepared[0], pool))
    dev, dev_sha = read_panel(args.output, 'development')
    dev_prepared, dev_scores, dev_times = available_scores(dev, lexicon, model, pool)
    report = {'training': training, 'calibration': compare(cal, prepared, scores, selected, all_models=True),
              'development': {'data_sha256': dev_sha, **compare(dev, dev_prepared, dev_scores, selected, all_models=True)},
              'example_selection_calibration': example_grid(cal, prepared, scores['model'], pool, selected),
              'timings': {'calibration': times, 'development': dev_times}, 'frozen_policy': frozen}
    write(args.output / 'local-results.json', report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('billing', 'historical', 'calibrate', 'holdout'))
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--data', type=Path, default=DATA)
    parser.add_argument('--confirmatory', type=Path, default=CONFIRM_DIR)
    parser.add_argument('--cache', type=Path, default=SHARED_CACHE)
    args = parser.parse_args()
    if args.action == 'billing':
        write(args.output / 'billing-review.json', settlement(args.cache))
    elif args.action == 'historical':
        before = settlement(args.cache)
        report = historical(args.data, args.confirmatory, args.cache, Lexicon(CATALOG))
        if before['ledger_sha256'] != settlement(args.cache)['ledger_sha256']:
            raise ValueError('Original research ledger changed')
        write(args.output / 'historical-results.json', report)
    else:
        local_research(args)


if __name__ == '__main__':
    main()
