"""Independent synthetic layouts for Phase 7. Source and labels are written only to ignored artifacts."""
from collections import Counter
from hashlib import sha256
import random

from app.ingest.mapping import ENTITY_FIELDS
from mapping_research_data import csv_bytes, norm, sha


LAYOUTS = {
    'bom': (
        {'product_id': 'Sku released by the recipe', 'component_id': 'Input stock key', 'bom_id': 'Recipe control code',
         'qty_per': 'Input drawn per finished unit', 'base_qty': 'Output lot basis', 'scrap_rate': 'Rejected input share'},
        {'product_id': '조립 후 품번', 'component_id': '투입 측 식별 문자열', 'bom_id': '조립 문서 키',
         'qty_per': '양품 한 개당 불출량', 'base_qty': '표준 작업 1회 산출량', 'scrap_rate': '투입 중 불용분'},
        {'product_id': 'Output catalogue reference', 'component_id': 'Consumed stock ID', 'bom_id': 'Assembly control ref',
         'qty_per': 'Recipe issue coefficient', 'base_qty': 'Nominal lot yield', 'scrap_rate': 'Unrecoverable input fraction'},
        {'product_id': '배합 완성 코드', 'component_id': '불출 품목 토큰', 'bom_id': '제조표 관리 번호',
         'qty_per': '산출 한 단위 소진 계수', 'base_qty': '통상 양품 회차 크기', 'scrap_rate': '비가역 감소 지분'},
    ),
    'inventory': (
        {'item_id': 'Warehouse object reference', 'on_hand_qty': 'Count before reservations', 'allocated_qty': 'Booked out of count',
         'available_qty': 'Balance free for issue', 'unit': 'Balance reporting UoM', 'as_of_date': 'Ledger cut-off day'},
        {'item_id': '창고 관리 키 문자열', 'on_hand_qty': '예약 포함 실사 총량', 'allocated_qty': '선점 물량 합계',
         'available_qty': '즉시 출고 가능한 잔량', 'unit': '실사 수량 기준 단위', 'as_of_date': '실물 집계 마감일'},
        {'item_id': 'Physical inventory article', 'on_hand_qty': 'Gross shelf count', 'allocated_qty': 'Fulfillment commitments',
         'available_qty': 'Shelf count net of commitments', 'unit': 'Canonical shelf measure', 'as_of_date': 'Observation date'},
        {'item_id': '선반 단위 참조코드', 'on_hand_qty': '차감 전 실사 수량', 'allocated_qty': '예약 출고분',
         'available_qty': '배정분 공제 잔고', 'unit': '재고 기준 표기 단위', 'as_of_date': '창고 관측 시점일'},
    ),
    'monthly_demand': (
        {'product_id': 'Volume outlook item ref', 'period': 'Bucket covered by outlook', 'demand_qty': 'Need aggregated per bucket'},
        {'product_id': '월 소요 추적 품목 키', 'period': '계획 귀속 월키', 'demand_qty': '월 귀속 필요 수량 합'},
        {'product_id': 'Forecast sellable SKU', 'period': 'Forecast bucket YYYY-MM', 'demand_qty': 'Bucket requirement units'},
        {'product_id': '판매 예정품 식별코드', 'period': '집계 구간 시작 연월', 'demand_qty': '기간별 고객 필요 총량'},
    ),
    'material': (
        {'material_id': 'Consumption stock ref', 'material_name': 'Ingredients display text', 'base_unit': 'Store-issued basis UoM',
         'safety_stock_qty': 'Policy floor for storage'},
        {'material_id': '원료 입고 대장키', 'material_name': '자재 라벨 표시명', 'base_unit': '불출 환산의 기준 단위',
         'safety_stock_qty': '보유 정책 최저 잔량'},
        {'material_id': 'Commodity lookup reference', 'material_name': 'Warehouse description of input', 'base_unit': 'Canonical material measure',
         'safety_stock_qty': 'Buffer policy quantity'},
        {'material_id': '현장 원료 참조 부호', 'material_name': '저장 대상 원료 명칭', 'base_unit': '원료 단위계 기본 기호',
         'safety_stock_qty': '운영 보유 하한'},
    ),
    'product': (
        {'product_id': 'Sellable catalogue reference', 'product_name': 'Finished label text', 'base_unit': 'Canonical finished goods measure'},
        {'product_id': '완성품 조회용 키', 'product_name': '출고 제품 표시 명칭', 'base_unit': '판매품 기준 계량 단위'},
        {'product_id': 'Released item registry code', 'product_name': 'Finished article display name', 'base_unit': 'Stocking measure of output'},
        {'product_id': '판매 대장 식별 문자열', 'product_name': '양품 라벨의 관리명', 'base_unit': '제품 등록 단위계'},
    ),
}
NEGATIVES = (
    ('Purchase order units already requested', 'Costs charged in local currency', 'Quantity sent back by buyer'),
    ('보충 요청 건 수량', '창고 재고 평가 금액', '거래처로 반송한 수량'),
    ('Inbound units still awaiting delivery', 'Accounting extension KRW', 'Units reversed after receipt'),
    ('도착 전 발주 물량', '통화 환산 장부 잔액', '환입 수량 집계'),
)
TITLES = {'bom': 'BOM recipe register', 'inventory': 'Inventory warehouse balances',
          'monthly_demand': 'Monthly demand forecast', 'material': 'Material stock directory',
          'product': 'Finished goods product catalog'}
VERSION = 'phase7-independent-layouts-v1'


def value(field, i, rng):
    if field.endswith('_id'):
        prefix = {'product_id': 'FG', 'component_id': 'RM', 'item_id': 'RM',
                  'material_id': 'RM', 'bom_id': 'BOM'}[field]
        return f'{prefix}-{4200+i}'
    if field.endswith('_name'):
        return ('Bleached kraft', 'Barrier sheet', 'Soft roll', 'Cushion insert')[i % 4]
    if field in ('base_unit', 'unit'):
        return ('EA', 'KG')[i % 2]
    if field == 'period':
        return f'2028-{i % 12 + 1:02d}'
    if field == 'as_of_date':
        return f'2028-06-{i + 1:02d}'
    if field == 'scrap_rate':
        return f'{rng.randint(2, 12) / 100:.2f}'
    if field == 'qty_per':
        return f'{rng.randint(3, 9) / 10:.1f}'
    return str(rng.randint(8, 200))


def panel():
    docs = []
    for entity, layouts in sorted(LAYOUTS.items()):
        for family, fields in enumerate(layouts):
            if not fields.keys() <= ENTITY_FIELDS[entity].keys():
                raise ValueError('Synthetic schema has an unknown field')
            for copy in range(3):
                rng = random.Random(f'{VERSION}-{entity}-{family}-{copy}')
                n = 10 + copy
                columns = [{'header': name, 'values': [value(key, i, rng) for i in range(n)],
                            'expected': key, 'semantic': key, 'state': 'DIRECT_MAPPING_READY', 'scenario': 'direct'}
                           for key, name in fields.items()]
                by_field = {column['expected']: column for column in columns}
                if entity == 'inventory':
                    allocated = [rng.randint(2, 65) for _ in range(n)]
                    available = [rng.randint(6, 135) for _ in range(n)]
                    for key, numbers in (('allocated_qty', allocated), ('available_qty', available),
                                         ('on_hand_qty', [a+b for a, b in zip(allocated, available, strict=True)])):
                        by_field[key]['values'] = list(map(str, numbers))
                for i, name in enumerate(NEGATIVES[family]):
                    columns.append({'header': name, 'values': [str(rng.randint(20, 400)) for _ in range(n)],
                                    'expected': None, 'semantic': None, 'state': 'HOLD',
                                    'scenario': ('purchase', 'money', 'returns')[i]})
                if entity == 'bom' and copy == 1:
                    scrap = by_field['scrap_rate']
                    scrap['values'] = [str(round(float(x)*100)) + '%' for x in scrap['values']]
                    scrap.update(expected=None, state='TRANSFORM_REQUIRED', scenario='percentage_transform')
                if copy == 2:
                    duplicate = dict(columns[0])
                    for col in (columns[0], duplicate):
                        col.update(expected=None, semantic=None, state='HOLD', scenario='ambiguous_duplicate')
                    columns.append(duplicate)
                rng.shuffle(columns)
                doc = {'id': f'phase7-{entity}-{family}-{copy}', 'family': f'phase7:{entity}:{family}',
                       'entity': entity, 'document_type': entity, 'title': TITLES[entity], 'columns': columns}
                doc['csv_sha256'] = sha256(csv_bytes(doc)).hexdigest()
                docs.append(doc)
    return docs, sha({'version': VERSION, 'documents': docs})


def manifest(docs, digest, known):
    prior = {norm(col['header']) for doc in known for col in doc['columns']}
    repeated = sorted({norm(col['header']) for doc in docs for col in doc['columns']} & prior)
    if repeated:
        raise ValueError('Independent Phase 7 layout already occurs in a previous partition: ' + ', '.join(repeated))
    return {'sha256': digest, 'documents': len(docs), 'families': len({d['family'] for d in docs}),
            'columns': sum(len(d['columns']) for d in docs),
            'states': dict(Counter(col['state'] for doc in docs for col in doc['columns']))}
