"""Pure module handoff tests. Test doubles never represent the delivered algorithm."""
import copy
import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.errors import ApiError, ErrorCode
from app.integrations import planning as adapter
from app.integrations.planning_validation import with_input_coverage
from contracts.interfaces.modules import PlanningInput, PlanCommand

ROOT = Path(__file__).resolve().parents[2] / 'contracts/examples/integration'


def payload(name): return json.loads((ROOT / name).read_text(encoding='utf-8'))['payload']


@pytest.fixture
def delivered(monkeypatch):
    from engine import planning
    source = PlanningInput.model_validate(payload('planning_input.json'))
    result = payload('planning_output.json')
    result['unverified'] = [{'code': code, 'message': 'Synthetic coverage evidence'}
                            for code in with_input_coverage(source).missing_inputs]
    monkeypatch.setattr(planning, 'AVAILABLE', True)
    monkeypatch.setattr(planning, 'run', lambda request: copy.deepcopy(result))
    class Provider:
        def load(self, command):
            base = {'execution_id': str(command.base_plan_execution_id), 'forecast_execution_id': str(command.forecast_execution_id)} if command.scenario == 'WHAT_IF' else None
            return source.model_copy(update={'command': command, 'base_plan_snapshot': base}, deep=True)
    monkeypatch.setattr(adapter, 'get_source_provider', Provider)
    return source, result


def test_delivered_module_is_called_without_saving_or_approving(delivered):
    command = payload('planning_input.json')['command']
    command.pop('horizon_months')  # Existing preview client never sent a horizon.
    with TestClient(app) as client:
        response = client.post('/plans', json=command)
    assert response.status_code == 200
    reply = response.json()
    assert reply['result']['status'] == 'PARTIAL' and len(reply['result']['plans']) == 2
    assert reply['persisted'] is False and reply['approval_available'] is False
    assert reply['forecast_execution_id'] == str(delivered[0].command.forecast_execution_id)
    assert reply['input_digest'].startswith('sha256:')


def test_what_if_calls_same_module_with_explicit_base_snapshot(delivered, monkeypatch):
    from engine import planning
    seen = []
    monkeypatch.setattr(planning, 'run', lambda request: (seen.append(request), delivered[1])[1])
    command = {**payload('planning_input.json')['command'], 'scenario': 'WHAT_IF',
               'base_plan_execution_id': '00000000-0000-4000-8000-000000000003', 'overrides': {'demand_multiplier': '1.1'}}
    with TestClient(app) as client:
        assert client.post('/plans', json=command).status_code == 422
        incomplete = client.post('/plans/what-if', json=command)
        assert incomplete.status_code == 500 and incomplete.json()['detail']['code'] == 'MODULE_ERROR'
        result = copy.deepcopy(delivered[1])
        result['plans'].append({**result['plans'][0], 'plan_id': 'STABLE', 'plan_type': 'STABLE'})
        monkeypatch.setattr(planning, 'run', lambda request: (seen.append(request), result)[1])
        response = client.post('/plans/what-if', json=command)
        assert response.status_code == 200 and len(response.json()['result']['plans']) == 3
    assert seen[0].command.overrides == {'demand_multiplier': '1.1'}


@pytest.mark.parametrize('mutation', ['out_of_scope', 'unit', 'duplicate', 'fake_feasible', 'missing_coverage', 'hard_violation', 'still_typed', 'too_few', 'exception'])
def test_bad_module_output_is_safe_error(delivered, monkeypatch, mutation):
    from engine import planning
    result = copy.deepcopy(delivered[1])
    if mutation == 'out_of_scope': result['plans'][0]['production'][0]['product_id'] = 'UNKNOWN'
    if mutation == 'unit': result['plans'][0]['production'][0]['unit'] = 'kg'
    if mutation == 'duplicate': result['plans'][0]['production'] *= 2
    if mutation == 'fake_feasible': result['plans'][0]['feasibility'] = 'FEASIBLE'
    if mutation in ('missing_coverage', 'hard_violation', 'still_typed'):
        from contracts.interfaces.planning import PlanningOutput
        plan = result['plans'][0]
        plan.update(feasibility='FEASIBLE', policy_ref='TEST-POLICY', unverified=[])
        result['unverified'] = []
        for check in result['constraint_evaluations']:
            if check['plan_id'] == plan['plan_id']:
                check.update(strength='HARD', application_state='APPLIED',
                             status='VIOLATED' if mutation == 'hard_violation' else 'SATISFIED')
        if mutation == 'still_typed':
            result = PlanningOutput.model_validate(result)
            result.constraint_evaluations[0].status = 'VIOLATED'
        if mutation == 'missing_coverage':
            delivered[0].missing_inputs = []
    if mutation == 'too_few': result['plans'] = result['plans'][:1]
    def execute(request):
        if mutation == 'exception': raise RuntimeError('secret internal data')
        return result
    monkeypatch.setattr(planning, 'run', execute)
    with TestClient(app) as client:
        response = client.post('/plans', json=payload('planning_input.json')['command'])
    assert response.status_code == 500 and response.json()['detail']['code'] == 'MODULE_ERROR'
    assert 'secret' not in response.text


@pytest.mark.parametrize(('overrides', 'code'), [
    ({'production_qty.TP-10R': '1'}, 'PLAN_OVERRIDE_UNSUPPORTED'),
    ({'demand_multiplier': '-1'}, 'REQUEST_INVALID'),
    ({'demand_multiplier.OTHER': '1'}, 'PLAN_OVERRIDE_UNSUPPORTED'),
    ({'overtime_hours_limit.SAW1.2027-02': '1'}, 'PLAN_OVERRIDE_UNSUPPORTED'),
])
def test_invalid_what_if_request_is_explicit_even_when_calculation_is_disabled(overrides, code):
    body = {**payload('planning_input.json')['command'], 'scenario': 'WHAT_IF',
            'base_plan_execution_id': str(UUID(int=3)), 'overrides': overrides}
    with TestClient(app) as client:
        reply = client.post('/plans/what-if', json=body)
    detail = reply.json()['detail']
    assert reply.status_code == 422 and detail['code'] == code
    assert 'WHATIF_INVALID' in str(detail['details'])


def test_module_failure_is_not_http_success(delivered, monkeypatch):
    from engine import planning
    output = {**delivered[1], 'status': 'INPUT_INVALID', 'plans': [], 'constraint_evaluations': [],
              'errors': [{'code': 'MISSING_INPUT', 'message': 'Synthetic missing data', 'input_refs': []}]}
    monkeypatch.setattr(planning, 'run', lambda request: output)
    with TestClient(app) as client:
        response = client.post('/plans', json=payload('planning_input.json')['command'])
    assert response.status_code == 422 and response.json()['result']['status'] == 'INPUT_INVALID'


def test_disabled_module_never_loads_db(monkeypatch):
    from engine import planning
    monkeypatch.setattr(planning, 'AVAILABLE', False)
    def forbidden(): raise AssertionError('DB must not be accessed')
    with pytest.raises(ApiError) as error:
        adapter.execute(PlanCommand.model_validate(payload('planning_input.json')['command']), forbidden)
    assert error.value.code == ErrorCode.MODULE_NOT_IMPLEMENTED


def test_provider_exception_does_not_leak_source_or_credentials(delivered, monkeypatch):
    class Broken:
        def load(self, command): raise RuntimeError('private source and credentials')
    monkeypatch.setattr(adapter, 'get_source_provider', Broken)
    with TestClient(app) as client:
        response = client.post('/plans', json=payload('planning_input.json')['command'])
    assert response.status_code == 500 and response.json()['detail']['code'] == 'MODULE_ERROR'
    assert 'credentials' not in response.text


def test_missing_saved_base_does_not_fabricate_what_if(monkeypatch):
    from app.plans.repository import PlanRepository
    def missing(self,id):
        raise ApiError(404,ErrorCode.PLAN_NOT_FOUND,'Missing base execution')
    monkeypatch.setattr(PlanRepository,'get',missing)
    command = PlanCommand.model_validate({**payload('planning_input.json')['command'], 'scenario': 'WHAT_IF',
        'base_plan_execution_id': str(UUID(int=3))})
    with pytest.raises(ApiError) as error: adapter.SqlPlanningSourceProvider(None).load(command)
    assert error.value.status == 404 and error.value.code == ErrorCode.PLAN_NOT_FOUND


def test_corrupt_saved_base_is_reported_as_persistence_error(monkeypatch):
    from app.plans.repository import PlanRepository

    def corrupt(*args):
        raise ValueError('private stored snapshot')

    monkeypatch.setattr(PlanRepository, 'get', corrupt)
    command = PlanCommand.model_validate({**payload('planning_input.json')['command'], 'scenario': 'WHAT_IF',
                                         'base_plan_execution_id': str(UUID(int=3))})
    with pytest.raises(ApiError) as error:
        adapter.SqlPlanningSourceProvider(None).load(command)
    assert error.value.code == ErrorCode.PERSISTENCE_ERROR
    assert 'private' not in error.value.message
