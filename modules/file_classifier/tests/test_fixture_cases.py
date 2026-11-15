"""시험셋(cases.json)이 분류 입력 계약을 지키고 생성기와 일치하는지 확인한다. 분류 성능 시험이 아니다."""
import importlib.util
import json
import pathlib

from contracts.interfaces.modules import ClassificationInput

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'
ENTITIES = {'product', 'material', 'bom', 'inventory', 'monthly_demand'}


def load_cases():
    return json.loads((FIXTURES / 'cases.json').read_text(encoding='utf-8'))['cases']


def test_every_payload_satisfies_the_input_contract():
    cases = load_cases()
    assert len(cases) >= 200
    assert len({c['case_id'] for c in cases}) == len(cases)
    for case in cases:
        ClassificationInput(**case['payload'])


def test_expectations_are_consistent():
    for case in load_cases():
        e = case['expected']
        assert (e['expected_entity'] is None) == e['must_hold'], case['case_id']
        assert e['expected_entity'] is None or e['expected_entity'] in ENTITIES, case['case_id']
        assert not (e['must_hold'] and e['hold_ok']), case['case_id']
        assert e['guidance_entity'] is None or (e['must_hold'] and e['guidance_entity'] in ENTITIES), case['case_id']
        assert case['split'] in ('dev', 'test')
        if case['payload']['format'] == 'csv':
            assert [s['name'] for s in case['payload']['sheets']] == [None], case['case_id']


def test_no_capacity_or_routing_recommendation_is_expected():
    for case in load_cases():
        if case['group'] == 'capacity_routing':
            assert case['expected']['must_hold'] and case['expected']['guidance_entity'] is None


def test_committed_cases_match_the_generator():
    spec = importlib.util.spec_from_file_location('build_cases', FIXTURES / 'build_cases.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.build() == load_cases()
