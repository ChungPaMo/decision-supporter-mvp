"""손계산 정답(tests/hand_calc/small_cases.json)과 계산 코어를 자동 비교한다.

정답은 PLANNING_RULES v0.4만 보고 엔진 코드와 따로 만들었다. expected에 적힌 항목만 비교하고,
모르는 항목이 있으면 비교를 빠뜨리지 않도록 실패시킨다.
"""
import copy
import json
from fractions import Fraction
from pathlib import Path

import pytest

from engine.planning_core import PLAN_SPECS, calculate, calculate_plans, decimal_str

CASES = json.loads((Path(__file__).parent / 'hand_calc' / 'small_cases.json').read_text(encoding='utf-8'))['cases']

KNOWN = {'status', 'error_codes', 'plans', 'planned_demand', 'target', 'unmade_after_prebuild', 'production',
         'end_inventory', 'stockout', 'scale_factor', 'used_hours', 'overtime_hours', 'per_unit',
         'material_requirements', 'evaluations', 'warnings', 'unverified_codes', 'feasibility', 'base'}


def _num(v):
    return None if v is None else Fraction(str(v))


def _compare_plan(got, exp, where):
    if exp.get('status', 'OK') != got.status:
        pytest.fail(f'{where} status {got.status} != {exp.get("status", "OK")}')
    if 'error_codes' in exp:
        assert got.error_codes == set(exp['error_codes']), where
    if got.status != 'OK':
        assert exp.get('plans', []) == [], where
        return
    for key in ('planned_demand', 'target', 'production', 'end_inventory', 'stockout'):
        for p, vals in exp.get(key, {}).items():
            assert getattr(got, key)[p] == vals, f'{where} {key} {p}'
    for p, v in exp.get('unmade_after_prebuild', {}).items():
        assert got.unmade_after_prebuild[p] == v, f'{where} unmade {p}'
    for r, v in exp.get('scale_factor', {}).items():
        values = v if isinstance(v, list) else [v]  # 한 달짜리 케이스는 값 하나로 적는다
        assert got.scale_factor[r] == [Fraction(x) for x in values], f'{where} scale {r}'
    for key in ('used_hours', 'overtime_hours'):
        for r, vals in exp.get(key, {}).items():
            assert getattr(got, key)[r] == [_num(v) for v in vals], f'{where} {key} {r}'
    for k, v in exp.get('per_unit', {}).items():  # 자재별로 적으므로 그 자재를 쓰는 모든 제품의 값이 같아야 한다
        values = {q for (_, mat), q in got.per_unit.items() if mat == k}
        assert values == {Fraction(v)}, f'{where} per_unit {k} {values}'
    for k, rows in exp.get('material_requirements', {}).items():
        for field, vals in rows.items():
            assert getattr(got.materials[k], field) == [_num(v) for v in vals], f'{where} material {k} {field}'
    ids = [e.constraint_id for e in got.evaluations]
    assert len(ids) == len(set(ids)), f'{where} duplicate constraint ids'
    evals = {e.constraint_id: e for e in got.evaluations}
    for x in exp.get('evaluations', []):
        e = evals.get(x['constraint_id'])
        assert e is not None, f'{where} missing {x["constraint_id"]}'
        for field, v in x.items():
            if field == 'constraint_id':
                continue
            actual = getattr(e, field)
            if field in ('limit_value', 'used_value'):
                assert actual == _num(v), f'{where} {x["constraint_id"]}.{field} {actual}'
            elif field == 'reason_codes':
                assert set(actual) == set(v), f'{where} {x["constraint_id"]}.reason_codes {actual}'
            else:
                assert actual == v, f'{where} {x["constraint_id"]}.{field} {actual}'
    if 'warnings' in exp:
        assert sorted((w.code, w.input_refs) for w in got.warnings) == \
               sorted((w['code'], tuple(w['input_refs'])) for w in exp['warnings']), where
    if 'unverified_codes' in exp:
        assert got.unverified_codes == set(exp['unverified_codes']), where
    assert got.feasibility == exp['feasibility'], f'{where} feasibility {got.feasibility}'


@pytest.mark.parametrize('case', CASES, ids=[c['case_id'] for c in CASES])
def test_hand_calc_case(case):
    exp = case['expected']
    assert set(exp) <= KNOWN, f'비교하지 않는 항목: {set(exp) - KNOWN}'
    _compare_plan(calculate(copy.deepcopy(case['input'])), exp, case['case_id'])
    if 'base' in exp:
        base_input = dict(case['input'], demand_multiplier=case['input'].get('base_demand_multiplier', '1'))
        base = calculate(base_input)
        for key, v in exp['base'].items():
            got = base.feasibility if key == 'feasibility' else (base.stockout if key == 'stockout' else getattr(base, key))
            assert got == v, f'{case["case_id"]} base {key}'


def test_three_plans_share_rules_and_differ_only_in_quantile_and_overtime():
    """HC-06(잔업 허용)과 HC-07(잔업 없음)은 같은 입력이다 → 기준형 = HC-06, 비용절감형 = HC-07."""
    hc06 = next(c for c in CASES if c['case_id'] == 'HC-06')
    data = {k: v for k, v in hc06['input'].items() if k not in ('demand', 'ot_allowed')}
    p50 = hc06['input']['demand']
    data['forecast'] = {'P50': p50, 'P80': {'A': ['88', '154']}}
    plans = calculate_plans(data)
    assert list(plans) == [spec[0] for spec in PLAN_SPECS] == ['BASELINE', 'STABLE', 'COST_SAVING']
    assert plans['BASELINE'].production == {'A': [100, 120]} and plans['BASELINE'].feasibility == 'FEASIBLE'
    assert plans['COST_SAVING'].production == {'A': [100, 100]} and plans['COST_SAVING'].feasibility == 'INFEASIBLE'
    # 안정형 P80: 2월 154 → 120 생산, 34 앞 달로 → 1월 88 + 34 = 122 > 120 → 120, 2 못 만듦 → 결품
    assert plans['STABLE'].production == {'A': [120, 120]}
    assert plans['STABLE'].stockout == {'A': [0, 2]} and plans['STABLE'].feasibility == 'INFEASIBLE'
    assert all(p.policy_ref == 'PLANNING_RULES-v0.4' for p in plans.values())


@pytest.mark.parametrize('value,text', [(Fraction(91, 10), '9.1'), (Fraction(12), '12'), (Fraction(6, 7), '0.8571'),
                                        (Fraction(1, 20000), '0.0001'), (Fraction(0), '0'), (Fraction(-5, 2), '-2.5')])
def test_decimal_str(value, text):
    assert decimal_str(value) == text


def test_engine_is_available_after_backend_integration():
    from engine import planning
    assert planning.AVAILABLE is True
