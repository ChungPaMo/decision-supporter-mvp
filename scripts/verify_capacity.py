"""Explicit, non-destructive development-DB verification. Never uses reset fixtures.
New approval probes run inside an outer transaction that is always rolled back.
The forecast call creates/reuses one SYNTHETIC-demand execution, without changing source data.
"""
from contextlib import contextmanager
from pathlib import Path
import json
import sys
from uuid import UUID

sys.path.insert(0,str(Path(__file__).resolve().parent))
from seed_tissue_capacity import verify_target, ROOT


def main():
    e=verify_target()
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from app.batches.sql_repository import SqlBatchRepository
    from app.batches.service import BatchService
    from app.errors import ApiError
    from app.forecast.runs import ForecastRuns
    from app.forecast.runs_schemas import ForecastRunRequest
    from app.integrations.planning import SqlPlanningSourceProvider, _json
    from contracts.interfaces.planning import PlanCommand
    checks=[]
    def ok(name): checks.append(name)
    # Real forecast persisted through the existing approved-demand service, idempotent dedup.
    reply=ForecastRuns(e).create(ForecastRunRequest(trained_until='2026-12-31',horizon_months=1))
    assert reply.execution.status in ('OK','PARTIAL')
    cmd=PlanCommand(forecast_execution_id=reply.execution.execution_id,product_ids=['TP-10R'],target_month='2027-01',horizon_months=1,as_of_date='2026-12-31')
    a=SqlPlanningSourceProvider(e).load(cmd); b=SqlPlanningSourceProvider(e).load(cmd)
    assert _json(a.model_dump(mode='json'))==_json(b.model_dump(mode='json'))
    assert len(a.capacity_snapshot.resources)==2 and len(a.routing_snapshot.routing_steps)==1
    assert a.routing_snapshot.routing_steps[0].resource_requirements[0].resource_id=='L1'
    assert {s.entity for s in a.approved_inputs.sources}>={'capacity','routing'}
    ok('real saved forecast -> approved capacity/routing snapshot; stable provenance/digest input')
    report={'forecast_execution_id':str(reply.execution.execution_id),'snapshot':a.model_dump(mode='json')}
    artifacts=ROOT/'.artifacts';artifacts.mkdir(exist_ok=True)
    (artifacts/'capacity_snapshot.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    with e.connect() as c:
        outer=c.begin()
        class BoundEngine:
            @contextmanager
            def begin(self):
                with c.begin_nested():
                    yield c
                    c.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
                    c.execute(text('SET CONSTRAINTS ALL DEFERRED'))
        svc=BatchService(SqlBatchRepository(BoundEngine()))
        def upload(entity,data,filename='probe.csv'):
            return svc.create_batch(filename,data,entity=entity,source_type='SYNTHETIC',source_note='rollback-only verification')
        def approve(batch): return svc.approve(batch.batch_id,approved_by='REVIEWER-PROBE',expected_result_digest=batch.result_digest)
        try:
            b=upload('capacity',b'resource_id,resource_name,kind,time_basis,parallel_units\nPROBE-X,Synthetic,EQUIPMENT,MACHINE_HOUR,1\n')
            assert c.execute(text("SELECT count(*) FROM production_resource WHERE resource_id='PROBE-X'")).scalar()==0
            ok('unapproved resources absent from business rows')
            assert approve(b).status=='APPROVED';ok('upload -> validate -> approve with deferred count gate')
            # A second live file with same logical resource races after first approval: revalidation stops it.
            b2=upload('capacity',b'resource_id,resource_name,kind,time_basis,parallel_units\nPROBE-Y,Synthetic,EQUIPMENT,MACHINE_HOUR,1\n')
            b3=upload('capacity',b'resource_id,resource_name,kind,time_basis,parallel_units\nPROBE-Y,OtherName,EQUIPMENT,MACHINE_HOUR,1\n')
            approve(b2)
            try: approve(b3)
            except ApiError as exc: assert exc.status==409
            else: raise AssertionError('stale competing approval accepted')
            assert svc.get_batch(b3.batch_id).status=='READY_FOR_APPROVAL';ok('competing batch result change rejected; original ready status preserved')
            # Force failure after mark_approved inside the same repository transaction.
            b4=upload('capacity',b'resource_id,resource_name,kind,time_basis,parallel_units\nPROBE-Z,Synthetic,EQUIPMENT,MACHINE_HOUR,1\n')
            original=__import__('app.batches.capacity',fromlist=['commit']).commit
            import app.batches.capacity as cap
            def fail(tx,bid,actor,records):
                tx.mark_approved(bid,actor,len(records));raise RuntimeError('injected failure')
            cap.commit=fail
            try:
                try: approve(b4)
                except RuntimeError: pass
            finally: cap.commit=original
            assert svc.get_batch(b4.batch_id).status=='READY_FOR_APPROVAL';ok('post-state-change failure rolls back approval')
            # FK, CHECK and immutable triggers exercised under savepoints; no lasting invalid rows.
            probes=[
                "UPDATE production_resource SET parallel_units=0 WHERE resource_id='M1'",
                "INSERT INTO production_resource(resource_id,resource_name,kind,time_basis,parallel_units,batch_id,payload) VALUES('BAD','bad','EQUIPMENT','MACHINE_HOUR',1,gen_random_uuid(),'{}')",
                "INSERT INTO production_hours_budget(capacity_id,resource_id,period,regular_hours,unit,time_basis,availability_basis,batch_id,payload) SELECT 'BAD','M1','2027-13',-1,'day','MACHINE_HOUR','NET',batch_id,'{}' FROM production_resource LIMIT 1",
            ]
            for sql in probes:
                try:
                    with c.begin_nested(): c.execute(text(sql))
                except IntegrityError: pass
                else: raise AssertionError('invalid write accepted')
            ok('invalid/late writes blocked by DB constraints and append-only gates')
            for values, state in [
                ("'CHECK-PROBE','Synthetic','EQUIPMENT','MACHINE_HOUR',0",'23514'),
            ]:
                try:
                    with c.begin_nested():
                        c.execute(text("UPDATE import_batch SET status='APPROVED',approved_by='REVIEWER-PROBE',approved_record_count=1,version=version+1 WHERE batch_id=:b"),{'b':b4.batch_id})
                        c.execute(text("INSERT INTO production_resource(resource_id,resource_name,kind,time_basis,parallel_units,batch_id,payload) VALUES("+values+",:b,'{}')"),{'b':b4.batch_id})
                except IntegrityError as exc: assert exc.orig.sqlstate==state
                else: raise AssertionError('CHECK was not enforced during approval')
            try:
                with c.begin_nested():
                    c.execute(text("UPDATE import_batch SET status='APPROVED',approved_by='REVIEWER-PROBE',approved_record_count=1,version=version+1 WHERE batch_id=:b"),{'b':b4.batch_id})
                    c.execute(text("INSERT INTO production_hours_budget(capacity_id,resource_id,period,regular_hours,unit,time_basis,availability_basis,batch_id,payload) VALUES('FK-PROBE','UNREGISTERED','2027-02',10,'h','MACHINE_HOUR','NET',:b,'{}')"),{'b':b4.batch_id})
            except IntegrityError as exc: assert exc.orig.sqlstate=='23503'
            else: raise AssertionError('resource FK was not enforced during approval')
            ok('CHECK 23514 and resource FK 23503 enforced inside matching approval transaction')
            # Same advisory key used by approval, tested from two real connections.
            c.execute(text('SELECT pg_advisory_xact_lock(762501)'))
            with e.connect() as other:
                assert other.execute(text('SELECT pg_try_advisory_xact_lock(762501)')).scalar() is False
            ok('concurrent approval advisory lock excludes a second session')
        finally: outer.rollback()
    with e.connect() as c:
        assert c.execute(text("SELECT count(*) FROM production_resource WHERE resource_id LIKE 'PROBE-%'")).scalar()==0
        print('revision',c.execute(text('SELECT version_num FROM alembic_version')).scalar())
        for table in ('production_resource','production_quantity_limit','production_hours_budget','production_routing','production_routing_step','production_routing_resource_requirement'):
            print(table,c.execute(text('SELECT count(*) FROM '+table)).scalar())
    print(json.dumps({'passed':len(checks),'failed':0,'checks':checks},indent=2))


if __name__=='__main__':main()
