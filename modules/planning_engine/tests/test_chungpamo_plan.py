"""㈜충파모제지(SYNTHETIC) 9제품 × 3개월 × 3안: 계산 코어 결과를 독립 계산 정답과 비교한다.

- 입력 tests/chungpamo/plan_input.json: synthetic/plan_input.py가 upload·입고 예정·예측 결과(고정)로 만든 것
- 정답 tests/chungpamo/expected.json: 엔진 코드를 보지 않은 별도 계산기가 PLANNING_RULES v0.4만 보고 계산
  (그 계산기는 손계산 HC-01~18도 모두 맞춘 뒤 이 정답을 냈다)
LightGBM·데이터 생성 없이 항상 같은 입력으로 돈다.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from engine.planning_core import PLAN_SPECS, calculate_plans

HERE = Path(__file__).parent
_spec = importlib.util.spec_from_file_location('hand_calc_compare', HERE / 'test_hand_calc.py')
_hc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hc)

INPUT = json.loads((HERE / 'chungpamo' / 'plan_input.json').read_text(encoding='utf-8'))
EXPECTED = json.loads((HERE / 'chungpamo' / 'expected.json').read_text(encoding='utf-8'))
RESULTS = calculate_plans(INPUT)


@pytest.mark.parametrize('plan_id', [s[0] for s in PLAN_SPECS])
def test_plan_matches_independent_answer(plan_id):
    exp, got = EXPECTED[plan_id], RESULTS[plan_id]
    assert set(exp) <= _hc.KNOWN, f'비교하지 않는 항목: {set(exp) - _hc.KNOWN}'
    _hc._compare_plan(got, exp, f'CHUNGPAMO {plan_id}')
    # 정답에는 판정이 전부 적혀 있으므로 빠지거나 더 나온 판정도 없어야 한다
    assert {e.constraint_id for e in got.evaluations} == {e['constraint_id'] for e in exp['evaluations']}


def test_input_is_the_frozen_chungpamo_dataset():
    assert INPUT['dataset_id'] == 'CHUNGPAMO-2027' and INPUT['months'] == ['2027-01', '2027-02', '2027-03']
    assert len(INPUT['products']) == 9 and set(INPUT['forecast']) == {'P50', 'P80'}
