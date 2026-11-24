"""Independent synthetic document families for offline manufacturing mapping research."""
import csv
from datetime import date, timedelta
import hashlib
import io
import json
from pathlib import Path
import random
import unicodedata

from evaluate_mapping_embeddings import DESCRIPTIONS, HOLDOUT
from evaluate_mapping_recommendations import CASES
from app.ingest.mapping import ENTITY_FIELDS


# Type and independently written header vocabulary for train | calibration | final.
# Calibration and final terms are fixtures, not target descriptors or training aliases.
FIELDS = {
    'product_id': ('product_code', '판매품 식별키,finished SKU|완제품 등록번호,finished goods key|상업상품 품번,sellable item ref'),
    'product_name': ('name', '상품 표시문구,finished item label|영업용 품명,catalog display title|납품품 호칭,sellable designation'),
    'product_type': ('category', '완제품 분류군,finished item class|판매품 계층,goods segment|출고품 계열,catalog assortment group'),
    'material_id': ('material_code', '원료 식별키,raw input key|원부재 등록번호,stock ingredient ref|배합재 품번,ingredient catalog key'),
    'material_name': ('name', '소재 표시명,raw input label|입고재 품명,ingredient display title|투입재 호칭,feedstock designation'),
    'period': ('month', '수요 귀속월,requirements month|판매예정 연월,demand bucket month|월간 소요 구간,consumption month bucket'),
    'demand_qty': ('number', '고객 필요수량,monthly requested units|월별 판매 필요개수,requested monthly volume|매월 주문 소요개수,customer requirement volume'),
    'base_unit': ('unit', '기준 계량기호,reference measure symbol|관리 기본계량,master measuring scale|표준 수불단위,catalog measure abbreviation'),
    'unit': ('unit', '표기 계량기호,measurement symbol|수불 계량표기,posting measuring scale|계상 단위기호,quantity denomination'),
    'safety_stock_qty': ('number', '품절 방지 비축량,minimum buffer stock|보유 하한량,protective reserve|유지해야 할 비축량,inventory cushion floor'),
    'bom_id': ('generic_code', '제품 배합표 키,recipe record key|구성명세 식별표,assembly structure reference|자재명세 문서번호,formula specification ref'),
    'bom_version': ('version', '구성표 개정차수,recipe edition revision|자재명세 변경판,assembly revision edition|배합표 발행판,formula release iteration'),
    'status': ('status', '구성 결재결과,recipe approval mark|구성표 심사단계,assembly authorization outcome|배합표 결재구분,formula review disposition'),
    'is_active': ('bool', '현행 구성 사용여부,recipe in-use flag|구성표 적용여부,assembly enable switch|현재 명세 사용,bill enabled indicator'),
    'valid_from': ('date', '효력 개시일,effectivity opens|구성 시행일,assembly becomes valid|배합 적용 첫날,first effective calendar day'),
    'valid_to': ('date', '효력 만료일,effectivity closes|구성 폐지일,assembly validity expires|배합 적용 마지막날,last eligible calendar day'),
    'base_qty': ('number', '모품 기준개수,reference output count|모제품 환산배치량,parent batch denominator|배합표 산출 기준량,formula batch reference output'),
    'line_no': ('number', '구성 상세 순서,recipe sequence index|투입행 차례,component display order|명세 전개 행순서,assembly detail ordinal'),
    'component_type': ('category', '하위재 분류군,child component class|투입 요소 종류,ingredient class group|배합 요소 대분류,assembly component tier'),
    'component_id': ('material_code', '투입재 식별키,child component key|하위 부품 참조번호,ingredient part number|배합 대상 투입품번,assembly input part ref'),
    'qty_per': ('number', '모품당 투입량,per-parent material usage|배합 소모 개수,component input factor|산출 기준당 소요개수,ingredient usage per recipe unit'),
    'scrap_rate': ('ratio', '투입 손실계수,input loss fraction|배합 폐기 비중,component waste fraction|정상 투입 제외 비중,unrecoverable material share'),
    'item_type': ('category', '창고 대상 품목군,stock kind class|재고객체 종류,warehouse inventory family|수불대상 대분류,warehouse item nature'),
    'item_id': ('stock_code', '창고품 구분코드,warehouse SKU key|보관품 식별번호,inventory catalog reference|수불 대상 품번,warehouse asset item ref'),
    'as_of_date': ('date', '재고 실사시점,stock count snapshot|잔량 관측 일자,warehouse snapshot stamp|수불 마감일,closing balance calendar day'),
    'on_hand_qty': ('number', '실물 창고 보유량,physical total stock|예약 포함 실사량,warehouse tally including reserved|차감 전 실보유량,physical balance before reservations'),
    'allocated_qty': ('number', '예약 물량,reserved stock units|출고 대기 배정량,committed warehouse balance|이미 묶인 재고개수,stock held for fulfilment'),
    'available_qty': ('number', '즉시 불출 가능량,unreserved stock units|차감 후 잔여량,warehouse free balance|예약 제외 잔여개수,stock free for fulfilment'),
}
NEGATIVES = {
    'returns': ('number', '고객 반송개수,refund volume|되돌려받은 물량,customer returned units|환입 처리량,reverse logistics tally'),
    'production': ('number', '공정 생산실적,factory manufactured volume|작업 완성분,completed shop output|공장실적 개수,manufacturing completion tally'),
    'purchase': ('number', '공급사 발주물량,procurement order count|구매 요청잔량,supplier requested quantity|입고대기 주문량,open vendor PO volume'),
    'shipping': ('number', '운송 인계물량,dispatched shipment volume|실제 불출개수,delivered outbound units|물류 인도수량,carrier fulfilment tally'),
    'money': ('money', '거래 금액,local currency total|정산 대가,billed sales value|거래 금전합계,settlement amount'),
    'customer': ('generic_code', '납품처 식별번호,buyer organization key|거래상대 참조,customer account identifier|청구처 등록코드,invoice party ref'),
    'order_date': ('date', '고객 요청일,order placed stamp|주문 접수 날짜,purchase booking date|거래 성립일,customer submission date'),
    'note': ('name', '현장 메모,operator remark|실사 비고,inspection annotation|담당 메모란,warehouse comment'),
    'unknown': ('number', '값A,value A|보조항목 팔,auxiliary 8|집계 열4,measure 4'),
}
TITLES = {
    'product': ('판매 제품 명세', 'Finished inventory catalog', '판매품 기준 정보'),
    'material': ('구매 자재 기준', 'Materials reference register', '배합재 마스터'),
    'bom': ('투입 구성 명세', 'Assembly bill register', '배합 전개 사양'),
    'inventory': ('창고 재고 현황', 'Warehouse stock snapshot', '수불 마감 실사'),
    'monthly_demand': ('월 수요 현황', 'Monthly customer requirements', '영업 소요 계획표'),
}
SPLITS = {'train': (0, 195, 2026112401), 'calibration': (1, 16, 2026112402), 'final': (2, 26, 2026112403)}
SCOPE = 'SYNTHETIC_MANUFACTURING_V1'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())


def target_catalog():
    return {entity: {key: {'description': DESCRIPTIONS[key], 'kind': FIELDS[key][0], 'required': spec['required'],
                           'aliases': sorted({key, *spec.get('strong', []), *spec.get('weak', [])})}
                     for key, spec in fields.items()} for entity, fields in ENTITY_FIELDS.items()}


def values(kind, rng, count, offset):
    if kind in ('product_code', 'material_code', 'stock_code', 'generic_code'):
        prefixes = {'product_code': ('FG', 'SKU'), 'material_code': ('RM', 'MAT'),
                    'stock_code': ('FG', 'RM'), 'generic_code': ('C', 'X')}
        return [f'{rng.choice(prefixes[kind])}-{offset + i % 9:06d}' for i in range(count)]
    if kind == 'name':
        return [rng.choice(('폴리 필름', 'Liner roll', '박스 조립용', 'Recycled kraft', '원단 복합재')) + f' {offset % 500 + i % 8}' for i in range(count)]
    if kind in ('date', 'month'):
        start = date(2022 + offset % 7, 1 + offset % 12, 1)
        dates = [start + timedelta(days=i * (31 if kind == 'month' else 2)) for i in range(count)]
        return [(d.strftime('%Y-%m') if kind == 'month' else d.isoformat()) for d in dates]
    if kind in ('unit', 'category', 'bool', 'status', 'version'):
        options = {'unit': ('EA', 'kg', 'm', 'BOX'), 'category': ('MATERIAL', 'PRODUCT', 'FINISHED'),
                   'bool': ('Y', 'N'), 'status': ('APPROVED', 'DRAFT'), 'version': ('V1', 'V2', 'V3')}
        return [rng.choice(options[kind]) for _ in range(count)]
    if kind == 'money':
        return [rng.choice(('$', '₩')) + f'{rng.randint(1, 800) * 137:,}' for _ in range(count)]
    if kind == 'ratio':
        return [str(rng.randint(0, 12) / 100) for _ in range(count)]
    return [str(rng.randint(0, 1500)) if rng.random() < .85 else str(rng.randint(-5, 1200) / 10) for _ in range(count)]


def make_document(split, entity, index, rng):
    phase = SPLITS[split][0]
    group = f'{split}:{entity}:{index % 6}'
    count = (16, 22, 28)[index % 3]
    offset = (phase + 1) * 100_000 + rng.randrange(90_000)
    specs = ENTITY_FIELDS[entity]
    chosen = [key for key, spec in specs.items() if spec['required'] or rng.random() > .24]
    if index % 7 == 0 and len(chosen) > 3:
        chosen.pop(rng.randrange(len(chosen)))  # simulate missing required/optional roles
    records = []
    used = set()

    def add(name, kind, vocab, expected, scenario):
        words = vocab.split('|')[phase].split(',')
        header = words[(index + len(records)) % len(words)]
        if index % 11 == 3:  # introduce spacing changes and a typo without copying other split stems
            header = header.replace(' ', '_') + ('.' if len(header) < 7 else header[-1])
        if norm(header) in used:
            return
        used.add(norm(header))
        records.append({'header': header, 'expected': expected, 'scenario': scenario,
                        'values': values(kind, rng, count, offset + len(records) * 31), '_role': name})

    for key in chosen:
        kind, vocabulary = FIELDS[key]
        add(key, kind, vocabulary, key, 'direct')
    distractors = list(NEGATIVES) if entity == 'monthly_demand' else ['note', 'unknown', 'money', 'customer', 'order_date']
    for key in rng.sample(distractors, 2 + (index % 3 == 1)):
        kind, vocabulary = NEGATIVES[key]
        add(key, kind, vocabulary, None, key)
    if entity == 'inventory':
        by_role = {col['_role']: col for col in records}
        triad = ('on_hand_qty', 'allocated_qty', 'available_qty')
        if all(key in by_role for key in triad):
            totals = [rng.randrange(30, 4000) for _ in range(count)]
            reserved = [rng.randrange(0, qty) for qty in totals]
            free = [qty - allocation + (1 if index % 9 == 0 else 0) for qty, allocation in zip(totals, reserved)]
            for key, data in zip(triad, (totals, reserved, free)):
                by_role[key]['values'] = list(map(str, data))
    if index % 13 == 5:  # header suggests a target, but the values are in the wrong dimension
        candidates = [col for col in records if FIELDS.get(col['_role'], ('',))[0] == 'number']
        if candidates:
            bad = candidates[-1]
            bad.update(expected=None, scenario='incompatible', values=values('money', rng, count, offset))
    if index % 19 == 8:
        column = records[0]
        column.update(expected=None, scenario='ambiguous_duplicate')
        records.append({**column, 'values': list(reversed(column['values']))})
    if index % 5 == 2:
        records[-1]['values'][0] = ''
    if index % 3 == 1:
        rng.shuffle(records)
    assumed = entity
    if index % 29 == 18:
        assumed = next(kind for kind in specs_by_entity() if kind != entity)
        for col in records:
            col.update(expected=None, scenario='wrong_route')
    for col in records:
        del col['_role']
    return {'id': f'{split}-{entity}-{index:03}', 'family': group, 'entity': assumed, 'document_type': entity,
            'title': TITLES[entity][phase], 'columns': records}


def specs_by_entity():
    return sorted(ENTITY_FIELDS)


def csv_bytes(doc):
    buffer = io.StringIO(newline='')
    columns = doc['columns']
    csv.writer(buffer, lineterminator='\n').writerows([[col['header'] for col in columns],
        *zip(*(col['values'] for col in columns), strict=True)])
    return buffer.getvalue().encode('utf-8')


def build(output: Path, *, write_csv=False):
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'scope': SCOPE, 'splits': {}, 'regression_sha256': {
        path.name: hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for path in (CASES, HOLDOUT)}}
    data = {}
    for name, (_, per_entity, seed) in SPLITS.items():
        rng = random.Random(seed)
        docs = [make_document(name, entity, i, rng) for entity in specs_by_entity() for i in range(per_entity)]
        for doc in docs:
            doc['csv_sha256'] = hashlib.sha256(csv_bytes(doc)).hexdigest()
        payload = {'scope': SCOPE, 'split': name, 'documents': docs}
        data[name] = payload
        manifest['splits'][name] = {'sha256': sha(payload), 'seed': seed, 'documents': len(docs),
                                    'columns': sum(len(doc['columns']) for doc in docs),
                                    'families': sorted({doc['family'] for doc in docs})}
    audit(data)
    for name, value in data.items():
        (output / f'{name}.json').write_bytes(canonical(value) + b'\n')
        if write_csv:
            folder = output / 'csv' / name
            folder.mkdir(parents=True, exist_ok=True)
            for doc in value['documents']:
                (folder / (doc['id'] + '.csv')).write_bytes(csv_bytes(doc))
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def audit(data):
    groups, headers, hashes = set(), set(), set()
    for split, payload in data.items():
        if payload['scope'] != SCOPE or payload['split'] != split:
            raise ValueError('Synthetic scope or split mismatch')
        docs = payload['documents']
        if len({doc['id'] for doc in docs}) != len(docs):
            raise ValueError('Duplicate document IDs')
        if any(not doc['id'] or any(ch not in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for ch in doc['id']) for doc in docs):
            raise ValueError('Invalid synthetic document filename')
        local_groups = {doc['family'] for doc in docs}
        local_headers = {(doc['document_type'], norm(col['header'])) for doc in docs for col in doc['columns']}
        local_hashes = {doc['csv_sha256'] for doc in docs}
        if groups & local_groups or headers & local_headers or hashes & local_hashes:
            raise ValueError('Cross-split document family, normalized header or file leakage')
        groups |= local_groups
        headers |= local_headers
        hashes |= local_hashes
        for doc in docs:
            if hashlib.sha256(csv_bytes(doc)).hexdigest() != doc['csv_sha256']:
                raise ValueError('Source file digest mismatch')
            if any(c['expected'] is not None and c['expected'] not in ENTITY_FIELDS[doc['entity']] for c in doc['columns']):
                raise ValueError('Unknown target field')


def load_frozen(directory, split):
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    payload = json.loads((directory / f'{split}.json').read_text(encoding='utf-8'))
    if sha(payload) != manifest['splits'][split]['sha256']:
        raise ValueError('Frozen split digest mismatch')
    audit({split: payload})
    folder = directory / 'csv' / split
    if folder.exists():
        for doc in payload['documents']:
            path = folder / (doc['id'] + '.csv')
            if hashlib.sha256(path.read_bytes()).hexdigest() != doc['csv_sha256']:
                raise ValueError('On-disk CSV digest mismatch')
    return payload['documents'], manifest['splits'][split]['sha256']
