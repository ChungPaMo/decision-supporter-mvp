"""Manufacturing mapping features and one-to-one assignment, separate from runtime API."""
from collections import Counter
from functools import lru_cache
from itertools import permutations
import math
import re
from time import perf_counter

import numpy as np
from scipy.optimize import linear_sum_assignment

from mapping_research_data import csv_bytes, norm, target_catalog
from app.ingest.mapping import map_sheet
from app.ingest.profiling import parse_analysis_file, profile
from app.ingest.recommendation import compatible, lexical_similarity, recommend


CATALOG = target_catalog()
STRING = slice(0, 4)
PROFILE = slice(4, 23)
DOMAIN = slice(23, 26)
RELATION = 26
BUSINESS_WORDS = {
    'demand_qty': '수요 필요 소요 주문 customer demand requirement requested consumption',
    'allocated_qty': '예약 배정 묶인 allocated reserved committed held',
    'available_qty': '가용 가능 잔여 free unreserved available',
    'on_hand_qty': '현재고 실물 보유 실사 total physical onhand tally',
    'qty_per': '투입 소모 소요 component usage ingredient factor',
    'base_qty': '기준 환산 산출 reference denominator output batch',
    'valid_from': '시작 개시 시행 첫날 start first opens begins',
    'valid_to': '종료 만료 폐지 마지막날 end last expires closes',
    'period': '귀속 연월 월간 월별 bucket monthly period month',
    'scrap_rate': '손실 폐기 비중 loss scrap fraction share waste',
}
CONFLICTS = {
    'demand_qty': '반품 반송 되돌려 환입 생산 공장실적 구매 발주 공급 출고 물류 return refund reverse production manufacture procurement supplier vendor shipment dispatched',
    'period': '주문일 접수 출고 배송 booked placed shipping submission',
    'on_hand_qty': '예약제외 unreserved free',
    'allocated_qty': '미할당 예약제외 unreserved free',
    'available_qty': '차감전 includingreserved physicaltotal',
}
TYPE_EXPECTATIONS = {
    'number': 0, 'money': 8, 'date': 4, 'month': 5, 'unit': 6, 'bool': 15, 'status': 16, 'version': 17,
    'category': 14, 'name': 18, 'product_code': 9, 'material_code': 10, 'stock_code': 3, 'generic_code': 3,
}


def bounded_number(s):
    try:
        result = float(s.replace(',', ''))
        return result if math.isfinite(result) else None
    except ValueError:
        return None


def stats(values, known=None):
    n = max(len(values), 1)
    filled = [value for value in values if value]
    size = max(len(filled), 1)
    counts = Counter(filled)
    raw = [bounded_number(s) for s in filled]
    numbers = [v for v in raw if v is not None]
    lengths = [len(s) for s in filled] or [0]
    if known is None:
        from app.ingest.profiling import value_formats
        formats = list(map(value_formats, filled))
        code = sum(bool(row[1]) for row in formats) / size
        dates = sum(bool(row[2] and row[2].endswith('_DATE')) for row in formats) / size
        months = sum(bool(row[2] and row[2].endswith('_MONTH')) for row in formats) / size
        units = sum(bool(row[3]) for row in formats) / size
    else:
        code = known.format_match_rates['CODE']
        dates = sum(v for k, v in known.date_formats.items() if k.endswith('_DATE')) / size
        months = sum(v for k, v in known.date_formats.items() if k.endswith('_MONTH')) / size
        units = sum(s in known.unit_candidates for s in filled) / size
    ratio = lambda predicate: sum(bool(predicate(s)) for s in filled) / size
    magnitude = math.log1p(max(map(abs, numbers), default=0)) / 14
    trend = sum(y >= x for x, y in zip(numbers, numbers[1:])) / max(len(numbers) - 1, 1)
    return np.array([
        len(numbers) / size, sum(v.is_integer() for v in numbers) / size, sum(v < 0 for v in numbers) / size,
        code, dates, months, units, 1 - len(filled) / n, ratio(lambda s: s[0] in '$₩€'),
        ratio(lambda s: s.startswith(('FG-', 'SKU-'))), ratio(lambda s: s.startswith(('RM-', 'MAT-'))),
        len(counts) / size, magnitude, sum(-c/size * math.log(c/size) for c in counts.values()) / math.log(max(n, 2)),
        ratio(lambda s: s in ('MATERIAL', 'PRODUCT', 'FINISHED')), ratio(lambda s: s in ('Y', 'N', 'TRUE', 'FALSE')),
        ratio(lambda s: s in ('APPROVED', 'DRAFT')), ratio(lambda s: re.fullmatch(r'V\d+', s)),
        min(sum(lengths) / size / 24, 1), trend, min(len(numbers) / size * (max(numbers, default=0) <= 1), 1),
    ], dtype=np.float32)


def ngrams(text):
    chars = '^' + norm(text) + '$'
    return Counter(chars[i:i + n] for n in (2, 3) for i in range(len(chars) - n + 1))


class Lexicon:
    def __init__(self, catalog):
        self.text = {(entity, field): spec['aliases'] for entity, fields in catalog.items() for field, spec in fields.items()}
        counters = [ngrams(alias) for aliases in self.text.values() for alias in aliases]
        self.document_freq = Counter(term for row in counters for term in row)
        self.n = len(counters)
        self.avgdl = sum(map(lambda counter: sum(counter.values()), counters)) / self.n

    @lru_cache(maxsize=2048)
    def score(self, header, entity, field):
        words = self.text[entity, field]
        query = ngrams(header)
        idf = lambda t: math.log1p(self.n / (1 + self.document_freq[t]))
        qnorm = math.sqrt(sum((count * idf(t))**2 for t, count in query.items()))
        cosine, bm25 = 0.0, 0.0
        bound = sum(idf(t) for t in query) or 1
        for word in words:
            doc = ngrams(word)
            both = query.keys() & doc.keys()
            length = sum(doc.values())
            dnorm = math.sqrt(sum((count * idf(t))**2 for t, count in doc.items()))
            cosine = max(cosine, sum(query[t] * doc[t] * idf(t)**2 for t in both) / (qnorm * dnorm or 1))
            bm25 = max(bm25, sum(idf(t) * 2.2 * doc[t] / (doc[t] + 1.2 * (.25 + .75 * length / self.avgdl)) for t in both) / bound)
        return float(norm(header) in set(map(norm, words))), lexical_similarity([norm(header)], list(map(norm, words))), cosine, bm25


def profile_fit(values, target_kind):
    if target_kind == 'ratio':
        return float(values[20])
    if target_kind == 'name':
        return float(values[18] * (1 - max(values[:1].tolist() + values[4:7].tolist() + values[14:18].tolist())))
    if target_kind in ('product_code', 'material_code'):
        return float(.45 * values[3] + .55 * values[TYPE_EXPECTATIONS[target_kind]])
    return float(values[TYPE_EXPECTATIONS[target_kind]])


def inventory_votes(columns):
    votes = np.zeros((len(columns), 3))
    numeric = [[bounded_number(s) for s in col['values']] for col in columns]
    eligible = [i for i, v in enumerate(numeric) if sum(x is not None for x in v) >= 8]
    for i, j, k in permutations(eligible, 3):
        triplets = [(a, b, c) for a, b, c in zip(numeric[i], numeric[j], numeric[k]) if None not in (a, b, c)]
        if len(triplets) >= 8:
            score = sum(a > b > 0 and c > 0 and abs(a - b - c) <= .02 for a, b, c in triplets) / len(triplets)
            if score >= .9:
                votes[i, 0] = votes[j, 1] = votes[k, 2] = max(score, votes[i, 0], votes[j, 1], votes[k, 2])
    return votes


def word_signal(header, words):
    text = norm(header)
    return any(norm(term) in text for term in words.split())


def allowed_shape(kind, values):
    if kind in ('number', 'ratio', 'date', 'month', 'unit', 'bool', 'status', 'version'):
        return profile_fit(values, kind) >= .80
    if kind.endswith('_code'):
        return values[3] >= .75 and max(values[4:7]) < .90
    return values[0] < .80 and max(values[4:7]) < .90


def prepare(doc, lexicon, prototypes):
    """Features use only the unlabelled source columns, title and proposed schema."""
    start = perf_counter()
    entity, columns = doc['entity'], doc['columns']
    catalog = CATALOG[entity]
    fields = tuple(catalog)
    parsed = parse_analysis_file('synthetic.csv', csv_bytes(doc))
    profiled = profile(parsed, 'TISSUE-LEGACY').sheets[0].columns
    base_start = perf_counter()
    exact = map_sheet(parsed.sheets[0], entity=entity).fields
    exact_ms = (perf_counter() - base_start) * 1000
    base_start = perf_counter()
    rapid = recommend(parsed, entity, 'TISSUE-LEGACY').sheets[0].suggestions
    rapid_ms = (perf_counter() - base_start) * 1000
    baseline = [[c.target_field for c in column.suggestions] for column in rapid]
    counts = Counter(norm(c['header']) for c in columns)
    triad = ('on_hand_qty', 'allocated_qty', 'available_qty')
    relations = inventory_votes(columns) if entity == 'inventory' else np.zeros((len(columns), 3))
    raw_profiles = [stats(col['values'], summary) for col, summary in zip(columns, profiled, strict=True)]
    matrix, eligible = [], []
    for i, (col, summary, values) in enumerate(zip(columns, profiled, raw_profiles, strict=True)):
        hdr, sample = col['header'], stats(col['values'][:3])
        vicinity = np.mean(raw_profiles[max(0, i-2):i] + raw_profiles[i+1:i+3], axis=0) if len(columns) > 1 else values
        cells, allowed = [], []
        for f, spec in catalog.items():
            words = BUSINESS_WORDS.get(f, '')
            title = bool(words and word_signal(doc['title'], words))
            conflict = word_signal(hdr, CONFLICTS.get(f, ''))
            proof = relations[i, triad.index(f)] if f in triad else 0
            kind = spec['kind']
            reference = prototypes.get((entity, f))
            similarity = 1 - float(np.mean(np.abs(values - reference))) if reference is not None else 0
            cells.append((*lexicon.score(hdr, entity, f), profile_fit(values, kind), profile_fit(sample, kind), similarity,
                          *values[[0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 18, 19]],
                          profile_fit(vicinity, kind), float(bool(summary.unit_candidates)), float(word_signal(hdr, words)),
                          float(conflict), float(title), proof))
            allowed.append(counts[norm(hdr)] == 1 and compatible(f, hdr, summary)[0] and allowed_shape(kind, values))
        matrix.append(cells)
        eligible.append(allowed)
    assert len(columns) == len(matrix) == len(baseline)
    return {'id': doc['id'], 'family': doc['family'], 'entity': entity, 'fields': fields,
            'headers': [column['header'] for column in columns], 'features': np.asarray(matrix, dtype=np.float32),
            'allowed': np.asarray(eligible, dtype=bool), 'rapid': baseline, 'exact_ms': exact_ms, 'rapid_ms': rapid_ms,
            'exact': [[field for field, evidence in exact.items() if evidence.col == i + 1] for i in range(len(columns))],
            'elapsed_ms': (perf_counter() - start) * 1000}


def train_prototypes(documents):
    by_field = {}
    for doc in documents:
        for col in doc['columns']:
            if col['expected'] is not None:
                by_field.setdefault((doc['entity'], col['expected']), []).append(stats(col['values']))
    return {key: np.median(rows, axis=0) for key, rows in by_field.items()}


def abstain(scores, allowed, threshold, margin, strategy='independent'):
    scores = np.asarray(scores, dtype=float)
    if scores.shape != allowed.shape or np.any(~np.isfinite(scores)):
        raise ValueError('Score matrix must be finite and aligned')
    rows, fields = scores.shape
    eligible = np.where(allowed, scores, -np.inf)
    rank = np.argsort(-eligible, axis=1, kind='stable')
    selections = [None] * rows
    ordering = [[int(j) for j in order if allowed[i, j]] for i, order in enumerate(rank)]
    for i, order in enumerate(ordering):
        if not order:
            continue
        first = scores[i, order[0]]
        second = scores[i, order[1]] if len(order) > 1 else -np.inf
        if first >= threshold and first - second >= margin:
            selections[i] = order[0]
    if strategy == 'independent':
        return selections, ordering
    if strategy == 'greedy':
        used = set()
        for i in sorted(range(rows), key=lambda r: -scores[r, selections[r]] if selections[r] is not None else 0):
            field = selections[i]
            if field in used:
                selections[i] = None
            elif field is not None:
                used.add(field)
        return selections, ordering
    if strategy != 'hungarian':
        raise ValueError('Unknown table matching strategy')
    # One private HOLD node per source column. Candidates below threshold are infeasible.
    weight = np.full((rows, fields + rows), -1e9)
    for i, selection in enumerate(selections):
        weight[i, fields + i] = 0
        if selection is not None:
            for field in ordering[i]:
                if scores[i, field] >= threshold:
                    weight[i, field] = max(scores[i, field] - threshold, 1e-9)
    chosen = linear_sum_assignment(weight, maximize=True)
    return [int(field) if field < fields else None for field in chosen[1]], ordering
