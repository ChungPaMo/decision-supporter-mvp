"""Engine orchestration, immutable lineage, safe failures and review events."""
import hashlib
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError,OperationalError,InterfaceError
from app.errors import ApiError,ErrorCode
from app.integrations import planning as adapter
from app.integrations.planning_validation import validate_overrides
from contracts.interfaces.planning import PlanningInput
from contracts.interfaces.plan_execution import PlanExecutionReply
from .repository import PlanRepository,digest
from .approval import transition


def db_error(exc):
    if isinstance(exc,(OperationalError,InterfaceError)):
        return ApiError(503,ErrorCode.DB_UNAVAILABLE,'Plan database is unavailable.')
    return ApiError(500,ErrorCode.PERSISTENCE_ERROR,'Plan transaction failed; no partial execution was saved.')


def what_if_snapshot(base,command,*,allow_test=False):
    if base.data_origin!='REAL_ENGINE' and not allow_test:
        raise ApiError(404,ErrorCode.PLAN_NOT_FOUND,'Test doubles are not operational base plans.')
    original=base.input_snapshot.command
    if command.dataset_id!=base.dataset_id or command.dataset_id!=base.input_snapshot.dataset_id:
        raise ApiError(409,ErrorCode.DATASET_MISMATCH,'What-if parent and child must belong to the same dataset.')
    if (base.status not in ('COMPLETED','PARTIAL') or command.base_plan_execution_id!=base.execution_id or
        command.forecast_execution_id!=base.forecast_execution_id or command.target_month!=original.target_month or
        command.horizon_months!=original.horizon_months or command.as_of_date!=original.as_of_date or
        set(command.product_ids)!=set(original.product_ids)):
        raise ApiError(409,ErrorCode.PLAN_INPUT_UNAVAILABLE,'What-if must preserve the saved forecast, products, horizon and as-of scope.')
    validate_overrides(command, base.input_snapshot)
    data=base.input_snapshot.model_dump(mode='json')
    data['command']=command.model_dump(mode='json')
    data['base_plan_snapshot']={'execution_id':str(base.execution_id),'forecast_execution_id':str(base.forecast_execution_id),
        'input_digest':base.input_digest,'result_digest':base.result_digest,'result':base.result_snapshot.model_dump(mode='json')}
    # Overrides are scenario requests, NOT edits to approved source facts. Engine interprets confirmed policy.
    return PlanningInput.model_validate(data)


def load_what_if(database,command):
    try:
        parent = PlanRepository(database).get(command.base_plan_execution_id)
    except DBAPIError as exc:
        raise db_error(exc) from None
    except ValueError:
        raise ApiError(500, ErrorCode.PERSISTENCE_ERROR, 'Stored parent plan integrity validation failed.') from None
    return what_if_snapshot(parent, command)


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
        if command.dataset_id!=getattr(self.database,'dataset_id','TISSUE-LEGACY'):
            raise ApiError(409,ErrorCode.DATASET_MISMATCH,'Plan request and selected dataset do not match.')
        validate_overrides(command)
        from engine import planning
        if not planning.AVAILABLE:
            raise ApiError(501,ErrorCode.MODULE_NOT_IMPLEMENTED,'Planning algorithm is not implemented; no execution was fabricated.')
        try:
            snapshot=adapter.SqlPlanningSourceProvider(self.database).load(command)
            identity=runtime_identity()
            key=digest({'input':snapshot.model_dump(mode='json'),'runtime':identity})[7:]
            with self.database.begin() as c:
                existing = self.repo.lock_and_find_reusable(c, key)
                if existing:
                    try:
                        detail = self.repo.detail(c, existing)
                    except ValueError:
                        raise ApiError(500, ErrorCode.PERSISTENCE_ERROR, 'Stored plan integrity validation failed.') from None
                    return PlanExecutionReply(execution=detail, reused=True)
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
