"""Explicit TEST DOUBLE boundary tests, never actual planning algorithm results."""
import copy
import json
from pathlib import Path
from uuid import UUID
from types import SimpleNamespace
from contextlib import contextmanager
from io import BytesIO
import pytest
from openpyxl import load_workbook
from fastapi.testclient import TestClient
from app.main import app
from app.errors import ApiError,ErrorCode
from app.integrations.planning_validation import validate_pair
from app.plans.service import what_if_snapshot, PlanService
from app.plans.repository import PlanRepository, digest
from app.plans.approval import transition,ApprovalContext
from app.plans.exports import test_double_export as make_test_export,formal_export
from contracts.interfaces.planning import PlanningInput,PlanningOutput,PlanCommand
from contracts.interfaces.plan_execution import PlanExecutionDetail,PlanDecisionRequest

ROOT=Path(__file__).resolve().parents[2]


def example():
    folder=ROOT/'contracts/examples/integration'
    inp=PlanningInput.model_validate(json.loads((folder/'planning_input.json').read_text(encoding='utf-8'))['payload'])
    out=PlanningOutput.model_validate(json.loads((folder/'planning_output.json').read_text(encoding='utf-8'))['payload'])
    return PlanExecutionDetail(execution_id=UUID(int=10),forecast_execution_id=inp.command.forecast_execution_id,
        base_plan_execution_id=None,scenario_type='BASE',target_month='2027-01',as_of_date='2026-12-31',status='PARTIAL',
        input_digest=digest(inp.model_dump(mode='json')),result_digest=digest(out.model_dump(mode='json')),
        engine_version=out.module_version,policy_version=None,runtime_identity={'test_double':True},
        created_at='2026-11-15T00:00:00Z',completed_at='2026-11-15T00:00:00Z',error_code=None,data_origin='TEST_DOUBLE',
        decision_status='DRAFT',selected_plan_id=None,version=1,input_snapshot=inp,result_snapshot=out)


def request(e,action='REVIEW',**changes):
    return PlanDecisionRequest(plan_id=e.result_snapshot.plans[0].plan_id,action=action,actor_id='REVIEWER-TEST',reason='SYNTHETIC test only',
        expected_version=e.version,expected_input_digest=e.input_digest,**changes)


def eligible_in_memory_only():
    # Pure transition test state, never persisted or exposed via a real API.
    from contracts.interfaces.planning import PlanningIssue
    e=example();e.data_origin='REAL_ENGINE';e.policy_version='TEST-POLICY'
    e.input_snapshot.missing_inputs=[];e.result_snapshot.unverified=[]
    e.result_snapshot.evidence=[PlanningIssue(code='TEST',message='Independent state-machine test',input_refs=[])]
    for p in e.result_snapshot.plans:p.feasibility='FEASIBLE';p.policy_ref='TEST-POLICY';p.unverified=[]
    for c in e.result_snapshot.constraint_evaluations:c.status='SATISFIED';c.application_state='APPLIED'
    return e


def test_input_digest_is_canonical_and_sensitive():
    e=example();d=e.input_snapshot.model_dump(mode='json')
    assert digest(d)==digest(dict(reversed(list(d.items()))))
    d['forecast_rows'][0]['p50']='1';assert digest(d)!=e.input_digest


@pytest.mark.parametrize('problem',['unit','scope','month','missing_forecast','constraint_product','material_reference'])
def test_scope_and_reference_validation(problem):
    e=example();s=e.input_snapshot;r=e.result_snapshot
    if problem=='unit':r.plans[0].production[0].unit='KG'
    if problem=='scope':r.plans[0].production[0].product_id='UNKNOWN'
    if problem=='month':r.plans[0].production[0].period='2027-02'
    if problem=='missing_forecast':s.forecast_rows=[]
    if problem=='constraint_product':r.constraint_evaluations[0].product_id='UNKNOWN'
    if problem=='material_reference':
        from contracts.interfaces.planning import MaterialRequirement
        r.material_requirements=[MaterialRequirement(plan_id=r.plans[0].plan_id,material_id='UNKNOWN',period='2027-01',required_qty=None,available_qty=None,shortage_qty=None,unit='EA',input_refs=[])]
    with pytest.raises(ValueError):validate_pair(s,r)


@pytest.mark.parametrize('patch',[{'plans':[]},{'constraint_evaluations':[{'plan_id':'unknown'}]},{'status':'FAILED'}])
def test_invalid_engine_dto_is_rejected(patch):
    e=example();data=e.result_snapshot.model_dump(mode='json');data.update(patch)
    with pytest.raises(ValueError):PlanningOutput.model_validate(data)


@pytest.mark.parametrize('problem',['base','forecast','product','month','override','quarantine'])
def test_what_if_scope_and_test_double_isolation(problem):
    e=example();data=e.input_snapshot.command.model_dump(mode='json')
    data.update(scenario='WHAT_IF',base_plan_execution_id=str(e.execution_id))
    if problem=='base':data['base_plan_execution_id']=str(UUID(int=999))
    if problem=='forecast':data['forecast_execution_id']=str(UUID(int=999))
    if problem=='product':data['product_ids']=['UNKNOWN']
    if problem=='month':data['target_month']='2027-02'
    if problem=='override':data['overrides']={'forecast_execution_id':'123'}
    with pytest.raises(ApiError):what_if_snapshot(e,PlanCommand.model_validate(data),allow_test=problem!='quarantine')


@pytest.mark.parametrize(('changes', 'status'), [
    ({'overrides': {'overtime_hours_limit.UNKNOWN.2027-01': '1'}}, 422),
    ({'overrides': {'receipt_qty.UNKNOWN': '0'}}, 422),
    ({'horizon_months': 3}, 409),
])
def test_what_if_parent_scope_checks_resources_purchase_orders_and_horizon(changes, status):
    parent = example()
    body = {**parent.input_snapshot.command.model_dump(), 'scenario': 'WHAT_IF',
            'base_plan_execution_id': parent.execution_id, **changes}
    with pytest.raises(ApiError) as error:
        what_if_snapshot(parent, PlanCommand.model_validate(body), allow_test=True)
    assert error.value.status == status
    if status == 422:
        assert error.value.details == {'status': 'INPUT_INVALID', 'reason': 'WHATIF_INVALID'}


def test_what_if_preserves_original_snapshot_and_results():
    e=example();before=e.model_dump(mode='json')
    cmd=PlanCommand(**{**e.input_snapshot.command.model_dump(),'scenario':'WHAT_IF','base_plan_execution_id':e.execution_id,'overrides':{'demand_multiplier.TP-10R':'100'}})
    child=what_if_snapshot(e,cmd,allow_test=True)
    assert child.command.overrides['demand_multiplier.TP-10R']=='100'
    assert child.base_plan_snapshot['result']==e.result_snapshot.model_dump(mode='json')
    child.forecast_rows[0].p50='0'
    assert e.model_dump(mode='json')==before


def test_what_if_preserves_absolute_monthly_and_receipt_overrides_without_editing_facts():
    from contracts.interfaces.capacity import CapacityRegistrationDraft
    from contracts.interfaces.planning import ScheduledReceipt

    parent = example()
    parent.input_snapshot.command.horizon_months = parent.horizon_months = 3
    parent.input_snapshot.scheduled_receipts = [ScheduledReceipt(
        po_id='PO1', material_id='MAT1', open_qty='50', unit='EA', expected_date='2027-01-20', batch_id=UUID(int=4),
    )]
    parent.input_snapshot.capacity_snapshot = CapacityRegistrationDraft.model_validate({
        'resources': [{'resource_id': 'SAW1', 'resource_name': 'Synthetic', 'kind': 'EQUIPMENT',
                       'time_basis': 'MACHINE_HOUR', 'parallel_units': 1}],
        'quantity_limits': [], 'hours_budgets': [], 'routing_steps': [],
    })
    overrides = {'demand_multiplier': '1.1', 'demand_multiplier.TP-10R': '0.9',
                 'overtime_hours_limit.SAW1.2027-02': '80', 'receipt_qty.PO1': '0'}
    command = PlanCommand.model_validate({**parent.input_snapshot.command.model_dump(), 'scenario': 'WHAT_IF',
                                         'base_plan_execution_id': parent.execution_id, 'overrides': overrides})
    child = what_if_snapshot(parent, command, allow_test=True)
    assert child.command.overrides == overrides
    assert child.approved_inputs == parent.input_snapshot.approved_inputs
    assert child.scheduled_receipts == parent.input_snapshot.scheduled_receipts
    assert child.scheduled_receipts[0].open_qty == '50'


@pytest.mark.parametrize('horizon', [1, 3, 6, 12])
def test_output_validation_covers_each_requested_product_month(horizon):
    execution = example()
    snapshot, result = execution.input_snapshot, execution.result_snapshot
    snapshot.command.horizon_months = horizon
    periods = snapshot.command.months
    snapshot.forecast_rows = [snapshot.forecast_rows[0].model_copy(update={'target_month': period}) for period in periods]
    result.status = 'OK'
    for candidate in result.plans:
        candidate.production = [candidate.production[0].model_copy(update={'period': period}) for period in periods]
    validate_pair(snapshot, result)
    result.plans[0].production.pop()
    with pytest.raises(ValueError, match='Incomplete OK candidate'):
        validate_pair(snapshot, result)


@pytest.mark.parametrize(('strength', 'status', 'valid'), [
    ('HARD', 'VIOLATED', False), ('HARD', 'UNVERIFIED', False),
    ('SOFT', 'VIOLATED', True), ('SOFT', 'UNVERIFIED', True),
    (None, 'VIOLATED', False), (None, 'UNVERIFIED', False), (None, 'SATISFIED', True),
])
def test_feasibility_considers_only_the_candidate_checks_and_their_strength(strength, status, valid):
    result = eligible_in_memory_only().result_snapshot
    result.plans[1].feasibility = 'INFEASIBLE'
    for check in result.constraint_evaluations:
        if check.plan_id == result.plans[0].plan_id:
            check.strength, check.status = strength, status
        else:
            check.strength, check.status = 'HARD', 'VIOLATED'
    if valid:
        assert PlanningOutput.model_validate(result.model_dump()).plans[0].feasibility == 'FEASIBLE'
    else:
        with pytest.raises(ValueError):
            PlanningOutput.model_validate(result.model_dump())


@pytest.mark.parametrize('issue', ['result', 'candidate', 'policy_ref'])
def test_feasible_requires_resolved_issues_and_policy_reference(issue):
    result = eligible_in_memory_only().result_snapshot.model_dump(mode='json')
    notice = {'code': 'MISSING', 'message': 'Unresolved input'}
    if issue == 'result':
        result['unverified'] = [notice]
    elif issue == 'candidate':
        result['plans'][0]['unverified'] = [notice]
    else:
        result['plans'][0]['policy_ref'] = ' '
    with pytest.raises(ValueError):
        PlanningOutput.model_validate(result)


def test_contradictory_output_is_rejected_before_persistence():
    execution = eligible_in_memory_only()
    check = execution.result_snapshot.constraint_evaluations[0]
    check.strength, check.status = 'HARD', 'VIOLATED'
    with pytest.raises(ValueError, match='violated hard constraint'):
        PlanRepository.save(None, execution.input_snapshot, execution.result_snapshot, {}, 'a' * 64)


def test_missing_coverage_is_rejected_even_when_snapshot_does_not_list_missing_inputs():
    execution = eligible_in_memory_only()
    assert execution.input_snapshot.missing_inputs == []
    with pytest.raises(ValueError, match='Missing approved input'):
        PlanRepository.save(None, execution.input_snapshot, execution.result_snapshot, {}, 'a' * 64)


def test_storage_revalidates_typed_result_that_was_mutated():
    execution = example()
    execution.result_snapshot.plans[0].production[0].production_qty = '-1'
    with pytest.raises(ValueError, match='production_qty'):
        PlanRepository.save(None, execution.input_snapshot, execution.result_snapshot, {}, 'a' * 64)


@pytest.mark.parametrize('application_state', ['MISSING_INPUT', 'UNSUPPORTED'])
def test_non_applied_hard_check_cannot_close_feasibility(application_state):
    result = eligible_in_memory_only().result_snapshot.model_dump(mode='json')
    result['constraint_evaluations'][0].update(strength='HARD', status='SATISFIED', application_state=application_state)
    with pytest.raises(ValueError):
        PlanningOutput.model_validate(result)


def test_legacy_snapshot_replay_keeps_the_raw_digest_and_one_month():
    execution = example()
    row = execution.model_dump(mode='json', exclude={'decisions'})
    row['input_snapshot']['command'].pop('horizon_months')
    row['input_snapshot'].pop('scheduled_receipts')
    row['input_digest'] = digest(row['input_snapshot'])
    projections = execution.result_snapshot.model_dump(mode='json')

    class Connection:
        def execute(self, query, parameters):
            sql = str(query)
            if 'FROM plan_execution e' in sql:
                assert "'1'::jsonb" in sql
                return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row))
            if 'FROM plan_decision' in sql:
                data = []
            elif 'FROM plan_execution_input' in sql:
                data = row['input_snapshot']['approved_inputs']['sources']
            else:
                collection = {'plan_candidate': 'plans', 'plan_constraint_evaluation': 'constraint_evaluations',
                              'plan_material_requirement': 'material_requirements'}[sql.split()[3]]
                data = projections[collection]
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: data),
                                   scalars=lambda: SimpleNamespace(all=lambda: data))

    reloaded = PlanRepository.detail(Connection(), execution.execution_id, include_test=True)
    assert reloaded.input_snapshot.command.months == ('2027-01',)
    assert reloaded.input_digest == row['input_digest']
    assert 'horizon_months' not in row['input_snapshot']['command']


def test_review_reject_and_final_state_conflicts():
    e=example();assert transition(e,request(e))=='REVIEW'
    e.decision_status='REVIEW';e.selected_plan_id=e.result_snapshot.plans[0].plan_id;e.version=2
    assert transition(e,request(e,'REJECT'))=='REJECTED'
    e.decision_status='REJECTED'
    with pytest.raises(ApiError):transition(e,request(e))


@pytest.mark.parametrize('problem',['stale','digest','candidate','unauthenticated','infeasible','unverified','no_policy','test_double','no_evidence'])
def test_approval_and_integrity_blockers(problem):
    e=eligible_in_memory_only();e.decision_status='REVIEW';e.selected_plan_id=e.result_snapshot.plans[0].plan_id
    req=request(e,'APPROVE' if problem not in ('stale','digest','candidate') else 'REJECT')
    if problem=='stale':req.expected_version+=1
    if problem=='digest':req.expected_input_digest='sha256:'+'0'*64
    if problem=='candidate':req.plan_id='UNKNOWN'
    if problem=='infeasible':e.result_snapshot.plans[0].feasibility='INFEASIBLE'
    if problem=='unverified':e.result_snapshot.plans[0].feasibility='UNVERIFIED'
    if problem=='no_policy':e.policy_version=None
    if problem=='test_double':e.data_origin='TEST_DOUBLE'
    if problem=='no_evidence':e.result_snapshot.evidence=[]
    ctx=None if problem=='unauthenticated' else ApprovalContext('AUTH-TEST',frozenset({'PLAN_APPROVER'}),True,True)
    with pytest.raises(ApiError):transition(e,req,ctx)


def test_verified_policy_state_machine_only_not_real_auth():
    e=eligible_in_memory_only();e.decision_status='REVIEW';e.selected_plan_id=e.result_snapshot.plans[0].plan_id
    ctx=ApprovalContext('AUTH-TEST',frozenset({'PLAN_APPROVER'}),True,True)
    assert transition(e,request(e,'APPROVE'),ctx)=='APPROVED'


def test_unapproved_formal_export_and_formula_injection():
    e=example();e.result_snapshot.plans[0].label='=HYPERLINK("bad")'
    with pytest.raises(ApiError):formal_export(e)
    content=make_test_export(e);wb=load_workbook(BytesIO(content),data_only=False)
    assert wb.sheetnames==['Overview','Forecast','MPS','RCCP','MRP','Exceptions','Audit']
    assert all('TEST-DOUBLE-ONLY' in ws.cell(1,1).value for ws in wb)
    assert wb['Overview']['F3'].data_type=='s' and wb['Overview']['F3'].value.startswith("'")
    assert not any(c.data_type=='f' for ws in wb for row in ws for c in row)


def test_unimplemented_real_api_and_approval_never_use_fixtures():
    e=example()
    with TestClient(app) as client:
        r=client.post('/plan-executions',json=e.input_snapshot.command.model_dump(mode='json'))
        assert r.status_code==501
        r=client.post('/plan-executions/'+str(e.execution_id)+'/decisions',json=request(e,'APPROVE').model_dump(mode='json'))
        assert r.status_code==501


def test_service_dedup_and_save_rollback_with_explicit_memory_double(monkeypatch):
    from engine import planning
    from app.plans import service
    e=example()
    class Database:
        def __init__(self):self.ids=[];self.fail=False
        @contextmanager
        def begin(self):
            before=list(self.ids)
            try:yield self
            except Exception:self.ids=before;raise
        def execute(self,q,p=None):return SimpleNamespace(scalar_one_or_none=lambda:self.ids[0] if self.ids else None)
    db=Database();svc=PlanService(db)
    class Repo:
        lock_and_find_reusable = staticmethod(PlanRepository.lock_and_find_reusable)
        def detail(self,c,id):return e
        def save(self,c,snapshot,result,identity,key):
            c.ids.append(e.execution_id)
            if c.fail:raise RuntimeError('save failure secret')
            return e
    svc.repo=Repo()
    monkeypatch.setattr(planning,'AVAILABLE',True)
    monkeypatch.setattr(service.adapter,'SqlPlanningSourceProvider',lambda database:SimpleNamespace(load=lambda cmd:e.input_snapshot.model_copy(deep=True)))
    monkeypatch.setattr(planning,'run',lambda snapshot:e.result_snapshot.model_dump(mode='json'))
    assert not svc.create(e.input_snapshot.command).reused
    assert svc.create(e.input_snapshot.command).reused
    def corrupt(*args):
        raise ValueError('private stored execution')
    monkeypatch.setattr(svc.repo, 'detail', corrupt)
    with pytest.raises(ApiError) as error:
        svc.create(e.input_snapshot.command)
    assert error.value.code == ErrorCode.PERSISTENCE_ERROR and 'private' not in error.value.message
    assert db.ids == [e.execution_id]
    db.ids=[];db.fail=True
    with pytest.raises(ApiError) as error:svc.create(e.input_snapshot.command)
    assert db.ids==[] and 'secret' not in error.value.message


def test_preview_and_store_share_canonical_selection_and_output_validation(monkeypatch):
    from engine import planning
    from app.api.plan_executions import get_service
    from app.integrations import planning as adapter

    execution = example()
    source, output = execution.input_snapshot, execution.result_snapshot
    source.approved_inputs.products.append(source.approved_inputs.products[0].model_copy(update={'product_id': 'P2'}))
    source.forecast_rows.append(source.forecast_rows[0].model_copy(update={'product_id': 'P2'}))

    class Provider:
        def __init__(self, *args):
            pass

        def load(self, command):
            return source.model_copy(update={'command': command, 'forecast_rows': [
                row for row in source.forecast_rows if row.product_id in command.product_ids]}, deep=True)

    class MemoryDatabase:
        @contextmanager
        def begin(self):
            yield self

    class MemoryRepository:
        items = {}

        def lock_and_find_reusable(self, _, key):
            return key if key in self.items else None

        def detail(self, _, key):
            return self.items[key]

        def save(self, _, snapshot, result, identity, key):
            self.items[key] = execution.model_copy(update={'input_snapshot': snapshot, 'result_snapshot': result,
                                                            'input_digest': digest(snapshot.model_dump(mode='json'))})
            return self.items[key]

    svc = PlanService(MemoryDatabase())
    svc.repo = MemoryRepository()
    monkeypatch.setattr(adapter, 'get_source_provider', Provider)
    monkeypatch.setattr(adapter, 'SqlPlanningSourceProvider', Provider)
    monkeypatch.setattr(planning, 'AVAILABLE', True)
    monkeypatch.setattr(planning, 'run', lambda _: output.model_dump(mode='json'))
    monkeypatch.setitem(app.dependency_overrides, get_service, lambda: svc)
    command = source.command.model_dump(mode='json')
    with TestClient(app) as client:
        preview = client.post('/plans', json={**command, 'product_ids': ['TP-10R', 'P2']})
        saved = client.post('/plan-executions', json={**command, 'product_ids': ['P2', 'TP-10R']})
        retry = client.post('/plan-executions', json={**command, 'product_ids': ['TP-10R', 'P2']})
        assert (preview.status_code, saved.status_code, retry.status_code) == (200, 201, 200)
        assert saved.json()['reused'] is False and retry.json()['reused'] is True
        assert saved.json()['execution']['input_digest'] == preview.json()['input_digest']
        assert retry.json()['execution'] == saved.json()['execution'] and len(svc.repo.items) == 1

        # Change the selection to avoid hitting the previously saved, reusable result.
        output.constraint_evaluations[0].period = '2027-02'
        for path in ('/plans', '/plan-executions'):
            failure = client.post(path, json=command)
            assert failure.status_code == 500 and failure.json()['detail']['code'] == 'MODULE_ERROR'
        invalid = {**command, 'scenario': 'WHAT_IF', 'base_plan_execution_id': str(execution.execution_id),
                   'overrides': {'production_qty.TP-10R': '100'}}
        for path in ('/plans/what-if', '/plan-executions'):
            failure = client.post(path, json=invalid)
            assert failure.status_code == 422 and failure.json()['detail']['details']['reason'] == 'WHATIF_INVALID'
        assert len(svc.repo.items) == 1
