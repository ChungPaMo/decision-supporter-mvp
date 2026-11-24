"""Freeze a fresh manufacturing panel with independent semantic and direct gold."""
import argparse
from collections import Counter
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import random

from app.ingest.mapping import ENTITY_FIELDS
from mapping_phase5_data import HEADERS as P5_HEADERS, write_frozen
from mapping_research_data import FIELDS, csv_bytes, norm, sha


OUT = Path('.artifacts/mapping-research/phase6')
VERSION = 'synthetic-manufacturing-phase6-v1'
SPLITS = {'development': (0, 14, 62901), 'selection': (1, 22, 62902),
          'risk': (2, 22, 62903), 'holdout': (3, 40, 62904)}
NAMES = {
    'product_id': ('sellable lookup key', '유통 제품 식별 ID', '출고 대상 SKU', 'Finished article record number'),
    'product_name': ('판매 표시 이름', 'Sellable label wording', '판매 상품 카탈로그명', 'FG commercial designation'),
    'product_type': ('제품 생산단계 구분', 'finished or semi item class', 'FG assortment category', '상품 생산 분류 등급'),
    'material_id': ('원재 구매 식별자', 'Raw input inventory code', '자재 reference number', '원료 품목 등록키'),
    'material_name': ('feedstock name leaf', '구매 소재 표시명', '원재료 설명 명칭', 'Raw input commercial label'),
    'period': ('수요계획 인식월', 'Demand posting month', '수요 확정 귀속 연월', 'Committed sales month bucket'),
    'demand_qty': ('고객 필요 월합계', 'Forecast total monthly units', '계획 판매 소요량', 'Committed demand volume per month'),
    'base_unit': ('Master stocking uom', '기초재고 환산 기본단위', 'Item reference unit code', '품목 기본 수불 기호'),
    'unit': ('기록 계량 단위기호', 'Actual measure unit notation', '재고량 단위표기', 'Transaction quantity uom code'),
    'safety_stock_qty': ('품절 방지 하한물량', 'Minimum service stock reserve', '품절 방지 재고 수준', 'Holding safety stock target'),
    'bom_id': ('제품 구성명세 관리번호', 'Bill of materials identity', '제조 조합표 레코드 키', 'Assembly composition specification ID'),
    'bom_version': ('조합표 개정 이력번호', 'Bill engineering revision', '소요표 변경판 구분', 'Recipe issued edition'),
    'status': ('구성 승인 프로세스 단계', 'Released recipe authorization flag', '조립 승인 진행단계', 'BOM published or draft state'),
    'is_active': ('사양 운영 사용 표시', 'Active recipe validity flag', '현행 조합표 적용중 표기', 'Composition enabled for use'),
    'valid_from': ('사양 효력 시작 날짜', 'Bill validity opening date', '레시피 적용시작 기준일', 'Assembly effectivity commencing date'),
    'valid_to': ('사양 효력 닫히는 날짜', 'Bill validity expiry date', '레시피 적용종료 기준일', 'Assembly effectivity expiration date'),
    'base_qty': ('기준 패키지 산출 개수', 'Nominal output per recipe', '작업배치 기준 생산수량', 'Finished quantity per base batch'),
    'line_no': ('구성 부품행 순차번호', 'BOM component position', '조합 투입 순번', 'Ingredient entry sequence number'),
    'component_type': ('부품 구성 분류종류', 'Component classification group', '조합표 하위품 종류', 'Entry product or input class'),
    'component_id': ('하위 부재료 품목번호', 'BOM component item identity', '조합 상세 구성품 식별키', 'Ingredient row part reference'),
    'qty_per': ('기준당 부품 투입 소모량', 'Usage volume per assembly', '단위 산출당 자재 소비계수', 'Material units used for one output'),
    'scrap_rate': ('투입 순손실 비율', 'Component wastage share', '조합 불량 차감률', 'Proportion lost from component usage'),
    'item_type': ('창고품 제품자재 구분', 'Stocked item accounting kind', '보유 재고 품목의 성격', 'Inventory article product or material class'),
    'item_id': ('창고품 추적 식별자', 'Inventory held item number', '실물 재고 품번 키', 'Stocktaking SKU reference'),
    'as_of_date': ('실사일 현재 기준', 'Stock level observation timestamp', '수불 실사 기준 날짜', 'Inventory balance accounting cutoff date'),
    'on_hand_qty': ('예약 포함 실물 잔고', 'Total physical inventory before holds', '실물 총량 차감 전', 'Stock count inclusive of allocations'),
    'allocated_qty': ('예약에 이미 묶인 재고', 'Committed quantity already booked', '실사 중 예약 물량', 'Reserved units excluded from free stock'),
    'available_qty': ('예약 차감 뒤 사용 가능', 'Quantity free after reservations', '배정 제외 실출고 가능분', 'Remaining pickable after allocation'),
}
SIDE = {
    'purchase': ('협력사 발주 예정량', 'Purchasing supply request count', '원부재 조달 요청 물량', 'Inbound restock requisition volume'),
    'returns': ('접수 반품 물건 개수', 'Returned line unit count', '역송 회수 수량', 'Customer credit return volume'),
    'production': ('설비 완성 실적수량', 'Manufactured unit actual tally', '완료 공정 발생 수량', 'Plant output actually finished'),
    'money': ('재화 매출 정산액', 'Revenue extended amount', '청구액 원화 합계', 'Settlement total in won'),
    'price': ('판매 단위 당 단가', 'Billed price per piece', '개당 합의 단가', 'Invoice rate per unit'),
    'customer': ('정산 상대 거래처키', 'Invoice buyer party number', '고객 사업주체 식별자', 'Billed counterparty record key'),
    'order_date': ('판매 건별 거래 접수일', 'Entered day of invoice order', '주문 이벤트 접수 날짜', 'Customer transaction booking day'),
    'unknown': ('기타 임시 열', 'Scratch column entry', '확인중 보조 항목', 'Misc entry A'),
    'note': ('회사 비고 메모', 'Note reviewed later', '참고 사항 설명란', 'Reviewer comment text'),
    'ambiguous': ('수량 코드', 'Business item measure', '식별 수량 표기', 'Reference amount code'),
}
TITLES = {'product': '제품 기준 목록', 'material': '원재료 사전', 'monthly_demand': '월간 수요 합계', 'bom': 'BOM 조립 사양',
          'inventory': '창고 실사 재고'}
ROUTE = {'product': 'material', 'material': 'product', 'inventory': 'bom', 'bom': 'inventory', 'monthly_demand': 'inventory'}


def values(role, index, depth, rng):
    kind = FIELDS.get(role, ({'customer': 'generic_code', 'order_date': 'date', 'note': 'name'}.get(role, 'number'), ''))[0]
    if kind.endswith('_code'):
        group = {'product_code': 'SX', 'material_code': 'RM', 'stock_code': 'WH', 'generic_code': 'CX'}[kind]
        return [f'{index + 41:02}{k % 7:03}' if index % 5 == 0 else f'{group}{index + 8}.{k % 7}' for k in range(depth)]
    if kind == 'name':
        return [f'{("Bush 링", "지지판", "Clamp assembly", "아연 와셔")[(k + index) % 4]} #{index + k % 5}' for k in range(depth)]
    if kind == 'version':
        return [f'R{index % 4}-{k // 4 + 1}' for k in range(depth)]
    if kind in ('date', 'month'):
        start = date(2031, index % 10 + 1, 1)
        times = [start + timedelta(days=(32 if kind == 'month' else 5) * k + (32 if role == 'valid_to' else 0))
                 for k in range(depth)]
        return [day.strftime(('%Y-%m', '%Y%m', '%Y/%m', '%Y-%m-01')[index % 4] if kind == 'month'
                             else ('%Y-%m-%d', '%Y/%m/%d', '%Y%m%d', '%Y.%m.%d')[index % 4]) for day in times]
    if kind == 'unit':
        return [('EA', 'kg', 'g', 'min')[index % 4]] * depth
    if kind in ('bool', 'status', 'category'):
        options = {'bool': ('TRUE', 'FALSE'), 'status': ('DRAFT', 'APPROVED'),
                   'category': ('FINISHED', 'SEMI_FINISHED') if role == 'product_type' else ('PRODUCT', 'MATERIAL')}[kind]
        return [options[(index + k // 3) % 2] for k in range(depth)]
    if role == 'line_no':
        return [str(k + 1) for k in range(depth)]
    if kind == 'ratio':
        return [f'0.{rng.randrange(21):02}' for _ in range(depth)]
    numbers = [rng.randrange(2, 6700) for _ in range(depth)]
    return [f'{n:,}' if index % 4 == 1 else f'{n}.25' if index % 4 == 2 else str(n) for n in numbers]


def panel(split):
    track, count, seed = SPLITS[split]
    rng = random.Random(seed)
    docs = []
    for entity, schema in sorted(ENTITY_FIELDS.items()):
        for i in range(count):
            sample = i + 5 * track
            width = i % 8
            nrows = 6 + (i + 3 * track) % 9
            roles = [field for field, spec in schema.items() if spec['required'] or rng.random() < .78]
            if width == 3:
                roles.remove(next(role for role in roles if schema[role]['required']))
            columns = []
            sides = rng.sample(list(SIDE), 2 + int(width in (3, 6)))
            for role in roles + sides:
                direct = role in schema
                name = role if direct and width == 0 else (NAMES if direct else SIDE)[role][track]
                if width == 5:
                    name = name.replace(' ', ' / ')
                if width == 7:
                    name = name.lower()
                rows = values(role, sample, nrows, rng)
                state = 'DIRECT_MAPPING_READY' if direct else 'HOLD'
                columns.append({'header': name, 'values': rows, 'expected': role if direct else None,
                                'semantic': role if direct else None, 'state': state, 'scenario': 'direct' if direct else role})
            original = {column['semantic']: column for column in columns if column['semantic']}
            inventory = {'on_hand_qty', 'allocated_qty', 'available_qty'}
            if entity == 'inventory' and inventory <= original.keys():
                used = [rng.randint(1, 70) for _ in range(nrows)]
                free = [rng.randint(1, 100) for _ in range(nrows)]
                for field, entries in (('allocated_qty', used), ('available_qty', free),
                                       ('on_hand_qty', [x + y for x, y in zip(used, free, strict=True)])):
                    original[field]['values'] = list(map(str, entries))
            if width == 2 and entity in ('bom', 'inventory', 'monthly_demand', 'product', 'material'):
                target = {'bom': 'line_no', 'inventory': 'on_hand_qty', 'monthly_demand': 'demand_qty',
                          'product': 'base_unit', 'material': 'base_unit'}[entity]
                if target in original:
                    changed = original[target]
                    changed['values'][0] = { 'line_no': '2.7', 'on_hand_qty': '1.200,23', 'demand_qty': '3.472,33',
                                            'base_unit': '팩'}[target]
                    changed.update(expected=None, state='TRANSFORM_REQUIRED', scenario='format_transform')
            if width == 4 and len(roles) >= 2 and i % 3 == 1:
                source, extra = columns[:2]
                extra['header'] = source['header']
                for column in (source, extra):
                    column.update(expected=None, semantic=None, state='HOLD', scenario='ambiguous_duplicate')
            if width == 6:
                rng.choice(columns)['values'][0] = ''
            route = entity
            if width == 7 and i % 3 == 1:
                route = ROUTE[entity]
                for column in columns:
                    column.update(expected=None, semantic=None, state='HOLD', scenario='wrong_route')
            rng.shuffle(columns)
            title = f'{("진행 장표", "Inventory feed file", "작성용 전산 탭", "Verification run")[track]} {TITLES[entity]}'
            doc = {'id': f'phase6-{split}-{entity}-{i:02d}', 'family': f'phase6:{split}:{entity}:{i % 8}',
                   'entity': route, 'document_type': entity, 'title': title, 'columns': columns}
            doc['csv_sha256'] = sha256(csv_bytes(doc)).hexdigest()
            docs.append(doc)
    return {'version': VERSION, 'split': split, 'documents': docs}


def validate(payload):
    split = payload['split']
    if payload['version'] != VERSION or len(payload['documents']) != SPLITS[split][1] * len(ENTITY_FIELDS):
        raise ValueError('Unexpected panel shape')
    ids, families, headers = set(), set(), set()
    states, roles = Counter(), Counter()
    standard = {norm(field) for fields in ENTITY_FIELDS.values() for field in fields}
    prior = {norm(name) for names in P5_HEADERS.values() for name in names}
    for doc in payload['documents']:
        duplicates = Counter(norm(col['header']) for col in doc['columns'])
        gold = []
        if doc['id'] in ids or sha256(csv_bytes(doc)).hexdigest() != doc['csv_sha256']:
            raise ValueError('Duplicate ID or original file mismatch')
        for col in doc['columns']:
            header = norm(col['header'])
            state, semantic, direct = col['state'], col['semantic'], col['expected']
            if (state, bool(semantic), bool(direct)) not in {('DIRECT_MAPPING_READY', True, True),
                    ('TRANSFORM_REQUIRED', True, False), ('HOLD', False, False)}:
                raise ValueError('Inconsistent semantic vs direct gold')
            if semantic and (semantic not in ENTITY_FIELDS[doc['entity']] or duplicates[header] != 1):
                raise ValueError('Wrong or ambiguous semantic field')
            if header not in standard:
                if header in prior:
                    raise ValueError('Phase 5 nonstandard header copied into Phase 6')
                headers.add(header)
            states[state] += 1
            roles[col['scenario']] += 1
            if semantic:
                gold.append(semantic)
        if len(set(gold)) != len(gold):
            raise ValueError('Duplicate gold destination')
        ids.add(doc['id'])
        families.add(doc['family'])
    info = {'sha256': sha(payload), 'documents': len(ids), 'families': len(families), 'states': dict(states), 'scenarios': dict(roles)}
    return info, headers


def freeze(output):
    output.mkdir(parents=True, exist_ok=True)
    manifest, prior = {'version': VERSION, 'splits': {}}, set()
    for split in SPLITS:
        payload = panel(split)
        info, headers = validate(payload)
        if headers & prior:
            raise ValueError('Nonstandard headers overlap between Phase 6 splits')
        prior.update(headers)
        manifest['splits'][split] = info
        write_frozen(output / f'{split}.json', payload)
    write_frozen(output / 'dataset-manifest.json', manifest)
    return manifest


def read_panel(output, split):
    payload = json.loads((output / f'{split}.json').read_bytes())
    manifest = json.loads((output / 'dataset-manifest.json').read_bytes())
    info, _ = validate(payload)
    if payload['split'] != split or info != manifest['splits'][split]:
        raise ValueError('Phase 6 split digest does not match manifest')
    return payload['documents'], info['sha256']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output), ensure_ascii=False, indent=2))
