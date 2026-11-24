"""Frozen synthetic panels for Phase 9. No source files or provider calls."""
from collections import Counter
from hashlib import sha256
import random

from app.ingest.mapping import ENTITY_FIELDS, norm_header
from mapping_research_data import csv_bytes, sha


VERSION = 'manufacturing-phase9-v1'
SPLITS = {'selection': (5, 2), 'risk': (5, 2), 'holdout': (10, 4)}
WORDS = {
    'product_id': ('완제품 추적 부호', 'sellable article tag'),
    'product_name': ('출고품 표시 문구', 'finished article display wording'),
    'base_unit': ('계량 환산의 바탕 단위', 'canonical posting measure'),
    'safety_stock_qty': ('보충 정책상 유지할 완충량', 'minimum buffer mandated by stock policy'),
    'material_id': ('공정 투입 원자재 관리키', 'identifier of consumable input stock'),
    'material_name': ('원료 불출표 설명문', 'description printed on the ingredient register'),
    'period': ('계획 귀속 집계 연월', 'monthly bucket to which demand belongs'),
    'demand_qty': ('해당 연월 고객 필요 합계', 'aggregate customer requirement for the bucket'),
    'bom_id': ('배합 사양 추적 표지', 'identifier of the recipe specification'),
    'bom_version': ('구성표 개정 기호', 'revision marking of recipe'),
    'status': ('구성표 결재 분류', 'release disposition of the recipe'),
    'is_active': ('배합표 사용 확인값', 'whether the recipe is currently enabled'),
    'valid_from': ('사양을 사용할 수 있는 첫날', 'first day recipe applies'),
    'valid_to': ('사양 사용 가능 마지막 날', 'last day recipe applies'),
    'base_qty': ('배합 시 기준 양품 산출 수', 'reference good output per production run'),
    'line_no': ('부품 행 정렬 번호', 'ordinal of ingredient row in recipe'),
    'component_type': ('투입 구성 분류값', 'category of ingredient in recipe'),
    'component_id': ('피투입 자재 추적 부호', 'stock tag of consumed component'),
    'qty_per': ('양품 산출 하나당 원재료 차감량', 'component drawn for one good output'),
    'unit': ('수치의 물리 계량 기호', 'quantity measure symbol'),
    'scrap_rate': ('투입 중 폐기 지분', 'fraction of component lost on issue'),
    'item_type': ('저장 물류 객체 분류', 'classification of stored article'),
    'item_id': ('실사 대상 물류 관리키', 'counted article identifier'),
    'as_of_date': ('창고 실물 집계 마감일', 'observed end of physical count'),
    'on_hand_qty': ('예약 공제 전 창고 실물 합계', 'gross physically counted stock'),
    'allocated_qty': ('출고 확약으로 이미 묶인 수', 'part of stock committed to fulfillment'),
    'available_qty': ('확약분을 뺀 불출 가능분', 'stock remaining after commitments'),
}

# The variant source is frozen per family and never shared across panel splits.
STYLES = {
    'selection': ('본사 대장', 'Line dossier', '이관 장부', 'Weekly shop form', '점검 원표'),
    'risk': ('협력 공정 전표', 'Dispatch control book', '현장 수불 대사', 'Shop-floor annex', '물류 정산 장부'),
    'holdout': ('기준 등록표', 'Export register', '가공 교대 전표', 'Audit printout', '전사 수기장',
                'Warehouse side sheet', '제조 절차 명세', 'Assembly control report', '월말 부속장', 'Planning docket'),
}
REQUIRED_EXTRAS = {
    'bom': ('base_qty', 'scrap_rate', 'valid_to'),
    'inventory': ('allocated_qty', 'available_qty'),
    'monthly_demand': ('unit',),
    'material': ('safety_stock_qty',),
    'product': ('safety_stock_qty',),
}
DISTRACTORS = {
    'bom': (('공정 불량 발생률 (완제품)', 'finished output defect percentage', 'finished_defect'),
            ('구매 입고 거래일', 'purchase receipt transaction day', 'event_date')),
    'inventory': (('도착 전 발주 잔량', 'purchase orders still open', 'open_orders'),
                  ('운송 중 입고 예정 수', 'scheduled quantity in transit', 'inbound'),
                  ('현장 반품 처리 수', 'units returned to sender', 'returns'),
                  ('유지 목표 안전재고', 'target safety buffer policy units', 'policy_buffer')),
    'monthly_demand': (('원장 주문 거래일', 'original sale transaction day', 'event_date'),
                       ('반품 후불 금액', 'value of returns in currency', 'money'),
                       ('자체 생산 실적 수량', 'units actually produced', 'production')),
    'material': (('발주 승인 수량', 'approved purchase units', 'open_orders'),
                 ('기준 금액 환산', 'extended material amount in currency', 'money')),
    'product': (('공급 거래처 추적 부호', 'identifier of supplying vendor', 'supplier'),
                ('상품 재무 장부 금액', 'product accounting amount in currency', 'money')),
}


def _values(field, rng, offset):
    dates = {'period': '2031-{:02d}', 'valid_from': '2031-02-{:02d}', 'valid_to': '2031-08-{:02d}',
             'as_of_date': '2031-05-{:02d}', 'event_date': '2031-05-{:02d}'}
    if field in dates:
        return [dates[field].format(i + 1) for i in range(9)]
    if field.endswith('_id') or field == 'supplier':
        return [f'SYN-{offset:04d}-{i:02d}' for i in range(9)]
    if field.endswith('_name'):
        return [f'Synthetic roll grade {offset}-{i:02d}' for i in range(9)]
    fixed = {'base_unit': 'EA', 'unit': 'EA', 'status': 'APPROVED', 'is_active': 'true',
             'component_type': 'MATERIAL', 'item_type': 'MATERIAL', 'bom_version': 'R2'}
    if field in fixed:
        return [fixed[field]] * 9
    if field == 'line_no':
        return [str(i + 1) for i in range(9)]
    if field in {'qty_per', 'base_qty', 'scrap_rate', 'finished_defect'}:
        return [f'0.{rng.randint(11, 92):02d}' for _ in range(9)]
    return [str(rng.randint(40, 420)) for _ in range(9)]


def _document(split, entity, family, copy):
    rng = random.Random(f'{VERSION}/{split}/{entity}/{family}/{copy}')
    style = STYLES[split][family]
    lang = family % 2
    fields = [f for f, spec in ENTITY_FIELDS[entity].items() if spec['required'] or f in REQUIRED_EXTRAS[entity]]
    columns = []
    transform = {'bom': 'scrap_rate', 'monthly_demand': 'period'}.get(entity) if family % 5 == 3 else None
    styled = lambda pair: f'{style} / {pair[lang]}'
    for field in fields:
        header = field if family % 5 == 0 else styled(WORDS[field])
        values = _values(field, rng, rng.randrange(1000, 9999))
        expected, state, scenario = field, 'DIRECT_MAPPING_READY', 'standard' if family % 5 == 0 else 'novel'
        if field == transform:
            values = [f'{int(float(x) * 100 + .5)}%' for x in values] if entity == 'bom' else [
                x.replace('-', '/') + '/15' for x in values]
            expected, state, scenario = None, 'TRANSFORM_REQUIRED', 'representation'
        columns.append({'header': header, 'values': values, 'expected': expected, 'semantic': field,
                        'state': state, 'scenario': scenario})
    if entity == 'inventory':
        stock = {col['expected']: col for col in columns}
        for i in range(9):
            stock['on_hand_qty']['values'][i] = str(int(stock['allocated_qty']['values'][i])
                                                    + int(stock['available_qty']['values'][i]))
    for ko, en, role in DISTRACTORS[entity]:
        columns.append({'header': styled((ko, en)), 'values': _values(role, rng, rng.randrange(1000, 9999)),
                        'expected': None, 'semantic': None, 'state': 'HOLD', 'scenario': role})
    if family % 5 == 2:
        columns.append({'header': styled(('역할 미기재 수치', 'unlabelled operational count')),
                        'values': _values('uncertain', rng, 0), 'expected': None, 'semantic': None,
                        'state': 'HOLD', 'scenario': 'ambiguous_numeric'})
    rng.shuffle(columns)
    key = f'phase9-{split}-{entity}-{family:02d}'
    item = {'id': f'{key}-{copy:02d}', 'family': key, 'entity': entity, 'document_type': entity,
            'title': f'Synthetic {entity} | {style}', 'columns': columns}
    item['csv_sha256'] = sha256(csv_bytes(item)).hexdigest()
    return item


def panels():
    docs = {split: [_document(split, entity, family, copy) for entity in sorted(ENTITY_FIELDS)
                    for family in range(families) for copy in range(copies)]
            for split, (families, copies) in SPLITS.items()}
    previous_families, previous_headers, previous_files = set(), set(), set()
    for split in docs.values():
        families = {d['family'] for d in split}
        novel = {norm_header(c['header']) for d in split for c in d['columns'] if c['header'] not in WORDS}
        files = {d['csv_sha256'] for d in split}
        if (previous_families & families or previous_headers & novel or previous_files & files or len(files) != len(split)):
            raise ValueError('Phase 9 family, novel header or file overlap')
        previous_families.update(families)
        previous_headers.update(novel)
        previous_files.update(files)
    return docs


def manifest(docs):
    return {split: {'sha256': sha({'version': VERSION, 'split': split, 'documents': panel}),
                    'documents': len(panel), 'families': len({doc['family'] for doc in panel}),
                    'entities': dict(Counter(doc['entity'] for doc in panel)),
                    'states': dict(Counter(col['state'] for doc in panel for col in doc['columns']))}
            for split, panel in docs.items()}
