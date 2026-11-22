"""What-if (PLANNING_RULES v0.4 §8). 기대값은 주석의 손계산."""
import copy
import json
from pathlib import Path

from what_if.core import run_what_if


def two_month():
    # HC-06/07과 같은 설비: S 정규 100 + 잔업 20, 1개 1시간. P50 80/140, P80 88/154
    return {
        'months': ['2027-01', '2027-02'], 'demand_multiplier': '1',
        'products': [{'id': 'A', 'unit': 'EA', 'safety_stock': 0, 'on_hand': 0, 'allocated': 0}],
        'forecast': {'P50': {'A': ['80', '140']}, 'P80': {'A': ['88', '154']}},
        'resources': [{'id': 'S', 'time_basis': 'MACHINE_HOUR', 'regular': [100, 100], 'overtime': [20, 20]}],
        'routing': {'A': {'S': {'run_time': '1', 'reference_qty': '1'}}},
    }


def test_overtime_override_recomputes_ot_plans_and_leaves_cost_saving():
    r = run_what_if(two_month(), {'overtime_hours_limit.S.2027-02': '40'})
    assert r.status == 'OK'
    # 기준: 기준형 100/120 FEASIBLE, 안정형 120/120 결품 2, 비용절감형 100/100 결품 20
    assert r.base['BASELINE'].production == {'A': [100, 120]}
    assert r.base['STABLE'].stockout == {'A': [0, 2]}
    # 기준형: 2월 CAP 140 → 140 그대로, 1월 80 → 잔업 0/40, 앞당김 없음
    assert r.scenario['BASELINE'].production == {'A': [80, 140]}
    assert r.scenario['BASELINE'].overtime_hours['S'] == [0, 40]
    # 안정형: 2월 154 → 140, 14 앞 달로 → 1월 88 + 14 = 102 ≤ 120 → 결품 없음
    assert r.scenario['STABLE'].production == {'A': [102, 140]}
    assert r.scenario['STABLE'].feasibility == 'FEASIBLE'
    # 비용절감형은 잔업 0 안 → 변화 없음
    assert r.scenario['COST_SAVING'].production == r.base['COST_SAVING'].production == {'A': [100, 100]}
    d = {x.plan_id: x for x in r.deltas()}
    assert d['STABLE'].feasibility == ('INFEASIBLE', 'FEASIBLE') and d['STABLE'].stockout_total == (2, 0)
    assert d['COST_SAVING'].stockout_total == (20, 20)


def test_product_multiplier_wins_over_global():
    data = two_month()
    data['months'] = ['2027-01']
    data['products'].append({'id': 'B', 'unit': 'EA', 'safety_stock': 0, 'on_hand': 0, 'allocated': 0})
    data['forecast'] = {'P50': {'A': ['100'], 'B': ['100']}, 'P80': {'A': ['100'], 'B': ['100']}}
    data['resources'][0].update(regular=[1000], overtime=[0])
    data['routing']['B'] = {'S': {'run_time': '1', 'reference_qty': '1'}}
    r = run_what_if(data, {'demand_multiplier': '1.2', 'demand_multiplier.A': '1.5'})
    # A는 제품 배수 1.5 → 150 (1.2 × 1.5 = 180 아님), B는 전체 배수 → 120
    assert r.scenario['BASELINE'].planned_demand == {'A': [150], 'B': [120]}
    assert r.base['BASELINE'].planned_demand == {'A': [100], 'B': [100]}


def with_receipt():
    data = two_month()
    data['months'] = ['2027-01']
    data['forecast'] = {'P50': {'A': ['100']}, 'P80': {'A': ['100']}}
    data['resources'][0].update(regular=[1000], overtime=[0])
    data.update(as_of='2026-12-31',
                materials=[{'id': 'K1', 'unit': 'kg', 'safety_stock': '0', 'on_hand': '50', 'allocated': '0'}],
                bom={'A': [{'material': 'K1', 'qty': '1', 'base_qty': '1', 'scrap_rate': '0'}]},
                receipts=[{'po_id': 'PO-1', 'material': 'K1', 'open_qty': '150', 'unit': 'kg',
                           'expected_date': '2026-12-20'}])
    return data


def test_receipt_cancel_and_change():
    # 기준: 가용 50 + 150(납기 지남) = 200, 소요 100 → 발주 0, MAT UNVERIFIED(RECEIPT_OVERDUE)
    cancel = run_what_if(with_receipt(), {'receipt_qty.PO-1': '0'})
    base = cancel.base['BASELINE']
    assert base.materials['K1'].available == [200] and [w.code for w in base.warnings] == ['RECEIPT_OVERDUE']
    # 취소: 가용 50 → 발주 필요 50, 납기 지남 경고도 사라짐
    s = cancel.scenario['BASELINE']
    assert s.materials['K1'].available == [50] and s.materials['K1'].shortage == [50] and s.warnings == []
    mat = next(e for e in s.evaluations if e.constraint_id == 'MAT-K1-2027-01')
    assert mat.reason_codes == ['PROCUREMENT_REQUIRED']
    # 수량 변경 30: 가용 80 → 발주 필요 20
    change = run_what_if(with_receipt(), {'receipt_qty.PO-1': '30'}).scenario['BASELINE']
    assert change.materials['K1'].available == [80] and change.materials['K1'].shortage == [20]


def test_invalid_overrides_are_all_reported_without_calculation():
    r = run_what_if(with_receipt(), {
        'demand_multiplier.ZZ': '1.1',               # 없는 제품
        'demand_multiplier': '-1',                   # 음수
        'overtime_hours_limit.S.2027-05': '10',      # 기간 밖 월
        'overtime_hours_limit.X.2027-01': '10',      # 없는 자원
        'receipt_qty.PO-9': '0',                     # 없는 발주
        'production_qty.A': '100',                   # 이번 범위 밖 키
    })
    assert r.status == 'INPUT_INVALID' and r.base == {} and r.scenario == {}
    assert {i.input_refs[1] for i in r.errors} == {'product', 'value', 'month', 'resource', 'po_id', 'key'}
    assert {i.code for i in r.errors} == {'WHATIF_INVALID'}


def test_original_input_is_not_modified():
    data = with_receipt()
    before = copy.deepcopy(data)
    run_what_if(data, {'receipt_qty.PO-1': '0', 'overtime_hours_limit.S.2027-01': '5', 'demand_multiplier': '2'})
    assert data == before


def test_chungpamo_february_saw1_extra_shift():
    """시연 장면: 2월 절단기 특근(잔업 한도 40 → 80h). 기준 결과는 고정 정답과 같고 안정형 결품이 줄어든다."""
    here = Path(__file__).parent / 'chungpamo'
    data = json.loads((here / 'plan_input.json').read_text(encoding='utf-8'))
    expected = json.loads((here / 'expected.json').read_text(encoding='utf-8'))
    r = run_what_if(data, {'overtime_hours_limit.SAW1.2027-02': '80'})
    for plan_id, res in r.base.items():
        assert res.production == expected[plan_id]['production']
    d = {x.plan_id: x for x in r.deltas()}
    assert d['STABLE'].stockout_total[1] < d['STABLE'].stockout_total[0]
    assert d['COST_SAVING'].stockout_total[1] == d['COST_SAVING'].stockout_total[0]
