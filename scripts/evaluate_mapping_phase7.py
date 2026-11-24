"""Phase 7 runner for local LLMs and separately approved Solar research batches."""
import argparse
from collections import Counter
from contextlib import contextmanager
from decimal import Decimal
from hashlib import sha256
from itertools import product
import json
import os
from pathlib import Path
import socket
import subprocess
from time import perf_counter, sleep
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from evaluate_mapping_phase6 import DATA, setup
from evaluate_mapping_research import metrics, timing, write
from mapping_phase5_audit import settlement, transition
from mapping_phase5_data import OUT as PHASE5, write_frozen
from mapping_phase6_data import OUT as PHASE6, read_panel
from mapping_phase6_rank import build_frames
from mapping_phase7_data import manifest, panel
from mapping_phase7_llm import HOLD, MODELS, RECIPES, Study, train_examples
from mapping_research_data import canonical, sha
from mapping_research_remote import (APPROVED_CAP, CHAT, SHARED_CACHE, VAT, BudgetExceeded, PaidResearch,
                                     ProviderFailure, expected_cost, load_local_key, lock_paid_cache)


OUT = Path('.artifacts/mapping-research/phase7')
LOCAL = 'phase7-local-qwen'
RATES = {**CHAT, MODELS[2]: CHAT[MODELS[0]]}  # Preview reservation uses list price.
ENDPOINT = '/chat/completions'
MAX_BYTES, MAX_OUTPUT = 21_000, 1024
DEVELOPMENT = ('direct-v1', 'direct', 'matchmaker', 'jev-selective', 'context-full', 'context-dynamic',
               'mag-point', 'mag-pair', 'mag-list', 'mag-point-list', 'mag-permute', 'top5', 'generator-verifier')
STAGE_COUNTS = dict.fromkeys(RECIPES, 1) | dict.fromkeys(
    ('jev-selective', 'jev-always', 'jev-dynamic', 'mag-point-list', 'mag-pair', 'mag-permute',
     'generator-verifier', 'hold-recovery'), 2) | dict.fromkeys(('matchmaker', 'matchmaker-dynamic'), 3)
P7_FILES = ('mapping_phase7_llm.py', 'mapping_phase7_data.py', 'evaluate_mapping_phase7.py', 'mapping_phase7_optimizer.py')


def witness(docs):
    """Predeclared BOM and inventory panel for the limited local LLM stage comparison."""
    return [next(doc for doc in docs if doc['entity'] == entity and doc['document_type'] == entity)
            for entity in ('bom', 'inventory')]


def heldout_witness(docs):
    firsts = [doc for doc in docs if doc['id'].endswith('-2-0')]
    return [*firsts, next(doc for doc in docs if doc['entity'] == 'bom' and doc['id'].endswith('-2-1'))]


def recipes_for(name):
    if name == 'smoke':
        return ('direct', 'context-full', 'context-dynamic', 'jev-typed', 'mag-list')
    return RECIPES


def cost_limit(models, recipes, count):
    return call_envelope(models, count * sum(STAGE_COUNTS[recipe] for recipe in recipes), MAX_OUTPUT)


def call_envelope(models, calls, outputs):
    rows = {}
    for model in models:
        in_rate, out_rate = RATES[model]
        row = {'calls_max': calls, 'input_token_proxy_max': calls * (MAX_BYTES + 512),
               'output_tokens_max': calls * outputs}
        amount = VAT * (in_rate * row['input_token_proxy_max'] + out_rate * row['output_tokens_max']) / 1_000_000
        rows[model] = {**row, 'maximum_usd': str(amount)}
    return {'models': rows, 'calls_max': calls * len(models),
            'maximum_usd': str(sum(Decimal(row['maximum_usd']) for row in rows.values()))}


def approval_plan(documents, panel_sha, recipe_set, preview):
    specs = recipes_for(recipe_set)
    exact = recipe_set == 'smoke'
    budget = cost_limit(MODELS, specs, len(documents))
    if exact:
        by_model = {}
        for model in MODELS:
            records = [row for recipe in specs for row in preview[f'{model}/{recipe}']]
            by_model[model] = {'calls_max': len(records),
                'input_token_proxy_max': sum(row['wire_bytes'] + 512 for row in records),
                'output_tokens_max': sum(row['output_tokens'] for row in records),
                'maximum_usd': str(sum(Decimal(row['reserve_usd']) for row in records))}
        budget = {'models': by_model, 'calls_max': sum(row['calls_max'] for row in by_model.values()),
                  'maximum_usd': str(sum(Decimal(row['maximum_usd']) for row in by_model.values()))}
    signed = {'scope': 'PHASE7_FIXED_SYNTHETIC_DEVELOPMENT', 'data_sha256': panel_sha,
              'source_sha256': [doc['csv_sha256'] for doc in documents], 'model_ids': list(MODELS),
              'recipes': list(specs), 'budget': budget,
              'code_sha256': sha({name: sha256(Path(__file__).with_name(name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                  for name in P7_FILES}),
              'allowed_input': ['schema and business field definitions', 'synthetic title and header',
                                'up to 3 synthetic samples per column', 'derived profiles and relations', 'local candidate order']}
    if any(recipe.startswith('matchmaker') for recipe in specs):
        signed['allowed_input'].append('up to two fixed synthetic training examples per document')
    if exact:
        signed['request_sha256'] = {key: [row['wire_sha256'] for row in batch] for key, batch in preview.items()}
    return {**signed, 'approval_sha256': sha(signed)}


def dry_run_plan(models, recipes, docs, frames, development):
    preview = {}
    for model, recipe in product(models, recipes):
        payloads = []

        def record(stage):
            wire = stage.wire
            size = len(canonical(wire))
            if size > MAX_BYTES or wire['max_tokens'] > MAX_OUTPUT:
                raise BudgetExceeded('Prepared request exceeds the signed envelope')
            payloads.append({'stage': stage.name, 'wire_sha256': sha(wire),
                             'wire_bytes': size, 'output_tokens': wire['max_tokens'],
                             'reserve_usd': str(VAT * expected_cost(wire, RATES[model]))})
            # Exercise conditional stages without using scoring labels or contacting a model.
            tokens = {key: ('HIGH' if 'HIGH' in values else 'MATCH' if 'MATCH' in values else values[0])
                      for key, values in stage.allowed.items()}
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(tokens)}}]}

        for doc, frame in zip(docs, frames, strict=True):
            Study(doc, frame, model, record, train_examples(doc, development)).run(recipe)
        if len(payloads) > len(docs) * STAGE_COUNTS[recipe]:
            raise BudgetExceeded('Prepared request count exceeds the signed envelope')
        preview[f'{model}/{recipe}'] = payloads
    return preview


def valid_approval(expected, supplied, cache, budget):
    keys = ('approval_sha256', 'maximum_usd', 'training_examples_allowed')
    if set(supplied) != set(keys) or supplied['approval_sha256'] != expected['approval_sha256']:
        raise ValueError('Approval must identify the exact fixed synthetic plan')
    maximum = Decimal(supplied['maximum_usd'])
    needed = Decimal(expected['budget']['maximum_usd'])
    if (not maximum.is_finite() or not needed <= maximum <= budget or
            Decimal(settlement(cache)['headroom_usd']) < needed):
        raise BudgetExceeded('The approved plan must fit the current shared reservation headroom')
    has_examples = any(recipe.startswith('matchmaker') for recipe in expected['recipes'])
    if type(supplied['training_examples_allowed']) is not bool or (has_examples and not supplied['training_examples_allowed']):
        raise ValueError('Synthetic training demonstrations need explicit approval')


class MeteredTransport:
    def __init__(self, model, client, allowed_calls, signed_requests=()):
        self.model, self.client, self.remaining = model, client, allowed_calls
        self.signed_requests = Counter(signed_requests)
        self.static = bool(self.signed_requests)
        self.telemetry = []

    def __call__(self, stage):
        wire = stage.wire
        if (wire['model'] != self.model or len(canonical(wire)) > MAX_BYTES or
                wire['max_tokens'] > MAX_OUTPUT or self.remaining <= 0):
            raise BudgetExceeded('Phase 7 request exceeds the reviewed route bounds')
        fingerprint = sha(wire)
        if self.static and self.signed_requests[fingerprint] <= 0:
            raise ValueError('Wire request is outside the approved exact synthetic request set')
        self.signed_requests[fingerprint] -= 1
        self.remaining -= 1
        start = perf_counter()
        before = self.client.spent
        cached = self.client.cached_response(ENDPOINT, wire)
        if cached is not None:
            body = cached
        else:
            try:
                body = self.client.call(ENDPOINT, wire, RATES[self.model])
            except ProviderFailure:
                body = {}
        self.telemetry.append({'stage': stage.name, 'ms': (perf_counter() - start) * 1000,
                               'usage': body.get('usage', {}), 'cached': cached is not None,
                               'provider_failed': not body,
                               'charged_or_reserved_usd': str(self.client.spent - before)})
        return body


@contextmanager
def loopback(binary, model, output, threads):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    opener = build_opener(ProxyHandler({}))
    output.mkdir(parents=True, exist_ok=True)
    argv = [str(binary), '--model', str(model), '--alias', LOCAL, '--host', '127.0.0.1',
            '--port', str(port), '--n-gpu-layers', '0', '--threads', str(threads), '--parallel', '1',
            '--ctx-size', '8192', '--jinja', '--no-webui']
    with (output / 'local-phase7-server.log').open('wb') as log:
        process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            deadline = perf_counter() + 60
            while perf_counter() < deadline and process.poll() is None:
                try:
                    with opener.open(url + '/health', timeout=1):
                        break
                except (URLError, TimeoutError):
                    sleep(.2)
            else:
                raise RuntimeError('Loopback model did not start. See the ignored runtime log')

            def call(stage):
                wire = stage.wire | {'chat_template_kwargs': {'enable_thinking': False}, 'seed': 74}
                request = Request(url + '/v1' + ENDPOINT, data=canonical(wire), headers={'Content-Type': 'application/json'})
                try:
                    with opener.open(request, timeout=75) as response:
                        return json.load(response)
                except (URLError, TimeoutError, ValueError):
                    return {}
            yield call
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def measured(call):
    telemetry = []

    def invoke(stage):
        start = perf_counter()
        answer = call(stage)
        telemetry.append({'stage': stage.name, 'ms': (perf_counter() - start) * 1000,
                          'usage': answer.get('usage', {}), 'provider_failed': not answer})
        return answer
    return invoke, telemetry


def score_one(docs, frames, model, recipe, call, telemetry, development, local_rows):
    all_rows, issue_types, changed, kinds = [], Counter(), 0, Counter()
    document_times, semantic_ok, direct_candidates, eligible, transforms = [], 0, 0, 0, 0
    for doc, frame, baseline in zip(docs, frames, local_rows, strict=True):
        locked = {str(i): row['prediction'] for i, row in enumerate(baseline) if row['prediction']} if recipe == 'hold-recovery' else {}
        started = perf_counter()
        result = Study(doc, frame, model, call, train_examples(doc, development)).run(recipe, locked)
        document_times.append((perf_counter() - started) * 1000)
        issue_types.update(result.issues)
        kinds.update(result.stage_calls)
        changed += bool(+result.issues)
        out = []
        for i, col in enumerate(doc['columns']):
            key = str(i)
            prediction = result.direct.get(key)
            ranked = result.candidates.get(key, ())
            eligible += col['expected'] is not None
            direct_candidates += bool(col['expected'] and (col['expected'] in ranked or col['expected'] == locked.get(key)))
            semantic_ok += bool(col['semantic'] and result.semantic.get(key) == col['semantic'])
            transforms += bool(col['state'] == 'TRANSFORM_REQUIRED' and result.transforms.get(key) == col['semantic'])
            out.append({'prediction': prediction, 'top3': [prediction] if prediction else [], 'ranking': list(ranked)})
        all_rows.append(out)
    summary = metrics(docs, all_rows)
    summary.pop('case_counts')
    usage = Counter()
    for row in telemetry:
        for key in ('prompt_tokens', 'completion_tokens'):
            usage[key] += (row['usage'].get(key) or 0)
    return {'metrics': summary, 'delta_vs_phase6': transition(local_rows, all_rows, docs), 'semantic_correct': semantic_ok,
            'transform_correct': transforms, 'candidate_hits': direct_candidates, 'eligible': eligible,
            'contract_affected': changed, 'contract_issues': dict(+issue_types), 'stage_calls': dict(kinds),
            'provider_failures': sum(row['provider_failed'] for row in telemetry),
            'logged_tokens': dict(usage), 'request_timing_ms': timing([row['ms'] for row in telemetry]) if telemetry else None,
            'doc_timing_ms': timing(document_times), 'new_requests': sum(not row.get('cached', False) for row in telemetry),
            'cost_or_reserve_usd': str(sum((Decimal(row.get('charged_or_reserved_usd', '0')) for row in telemetry), Decimal(0)))}


def baselines(docs, ready, frozen):
    lexicon, generator, examples, aliases, scorer, provenance = ready
    frames = build_frames(docs, lexicon, generator, aliases)
    if provenance != frozen['provenance'] or frozen['sha256'] != sha({k: v for k, v in frozen.items() if k != 'sha256'}):
        raise ValueError('Reference Phase 6 policies or training provenance moved')
    from evaluate_mapping_phase6 import baseline as exact_rapid, prior_results, calculate
    from mapping_phase6_risk import make_predictions
    combos, _ = calculate(frames, scorer, (frozen['winner']['strategy'],))
    winner = frozen['winner']
    local = [make_predictions(p, winner['threshold'], winner['margin']) for p in combos[winner['strategy']]]
    variants = {'phase5': [prior_results(frame, examples) for frame in frames], 'phase6': local}
    variants['exact_rapid'] = [exact_rapid(frame.item) for frame in frames]
    reports = {name: {key: value for key, value in metrics(docs, rows).items() if key != 'case_counts'}
               for name, rows in variants.items()}
    return frames, local, reports


def freeze_local(report):
    """Select on Selection only. An all-HOLD policy cannot qualify for deployment."""
    rows = report['results']

    def qualifies(row):
        metric = row['metrics']
        return (metric['top1_recall'] >= .90 and metric['precision'] >= .98 and metric['wrong_rate'] <= .01
                and metric['hold_recall'] >= .98 and row['contract_affected'] <= .01 * metric['documents']
                and not row['provider_failures'])

    names = [name for name, item in rows.items() if qualifies(item)]
    exploratory = not names
    if exploratory:
        names = [name for name, row in rows.items() if row['metrics']['correct'] and not row['provider_failures']]
    if not names:
        raise ValueError('No nonempty local LLM comparison to freeze')

    def key(name):
        row = rows[name]
        return (-row['metrics']['wrong'], row['metrics']['correct'], -row['contract_affected'], -row['new_requests'])

    frozen = {'winner': max(names, key=key), 'selection_sha256': report['data_sha256'],
              'selection_report_sha256': sha(report), 'exploration_only': exploratory}
    return {**frozen, 'sha256': sha(frozen)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'baselines', 'local-development', 'freeze-local', 'local-holdout',
                                           'solar-development'))
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--phase6', type=Path, default=PHASE6 / 'verified')
    parser.add_argument('--phase5', type=Path, default=PHASE5 / 'verified')
    parser.add_argument('--data', type=Path, default=DATA)
    parser.add_argument('--llama', type=Path, default=Path('.artifacts/mapping-research/models/llama/llama-server.exe'))
    parser.add_argument('--weights', type=Path, default=Path('.artifacts/mapping-research/models/qwen25-15b/model.gguf'))
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--recipe-set', choices=('smoke', 'full'), default='smoke')
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    partitions = {split: read_panel(args.phase6, split) for split in ('development', 'selection', 'risk', 'holdout')}
    dev, dev_sha = partitions['development']
    fixed, digest = panel()
    info = manifest(fixed, digest, [row for docs, _ in partitions.values() for row in docs])
    write_frozen(args.output / 'independent-manifest.json', info)
    write_frozen(args.output / 'independent.json', {'sha256': digest, 'documents': fixed})
    solar_docs = witness(dev)
    phase6_paths = argparse.Namespace(output=args.phase6, phase5=args.phase5, data=args.data)
    if args.action == 'solar-development' and args.approval is None:
        parser.error('A separate approved plan file is required before sending synthetic data')
    if args.action in ('plan', 'solar-development'):
        from mapping_phase7_optimizer import MAX_CALLS
        ready = setup(phase6_paths)
        lexicon, generator, _, aliases, _, _ = ready
        preview = dry_run_plan(MODELS, recipes_for(args.recipe_set), solar_docs,
                               build_frames(solar_docs, lexicon, generator, aliases), dev)
        signed = approval_plan(solar_docs, dev_sha, args.recipe_set, preview)
        if args.action == 'plan':
            write(args.output / ('plan-' + args.recipe_set + '.json'), {'plan': signed, 'ledger': settlement(SHARED_CACHE),
                  'independent': info, 'full_20_doc_envelope': cost_limit(MODELS, RECIPES, 20),
                  'optimizer_envelope_mini': call_envelope((MODELS[0],), sum(MAX_CALLS.values()), 256),
                  'optimizer_envelope_all': call_envelope(MODELS, sum(MAX_CALLS.values()), 256), 'mock_wire_preview': preview})
            return
        valid_approval(signed, json.loads(args.approval.read_bytes()), SHARED_CACHE, APPROVED_CAP)
    if args.action == 'freeze-local':
        report = json.loads((args.output / 'local-development.json').read_bytes())
        if (set(report['results']) != set(DEVELOPMENT) or report['data_sha256'] != partitions['selection'][1]
                or report['documents'] != [doc['id'] for doc in witness(partitions['selection'][0])]):
            raise ValueError('The predetermined Selection comparison is incomplete or changed')
        write_frozen(args.output / 'local-winner.json', freeze_local(report))
        return
    if args.action != 'solar-development':
        ready = setup(phase6_paths)
    frozen = json.loads((args.phase6 / 'frozen-policy.json').read_bytes())
    if args.action == 'baselines':
        results = {name: baselines(docs, ready, frozen)[2] for name, docs in
                   [('independent', fixed), ('phase6_regression', partitions['holdout'][0])]}
        write(args.output / 'baseline-results.json', results)
    elif args.action.startswith('local-'):
        holdout = args.action == 'local-holdout'
        docs = heldout_witness(fixed) if holdout else witness(partitions['selection'][0])
        # Demos never use the test example or Selection/Risk labels.
        training = dev
        if holdout:
            policy = json.loads((args.output / 'local-winner.json').read_bytes())
            if policy['sha256'] != sha({k: v for k, v in policy.items() if k != 'sha256'}):
                raise ValueError('Local policy verification failed')
            if policy['selection_sha256'] != partitions['selection'][1]:
                raise ValueError('Local policy belongs to another Selection partition')
            recipes = ('direct-v1', policy['winner']) if policy['winner'] != 'direct-v1' else ('direct-v1',)
        else:
            recipes = DEVELOPMENT
        frames, local, reference = baselines(docs, ready, frozen)
        results = {}
        with loopback(args.llama, args.weights, args.output, args.threads) as offline:
            for recipe in recipes:
                call, log = measured(offline)
                results[recipe] = score_one(docs, frames, LOCAL, recipe, call, log, training, local)
                write(args.output / (args.action + '.json'), {'data_sha256': digest if holdout else partitions['selection'][1],
                      'documents': [doc['id'] for doc in docs], 'model': args.weights.name, 'model_id': LOCAL,
                      'reference': reference, 'results': results})
    else:
        frames, local, reference = baselines(solar_docs, ready, frozen)
        with lock_paid_cache(SHARED_CACHE):
            valid_approval(signed, json.loads(args.approval.read_bytes()), SHARED_CACHE, APPROVED_CAP)
            if not load_local_key():
                raise ValueError('Local Upstage credential is unavailable')
            paid = PaidResearch(SHARED_CACHE, APPROVED_CAP, approved=True)
            results = {}
            for model, recipe in product(MODELS, signed['recipes']):
                key = f'{model}/{recipe}'
                call = MeteredTransport(model, paid, len(solar_docs) * STAGE_COUNTS[recipe],
                                        signed.get('request_sha256', {}).get(key, ()))
                results[key] = score_one(solar_docs, frames, model, recipe, call, call.telemetry, dev, local)
                write(args.output / 'solar-development.json', {'plan': signed, 'reference': reference,
                      'results': results, 'ledger': settlement(SHARED_CACHE)})


if __name__ == '__main__':
    main()
