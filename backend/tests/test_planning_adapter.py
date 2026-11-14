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
from contracts.interfaces.modules import PlanningInput, PlanCommand

ROOT = Path(__file__).resolve().parents[2] / 'contracts/examples/integration'


def payload(name): return json.loads((ROOT / name).read_text(encoding='utf-8'))['payload']


@pytest.fixture
def delivered(monkeypatch):
    from engine import planning
    source = PlanningInput.model_validate(payload('planning_input.json'))
    result = payload('planning_output.json')
    monkeypatch.setattr(planning, 'AVAILABLE', True)
    monkeypatch.setattr(planning, 'run', lambda request: copy.deepcopy(result))
    class Provider:
        def load(self, command):
            base = {'execution_id': str(command.base_plan_execution_id), 'forecast_execution_id': str(command.forecast_execution_id)} if command.scenario == 'WHAT_IF' else None
            return source.model_copy(update={'command': command, 'base_plan_snapshot': base}, deep=True)
    monkeypatch.setattr(adapter, 'get_source_provider', Provider)
    return source, result


def test_delivered_module_is_called_without_saving_or_approving(delivered):
    with TestClient(app) as client:
        response = client.post('/plans', json=payload('planning_input.json')['command'])
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
               'base_plan_execution_id': '00000000-0000-4000-8000-000000000003', 'overrides': {'production_qty': '8500'}}
    with TestClient(app) as client:
        assert client.post('/plans', json=command).status_code == 422
        assert client.post('/plans/what-if', json=command).status_code == 200
    assert seen[0].command.overrides == {'production_qty': '8500'}


@pytest.mark.parametrize('mutation', ['out_of_scope', 'unit', 'duplicate', 'fake_feasible', 'too_few', 'exception'])
def test_bad_module_output_is_safe_error(delivered, monkeypatch, mutation):
    from engine import planning
    result = copy.deepcopy(delivered[1])
    if mutation == 'out_of_scope': result['plans'][0]['production'][0]['product_id'] = 'UNKNOWN'
    if mutation == 'unit': result['plans'][0]['production'][0]['unit'] = 'kg'
    if mutation == 'duplicate': result['plans'][0]['production'] *= 2
    if mutation == 'fake_feasible': result['plans'][0]['feasibility'] = 'FEASIBLE'
    if mutation == 'too_few': result['plans'] = result['plans'][:1]
    def execute(request):
        if mutation == 'exception': raise RuntimeError('secret internal data')
        return result
    monkeypatch.setattr(planning, 'run', execute)
    with TestClient(app) as client:
        response = client.post('/plans', json=payload('planning_input.json')['command'])
    assert response.status_code == 500 and response.json()['detail']['code'] == 'MODULE_ERROR'
    assert 'secret' not in response.text


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


def test_missing_saved_base_does_not_fabricate_what_if():
    command = PlanCommand.model_validate({**payload('planning_input.json')['command'], 'scenario': 'WHAT_IF',
        'base_plan_execution_id': str(UUID(int=3))})
    with pytest.raises(ApiError) as error: adapter.SqlPlanningSourceProvider(None).load(command)
    assert error.value.code == ErrorCode.PLAN_HISTORY_NOT_IMPLEMENTED
