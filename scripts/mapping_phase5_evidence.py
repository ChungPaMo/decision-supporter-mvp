"""Research-only column profiles, hierarchical concepts and relation evidence."""
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from itertools import permutations
import re
import unicodedata

from app.ingest.ai_mapping import FIELD_ENUMS, has_term, local_rejection
from app.ingest.mapping import ENTITY_FIELDS, norm_header
from app.ingest.parsing import Cell
from app.ingest.profiling import profile, value_formats
from app.ingest.recommendation import QUANTITIES
from app.ingest.validation import normalize_unit, parse_period, parse_qty
from contracts.mapping_knowledge import BUSINESS_WORDS, CONFLICTS, DESCRIPTIONS
from mapping_research_data import FIELDS, norm, sha


PROFILE_VERSION = 'phase5-cell-evidence-v1'
KNOWLEDGE_VERSION = 'manufacturing-research-v2'
RELATION_FIELDS = ('on_hand_qty', 'allocated_qty', 'available_qty')
AMOUNT_SIGNS = frozenset('₩$€¥£')
US_GROUP = re.compile(r'[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?')
EU_GROUP = re.compile(r'[+-]?\d{1,3}(?:[.\u00a0\u202f ]\d{3})+(?:,\d+)?')
LOCALE_DECIMAL = re.compile(r'[+-]?\d+,\d{1,2}')
DATES = re.compile(r'(\d{4})[.](\d{1,2})[.](\d{1,2})')
CODE_FIELDS = {field for field, (kind, _) in FIELDS.items() if kind.endswith('_code')}
DATE_FIELDS = {'valid_from', 'valid_to', 'as_of_date'}

# Concepts with no direct destination also enter the hierarchy for negative evidence.
NEGATIVE = {
    'PURCHASE_ORDER': ('procurement', ('발주', '구매처', '조달', 'procurement', 'supplier', 'purchase', 'replenishment'), 'TRANSFORM_REQUIRED'),
    'RETURNS': ('sales', ('반품', '반송', '회수', 'reverse logistics', 'return', 'refund', 'refunded'), 'TRANSFORM_REQUIRED'),
    'PRODUCTION_ACTUAL': ('production', ('생산실적', '제조완료', '완성실적', 'production actual', 'factory output',
                                        'manufacturing completion', 'build completion'), 'TRANSFORM_REQUIRED'),
    'MONEY': ('accounting', ('금액', '금전', '단가', '정산', 'amount', 'price', 'cost', 'invoiced', 'currency'), 'NON_MATCH'),
    'COUNTERPARTY': ('counterparty', ('거래처', '청구처', '납품처', '납품상대방', 'customer account', 'invoice party',
                                       'account ref', 'organization identifier', 'buyer organization'), 'NON_MATCH'),
    'ORDER_EVENT': ('sales', ('주문접수', '거래접수', '거래등록일', '건별', 'order date', 'order placed', 'order placement',
                              'sales ledger', 'transaction line', 'individual order'), 'TRANSFORM_REQUIRED'),
}
DOMAINS = {'product': 'product_master', 'material': 'material_master', 'bom': 'bom',
           'inventory': 'inventory', 'monthly_demand': 'sales'}
CONTRASTS = {
    'base_qty': ('qty_per', 'line_no'), 'qty_per': ('base_qty', 'line_no', 'scrap_rate'),
    'component_id': ('product_id', 'bom_id'), 'product_id': ('material_id', 'component_id', 'bom_id'),
    'material_id': ('product_id', 'component_id'), 'product_name': ('material_name',),
    'material_name': ('product_name',), 'valid_from': ('valid_to', 'as_of_date', 'period'),
    'valid_to': ('valid_from', 'as_of_date', 'period'), 'period': ('as_of_date',),
    **{field: tuple(other for other in RELATION_FIELDS if other != field) for field in RELATION_FIELDS},
}


def knowledge():
    direct = {}
    for entity, fields in ENTITY_FIELDS.items():
        for field in fields:
            kind = FIELDS[field][0]
            direct[f'{entity}.{field}'] = {
                'domain': DOMAINS[entity], 'document_type': entity, 'field': field,
                'definition': DESCRIPTIONS[field], 'positive_examples': fields[field]['strong'][:4],
                'counterexamples': CONFLICTS.get(field, '').split(),
                'confusions': list(CONTRASTS.get(field, ())), 'type': kind,
                'unit_evidence': 'registered unit or separately confirmed conversion' if kind == 'unit' else 'not inferred',
                'evidence': ['header role', 'compatible original format', 'unambiguous table and entity'],
                'direct': True, 'transform': False, 'unknown_if': 'insufficient role evidence or multiple plausible meanings',
            }
    return {'version': KNOWLEDGE_VERSION, 'direct': direct, 'excluded': NEGATIVE,
            'unknown': 'HOLD when evidence does not establish a unique supported role'}


def normalized_words(value):
    return re.sub(r'[_./-]+', ' ', unicodedata.normalize('NFKC', value.casefold())).strip()


@lru_cache(maxsize=8192)
def role_signal(header, terms):
    label = normalized_words(header)
    compact = norm(label)
    return any(has_term(label, (term,)) if term.isascii() else norm(term) in compact for term in terms)


@lru_cache(maxsize=8192)
def negative_roles(header):
    return frozenset(key for key, (_, terms, _) in NEGATIVE.items() if role_signal(header, terms))


@dataclass(frozen=True)
class Observation:
    flags: Counter
    numbers: tuple[Decimal | None, ...]
    nonempty: int
    units: tuple[str, ...]
    scalar_values: tuple[str, ...]

    def ratio(self, flag):
        return self.flags[flag] / max(1, self.nonempty)


@lru_cache(maxsize=32768)
def measure_cell(text, kind, fmt):
    cell = Cell(text, kind, fmt)
    flags = {f'cell:{kind}'}
    if not text:
        return None, ('empty',)
    decimal, code, shape, unit = value_formats(text) if len(text) <= 128 else (False, False, None, None)
    amount = any(sign in text for sign in AMOUNT_SIGNS) or bool(re.search(r'\b(?:USD|KRW|EUR|JPY)\b', text, re.I))
    number = parse_qty(cell, scale=6)[0] if decimal else None
    if amount:
        flags.add('currency')
    if number is not None:
        flags.add('native_number')
        flags.add('integer' if number == number.to_integral_value() else 'fraction')
    if US_GROUP.fullmatch(text):
        flags.add('thousands')
    elif EU_GROUP.fullmatch(text) or LOCALE_DECIMAL.fullmatch(text):
        flags.add('locale_number')
    if (decimal and text.startswith('-')) or re.fullmatch(r'\([\d., ]+\)', text):
        flags.add('negative')
    if text.endswith('%'):
        flags.add('percent')
    if code:
        flags.add('code')
    if text.isdigit():
        flags.add('digit_string')
        if len(text) > 1 and text.startswith('0'):
            flags.add('leading_zero')
    if kind == 'number' and fmt and re.fullmatch(r'0{2,}', fmt):
        flags.add('excel_zero_mask')
    if fmt:
        flags.add('excel_format')
    dotted = DATES.fullmatch(text)
    if dotted:
        try:
            date(*map(int, dotted.groups()))
        except ValueError:
            dotted = None
    if (shape and shape.endswith('_DATE')) or dotted:
        flags.add('calendar_date')
    if parse_period(cell)[0] is not None:
        flags.add('registration_period')
        if (shape and shape.endswith('_MONTH')) or '년' in text:
            flags.add('explicit_month')
    if normalize_unit(text):
        flags.add('recognized_unit')
    elif unit:
        flags.add('unit_conversion_required')
    for field, options in FIELD_ENUMS.items():
        if text.casefold() in options:
            flags.add('enum:' + field)
    if text.startswith(('=', '#REF!', '#VALUE!', '#DIV/0!')):
        flags.add('formula_or_error')
    return number, tuple(sorted(flags))


def observe(cells):
    flags, numbers, units, values = Counter(), [], set(), []
    for cell in cells:
        text = (cell.value or '').strip()
        number, found = measure_cell(text, cell.kind, cell.number_format)
        flags.update(found)
        numbers.append(number)
        if text:
            values.append(text)
            if unit := normalize_unit(text):
                units.add(unit)
    flags['distinct'] = len(set(values))
    return Observation(flags, tuple(numbers), len(values), tuple(sorted(units)), tuple(values))


def observe_sheet(parsed, dataset_id):
    sheet = parsed.sheets[0]
    columns = []
    for i in range(len(sheet.header)):
        columns.append(observe(row.cells[i] if i < len(row.cells) else Cell(None, 'empty') for row in sheet.rows))
    return sheet, profile(parsed, dataset_id).sheets[0].columns, columns


def format_issue(field, observation, header):
    if not observation.nonempty:
        return 'EMPTY_COLUMN'
    found = observation.ratio
    flags = observation.flags
    if flags['formula_or_error']:
        return 'SOURCE_ERROR_OR_FORMULA'
    if field in QUANTITIES | {'line_no'}:
        if flags['currency']:
            return 'MONEY_AS_QUANTITY'
        if flags['percent']:
            return 'PERCENT_NEEDS_CONVERSION'
        if flags['negative']:
            return 'NEGATIVE_QUANTITY'
        if flags['locale_number']:
            return 'LOCALE_NEEDS_CONFIRMATION'
        if flags['leading_zero'] or flags['excel_zero_mask']:
            return 'NUMERIC_CODE_AMBIGUITY'
        scale = 6 if field in {'qty_per', 'scrap_rate'} else 4
        if found('native_number') != 1:
            return 'MIXED_OR_UNPARSEABLE_NUMBER'
        if any(parse_qty(Cell(value, 'text'), scale=scale)[0] is None for value in observation.scalar_values):
            return 'UNSUPPORTED_QUANTITY_PRECISION'
        if field == 'line_no' and any(not re.fullmatch(r'[0-9]{1,6}', value) or int(value) < 1
                                      for value in observation.scalar_values):
            return 'NON_POSITIVE_OR_FRACTIONAL_LINE_NUMBER'
        if field == 'scrap_rate' and any(number is not None and number > 1 for number in observation.numbers):
            return 'FRACTION_OUT_OF_RANGE'
    if field in {'unit', 'base_unit'} and found('recognized_unit') != 1:
        return 'UNREGISTERED_OR_MIXED_UNIT'
    if field in FIELD_ENUMS and found('enum:' + field) != 1:
        return 'UNSUPPORTED_ENUM_VALUE'
    if field == 'period':
        if found('registration_period') != 1:
            return 'DATE_MONTH_GRANULARITY' if flags['calendar_date'] else 'INVALID_MONTH_REPRESENTATION'
        if found('explicit_month') != 1 and not role_signal(header, ('월', '연월', 'month', 'monthly')):
            return 'MONTH_START_WITHOUT_MONTHLY_ROLE'
    if field in DATE_FIELDS and found('calendar_date') != 1:
        return 'INVALID_CALENDAR_DATE'
    if field in CODE_FIELDS and (found('code') != 1 or found('registration_period') == 1 or flags['currency']):
        return 'INVALID_OR_DATE_LIKE_IDENTIFIER'
    return None


def verify(field, header, old_profile, observation, *, duplicate=False, hierarchical=True, strict=False):
    legacy = local_rejection(field, header, old_profile, observation.scalar_values, role_conflict=duplicate)
    if strict:
        return legacy
    label = header.display
    detail = format_issue(field, observation, label)
    # A format improvement can recover a Phase 4 type block only where the existing input parser accepts it.
    if legacy not in (None, 'TYPE_INCOMPATIBLE', 'NON_DECIMAL_VALUES', 'NEEDS_TRANSFORM'):
        return legacy
    if legacy == 'NEEDS_TRANSFORM' and (field != 'period' or detail or negative_roles(label)):
        return legacy
    if detail:
        return detail
    if hierarchical:
        blocked = negative_roles(label)
        if 'COUNTERPARTY' in blocked and field in CODE_FIELDS | {'product_name', 'material_name'}:
            return 'COUNTERPARTY_ROLE'
        if 'MONEY' in blocked and field in QUANTITIES | CODE_FIELDS:
            return 'MONEY_ROLE'
        if blocked & {'PURCHASE_ORDER', 'RETURNS', 'PRODUCTION_ACTUAL', 'ORDER_EVENT'} and field in {'demand_qty', 'period'}:
            return 'TRANSFORM_REQUIRED'
    return None


def soft_fit(field, item):
    flags, ratio = item.flags, item.ratio
    if field in QUANTITIES | {'line_no'}:
        return min(1.0, ratio('native_number') + 0.5 * ratio('locale_number'))
    if field == 'period':
        return ratio('registration_period')
    if field in DATE_FIELDS:
        return ratio('calendar_date')
    if field in CODE_FIELDS:
        return ratio('code')
    if field in FIELD_ENUMS:
        return ratio('enum:' + field)
    if field in {'unit', 'base_unit'}:
        return ratio('recognized_unit')
    if field.endswith('_name'):
        return max(0.0, 1.0 - max(ratio('native_number'), ratio('calendar_date'), ratio('recognized_unit')))
    return float(bool(flags['code']))


def relationship(entity, observations):
    """Give indirect evidence to a unique inventory triad. Other shapes stay diagnostic."""
    votes = {}
    if entity != 'inventory':
        return votes
    numeric = [i for i, obs in enumerate(observations) if obs.nonempty >= 5 and obs.ratio('native_number') == 1
               and not obs.flags['leading_zero'] and obs.ratio('registration_period') < 1]
    if len(numeric) > 10:
        return votes
    valid = []
    for group in permutations(numeric, 3):
        a, b, c = [observations[i].numbers for i in group]
        pairs = [(x, y, z) for x, y, z in zip(a, b, c, strict=True) if None not in (x, y, z)]
        if len(pairs) >= 5 and all(x > y and x > z and y >= 0 and z >= 0 and x == y + z for x, y, z in pairs):
            valid.append(group)
    # The equation distinguishes total from its addends, but cannot orient allocated vs available.
    if valid and len({(group[0], *sorted(group[1:])) for group in valid}) == 1:
        votes[valid[0][0], 'on_hand_qty'] = 1.0
        for i in valid[0][1:]:
            for field in ('allocated_qty', 'available_qty'):
                votes[i, field] = 0.5
    return votes


def version_manifest():
    return {'profile_version': PROFILE_VERSION, 'knowledge_version': KNOWLEDGE_VERSION, 'knowledge_sha256': sha(knowledge())}
