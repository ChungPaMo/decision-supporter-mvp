"""손계산 케이스가 다루지 않는 입력 경계 (PLANNING_RULES v0.4 §3, §5.1, §7). 기대값은 주석의 손계산."""
from fractions import Fraction

from engine.planning_core import calculate, calculate_plans


def base(months=('2027-01',), demand=('100',), regular=(1000,), **extra):
    data = {
        'months': list(months), 'ot_allowed': False, 'demand_multiplier': '1',
        'products': [{'id': 'A', 'unit': 'EA', 'safety_stock': 0, 'on_hand': 0, 'allocated': 0}],
        'demand': {'A': list(demand)},
        'resources': [{'id': 'S', 'time_basis': 'MACHINE_HOUR', 'regular': list(regular), 'overtime': [0] * len(regular)}],
        'routing': {'A': {'S': {'run_time': '1', 'reference_qty': '1'}}},
    }
    data.update(extra)
    return data


def ev(result, cid):
    return next(e for e in result.evaluations if e.constraint_id == cid)


def ids(result):
    return {e.constraint_id for e in result.evaluations}


def test_zero_reference_or_base_qty_is_input_invalid_not_crash():
    d = base()
    d['routing']['A']['S']['reference_qty'] = '0'
    d['materials'] = [{'id': 'K1', 'unit': 'kg', 'safety_stock': '0', 'on_hand': '0', 'allocated': '0'}]
    d['bom'] = {'A': [{'material': 'K1', 'qty': '1', 'base_qty': '0', 'scrap_rate': '0'}]}
    r = calculate(d)
    assert r.status == 'INPUT_INVALID' and r.error_codes == {'INVALID_QUANTITY'} and len(r.errors) == 2


def test_missing_regular_hours_means_no_limit_and_unverified():
    # 2월 가용시간 없음 → 한도 없음: 200 그대로, CAP-S-2027-02 UNVERIFIED/MISSING_INPUT
    r = calculate(base(months=('2027-01', '2027-02', '2027-03'), demand=('50', '200', '50'), regular=(100, None, 100)))
    assert r.production == {'A': [50, 200, 50]}
    e = ev(r, 'CAP-S-2027-02')
    assert (e.status, e.application_state, e.limit_value, e.used_value) == ('UNVERIFIED', 'MISSING_INPUT', None, 200)
    assert ev(r, 'CAP-S-2027-01').status == 'SATISFIED'
    assert r.unverified_codes == {'CAPACITY_MISSING'} and r.feasibility == 'UNVERIFIED'
    assert r.overtime_hours['S'] == [0, None, 0]


def test_short_regular_array_is_missing_hours():
    r = calculate(base(months=('2027-01', '2027-02'), demand=('10', '10'), regular=(100,)))
    assert ev(r, 'CAP-S-2027-02').application_state == 'MISSING_INPUT' and r.feasibility == 'UNVERIFIED'


def test_missing_overtime_limit_counts_as_zero_with_warning():
    # 잔업 허용 안인데 잔업 한도 없음 → 잔업 0으로 보수적으로 계산: 120 중 100만, 결품 20
    d = base(demand=('120',), regular=(100,), ot_allowed=True)
    del d['resources'][0]['overtime']
    r = calculate(d)
    assert r.production == {'A': [100]} and r.stockout == {'A': [20]}
    assert [(w.code, w.input_refs) for w in r.warnings] == [('OVERTIME_LIMIT_MISSING', ('S', '2027-01'))]
    assert r.feasibility == 'INFEASIBLE'


def test_routing_resource_absent_from_resources_is_unverified_not_dropped():
    # Z는 공정표에만 있음 → 한도 모름, Z 사용 10 × 5 = 50시간은 보이되 UNVERIFIED
    d = base(demand=('10',))
    d['routing']['A']['Z'] = {'run_time': '5', 'reference_qty': '1'}
    r = calculate(d)
    e = ev(r, 'CAP-Z-2027-01')
    assert (e.status, e.application_state, e.used_value) == ('UNVERIFIED', 'MISSING_INPUT', 50)
    assert r.production == {'A': [10]} and r.feasibility == 'UNVERIFIED'


def _with_materials(**extra):
    d = base(demand=('10',))
    d['products'].append({'id': 'B', 'unit': 'EA', 'safety_stock': 0, 'on_hand': 0, 'allocated': 0})
    d['demand']['B'] = ['5']
    d['routing']['B'] = {'S': {'run_time': '1', 'reference_qty': '1'}}
    d['materials'] = [{'id': 'K1', 'unit': 'kg', 'safety_stock': '0', 'on_hand': '1000', 'allocated': '0'}]
    d['bom'] = {'A': [{'material': 'K1', 'qty': '1', 'base_qty': '1', 'scrap_rate': '0'}],
                'B': [{'material': 'K1', 'qty': '2', 'base_qty': '1', 'scrap_rate': '0'}]}
    d.update(extra)
    return d


def test_bom_missing_makes_every_mat_unverified():
    d = _with_materials()
    del d['bom']['B']
    r = calculate(d)
    e = ev(r, 'MAT-K1-2027-01')
    assert (e.status, e.application_state) == ('UNVERIFIED', 'MISSING_INPUT') and 'B' in e.input_refs
    assert e.used_value == 10  # 계산된 숫자는 A분(10 × 1)만이라도 그대로 보여준다
    assert [(w.code, w.input_refs) for w in r.warnings] == [('BOM_MISSING', ('B',))]
    assert r.feasibility == 'UNVERIFIED'


def test_bom_material_absent_from_materials_is_input_invalid():
    d = _with_materials()
    d['bom']['B'].append({'material': 'K9', 'qty': '1', 'base_qty': '1', 'scrap_rate': '0'})
    r = calculate(d)
    assert r.status == 'INPUT_INVALID' and r.error_codes == {'MATERIAL_MISSING'}


def test_unused_material_is_excluded_even_without_inventory():
    # Z는 어느 BOM에도 없음 → 표·판정·재고 누락 검사 모두 제외, K1은 1000 ≥ 10 + 10 → FEASIBLE
    d = _with_materials()
    d['materials'].append({'id': 'Z', 'unit': 'EA', 'safety_stock': '0'})
    r = calculate(d)
    assert not any(c.startswith('MAT-Z') for c in ids(r)) and 'Z' not in r.materials
    assert r.warnings == [] and r.feasibility == 'FEASIBLE'
    assert r.materials['K1'].required == [20]


def test_material_inventory_unit_mismatch_is_input_invalid():
    d = _with_materials()
    d['materials'][0]['inventory_unit'] = 'g'
    assert calculate(d).error_codes == {'UNIT_MISMATCH'}


def test_receipt_due_on_as_of_date_is_overdue():
    d = _with_materials(as_of='2026-12-31',
                        receipts=[{'po_id': 'PO-1', 'material': 'K1', 'open_qty': '5', 'unit': 'kg',
                                   'expected_date': '2026-12-31'}])
    r = calculate(d)
    assert ev(r, 'MAT-K1-2027-01').reason_codes == ['RECEIPT_OVERDUE']
    assert r.materials['K1'].available == [1005]


def test_short_or_missing_forecast_is_forecast_missing():
    r = calculate(base(months=('2027-01', '2027-02', '2027-03'), demand=('100', '100'), regular=(1000,) * 3))
    assert r.status == 'INPUT_INVALID' and r.error_codes == {'FORECAST_MISSING'}
    d = base()
    del d['demand'], d['ot_allowed']
    plans = calculate_plans({**d, 'forecast': {'P50': {'A': ['10']}}})
    assert plans['BASELINE'].status == 'OK' and plans['STABLE'].error_codes == {'FORECAST_MISSING'}


def test_none_month_in_quantity_limit_means_no_limit_that_month():
    # 2월 70 → 한도 50, 20을 1월로 → 1월 30 + 20 = 50 (1월 한도 없음)
    r = calculate(base(months=('2027-01', '2027-02'), demand=('30', '70'), regular=(1000, 1000),
                       quantity_limits={'A': [None, 50]}))
    assert r.production == {'A': [50, 50]}
    assert 'QTY-A-2027-01' not in ids(r) and ev(r, 'QTY-A-2027-02').reason_codes == ['QUANTITY_LIMIT_BINDING']


def test_unrouted_product_still_obeys_quantity_limit():
    # 라우팅 없음 + 한도 50, 수요 100 → 50만 생산, 결품 50, QTY 판정도 냄
    d = base(quantity_limits={'A': [50]})
    d['routing'] = {}
    r = calculate(d)
    assert r.production == {'A': [50]} and r.stockout == {'A': [50]}
    assert ev(r, 'QTY-A-2027-01').reason_codes == ['QUANTITY_LIMIT_BINDING']
    assert ev(r, 'CAP-S-2027-01').status == 'UNVERIFIED' and r.feasibility == 'INFEASIBLE'


def test_quantity_binding_only_when_limit_is_the_tightest():
    # X 100, 한도 90(비율 0.9), 설비 50(비율 0.5) → 설비가 원인: P 50, QTY 표시 없음
    r = calculate(base(regular=(50,), quantity_limits={'A': [90]}))
    assert r.production == {'A': [50]}
    assert ev(r, 'QTY-A-2027-01').reason_codes == [] and ev(r, 'CAP-S-2027-01').reason_codes == ['CAPACITY_BINDING']


def test_zero_hour_resource_does_not_scale_product():
    # A는 R을 0시간 사용 → R이 넘쳐도(B 때문) A는 줄지 않는다. R: B 20시간 > 10 → B만 10
    d = base(demand=('30',))
    d['products'].append({'id': 'B', 'unit': 'EA', 'safety_stock': 0, 'on_hand': 0, 'allocated': 0})
    d['demand']['B'] = ['20']
    d['resources'].append({'id': 'R', 'time_basis': 'MACHINE_HOUR', 'regular': [10], 'overtime': [0]})
    d['routing']['A']['R'] = {'run_time': '0', 'reference_qty': '1'}
    d['routing']['B'] = {'R': {'run_time': '1', 'reference_qty': '1'}}
    r = calculate(d)
    assert r.production == {'A': [30], 'B': [10]} and r.scale_factor['R'] == [Fraction(1, 2)]


def test_non_integer_product_quantity_is_input_invalid():
    d = base()
    d['products'][0]['on_hand'] = '2.5'
    assert calculate(d).error_codes == {'INVALID_QUANTITY'}
    d['products'][0]['on_hand'] = '100.0'
    assert calculate(d).status == 'OK'
