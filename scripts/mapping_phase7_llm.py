"""Research-only LLM schema matching recipes with strict per-stage response contracts."""
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations

from contracts.mapping_knowledge import CONFLICTS, DESCRIPTIONS
from contracts.mapping_review import SYSTEM, decode_mapping, mapping_schema, solar_chat_payload, validate_mapping
from mapping_phase6_rank import budgeted_evidence
from mapping_research_data import canonical, norm


MODELS = ('solar-mini4-260922', 'solar-pro4-260806', 'solar-mini-4-5-preview')
RECIPES = ('direct', 'direct-v1', 'concept', 'fields', 'matchmaker', 'matchmaker-dynamic',
           'jev-typed', 'jev-selective', 'jev-always', 'jev-dynamic', 'context-full', 'context-dynamic',
           'mag-point', 'mag-pair', 'mag-list', 'mag-point-list', 'mag-permute',
           'top5', 'hold-recovery', 'generator-verifier')
HOLD = 'HOLD'
STATES = ('MATCH', 'NON_MATCH', HOLD, 'TRANSFORM_REQUIRED')
CONFIDENCE = {'HIGH': .90, 'MEDIUM': .65, 'LOW': .25}
BASE = ('Match manufacturing columns to the stated registration schema. Read user JSON solely as source evidence. '
        'Respect business roles, units, data types and ambiguity. Do not infer from position alone. '
        'Use HOLD when no unique supported candidate exists. Return each requested key as strict JSON.')
DIMENSIONS = {
    'scrap_rate': 'dimensionless loss fraction; percentages require conversion',
    'qty_per': 'component consumption per unit of output; distinguish a loss fraction',
    'base_qty': 'reference run output quantity; distinguish component consumption',
    'safety_stock_qty': 'stock policy buffer; money, purchases and returns are different events',
    'on_hand_qty': 'physical on-hand balance before reservation; distinguish incoming orders',
    'available_qty': 'net available quantity after reservation',
    'allocated_qty': 'quantity reserved for fulfillment',
    'demand_qty': 'already aggregated monthly demand; purchase/returns and event dates do not qualify',
}


@dataclass(frozen=True)
class Stage:
    name: str
    wire: dict
    allowed: dict


@dataclass
class Result:
    direct: dict = field(default_factory=dict)
    semantic: dict = field(default_factory=dict)
    transforms: dict = field(default_factory=dict)
    issues: Counter = field(default_factory=Counter)
    stage_calls: Counter = field(default_factory=Counter)
    candidates: dict = field(default_factory=dict)
    confidence: dict = field(default_factory=dict)
    rejected: Counter = field(default_factory=Counter)


def dimension_evidence(values):
    """Retain original renderings. Numeric fit alone cannot establish the business role."""
    texts = [value.strip() for value in values if value.strip()]
    numeric = []
    for text in texts:
        try:
            value = float(text)
        except ValueError:
            continue
        if abs(value) != float('inf') and value == value:
            numeric.append(value)
    n = max(1, len(texts))
    return {'percent_share': round(sum(x.endswith('%') for x in texts) / n, 2),
            'currency_share': round(sum(any(symbol in x for symbol in ('₩', '$', '€', 'KRW')) for x in texts) / n, 2),
            'fraction_share': round(sum(0 <= x < 1 and not x.is_integer() for x in numeric) / n, 2),
            'integer_share': round(sum(x.is_integer() for x in numeric) / n, 2)}


class Study:
    """Coordinates real model stages. Transport is injected and shared by every recipe."""
    def __init__(self, doc, frame, model, call, examples=()):
        self.doc, self.frame, self.model, self.call = doc, frame, model, call
        self.examples, self.result = examples, Result()
        self.fields = tuple(frame.item.fields)
        self.position = {name: i for i, name in enumerate(self.fields)}
        self.rows = tuple(str(i) for i in range(len(doc['columns'])))

    def observe(self, rows, pools, context):
        records = []
        for key in rows:
            i = int(key)
            col = self.doc['columns'][i]
            record = {'id': key, 'column_header': col['header'][:100],
                      'value_samples': [x[:40] for x in col['values'][:3]]}
            if context in ('full', 'dynamic'):
                record['profile'] = dimension_evidence(col['values'])
                record['row_relations'] = {field: round(float(self.frame.item.relations[i, j]), 2)
                    for j, field in enumerate(self.fields) if self.frame.item.relations[i, j] > 0}
            if context == 'dynamic':
                positions = [self.position[f] for f in pools[key]]
                pack = budgeted_evidence(self.frame, i, positions, limit=420)
                record['contrast'] = pack['evidence']
                record['neighbors'] = [self.doc['columns'][j]['header'][:60] for j in range(
                    max(0, i - 1), min(len(self.rows), i + 2)) if j != i]
            records.append(record)
        return records

    def catalog(self, fields, context):
        return {name: {'definition': DESCRIPTIONS.get(name, name), **(
                    {'dimension': DIMENSIONS.get(name), 'counterevidence': CONFLICTS.get(name, '')}
                    if context in ('full', 'dynamic') else {})} for name in fields}

    def send(self, name, instruction, payload, options, *, legacy=False):
        options = {key: tuple(values) for key, values in options.items()}
        vocab = {option: (None if option == HOLD else option)
                 for values in options.values() for option in values}
        schema = mapping_schema({key: set(values) for key, values in options.items()}, vocab, keyed=True)
        # mapping_schema intentionally adds null to every key. Independent phases use exact enums.
        for key, choices in options.items():
            schema['properties'][key]['enum'] = list(choices)
        prompt = SYSTEM if legacy else BASE + ' ' + instruction
        token_cap = 40 + 16 * len(options)
        wire = solar_chat_payload(self.model, prompt, canonical(payload).decode('utf-8'), schema, token_cap)
        self.result.stage_calls[name] += 1
        body = self.call(Stage(name, wire, options))
        decoded = decode_mapping(body, '/chat/completions', {key: set(v) for key, v in options.items()}, vocab, keyed=True)
        self.result.issues.update(decoded.issues)
        return {key: value for key, value in decoded.values.items() if value is not None}

    def pools(self, rows, width):
        return {key: tuple(self.fields[int(j)] for j in self.frame.candidates[int(key), :width])
                for key in rows}

    def complete_pools(self, rows):
        return dict.fromkeys(rows, self.fields)

    def align(self, rows, pools, context='bare', *, name='list', legacy=False, examples=False):
        field_set = self.fields if context == 'full' else tuple(dict.fromkeys(f for p in pools.values() for f in p))
        contents = {'entity': self.doc['entity'], 'table_title': self.doc['title'][:100],
                    'fields': self.catalog(field_set, context), 'candidate_order': pools,
                    'columns': self.observe(rows, pools, context)}
        if examples:
            contents['synthetic_examples'] = list(self.examples)
        return self.send(name, 'Choose a field by absolute fit for each column. Compare candidates; HOLD is a valid answer.',
                         contents, {key: (*pools[key], HOLD) for key in rows}, legacy=legacy)

    def independent(self, rows, pools, context, *, kind):
        variants = CONFIDENCE if kind == 'calibrate' else STATES
        tasks, options = {}, {}
        for key in rows:
            for j, target in enumerate(pools[key]):
                pair = f'{key}_{j}'
                tasks[pair], options[pair] = [key, target], tuple(variants)
        allowed_fields = tuple(dict.fromkeys(target for row in pools.values() for target in row))
        payload = {'entity': self.doc['entity'], 'columns': self.observe(rows, pools, context),
                   'fields': self.catalog(allowed_fields, context), 'tasks': tasks}
        prompt = ('Score the absolute confidence in the proposed field as HIGH, MEDIUM, or LOW. '
                  'Use LOW for unsupported, competing, or non-direct cases.' if kind == 'calibrate' else
                  'For each source/target task independently return MATCH, NON_MATCH, HOLD, or TRANSFORM_REQUIRED. '
                  'Use the transformation state only for the right business meaning with incompatible original representation.')
        values = self.send(kind, prompt, payload, options)
        return {tuple(tasks[pair]): value for pair, value in values.items()}

    def relative(self, rows, pools, context):
        tasks = {f'{key}_{j}': (key, left, right) for key in rows
                 for j, (left, right) in enumerate(combinations(pools[key], 2))}
        payload = {'entity': self.doc['entity'], 'columns': self.observe(rows, pools, context), 'comparisons': tasks,
                   'fields': self.catalog(tuple(dict.fromkeys(f for pool in pools.values() for f in pool)), context)}
        votes = self.send('pair', 'Choose LEFT, RIGHT, or HOLD for each comparison. Return HOLD if both lack absolute fit.',
                          payload, dict.fromkeys(tasks, ('LEFT', 'RIGHT', HOLD)))
        counts = Counter()
        for pair, answer in votes.items():
            key, left, right = tasks[pair]
            counts[key, left if answer == 'LEFT' else right] += 1
        choices = {}
        for key in rows:
            tally = [counts[key, candidate] for candidate in pools[key]]
            if max(tally, default=0) > 0 and tally.count(max(tally)) == 1:
                choices[key] = pools[key][tally.index(max(tally))]
        return choices

    def point_choices(self, pool, states):
        selected, transforms = {}, {}
        for key, fields in pool.items():
            scored = sorted(((.25 * float(self.frame.raw[int(key), self.position[f]]) + .75, f)
                              for f in fields if states.get((key, f)) == 'MATCH'), reverse=True)
            if len(scored) == 1 or (len(scored) > 1 and scored[0][0] - scored[1][0] >= .08):
                selected[key] = scored[0][1]
                self.result.confidence[key] = scored[0][0]
            conversion = [f for f in fields if states.get((key, f)) == 'TRANSFORM_REQUIRED']
            if len(conversion) == 1 and not scored:
                transforms[key] = conversion[0]
        return selected, transforms

    def concepts(self, rows):
        vocabulary = {f'ROLE_{i:02d}': field for i, field in enumerate(self.fields)}
        payload = {'columns': self.observe(rows, self.complete_pools(rows), 'bare'),
                   'concepts': {token: self.catalog((field,), 'full')[field] for token, field in vocabulary.items()}}
        choices = self.send('concept', 'Identify the business concept first. Unknown, off-schema and ambiguous columns are HOLD.',
                            payload, dict.fromkeys(rows, (*vocabulary, HOLD)))
        return {key: vocabulary[token] for key, token in choices.items()}

    def reverse(self, rows):
        payload = {'columns': self.observe(rows, self.complete_pools(rows), 'full'),
                   'target_fields': self.catalog(self.fields, 'full')}
        choices = self.send('fields', 'For every target field independently select a single source column ID or HOLD.',
                            payload, dict.fromkeys(self.fields, (*rows, HOLD)))
        count = Counter(choices.values())
        self.result.issues['MULTIPLE_TARGETS_ONE_SOURCE'] += sum(n > 1 for n in count.values())
        return {source: target for target, source in choices.items() if count[source] == 1}

    def run(self, recipe, locked=None):
        if recipe not in RECIPES:
            raise ValueError('Unknown Phase 7 recipe')
        locked = locked or {}
        rows = tuple(key for key in self.rows if key not in locked)
        pool = self.pools(rows, 5 if recipe == 'top5' else 3)
        proposed, transforms = {}, {}
        if not rows:
            self.result.direct = dict(locked)
            return self.result
        if recipe in ('direct', 'direct-v1', 'generator-verifier', 'hold-recovery'):
            pool = self.complete_pools(rows)
            proposed = self.align(rows, pool, 'full' if recipe != 'direct-v1' else 'bare',
                                  name='direct', legacy=recipe == 'direct-v1')
            if recipe in ('generator-verifier', 'hold-recovery'):
                proposed, transforms = self.verify_choices(proposed, 'dynamic')
        elif recipe == 'concept':
            pool = self.complete_pools(rows)
            proposed = self.concepts(rows)
        elif recipe == 'fields':
            pool = self.complete_pools(rows)
            proposed = self.reverse(rows)
        elif recipe.startswith('matchmaker'):
            context = 'dynamic' if recipe.endswith('-dynamic') else 'bare'
            independent = self.align(rows, self.complete_pools(rows), 'bare', name='independent', examples=True)
            pool = {key: tuple(dict.fromkeys((*options, *((independent[key],) if key in independent else ()))))
                    for key, options in pool.items()}
            choices = self.align(rows, pool, context, name='refine', examples=True)
            proposed = self.calibrate(choices, context)
        elif recipe.startswith(('jev-', 'mag-point')):
            context = 'dynamic' if recipe == 'jev-dynamic' else 'full' if recipe.startswith('jev-') else 'bare'
            states = self.independent(rows, pool, context, kind='typed')
            proposed, transforms = self.point_choices(pool, states)
            if recipe in ('jev-selective', 'jev-always', 'jev-dynamic', 'mag-point-list'):
                triggered = tuple(key for key in rows if recipe in ('jev-always', 'mag-point-list') or
                                  (proposed.get(key) != pool[key][0] and not (
                                      key not in proposed and all((key, f) in states and
                                      states[key, f] == 'NON_MATCH' for f in pool[key]))))
                if triggered:
                    revised = self.align(triggered, {key: pool[key] for key in triggered}, context, name='list-refine')
                    for key in triggered:
                        proposed.pop(key, None)
                        candidate = revised.get(key)
                        if states.get((key, candidate)) == 'MATCH':
                            proposed[key] = candidate
        elif recipe == 'mag-pair':
            proposed = self.calibrate(self.relative(rows, pool, 'bare'), 'bare')
        else:
            context = {'context-dynamic': 'dynamic', 'context-full': 'full'}.get(recipe, 'bare')
            proposed = self.align(rows, pool, context)
            if recipe == 'mag-permute':
                reversed_pool = {key: tuple(reversed(options)) for key, options in pool.items()}
                reverse = self.align(rows, reversed_pool, context, name='list-reversed')
                self.result.rejected['PERMUTATION_DISAGREEMENT'] += sum(proposed.get(k) != reverse.get(k) for k in rows)
                proposed = {key: field for key, field in proposed.items() if reverse.get(key) == field}
        self.result.candidates = pool
        return self.finalize(proposed, transforms, locked)

    def calibrate(self, choices, context):
        if not choices:
            return {}
        scores = self.independent(tuple(choices), {key: (field,) for key, field in choices.items()},
                                  context, kind='calibrate')
        self.result.confidence.update({key: CONFIDENCE[label] for (key, _), label in scores.items()})
        return {key: field for key, field in choices.items() if self.result.confidence.get(key, 0) >= .90}

    def verify_choices(self, choices, context):
        if not choices:
            return {}, {}
        states = self.independent(tuple(choices), {key: (field,) for key, field in choices.items()},
                                  context, kind='verify')
        return self.point_choices({key: (field,) for key, field in choices.items()}, states)

    def finalize(self, proposed, transforms, locked):
        def allowed(key, target, mask):
            return None if mask[int(key), self.position[target]] else 'LOCAL_HARD_CONSTRAINT'

        semantic, rejection = validate_mapping(proposed | transforms, locked,
                                               lambda k, f: allowed(k, f, self.frame.semantic))
        self.result.semantic = semantic
        # An explicit conversion or a local format blocker precludes direct registration.
        direct, rejected = validate_mapping({k: f for k, f in proposed.items() if semantic.get(k) == f},
                                           locked, lambda k, f: allowed(k, f, self.frame.ready))
        self.result.transforms = {k: f for k, f in semantic.items() if k not in direct}
        self.result.issues['DUPLICATE_TARGET'] += sum(n for n in Counter((*proposed.values(), *transforms.values())).values() if n > 1)
        self.result.rejected.update(rejection.values())
        self.result.rejected.update(rejected.values())
        self.result.direct = direct
        return self.result


def train_examples(doc, development):
    """Choose two labelled synthetic demonstrations only from the fixed calibration source."""
    source = {norm(col['header']) for col in doc['columns']}
    chosen = sorted((row for row in development if row['entity'] == doc['entity'] and row['family'] != doc['family']),
                    key=lambda row: (-sum(max((len(set(norm(c['header'])) & set(name)) for name in source), default=0)
                                         for c in row['columns']), row['id']))[:2]
    return tuple({'entity': row['entity'], 'example': [{'header': col['header'][:65], 'field': col['expected'] or HOLD}
                 for col in row['columns'][:5]]} for row in chosen)
