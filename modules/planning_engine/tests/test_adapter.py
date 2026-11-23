"""팀 계약 변환부: PlanningInput → 계산 코어 → PlanningOutput (engine/adapter.py, PLANNING_RULES v0.4 §11).

- 공식 합성 3개월: 계약 입력(tests/chungpamo/planning_input.json)으로 돌린 결과가 독립 정답(expected.json)과 같다
- 출력은 계약 DTO 검증과 백엔드 공통 출력 검사(validate_pair, Preview·저장·상세가 함께 쓰는 검사)를 통과한다
- 1·3·6·12개월(연도 경계 포함)은 손계산 가능한 작은 입력으로 확인한다. 기대값은 주석의 손계산
"""
import copy
import json
from fractions import Fraction
from pathlib import Path

import pytest

from app.integrations.planning_validation import validate_pair
from contracts.interfaces.modules import PlanningInput
from engine.adapter import run
from engine.planning_core import PLAN_SPECS, decimal_str
from what_if.core import run_what_if

HERE = Path(__file__).parent / 'chungpamo'
OFFICIAL = json.loads((HERE / 'planning_input.json').read_text(encoding='utf-8'))['payload']
EXPECTED = json.loads((HERE / 'expected.json').read_text(encoding='utf-8'))
PARENT = '00000000-0000-4000-8000-0000000000aa'


def checked(payload: dict):
    """계약 입력 검증 → 실행 → 계약 출력 + 백엔드 공통 출력 검사."""
    request = PlanningInput.model_validate(payload)
    out = run(request.model_copy(deep=True))
    validate_pair(request, out)
    return out


def production(out, plan_id):
    plan = next(p for p in out.plans if p.plan_id == plan_id)
    got: dict[str, list[int]] = {}
    for row in plan.production:
        got.setdefault(row.product_id, []).append(int(row.production_qty))
    return got


def feasibility(out):
    return {p.plan_id: p.feasibility for p in out.plans}


def dec(value) -> str | None:
    return None if value is None else decimal_str(Fraction(value))


# ---------- 공식 합성 3개월 ----------

def test_official_three_months_match_independent_answer():
    out = checked(OFFICIAL)
    assert out.status == 'OK' and out.errors == [] and out.unverified == []
    for plan_id, _, _ in PLAN_SPECS:
        exp = EXPECTED[plan_id]
        assert production(out, plan_id) == exp['production'], plan_id
        assert feasibility(out)[plan_id] == exp['feasibility'], plan_id
        got = {e.constraint_id: e for e in out.constraint_evaluations if e.plan_id == plan_id}
        assert set(got) == {e['constraint_id'] for e in exp['evaluations']}, plan_id
        for e in exp['evaluations']:
            g = got[e['constraint_id']]
            used = e.get('used_value')
            if e['constraint_id'].startswith('SS-') and used is not None and Fraction(used) < 0:
                used = '0'  # 계약 수량은 비음수(C05)
            assert (g.status, sorted(g.reason_codes)) == (e['status'], sorted(e['reason_codes'])), e['constraint_id']
            assert (g.limit_value, g.used_value) == (dec(e.get('limit_value')), dec(used)), e['constraint_id']
        rows = {(m.material_id, m.period): m for m in out.material_requirements if m.plan_id == plan_id}
        for kid, exp_m in exp['material_requirements'].items():
            for i, month in enumerate(['2027-01', '2027-02', '2027-03']):
                m = rows[(kid, month)]
                assert (m.required_qty, m.available_qty, m.shortage_qty) == (
                    dec(exp_m['required'][i]), dec(exp_m['available'][i]), dec(exp_m['shortage'][i])), (plan_id, kid, month)


def test_official_without_receipt_feed_is_calculated_but_never_feasible():
    """실제 DB 현재 상태: 입고 예정 공급 미연결(null) + 백엔드 missing_inputs."""
    payload = copy.deepcopy(OFFICIAL)
    payload['scheduled_receipts'] = None
    payload['missing_inputs'] = ['POLICY_NOT_CONFIRMED', 'RECEIPT_SOURCE_UNAVAILABLE']
    out = checked(payload)
    assert out.status == 'OK'
    assert [i.code for i in out.unverified] == ['RECEIPT_SOURCE_UNAVAILABLE', 'POLICY_NOT_CONFIRMED']
    assert 'FEASIBLE' not in feasibility(out).values()
    # 1/20 원단 10,000 kg 입고가 빠져 1월 MR-N3 가용이 10,000 줄어든다
    base = {(m.plan_id, m.material_id, m.period): m for m in checked(OFFICIAL).material_requirements}
    now = {(m.plan_id, m.material_id, m.period): m for m in out.material_requirements}
    key = ('BASELINE', 'MR-N3', '2027-01')
    assert Fraction(base[key].available_qty) - Fraction(now[key].available_qty) == 10000


def what_if_payload(overrides):
    payload = copy.deepcopy(OFFICIAL)
    payload['command'].update(scenario='WHAT_IF', base_plan_execution_id=PARENT, overrides=overrides)
    return payload


def test_official_what_if_recalculates_three_plans_like_the_core():
    overrides = {'overtime_hours_limit.SAW1.2027-02': '80', 'receipt_qty.PO-2701-001': '0'}
    out = run(PlanningInput.model_validate(what_if_payload(overrides)))
    assert out.status == 'OK' and {p.plan_type for p in out.plans} == {'BASELINE', 'STABLE', 'COST_SAVING'}
    core = run_what_if(json.loads((HERE / 'plan_input.json').read_text(encoding='utf-8')), overrides)
    for plan_id, _, _ in PLAN_SPECS:
        assert production(out, plan_id) == core.scenario[plan_id].production
        assert feasibility(out)[plan_id] == core.scenario[plan_id].feasibility


def test_invalid_what_if_returns_input_invalid_without_plans():
    out = run(PlanningInput.model_validate(what_if_payload({'overtime_hours_limit.NOPE.2027-02': '1'})))
    assert out.status == 'INPUT_INVALID' and out.plans == []
    assert [(e.code, e.input_refs) for e in out.errors] == [('WHATIF_INVALID', ['overtime_hours_limit.NOPE.2027-02', 'resource'])]


# ---------- 작은 입력: 기간 1·3·6·12개월 ----------

def months_from(start: str, n: int) -> list[str]:
    y, m = map(int, start.split('-'))
    return [f'{y + (m - 1 + i) // 12:04d}-{(m - 1 + i) % 12 + 1:02d}' for i in range(n)]


def small(n: int, start: str = '2027-01', last_demand: str = '150') -> dict:
    """제품 A(재고 0, SS 0), 설비 S(정규 100 + 잔업 20 h, 1개 1 h), 자재 K(1개당 2 kg, 재고 넉넉).
    수요는 매달 100, 마지막 달만 last_demand. 입고 공급은 연결됐고 해당 발주 없음([])."""
    months = months_from(start, n)
    b = {k: f'00000000-0000-4000-8000-{i:012d}' for i, k in enumerate(['product', 'material', 'bom', 'inventory', 'capacity', 'routing', 'demand'], 1)}
    src = lambda k, entity: {'batch_id': b[k], 'batch_version': 1, 'entity': entity, 'source_sha256': '0' * 64,
                             'result_digest': '1' * 64, 'approved_at': '2026-12-31T00:00:00Z'}
    res = {'resource_id': 'S', 'resource_name': 'saw', 'kind': 'EQUIPMENT', 'time_basis': 'MACHINE_HOUR', 'parallel_units': 1}
    step = {'routing_id': 'RT-A', 'routing_version': 'V1', 'step_id': 'CUT', 'product_id': 'A', 'operation_id': 'CUT',
            'resource_id': 'S', 'predecessor_step_ids': [], 'reference_qty': '1', 'quantity_unit': 'EA', 'run_time': '1',
            'time_unit': 'h', 'time_basis': 'MACHINE_HOUR', 'valid_from': '2020-01-01', 'resource_requirements': []}
    demand = ['100'] * (n - 1) + [last_demand]
    return {
        'dataset_id': 'CHUNGPAMO-2027',
        'command': {'dataset_id': 'CHUNGPAMO-2027', 'forecast_execution_id': '00000000-0000-4000-8000-0000000000f0',
                    'product_ids': ['A'], 'target_month': start, 'horizon_months': n, 'as_of_date': '2026-12-31'},
        'forecast_input_digest': 'sha256:' + 'c' * 64,
        'forecast_rows': [{'product_id': 'A', 'target_month': m, 'p50': d, 'p80': d, 'p90': d, 'unit': 'EA'}
                          for m, d in zip(months, demand)],
        'approved_inputs': {
            'products': [{'product_id': 'A', 'product_name': 'a', 'base_unit': 'EA', 'product_type': None,
                          'safety_stock_qty': '0', 'source_type': 'SYNTHETIC', 'batch_id': b['product']}],
            'materials': [{'material_id': 'K', 'material_name': 'k', 'base_unit': 'kg', 'safety_stock_qty': '0',
                           'source_type': 'SYNTHETIC', 'batch_id': b['material']}],
            'boms': [{'header': {'bom_id': 'BOM-A', 'product_id': 'A', 'bom_version': 'V1', 'status': 'APPROVED',
                                 'is_active': True, 'valid_from': '2020-01-01', 'valid_to': None, 'base_qty': '1'},
                      'lines': [{'bom_id': 'BOM-A', 'line_no': 1, 'component_type': 'MATERIAL', 'component_id': 'K',
                                 'qty_per': '2', 'unit': 'kg', 'scrap_rate': '0'}],
                      'source_type': 'SYNTHETIC', 'batch_id': b['bom']}],
            'inventory': [{'item_type': t, 'item_id': i, 'as_of_date': '2026-12-31', 'on_hand_qty': q,
                           'allocated_qty': '0', 'unit': u, 'source_type': 'SYNTHETIC', 'batch_id': b['inventory']}
                          for t, i, q, u in [('PRODUCT', 'A', '0', 'EA'), ('MATERIAL', 'K', '100000', 'kg')]],
            'sources': [src('product', 'product'), src('material', 'material'), src('bom', 'bom'),
                        src('inventory', 'inventory'), src('capacity', 'capacity'), src('routing', 'routing')],
        },
        'scheduled_receipts': [],
        'capacity_snapshot': {'resources': [res], 'quantity_limits': [], 'routing_steps': [],
                              'hours_budgets': [{'capacity_id': 'H-S', 'resource_id': 'S', 'period': m,
                                                 'regular_hours': '100', 'overtime_hours_limit': '20', 'unit': 'h',
                                                 'time_basis': 'MACHINE_HOUR', 'availability_basis': 'NET'}
                                                for m in months]},
        'routing_snapshot': {'resources': [res], 'quantity_limits': [], 'hours_budgets': [], 'routing_steps': [step]},
        'missing_inputs': [],
    }


@pytest.mark.parametrize('n, start', [(1, '2027-01'), (3, '2027-01'), (6, '2027-01'), (12, '2027-07')])
def test_horizon_lengths(n, start):
    out = checked(small(n, start))
    months = months_from(start, n)
    assert out.status == 'OK'
    base, cost = production(out, 'BASELINE')['A'], production(out, 'COST_SAVING')['A']
    if n == 1:
        # 150 > 120 → 120, 30 못 만듦(앞 달 없음) → 결품
        assert base == [120] and feasibility(out)['BASELINE'] == 'INFEASIBLE'
    else:
        # 마지막 달 150 → 120, 30 앞 달로 → 130 → 120, 10 또 앞 달로 → 110
        assert base == [100] * (n - 3) + [110, 120, 120]
        assert feasibility(out)['BASELINE'] == 'FEASIBLE'  # 모든 입력 확인됨 → 백엔드 검사도 FEASIBLE 허용
    # 비용절감형(정규 100): 넘친 50이 1월까지 밀려 매달 100, 결품 50 → INFEASIBLE
    assert cost == [100] * n and feasibility(out)['COST_SAVING'] == 'INFEASIBLE'
    mats = [m for m in out.material_requirements if m.plan_id == 'BASELINE']
    assert [m.period for m in mats] == months and [m.required_qty for m in mats] == [str(2 * q) for q in base]
    caps = [e for e in out.constraint_evaluations if e.plan_id == 'BASELINE' and e.constraint_id.startswith('CAP-')]
    assert [e.period for e in caps] == months and {e.unit for e in caps} == {'h'}


def test_twelve_months_cross_the_year_boundary():
    out = checked(small(12, '2027-07'))
    assert {r.period for r in out.plans[0].production} >= {'2027-12', '2028-01', '2028-06'}


# ---------- 월별 BOM·라우팅 버전 ----------

def add_bom_v2(payload, valid_from, qty='3', v1_to=None):
    boms = payload['approved_inputs']['boms']
    if v1_to:
        boms[0]['header']['valid_to'] = v1_to
    v2 = copy.deepcopy(boms[0])
    v2['header'].update(bom_version='V2', valid_from=valid_from, valid_to=None)
    v2['lines'][0]['qty_per'] = qty
    boms.append(v2)


def test_bom_version_changes_by_month():
    payload = small(3, last_demand='100')
    add_bom_v2(payload, '2027-03-01', v1_to='2027-02-28')
    out = checked(payload)
    # 생산 100/100/100, 1·2월 V1(2 kg), 3월 V2(3 kg)
    assert [m.required_qty for m in out.material_requirements if m.plan_id == 'BASELINE'] == ['200', '200', '300']
    assert [(e.code, e.input_refs) for e in out.evidence if e.code == 'BOM_VERSION_SELECTED'] == [
        ('BOM_VERSION_SELECTED', ['A', '2027-01', 'BOM-A', 'V1']), ('BOM_VERSION_SELECTED', ['A', '2027-02', 'BOM-A', 'V1']),
        ('BOM_VERSION_SELECTED', ['A', '2027-03', 'BOM-A', 'V2'])]


def test_routing_version_changes_by_month():
    payload = small(3, last_demand='100')
    steps = payload['routing_snapshot']['routing_steps']
    steps[0]['valid_to'] = '2027-02-28'
    steps.append({**copy.deepcopy(steps[0]), 'routing_version': 'V2', 'run_time': '2', 'valid_from': '2027-03-01', 'valid_to': None})
    out = checked(payload)
    # 3월만 1개 2 h: 기준형 한도 120 h → 3월 60개, 40개 앞 달로 → 2월 140 → 120, 20개 다시 앞 달로 → 1월 120
    assert production(out, 'BASELINE')['A'] == [120, 120, 60]
    used = [e.used_value for e in out.constraint_evaluations if e.plan_id == 'BASELINE' and e.constraint_id.startswith('CAP-')]
    assert used == ['120', '120', '120']


def test_midmonth_version_change_is_unsupported():
    payload = small(3)
    add_bom_v2(payload, '2027-03-15', v1_to='2027-03-14')
    out = run(PlanningInput.model_validate(payload))
    assert out.status == 'UNSUPPORTED' and out.plans == []
    assert {(e.code, tuple(e.input_refs)) for e in out.errors} == {('BOM_VERSION_MIDMONTH', ('A', '2027-03'))}


def test_two_full_versions_in_a_month_are_ambiguous():
    payload = small(3)
    add_bom_v2(payload, '2027-03-01')  # V1도 끝나지 않음 → 3월에 둘 다 유효
    out = run(PlanningInput.model_validate(payload))
    assert out.status == 'INPUT_INVALID'
    assert [(e.code, e.input_refs) for e in out.errors] == [('BOM_VERSION_AMBIGUOUS', ['A', '2027-03'])]


# ---------- 기타 변환 규칙 ----------

def test_minutes_budget_is_converted_to_hours():
    payload = small(1, last_demand='100')
    for b in payload['capacity_snapshot']['hours_budgets']:
        b.update(regular_hours='6000', overtime_hours_limit='1200', unit='min')
    cap = next(e for e in checked(payload).constraint_evaluations if e.constraint_id == 'CAP-S-2027-01')
    assert (cap.limit_value, cap.unit) == ('120', 'h')


def test_unsupported_and_invalid_inputs_are_all_reported():
    payload = small(1)
    payload['capacity_snapshot']['quantity_limits'] = [{'capacity_id': 'Q-A', 'product_id': 'A', 'period': '2027-01',
                                                        'limit_qty': '50', 'unit': 'EA', 'accounting_point': 'OPERATION_OUTPUT',
                                                        'operation_id': 'CUT'}]
    payload['approved_inputs']['inventory'].append(copy.deepcopy(payload['approved_inputs']['inventory'][0]))
    out = run(PlanningInput.model_validate(payload))
    # INPUT_INVALID가 UNSUPPORTED보다 먼저이고, 두 문제를 모두 나열한다
    assert out.status == 'INPUT_INVALID'
    assert {e.code for e in out.errors} == {'INVENTORY_AMBIGUOUS', 'QUANTITY_LIMIT_POINT_UNSUPPORTED'}


def test_input_snapshot_is_not_modified():
    request = PlanningInput.model_validate(what_if_payload({'receipt_qty.PO-2701-001': '0'}))
    before = request.model_dump(mode='json')
    run(request)
    assert request.model_dump(mode='json') == before


# ---------- 백엔드 실행 경로(run_snapshot) ----------

@pytest.mark.parametrize('receipts', ['given', 'null'])
def test_backend_run_snapshot_accepts_engine_output(monkeypatch, receipts):
    """백엔드 Preview·저장이 쓰는 run_snapshot(입력 일치 검사 → planning.run → 출력 검사)을 실제 엔진으로 통과한다."""
    from app.integrations.planning import run_snapshot
    from engine import planning
    monkeypatch.setattr(planning, 'AVAILABLE', True)
    payload = copy.deepcopy(OFFICIAL)
    if receipts == 'null':
        payload['scheduled_receipts'] = None
        payload['missing_inputs'] = ['POLICY_NOT_CONFIRMED', 'RECEIPT_SOURCE_UNAVAILABLE']
    snapshot = PlanningInput.model_validate(payload)
    reply = run_snapshot(snapshot.command, snapshot)
    assert reply.result.status == 'OK'
    assert feasibility(reply.result) == {'BASELINE': 'UNVERIFIED', 'STABLE': 'INFEASIBLE', 'COST_SAVING': 'INFEASIBLE'}


def test_backend_run_snapshot_what_if():
    from app.integrations.planning import run_snapshot
    payload = what_if_payload({'overtime_hours_limit.SAW1.2027-02': '80'})
    payload['base_plan_snapshot'] = {'execution_id': PARENT, 'forecast_execution_id': payload['command']['forecast_execution_id']}
    snapshot = PlanningInput.model_validate(payload)
    reply = run_snapshot(snapshot.command, snapshot)
    stockout = {p.plan_id: p.feasibility for p in reply.result.plans}
    assert reply.result.status == 'OK' and stockout['STABLE'] == 'INFEASIBLE'
    assert production(reply.result, 'STABLE') != production(checked(OFFICIAL), 'STABLE')  # 2월 특근으로 안정형 생산이 바뀐다


# ---------- 검토 후 보강 (2026-11-23) ----------

def test_allocated_above_on_hand_is_input_invalid():
    payload = small(3)
    payload['approved_inputs']['inventory'][1].update(on_hand_qty='10', allocated_qty='50')
    out = run(PlanningInput.model_validate(payload))
    assert out.status == 'INPUT_INVALID'
    assert [(e.code, e.input_refs) for e in out.errors] == [('INVALID_QUANTITY', ['K', 'allocated'])]


def test_id_too_long_for_constraint_id_is_input_invalid():
    payload = json.loads(json.dumps(small(1)).replace('"S"', '"' + 'S' * 29 + '"'))
    out = run(PlanningInput.model_validate(payload))
    assert out.status == 'INPUT_INVALID' and [e.code for e in out.errors] == ['ID_TOO_LONG']


def test_unused_resource_is_left_out():
    payload = small(3)
    extra = {'resource_id': 'X', 'resource_name': 'x', 'kind': 'WORKCENTER', 'time_basis': 'ELAPSED', 'parallel_units': 1}
    payload['capacity_snapshot']['resources'].append(extra)
    # 백엔드 커버리지 검사는 등록 자원마다 예산을 요구하므로 예산은 두되, 엔진이 지원하지 않는 ELAPSED·GROSS로 둔다
    payload['capacity_snapshot']['hours_budgets'] += [{'capacity_id': 'H-X', 'resource_id': 'X', 'period': m,
        'regular_hours': '1', 'unit': 'h', 'time_basis': 'ELAPSED', 'availability_basis': 'GROSS'}
        for m in ['2027-01', '2027-02', '2027-03']]
    out = checked(payload)
    assert out.status == 'OK' and feasibility(out)['BASELINE'] == 'FEASIBLE'
    assert not any(e.resource_id == 'X' for e in out.constraint_evaluations)


def test_routing_steps_with_mixed_validity_are_unsupported():
    payload = small(3)
    steps = payload['routing_snapshot']['routing_steps']
    steps.append({**copy.deepcopy(steps[0]), 'step_id': 'PACK', 'operation_id': 'PACK', 'valid_from': '2027-02-01'})
    out = run(PlanningInput.model_validate(payload))
    assert out.status == 'UNSUPPORTED'
    assert [(e.code, e.input_refs) for e in out.errors] == [('ROUTING_STEP_VALIDITY_MIXED', ['A', 'RT-A', 'V1'])]


def test_routing_midmonth_and_ambiguous_versions():
    payload = small(3)
    steps = payload['routing_snapshot']['routing_steps']
    steps.append({**copy.deepcopy(steps[0]), 'routing_version': 'V2', 'valid_from': '2027-02-10'})
    out = run(PlanningInput.model_validate(payload))
    # 2월: V2가 달 중간 시작 → UNSUPPORTED, 3월: V1·V2 모두 전체 유효 → AMBIGUOUS(INPUT_INVALID가 먼저)
    assert out.status == 'INPUT_INVALID'
    assert [(e.code, e.input_refs) for e in out.errors] == [
        ('ROUTING_VERSION_AMBIGUOUS', ['A', '2027-03']), ('ROUTING_VERSION_MIDMONTH', ['A', '2027-02'])]


def test_routing_minutes_and_concurrent_requirement_are_summed_per_resource():
    payload = small(1, last_demand='100')
    lb = {'resource_id': 'LB', 'resource_name': 'labor', 'kind': 'LABOR_POOL', 'time_basis': 'PERSON_HOUR', 'parallel_units': 1}
    for snap in ('capacity_snapshot', 'routing_snapshot'):
        payload[snap]['resources'].append(lb)
    payload['capacity_snapshot']['hours_budgets'].append({'capacity_id': 'H-LB', 'resource_id': 'LB', 'period': '2027-01',
        'regular_hours': '1000', 'overtime_hours_limit': '0', 'unit': 'h', 'time_basis': 'PERSON_HOUR', 'availability_basis': 'NET'})
    step = payload['routing_snapshot']['routing_steps'][0]
    step.update(run_time='30', time_unit='min', reference_qty='1')  # S: 개당 0.5 h
    step['resource_requirements'] = [{'resource_id': 'LB', 'reference_qty': '10', 'quantity_unit': 'EA', 'run_time': '1',
                                      'time_unit': 'h', 'time_basis': 'PERSON_HOUR'}]  # LB: 개당 0.1 h
    payload['routing_snapshot']['routing_steps'].append({**copy.deepcopy(step), 'step_id': 'CUT2', 'run_time': '6',
                                                         'resource_requirements': []})  # S: 개당 0.1 h 더
    used = {e.resource_id: e.used_value for e in checked(payload).constraint_evaluations
            if e.plan_id == 'BASELINE' and e.constraint_id.startswith('CAP-')}
    assert used == {'S': '60', 'LB': '10'}  # 100개 × 0.6 h, 100개 × 0.1 h


def test_smallest_quantity_limit_and_latest_inventory_are_used():
    payload = small(1, last_demand='100')
    payload['capacity_snapshot']['quantity_limits'] = [
        {'capacity_id': c, 'product_id': 'A', 'period': '2027-01', 'limit_qty': q, 'unit': 'EA',
         'accounting_point': 'FINISHED_OUTPUT', 'operation_id': None} for c, q in [('Q1', '90'), ('Q2', '70')]]
    inv = payload['approved_inputs']['inventory']
    inv.append({**copy.deepcopy(inv[0]), 'as_of_date': '2026-11-30', 'on_hand_qty': '999'})  # 더 오래된 재고는 무시
    inv.append({**copy.deepcopy(inv[0]), 'as_of_date': '2027-01-05', 'on_hand_qty': '999'})  # 기준일 뒤 재고도 무시
    out = run(PlanningInput.model_validate(payload))
    assert production(out, 'BASELINE')['A'] == [70]  # 재고 0, 수요 100, 한도 min(90, 70)
