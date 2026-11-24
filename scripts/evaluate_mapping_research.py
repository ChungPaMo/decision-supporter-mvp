"""Reproducible manufacturing mapping benchmark. Run from the repository root."""
import argparse
from collections import Counter
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
from time import perf_counter

import numpy as np

from mapping_research_data import build, canonical, load_frozen, sha
from mapping_research_features import CATALOG, PROFILE, RELATION, STRING, Lexicon, abstain, bounded_number, prepare, train_prototypes


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_bytes(canonical(data) + b'\n')
    tmp.replace(path)


def hard_scores(features, method):
    if method == 'tfidf':
        return features[:, :, 2]
    if method == 'bm25':
        return features[:, :, 3]
    if method == 'profile-rule':
        return .65 * features[:, :, 4] + .35 * features[:, :, 6]
    if method == 'sample3-rule':
        return features[:, :, 5]
    if method == 'business-rule':
        return (.55 * features[:, :, 1] + .25 * features[:, :, 4] + .18 * features[:, :, 23]
                - .65 * features[:, :, 24] + .02 * features[:, :, 25])
    if method == 'stats-business-rule':
        return (.52 * features[:, :, 4] + .22 * features[:, :, 6] + .23 * features[:, :, 23]
                - .65 * features[:, :, 24] + .03 * features[:, :, 25])
    raise ValueError('Unknown baseline')


def make_targets(documents, prepared):
    return [np.asarray([[col['expected'] == name for name in record['fields']] for col in doc['columns']], dtype=bool)
            for doc, record in zip(documents, prepared, strict=True)]


def flatten(pack, *, attributes):
    return np.concatenate([record['features'].reshape(-1, record['features'].shape[-1])[:, attributes] for record in pack])


def fit_model(algorithm, config, train, targets, *, threads):
    subset = {'strings': STRING, 'profiles': PROFILE, 'strings_profiles': slice(0, PROFILE.stop), 'profile_business':slice(PROFILE.start,RELATION),
              'business': slice(0, RELATION), 'relations': slice(None)}[config]
    x, y = flatten(train, attributes=subset), np.concatenate([row.ravel() for row in targets]).astype(np.uint8)
    started = perf_counter()
    if algorithm == 'logreg':
        from sklearn.linear_model import LogisticRegression
        model = LogisticRegression(C=1, max_iter=400, class_weight='balanced', random_state=23)
    elif algorithm == 'rf':
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(n_estimators=70, max_depth=12, min_samples_leaf=8, class_weight='balanced',
                                       n_jobs=threads, random_state=23)
    elif algorithm == 'lightgbm':
        from lightgbm import LGBMClassifier
        model = LGBMClassifier(n_estimators=100, num_leaves=15, max_depth=6, learning_rate=.06, n_jobs=threads,
                               verbosity=-1, class_weight='balanced', random_state=23)
    elif algorithm == 'catboost':
        from catboost import CatBoostClassifier
        model = CatBoostClassifier(iterations=100, depth=5, learning_rate=.1, thread_count=threads, random_seed=23,
                                   auto_class_weights='Balanced', allow_writing_files=False, verbose=False)
    else:
        raise ValueError('Unsupported learner')
    if algorithm == 'lightgbm':  # LightGBM's sklearn wrapper warns on matching ndarray schemas.
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='X does not have valid feature names')
            model.fit(x, y)
    else:
        model.fit(x, y)
    elapsed = perf_counter() - started

    def predict(record):
        features = record['features']
        shape = features.shape[:2]
        pairs = features.reshape(-1, features.shape[-1])[:, subset]
        if algorithm == 'lightgbm':
            return model.booster_.predict(pairs, num_threads=threads).reshape(shape)
        return model.predict_proba(pairs)[:, 1].reshape(shape)

    return predict, elapsed, len(y), int(y.sum())


def fit_multiclass(train, documents):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    def texts(doc):
        return [doc['entity'] + ' ' + header for header in doc['headers']]

    clock = perf_counter()
    tokenizer = TfidfVectorizer(analyzer='char', ngram_range=(2,4), min_df=2, max_features=6000)
    features = tokenizer.fit_transform([text for doc in train for text in texts(doc)])
    labels = [col['expected'] or 'HOLD' for doc in documents for col in doc['columns']]
    learner = LogisticRegression(max_iter=250, class_weight='balanced', random_state=24).fit(features,labels)
    classes = {key:i for i,key in enumerate(learner.classes_)}

    def predict(doc):
        scores = learner.predict_proba(tokenizer.transform(texts(doc)))
        return scores[:,[classes[field] for field in doc['fields']]] - scores[:,classes['HOLD'],None]

    return predict, {'fit_seconds':perf_counter()-clock, 'training_columns':len(labels), 'classes':len(classes)}


def group_cv(train, targets, threads):
    """Train-only grouped check. Exclude prototypes fitted on the whole train split."""
    from sklearn.model_selection import GroupKFold

    inputs = []
    for record in train:
        features = record['features'].copy()
        features[:,:,6] = 0  # remove fold-external distribution reference
        inputs.append({**record,'features':features})
    reports = []
    for development, validation in GroupKFold(n_splits=3).split(inputs, groups=[row['family'] for row in inputs]):
        assert not ({inputs[i]['family'] for i in development} & {inputs[i]['family'] for i in validation})
        fit, seconds, _, _ = fit_model('lightgbm','business',[inputs[i] for i in development],
                                       [targets[i] for i in development],threads=threads)
        set_ = [inputs[i] for i in validation]
        truth = [targets[i] for i in validation]
        tops, _, correct = rank_signals([fit(row) for row in set_],set_,truth)
        reports.append({'documents':len(set_), 'unfiltered_eligible_top1_hits':int(correct.sum()),
                        'eligible_candidates':int(np.sum(tops > -1e5)), 'mappable_columns':sum(int(row.sum()) for row in truth),
                        'fit_seconds':seconds})
    return reports


def rank_signals(scores, prepared, targets):
    tops, gaps, correct = [], [], []
    for raw, record, target in zip(scores, prepared, targets, strict=True):
        masked = np.where(record['allowed'], raw, -1e6)
        order = np.argsort(-masked, axis=1, kind='stable')
        ix = np.arange(len(masked))
        first = masked[ix, order[:, 0]]
        second = masked[ix, order[:, 1]] if masked.shape[1] > 1 else np.full(len(masked), -1e6)
        tops.extend(first)
        gaps.extend(first - second)
        correct.extend(target[ix, order[:, 0]] & (first > -1e5))
    return np.asarray(tops), np.asarray(gaps), np.asarray(correct, dtype=bool)


def calibrate(scores, prepared, targets):
    best, gap, correct = rank_signals(scores, prepared, targets)
    eligible = best > -1e5
    levels = np.unique(np.quantile(best[eligible], np.linspace(0, 1, 26))) if eligible.any() else np.array([1.0])
    policies = []
    for threshold in levels:
        for margin in (0, .015, .05, .10):
            accept = eligible & (best >= threshold) & (gap >= margin)
            matched = int(np.count_nonzero(accept & correct))
            total = int(np.count_nonzero(accept))
            precision = matched / total if total else 0
            policies.append((precision >= .95, matched if precision >= .95 else matched - 2 * (total - matched),
                             matched, precision, float(threshold), margin, total))
    _, _, matched, precision, threshold, margin, total = max(policies)
    return {'threshold': threshold, 'margin': margin, 'calibration_n': int(len(best)),
            'calibration_correct': matched, 'calibration_covered': total, 'calibration_precision': precision}


def decisions(raw, record, policy, strategy='independent'):
    selection, order = abstain(raw, record['allowed'], policy['threshold'], policy['margin'], strategy)
    fields = record['fields']
    raw_order = np.argsort(-raw, axis=1, kind='stable')
    return [{'prediction': fields[first] if first is not None else None,
             'top3': ([fields[first]] + [fields[j] for j in order[i] if first != j][:2]) if first is not None else [],
             'ranking': [fields[j] for j in raw_order[i] if raw[i, j] > -1e5][:5]} for i, first in enumerate(selection)]


def baseline_decisions(record, method):
    return [{'prediction': row[0] if row else None, 'top3': row, 'ranking': None} for row in record[method]]


def metrics(documents, rows):
    counts = Counter()
    per_family, cases, wrong_examples = {}, [], []
    label_counts = Counter()
    for doc, predictions in zip(documents, rows, strict=True):
        family = per_family.setdefault(doc['family'], Counter())
        declared = [row['prediction'] for row in predictions if row['prediction'] is not None]
        dup = len(declared) - len(set(declared))
        counts['documents'] += 1
        counts['duplicate_columns'] += dup
        counts['documents_with_duplicate'] += bool(dup)
        good, required = 0, {f for f, item in CATALOG[doc['entity']].items() if item['required']}
        actual, correct_fields = set(), set()
        for col, row in zip(doc['columns'], predictions, strict=True):
            expected, pred = col['expected'], row['prediction']
            key = (doc['entity'], expected)
            if pred == expected:
                good += 1
                label_counts[key, 'tp'] += 1
            else:
                label_counts[key, 'fn'] += 1
                label_counts[(doc['entity'], pred), 'fp'] += 1
            correct = pred is not None and pred == expected
            wrong = pred is not None and pred != expected
            counts['n'] += 1
            counts['eligible'] += expected is not None
            counts['negative'] += expected is None
            counts['correct'] += correct
            counts['wrong'] += wrong
            counts['hold'] += pred is None
            counts['negative_hold'] += expected is None and pred is None
            counts['positive_hold'] += expected is not None and pred is None
            counts['top3'] += expected is not None and expected in row['top3']
            for n in (1, 3, 5):
                counts[f'raw_top{n}'] += expected is not None and row['ranking'] is not None and expected in row['ranking'][:n]
            family['correct'] += correct
            family['wrong'] += wrong
            family['n'] += 1
            if expected is not None:
                actual.add(expected)
            if correct:
                correct_fields.add(expected)
            if wrong and pred in required:
                counts['wrong_required'] += 1
            cases.append((doc['id'], correct, wrong, 1))
            if wrong:
                wrong_examples.append({'document': doc['id'], 'header': col['header'], 'truth': expected,
                                       'prediction': pred, 'scenario': col['scenario']})
        counts['all_columns_correct'] += good == len(predictions)
        counts['required_present'] += len(required & actual)
        counts['required_correct'] += len(required & correct_fields)
        counts['required_missing'] += len(required - actual)
        counts['required_missing_detected'] += len(required - actual - set(declared))
        stock_fields = ('on_hand_qty','allocated_qty','available_qty')
        if doc['entity'] == 'inventory' and all(declared.count(field) == 1 for field in stock_fields):
            mapped = {p['prediction']:col['values'] for p,col in zip(predictions,doc['columns'],strict=True)}
            triples = [tuple(map(bounded_number,sample)) for sample in zip(*(mapped[field] for field in stock_fields),strict=True)]
            comparable = [(a,b,c) for a,b,c in triples if None not in (a,b,c)]
            if len(comparable) >= 8:
                counts['inventory_relations_checked'] += 1
                counts['inventory_relation_mismatch'] += sum(abs(a-b-c) <= .02 for a,b,c in comparable) / len(comparable) < .9
    n, p, neg, tp, bad = (counts[k] for k in ('n', 'eligible', 'negative', 'correct', 'wrong'))
    ratio = lambda a, b: a / b if b else None
    available_labels = {key for key, _ in label_counts}
    macro = np.mean([ratio(2 * label_counts[k, 'tp'], 2 * label_counts[k, 'tp'] + label_counts[k, 'fn'] + label_counts[k, 'fp'])
                     for k in available_labels])
    status = {k: counts[k] for k in ('correct', 'wrong', 'hold', 'negative_hold', 'positive_hold', 'top3')}
    return {**dict(counts), **status, 'top1_recall': ratio(tp, p), 'top3_recall': ratio(counts['top3'], p),
            'precision': ratio(tp, tp + bad), 'wrong_rate': ratio(bad, n), 'hold_recall': ratio(counts['negative_hold'], neg),
            'coverage': ratio(p - counts['positive_hold'], p), 'macro_f1': float(macro),
            'micro_f1': ratio(2 * tp, p + tp + bad), 'document_exact': ratio(counts['all_columns_correct'], counts['documents']),
            'required_recall': ratio(counts['required_correct'], counts['required_present']),
            'required_missing_recall': ratio(counts['required_missing_detected'], counts['required_missing']),
            'inventory_relation_failure_rate':ratio(counts['inventory_relation_mismatch'],counts['inventory_relations_checked']),
            'manual_columns_per_document': ratio(n - tp - counts['negative_hold'], counts['documents']),
            'wrong_by_scenario': dict(Counter(row['scenario'] for row in wrong_examples)),
            'wrong_examples': wrong_examples[:16], 'per_family': {k:dict(v) for k,v in per_family.items()},
            'case_counts': cases, 'raw_ranking_available': all(r['ranking'] is not None for rows_ in rows for r in rows_)}


def calibration_quality(calibration_set, final_set):
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    cal, _, truth = calibration_set
    final, _, expected = final_set
    valid, test = cal > -1e5, final > -1e5
    if valid.sum() < 2 or len(set(truth[valid])) < 2 or not any(test):
        return {'status': 'NOT_RUN', 'reason': 'Insufficient top-candidate classes'}
    models = {'platt': LogisticRegression(C=1e3).fit(cal[valid, None], truth[valid]),
              'isotonic': IsotonicRegression(out_of_bounds='clip').fit(cal[valid], truth[valid])}
    scores = {'platt': models['platt'].predict_proba(final[test, None])[:, 1],
              'isotonic': models['isotonic'].predict(final[test])}
    return {name: {'brier': float(np.mean((value - expected[test])**2)), 'n': int(test.sum()),
                   'ece10': float(sum(np.mean(group) * abs(np.mean(value[group] - expected[test][group]))
                                     for group in (np.minimum(value * 10, 9).astype(int) == i for i in range(10)) if any(group)))}
            for name, value in scores.items()}


def risk_curve(scores, prepared, targets):
    best, _, correct = rank_signals(scores, prepared, targets)
    valid = best > -1e5
    if not any(valid):
        return []
    rows = []
    for threshold in np.unique(np.quantile(best[valid], np.linspace(0, 1, 21))):
        use = valid & (best >= threshold)
        rows.append({'threshold': float(threshold), 'coverage': float(use.mean()), 'risk': float((~correct[use]).mean())})
    return rows


def review_priority(signals):
    best, gap, correct = signals
    candidates = np.flatnonzero(best > -1e5)
    count = len(candidates) // 10
    if not count:
        return None
    chosen = candidates[np.argsort(gap[candidates],kind='stable')[:count]]
    return {'requests':count,'wrong_or_unmappable_reviewed':int((~correct[chosen]).sum()),
            'unselected_population_error_rate':float((~correct[candidates]).mean())}


def bootstrapped_difference(base, candidate):
    def group(rows):
        values = {}
        for doc, good, bad, n in rows:
            values[doc] = np.array([good, bad, n], dtype=float) + values.get(doc, np.zeros(3))
        return values

    first, second = group(base), group(candidate)
    keys = sorted(first)
    differences = np.array([second[k] - first[k] for k in keys])[:, :2]
    n = np.array([first[k][2] for k in keys])
    rng = np.random.default_rng(2424)
    draw = rng.integers(len(keys), size=(1000, len(keys)))
    samples = differences[draw].sum(axis=1) / n[draw].sum(axis=1)[:, None]
    return {'rows': len(keys), 'replicates': len(draw), 'correct_delta_95': np.quantile(samples[:, 0], [.025,.975]).tolist(),
            'wrong_delta_95': np.quantile(samples[:, 1], [.025,.975]).tolist()}


def timing(values):
    return {'ms_p50': float(np.median(values)), 'ms_p95': float(np.percentile(values, 95)), 'ms_mean': float(np.mean(values))}


def timed_predictions(function, prepared):
    outputs, seconds = [], []
    for doc in prepared:
        start = perf_counter()
        outputs.append(function(doc))
        seconds.append((perf_counter() - start) * 1000)
    return outputs, seconds


def peak_rss_mib():
    if os.name != 'nt':
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1048576 if platform.system() == 'Darwin' else 1024)
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
            (field, ctypes.c_size_t) for field in ('peak', 'rss', 'peak_paged', 'paged', 'peak_nonpaged',
                                                  'nonpaged', 'pagefile', 'peak_pagefile')]
    counters = Counters(cb=ctypes.sizeof(Counters))
    current_process = ctypes.windll.kernel32.GetCurrentProcess
    current_process.restype = wintypes.HANDLE
    memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
    memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if memory_info(current_process(), ctypes.byref(counters), counters.cb):
        return counters.peak / 1048576
    return None


def benchmark(directory, output, threads):
    start = perf_counter()
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    train_docs, train_sha = load_frozen(directory, 'train')
    cal_docs, cal_sha = load_frozen(directory, 'calibration')
    lexicon, prototypes = Lexicon(CATALOG), train_prototypes(train_docs)
    train, cal = ([prepare(doc, lexicon, prototypes) for doc in split] for split in (train_docs, cal_docs))
    train_y, cal_y = make_targets(train_docs, train), make_targets(cal_docs, cal)
    model_specs = [('logreg', feature) for feature in ('strings', 'profiles', 'strings_profiles', 'business', 'relations')]
    model_specs += [('rf','business'), ('lightgbm','strings'), ('lightgbm','profile_business'), ('lightgbm','business'),
                    ('lightgbm','relations'), ('catboost','business')]
    models = {'tfidf': lambda record: hard_scores(record['features'], 'tfidf'),
              'bm25': lambda record: hard_scores(record['features'], 'bm25')}
    for name in ('sample3-rule', 'profile-rule', 'business-rule', 'stats-business-rule'):
        models[name] = lambda record, method=name: hard_scores(record['features'], method)
    failures, learning = {}, {}
    try:
        models['logreg-multiclass'], learning['logreg-multiclass'] = fit_multiclass(train, train_docs)
    except (ImportError, RuntimeError, ValueError, OSError) as exc:
        failures['logreg-multiclass'] = {'status':'FAILED', 'exception':type(exc).__name__, 'message':str(exc)[:200]}
    for algorithm, config in model_specs:
        name = f'{algorithm}-{config}'
        try:
            models[name], elapsed, pairs, positive = fit_model(algorithm, config, train, train_y, threads=threads)
            learning[name] = {'fit_seconds': elapsed, 'pairs': pairs, 'positive_pairs': positive}
        except (ImportError, RuntimeError, ValueError, OSError) as exc:
            failures[name] = {'status': 'FAILED', 'exception': type(exc).__name__, 'message': str(exc)[:200]}
    policies, cal_scores = {}, {}
    for name, model in models.items():
        cal_scores[name], _ = timed_predictions(model, cal)
        policies[name] = calibrate(cal_scores[name], cal, cal_y)
    selected = max((name for name in models if name.startswith(('logreg', 'rf-', 'lightgbm', 'catboost'))),
                   key=lambda name: (policies[name]['calibration_precision'] >= .95,
                                     policies[name]['calibration_correct'] if policies[name]['calibration_precision'] >= .95
                                     else policies[name]['calibration_correct'] * policies[name]['calibration_precision']), default='business-rule')
    frozen = {'train_sha256':train_sha, 'calibration_sha256':cal_sha, 'final_sha256': manifest['splits']['final']['sha256'],
              'policies': policies, 'selected': selected, 'selected_constraints': ['independent','greedy','hungarian']}
    write(output / 'frozen-policies.json', {**frozen, 'sha256':sha(frozen)})
    final_docs, final_sha = load_frozen(directory, 'final')
    assert final_sha == frozen['final_sha256']
    prepared = [prepare(doc, lexicon, prototypes) for doc in final_docs]
    final_y = make_targets(final_docs, prepared)
    results = {name: {**metrics(final_docs, [baseline_decisions(row, name) for row in prepared]),
                      **timing([row[name + '_ms'] for row in prepared])} for name in ('exact','rapid')}
    selected_predictions = None
    for name, model in models.items():
        raw, latencies = timed_predictions(model, prepared)
        outcome = [decisions(score, row, policies[name]) for score, row in zip(raw, prepared, strict=True)]
        results[name] = {'status':'MEASURED', **metrics(final_docs, outcome), **timing(latencies), **learning.get(name, {})}
        if name == selected:
            selected_predictions = raw
            signals = rank_signals(cal_scores[name], cal, cal_y)
            results[name]['calibration_quality'] = calibration_quality(signals, rank_signals(raw, prepared, final_y))
            results[name]['calibration_review_queue'] = review_priority(signals)
            results[name]['risk_coverage'] = risk_curve(raw, prepared, final_y)
    for strategy in ('greedy', 'hungarian'):
        started = perf_counter()
        outcome = [decisions(score, row, policies[selected], strategy) for score, row in zip(selected_predictions, prepared, strict=True)]
        results[f'{selected}-{strategy}'] = {**metrics(final_docs, outcome), 'assignment_seconds':perf_counter() - started}
    score_data = {'name':selected, 'calibration_sha256':cal_sha, 'final_sha256':final_sha,
                  'calibration':[matrix.tolist() for matrix in cal_scores[selected]],
                  'final':[matrix.tolist() for matrix in selected_predictions]}
    write(output / 'cpu-selected-scores.json', {**score_data, 'sha256':sha(score_data)})
    for name in results:
        results[name]['paired_vs_rapid'] = bootstrapped_difference(results['rapid']['case_counts'], results[name].pop('case_counts') if name != 'rapid' else results[name]['case_counts'])
    results['rapid'].pop('case_counts')
    packages = {}
    for package in ('numpy','scipy','rapidfuzz','scikit-learn','lightgbm','catboost'):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    try:
        cv = group_cv(train, train_y, threads)
    except (ImportError,RuntimeError,ValueError,OSError) as exc:
        cv = {'status':'FAILED', 'exception':type(exc).__name__, 'message':str(exc)[:200]}
    outcome = {'manifest':manifest, 'selected':selected, 'models':results, 'failures':failures, 'threads':threads, 'train_group_cv':cv,
               'common_features_per_document': timing([doc['elapsed_ms'] for doc in prepared]),
               'environment': {'os':platform.platform(),'python':platform.python_version(),'cpu':os.cpu_count(),'packages':packages},
               'elapsed_seconds':perf_counter() - start, 'peak_process_mib':peak_rss_mib()}
    write(output / 'cpu-results.json', outcome)
    print(json.dumps({name:{k:row[k] for k in ('correct','top3','wrong','hold','precision','coverage')} for name,row in results.items()}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('generate', 'cpu'))
    parser.add_argument('--data', type=Path, default=Path('.artifacts/mapping-research/data'))
    parser.add_argument('--output', type=Path, default=Path('.artifacts/mapping-research/results'))
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--write-csv', action='store_true', help='Materialize the generated CSV documents in the data folder')
    args = parser.parse_args()
    if args.phase == 'generate':
        print(json.dumps(build(args.data,write_csv=args.write_csv), ensure_ascii=False))
    else:
        benchmark(args.data, args.output, args.threads)


if __name__ == '__main__':
    main()
