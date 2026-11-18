from fastapi import APIRouter, File, Form, UploadFile, Depends
from app.api.datasets import dataset_context
from pydantic import ValidationError
from fastapi.responses import JSONResponse

from app.errors import ERROR_RESPONSES
from app.integrations import modules
from app.integrations import planning as plan_adapter
from app.errors import ApiError, ErrorCode, ErrorResponse
from contracts.interfaces.modules import ClassificationInput, ClassificationOutput, PlanCommand, PlanningReply
from contracts.interfaces.planning import PlanningInputDiagnostics
from app.ingest.parsing import MAX_BYTES, FileError, parse_file

router = APIRouter(tags=['module-integration'], responses=ERROR_RESPONSES)


@router.get('/integrations/modules', summary='실제 연결 상태와 미구현 모듈 확인')
def capabilities():
    import file_classifier
    from engine import planning
    return {'contract_version': 'module-capabilities-0.1', 'forecast': 'IMPLEMENTED',
            'file_classifier': 'IMPLEMENTED' if getattr(file_classifier, 'AVAILABLE', False) else 'NOT_IMPLEMENTED',
            'planning': 'IMPLEMENTED' if planning.AVAILABLE else 'NOT_IMPLEMENTED', 'planning_api': 'READ_ONLY_PREVIEW',
            'capacity_registration': 'IMPLEMENTED',
            'plan_persistence': 'ENGINE_GATED', 'formal_plan_approval': 'DISABLED_AUTH_POLICY'}


@router.post('/classifications', response_model=ClassificationOutput,
             summary='규칙 기반 유형 추천·HOLD (허용한 메타·최대 20개 샘플 행)')
def classify(body: ClassificationInput):
    return modules.classify(body)


@router.post('/classifications/file', response_model=ClassificationOutput,
             summary='원본 파일을 분류 DTO로 변환 (샘플 행은 명시적으로 허용한 만큼만, 저장 없음)')
async def classify_file(file: UploadFile = File(...), sample_row_limit: int = Form(0, ge=0, le=20)):
    try:
        parsed = parse_file(file.filename or '', await file.read(MAX_BYTES + 1))
        descriptor = modules.descriptor(parsed, sample_row_limit)
    except FileError as exc:
        raise ApiError(exc.http_status, ErrorCode(exc.code), exc.message) from None
    except ValidationError:
        raise ApiError(422, ErrorCode.REQUEST_INVALID, '분류 입력 한도(20시트·100열·20행·셀 500자)를 확인하세요.') from None
    return modules.classify(descriptor)


def plan_reply(body):
    factory = plan_adapter.get_source_provider if body.dataset_id=='TISSUE-LEGACY' else lambda:plan_adapter.get_source_provider(body.dataset_id)
    reply = plan_adapter.execute(body, provider_factory=factory)
    status = {'INPUT_INVALID': 422, 'UNSUPPORTED': 422, 'FAILED': 500}.get(reply.result.status, 200)
    return JSONResponse(status_code=status, content=reply.model_dump(mode='json'))


@router.post('/planning-inputs/preview', response_model=PlanningInputDiagnostics,
             summary='Read-only single-month approved input diagnostics, independent of plan calculation')
def preview_planning_inputs(body: PlanCommand, dataset_id: str = Depends(dataset_context)):
    command = scoped_command(body, dataset_id)
    if command.scenario != 'BASE':
        raise ApiError(422, ErrorCode.REQUEST_INVALID, '계획 입력 진단은 BASE 요청만 받습니다.')
    return plan_adapter.preview_inputs(command)


@router.post('/plans', response_model=PlanningReply,
             responses={422: {'model': PlanningReply | ErrorResponse}, 500: {'model': PlanningReply | ErrorResponse}},
             summary='실제 예측 실행 ID를 참조하는 계획 진입점 (현재 501, 저장 없음)')
def create_plan(body: PlanCommand, dataset_id: str = Depends(dataset_context)):
    body = scoped_command(body,dataset_id)
    if body.scenario != 'BASE': raise ApiError(422, ErrorCode.REQUEST_INVALID, 'What-if는 /plans/what-if를 사용하세요.')
    return plan_reply(body)


@router.post('/plans/what-if', response_model=PlanningReply,
             responses={422: {'model': PlanningReply | ErrorResponse}, 500: {'model': PlanningReply | ErrorResponse}},
             summary='저장된 기준 계획의 What-if 진입점 (현재 501)')
def what_if(body: PlanCommand, dataset_id: str = Depends(dataset_context)):
    body = scoped_command(body,dataset_id)
    if body.scenario != 'WHAT_IF': raise ApiError(422, ErrorCode.REQUEST_INVALID, 'WHAT_IF 시나리오와 기준 계획 ID가 필요합니다.')
    return plan_reply(body)


def scoped_command(body,dataset_id):
    if 'dataset_id' in body.model_fields_set and body.dataset_id!=dataset_id:
        raise ApiError(409,ErrorCode.DATASET_MISMATCH,'Query dataset and command dataset disagree.')
    return body.model_copy(update={'dataset_id':dataset_id})
