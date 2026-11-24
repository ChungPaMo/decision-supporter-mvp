"""Research-only typed decisions, evidence packing and reranking."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from time import perf_counter

import numpy as np
from rapidfuzz.fuzz import ratio
from scipy.optimize import linear_sum_assignment

from contracts.mapping_knowledge import DESCRIPTIONS
from mapping_phase5_evidence import negative_roles, role_signal, soft_fit
from mapping_phase5_local import prepare_local, score
from mapping_research_data import norm


REVIEW_VERSION = 'typed-manufacturing-rank-v1'
STOCK = ('on_hand_qty', 'allocated_qty', 'available_qty')
QUANTITY = ('base_qty', 'qty_per', 'line_no', 'scrap_rate')
ROLES = {
    'on_hand_qty': ('physical', 'before holds', 'before deductions', 'inclusive of', 'current balance', '실물', '차감 전', '예약 포함', '실보유'),
    'allocated_qty': ('committed', 'already booked', 'already allocated', 'reserved units', 'picked reserved',
                      'held for', '기배정', '예약 물량', '이미 묶인'),
    'available_qty': ('after reservation', 'after reservations', 'after allocation', 'net available', 'pickable',
                      'left after', 'unreserved', 'free after', '차감 뒤', '차감 가용', '사용 가능', '배정 제외', '불출 가능'),
    'base_qty': ('reference output', 'base batch', 'nominal output', 'basis output', '기준 생산', '기준 산출', '배치 기준'),
    'qty_per': ('usage', 'material units used', 'per output', 'consumption', '투입 소모', '자재 소비', '자재 소요', '단위 산출당'),
    'line_no': ('sequence', 'ordinal', 'entry position', '순차', '순번'),
    'scrap_rate': ('wastage', 'loss', 'lost', 'scrap', '손실', '불량', '폐기'),
    'valid_from': ('starting', 'commencing', 'opening', 'begins', '시작', '개시'),
    'valid_to': ('expiry', 'expiration', 'ends', 'closing', '종료', '만료'),
    'period': ('month', 'monthly', '귀속', '연월', '월간'),
    'demand_qty': ('demand volume', 'demand qty', 'monthly units', 'forecast', '고객 필요', '수요량', '판매 소요'),
    'bom_id': ('bill of materials', 'composition specification', '조합표', '구성명세'),
    'component_id': ('component', 'ingredient row', '구성품', '하위', '부품'),
}
GROUPS = (STOCK, QUANTITY, ('valid_from', 'valid_to', 'period', 'as_of_date'),
          ('bom_id', 'product_id', 'material_id', 'component_id', 'item_id'))
FORMAT_REASONS = {'TYPE_INCOMPATIBLE', 'UNSUPPORTED_ENUM_VALUE', 'NON_POSITIVE_OR_FRACTIONAL_LINE_NUMBER',
                  'UNREGISTERED_OR_MIXED_UNIT', 'INVALID_CALENDAR_DATE', 'INVALID_MONTH_REPRESENTATION',
                  'DATE_MONTH_GRANULARITY', 'LOCALE_NEEDS_CONFIRMATION', 'UNSUPPORTED_QUANTITY_PRECISION',
                  'MIXED_OR_UNPARSEABLE_NUMBER', 'PERCENT_NEEDS_CONVERSION', 'NEGATIVE_QUANTITY',
                  'INVALID_OR_DATE_LIKE_IDENTIFIER', 'FRACTION_OUT_OF_RANGE', 'NON_DECIMAL_VALUES'}


@dataclass(frozen=True)
class Frame:
    item: object
    raw: np.ndarray
    schema: np.ndarray
    instance: np.ndarray
    cues: np.ndarray
    neighborhood: np.ndarray
    alias: np.ndarray
    candidates: np.ndarray
    semantic: np.ndarray
    ready: np.ndarray
    milliseconds: float


@dataclass(frozen=True)
class Proposal:
    fields: tuple
    rank: np.ndarray
    ready_rank: tuple
    semantic_target: tuple
    semantic_confidence: tuple
    target: tuple
    confidence: tuple
    margin: tuple
    state: tuple
    routed: int


class LearnedAliases:
    def __init__(self, training):
        observed = defaultdict(set)
        targets = defaultdict(set)
        for doc in training:
            for col in doc['columns']:
                handle = (doc['entity'], norm(col['header']))
                role = col.get('semantic', col['expected'])
                observed[(*handle, role)].add(doc['family'])
                targets[handle].add(role)
        self.entries = defaultdict(list)
        for (entity, header, role), families in observed.items():
            if role and len(families) >= 2 and len(targets[entity, header]) == 1:
                self.entries[entity, role].append(header)
        self.entries = {key: tuple(sorted(value)) for key, value in self.entries.items()}

    def get(self, entity, field, header):
        return max((ratio(norm(header), sample) / 100 for sample in self.entries.get((entity, field), ())), default=0.0)


def contrast(item, i):
    label = item.headers[i].display
    evidence = {field: float(role_signal(label, tokens)) for field, tokens in ROLES.items() if field in item.fields}
    if ('available_qty' in item.fields and role_signal(label, ('차감 후', '제외 후'))
            and role_signal(label, ('가용', '잔량', '가능'))):
        evidence['available_qty'] = 1.
    if evidence.get('available_qty') and not role_signal(label, ('already booked', 'reserved units', '기배정', '이미 묶인')):
        evidence['allocated_qty'] = 0.
    if evidence.get('allocated_qty') and role_signal(label, ('already booked', 'reserved units', '기배정', '이미 묶인')):
        evidence['available_qty'] = 0.
    if evidence.get('on_hand_qty') and role_signal(label, ('physical', '실물', '차감 전', 'inclusive of', '예약 포함')):
        evidence['allocated_qty'] = 0.
    for group in GROUPS:
        supported = [field for field in group if evidence.get(field)]
        if len(supported) == 1:
            for field in set(group) - set(supported):
                if field in item.fields:
                    evidence[field] = -.7
    return np.array([evidence.get(field, 0) for field in item.fields])


def build_frames(body, lexicon, generator, aliases):
    frames = []
    for doc in body:
        started = perf_counter()
        item = prepare_local(doc, lexicon)
        raw = score(generator, [item])[0]
        schema = item.features[:, :, [0, 1, 2, 3, 4, 7]]
        instance = item.features[:, :, [5, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]]
        cues = np.array([contrast(item, i) for i in range(len(item.headers))])
        peers = np.zeros_like(raw)
        for field in range(raw.shape[1]):
            anchors = np.where(cues[:, field] > .5)[0]
            if len(anchors) == 1:
                peers[:, field] = -.25
                peers[anchors[0], field] = .30
        candidates = np.argsort(-raw, axis=1, kind='stable')
        semantic = np.zeros_like(raw, dtype=bool)
        ready = np.equal(item.hard, None)
        for i, header in enumerate(item.headers):
            for j, field in enumerate(item.fields):
                reason = item.hard[i, j]
                incompatible = negative_roles(header.display)
                type_block_only = reason in FORMAT_REASONS
                semantic[i, j] = (reason is None or type_block_only) and not item.route_suspect
                if (field in {'demand_qty', 'period'} and incompatible
                        & {'PURCHASE_ORDER', 'RETURNS', 'PRODUCTION_ACTUAL', 'ORDER_EVENT', 'MONEY'}):
                    semantic[i, j] = ready[i, j] = False
        if item.route_suspect:
            ready[:] = False
        alias = np.array([[aliases.get(item.entity, field, column.display) for field in item.fields] for column in item.headers])
        frames.append(Frame(item, raw, schema, instance, cues, peers, alias, candidates, semantic, ready,
                            (perf_counter() - started) * 1000))
    return frames


def features(frame, mode):
    raw = frame.raw[:, :, None]
    edge = frame.cues[:, :, None]
    neighbor = np.stack((frame.neighborhood, frame.item.relations), axis=-1)
    alias = frame.alias[:, :, None]
    groups = {
        'point': (raw,), 'schema': (raw, frame.schema), 'instance': (raw, frame.instance),
        'typed': (raw, frame.schema, frame.instance),
        'contrast': (raw, frame.schema, frame.instance, edge),
        'neighbors': (raw, frame.schema, frame.instance, neighbor),
        'full': (raw, frame.schema, frame.instance, frame.item.role[:, :, None], alias),
        'negative': (raw, frame.schema, frame.instance, np.minimum(edge, 0)),
        'combined': (raw, frame.schema, frame.instance, edge, neighbor, alias),
        'without_alias': (raw, frame.schema, frame.instance, edge, neighbor),
        'without_type': (raw, frame.schema, edge, neighbor, alias),
    }
    return np.concatenate(groups[mode], axis=-1)


class Models:
    def __init__(self, frames, gold):
        from sklearn.linear_model import LogisticRegression

        self.models = {}
        labels = [np.array([[int(c.get('semantic', c['expected']) == field) for field in frame.item.fields]
                            for c in doc['columns']]) for frame, doc in zip(frames, gold, strict=True)]
        self.train_size = sum(a.size for a in labels)
        label = np.concatenate([a.ravel() for a in labels])
        for mode in ('point', 'schema', 'instance', 'typed', 'contrast', 'neighbors', 'full', 'negative', 'combined',
                     'without_alias', 'without_type'):
            rows = np.concatenate([features(frame, mode).reshape(-1, features(frame, mode).shape[-1]) for frame in frames])
            self.models[mode] = LogisticRegression(C=3., max_iter=400).fit(rows, label)
        pairs, pair_gold = [], []
        for frame, label in zip(frames, labels, strict=True):
            attrs = features(frame, 'combined')
            for i, row in enumerate(frame.candidates):
                choices = row[:min(5, len(row))]
                for j, k in combinations(choices, 2):
                    if label[i, j] != label[i, k]:
                        delta = attrs[i, j] - attrs[i, k]
                        pairs.extend([delta, -delta])
                        pair_gold.extend([label[i, j], label[i, k]])
        self.pair = LogisticRegression(C=2., max_iter=400, fit_intercept=False).fit(pairs, pair_gold)

    def predict(self, frame, mode):
        attrs = features(frame, mode)
        return self.models[mode].predict_proba(attrs.reshape(-1, attrs.shape[-1]))[:, 1].reshape(frame.raw.shape)

    def pairwise(self, frame, mask, absolute):
        attrs = features(frame, 'combined')
        result = np.zeros_like(absolute)
        for i, row in enumerate(mask):
            indices = np.flatnonzero(row)
            if len(indices) <= 1:
                result[i, indices] = absolute[i, indices]
                continue
            duel = list(combinations(indices, 2))
            scores = self.pair.predict_proba(np.array([attrs[i, a] - attrs[i, b] for a, b in duel]))[:, 1]
            for (a, b), p in zip(duel, scores, strict=True):
                result[i, a] += p
                result[i, b] += 1 - p
            result[i] = .68 * result[i] / (len(indices) - 1) + .32 * absolute[i]
        return result


def candidate_mask(frame, width):
    mask = np.zeros_like(frame.raw, dtype=bool)
    chosen = frame.candidates if width == 'all' else frame.candidates[:, :min(3 if width == 'expand' else width, frame.raw.shape[1])]
    np.put_along_axis(mask, chosen, True, axis=1)
    if width == 'expand':
        for i, row in enumerate(frame.cues):
            strong = np.flatnonzero((row >= 1.) & frame.semantic[i])
            if len(strong) == 1 and frame.raw[i, chosen[i, 0]] < .83:
                mask[i, strong[0]] = True
    return mask


def ordered(matrix, mask):
    return [tuple(int(j) for j in row if mask[i, j]) for i, row in enumerate(np.argsort(-matrix, axis=1, kind='stable'))]


def listwise(rows, ranking, absolute, assigned, indices):
    if not indices:
        return assigned
    fixed = {j for i, j in enumerate(assigned) if i not in indices and j is not None}
    m = ranking.shape[1]
    weights = np.full((len(indices), m + len(indices)), -1e6)
    for offset, i in enumerate(indices):
        weights[offset, m + offset] = 0
        for field in rows[i]:
            if field not in fixed and absolute[i, field] > .30:
                weights[offset, field] = ranking[i, field] - .28
    result = assigned.copy()
    _, selected = linear_sum_assignment(weights, maximize=True)
    for i, selected_field in zip(indices, selected, strict=True):
        result[i] = int(selected_field) if selected_field < m else None
    return result


def reconcile(assigned, absolute):
    groups = defaultdict(list)
    for i, field in enumerate(assigned):
        if field is not None:
            groups[field].append(i)
    for field, cols in groups.items():
        if len(cols) == 1:
            continue
        ranked = sorted(cols, key=lambda ix: (-absolute[ix, field], ix))
        keep = ranked[0] if absolute[ranked[0], field] - absolute[ranked[1], field] >= .06 else None
        for i in cols:
            if i != keep:
                assigned[i] = None
    return assigned


def group_drilldown(frame, matrix, mask):
    ranking = matrix.copy()
    for group in GROUPS:
        indices = [frame.item.fields.index(field) for field in group if field in frame.item.fields]
        if len(indices) < 2:
            continue
        strength = np.max(np.where(mask[:, indices], matrix[:, indices], 0.), axis=1)
        evidence = np.count_nonzero((frame.cues[:, indices] > 0).any(axis=0))
        # Roll up to the role group, then allow its stronger evidence only where the source itself supports the group.
        factor = min(1., evidence / len(indices)) * .08
        ranking[:, indices] = np.clip(matrix[:, indices] + factor * strength[:, None], 0, 1)
    return ranking


def typed_state(frame, row, candidate, certainty):
    if candidate is None or certainty < .60:
        return 'HOLD'
    if not frame.semantic[row, candidate]:
        return 'NON_MATCH'
    return 'MATCH' if frame.ready[row, candidate] else 'TRANSFORM_REQUIRED'


def propose(frame, model, mode, width, refine='none', *, pairwise=False, cached=None):
    cached = cached if cached is not None else {}
    def predict(key):
        if key == 'grouped':
            key = 'combined'
        if key not in cached:
            cached[key] = model.predict(frame, key)
        return cached[key]

    allowed = candidate_mask(frame, width)
    mask = allowed & frame.semantic
    absolute = predict(mode)
    if pairwise:
        ranking = model.pairwise(frame, mask, absolute)
    elif mode == 'grouped':
        ranking = group_drilldown(frame, absolute, mask)
    else:
        ranking = absolute
    all_rows = ordered(ranking, mask)
    semantic = [row[0] if row else None for row in all_rows]
    candidates = [tuple(j for j in row if frame.ready[i, j]) for i, row in enumerate(all_rows)]
    assigned = [row[0] if row and semantic[i] == row[0] else None for i, row in enumerate(candidates)]
    routed = []
    if refine == 'all':
        routed = [i for i, p in enumerate(assigned) if p is not None]
    elif refine == 'selective':
        schema = ordered(predict('schema'), mask)
        instance = ordered(predict('instance'), mask)
        duplicate = Counter(p for p in assigned if p is not None)
        for i, row in enumerate(candidates):
            if assigned[i] is None or len(row) < 2:
                continue
            close = abs(ranking[i, row[0]] - ranking[i, row[1]]) < .16
            if close and (schema[i][:1] != instance[i][:1] or duplicate[assigned[i]] > 1):
                routed.append(i)
    if routed:
        assigned = listwise(candidates, ranking, absolute, assigned, routed)
    before = assigned.copy()
    assigned = reconcile(assigned, absolute)
    confidence, margins, states = [], [], []
    for i, selected in enumerate(assigned):
        main = semantic[i]
        if selected is None:
            confidence.append(0.)
            margins.append(0.)
            state = typed_state(frame, i, main, absolute[i, main] if main is not None else 0.)
            states.append('TRANSFORM_REQUIRED' if state == 'TRANSFORM_REQUIRED'
                          else 'DUPLICATE' if before[i] is not None else 'HOLD')
            continue
        confidence.append(float(absolute[i, selected]))
        rival = max((ranking[i, index] for index in all_rows[i] if index != selected), default=0.)
        margins.append(float(ranking[i, selected] - rival))
        states.append('MATCH')
    return Proposal(frame.item.fields, np.array([list(row) + [-1] * (frame.raw.shape[1] - len(row)) for row in all_rows]),
                    tuple(candidates),
                    tuple(semantic), tuple(float(absolute[i, j]) if j is not None else 0. for i, j in enumerate(semantic)),
                    tuple(assigned), tuple(confidence), tuple(margins), tuple(states), len(routed))


def budgeted_evidence(frame, row, candidate_ids, *, limit=560):
    """Pack only reusable role contrast and local statistics, without sampled values."""
    if limit < 0:
        raise ValueError('Evidence limit must be nonnegative')
    header = frame.item.headers[row]
    nearby = {i for i in range(max(0, row - 2), min(len(frame.item.headers), row + 3)) if i != row}
    nodes = []
    for j in candidate_ids:
        field = frame.item.fields[j]
        nodes.append((3 + abs(frame.cues[row, j]), f'{field}: {DESCRIPTIONS[field]}'))
        for group in GROUPS:
            if field not in group:
                continue
            for rival in group:
                if rival != field and rival in frame.item.fields:
                    nodes.append((2., f'distinguish {field} / {rival} by role, date granularity or unit'))
        nodes.append((1.8, f'{field} format evidence={soft_fit(field, frame.item.observations[row]):.2f}'))
    nodes.extend((1.1, f'neighbor col {frame.item.headers[i].col} {frame.item.headers[i].display[:48]}')
                 for i in sorted(nearby))
    selected, size = [], 0
    for _, datum in sorted(nodes, key=lambda node: (-node[0], node[1])):
        length = len(datum.encode('utf-8'))
        if datum not in selected and size + length <= limit:
            selected.append(datum)
            size += length
    return {'source_id': str(header.col), 'evidence': selected, 'bytes': size}
