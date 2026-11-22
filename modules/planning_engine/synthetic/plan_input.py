"""㈜충파모제지 upload·입고 예정·예측 결과 → 계획 계산 코어 내부 형식 입력 JSON (SYNTHETIC).

입력: data/upload/01~09, data/derived/scheduled_receipts.csv, data/forecast/forecast.json
출력: modules/planning_engine/tests/chungpamo/plan_input.json (테스트용 고정 입력, 커밋 대상)

팀 계약 PlanningInput 변환부가 아니다. 계산 코어를 충파모 전체 데이터로 검증하려고 같은 규칙으로 직접 조립한다.
- 기준일 2026-12-31, 계획 2027-01~03 (규칙서 §0 3개월)
- BOM은 2027-01-01에 유효한 APPROVED·활성 버전 1개(여러 개면 실패)
- 라우팅 resource_requirements(포장 작업자 LB1 등)는 같은 제품의 별도 자원 행으로 펼친다
- 같은 제품·자원 행이 둘 이상이면 실패(내부 형식은 제품·자원당 1행)
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data'
OUT = HERE.parent / 'tests' / 'chungpamo' / 'plan_input.json'
AS_OF = '2026-12-31'
MONTHS = ['2027-01', '2027-02', '2027-03']


def rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def build() -> dict:
    up = DATA / 'upload'
    inventory = {(r['품목구분'], r['품목코드']): r for r in rows(up / '04_inventory.csv')}
    products = []
    for r in rows(up / '01_products.csv'):
        item = {'id': r['제품코드'], 'unit': r['단위'], 'safety_stock': int(r['안전재고'])}
        inv = inventory.get(('PRODUCT', r['제품코드']))
        if inv is not None:
            if inv['단위'] != r['단위']:
                item['inventory_unit'] = inv['단위']
            item['on_hand'], item['allocated'] = int(inv['현재고']), int(inv['할당재고'])
        products.append(item)
    materials = []
    for r in rows(up / '02_materials.csv'):
        item = {'id': r['자재코드'], 'unit': r['단위'], 'safety_stock': r['안전재고']}
        inv = inventory.get(('MATERIAL', r['자재코드']))
        if inv is not None:
            if inv['단위'] != r['단위']:
                item['inventory_unit'] = inv['단위']
            item['on_hand'], item['allocated'] = inv['현재고'], inv['할당재고']
        materials.append(item)

    forecast_doc = json.loads((DATA / 'forecast' / 'forecast.json').read_text(encoding='utf-8'))
    forecast = {'P50': {}, 'P80': {}}
    by_key = {(f['product_id'], f['target_month']): f for f in forecast_doc['forecasts']}
    for p in products:
        for q in ('P50', 'P80'):
            forecast[q][p['id']] = [by_key[(p['id'], m)][q.lower()] for m in MONTHS if (p['id'], m) in by_key]

    budgets = {(r['resource_id'], r['period']): r for r in rows(up / '08_capacity_hours_budgets.csv')}
    resources = []
    for r in rows(up / '06_capacity_resources.csv'):
        b = [budgets.get((r['resource_id'], m)) for m in MONTHS]
        item = {'id': r['resource_id'], 'time_basis': r['time_basis'],
                'regular': [None if x is None else x['regular_hours'] for x in b],
                'overtime': [None if x is None else x['overtime_hours_limit'] for x in b]}
        bases = {x['availability_basis'] for x in b if x is not None}
        if bases:
            item['availability_basis'] = bases.pop() if len(bases) == 1 else 'MIXED'
        resources.append(item)

    routing: dict[str, dict] = {}
    for r in rows(up / '09_routing_steps.csv'):
        lines = [r] + json.loads(r['resource_requirements'] or '[]')
        for line in lines:
            step = {'run_time': line['run_time'], 'reference_qty': line['reference_qty'],
                    'time_unit': line['time_unit']}
            if line.get('setup_time'):
                step['setup_time'] = line['setup_time']
            if line.get('alternative_group_ref'):
                step['alternative_group'] = line['alternative_group_ref']
            steps = routing.setdefault(r['product_id'], {})
            if line['resource_id'] in steps:
                raise ValueError(f'중복 자원 행: {r["product_id"]} {line["resource_id"]}')
            steps[line['resource_id']] = step

    limits: dict[str, list] = {}
    for r in rows(up / '07_capacity_quantity_limits.csv'):
        limits.setdefault(r['product_id'], [None] * len(MONTHS))[MONTHS.index(r['period'])] = int(r['limit_qty'])

    start = MONTHS[0] + '-01'
    bom: dict[str, list] = {}
    versions: dict[str, set] = {}
    for r in rows(up / '03_bom.csv'):
        valid = r['상태'] == 'APPROVED' and r['활성'] == 'Y' and r['유효시작일'] <= start and \
            (not r['유효종료일'] or r['유효종료일'] >= start)
        if not valid:
            continue
        versions.setdefault(r['제품코드'], set()).add(r['버전'])
        bom.setdefault(r['제품코드'], []).append({
            'material': r['구성품코드'], 'qty': r['소요량'], 'base_qty': r['기준수량'], 'scrap_rate': r['스크랩률'],
            **({'component_type': 'PRODUCT'} if r['구성유형'] == 'PRODUCT' else {})})
    ambiguous = [p for p, v in versions.items() if len(v) > 1]
    if ambiguous:
        raise ValueError(f'유효 BOM 버전이 여러 개: {ambiguous}')

    receipts = [{'po_id': r['po_id'], 'material': r['material_id'], 'open_qty': r['qty'], 'unit': r['unit'],
                 'expected_date': r['expected_date']} for r in rows(DATA / 'derived' / 'scheduled_receipts.csv')]

    sources = sorted([*(up.glob('0*.csv')), DATA / 'derived' / 'scheduled_receipts.csv'])
    digest = hashlib.sha256()
    for s in sources:
        digest.update(s.name.encode() + b'\0' + s.read_bytes().replace(b'\r\n', b'\n'))
    return {
        'description': '㈜충파모제지(SYNTHETIC) 2027-01~03 계획 계산 입력. synthetic/plan_input.py로 생성. 손으로 고치지 말 것',
        'dataset_id': 'CHUNGPAMO-2027',
        'source_digest': 'sha256:' + digest.hexdigest(),
        'forecast_input_digest': forecast_doc['run']['input_digest'],
        'forecast_run': forecast_doc['run']['engine'],
        'months': MONTHS, 'as_of': AS_OF, 'demand_multiplier': '1',
        'products': products, 'forecast': forecast, 'resources': resources, 'routing': routing,
        'quantity_limits': limits, 'materials': materials, 'bom': bom, 'receipts': receipts,
    }


def main() -> None:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{OUT}: 제품 {len(data["products"])}, 자원 {len(data["resources"])}, 자재 {len(data["materials"])}, '
          f'입고 {len(data["receipts"])}')


if __name__ == '__main__':
    main()
