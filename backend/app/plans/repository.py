"""Atomic SQL repository. Public reads always exclude quarantined test doubles."""
import json
from uuid import uuid4
from sqlalchemy import text
from app.errors import ApiError, ErrorCode
from contracts.interfaces.plan_execution import PlanExecutionDetail, PlanExecutionSummary, PlanExecutionList
from app.integrations.planning import _json


def digest(value):
    import hashlib
    return 'sha256:'+hashlib.sha256(_json(value).encode()).hexdigest()


SUMMARY = '''e.execution_id,e.forecast_execution_id,e.base_plan_execution_id,e.scenario_type,e.target_month,
 e.as_of_date::text,e.status,e.input_digest,e.result_digest,e.engine_version,e.policy_version,e.runtime_identity,
 e.created_at,e.completed_at,e.error_code,e.data_origin,r.status AS decision_status,r.selected_plan_id,r.version'''


class PlanRepository:
    def __init__(self,database): self.database=database

    @staticmethod
    def detail(c,execution_id,*,include_test=False):
        row=c.execute(text(f'SELECT {SUMMARY},e.input_snapshot,e.result_snapshot FROM plan_execution e JOIN plan_review r USING(execution_id) WHERE e.execution_id=:id'+
                            ('' if include_test else " AND e.data_origin='REAL_ENGINE'")),{'id':execution_id}).mappings().first()
        if not row: raise ApiError(404,ErrorCode.PLAN_NOT_FOUND,'Plan execution not found.')
        events=c.execute(text('SELECT decision_id,execution_id,plan_id,action,status_before,status_after,actor_id,auth_verified,reason,input_digest,decided_at,exception_codes FROM plan_decision WHERE execution_id=:id ORDER BY review_version'),{'id':execution_id}).mappings().all()
        result=PlanExecutionDetail.model_validate({**row,'decisions':[dict(e) for e in events]})
        from .service import validate_pair
        validate_pair(result.input_snapshot,result.result_snapshot)
        if digest(result.input_snapshot.model_dump(mode='json'))!=result.input_digest or digest(result.result_snapshot.model_dump(mode='json'))!=result.result_digest:
            raise ValueError('Stored plan digest mismatch')
        from contracts.interfaces.planning import ApprovedSource
        sources=c.execute(text('''SELECT i.batch_id,i.batch_version,b.entity,i.source_sha256,i.result_digest,i.approved_at
            FROM plan_execution_input i JOIN import_batch b USING(batch_id) WHERE i.execution_id=:id'''),{'id':execution_id}).mappings().all()
        if sorted(_json(ApprovedSource.model_validate(r).model_dump(mode='json')) for r in sources)!=sorted(
                _json(r.model_dump(mode='json')) for r in result.input_snapshot.approved_inputs.sources):
            raise ValueError('Stored source provenance mismatch')
        for table,key,expected in (
            ('plan_candidate','plan_id',result.result_snapshot.plans),
            ('plan_constraint_evaluation','constraint_id',result.result_snapshot.constraint_evaluations),
            ('plan_material_requirement','material_id',result.result_snapshot.material_requirements)):
            rows=c.execute(text(f'SELECT payload FROM {table} WHERE execution_id=:id'),{'id':execution_id}).scalars().all()
            if sorted(_json(p) for p in rows)!=sorted(_json(p.model_dump(mode='json')) for p in expected):
                raise ValueError('Stored relational projection mismatch')
        return result

    def get(self,id):
        with self.database.connect().execution_options(isolation_level='REPEATABLE READ') as c:
            return self.detail(c,id)

    def list(self,limit=20,offset=0):
        with self.database.connect().execution_options(isolation_level='REPEATABLE READ') as c:
            total=c.execute(text("SELECT count(*) FROM plan_execution WHERE data_origin='REAL_ENGINE'")).scalar_one()
            rows=c.execute(text(f"SELECT {SUMMARY} FROM plan_execution e JOIN plan_review r USING(execution_id) WHERE e.data_origin='REAL_ENGINE' ORDER BY e.created_at DESC,e.execution_id DESC LIMIT :l OFFSET :o"),{'l':limit,'o':offset}).mappings().all()
            return PlanExecutionList(items=[PlanExecutionSummary.model_validate(r) for r in rows],total=total,limit=limit,offset=offset)

    @staticmethod
    def save(c,snapshot,result,runtime,dedup_key,*,origin='REAL_ENGINE'):
        """Internal transport only, never exposed as an upload-result API."""
        from .service import validate_pair
        from contracts.interfaces.planning import PlanningInput,PlanningOutput
        snapshot=PlanningInput.model_validate(snapshot)
        result=PlanningOutput.model_validate(result)
        validate_pair(snapshot,result)
        id=uuid4();cmd=snapshot.command
        status={'OK':'COMPLETED','PARTIAL':'PARTIAL'}.get(result.status,'FAILED')
        values={'id':id,'forecast':cmd.forecast_execution_id,'base':cmd.base_plan_execution_id,'scenario':cmd.scenario,
                'month':cmd.target_month,'asof':cmd.as_of_date,'status':status,'input':_json(snapshot.model_dump(mode='json')),
                'result':_json(result.model_dump(mode='json')),'dig':digest(snapshot.model_dump(mode='json')),
                'rdig':digest(result.model_dump(mode='json')),'key':dedup_key,'engine':result.module_version,
                'policy':snapshot.policy_snapshot.get('policy_version'),'runtime':_json(runtime),'origin':origin,
                'error':result.errors[0].code if result.errors else None}
        c.execute(text('''INSERT INTO plan_execution(execution_id,forecast_execution_id,base_plan_execution_id,scenario_type,target_month,as_of_date,status,
          input_digest,result_digest,dedup_key,input_snapshot,result_snapshot,engine_version,policy_version,runtime_identity,data_origin,error_code)
          VALUES(:id,:forecast,:base,:scenario,:month,:asof,:status,:dig,:rdig,:key,CAST(:input AS jsonb),CAST(:result AS jsonb),:engine,:policy,CAST(:runtime AS jsonb),:origin,:error)'''),values)
        for p in result.plans:
            d=p.model_dump(mode='json')
            c.execute(text('''INSERT INTO plan_candidate(execution_id,plan_id,plan_type,label,feasibility,production_rows,policy_ref,unverified,payload)
                VALUES(:id,:plan_id,:plan_type,:label,:feasibility,CAST(:production AS jsonb),:policy_ref,CAST(:unverified AS jsonb),CAST(:payload AS jsonb))'''),
                {**d,'id':id,'production':_json(d['production']),'unverified':_json(d['unverified']),'payload':_json(d)})
        for table,rows in [('plan_constraint_evaluation',result.constraint_evaluations),('plan_material_requirement',result.material_requirements)]:
            for row in rows:
                d=row.model_dump(mode='json');keys=list(d)
                columns=['execution_id',*keys,'payload'];casts={'input_refs','reason_codes'}
                params={k:_json(v) if k in casts else v for k,v in d.items()}
                vals=[':execution_id',*[f'CAST(:{k} AS jsonb)' if k in casts else ':'+k for k in keys],'CAST(:payload AS jsonb)']
                c.execute(text(f'INSERT INTO {table}('+','.join(columns)+') VALUES('+','.join(vals)+')'),{**params,'execution_id':id,'payload':_json(d)})
        for s in snapshot.approved_inputs.sources:
            c.execute(text('''INSERT INTO plan_execution_input(execution_id,batch_id,batch_version,source_sha256,result_digest,approved_at)
              VALUES(:id,:batch_id,:batch_version,:source_sha256,:result_digest,:approved_at)'''),{'id':id,**s.model_dump()})
        c.execute(text('INSERT INTO plan_review(execution_id) VALUES(:id)'),{'id':id})
        return PlanRepository.detail(c,id,include_test=origin=='TEST_DOUBLE')
