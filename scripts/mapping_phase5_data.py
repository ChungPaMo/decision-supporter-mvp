"""Freeze independent synthetic schema-matching panels before evaluating policies."""
import argparse
from collections import Counter
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import random

from app.ingest.mapping import ENTITY_FIELDS
from mapping_research_data import FIELDS, canonical, csv_bytes, norm, sha


OUT = Path('.artifacts/mapping-research/phase5')
VERSION = 'synthetic-mapping-phase5-v1'
# Four independently authored vocabulary tracks. Common standardized headers are included explicitly.
HEADERS = {
    'product_id': ('출고품 식별표', '온라인 SKU번호', 'Finished good lookup', '판매카탈로그 관리키'),
    'product_name': ('Sellable item wording', '완성품 인쇄호칭', '제품 라벨명', 'Customer-facing item designation'),
    'base_unit': ('재고 기준UOM', 'Unit of catalog control', '기본 계상 단위', 'Default stocking measure'),
    'product_type': ('완성품 속성 분류', 'Catalog article class', '품목 카테고리', '판매품종 관리군'),
    'material_id': ('Ingredient identification', '투입 원료 재질번호', 'Purchased material ref', '자재관리 품목키'),
    'material_name': ('원료 표시 이름', '구매품 호칭', 'Material registry label', '생산투입 원료 명칭'),
    'period': ('Monthly plan slice', '출고예정 수요월', '연월 버킷', 'Sales plan fiscal month'),
    'demand_qty': ('Forecast units per month', '판매 계획 물량', 'Consolidated monthly demand units', '월간 고객 수요 총량'),
    'unit': ('재고수불 계량 단위', 'Column quantity UOM', '계획 물량 표기 단위', 'Stock movement measure'),
    'safety_stock_qty': ('유지 재고 최소분', 'Inventory safety buffer', '품절 대응 재고량', 'Stock level for service buffer'),
    'bom_id': ('조립 사양 번호', 'BOM specification identifier', 'Manufacturing recipe key', '소요량 명세 식별번호'),
    'bom_version': ('BOM version edition', '구성 개정 표기', 'Assembly revision ref', '투입명세 개정코드'),
    'status': ('명세 결재 상태', 'Assembly drawing approval state', 'Release approval status', '사양 확정 여부'),
    'is_active': ('사양 적용 중', 'Recipe enabled bit', '조립표 사용 설정', 'Current use flag'),
    'valid_from': ('조립 사양 시작일', 'Use from calendar', 'Date effective since', '생산 사양 적용 개시일'),
    'valid_to': ('조립 사양 종료일', 'Use until calendar', 'Date after last effective span', '생산 사양 효력 만료일'),
    'base_qty': ('생산 1회 기준 산출', 'Output per reference batch', 'Assembly basis output', '모품 산출 기준수량'),
    'line_no': ('부품행 번호', 'Assembly line sequence', 'Component row ordinal', '구성품 라인 순번'),
    'component_type': ('투입 종류 분류', 'Component material kind', 'BOM child item category', '구성품 재종 분류'),
    'component_id': ('투입품 원료코드', 'Child component identifier', 'BOM child material ref', '구성부품 재고 참조키'),
    'qty_per': ('산출량당 구성품 소모량', 'Units of part per finished item', 'Consumption multiplier', '조립 1단위 자재 소요량'),
    'scrap_rate': ('BOM 폐기율', 'Ingredient yield loss ratio', '투입 손실률', 'Component scrap fraction'),
    'item_type': ('보유대상 재고 분류', 'Warehouse item kind', '재고상품 자재 구분', 'Stock item material or product'),
    'item_id': ('보관대상 식별 코드', 'Warehouse tracking SKU', 'Stock article ID', '실사 기준 품번'),
    'as_of_date': ('실사 기준일', 'Physical count date', 'Warehouse observation date', '재고 시점 기준일'),
    'on_hand_qty': ('물리 재고 합계', 'Stock before commitments', 'Physical qty before deductions', '보관중 총 실물수량'),
    'allocated_qty': ('예약 묶음 재고량', 'Units committed to picks', 'Committed inventory qty', '출고용 기배정수량'),
    'available_qty': ('불출 가능 실재고', 'Free-to-use stock', 'Stock after reservations', '예약 차감 가용량'),
}
DISTRACTORS = {
    'purchase': ('조달처 발주 잔량', 'Outstanding procurement units', 'Replenishment order qty', '구매처 PO 개수'),
    'returns': ('회수 접수 수량', 'Return authorization units', 'Refunded goods count', '역물류 반송 물량'),
    'production': ('제조 완료 실적량', 'Build completion units', 'Actual factory output', '라인 완성 실적수량'),
    'money': ('청구 정산 금액', 'Amount net of tax', 'Invoiced contract value', '납품매출 원화금액'),
    'customer': ('납품 상대방 번호', 'Invoice account ref', 'Customer organization identifier', '거래처 원장 코드'),
    'order_date': ('원장 거래 등록일', 'Individual order entered', 'Order placement timestamp', '거래접수 일자'),
    'transform': ('주문 원장 건별 수량', 'Transaction line demand qty', 'Sales ledger daily quantity', '청구 건별 고객요청 수량'),
    'note': ('창고 운영메모', 'Reviewer remarks', 'Workbook note', '비고 검토 란'),
    'unknown': ('보조 수치', 'Unspecified measure', 'Unassigned code', '기타 계수'),
}
# Development, calibration and holdout differ in vocabulary, row count, alphabets and formatter mix.
SPLITS = {'train_extra': (0, 8, 59101), 'development': (1, 12, 59102),
          'calibration': (2, 12, 59103), 'holdout': (3, 36, 59104)}


def generate_values(role, index, size, rng, track):
    kind = FIELDS.get(role, ({
        'money': 'money', 'customer': 'generic_code', 'order_date': 'date', 'note': 'name',
    }.get(role, 'number'), ''))[0]
    if kind.endswith('_code'):
        root = 'P' if role == 'product_id' else 'R' if role in ('component_id', 'material_id') else 'X'
        return [f'{track + 1:02}{i % 7 + index * 9:05}' if index % 4 == 1 else f'{root}{track + 2}-{i % 7 + index * 9:04}'
                for i in range(size)]
    if kind in ('date', 'month'):
        days = [date(2026 + track, 1, 1) + timedelta(days=31 * i if kind == 'month' else 3 * i + 1) for i in range(size)]
        if kind == 'month':
            return [day.strftime(('%Y-%m', '%Y%m', '%Y/%m', '%Y-%m-01')[index % 4]) for day in days]
        if role == 'valid_to':
            days = [day + timedelta(days=100) for day in days]
        return [day.strftime(('%Y-%m-%d', '%Y/%m/%d', '%Y%m%d', '%Y.%m.%d')[index % 4]) for day in days]
    if kind == 'unit':
        return [('EA', 'kg', '개', 'g')[index % 4]] * size
    if kind == 'category':
        options = ('FINISHED', 'SEMI_FINISHED') if role == 'product_type' else ('PRODUCT', 'MATERIAL')
        return [options[i % 2] for i in range(size)]
    if kind == 'status':
        return [('APPROVED', 'DRAFT')[i % 2] for i in range(size)]
    if kind == 'bool':
        return [('Y', 'N')[i % 2] for i in range(size)]
    if kind == 'version':
        return [f'R-{i // 2 + 1}' for i in range(size)]
    if kind == 'ratio':
        return [f'0.{i % 13:02}' for i in range(size)]
    if kind == 'name':
        return [f'{("시트부품", "Wire bracket", "슬리브", "Pressed insert")[(index + i) % 4]} {track + 2}-{i % 7}'
                for i in range(size)]
    if kind == 'money':
        # Alternates explicit currency and ordinary numeric amounts that need role evidence.
        return [f'₩{i * 183 + 10:,}' if index % 2 else str(i * 183 + 10) for i in range(size)]
    if role == 'line_no':
        return [str(i + 1) for i in range(size)]
    if role == 'base_qty':
        return [str(12 + index % 4)] * size
    values = [rng.randint(1, 4200) for _ in range(size)]
    return [f'{value:,}' if index % 4 == 0 else f'{value}.{i % 7}' if index % 4 == 2 else str(value)
            for i, value in enumerate(values)]


def panel(split):
    track, size, seed = SPLITS[split]
    rng = random.Random(seed)
    docs = []
    for entity in sorted(ENTITY_FIELDS):
        for i in range(size):
            regime = i % 6
            nrows = (7, 9, 11, 15)[(track + i) % 4]
            fields = ENTITY_FIELDS[entity]
            roles = [role for role, spec in fields.items() if spec['required'] or rng.random() < .75]
            if regime == 3:
                roles.remove(next(role for role in roles if fields[role]['required']))
            negative = ('purchase', 'returns', 'production', 'money', 'customer', 'order_date', 'transform', 'note', 'unknown')
            columns = []
            for role in roles + rng.sample(negative, 3 if entity == 'monthly_demand' else 2):
                names = HEADERS if role in fields else DISTRACTORS
                header = role if role in fields and (regime == 0 or (regime == 5 and i // 6 % 2 == 0)) else names[role][track]
                if regime == 2:
                    header = header.replace(' ', ' _ ')
                data = generate_values(role, i, nrows, rng, track)
                columns.append({'header': header, 'values': data, 'expected': role if role in fields else None,
                                'scenario': 'direct' if role in fields else role})
            by_field = {col['expected']: col for col in columns if col['expected']}
            inventory = ('on_hand_qty', 'allocated_qty', 'available_qty')
            if all(field in by_field for field in inventory):
                reserved = [rng.randint(0, 120) for _ in range(nrows)]
                free = [rng.randint(30, 250) for _ in range(nrows)]
                for field, values in zip(inventory, ([a + b for a, b in zip(reserved, free)], reserved, free), strict=True):
                    by_field[field]['values'] = list(map(str, values))
            if regime == 4:
                item = rng.choice(columns)
                item['values'][1] = ''
            if i % 11 == 8 and entity == 'monthly_demand' and 'demand_qty' in by_field:
                by_field['demand_qty'].update(expected=None, scenario='mixed_units_or_text')
                by_field['demand_qty']['values'][0] = 'check'
            if i % 13 == 5 and len(columns) > 4:
                first, second = columns[:2]
                first.update(expected=None, scenario='ambiguous_duplicate')
                second.update(header=first['header'], expected=None, scenario='ambiguous_duplicate')
            title = ('원천 자료', 'Source register', '기초자료 입력', 'Synthetic operations ledger')[track]
            title += ' ' + {'monthly_demand': '월 수요', 'inventory': '실사 재고', 'bom': '구성명세',
                            'material': '원재료 기본', 'product': '완제품 기준'}[entity]
            route = entity
            if i % 17 == 11:
                route = next(value for value in sorted(ENTITY_FIELDS) if value not in (entity, 'bom'))
                for item in columns:
                    item.update(expected=None, scenario='wrong_route')
            rng.shuffle(columns)
            doc = {'id': f'phase5-{split}-{entity}-{i:02d}', 'family': f'phase5:{split}:{entity}:{regime}',
                   'title': title, 'entity': route, 'document_type': entity, 'columns': columns}
            doc['csv_sha256'] = sha256(csv_bytes(doc)).hexdigest()
            docs.append(doc)
    return {'version': VERSION, 'split': split, 'documents': docs}


def validate(payload):
    split = payload['split']
    if payload['version'] != VERSION or len(payload['documents']) != SPLITS[split][1] * len(ENTITY_FIELDS):
        raise ValueError('Unexpected synthetic split shape')
    ids, families, nonstandard, kinds = set(), set(), set(), Counter()
    for doc in payload['documents']:
        rows = doc['columns']
        gold = [row['expected'] for row in rows if row['expected']]
        duplicates = Counter(norm(row['header']) for row in rows)
        if (doc['id'] in ids or len(gold) != len(set(gold)) or set(gold) - ENTITY_FIELDS[doc['entity']].keys()
                or any(duplicates[norm(row['header'])] != 1 for row in rows if row['expected'])
                or (doc['entity'] != doc['document_type'] and gold)
                or sha256(csv_bytes(doc)).hexdigest() != doc['csv_sha256']):
            raise ValueError('Synthetic label or original-cell digest check failed')
        ids.add(doc['id'])
        families.add(doc['family'])
        nonstandard.update(norm(row['header']) for row in rows if row['header'] not in HEADERS)
        kinds.update(row['scenario'] for row in rows)
    return {'sha256': sha(payload), 'documents': len(ids), 'families': sorted(families), 'labels': dict(kinds)}, nonstandard


def freeze(output=OUT):
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'version': VERSION, 'splits': {}}
    previous = set()
    for split in SPLITS:
        payload = panel(split)
        info, headers = validate(payload)
        if previous & headers:
            raise ValueError('Independent vocabulary reused across Phase 5 splits')
        previous.update(headers)
        manifest['splits'][split] = info
        write_frozen(output / f'{split}.json', payload)
    write_frozen(output / 'dataset-manifest.json', manifest)
    return manifest


def write_frozen(path, payload):
    expected = canonical(payload) + b'\n'
    if path.exists():
        if path.read_bytes() != expected:
            raise ValueError(f'Frozen artifact would change: {path.name}')
    else:
        with path.open('xb') as stream:
            stream.write(expected)


def read_panel(output, split):
    manifest = json.loads((output / 'dataset-manifest.json').read_bytes())
    payload = json.loads((output / f'{split}.json').read_bytes())
    info, _ = validate(payload)
    if payload['split'] != split or manifest['splits'][split] != info:
        raise ValueError('Phase 5 panel differs from the frozen manifest')
    return payload['documents'], info['sha256']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output), ensure_ascii=True))
