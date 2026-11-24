"""Phase 9 research evaluation helpers and document-level assignment."""
from collections import Counter
from dataclasses import dataclass

from scipy.optimize import linear_sum_assignment

from contracts.mapping_review import validate_mapping
from evaluate_mapping_phase5 import baseline
from evaluate_mapping_phase7 import MODELS, Study
from evaluate_mapping_research import bootstrapped_difference, metrics


METHODS = ('exact_rapid', 'phase5', 'phase6', 'mini_raw', 'pro_raw', 'mini_guarded',
           'pro_guarded', 'locked_hold_recovery', 'phase6_independent_verifier')
MINI, PRO = MODELS[:2]


@dataclass
class DocumentResult:
    rows: dict
    issues: dict


def rows_for(count, mapping, ranking):
    return [{'prediction': mapping.get(key), 'top3': [mapping[key]] if key in mapping else [],
             'ranking': list(ranking[key])}
            for key in map(str, range(count))]


def assignment(frame, scores, locked=None, *, minimum=.90, margin=.05):
    """Give every source a private HOLD, with absolute and row-margin gates before matching."""
    locked = dict(locked or {})
    if len(set(locked.values())) != len(locked):
        raise ValueError('Locked mapping must already have unique targets')
    occupied = set(locked.values())
    fields = [f for f in frame.item.fields if f not in occupied]
    positions = {f: i for i, f in enumerate(frame.item.fields)}
    active = [str(i) for i in range(frame.ready.shape[0]) if str(i) not in locked]
    scores_by_row = []
    for row in active:
        supported = {field: scores[row, field] for field in fields
                     if (row, field) in scores and frame.ready[int(row), positions[field]]}
        scores_by_row.append(supported)
    if not active:
        return locked
    costs = []
    for i, supported in enumerate(scores_by_row):
        costs.append([-supported[f] if f in supported and supported[f] >= minimum
                      and all(supported[f] - confidence >= margin for other, confidence in supported.items() if other != f)
                      else 2 for f in fields] + [0 if i == j else 2 for j in range(len(active))])
    src, dst = linear_sum_assignment(costs)
    return locked | {active[i]: fields[j] for i, j in zip(src, dst, strict=True)
                     if j < len(fields) and costs[i][j] < 0
                     and all(other[j] >= 0 or other[j] - costs[i][j] >= margin
                             for k, other in enumerate(costs) if k != i)}


def document_eval(doc, frame, phase6, call):
    """All A requests are independent of provider output. The same responses feed each ablation."""
    refs = baseline(frame.item)
    study = Study(doc, frame, MINI, call)
    columns = study.rows
    pool = study.pools(columns, 3)
    rank = study.pools(columns, 5)
    proposals = {str(i): row['prediction'] for i, row in enumerate(phase6) if row['prediction']}
    locked = {k: f for k, f in proposals.items() if refs[int(k)]['prediction'] == f
              and frame.ready[int(k), study.position[f]]}

    rows, issues = {}, {}
    for model, prefix in ((MINI, 'mini'), (PRO, 'pro')):
        run = Study(doc, frame, model, call)
        choices = run.align(columns, run.complete_pools(columns), 'full', name='direct')
        guarded = run.finalize(choices, {}, {})
        rows[prefix + '_raw'] = rows_for(len(columns), choices, rank)
        rows[prefix + '_guarded'] = rows_for(len(columns), guarded.direct, rank)
        issues[prefix + '_raw'] = issues[prefix + '_guarded'] = dict(+guarded.issues)

    # The verifier sees all top candidates with a consistent order, not a prior model's answer.
    blind_pool = {k: tuple(sorted(set(options) | ({proposals[k]} if k in proposals else set())))
                  for k, options in pool.items()}
    states = study.independent(columns, blind_pool, 'dynamic', kind='verify')
    accepted, _ = study.point_choices(blind_pool, states)
    compatible = lambda k, f: None if frame.ready[int(k), study.position[f]] else 'LOCAL_HARD_CONSTRAINT'
    recover, rejected = validate_mapping({k: f for k, f in accepted.items() if k not in locked}, locked, compatible)
    verified, unique = validate_mapping({k: f for k, f in proposals.items() if states.get((k, f)) == 'MATCH'}, {}, compatible)
    choose = {'locked_hold_recovery': (recover, rejected), 'phase6_independent_verifier': (verified, unique)}
    for name, (mapping, rejection) in choose.items():
        rows[name] = rows_for(len(columns), mapping, rank)
        issues[name] = dict(study.result.issues + Counter(x for x in rejection.values() if x == 'DUPLICATE_TARGET'))
    return DocumentResult(rows, issues)


def summary(docs, rows, *, baseline_rows=None, contract_counts=()):
    report = metrics(docs, rows)
    report.pop('case_counts')
    if contract_counts:
        report['contract_documents'] = sum(bool(flags) for flags in contract_counts)
        report['contract_impact_rate'] = report['contract_documents'] / len(docs)
        report['contract_issues'] = dict(sum((Counter(flags) for flags in contract_counts), Counter()))
    if baseline_rows is not None:
        paired, new_wrong = [], 0
        for doc, before, after in zip(docs, baseline_rows, rows, strict=True):
            for col, left, right in zip(doc['columns'], before, after, strict=True):
                truth, x, y = col['expected'], left['prediction'], right['prediction']
                new_wrong += y is not None and y != truth and x != y
                paired.append((doc['family'], x is not None and x == truth, x is not None and x != truth,
                               y is not None and y == truth, y is not None and y != truth))
        held = sum(correct and new for _, correct, _, new, _ in paired)
        before = sum(correct for _, correct, _, _, _ in paired)
        report['paired'] = {
            'existing_correct_preserved': held, 'existing_correct': before,
            'correct_recovered': sum(not correct and new for _, correct, _, new, _ in paired),
            'new_wrong': new_wrong,
            'family_bootstrap': bootstrapped_difference([(f, g, b, 1) for f, g, b, _, _ in paired],
                                                        [(f, g, b, 1) for f, _, _, g, b in paired]),
        }
    return report
