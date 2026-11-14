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
from app.plans.service import validate_pair,what_if_snapshot,PlanService
from app.plans.repository import digest
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


def test_what_if_preserves_original_snapshot_and_results():
    e=example();before=e.model_dump(mode='json')
    cmd=PlanCommand(**{**e.input_snapshot.command.model_dump(),'scenario':'WHAT_IF','base_plan_execution_id':e.execution_id,'overrides':{'production_qty.TP-10R':'100'}})
    child=what_if_snapshot(e,cmd,allow_test=True)
    assert child.command.overrides['production_qty.TP-10R']=='100'
    assert child.base_plan_snapshot['result']==e.result_snapshot.model_dump(mode='json')
    child.forecast_rows[0].p50='0'
    assert e.model_dump(mode='json')==before


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
        def execute(self,q,p=None):return SimpleNamespace(scalar=lambda:self.ids[0] if self.ids else None)
    db=Database();svc=PlanService(db)
    class Repo:
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
    db.ids=[];db.fail=True
    with pytest.raises(ApiError) as error:svc.create(e.input_snapshot.command)
    assert db.ids==[] and 'secret' not in error.value.message
