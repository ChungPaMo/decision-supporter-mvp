"""Freeze and run the explicitly approved Phase 9-A Solar baseline on synthetic data."""
from argparse import ArgumentParser, Namespace
from collections import Counter
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from contracts.mapping_review import strict_json
from evaluate_mapping_phase6 import DATA, PHASE5, OUT as PHASE6, baseline, prior_results, setup
from evaluate_mapping_phase7 import baselines
from evaluate_mapping_research import timing, write
from mapping_phase5_audit import settlement
from mapping_phase9 import METHODS, MINI, PRO, document_eval, summary
from mapping_phase9_data import manifest, panels
from mapping_research_data import canonical, sha
from mapping_research_remote import (CHAT, PHASE9_APPROVED_CAP, SHARED_CACHE, VAT, PaidResearch,
                                     expected_cost, load_local_key, lock_paid_cache)


OUT = Path('.artifacts/mapping-research/phase9')
STAGE_LIMIT = Decimal('1.00')
ENDPOINT = '/chat/completions'
MAX_BYTES, MAX_OUTPUT = 24_000, 1_250
FILES = ('evaluate_mapping_phase9.py', 'mapping_phase9.py', 'mapping_phase9_data.py',
         'mapping_phase7_llm.py', 'mapping_research_remote.py')


def code_digest():
    paths = [Path(__file__).with_name(name) for name in FILES]
    paths.append(Path(__file__).resolve().parents[1] / 'contracts/mapping_review.py')
    return sha({path.name: sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for path in paths})


def selection():
    splits = panels()
    docs = splits['selection']
    paths = Namespace(output=PHASE6 / 'verified', phase5=PHASE5 / 'verified', data=DATA)
    frozen = strict_json((paths.output / 'frozen-policy.json').read_bytes())
    ready = setup(paths)
    frames, local, _ = baselines(docs, ready, frozen)
    refs = {'exact_rapid': [baseline(frame.item) for frame in frames],
            'phase5': [prior_results(frame, ready[2]) for frame in frames], 'phase6': local}
    baseline_quality = {name: summary(docs, rows, baseline_rows=local) for name, rows in refs.items()}
    return docs, frames, local, manifest(splits), splits, frozen['sha256'], baseline_quality


def build_plan(docs, frames, local, partitions, policy_sha, ledger):
    requests, seen = [], set()
    for doc, frame, previous in zip(docs, frames, local, strict=True):
        captured = []

        def capture(stage):
            wire = stage.wire
            size, tokens = len(canonical(wire)), wire['max_tokens']
            fingerprint = sha(wire)
            if size > MAX_BYTES or tokens > MAX_OUTPUT or fingerprint in seen:
                raise ValueError('Every Phase 9-A wire must be unique and within the review envelope')
            seen.add(fingerprint)
            reserve = VAT * expected_cost(wire, CHAT[wire['model']])
            record = {'document_id': doc['id'], 'stage': stage.name, 'model': wire['model'],
                      'wire_sha256': fingerprint, 'input_token_proxy': size + 512,
                      'output_tokens_max': tokens, 'reserve_usd': str(reserve)}
            requests.append(record)
            captured.append(wire['model'])
            return {}

        document_eval(doc, frame, previous, capture)
        if Counter(captured) != {MINI: 2, PRO: 1}:
            raise ValueError('Phase 9-A requires two Mini and one Pro call per document')
    total = sum((Decimal(row['reserve_usd']) for row in requests), Decimal(0))
    locked = Decimal(ledger['locked_usd'])
    if total > STAGE_LIMIT or locked + total > PHASE9_APPROVED_CAP:
        raise ValueError('Frozen stage reservation exceeds its budget')
    payload = {'scope': 'PHASE9_A_SYNTHETIC_SELECTION_ONLY', 'endpoint': ENDPOINT,
               'ledger_sha256': ledger['ledger_sha256'], 'locked_usd': str(locked),
               'cumulative_limit_usd': str(PHASE9_APPROVED_CAP), 'stage_limit_usd': str(STAGE_LIMIT),
               'maximum_usd': str(total), 'calls_max': len(requests), 'providers': list(CHAT),
               'selection_sha256': partitions['selection']['sha256'], 'policy_sha256': policy_sha,
               'code_sha256': code_digest(), 'source_sha256': [doc['csv_sha256'] for doc in docs],
               'allowed_input': ['synthetic entity and title, column headers and up to three values per column',
                                 'fixed schema, business definitions, derived profiles and relations, candidate order',
                                 'derived contrastive evidence and task IDs'],
               'requests': requests}
    return {**payload, 'approval_sha256': sha(payload)}


def validate_approval(plan, approval):
    signed = {key: value for key, value in plan.items() if key != 'approval_sha256'}
    if (plan.get('scope') != 'PHASE9_A_SYNTHETIC_SELECTION_ONLY' or
            sha(signed) != plan.get('approval_sha256') or
            set(approval) != {'approval_sha256', 'maximum_usd'} or
            approval['approval_sha256'] != plan['approval_sha256']):
        raise ValueError('A separate approval tied to the exact Phase 9-A plan is required')
    cap = Decimal(approval['maximum_usd'])
    if not cap.is_finite() or not Decimal(plan['maximum_usd']) <= cap <= STAGE_LIMIT:
        raise ValueError('Approved stage cap does not cover the plan within the stage ceiling')
    return cap


def execute(plan, docs, frames, local, approval, references, output):
    expected = iter(plan['requests'])
    with lock_paid_cache(SHARED_CACHE):
        ledger = settlement(SHARED_CACHE)
        if ledger['ledger_sha256'] != plan['ledger_sha256']:
            raise ValueError('Shared ledger changed after planning; prepare an updated plan for approval')
        approved = validate_approval(plan, approval)
        locked = Decimal(ledger['locked_usd'])
        if not load_local_key():
            raise ValueError('Upstage credential is unavailable in the ignored local file')
        client = PaidResearch(SHARED_CACHE, min(locked + approved, PHASE9_APPROVED_CAP), approved=True, phase9=True)
        consumed, telemetry, doc_elapsed, evaluated = 0, [], [], []

        def invoke(stage):
            nonlocal consumed
            item = next(expected)
            wire = stage.wire
            name = wire['model']
            if (sha(wire) != item['wire_sha256'] or stage.name != item['stage'] or name != item['model']
                    or item['document_id'] != doc['id']):
                raise ValueError('Request differs from its approved exact wire digest')
            before, started = client.spent, perf_counter()
            cached = client.cached_response(ENDPOINT, wire)
            body = cached if cached is not None else client.call(ENDPOINT, wire, CHAT[name])
            elapsed = (perf_counter() - started) * 1000
            consumed += 1
            delta = client.spent - before
            if delta > Decimal(item['reserve_usd']) or client.spent > locked + approved:
                raise ValueError('Provider usage exceeded its reservation; stop for reconciliation')
            if body.get('model') != name:
                raise ValueError('Provider response model does not match the approved snapshot')
            telemetry.append({'document_id': doc['id'], 'model': name, 'stage': stage.name, 'ms': elapsed,
                              'cached': cached is not None, 'usage': body.get('usage'), 'cost_usd': str(delta)})
            return body

        for doc, frame, previous in zip(docs, frames, local, strict=True):
            started = perf_counter()
            evaluated.append(document_eval(doc, frame, previous, invoke))
            doc_elapsed.append((perf_counter() - started) * 1000)
        if consumed != plan['calls_max'] or next(expected, None) is not None:
            raise ValueError('Executed steps differ from frozen plan')
        results = {name: summary(docs, [item.rows[name] for item in evaluated], baseline_rows=local,
                                 contract_counts=[item.issues[name] for item in evaluated])
                   for name in METHODS if name not in references}
        write(output / 'selection-results.json', {'plan_sha256': plan['approval_sha256'],
              'results': references | results, 'doc_timing_ms': timing(doc_elapsed),
              'request_telemetry': telemetry, 'locked_after_usd': str(client.spent)})


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'run'))
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--approval', type=Path)
    args = parser.parse_args()
    if args.action == 'run' and not args.approval:
        parser.error('A separate exact-plan approval JSON is required for a paid run')
    docs, frames, local, partitions, splits, policy, references = selection()
    ledger = settlement(SHARED_CACHE)
    plan = build_plan(docs, frames, local, partitions, policy, ledger)
    if args.action == 'plan':
        args.output.mkdir(parents=True, exist_ok=True)
        write(args.output / 'selection-plan.json', plan)
        write(args.output / 'data-manifest.json', partitions)
        write(args.output / 'local-selection.json', references)
        for name, panel in splits.items():
            write(args.output / f'{name}.json', {'manifest': partitions[name], 'documents': panel})
        return
    if strict_json((args.output / 'selection-plan.json').read_bytes()) != plan:
        raise ValueError('Current code, data or ledger differ from the recorded plan')
    execute(plan, docs, frames, local, strict_json(args.approval.read_bytes()), references, args.output)


if __name__ == '__main__':
    main()
