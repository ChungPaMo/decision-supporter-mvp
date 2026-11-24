"""Independent calibration, selective estimates and conformal diagnostics."""
from collections import Counter, defaultdict
from math import ceil

import numpy as np


THRESHOLDS = (.32, .42, .50, .58, .64, .70, .76, .81, .86, .90, .93, .95, .97, .985, .995, 1.01)
MARGINS = (-.10, .0, .06, .12)


def make_predictions(item, threshold, margin, *, kind=None, overrides=None):
    rows = []
    for i, field in enumerate(item.target):
        name = item.fields[field] if field is not None else None
        bound = overrides.get(name if kind == 'field' else kind, threshold) if overrides else threshold
        pred = name if name and item.confidence[i] >= bound and item.margin[i] >= margin else None
        order = [item.fields[j] for j in item.rank[i].tolist() if j >= 0]
        ready_order = [item.fields[j] for j in item.ready_rank[i]]
        rows.append({'prediction': pred, 'rank': order,
                     'top3': [pred, *[field for field in ready_order if field != pred][:2]] if pred else [], 'ranking': order[:3]})
    return rows


def risk_counts(docs, rows):
    counts = Counter(n=0, eligible=0, correct=0, wrong=0, negatives=0, negative_wrong=0)
    for doc, predictions in zip(docs, rows, strict=True):
        for col, row in zip(doc['columns'], predictions, strict=True):
            label, field = col['expected'], row['prediction']
            counts['n'] += 1
            counts['eligible'] += label is not None
            counts['correct'] += field is not None and field == label
            counts['wrong'] += field is not None and field != label
            counts['negatives'] += label is None
            counts['negative_wrong'] += field is not None and label is None
    counts = dict(counts)
    return {**counts, 'precision': counts['correct'] / max(1, counts['correct'] + counts['wrong']),
            'exact_recall': counts['correct'] / max(1, counts['eligible']),
            'wrong_rate': counts['wrong'] / max(1, counts['n']),
            'hold_recall': 1 - counts['negative_wrong'] / max(1, counts['negatives'])}


def per_column(docs, proposals):
    for doc, proposal in zip(docs, proposals, strict=True):
        for col, target, score, margin in zip(doc['columns'], proposal.target, proposal.confidence, proposal.margin, strict=True):
            guess = proposal.fields[target] if target is not None else None
            yield doc['entity'], guess, score, margin, col['expected']


def select_groups(docs, proposals, kind, threshold, margin):
    values = defaultdict(list)
    for entity, field, score, gap, gold in per_column(docs, proposals):
        if field and gap >= margin:
            values[entity if kind == 'domain' else field].append((score, field == gold))
    result = {}
    for key, samples in values.items():
        if len(samples) < 25:
            continue
        feasible = []
        for cutoff in THRESHOLDS:
            results = [ok for score, ok in samples if score >= cutoff]
            if results and sum(results) / len(results) >= .98:
                feasible.append((sum(results), -cutoff, cutoff))
        if feasible:
            result[key] = max(feasible)[2]
    return result


def select(docs, methods, exclude=()):
    search, best = [], {}
    for name, proposals in methods.items():
        styles = [(cut, gap) for cut in THRESHOLDS for gap in MARGINS]
        for cutoff, margin in styles:
            rows = [make_predictions(p, cutoff, margin) for p in proposals]
            item = {'strategy': name, 'threshold': cutoff, 'margin': margin, **risk_counts(docs, rows)}
            search.append(item)
            existing = best.get(name)
            def ordering(row):
                admissible = meets_risk(row)
                return admissible, row['correct'] if admissible else row['correct'] - 5 * row['wrong'], -row['wrong']
            if existing is None or ordering(item) > ordering(existing):
                best[name] = item
    candidates = [row for name, row in best.items() if name not in exclude and row['correct']]
    if not candidates:
        raise ValueError('No nontrivial selective policy')
    winner = max(candidates, key=ordering)
    curves = {}
    for limit in (.95, .98, .99):
        feasible = [item for item in search if item['correct'] and item['precision'] >= limit]
        curves[str(limit)] = max(feasible, key=lambda item: (item['correct'], -item['wrong'])) if feasible else None
    return winner, best, curves


def meets_risk(item):
    return item['correct'] > 0 and item['precision'] >= .98 and item['wrong_rate'] <= .01 and item['hold_recall'] >= .98


def group_threshold(docs, proposals, margin, alpha):
    """CRC for bounded monotone group error presence with frozen row assignments."""
    observed = []
    for cutoff in THRESHOLDS:
        losses = {doc['family']: False for doc in docs}
        for doc, item in zip(docs, proposals, strict=True):
            rows = make_predictions(item, cutoff, margin)
            failures = any(row['prediction'] and row['prediction'] != c['expected'] for c, row in zip(doc['columns'], rows, strict=True))
            losses[doc['family']] |= failures
        n = len(losses)
        errors = sum(losses.values())
        observed.append({'threshold': cutoff, 'groups': n, 'error_groups': errors, 'adjusted': (errors + 1) / (n + 1)})
    valid = [row for row in observed if row['adjusted'] <= alpha]
    return {'level': alpha, 'selected': valid[0] if valid else None, 'curve': observed}


def confidence_diagnostic(selection, selection_predictions, risk, risk_predictions):
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression

    def sample(docs, proposals):
        samples = [(p, field == gold) for _, field, p, _, gold in per_column(docs, proposals) if field]
        x, y = np.array(samples, dtype=float).T
        return x, y
    x, y = sample(selection, selection_predictions)
    a, b = sample(risk, risk_predictions)
    iso = IsotonicRegression(out_of_bounds='clip').fit(x, y)
    log = LogisticRegression(C=100.).fit(x[:, None], y)
    result = {}
    for name, probabilities in {'raw': a, 'isotonic': iso.predict(a), 'logistic': log.predict_proba(a[:, None])[:, 1]}.items():
        bins = np.minimum(9, (probabilities * 10).astype(int))
        ece = sum((part := bins == i).mean() * abs(probabilities[part].mean() - b[part].mean())
                  for i in range(10) if (bins == i).any())
        result[name] = {'count': len(b), 'brier': float(np.mean((probabilities - b) ** 2)), 'ece10': float(ece)}
    return result


def candidate_set(item, i):
    """Directional singleton/set diagnostic with explicit HOLD coverage."""
    target = item.target[i]
    p = item.confidence[i]
    options = {None: 1. - p}
    if target is not None:
        options[item.fields[target]] = p
    return options


def conformal_calibrate(docs, proposals, alpha=.1):
    maxima = {}
    for doc, item in zip(docs, proposals, strict=True):
        loss = max(1 - candidate_set(item, i).get(col['expected'], 0.) for i, col in enumerate(doc['columns']))
        maxima[doc['family']] = max(loss, maxima.get(doc['family'], 0.))
    k = ceil((len(maxima) + 1) * (1 - alpha))
    return sorted(maxima.values())[k - 1] if k <= len(maxima) else 1.


def conformal_measure(docs, proposals, q):
    counts = Counter(columns=0, covered=0, singletons=0, direct_singletons=0, direct_wrong=0, pooled_full_sets=0)
    for doc, item in zip(docs, proposals, strict=True):
        for i, col in enumerate(doc['columns']):
            candidates = candidate_set(item, i)
            if q >= 1.:
                # At the vacuous cutoff missing candidates enter with score zero.
                choices = {None, *item.fields}
                counts['pooled_full_sets'] += 1
            else:
                choices = {value for value, p in candidates.items() if 1 - p <= q}
            counts['columns'] += 1
            counts['covered'] += col['expected'] in choices
            counts['singletons'] += len(choices) == 1
            if len(choices) == 1 and None not in choices:
                counts['direct_singletons'] += 1
                counts['direct_wrong'] += col['expected'] not in choices
    return dict(counts)
