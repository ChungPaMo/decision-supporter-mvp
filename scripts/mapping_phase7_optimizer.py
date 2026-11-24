"""Official DSPy/GEPA on a bounded transport, with fixtures for offline verification."""
import argparse
from collections import Counter
from importlib.metadata import version
import json
import os
from pathlib import Path

from contracts.mapping_review import decode_mapping, finished_text, mapping_schema, solar_chat_payload, strict_json
from mapping_research_data import canonical
from mapping_phase7_llm import DIMENSIONS, HOLD, MODELS, Stage


METHODS = ('existing', 'manual', 'dynamic', 'bootstrap', 'mipro', 'gepa', 'gepa-dynamic')
COMBINED = 'gepa-verifier'
MAX_CALLS = {'existing': 4, 'manual': 4, 'dynamic': 4, 'bootstrap': 12, 'mipro': 32, 'gepa': 26, 'gepa-dynamic': 26}
COMBINED_CALLS = MAX_CALLS['gepa'] + 2
MAX_METRIC = 16
INSTRUCTIONS = 'Map original columns to allowed fields. Return a JSON object of column ID to field or HOLD.'
MANUAL = INSTRUCTIONS + ' Use canonical units and business role. Ratios differ from component amounts. Avoid duplicate targets.'


def diagnostics(example, predicted):
    try:
        fields = strict_json(predicted) if isinstance(predicted, str) else predicted
    except (TypeError, ValueError):
        fields = None
    gold = strict_json(example.output)
    valid = strict_json(example.source)['fields']
    if not isinstance(fields, dict):
        return 0.0, {'FORMAT': 1}
    counts = Counter()
    counts['FORMAT'] = len(set(fields) ^ set(gold))
    safe = set(valid) | {HOLD}
    duplicates = Counter(val for val in fields.values() if isinstance(val, str) and val != HOLD)
    counts['DUPLICATE'] = sum(n for n in duplicates.values() if n > 1)
    for key, target in gold.items():
        guess = fields.get(key)
        if not isinstance(guess, str) or guess not in safe:
            counts['FORMAT'] += 1
        elif guess != target:
            counts['OVER_HOLD' if guess == HOLD else 'FALSE_RECOMMENDATION' if target == HOLD else 'WRONG_ROLE'] += 1
    penalties = {'FORMAT': 2.0, 'DUPLICATE': 2.0, 'WRONG_ROLE': 1.5, 'FALSE_RECOMMENDATION': 1.5, 'OVER_HOLD': 1.0}
    score = 1.0 / (1.0 + sum(penalties[key] * n for key, n in counts.items()))
    return score, dict(+counts)


class OptimizerTransport:
    """Counts and bounds optimizer, teacher, proposer, and reflection calls together."""
    def __init__(self, call, model, maximum_calls):
        if model in MODELS:
            from evaluate_mapping_phase7 import MeteredTransport
            if not isinstance(call, MeteredTransport):
                raise ValueError('Paid optimizer calls require the shared research ledger transport')
        self.call, self.model, self.remaining = call, model, maximum_calls
        self.calls = Counter()
        self.exhausted = False

    def run(self, messages):
        if not isinstance(messages, list) or any(set(m) != {'role', 'content'} or not isinstance(m['content'], str)
                or m['role'] not in ('system', 'user', 'assistant') for m in messages):
            raise ValueError('Unsupported optimizer message contract')
        wire = {'model': self.model, 'temperature': 0, 'max_tokens': 256, 'messages': messages}
        stage = 'task' if '[[ ## output ## ]]' in messages[0]['content'] else 'prompt-or-reflection'
        answer, failure = finished_text(self.invoke(wire, stage), '/chat/completions')
        if failure or not isinstance(answer, str):
            raise ValueError('Unusable optimizer response')
        return [answer]

    def invoke(self, wire, stage, allowed=None):
        if self.remaining <= 0:
            self.exhausted = True
            raise RuntimeError('Phase 7 optimizer call budget exhausted')
        from evaluate_mapping_phase7 import MAX_BYTES
        if len(canonical(wire)) > MAX_BYTES:
            raise ValueError('Optimizer request exceeds its approved input envelope')
        self.remaining -= 1
        self.calls[stage] += 1
        return self.call(Stage('dspy-' + stage, wire, allowed or {}))

    def verify(self, source, output):
        data = strict_json(source)
        guesses = strict_json(output)
        if not isinstance(guesses, dict):
            raise ValueError('Invalid optimized mapping')
        valid_ids = {str(col['id']) for col in data['columns']}
        counts = Counter(value for value in guesses.values() if isinstance(value, str))
        proposed = {i: value for i, value in guesses.items() if i in valid_ids and isinstance(value, str)
                    and value in data['fields'] and counts[value] == 1}
        safe = dict.fromkeys(sorted(valid_ids), HOLD)
        if proposed:
            decisions = {'MATCH': 'MATCH', 'HOLD': None}
            allowed = {key: {'MATCH'} for key in proposed}
            schema = mapping_schema(allowed, decisions, keyed=True)
            payload = canonical({'source': data, 'proposed': proposed}).decode('utf-8')
            wire = solar_chat_payload(self.model, 'Judge each proposed match independently. Confirm only direct matches. '
                                      'Reject ambiguous roles, wrong units and any needed conversion.', payload, schema, 128)
            verified = decode_mapping(self.invoke(wire, 'independent-verifier', allowed), '/chat/completions',
                                      allowed, decisions, keyed=True)
            safe.update({key: proposed[key] for key, value in verified.values.items() if value == 'MATCH'})
        return json.dumps(safe)


def framework():
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'true'
    os.environ['LITELLM_TELEMETRY'] = 'false'
    os.environ['DSPY_CACHEDIR'] = str(Path('.artifacts/mapping-research/phase7/dspy-cache').resolve())
    import dspy
    return dspy


def run_method(method, train, development, evaluation, transport):
    """Train and Development compile the prompt. Evaluation labels are only used by the scorer."""
    dspy = framework()
    if method not in (*METHODS, COMBINED):
        raise ValueError('Unknown optimizer')
    if not train or not development or not evaluation:
        raise ValueError('Optimizer partitions must be nonempty')
    scopes = (set(row['id'] for row in part) for part in (train, development, evaluation))
    t, d, e = scopes
    if t & d or t & e or d & e:
        raise ValueError('Optimizer partitions overlap')

    class LM(dspy.BaseLM):
        def __init__(self):
            super().__init__(transport.model, temperature=0, max_tokens=256, cache=False)

        def __call__(self, prompt=None, messages=None, **kwargs):
            return transport.run(messages if messages is not None else [{'role': 'user', 'content': prompt}])

    lm = LM()
    task = dspy.Signature('source: str -> output: str', INSTRUCTIONS if method == 'existing' else MANUAL)

    def rows(data):
        return [dspy.Example(source=json.dumps(r['source'], ensure_ascii=False),
                             output=json.dumps(r['output'], ensure_ascii=False)).with_inputs('source') for r in data]

    tr, dev, ev = map(rows, (train, development, evaluation))

    def score(example, pred, trace=None):
        value, issues = diagnostics(example, getattr(pred, 'output', None))
        return value == 1 if trace is not None else value

    def feedback(example, pred, trace=None, pred_name=None, pred_trace=None):
        value, issues = diagnostics(example, getattr(pred, 'output', None))
        return dspy.Prediction(score=value, feedback='Issue counts by type: ' + json.dumps(issues, sort_keys=True))

    def example_tokens(example):
        parsed = json.loads(example.source)
        combined = ' '.join(col['header'].lower() for col in parsed['columns'])
        return set(combined.split())

    class Program(dspy.Module):
        def __init__(self):
            super().__init__()
            self.map_fields = dspy.Predict(task, lm=lm)

        def forward(self, source):
            if method in ('dynamic', 'gepa-dynamic'):
                words = example_tokens(dspy.Example(source=source))
                sample = max(tr, key=lambda ex: len(words & example_tokens(ex)))
                source_data = json.loads(source)
                source = json.dumps({'document': source_data, 'training_example': {
                    'source': json.loads(sample.source), 'answer': json.loads(sample.output)}}, ensure_ascii=False)
            return self.map_fields(source=source)

    student = Program()
    with dspy.context(lm=lm, adapter=dspy.ChatAdapter(), disable_history=True, track_usage=False):
        # DSPy may call the adapter twice per evaluation. Hold back this allowance
        # so optimization failures cannot silently consume the paired comparison.
        uses_compiler = method in ('bootstrap', 'mipro') or method.startswith('gepa')
        holdback = len(ev) * (5 if method == COMBINED else 4) if uses_compiler else 0
        if uses_compiler and transport.remaining <= holdback:
            raise ValueError('No optimization calls remain after reserving paired evaluations')
        transport.remaining -= holdback
        try:
            if method == 'bootstrap':
                student = dspy.BootstrapFewShot(metric=score, max_bootstrapped_demos=1, max_labeled_demos=1,
                                               max_rounds=1, max_errors=1).compile(student, trainset=tr)
            elif method == 'mipro':
                student = dspy.MIPROv2(metric=score, task_model=lm, prompt_model=lm, auto=None, num_candidates=2,
                    max_bootstrapped_demos=0, max_labeled_demos=0, num_threads=1, max_errors=1, seed=7, track_stats=False
                    ).compile(student, trainset=tr, valset=dev, num_trials=2, minibatch=False,
                              program_aware_proposer=False, data_aware_proposer=False, fewshot_aware_proposer=False,
                              tip_aware_proposer=False)
            elif method.startswith('gepa'):
                student = dspy.GEPA(metric=feedback, reflection_lm=lm, max_metric_calls=MAX_METRIC,
                                    reflection_minibatch_size=2, use_merge=False, skip_perfect_score=False,
                                    num_threads=1, seed=7).compile(student, trainset=tr, valset=dev)
        finally:
            transport.remaining += holdback
        before, after = Counter(), Counter()
        before_score, after_score = [], []
        seed_program = Program()
        for example in ev:
            try:
                value, issues = diagnostics(example, seed_program(**example.inputs()).output)
            except (ValueError, RuntimeError):
                value, issues = 0.0, {'FORMAT': 1}
            before.update(issues)
            before_score.append(value)
        for example in ev:
            try:
                prediction = student(**example.inputs()).output
                if method == COMBINED:
                    prediction = transport.verify(example.source, prediction)
                value, issues = diagnostics(example, prediction)
            except (ValueError, RuntimeError):
                value, issues = 0.0, {'FORMAT': 1}
            after.update(issues)
            after_score.append(value)
    return {'method': method, 'before': dict(+before), 'after': dict(+after),
            'before_score': sum(before_score) / len(ev), 'after_score': sum(after_score) / len(ev),
            'calls': dict(transport.calls), 'evaluated': len(ev), 'budget_exhausted': transport.exhausted}


def check_fixture():
    """Known answers exercise compiler and transport plumbing, not model quality."""
    def row(i):
        return {'id': str(i), 'source': {'columns': [{'header': 'loss fraction', 'id': '0'}],
                'fields': DIMENSIONS}, 'output': {'0': 'scrap_rate'}}

    def mock(stage):
        if stage.name == 'dspy-independent-verifier':
            output = '{"0":"MATCH"}'
        elif stage.name == 'dspy-task':
            output = '[[ ## output ## ]]\n{"0":"scrap_rate"}\n[[ ## completed ## ]]'
        elif any('proposed_instruction' in message['content'] for message in stage.wire['messages']):
            output = '[[ ## proposed_instruction ## ]]\nVerify the dimension and keep one destination.\n[[ ## completed ## ]]'
        else:
            output = 'Verify role and fraction before recommending.'
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': output}}]}

    return {method: run_method(method, [row(1), row(2)], [row(3), row(4)], [row(5)],
                               OptimizerTransport(mock, 'fixture', MAX_CALLS.get(method, COMBINED_CALLS)))
            for method in (*METHODS, COMBINED)}


def source_examples(documents):
    from contracts.mapping_knowledge import DESCRIPTIONS
    from mapping_research_features import CATALOG
    result = []
    for doc in documents:
        roles = {'qty_per', 'scrap_rate'} if doc['entity'] == 'bom' else {'allocated_qty', 'available_qty', 'on_hand_qty'}
        chosen = [col for col in doc['columns'] if col['expected'] in roles][:2]
        chosen += [col for col in doc['columns'] if col.get('state', HOLD if col['expected'] is None else '') == HOLD][:1]
        candidates = {field: DESCRIPTIONS.get(field, field) + ' ' + DIMENSIONS.get(field, '')
                      for field in CATALOG[doc['entity']]}
        result.append({'id': doc['id'], 'source': {'fields': candidates, 'columns': [
            {'id': str(i), 'header': col['header'], 'samples': col['values'][:2]} for i, col in enumerate(chosen)]},
            'output': {str(i): col['expected'] or HOLD for i, col in enumerate(chosen)}})
    return result


def local_optimizers(args):
    from evaluate_mapping_phase7 import LOCAL, loopback, measured, witness
    from evaluate_mapping_research import write
    from mapping_phase6_data import read_panel
    from mapping_research_data import load_frozen
    train, tr_sha = load_frozen(args.data, 'train')
    development, dev_sha = read_panel(args.phase6, 'development')
    selection, select_sha = read_panel(args.phase6, 'selection')
    tr, dev, ev = (source_examples(witness(documents)) for documents in (train, development, selection))
    results = {}
    with loopback(args.llama, args.weights, args.output, args.threads) as offline:
        for method in (args.methods or METHODS):
            call, telemetry = measured(offline)
            transport = OptimizerTransport(call, LOCAL, MAX_CALLS.get(method, COMBINED_CALLS))
            try:
                results[method] = run_method(method, tr, dev, ev, transport)
                results[method]['status'] = 'CALL_BUDGET' if transport.exhausted else 'MEASURED'
            except (RuntimeError, ValueError) as exc:
                results[method] = {'status': 'CALL_BUDGET' if transport.exhausted else 'FAILED',
                                   'error_type': type(exc).__name__, 'calls': dict(transport.calls)}
            results[method]['provider_failures'] = sum(row['provider_failed'] for row in telemetry)
            results[method]['usage'] = {kind: sum((row['usage'].get(kind) or 0) for row in telemetry)
                                        for kind in ('prompt_tokens', 'completion_tokens')}
            write(args.output / 'optimizer-local.json', {'train_sha': tr_sha, 'development_sha': dev_sha,
                    'selection_sha': select_sha, 'optimizer': {'dspy': version('dspy'), 'gepa': version('gepa')},
                    'results': results})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--mock', action='store_true')
    action.add_argument('--local', action='store_true')
    parser.add_argument('--methods', nargs='+', choices=(*METHODS, COMBINED))
    parser.add_argument('--data', type=Path, default=Path('.artifacts/mapping-research/data'))
    parser.add_argument('--phase6', type=Path, default=Path('.artifacts/mapping-research/phase6/verified'))
    parser.add_argument('--output', type=Path, default=Path('.artifacts/mapping-research/phase7/optimizer-local'))
    parser.add_argument('--llama', type=Path, default=Path('.artifacts/mapping-research/models/llama/llama-server.exe'))
    parser.add_argument('--weights', type=Path, default=Path('.artifacts/mapping-research/models/qwen25-15b/model.gguf'))
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    if args.mock:
        print(json.dumps({'dspy': version('dspy'), 'gepa': version('gepa'), 'transport': 'mock',
                          'results': check_fixture()}, indent=2))
    else:
        local_optimizers(args)
