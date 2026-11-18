"""HTTP and shared input validation with typed, synthetic contract fixtures."""
from pathlib import Path
import json
from uuid import UUID

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import OperationalError

from app.api.plan_executions import get_service
from app.errors import ApiError, ErrorCode
from app.integrations import planning as adapter
from app.main import app
from app.plans.service import PlanService
from contracts.interfaces.planning import PlanningInput, PlanningInputDiagnostics


EXAMPLES = Path(__file__).resolve().parents[2] / 'contracts/examples/integration'
PATH = '/planning-inputs/preview'


def example(name):
    return json.loads((EXAMPLES / f'{name}.json').read_text(encoding='utf-8'))['payload']


@pytest.fixture
def snapshot_data():
    data = example('planning_input')
    facts = data['approved_inputs']
    source = facts['sources'][0]
    for index, entity in enumerate(('material', 'bom', 'inventory', 'capacity', 'routing'), start=10):
        facts['sources'].append({**source, 'batch_id': str(UUID(int=index)), 'entity': entity})
    facts['materials'] = [{'material_id': 'M', 'material_name': 'Synthetic', 'safety_stock_qty': '0',
                           'base_unit': 'kg', 'source_type': 'SYNTHETIC', 'batch_id': str(UUID(int=10))}]
    facts['boms'] = [{
        'header': {'bom_id': 'B', 'product_id': 'TP-10R', 'bom_version': 'V1', 'status': 'ACTIVE',
                   'is_active': True, 'valid_from': '2026-12-01', 'valid_to': None, 'base_qty': '1'},
        'lines': [{'bom_id': 'B', 'line_no': 1, 'component_type': 'MATERIAL', 'component_id': 'M',
                   'qty_per': '2', 'unit': 'kg', 'scrap_rate': '0'}],
        'source_type': 'SYNTHETIC', 'batch_id': str(UUID(int=11)),
    }]
    facts['inventory'] = [
        {'item_type': kind, 'item_id': key, 'unit': unit, 'as_of_date': '2026-12-31',
         'on_hand_qty': '3', 'allocated_qty': '0', 'source_type': 'SYNTHETIC', 'batch_id': str(UUID(int=12))}
        for kind, key, unit in [('PRODUCT', 'TP-10R', 'EA'), ('MATERIAL', 'M', 'kg')]
    ]
    resource = {'resource_id': 'R', 'resource_name': 'Synthetic', 'kind': 'EQUIPMENT',
                'time_basis': 'MACHINE_HOUR', 'parallel_units': 1}
    draft = {'resources': [resource], 'quantity_limits': [], 'hours_budgets': [], 'routing_steps': []}
    data['capacity_snapshot'] = {**draft, 'hours_budgets': [
        {'capacity_id': 'CAP', 'period': '2027-01', 'resource_id': 'R', 'regular_hours': '100',
         'unit': 'h', 'time_basis': 'MACHINE_HOUR', 'availability_basis': 'NET'}]}
    data['routing_snapshot'] = {**draft, 'routing_steps': [
        {'routing_id': 'RT', 'routing_version': 'V1', 'step_id': 'S', 'product_id': 'TP-10R',
         'operation_id': 'OP', 'resource_id': 'R', 'predecessor_step_ids': [], 'reference_qty': '1',
         'quantity_unit': 'EA', 'run_time': '1', 'time_unit': 'min', 'time_basis': 'MACHINE_HOUR',
         'valid_from': '2026-12-01', 'valid_to': None}]}
    data['missing_inputs'] = ['POLICY_NOT_CONFIRMED']
    return data


def use_provider(monkeypatch, data):
    class ContractProvider:
        def __init__(self, dataset_id='TISSUE-LEGACY'):
            self.dataset_id = dataset_id

        def load(self, command):
            assert command.dataset_id == self.dataset_id
            return PlanningInput.model_validate({**data, 'dataset_id': self.dataset_id, 'command': command})

    monkeypatch.setattr(adapter, 'get_source_provider', ContractProvider)


def test_summary_does_not_calculate_or_create_plan_history(monkeypatch, snapshot_data):
    from engine import planning

    def forbidden(*args, **kwargs):
        pytest.fail('Diagnostics must never call calculation or plan save')

    monkeypatch.setattr(planning, 'AVAILABLE', False)
    monkeypatch.setattr(planning, 'run', forbidden)
    monkeypatch.setattr('app.plans.repository.PlanRepository.save', forbidden)
    use_provider(monkeypatch, snapshot_data)
    command = snapshot_data['command']

    class Database:
        def connect(self):
            forbidden()

        def begin(self):
            forbidden()

    service = PlanService(Database())
    app.dependency_overrides[get_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(PATH, json=command)
            assert response.status_code == 200
            preview = client.post('/plans', json=command)
            assert preview.status_code == 501 and preview.json()['detail']['code'] == 'MODULE_NOT_IMPLEMENTED'
            stored = client.post('/plan-executions', json=command)
            assert stored.status_code == 501 and stored.json()['detail']['code'] == 'MODULE_NOT_IMPLEMENTED'
    finally:
        app.dependency_overrides.pop(get_service)

    report = PlanningInputDiagnostics.model_validate(response.json())
    assert report.engine_available is False and report.persisted is False
    assert report.status == 'INPUTS_PRESENT' and report.scope == 'SINGLE_MONTH'
    assert report.warning_codes == ['POLICY_NOT_CONFIRMED'] and report.missing_inputs == []
    assert report.inputs['forecast'].row_count == 1 and report.inputs['routing'].ready
    assert report.inputs['quantity_limits'].row_count == 0 and report.inputs['quantity_limits'].ready
    assert len(report.approved_sources) == 6
    assert report.input_digest == adapter.snapshot_digest(PlanningInput.model_validate(snapshot_data))
    assert 'result' not in response.json() and 'execution_id' not in response.json()


def test_incomplete_inputs_report_coverage_using_query_dataset(monkeypatch):
    data = example('planning_input')
    use_provider(monkeypatch, data)
    with TestClient(app) as client:
        response = client.post(PATH, params={'dataset_id': 'CHUNGPAMO-2027'}, json=data['command'])
    assert response.status_code == 200
    report = response.json()
    assert report['dataset_id'] == 'CHUNGPAMO-2027' and report['status'] == 'NEEDS_REVIEW'
    assert {'BOM_COVERAGE', 'INVENTORY_COVERAGE', 'HOURS_COVERAGE', 'ROUTING_COVERAGE'} <= set(report['missing_inputs'])
    assert report['inputs']['inventory'] == {'ready': False, 'row_count': 0}
    assert report['inputs']['forecast']['ready'] is True


def test_engine_available_does_not_resolve_ambiguous_input_or_call_engine(monkeypatch, snapshot_data):
    from engine import planning

    monkeypatch.setattr(planning, 'AVAILABLE', True)
    monkeypatch.setattr(planning, 'run', lambda _: pytest.fail('diagnostics must not calculate'))
    bom = snapshot_data['approved_inputs']['boms'][0]
    bom['header']['valid_from'] = '2027-01-02'
    inventory = snapshot_data['approved_inputs']['inventory']
    inventory.append({**inventory[0], 'as_of_date': '2026-12-30'})
    use_provider(monkeypatch, snapshot_data)
    with TestClient(app) as client:
        response = client.post(PATH, json=snapshot_data['command'])
    assert response.status_code == 200
    report = response.json()
    assert report['engine_available'] is True and report['status'] == 'NEEDS_REVIEW'
    assert report['missing_inputs'] == []
    assert set(report['warning_codes']) == {'BOM_VERSION_POLICY_REQUIRED', 'INVENTORY_SNAPSHOT_POLICY_REQUIRED', 'POLICY_NOT_CONFIRMED'}
    assert not report['inputs']['bom']['ready'] and not report['inputs']['inventory']['ready']


def test_example_matches_the_api_response(monkeypatch):
    data = example('planning_input')
    use_provider(monkeypatch, data)
    with TestClient(app) as client:
        response = client.post(PATH, json=data['command'])
    assert response.status_code == 200 and response.json() == example('planning_input_diagnostics')


@pytest.mark.parametrize(('change', 'status', 'code'), [
    ({'dataset_id': 'OTHER'}, 409, 'DATASET_MISMATCH'),
    ({'forecast_execution_id': 'not-a-uuid'}, 422, 'REQUEST_INVALID'),
    ({'target_month': '2027-13'}, 422, 'REQUEST_INVALID'),
    ({'as_of_date': '2026-02-30'}, 422, 'REQUEST_INVALID'),
    ({'scenario': 'WHAT_IF', 'base_plan_execution_id': str(UUID(int=4))}, 422, 'REQUEST_INVALID'),
])
def test_invalid_requests_do_not_load_provider(monkeypatch, change, status, code):
    monkeypatch.setattr(adapter, 'get_source_provider', lambda *args: pytest.fail('unexpected read'))
    with TestClient(app) as client:
        response = client.post(PATH, json={**example('planning_input')['command'], **change})
    assert response.status_code == status and response.json()['detail']['code'] == code


@pytest.mark.parametrize('missing', [True, False])
def test_provider_error_contract_is_preserved(monkeypatch, missing):
    def unavailable(*args):
        if missing:
            raise ApiError(404, ErrorCode.FORECAST_NOT_FOUND, 'Forecast not found.')
        raise OperationalError(None, None, RuntimeError('private database details'))

    class Database:
        connect = unavailable

    def factory():
        return adapter.SqlPlanningSourceProvider(Database())

    monkeypatch.setattr(adapter, 'get_source_provider', factory)
    with TestClient(app) as client:
        response = client.post(PATH, json=example('planning_input')['command'])
    assert response.status_code == (404 if missing else 503)
    assert response.json()['detail']['code'] == ('FORECAST_NOT_FOUND' if missing else 'DB_UNAVAILABLE')
    assert 'private' not in response.text


@pytest.mark.parametrize(('path', 'value', 'reason'), [
    (('forecast_rows', 0, 'target_month'), '2027-02', 'FORECAST_PRODUCT_MONTH_COVERAGE'),
    (('forecast_rows', 0, 'product_id'), 'OTHER', 'FORECAST_PRODUCT_MONTH_COVERAGE'),
    (('approved_inputs', 'boms', 0, 'header', 'product_id'), 'OTHER', 'BOM_PRODUCT_OR_PERIOD_MISMATCH'),
    (('approved_inputs', 'boms', 0, 'lines', 0, 'component_id'), 'OTHER', 'BOM_COMPONENT_OR_UNIT_MISMATCH'),
    (('approved_inputs', 'boms', 0, 'lines', 0, 'unit'), 'EA', 'BOM_COMPONENT_OR_UNIT_MISMATCH'),
    (('approved_inputs', 'inventory', 0, 'as_of_date'), '2027-01-01', 'INVENTORY_REFERENCE_UNIT_OR_DATE_MISMATCH'),
    (('capacity_snapshot', 'hours_budgets', 0, 'period'), '2027-02', 'CAPACITY_PERIOD_MISMATCH'),
    (('capacity_snapshot', 'hours_budgets', 0, 'time_basis'), 'PERSON_HOUR', 'STORED_INPUT_INVALID'),
    (('routing_snapshot', 'routing_steps', 0, 'resource_id'), 'OTHER', 'STORED_INPUT_INVALID'),
    (('routing_snapshot', 'routing_steps', 0, 'product_id'), 'OTHER', 'ROUTING_PRODUCT_UNIT_OR_PERIOD_MISMATCH'),
    (('routing_snapshot', 'routing_steps', 0, 'quantity_unit'), 'kg', 'ROUTING_PRODUCT_UNIT_OR_PERIOD_MISMATCH'),
    (('approved_inputs', 'sources', 0, 'entity'), 'material', 'APPROVED_SOURCE_MISMATCH'),
])
def test_conflicting_inputs_return_safe_409(monkeypatch, snapshot_data, path, value, reason):
    node = snapshot_data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    use_provider(monkeypatch, snapshot_data)
    with TestClient(app) as client:
        response = client.post(PATH, json=snapshot_data['command'])
    assert response.status_code == 409
    assert response.json()['detail']['details'] == {'reason': reason}


def test_storage_disabled_keeps_existing_error_contract():
    with TestClient(app) as client:
        response = client.post(PATH, json=example('planning_input')['command'])
    assert response.status_code == 501 and response.json()['detail']['code'] == 'PERSISTENCE_DISABLED'
