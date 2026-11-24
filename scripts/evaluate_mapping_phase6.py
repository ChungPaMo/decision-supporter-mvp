"""Phase 6 controlled offline schema-matching benchmark."""
import argparse
from collections import Counter
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json
from time import perf_counter

import numpy as np

from contracts.mapping_review import validate_mapping
from evaluate_mapping_phase5 import baseline, train_model
from evaluate_mapping_research import bootstrapped_difference, metrics, timing, write
from mapping_phase5_audit import analyze_method, compact, settlement, transition
from mapping_phase5_data import OUT as PHASE5, read_panel as phase5_panel, write_frozen
from mapping_phase5_local import decisions, example_effect
from mapping_phase6_contract import build_request
from mapping_phase6_data import OUT, read_panel
from mapping_phase6_rank import FORMAT_REASONS, LearnedAliases, Models, build_frames, candidate_mask, propose
from mapping_phase6_risk import (confidence_diagnostic, conformal_calibrate, conformal_measure, group_threshold,
                                 make_predictions, meets_risk, risk_counts, select, select_groups)
from mapping_research_data import load_frozen, sha
from mapping_research_features import CATALOG, Lexicon
from mapping_research_phase3 import CONFIRM_DIR, DATA
from mapping_research_remote import CHAT, SHARED_CACHE
from verify_upstage_backend_replay import load_panel


METHODS = {
    'A05_typed': ('typed', 3, 'none', False),
    'A06_selective': ('combined', 3, 'selective', False),
    'A07_full': ('full', 3, 'none', False),
    'A07_fixed': ('schema', 3, 'none', False),
    'A07_contrast': ('contrast', 3, 'none', False),
    'A07_neighbors': ('neighbors', 3, 'none', False),
    'A07_negative': ('negative', 3, 'none', False),
    'A07_combined': ('combined', 3, 'none', False),
    'A08_confidence': ('combined', 'expand', 'none', False),
    'A09_pointwise': ('point', 3, 'none', False),
    'A10_pairwise': ('combined', 3, 'none', True),
    'A11_listwise': ('combined', 3, 'all', False),
    'A11_pair_list': ('combined', 3, 'all', True),
    'A12_rollup': ('grouped', 3, 'none', False),
    'A15_no_alias': ('without_alias', 3, 'none', False),
    'A18_no_type_evidence': ('without_type', 3, 'none', False),
    'A18_top1': ('combined', 1, 'none', False),
    'A18_top5': ('combined', 5, 'none', False),
    'A18_all': ('combined', 'all', 'none', False),
}


def code_digest():
    base = Path(__file__).parent
    sources = sorted([Path(__file__), *base.glob('mapping_phase6_*.py')])
    return sha({file.name: sha256(file.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for file in sources})


def setup(args):
    lexicon = Lexicon(CATALOG)
    generator, examples, training = train_model(args.phase5, args.data, lexicon)
    original, base_sha = load_frozen(args.data, 'train')
    extra, extra_sha = phase5_panel(args.phase5, 'train_extra')
    dev, dev_sha = read_panel(args.output, 'development')
    old_dev, old_dev_sha = phase5_panel(args.phase5, 'development')
    old_cal, old_cal_sha = phase5_panel(args.phase5, 'calibration')
    aliases = LearnedAliases(original + extra + dev)
    labelled = old_dev + old_cal + dev
    frames = build_frames(labelled, lexicon, generator, aliases)
    model = Models(frames, labelled)
    return lexicon, generator, examples, aliases, model, {
        'train_sha': base_sha, 'phase5_extra_sha': extra_sha, 'phase5_dev_sha': old_dev_sha, 'phase5_cal_sha': old_cal_sha,
        'phase6_dev_sha': dev_sha, 'generator_training_docs': training['training_documents'],
        'verifier_training_docs': len(labelled), 'training_pairs': model.train_size, 'code_sha': code_digest(),
    }


def calculate(frames, scorer, names):
    predictions = {name: [] for name in names}
    ticks = {name: [] for name in names}
    for frame in frames:
        shared = {}
        for name in names:
            mode, width, refine, pair = METHODS[name]
            start = perf_counter()
            predictions[name].append(propose(frame, scorer, mode, width, refine, pairwise=pair, cached=shared))
            ticks[name].append((perf_counter() - start) * 1000)
    return predictions, {name: timing(costs) for name, costs in ticks.items()}


def prior_results(frame, pool):
    votes, _ = example_effect(frame.item, pool, 'bm25', 2)
    values = np.clip(frame.raw + .08 * votes, 0, 1)
    return decisions(frame.item, values, .83, 0., 'local')


def baseline_stage(docs, frames, predictions, pool):
    causes = Counter()
    for doc, frame, rows in zip(docs, frames, predictions, strict=True):
        votes, _ = example_effect(frame.item, pool, 'bm25', 2)
        scores = np.clip(frame.raw + .08 * votes, 0, 1)
        for i, (col, row) in enumerate(zip(doc['columns'], rows, strict=True)):
            field = col['expected']
            if field is None or row['prediction'] == field:
                continue
            j = frame.item.fields.index(field)
            if j not in frame.candidates[i, :3]:
                reason = 'RAW_TOP3_MISS'
            elif frame.item.hard[i, j] is not None:
                reason = 'FORMAT_OR_HARD_ROLE/' + frame.item.hard[i, j]
            elif scores[i, j] < .83:
                reason = 'CONFIDENCE'
            else:
                ready = np.equal(frame.item.hard[i], None)
                top = np.argmax(np.where(ready, scores[i], -1))
                reason = 'REORDERING' if top != j else 'DUPLICATE_OR_SCOPE'
            causes[('positive_hold/' if row['prediction'] is None else 'wrong_assignment/') + reason] += 1
    return dict(causes)


def boundaries(docs, frames, proposals, predictions, width):
    counts = Counter()
    causes = Counter()
    for doc, frame, p, rows in zip(docs, frames, proposals, predictions, strict=True):
        mask = candidate_mask(frame, width)
        for i, (col, row, target, score) in enumerate(zip(doc['columns'], rows, p.semantic_target,
                                                          p.semantic_confidence, strict=True)):
            field = col['expected']
            semantic = col.get('semantic', field)
            is_transform = col.get('state') == 'TRANSFORM_REQUIRED'
            counts['columns'] += 1
            counts['transform_gold'] += is_transform
            counts['predicted_transform'] += p.state[i] == 'TRANSFORM_REQUIRED'
            counts['transform_true'] += is_transform and p.state[i] == 'TRANSFORM_REQUIRED'
            counts['unsafe_direct_on_transform'] += is_transform and row['prediction'] is not None
            if semantic is not None:
                counts['semantic_gold'] += 1
                counts['semantic_correct'] += bool(target is not None and p.fields[target] == semantic and score >= .60)
            if field is None:
                continue
            j = p.fields.index(field)
            for k in (1, 3, 5):
                counts[f'raw_top{k}'] += j in frame.candidates[i, :k]
            counts['configured_pool_hit'] += int(mask[i, j])
            if field == row['prediction']:
                continue
            if not mask[i, j]:
                cause = 'CANDIDATE_RETRIEVAL'
            elif not frame.ready[i, j]:
                why = frame.item.hard[i, j]
                cause = 'TYPE' if why in FORMAT_REASONS else 'ROLE'
            elif target != j:
                cause = 'RANK'
            elif p.target[i] != j:
                cause = 'CONFLICT_OR_LISTWISE'
            else:
                cause = 'CONFIDENCE'
            causes[cause] += 1
    return {**dict(counts), 'first_loss_stage': dict(causes)}


def summary(docs, rows):
    report = compact(metrics(docs, rows))
    report['elapsed_scope'] = 'local offline'
    return report


def compare(docs, frames, combos, policy, pool, *, compare_all):
    rf = [baseline(frame.item) for frame in frames]
    phase5 = [prior_results(frame, pool) for frame in frames]
    winner = policy['winner']
    selected = winner['strategy']
    names = combos.keys() if compare_all else (selected,)
    output = {}
    for name in names:
        entry = policy['methods'][name]
        predictions = [make_predictions(item, entry['threshold'], entry['margin']) for item in combos[name]]
        output[name] = {'metrics': summary(docs, predictions), 'routed_columns': sum(item.routed for item in combos[name])}
    candidates = combos[selected]
    optimum = [make_predictions(item, winner['threshold'], winner['margin']) for item in candidates]
    old_stats, new_stats = (metrics(docs, rows) for rows in (phase5, optimum))
    families = {doc['id']: doc['family'] for doc in docs}
    grouped = [[(families[doc], ok, wrong, n) for doc, ok, wrong, n in item['case_counts']]
               for item in (old_stats, new_stats)]
    changes = transition(phase5, optimum, docs)
    protected = Counter()
    for doc, old, new in zip(docs, phase5, optimum, strict=True):
        for col, first, second in zip(doc['columns'], old, new, strict=True):
            gold = col['expected']
            if first['prediction'] is None and second['prediction'] is not None:
                protected['old_hold_recovered' if second['prediction'] == gold else 'old_hold_new_wrong'] += 1
            if first['prediction'] is not None and first['prediction'] == gold:
                protected['prior_correct'] += 1
                protected['prior_correct_kept'] += first['prediction'] == second['prediction']
    return {'A01_exact_rapid': summary(docs, rf), 'A02_phase5': compact(old_stats), 'comparisons': output,
            'winner': selected, 'delta_vs_phase5': changes, 'hold_recovery': dict(protected),
            'group_bootstrap_95': bootstrapped_difference(*grouped),
            'stages': boundaries(docs, frames, candidates, optimum, METHODS[selected][1]),
            'phase5_failure_breakdown': baseline_stage(docs, frames, phase5, pool)}


def plan(frames, ledger):
    records = {}
    for model in CHAT:
        projected = [build_request(frame, model)[2] for frame in frames]
        totals = sum((Decimal(record['reserve_usd']) for record in projected), Decimal(0))
        records[model] = {'requested_documents': len(frames), 'wire_bytes_before_margin': sum(x['wire_bytes'] for x in projected),
                          'max_output_tokens': sum(x['max_output_tokens'] for x in projected),
                          'reserve_upper_usd': str(totals), 'fits_current_headroom': totals <= Decimal(ledger['headroom_usd'])}
    return {'status': 'NOT_RUN_NEW_TRANSFER_APPROVAL_REQUIRED', 'provider_calls': 0, 'records': records}


def historical(args, ready):
    lexicon, generator, pool, aliases = ready[:4]
    ledger = [json.loads(line) for line in (args.cache / 'billing.jsonl').read_bytes().splitlines()]
    result = {}
    for split in ('final', 'confirmatory'):
        panel = load_panel(split, args.data, args.confirmatory)
        frames = build_frames(panel.docs, lexicon, generator, aliases)
        recipes = {name: analyze_method(panel, name, args.cache, ledger) for name in ('mini-table', 'pro-table', 'mini-business', 'pro-business')}
        base = [prior_results(frame, pool) for frame in frames]
        overlay = []
        for j, (old, frame) in enumerate(zip(base, frames, strict=True)):
            locked = {str(i): row['prediction'] for i, row in enumerate(old) if row['prediction']}
            mini = recipes['mini-business']['predictions'][j]
            pro = recipes['pro-business']['predictions'][j]
            proposed = {str(i): a['prediction'] for i, (a, b) in enumerate(zip(mini, pro, strict=True))
                        if str(i) not in locked and a['prediction'] is not None and a['prediction'] == b['prediction']}
            safe, _ = validate_mapping(proposed, locked, lambda pos, field: None
                                      if frame.ready[int(pos), frame.item.fields.index(field)] else 'HARD')
            overlay.append([{'prediction': safe.get(str(i)), 'ranking': None,
                             'top3': [safe[str(i)]] if str(i) in safe else []} for i in range(len(old))])
        result[split] = {'A02': summary(panel.docs, base),
                         'A17': {'metrics': summary(panel.docs, overlay), 'delta': transition(base, overlay, panel.docs)},
                         'cached_solar': {name: {**record['details'], 'metrics': summary(panel.docs, record['predictions'])}
                                          for name, record in recipes.items()}}
    return result


def calibration_run(args, ready):
    lexicon, generator, pool, aliases, scorer, provenance = ready
    docs, digest = read_panel(args.output, 'selection')
    frames = build_frames(docs, lexicon, generator, aliases)
    combinations, times = calculate(frames, scorer, METHODS)
    winner, opt, curves = select(docs, combinations, exclude=('A09_pointwise', 'A18_no_type_evidence'))
    name = winner['strategy']
    ri_docs, ri_sha = read_panel(args.output, 'risk')
    ri_frames = build_frames(ri_docs, lexicon, generator, aliases)
    selected = combinations[name]
    ri_prediction, _ = calculate(ri_frames, scorer, [name])
    risk = ri_prediction[name]
    thresholds = {kind: select_groups(docs, selected, kind, winner['threshold'], winner['margin'])
                  for kind in ('field', 'domain')}
    comparisons = {}
    for kind, mapped in thresholds.items():
        rows = [make_predictions(item, winner['threshold'], winner['margin'],
                                 kind='field' if kind == 'field' else doc['entity'], overrides=mapped)
                for doc, item in zip(ri_docs, risk, strict=True)]
        comparisons[kind] = risk_counts(ri_docs, rows)
    diagnostics = {'field_or_domain': comparisons, 'confidence': confidence_diagnostic(docs, selected, ri_docs, risk),
                   'crc_group_error_1pct': group_threshold(ri_docs, risk, winner['margin'], .01),
                   'crc_group_error_5pct': group_threshold(ri_docs, risk, winner['margin'], .05),
                   'conformal_cutoff': conformal_calibrate(ri_docs, risk)}
    policy = {'winner': winner, 'methods': opt, 'curves': curves, 'risk_targets_met': meets_risk(winner),
              'selection_sha': digest, 'risk_sha': ri_sha, 'risk_diagnostics': diagnostics,
              'provenance': provenance}
    policy['sha256'] = sha(policy)
    frozen = args.output / 'frozen-policy.json'
    write_frozen(frozen, policy)
    original = settlement(args.cache)
    write(args.output / 'selection-results.json', {'report': compare(docs, frames, combinations, policy, pool, compare_all=True),
        'timings_computed_with_shared_features': times, 'paid_plan_first_10_selection_documents': plan(frames[:10], original)})


def eval_holdout(args, ready):
    lexicon, generator, pool, aliases, scorer, provenance = ready
    policy = json.loads((args.output / 'frozen-policy.json').read_bytes())
    if policy['sha256'] != sha({k: v for k, v in policy.items() if k != 'sha256'}) or policy['provenance'] != provenance:
        raise ValueError('Frozen policy or algorithm changed after selection')
    docs, digest = read_panel(args.output, 'holdout')
    frames = build_frames(docs, lexicon, generator, aliases)
    # Fixed ablations and candidate widths, evaluated with their selection-set thresholds only.
    names = list(METHODS)
    combos, times = calculate(frames, scorer, names)
    selected = policy['winner']['strategy']
    test_time = []
    mode, width, refine, pair = METHODS[selected]
    for frame in frames:
        start = perf_counter()
        propose(frame, scorer, mode, width, refine, pairwise=pair)
        test_time.append((perf_counter() - start) * 1000)
    report = compare(docs, frames, combos, policy, pool, compare_all=True)
    p5_gold, p5_sha = phase5_panel(args.phase5, 'holdout')
    p5_frames = build_frames(p5_gold, lexicon, generator, aliases)
    regression, _ = calculate(p5_frames, scorer, [selected])
    prior = compare(p5_gold, p5_frames, regression, policy, pool, compare_all=False)
    write(args.output / 'holdout-results.json', {'policy_sha': policy['sha256'], 'holdout_sha': digest,
        'report': report, 'phase5_known_regression': {'digest': p5_sha, **prior},
        'conformal': conformal_measure(docs, combos[selected], policy['risk_diagnostics']['conformal_cutoff']),
        'profile_and_retrieval_ms': timing([f.milliseconds for f in frames]), 'winner_rerank_ms': timing(test_time),
        'ablation_per_method_ms_cached': times})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('select', 'holdout', 'historical', 'billing'))
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--phase5', type=Path, default=PHASE5 / 'verified')
    parser.add_argument('--cache', type=Path, default=SHARED_CACHE)
    parser.add_argument('--data', type=Path, default=DATA)
    parser.add_argument('--confirmatory', type=Path, default=CONFIRM_DIR)
    args = parser.parse_args()
    before = settlement(args.cache)
    if args.action == 'billing':
        write(args.output / 'billing.json', before)
    else:
        from threadpoolctl import threadpool_limits

        with threadpool_limits(limits=2):
            ready = setup(args)
            if args.action == 'select':
                calibration_run(args, ready)
            elif args.action == 'holdout':
                eval_holdout(args, ready)
            else:
                write(args.output / 'historical-results.json', historical(args, ready))
    if before['ledger_sha256'] != settlement(args.cache)['ledger_sha256']:
        raise ValueError('Original research ledger changed')


if __name__ == '__main__':
    main()
