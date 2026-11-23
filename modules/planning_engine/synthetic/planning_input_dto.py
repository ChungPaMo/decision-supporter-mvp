"""㈜충파모제지 upload·입고 예정·예측 → 팀 계약 PlanningInput JSON (SYNTHETIC 시험 입력).

입력: data/upload/01~09, data/derived/scheduled_receipts.csv, data/forecast/forecast.json
출력: modules/planning_engine/tests/chungpamo/planning_input.json (테스트용 고정 입력, 커밋 대상)

백엔드 SQL 조립을 대신하지 않는다. 이 PC는 DB를 쓰지 않으므로, 같은 원본으로 계약 DTO 모양의 입력을 만들어
변환부(`engine/adapter.py`)가 PlanningInput부터 PlanningOutput까지 독립 정답(expected.json)과 같은 답을 내는지 확인한다.
- UUID는 파일 이름에서 만든 고정 값(uuid5)이고 DB 기록이 아니다. source_sha256은 실제 파일 SHA-256이다.
- 기준일 2026-12-31, 계획 2027-01부터 3개월. missing_inputs는 비워 두고 누락 경우는 테스트에서 따로 만든다.
실행: PYTHONUTF8=1 .venv/Scripts/python.exe modules/planning_engine/synthetic/planning_input_dto.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data'
OUT = HERE.parent / 'tests' / 'chungpamo' / 'planning_input.json'
AS_OF = '2026-12-31'
NS = uuid.UUID('6f1c1d1e-2027-4c0a-9d00-000000000000')
FILES = {  # 파일 → 승인 배치 entity
    '01_products.csv': 'product', '02_materials.csv': 'material', '03_bom.csv': 'bom', '04_inventory.csv': 'inventory',
    '05_monthly_demand.csv': 'monthly_demand', '06_capacity_resources.csv': 'capacity',
    '07_capacity_quantity_limits.csv': 'capacity', '08_capacity_hours_budgets.csv': 'capacity',
    '09_routing_steps.csv': 'routing', 'scheduled_receipts.csv': 'scheduled_receipt',
}


def rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def none(value: str):
    return value if value != '' else None


def build() -> dict:
    up = DATA / 'upload'
    paths = {name: (DATA / 'derived' / name if name == 'scheduled_receipts.csv' else up / name) for name in FILES}
    batch = {name: str(uuid.uuid5(NS, name)) for name in FILES}
    sources = [{'batch_id': batch[name], 'batch_version': 1, 'entity': FILES[name],
                'source_sha256': hashlib.sha256(paths[name].read_bytes()).hexdigest(),
                'result_digest': hashlib.sha256(b'result\0' + paths[name].read_bytes()).hexdigest(),
                'approved_at': '2026-12-31T00:00:00Z'} for name in FILES]

    products = [{'product_id': r['제품코드'], 'product_name': r['제품명'], 'base_unit': r['단위'],
                 'product_type': none(r['제품유형']), 'safety_stock_qty': r['안전재고'], 'source_type': 'SYNTHETIC',
                 'batch_id': batch['01_products.csv']} for r in rows(up / '01_products.csv')]
    materials = [{'material_id': r['자재코드'], 'material_name': r['자재명'], 'base_unit': r['단위'],
                  'safety_stock_qty': r['안전재고'], 'source_type': 'SYNTHETIC', 'batch_id': batch['02_materials.csv']}
                 for r in rows(up / '02_materials.csv')]
    boms: dict[tuple[str, str], dict] = {}
    for r in rows(up / '03_bom.csv'):
        b = boms.setdefault((r['BOM코드'], r['버전']), {
            'header': {'bom_id': r['BOM코드'], 'product_id': r['제품코드'], 'bom_version': r['버전'], 'status': r['상태'],
                       'is_active': r['활성'] == 'Y', 'valid_from': r['유효시작일'], 'valid_to': none(r['유효종료일']),
                       'base_qty': r['기준수량']},
            'lines': [], 'source_type': 'SYNTHETIC', 'batch_id': batch['03_bom.csv']})
        b['lines'].append({'bom_id': r['BOM코드'], 'line_no': int(r['순번']), 'component_type': r['구성유형'],
                           'component_id': r['구성품코드'], 'qty_per': r['소요량'], 'unit': r['단위'],
                           'scrap_rate': r['스크랩률']})
    inventory = [{'item_type': r['품목구분'], 'item_id': r['품목코드'], 'as_of_date': r['기준일'],
                  'on_hand_qty': r['현재고'], 'allocated_qty': r['할당재고'], 'unit': r['단위'],
                  'source_type': 'SYNTHETIC', 'batch_id': batch['04_inventory.csv']} for r in rows(up / '04_inventory.csv')]

    forecast_doc = json.loads((DATA / 'forecast' / 'forecast.json').read_text(encoding='utf-8'))
    months = sorted({f['target_month'] for f in forecast_doc['forecasts']})
    unit = {p['product_id']: p['base_unit'] for p in products}
    forecast_rows = [{'product_id': f['product_id'], 'target_month': f['target_month'], 'p50': f['p50'], 'p80': f['p80'],
                      'p90': f['p90'], 'unit': unit[f['product_id']]} for f in forecast_doc['forecasts']]

    resources = [{'resource_id': r['resource_id'], 'resource_name': r['resource_name'], 'kind': r['kind'],
                  'time_basis': r['time_basis'], 'parallel_units': int(r['parallel_units'])}
                 for r in rows(up / '06_capacity_resources.csv')]
    limits = [{**r, 'operation_id': none(r['operation_id'])} for r in rows(up / '07_capacity_quantity_limits.csv')]
    budgets = [{**r, 'overtime_hours_limit': none(r['overtime_hours_limit']), 'calendar_ref': none(r['calendar_ref'])}
               for r in rows(up / '08_capacity_hours_budgets.csv')]
    steps = []
    for r in rows(up / '09_routing_steps.csv'):
        step = {k: none(v) for k, v in r.items()}
        step['concurrent_units'] = None if step['concurrent_units'] is None else int(step['concurrent_units'])
        step['predecessor_step_ids'] = json.loads(r['predecessor_step_ids'] or '[]')
        step['resource_requirements'] = json.loads(r['resource_requirements'] or '[]')
        steps.append(step)
    common = {'resources': resources, 'unresolved_policy_refs': []}
    receipts = [{'po_id': r['po_id'], 'material_id': r['material_id'], 'open_qty': r['qty'], 'unit': r['unit'],
                 'expected_date': r['expected_date'], 'supplier_id': none(r['supplier_id']),
                 'batch_id': batch['scheduled_receipts.csv']} for r in rows(paths['scheduled_receipts.csv'])]
    return {
        '_note': '㈜충파모제지(SYNTHETIC) 계약 PlanningInput 시험 입력. synthetic/planning_input_dto.py로 생성. '
                 'UUID는 고정 가짜 값이며 DB 기록이 아니다. 손으로 고치지 말 것',
        'payload': {
            'dataset_id': 'CHUNGPAMO-2027',
            'command': {'dataset_id': 'CHUNGPAMO-2027', 'forecast_execution_id': str(uuid.uuid5(NS, 'forecast')),
                        'product_ids': [p['product_id'] for p in products], 'target_month': months[0],
                        'horizon_months': len(months), 'as_of_date': AS_OF, 'scenario': 'BASE'},
            'forecast_input_digest': forecast_doc['run']['input_digest'],
            'forecast_model_version': forecast_doc['run']['quantile_model_version'],
            'forecast_rows': forecast_rows,
            'approved_inputs': {'products': products, 'materials': materials, 'boms': list(boms.values()),
                                'inventory': inventory, 'sources': sources},
            'scheduled_receipts': receipts,
            'capacity_snapshot': {**common, 'quantity_limits': limits, 'hours_budgets': budgets, 'routing_steps': []},
            'routing_snapshot': {**common, 'quantity_limits': [], 'hours_budgets': [], 'routing_steps': steps},
            'missing_inputs': [],
        },
    }


def main() -> None:
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    p = doc['payload']
    print(f'{OUT}: 제품 {len(p["command"]["product_ids"])}, 예측 {len(p["forecast_rows"])}행, '
          f'라우팅 {len(p["routing_snapshot"]["routing_steps"])}행, 입고 {len(p["scheduled_receipts"])}건')


if __name__ == '__main__':
    main()
