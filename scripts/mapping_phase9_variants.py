"""Research policies for Phase 9-B. The caller supplies an approved or offline transport."""
from dataclasses import dataclass

from mapping_phase7_llm import Study, train_examples
from mapping_phase9 import MINI, PRO, assignment


RECIPES = ('matchmaker-dynamic', 'jev-selective', 'jev-dynamic', 'context-full', 'context-dynamic',
           'mag-point', 'mag-pair', 'mag-list', 'mag-point-list', 'mag-permute')


@dataclass
class Comparison:
    direct: dict
    transforms: dict
    contract_issues: dict
    proposals: dict


def published_recipe(doc, frame, call, recipe, *, examples=()):
    if recipe not in RECIPES:
        raise ValueError('Unknown paper-inspired comparison')
    demos = train_examples(doc, examples) if recipe == 'matchmaker-dynamic' else ()
    return Study(doc, frame, MINI, call, demos).run(recipe)


def bidirectional(doc, frame, call):
    run = Study(doc, frame, MINI, call)
    forward = run.align(run.rows, run.complete_pools(run.rows), 'full', name='forward')
    reverse = run.reverse(run.rows)
    candidates = {k: tuple(dict.fromkeys(f for f in (forward.get(k), reverse.get(k)) if f))
                  for k in run.rows if k in forward or k in reverse}
    # Verify both the agreements and disagreements. Agreement alone cannot enter the mapping.
    evidence = run.independent(tuple(candidates), candidates, 'dynamic', kind='verify') if candidates else {}
    scores = {(k, field): .90 + .09 * float(frame.raw[int(k), run.position[field]])
              for (k, field), status in evidence.items() if status == 'MATCH'}
    chosen = assignment(frame, scores)
    transforms = {k: fields[0] for k, fields in candidates.items() if k not in chosen and len(fields) == 1
                  and evidence.get((k, fields[0])) == 'TRANSFORM_REQUIRED'}
    final = run.finalize(chosen, transforms, {})
    return Comparison(final.direct, final.transforms, dict(+final.issues),
                      {'source_to_target': forward, 'target_to_source': reverse,
                       'agreement': {k: f for k, f in forward.items() if reverse.get(k) == f}})


def generator_verifier(doc, frame, call, generator, verifier, *, blind):
    if generator not in (MINI, PRO) or verifier not in (MINI, PRO):
        raise ValueError('The comparison requires pinned Mini 4 or Pro 4')
    suggest = Study(doc, frame, generator, call)
    proposed = suggest.align(suggest.rows, suggest.complete_pools(suggest.rows), 'full', name='generate')
    check = Study(doc, frame, verifier, call)
    if blind:
        independent = check.align(check.rows, check.complete_pools(check.rows), 'dynamic', name='blind-verify')
        accepted = {k: f for k, f in proposed.items() if independent.get(k) == f}
        transforms = {}
    else:
        accepted, transforms = check.verify_choices(proposed, 'dynamic')
    result = check.finalize(accepted, transforms, {})
    return Comparison(result.direct, result.transforms, dict(suggest.result.issues + result.issues), proposed)


def cascade(doc, frame, call, *, locked=None, all_on_failure=False):
    first = Study(doc, frame, MINI, call)
    locked = locked or {}
    active = tuple(k for k in first.rows if k not in locked)
    if not active:
        return Comparison(dict(locked), {}, {}, {})
    mini = first.align(active, first.complete_pools(active), 'full', name='mini')
    checked = first.finalize(mini, {}, locked)
    if all_on_failure and (not mini or checked.issues):
        pending = tuple(k for k in active if k not in checked.direct)
    else:
        pending = tuple(k for k in active if k not in checked.direct and (
            k in mini or (first.frame.raw[int(k)].max() >= .60 and first.frame.ready[int(k)].any())))
    if not pending:
        return Comparison(checked.direct, checked.transforms, dict(+checked.issues), {'mini': mini, 'pro': {}})
    second = Study(doc, frame, PRO, call)
    pro = second.align(pending, second.complete_pools(pending), 'dynamic', name='pro-fallback')
    result = second.finalize(pro, {}, checked.direct)
    return Comparison(result.direct, result.transforms, dict(checked.issues + result.issues),
                      {'mini': mini, 'pro': pro})
