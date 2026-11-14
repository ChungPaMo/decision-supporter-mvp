"""Engine orchestration, immutable lineage, safe failures and review events."""
import hashlib
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError,OperationalError,InterfaceError
from app.errors import ApiError,ErrorCode
from app.integrations import planning as adapter
from contracts.interfaces.planning import PlanningInput,PlanningOutput,PlanCommand
from contracts.interfaces.plan_execution import PlanExecutionReply
from .repository import PlanRepository,digest
from .approval import transition


def db_error(exc):
    if isinstance(exc,(OperationalError,InterfaceError)):
        return ApiError(503,ErrorCode.DB_UNAVAILABLE,'Plan database is unavailable.')
    return ApiError(500,ErrorCode.PERSISTENCE_ERROR,'Plan transaction failed; no partial execution was saved.')


def validate_pair(snapshot,result):
    # Reuse exactly the preview boundary checks, without running a calculation.
    command=snapshot.command
    units={r.product_id:r.unit for r in snapshot.forecast_rows}
    if set(command.product_ids)!=set(units) or any(r.target_month!=command.target_month for r in snapshot.forecast_rows):
        raise ValueError('Missing forecast input scope')
    if len(units)!=len(snapshot.forecast_rows): raise ValueError('Duplicate forecast input')
    ids=[s.batch_id for s in snapshot.approved_inputs.sources]
    if len(ids)!=len(set(ids)): raise ValueError('Duplicate input source')
    for p in result.plans:
        if any(r.product_id not in command.product_ids or r.period!=command.target_month or r.unit!=units[r.product_id] for r in p.production):
            raise ValueError('Output scope or unit mismatch')
        if result.status=='OK' and {r.product_id for r in p.production}!=set(command.product_ids): raise ValueError('Incomplete OK candidate')
        if snapshot.missing_inputs and p.feasibility=='FEASIBLE': raise ValueError('Missing input cannot be verified')
    resources={r.resource_id for d in (snapshot.capacity_snapshot,snapshot.routing_snapshot) if d for r in d.resources}
    materials={m.material_id:m.base_unit for m in snapshot.approved_inputs.materials}
    keys=set()
    for r in result.constraint_evaluations:
        if r.period!=command.target_month or (r.product_id and r.product_id not in command.product_ids) or (r.resource_id and r.resource_id not in resources):
            raise ValueError('Constraint reference outside input')
    for r in result.material_requirements:
        k=(r.plan_id,r.material_id,r.period)
        if k in keys or r.material_id not in materials or r.unit!=materials[r.material_id] or r.period!=command.target_month:
            raise ValueError('Material reference or unit mismatch')
        keys.add(k)


def what_if_snapshot(base,command,*,allow_test=False):
    if base.data_origin!='REAL_ENGINE' and not allow_test:
        raise ApiError(404,ErrorCode.PLAN_NOT_FOUND,'Test doubles are not operational base plans.')
    original=base.input_snapshot.command
    if (base.status not in ('COMPLETED','PARTIAL') or command.base_plan_execution_id!=base.execution_id or
        command.forecast_execution_id!=base.forecast_execution_id or command.target_month!=original.target_month or
        command.as_of_date!=original.as_of_date or set(command.product_ids)!=set(original.product_ids)):
        raise ApiError(409,ErrorCode.PLAN_INPUT_UNAVAILABLE,'What-if must preserve the saved forecast, products, month and as-of scope.')
    hours=base.input_snapshot.capacity_snapshot.hours_budgets if base.input_snapshot.capacity_snapshot else []
    allowed={f'production_qty.{p}' for p in command.product_ids}|{f'overtime_hours_limit.{h.capacity_id}' for h in hours}
    if set(command.overrides)-allowed:
        raise ApiError(422,ErrorCode.PLAN_OVERRIDE_UNSUPPORTED,'Only scoped production_qty.<product> and overtime_hours_limit.<capacity> requests are supported.')
    data=base.input_snapshot.model_dump(mode='json')
    data['command']=command.model_dump(mode='json')
    data['base_plan_snapshot']={'execution_id':str(base.execution_id),'forecast_execution_id':str(base.forecast_execution_id),
        'input_digest':base.input_digest,'result_digest':base.result_digest,'result':base.result_snapshot.model_dump(mode='json')}
    if command.overrides:
        data['missing_inputs']=sorted(set([*data['missing_inputs'],'WHAT_IF_OVERRIDE_POLICY_UNCONFIRMED']))
    # Overrides are scenario requests, NOT edits to approved source facts. Engine interprets confirmed policy.
    return PlanningInput.model_validate(data)


def load_what_if(database,command):
    try: return what_if_snapshot(PlanRepository(database).get(command.base_plan_execution_id),command)
    except DBAPIError as exc: raise db_error(exc) from None


def runtime_identity():
    import engine
    from engine import planning
    folder=Path(engine.__file__).parent.parent
    return {'engine_version':engine.__version__,'planning_source_sha256':{
        p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob('*.py')) if 'tests' not in p.parts and '__pycache__' not in p.parts}}


class PlanService:
    def __init__(self,database): self.database=database;self.repo=PlanRepository(database)

    def create(self,command):
        from engine import planning
        if not planning.AVAILABLE:
            raise ApiError(501,ErrorCode.MODULE_NOT_IMPLEMENTED,'Planning algorithm is not implemented; no execution was fabricated.')
        try:
            snapshot=adapter.SqlPlanningSourceProvider(self.database).load(command)
            identity=runtime_identity()
            key=digest({'input':snapshot.model_dump(mode='json'),'runtime':identity})[7:]
            with self.database.begin() as c:
                c.execute(text('SELECT pg_advisory_xact_lock(:k)'),{'k':int(key[:15],16)})
                existing=c.execute(text("SELECT execution_id FROM plan_execution WHERE dedup_key=:k AND data_origin='REAL_ENGINE' AND status<>'FAILED'"),{'k':key}).scalar()
                if existing: return PlanExecutionReply(execution=self.repo.detail(c,existing),reused=True)
                result=adapter.run_snapshot(command,snapshot).result
                detail=self.repo.save(c,snapshot,result,identity,key)
            return PlanExecutionReply(execution=detail,reused=False)
        except ApiError: raise
        except DBAPIError as exc: raise db_error(exc) from None
        except Exception: raise ApiError(500,ErrorCode.MODULE_ERROR,'Plan result or stored snapshot validation failed.') from None

    def decide(self,id,request):
        # No public client-supplied context/role can enable formal approval.
        if request.action=='APPROVE':
            raise ApiError(501,ErrorCode.PLAN_APPROVAL_DISABLED,'Authentication, approver roles and final policy are not integrated.')
        try:
            with self.database.begin() as c:
                c.execute(text('SELECT execution_id FROM plan_review WHERE execution_id=:id FOR UPDATE'),{'id':id})
                execution=self.repo.detail(c,id)
                target=transition(execution,request)
                c.execute(text('''INSERT INTO plan_decision(decision_id,execution_id,plan_id,action,status_before,status_after,review_version,actor_id,
                  auth_verified,reason,input_digest) VALUES(:decision,:id,:plan,:action,:before,:after,:version,:actor,false,:reason,:digest)'''),
                  {'decision':uuid4(),'id':id,'plan':request.plan_id,'action':request.action,'before':execution.decision_status,'after':target,
                   'version':request.expected_version,'actor':request.actor_id,'reason':request.reason,'digest':request.expected_input_digest})
                return self.repo.detail(c,id)
        except DBAPIError as exc: raise db_error(exc) from None
