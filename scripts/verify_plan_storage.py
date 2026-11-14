"""Rollback-only integration checks, using TEST_DOUBLE rows quarantined from real APIs.
No schema reset, no seed changes, no formal approval, no committed plan records.
"""
from pathlib import Path
from contextlib import contextmanager
from uuid import uuid4
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from seed_tissue_capacity import verify_target,ROOT


def main():
    e=verify_target()
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from app.plans.repository import PlanRepository,digest
    from app.plans.service import what_if_snapshot
    from app.plans.exports import formal_export,test_double_export
    from app.integrations.planning import SqlPlanningSourceProvider
    from contracts.interfaces.planning import PlanCommand,PlanningOutput,MaterialRequirement
    from app.errors import ApiError
    checks=[]
    def ok(label):checks.append(label)
    with e.connect() as c:
        assert c.execute(text('SELECT version_num FROM alembic_version')).scalar()=='0007'
        forecast=c.execute(text("SELECT execution_id FROM forecast_run WHERE status IN ('OK','PARTIAL') ORDER BY created_at LIMIT 1")).scalar_one()
        before={t:c.execute(text('SELECT count(*) FROM '+t)).scalar() for t in ('plan_execution','plan_candidate','plan_decision','import_batch')}
    command=PlanCommand(forecast_execution_id=forecast,product_ids=['TP-10R'],target_month='2027-01',as_of_date='2026-12-31')
    snapshot=SqlPlanningSourceProvider(e).load(command)
    result=PlanningOutput.model_validate(json.loads((ROOT/'contracts/examples/integration/planning_output.json').read_text(encoding='utf-8'))['payload'])
    # A nullable, exact-decimal MRP test row, not an engine-calculated requirement.
    result.material_requirements=[MaterialRequirement(plan_id=result.plans[0].plan_id,material_id='TP-ROLL',period='2027-01',
        required_qty='123.000001',available_qty=None,shortage_qty=None,unit='EA',input_refs=['TEST-DOUBLE-ONLY'])]
    with e.connect() as c:
        outer=c.begin()
        try:
            with c.begin_nested():
                first=PlanRepository.save(c,snapshot,result,{'test_double':True},'1'*64,origin='TEST_DOUBLE')
                c.execute(text('SET CONSTRAINTS ALL IMMEDIATE'));c.execute(text('SET CONSTRAINTS ALL DEFERRED'))
            restored=PlanRepository.detail(c,first.execution_id,include_test=True)
            assert restored.input_digest==digest(snapshot.model_dump(mode='json'))
            assert restored.result_snapshot==result
            assert c.execute(text('SELECT required_qty FROM plan_material_requirement WHERE execution_id=:id'),{'id':first.execution_id}).scalar().as_tuple().exponent==-6
            ok('atomic execution/candidate/RCCP/MRP/source snapshot roundtrip; Decimal/null preservation')
            try:PlanRepository.detail(c,first.execution_id)
            except ApiError as exc:assert exc.status==404
            else:raise AssertionError('Test execution visible operationally')
            try:formal_export(first)
            except ApiError:pass
            else:raise AssertionError('Test execution exported formally')
            assert test_double_export(first).startswith(b'PK')
            ok('test double excluded from real detail, formal export and real base lineage')
            new_command=PlanCommand(**{**command.model_dump(),'scenario':'WHAT_IF','base_plan_execution_id':first.execution_id,'overrides':{'production_qty.TP-10R':'100'}})
            child_input=what_if_snapshot(first,new_command,allow_test=True)
            with c.begin_nested():
                child=PlanRepository.save(c,child_input,result,{'test_double':True},'2'*64,origin='TEST_DOUBLE')
                c.execute(text('SET CONSTRAINTS ALL IMMEDIATE'));c.execute(text('SET CONSTRAINTS ALL DEFERRED'))
            assert child.base_plan_execution_id==first.execution_id
            assert PlanRepository.detail(c,first.execution_id,include_test=True).input_snapshot==snapshot
            ok('stored base -> separate What-if child; root snapshot/result unchanged')
            try:
                with c.begin_nested():PlanRepository.save(c,snapshot,result,{'test_double':True},'1'*64,origin='TEST_DOUBLE')
            except IntegrityError:pass
            else:raise AssertionError('duplicate accepted')
            ok('duplicate completed execution unique constraint')
            try:
                with c.begin_nested():
                    c.execute(text('''INSERT INTO plan_execution(execution_id,forecast_execution_id,scenario_type,target_month,as_of_date,status,
                        input_digest,result_digest,dedup_key,input_snapshot,result_snapshot,engine_version,runtime_identity,data_origin)
                        SELECT :new,forecast_execution_id,'INVALID',target_month,as_of_date,status,input_digest,result_digest,:key,
                        input_snapshot,result_snapshot,engine_version,runtime_identity,data_origin FROM plan_execution WHERE execution_id=:id'''),
                        {'new':uuid4(),'key':'9'*64,'id':first.execution_id})
            except IntegrityError as exc:assert exc.orig.sqlstate=='23514'
            else:raise AssertionError('invalid scenario CHECK accepted')
            ok('scenario CHECK constraint 23514')
            for sql in ('UPDATE plan_execution SET input_snapshot=\'{}\' WHERE execution_id=:id',
                        "UPDATE plan_candidate SET label='mutated' WHERE execution_id=:id"):
                try:
                    with c.begin_nested():c.execute(text(sql),{'id':first.execution_id})
                except IntegrityError:pass
                else:raise AssertionError('immutable plan changed')
            ok('execution/result projections immutable')
            def decision(action,before,after,version):
                c.execute(text('''INSERT INTO plan_decision(decision_id,execution_id,plan_id,action,status_before,status_after,review_version,
                    actor_id,auth_verified,reason,input_digest) VALUES(:did,:id,:pid,:action,:before,:after,:v,'TEST-REVIEWER',false,'TEST-DOUBLE-ONLY',:dig)'''),
                    {'did':uuid4(),'id':first.execution_id,'pid':first.result_snapshot.plans[0].plan_id,'action':action,'before':before,'after':after,'v':version,'dig':first.input_digest})
            decision('REVIEW','DRAFT','REVIEW',1)
            try:
                with c.begin_nested():decision('REVIEW','DRAFT','REVIEW',1)
            except IntegrityError:pass
            else:raise AssertionError('stale competing decision accepted')
            try:
                with c.begin_nested():decision('APPROVE','REVIEW','APPROVED',2)
            except IntegrityError:pass
            else:raise AssertionError('unauthenticated/test approval allowed')
            decision('REJECT','REVIEW','REJECTED',2)
            assert PlanRepository.detail(c,first.execution_id,include_test=True).decision_status=='REJECTED'
            try:
                with c.begin_nested():c.execute(text("UPDATE plan_decision SET reason='changed' WHERE execution_id=:id"),{'id':first.execution_id})
            except IntegrityError:pass
            else:raise AssertionError('audit event mutable')
            ok('review/reject state machine, unauthenticated approval denied; event append-only')
            count=c.execute(text('SELECT count(*) FROM plan_execution')).scalar()
            class FailMidSave:
                def execute(self,q,p=None):
                    if str(q).startswith('INSERT INTO plan_constraint_evaluation'):raise RuntimeError('injected mid-save failure')
                    return c.execute(q,p)
            try:
                with c.begin_nested():PlanRepository.save(FailMidSave(),snapshot,result,{},'3'*64,origin='TEST_DOUBLE')
            except RuntimeError:pass
            assert c.execute(text('SELECT count(*) FROM plan_execution')).scalar()==count
            ok('mid-candidate persistence error rolls back entire execution')
            # Different forecast cannot form lineage with a parent execution.
            bad=child_input.model_copy(deep=True);bad.command.forecast_execution_id=uuid4()
            try:
                with c.begin_nested():PlanRepository.save(c,bad,result,{},'4'*64,origin='TEST_DOUBLE')
            except IntegrityError:pass
            else:raise AssertionError('invalid forecast FK accepted')
            ok('forecast/parent/candidate relational foreign keys')
            c.execute(text('SELECT pg_advisory_xact_lock(787007)'))
            with e.connect() as other:assert not other.execute(text('SELECT pg_try_advisory_xact_lock(787007)')).scalar()
            ok('two-connection advisory serialization primitive')
        finally:outer.rollback()
    with e.connect() as c:
        for table,n in before.items():assert c.execute(text('SELECT count(*) FROM '+table)).scalar()==n
    # Real production APIs remain empty and engine gated, without dependency overrides.
    import os
    os.environ['PERSISTENCE']='postgres'
    from app.main import app
    from fastapi.testclient import TestClient
    client=TestClient(app)
    assert client.get('/plan-executions').json()['total']==before['plan_execution']
    assert client.post('/plan-executions',json=command.model_dump(mode='json')).status_code==501
    ok('real API 501 and empty history; test probes fully rolled back')
    print(json.dumps({'passed':len(checks),'failed':0,'checks':checks},indent=2))


if __name__=='__main__':main()
