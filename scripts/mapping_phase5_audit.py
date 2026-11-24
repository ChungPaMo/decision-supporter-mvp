"""Read-only billing reconciliation and full pinned response-corpus error attribution."""
from collections import Counter, defaultdict
from decimal import Decimal
from hashlib import sha256
import json

import httpx

from app.api.ingest_ai import review_mapping_file
from app.config import Settings
from app.integrations.upstage import UpstageClient
from contracts.mapping_review import decode_mapping, strict_json, validate_mapping
from evaluate_mapping_research import baseline_decisions, timing
from mapping_phase5_evidence import format_issue
from mapping_phase5_local import prepare_local
from mapping_research_data import csv_bytes, sha
from mapping_research_phase3 import collision_guard, make_jobs, request_key, row_result, scored, source_prior
from mapping_research_remote import APPROVED_CAP, billing_summary
from verify_upstage_backend_replay import DATASET, ReplayMeter, adapt_ids, load_panel


RECIPES = ('mini-table', 'mini-business', 'pro-table', 'pro-business', 'preview-business',
           'concept', 'rapid-verify', 'rapid-hold')
CONSOLE = {'date_kst': '2026-11-24', 'displayed_usd_before_vat': '1.65', 'credits_used_usd': '1.65',
           'postpaid_usd': '0', 'counts': {'classify_pages': 17, 'parse_enhanced_pages': 13,
           'parse_standard_pages': 24, 'extract_enhanced_pages': 9, 'extract_standard_pages': 6,
           'ocr_pages': 4, 'embedding_input_tokens': 270664}}


def settlement(cache):
    audit = cache / 'billing.jsonl'
    raw = audit.read_bytes()
    events = [json.loads(line) for line in raw.splitlines()]
    requests = defaultdict(list)
    for row in events:
        requests[row['request_sha256']].append(row)
    buckets, usage = Counter(), Counter()
    for group in requests.values():
        reserve = [row for row in group if row['state'] == 'RESERVED']
        if len(reserve) != 1:
            raise ValueError('Each ledger request requires exactly one reservation')
        mode = reserve[0].get('mode') or 'default'
        current = sum((Decimal(row.get('cost_delta_usd') or '0') for row in group), Decimal(0))
        completed = [row for row in group if row['state'] in ('RECEIVED', 'FAILED')]
        if len(completed) > 1:
            raise ValueError('Ledger request has multiple completion events')
        last = completed[0] if completed else reserve[0]
        note = last.get('usage') or {}
        if mode in ('standard', 'enhanced', 'auto'):
            for suffix in ('standard', 'enhanced'):
                pages = note.get(suffix)
                if isinstance(pages, list):
                    usage['parse_' + suffix + '_pages'] += len(pages)
        if last['state'] == 'RECEIVED' and last.get('calculated_cost_usd') is not None:
            resolved = Decimal(last['calculated_cost_usd'])
            if resolved != current:
                raise ValueError('Measured cost and reservation delta disagree')
            buckets['locally_calculated'] += current
        else:
            if current:
                buckets['pending'] += current
                reason = last.get('category') or last['state']
                buckets[f'{mode}/{reason}'] += current
    total = buckets['locally_calculated'] + buckets['pending']
    summary = billing_summary(cache)
    if total != Decimal(summary['cost_or_reserve_usd']) or len(requests) != summary['calls']:
        raise ValueError('Ledger reconciliation mismatch')
    return {'ledger_sha256': sha256(raw).hexdigest(), 'scope_comparison': 'CONSOLE_AGGREGATE_ONLY',
            'ledger_local_usd': str(buckets['locally_calculated']), 'pending_usd': str(buckets['pending']),
            'locked_usd': str(total), 'headroom_usd': str(APPROVED_CAP - total), 'approved_usd': str(APPROVED_CAP),
            'adjustment_usd': '0', 'new_calls': 0, 'pending_by_mode_reason': {
                key: str(value) for key, value in buckets.items() if '/' in key},
            'console': CONSOLE, 'explicit_parse_page_modes_in_ledger': dict(usage), 'historical': summary}


def read_cache(cache, endpoint, payload):
    key = request_key(endpoint, payload)
    path = cache / f'{key}.json'
    if not path.exists():
        return None, key
    entry = strict_json(path.read_bytes())
    if entry['request_sha256'] != key or entry['body_sha256'] != sha(entry['body']):
        raise ValueError('Pinned API cache identity changed')
    return entry['body'], key


def stock_or_bom(truth, field):
    categories = (
        ({'product_id', 'material_id', 'component_id'}, 'product_material_component'),
        ({'base_qty', 'qty_per'}, 'bom_output_vs_usage'),
        ({'on_hand_qty', 'allocated_qty', 'available_qty'}, 'inventory_quantity_role'),
    )
    return next((name for fields, name in categories if truth in fields and field in fields), 'wrong_business_field')


def transition(before, after, docs):
    counts = Counter()
    for doc, old, new in zip(docs, before, after, strict=True):
        for i, col in enumerate(doc['columns']):
            target, first, second = col['expected'], old[i]['prediction'], new[i]['prediction']
            counts['correct_added'] += second is not None and second == target and first != target
            counts['correct_lost'] += first is not None and first == target and second != target
            counts['wrong_added'] += second is not None and second != target and (first is None or first == target)
            counts['wrong_removed'] += first is not None and first != target and (second is None or second == target)
            counts['different_wrong'] += first is not None and second is not None and first != second and target not in (first, second)
    return dict(counts)


def analyze_method(panel, method, cache, ledger):
    records = {}
    duplicates, errors, first, overlapping, wrong = (Counter() for _ in range(5))
    affected, ids, requests = set(), set(), set()
    for j, (endpoint, payload, allowed, vocab, keyed) in make_jobs(panel, range(len(panel.docs)), method, None):
        ids.add(j)
        body, key = read_cache(cache, endpoint, payload)
        if body is None:
            continue
        requests.add(key)
        result = decode_mapping(body, endpoint, allowed, vocab, keyed=keyed)
        records[j] = body, result, key
        repeated = Counter(field for field in result.values.values() if field)
        duplicates.update({j: sum(count for count in repeated.values() if count > 1)})
        errors.update(result.issues)
        if result.issues or duplicates[j]:
            affected.add(j)
        for pos in allowed:
            col = panel.docs[j]['columns'][int(pos)]
            target, candidate = col['expected'], result.values.get(pos)
            reasons = []
            if result.fatal or pos in result.rejected:
                reasons.append(result.fatal or result.rejected[pos])
            if candidate and repeated[candidate] > 1:
                reasons.append('DUPLICATE_TARGET')
            if target is not None and candidate is None and not reasons:
                reasons.append('MODEL_HOLD_WITH_GOLD')
            if candidate is not None and target != candidate:
                error = col['scenario'] if target is None else stock_or_bom(target, candidate)
                wrong[error] += 1
                reasons.append('MODEL_ROLE/' + error)
            if reasons:
                first[reasons[0]] += 1
                overlapping.update(reasons)
    predictions = []
    for j, doc in enumerate(panel.docs):
        result = records[j][1] if j in records else None
        prior = source_prior(panel, j, 'rapid') if method == 'rapid-hold' else {}
        safe, _ = collision_guard(result.values if result else {}, prior, panel.records[j])
        predictions.append(row_result(safe, len(doc['columns'])))
    billed = [event for event in ledger if event['request_sha256'] in requests]
    completed = [event for event in billed if event['state'] == 'RECEIVED']
    total = sum((Decimal(event.get('cost_delta_usd') or '0') for event in billed), Decimal(0))
    return {'records': records, 'predictions': predictions, 'details': {
        'cached_requests': len(requests), 'covered_documents': len(records), 'planned_documents': len(ids),
        'contract_affected': len(affected), 'duplicate_target_rows': sum(duplicates.values()),
        'errors': dict(errors), 'first_failure': dict(first), 'overlapping': dict(overlapping), 'raw_role_errors': dict(wrong),
        'historical_usd': str(total), 'historical_usage': {key: sum((row.get('usage') or {}).get(key) or 0
                for row in completed) for key in ('prompt_tokens', 'completion_tokens', 'input_tokens', 'output_tokens')},
        'historical_timings': timing([event['ms'] for event in completed if 'ms' in event]) if completed else None,
    }}


def protect(item, proposals, *, strict=False):
    mapping = item.baseline.sheets[0].existing_mapping
    locked = {str(pos - 1): field for field, pos in mapping.items()}
    matrix = item.legacy if strict else item.hard
    effective = {pos: field for pos, field in proposals.items() if locked.get(pos) != field}
    return validate_mapping(effective, locked, lambda pos, field: matrix[int(pos), item.fields.index(field)])


def recover_duplicates(item, proposals):
    groups = defaultdict(list)
    candidates = dict(proposals)
    locked = set(item.baseline.sheets[0].existing_mapping)
    for pos, field in proposals.items():
        if field:
            groups[field].append(pos)
    for field, contenders in groups.items():
        if field in locked or len(contenders) < 2:
            continue
        target = item.fields.index(field)
        ranked = []
        for pos in contenders:
            i = int(pos)
            if item.hard[i, target] is None:
                values = item.features[i, target]
                strength = max(float(values[1]), .55 * values[2] + .25 * values[3] + .2 * max(0, item.role[i, target]))
                ranked.append((strength, pos))
        ranked.sort(reverse=True)
        if ranked and ranked[0][0] >= .65 and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= .20):
            for pos in contenders:
                if pos != ranked[0][1]:
                    candidates[pos] = None
    return protect(item, candidates)[0] if not item.route_suspect else {}


def backtest(panel, prepared, raw, reference):
    before, new, strict, duplicate_resolved = [], [], [], []
    type_detail, loss_type, losses, restoration = (Counter() for _ in range(4))
    files = [csv_bytes(doc) for doc in panel.docs]
    hashes = [sha256(data).hexdigest() for data in files]
    settings = Settings(_env_file=None, upstage_api_enabled=True, ai_mapping_enabled=True, ai_external_data_allowed=True,
                        upstage_api_key='offline-fixture-placeholder', ai_mapping_strategy='concept', ai_mapping_max_columns=64,
                        ai_external_synthetic_sources={DATASET: set(hashes)})
    for j, (doc, item, data) in enumerate(zip(panel.docs, prepared, files, strict=True)):
        body, decoded, _ = raw[j]
        provider = UpstageClient(settings, ReplayMeter(), transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=adapt_ids(body))))
        previous = review_mapping_file(settings, provider, DATASET, 'fixture.csv', data, None, doc['entity'], {}, True)
        legacy = {str(i): row.target_field for i, row in enumerate(previous.columns)}
        old = row_result(legacy, len(doc['columns']))
        upgraded, _ = protect(item, decoded.values)
        isolated_profile = dict(upgraded)
        if item.route_suspect:
            upgraded = {}
        before.append(old)
        strict.append(row_result(isolated_profile, len(doc['columns'])))
        new.append(row_result(upgraded, len(doc['columns'])))
        duplicate_resolved.append(row_result(recover_duplicates(item, decoded.values), len(doc['columns'])))
        for i, (col, row) in enumerate(zip(doc['columns'], previous.columns, strict=True)):
            target, observed = col['expected'], row.target_field
            model = decoded.values.get(str(i))
            revised = upgraded.get(str(i))
            if row.hold_reason == 'TYPE_INCOMPATIBLE' and model is not None:
                detail = format_issue(model, item.observations[i], col['header']) or 'LEGACY_TYPE_BLOCK_RECOVERABLE'
                type_detail[f'{model}/{detail}'] += 1
            if reference[j][i]['prediction'] == target and target and observed != target:
                losses[row.hold_reason or row.reason] += 1
                if row.hold_reason == 'TYPE_INCOMPATIBLE':
                    detail = format_issue(target, item.observations[i], col['header']) or 'LEGACY_TYPE_BLOCK_RECOVERABLE'
                    loss_type[f'{target}/{detail}'] += 1
            if observed != target and target and revised == target:
                restoration[row.hold_reason or row.reason] += 1
    return before, strict, new, duplicate_resolved, {'legacy_type_holds': dict(type_detail),
             'lost_phase3_correct_by_reason': dict(losses), 'lost_correct_type_reasons_by_field': dict(loss_type),
             'recovered_phase4_correct_by_reason': dict(restoration), 'change_vs_backend': transition(before, new, panel.docs),
             'local_conflict_resolution_minus_hard': transition(new, duplicate_resolved, panel.docs),
             'phase4_minus_phase3': transition(reference, before, panel.docs)}


def historical(data, confirm, cache, lexicon):
    ledger = [json.loads(line) for line in (cache / 'billing.jsonl').read_bytes().splitlines()]
    report = {}
    for split in ('final', 'confirmatory'):
        panel = load_panel(split, data, confirm)
        panel.baselines = {method: [baseline_decisions(record, method) for record in panel.records] for method in ('exact', 'rapid')}
        prepared = [prepare_local(doc, lexicon) for doc in panel.docs]
        results = {method: analyze_method(panel, method, cache, ledger) for method in RECIPES}
        concept = results['concept']
        cached = concept['predictions']
        previous, profiles, guarded, duplicate_resolved, reasons = backtest(panel, prepared, concept['records'], cached)
        n = len(prepared)

        def maps(method):
            return results[method]['predictions']

        def by_cols(match):
            return [row_result({str(i): match(j, i) for i in range(len(doc['columns']))}, len(doc['columns']))
                    for j, doc in enumerate(panel.docs)]

        def agreement(methods, j, i):
            keys = {results[method]['records'][j][2] for method in methods if j in results[method]['records']}
            if len(keys) != len(methods):
                return None
            values = [maps(method)[j][i]['prediction'] for method in methods]
            return values[0] if values[0] and len(set(values)) == 1 else None

        def fallback(j, i):
            base = maps('mini-business')[j]
            target = base[i]['prediction']
            secondary = maps('pro-business')[j][i]['prediction']
            locked = {row['prediction'] for row in base if row['prediction']}
            return target or (secondary if secondary not in locked else None)

        strategies = {
            'Mini→Pro hold-only': by_cols(fallback),
            'Mini/Pro business unanimity': by_cols(lambda j, i: agreement(('mini-business', 'pro-business'), j, i)),
            'Mini 2 input variants unanimity': by_cols(lambda j, i: agreement(('mini-table', 'mini-business'), j, i)),
            'Mini 3 input variants unanimity': by_cols(lambda j, i: agreement(('mini-table', 'mini-business', 'concept'), j, i)),
            'Mini 5 input variants unanimity': by_cols(lambda j, i: agreement(
                ('mini-table', 'mini-business', 'concept', 'rapid-verify', 'rapid-hold'), j, i)),
            'Mini Concept→local hard verifier': guarded,
            'Mini Concept→local conflict resolution': duplicate_resolved,
        }
        # Partial caches remain diagnostic. Missing actual inputs must be visible in the report.
        report[split] = {'documents': n, 'digest': panel.digest, 'attribution': reasons, 'methods': {
            method: {**result['details'], 'metrics': compact(scored(panel.docs, result['predictions']))}
            for method, result in results.items()}, 'replay': {
                'phase4': compact(scored(panel.docs, previous)), 'profile_hard_no_route_filter': compact(scored(panel.docs, profiles)),
                'profile_hard_and_route_filter': compact(scored(panel.docs, guarded))},
            'offline_stages': {name: {'metrics': compact(scored(panel.docs, predictions)),
                                    'change_vs_mini_business': transition(maps('mini-business'), predictions, panel.docs)}
                               for name, predictions in strategies.items()}}
    return report


def compact(metrics):
    metrics = dict(metrics)
    for key in ('case_counts', 'per_family'):
        metrics.pop(key, None)
    return metrics
