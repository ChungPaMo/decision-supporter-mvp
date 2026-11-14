from uuid import UUID
from typing import Annotated
from fastapi import APIRouter,Depends,Query,Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from app.config import get_settings
from app.errors import ApiError,ErrorCode,ErrorResponse,ERROR_RESPONSES
from app.plans.service import PlanService,db_error
from app.plans.exports import formal_export
from app.exports.xlsx import MEDIA_TYPE
from contracts.interfaces.planning import PlanCommand
from contracts.interfaces.plan_execution import (PlanExecutionCreate,PlanExecutionReply,PlanExecutionList,PlanExecutionDetail,
                                                 PlanCandidateDetail,PlanDecisionRequest,PlanDecisionHistory)

router=APIRouter(prefix='/plan-executions',tags=['plan-executions'],responses=ERROR_RESPONSES)


def get_service():
    if get_settings().persistence!='postgres':
        raise ApiError(501,ErrorCode.PERSISTENCE_DISABLED,'Plan persistence is disabled.')
    from app.db import get_engine
    return PlanService(get_engine())


Service=Annotated[PlanService,Depends(get_service)]


def read(call):
    try: return call()
    except DBAPIError as exc: raise db_error(exc) from None
    except ValueError: raise ApiError(500,ErrorCode.PERSISTENCE_ERROR,'Stored plan integrity validation failed.') from None


@router.post('',response_model=PlanExecutionReply,status_code=201,
             responses={200:{'model':PlanExecutionReply},422:{'model':PlanExecutionReply|ErrorResponse},500:{'model':PlanExecutionReply|ErrorResponse}},
             summary='Engine-gated immutable plan execution (currently 501)')
def create(body:PlanExecutionCreate,svc:Service):
    reply=svc.create(PlanCommand.model_validate(body.model_dump()))
    status=200 if reply.reused else 201
    if reply.execution.status=='FAILED':status=422 if reply.execution.result_snapshot.status in ('INPUT_INVALID','UNSUPPORTED') else 500
    return JSONResponse(status_code=status,content=reply.model_dump(mode='json'))


@router.get('',response_model=PlanExecutionList,summary='Real engine execution history; excludes test doubles')
def history(svc:Service,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0)):
    return read(lambda:svc.repo.list(limit,offset))


@router.get('/{execution_id}',response_model=PlanExecutionDetail)
def detail(execution_id:UUID,svc:Service):return read(lambda:svc.repo.get(execution_id))


@router.get('/{execution_id}/candidates',response_model=list[PlanCandidateDetail])
def candidates(execution_id:UUID,svc:Service):return read(lambda:svc.repo.get(execution_id)).result_snapshot.plans


@router.get('/{execution_id}/decisions',response_model=PlanDecisionHistory)
def decisions(execution_id:UUID,svc:Service):return PlanDecisionHistory(items=read(lambda:svc.repo.get(execution_id)).decisions)


@router.post('/{execution_id}/decisions',response_model=PlanExecutionDetail,summary='REVIEW/REJECT audit; APPROVE disabled pending authentication/policy')
def decision(execution_id:UUID,body:PlanDecisionRequest,svc:Service):return read(lambda:svc.decide(execution_id,body))


@router.get('/{execution_id}/export.xlsx',response_class=Response,
            responses={200:{'content':{MEDIA_TYPE:{'schema':{'type':'string','format':'binary'}}}}},
            summary='Approved stored plan only; never exports DEMO input')
def export(execution_id:UUID,svc:Service):
    content=formal_export(read(lambda:svc.repo.get(execution_id)))
    return Response(content=content,media_type=MEDIA_TYPE,headers={'Content-Disposition':f'attachment; filename="MPS_{execution_id}.xlsx"','Cache-Control':'no-store'})
