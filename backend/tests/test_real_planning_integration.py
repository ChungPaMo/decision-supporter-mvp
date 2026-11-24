"""Real adapter and core with synthetic approved facts and an in-memory repository."""
from contextlib import contextmanager
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from app.api.plan_executions import get_service
from app.errors import ApiError, ErrorCode
from app.integrations import planning
from app.integrations.planning_validation import input_coverage, validate_pair
from app.main import app
from app.plans.repository import digest
from app.plans.service import PlanService, what_if_snapshot
from contracts.interfaces.plan_execution import PlanExecutionDetail
from contracts.interfaces.planning import PlanningInput, PlanningReply
from tests.test_planning_input_diagnostics import snapshot_data  # Reuse synthetic coverage fixture.


OFFICIAL = Path(__file__).resolve().parents[2] / 'modules/planning_engine/tests/chungpamo'


@pytest.fixture
def official():
    return PlanningInput.model_validate(json.loads((OFFICIAL / 'planning_input.json').read_text(encoding='utf-8'))['payload'])


def post(client, path, command):
    return client.post(path, params={'dataset_id': command.dataset_id}, json=command.model_dump(mode='json'))


def rounded(value):
    if value is None:
        return None
    exact = Fraction(value)
    return (Decimal(exact.numerator) / Decimal(exact.denominator)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def test_official_preview_matches_independent_answer(monkeypatch, official):
    source = SimpleNamespace(load=lambda cmd: official.model_copy(update={'command': cmd}))
    monkeypatch.setattr(planning, 'get_source_provider', lambda dataset: source)
    client = TestClient(app)
    report = post(client, '/planning-inputs/preview', official.command)
    reply = post(client, '/plans', official.command)
    assert report.status_code == reply.status_code == 200, reply.json()
    assert report.json()['engine_available'] and report.json()['status'] == 'INPUTS_PRESENT'
    assert report.json()['missing_inputs'] == report.json()['warning_codes'] == []
    result = PlanningReply.model_validate(reply.json())
    assert result.input_digest == report.json()['input_digest'] and not result.persisted
    assert result.result.status == 'OK' and len(result.result.constraint_evaluations) == 306
    actual = result.result
    expected = json.loads((OFFICIAL / 'expected.json').read_text(encoding='utf-8'))
    assert {plan.plan_id for plan in actual.plans} == expected.keys()
    for plan in actual.plans:
        gold = expected[plan.plan_id]
        assert plan.feasibility == gold['feasibility']
        assert {(r.product_id, r.period): int(r.production_qty) for r in plan.production} == {
            (product, month): qty for product, rows in gold['production'].items()
            for month, qty in zip(official.command.months, rows, strict=True)}
        evaluations = {r.constraint_id: r for r in actual.constraint_evaluations if r.plan_id == plan.plan_id}
        assert evaluations.keys() == {r['constraint_id'] for r in gold['evaluations']}
        for row in gold['evaluations']:
            item = evaluations[row['constraint_id']]
            assert (item.status, set(item.reason_codes)) == (row['status'], set(row['reason_codes']))
            used = rounded(row.get('used_value'))
            if item.dimension == 'SAFETY_STOCK' and used is not None:
                used = max(0, used)
            assert (rounded(item.limit_value), rounded(item.used_value)) == (rounded(row.get('limit_value')), used)
        material = {(r.material_id, r.period): (rounded(r.required_qty), rounded(r.available_qty), rounded(r.shortage_qty))
                    for r in actual.material_requirements if r.plan_id == plan.plan_id}
        assert material == {(key, month): tuple(rounded(data[field][i]) for field in ('required', 'available', 'shortage'))
                            for key, data in gold['material_requirements'].items()
                            for i, month in enumerate(official.command.months)}


def test_receipt_feed_distinguishes_open_empty_and_unconnected(official):
    def result(receipts):
        snapshot = official.model_copy(update={'scheduled_receipts': receipts})
        return planning.run_snapshot(snapshot.command, snapshot).result

    complete, empty, missing = map(result, (official.scheduled_receipts, [], None))
    assert complete.status == empty.status == missing.status == 'OK'
    assert complete.unverified == empty.unverified == []
    assert [row.code for row in missing.unverified] == ['RECEIPT_SOURCE_UNAVAILABLE']
    assert all(plan.feasibility != 'FEASIBLE' for plan in missing.plans)

    def january_available(output):
        return Decimal(next(row.available_qty for row in output.material_requirements if
                            (row.plan_id, row.material_id, row.period) == ('BASELINE', 'MR-N3', '2027-01')))

    assert january_available(complete) - january_available(empty) == 10000
    assert january_available(empty) == january_available(missing)


@pytest.mark.parametrize('horizon', [1, 3, 6, 12])
def test_complete_used_scope_stays_feasible(snapshot_data, horizon):
    snapshot_data['command']['horizon_months'] = horizon
    months = [f'2027-{i:02}' for i in range(1, horizon + 1)]
    forecast = snapshot_data['forecast_rows'][0]
    snapshot_data['forecast_rows'] = [{**forecast, 'target_month': m, 'p50': '1', 'p80': '1', 'p90': '1'} for m in months]
    snapshot_data['approved_inputs']['products'][0]['safety_stock_qty'] = '0'
    snapshot_data['approved_inputs']['inventory'][1]['on_hand_qty'] = '100'
    draft = snapshot_data['capacity_snapshot']
    budget = draft['hours_budgets'][0]
    draft['hours_budgets'] = [{**budget, 'period': m} for m in months]
    draft['resources'] = [*draft['resources'], {**draft['resources'][0], 'resource_id': 'UNUSED'}]
    snapshot = PlanningInput.model_validate(snapshot_data)
    reply = planning.run_snapshot(snapshot.command, snapshot)
    assert reply.result.unverified == []
    assert all(plan.feasibility == 'FEASIBLE' for plan in reply.result.plans)
    assert {r.period for plan in reply.result.plans for r in plan.production} == set(months)
    assert all(r.resource_id != 'UNUSED' for r in reply.result.constraint_evaluations)


def test_required_missing_codes_track_real_calculation_without_duplicates(snapshot_data):
    snapshot_data['forecast_rows'][0].update(p50='1', p80='1', p90='1')
    snapshot_data['capacity_snapshot']['hours_budgets'] = []
    snapshot_data['approved_inputs']['inventory'].pop()
    snapshot_data['scheduled_receipts'] = None
    snapshot_data['missing_inputs'] += ['HOURS_COVERAGE', 'HOURS_COVERAGE']
    snapshot = PlanningInput.model_validate(snapshot_data)
    _, missing, warnings = input_coverage(snapshot)
    assert missing == ['HOURS_COVERAGE', 'INVENTORY_COVERAGE', 'RECEIPT_SOURCE_UNAVAILABLE'] and warnings == []
    result = planning.run_snapshot(snapshot.command, snapshot).result
    assert [issue.code for issue in result.unverified] == ['RECEIPT_SOURCE_UNAVAILABLE', 'HOURS_COVERAGE', 'INVENTORY_COVERAGE']
    assert {p.feasibility for p in result.plans} == {'UNVERIFIED'}
    assert any(row.status == 'UNVERIFIED' and row.resource_id == 'R' for row in result.constraint_evaluations)
    result.plans[0].feasibility = 'FEASIBLE'
    with pytest.raises(ValueError):
        validate_pair(snapshot, result)


@pytest.mark.parametrize('state, expected_status, suffix', [
    ('next_month', 200, 'VERSION_SELECTED'), ('midmonth', 422, 'VERSION_MIDMONTH'),
    ('ambiguous', 422, 'VERSION_AMBIGUOUS'), ('missing', 200, 'COVERAGE'),
])
@pytest.mark.parametrize('kind', ['BOM', 'ROUTING'])
def test_version_diagnostics_match_http_calculation(monkeypatch, snapshot_data, kind, state, expected_status, suffix):
    from copy import deepcopy

    snapshot_data['command']['horizon_months'] = 2
    forecast = snapshot_data['forecast_rows'][0]
    snapshot_data['forecast_rows'].append({**forecast, 'target_month': '2027-02'})
    budgets = snapshot_data['capacity_snapshot']['hours_budgets']
    budgets.append({**budgets[0], 'period': '2027-02'})
    if kind == 'BOM':
        rows = snapshot_data['approved_inputs']['boms']
        active, next_version = rows[0]['header'], deepcopy(rows[0])
        updated = next_version['header']
        updated.update(bom_id='B-NEXT', bom_version='V2')
        next_version['lines'][0].update(bom_id='B-NEXT', qty_per='3')
    else:
        rows = snapshot_data['routing_snapshot']['routing_steps']
        active, next_version = rows[0], deepcopy(rows[0])
        updated = next_version
        updated.update(routing_version='V2', run_time='2')
    if state in ('next_month', 'missing'):
        active['valid_to'] = '2027-01-31'
    if state == 'midmonth':
        active['valid_to'] = '2027-01-14'
    updated['valid_from'] = {'next_month': '2027-02-01', 'midmonth': '2027-01-15'}.get(state, '2027-01-01')
    if state != 'missing':
        rows.append(next_version)

    snapshot = PlanningInput.model_validate(snapshot_data)
    monkeypatch.setattr(planning, 'get_source_provider', lambda: SimpleNamespace(load=lambda _: snapshot))
    client = TestClient(app)
    diag = post(client, '/planning-inputs/preview', snapshot.command).json()
    reply = post(client, '/plans', snapshot.command)
    assert reply.status_code == expected_status, reply.json()
    output = PlanningReply.model_validate(reply.json()).result
    code = kind + '_' + suffix
    if state == 'next_month':
        assert diag['status'] == 'INPUTS_PRESENT' and not diag['warning_codes']
        assert {tuple(issue.input_refs[1:]) for issue in output.evidence if issue.code == code} == (
            {('2027-01', 'B', 'V1'), ('2027-02', 'B-NEXT', 'V2')} if kind == 'BOM'
            else {('2027-01', 'RT', 'V1'), ('2027-02', 'RT', 'V2')})
    elif state == 'missing':
        assert code in diag['missing_inputs'] and code not in diag['warning_codes']
        assert code in {issue.code for issue in output.unverified}
        assert all(plan.feasibility != 'FEASIBLE' for plan in output.plans)
    else:
        assert code not in diag['missing_inputs'] and code in diag['warning_codes']
        assert output.status == ('UNSUPPORTED' if state == 'midmonth' else 'INPUT_INVALID')
        assert code in {issue.code for issue in output.errors} and not output.plans


class MemoryPlans:
    def __init__(self):
        self.items = {}
        self.keys = {}

    def lock_and_find_reusable(self, _, key):
        return self.keys.get(key)

    def detail(self, _, id):
        return self.items[id]

    def save(self, _, snapshot, result, runtime, key):
        command = snapshot.command
        row = PlanExecutionDetail(execution_id=UUID(int=len(self.items) + 1), dataset_id=snapshot.dataset_id,
            forecast_execution_id=command.forecast_execution_id, base_plan_execution_id=command.base_plan_execution_id,
            scenario_type=command.scenario, target_month=command.target_month, horizon_months=command.horizon_months,
            as_of_date=command.as_of_date.isoformat(), status='COMPLETED', input_digest=planning.snapshot_digest(snapshot),
            result_digest=digest(result.model_dump(mode='json')), engine_version=runtime['engine_version'],
            runtime_identity=runtime, policy_version=result.plans[0].policy_ref, created_at='2026-11-24T00:00:00Z',
            completed_at='2026-11-24T00:00:00Z', error_code=None, data_origin='REAL_ENGINE', decision_status='DRAFT',
            selected_plan_id=None, version=1, input_snapshot=snapshot, result_snapshot=result)
        self.keys[key] = row.execution_id
        self.items[row.execution_id] = row
        return row


def test_actual_base_and_what_if_through_preview_and_memory_storage(monkeypatch, official):
    class MemoryDatabase:
        dataset_id = official.dataset_id

        @contextmanager
        def begin(self):
            yield self

    service = PlanService(MemoryDatabase())
    service.repo = MemoryPlans()

    def load(command):
        if command.scenario == 'BASE':
            return official.model_copy(update={'command': command})
        return what_if_snapshot(service.repo.items[command.base_plan_execution_id], command)

    provider = SimpleNamespace(load=load)
    monkeypatch.setattr(planning, 'get_source_provider', lambda _: provider)
    monkeypatch.setattr(planning, 'SqlPlanningSourceProvider', lambda _: provider)
    monkeypatch.setitem(app.dependency_overrides, get_service, lambda: service)
    client = TestClient(app)
    base = post(client, '/plan-executions', official.command)
    repeat = post(client, '/plan-executions', official.command)
    assert (base.status_code, repeat.status_code) == (201, 200)
    parent = PlanExecutionDetail.model_validate(base.json()['execution'])
    assert repeat.json() == {'execution': base.json()['execution'], 'reused': True}
    assert parent.result_snapshot.status == 'OK' and len(parent.result_snapshot.plans) == 3
    assert parent.result_digest == digest(parent.result_snapshot.model_dump(mode='json'))
    what_if = parent.input_snapshot.command.model_copy(update={'scenario': 'WHAT_IF', 'base_plan_execution_id': parent.execution_id,
        'overrides': {'overtime_hours_limit.SAW1.2027-02': '80', 'receipt_qty.PO-2701-001': '0'}})
    preview, child, retry = (post(client, path, what_if) for path in ('/plans/what-if', '/plan-executions', '/plan-executions'))
    assert (preview.status_code, child.status_code, retry.status_code) == (200, 201, 200)
    saved = PlanExecutionDetail.model_validate(child.json()['execution'])
    assert retry.json() == {'execution': child.json()['execution'], 'reused': True} and len(service.repo.items) == 2
    assert saved.result_snapshot == PlanningReply.model_validate(preview.json()).result
    assert saved.input_digest == preview.json()['input_digest'] != parent.input_digest
    assert saved.input_snapshot.base_plan_snapshot['result_digest'] == parent.result_digest
    assert saved.input_snapshot.base_plan_snapshot['result'] == parent.result_snapshot.model_dump(mode='json')
    assert saved.input_snapshot.scheduled_receipts == parent.input_snapshot.scheduled_receipts
    assert [plan.plan_type for plan in saved.result_snapshot.plans] == [plan.plan_type for plan in parent.result_snapshot.plans]
    assert saved.result_snapshot.material_requirements != parent.result_snapshot.material_requirements
    assert saved.result_snapshot.constraint_evaluations != parent.result_snapshot.constraint_evaluations


@pytest.mark.parametrize('mutate', ['drop', 'duplicate', 'duplicate_warning'])
def test_run_snapshot_rejects_bad_missing_evidence(monkeypatch, official, mutate):
    from engine import planning as engine

    snapshot = official.model_copy(update={'scheduled_receipts': None})
    real_run = engine.run

    def corrupt(request):
        output = real_run(request)
        if mutate == 'duplicate_warning':
            output.warnings = output.unverified * 2
        else:
            output.unverified = [] if mutate == 'drop' else output.unverified * 2
        return output

    monkeypatch.setattr(engine, 'run', corrupt)
    with pytest.raises(ApiError) as error:
        planning.run_snapshot(snapshot.command, snapshot)
    assert (error.value.status, error.value.code) == (500, ErrorCode.MODULE_ERROR)
