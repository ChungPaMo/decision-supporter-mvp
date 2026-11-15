"""분류 규칙 시험. 시험셋은 합성 자료이며 규칙과 같은 사람이 만들었으므로, 여기의 통과는 실제 성능 보증이 아니다."""
import json
import pathlib
import random

import pytest

from contracts.interfaces.modules import ClassificationInput
from file_classifier import classify
from file_classifier.rules import MODULE_VERSION, norm

CASES = json.loads((pathlib.Path(__file__).parent / 'fixtures' / 'cases.json').read_text(encoding='utf-8'))['cases']
POSITIVE = [c for c in CASES if c['expected']['expected_entity']]


def run(payload):
    return classify(ClassificationInput(**payload))


@pytest.mark.parametrize('case', CASES, ids=[c['case_id'] for c in CASES])
def test_case(case):
    expected, output = case['expected'], run(case['payload'])
    assert output.module_version == MODULE_VERSION
    if output.recommended_entity is None:
        assert output.hold and output.reasons
        assert expected['must_hold'] or expected['hold_ok'], '추천해야 할 사례를 보류했다'
    else:
        assert not output.hold
        assert output.recommended_entity == expected['expected_entity'], '오분류'
    if expected['guidance_entity']:
        assert expected['guidance_entity'] in [c.entity for c in output.candidates]
        assert any('monthly_demand' in reason for reason in output.reasons)


def test_same_input_gives_same_output():
    for case in CASES[::7]:
        assert run(case['payload']) == run(case['payload'])


def test_filename_does_not_change_the_result():
    for case in CASES[::5]:
        renamed = {**case['payload'], 'filename': 'BOM_재고_수요_제품_자재.xlsx'}
        assert run(renamed).recommended_entity == run(case['payload']).recommended_entity


def test_unknown_column_names_cause_hold_never_another_entity():
    """아는 열 이름 일부를 처음 보는 이름으로 바꿔도 다른 종류로 추천하면 안 된다 (보류는 허용)."""
    rng = random.Random(11)
    unknown = ['항목A', '값1', 'col_x', '기타정보', 'field9', '참고값']
    for case in POSITIVE:
        for _ in range(8):
            payload = json.loads(json.dumps(case['payload']))
            for sheet in payload['sheets']:
                filled = [i for i, name in enumerate(sheet['columns']) if norm(name)]
                for i in rng.sample(filled, min(len(filled), rng.randint(1, 3))):
                    sheet['columns'][i] = rng.choice(unknown) + str(i)
            got = run(payload).recommended_entity
            assert got in (None, case['expected']['expected_entity']), (case['case_id'], payload['sheets'][0]['columns'])


def test_demand_with_unfamiliar_period_and_quantity_names_is_not_a_product_master():
    output = run({'filename': 'a.csv', 'sha256': '0' * 64,
                  'sheets': [{'name': None, 'columns': ['제품코드', '품명', '집계월', '월간수요', 'uom'], 'sample_rows': []}]})
    assert output.recommended_entity != 'product'


@pytest.mark.parametrize('columns', [
    ['capacity_id', 'resource_id', 'period', 'regular_hours', 'overtime_hours_limit', 'unit'],
    ['routing_id', 'routing_version', 'step_id', 'product_id', 'operation_id', 'resource_id', 'run_time'],
    ['capacity_id', 'product_id', 'period', 'limit_qty', 'unit'],
])
def test_capacity_and_routing_are_never_recommended(columns):
    output = run({'filename': 'a.csv', 'sha256': '0' * 64, 'sheets': [{'name': None, 'columns': columns, 'sample_rows': []}]})
    assert output.recommended_entity is None and output.hold
