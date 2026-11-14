from fastapi import APIRouter

from app.errors import ERROR_RESPONSES
from app.integrations import modules
from contracts.interfaces.modules import ClassificationInput, ClassificationOutput, PlanCommand, PlanningOutput

router = APIRouter(tags=['module-integration'], responses=ERROR_RESPONSES)


@router.get('/integrations/modules', summary='실제 연결 상태와 미구현 모듈 확인')
def capabilities():
    return {'contract_version': 'module-capabilities-0.1', 'forecast': 'IMPLEMENTED',
            'file_classifier': 'NOT_IMPLEMENTED', 'planning': 'NOT_IMPLEMENTED',
            'plan_persistence': 'NOT_IMPLEMENTED', 'formal_plan_approval': 'NOT_IMPLEMENTED'}


@router.post('/classifications', response_model=ClassificationOutput,
             summary='허용한 파일 메타·최대 20개 샘플 행 분류 (현재 501)')
def classify(body: ClassificationInput):
    return modules.classify(body)


@router.post('/plans', response_model=PlanningOutput,
             summary='실제 예측 실행 ID를 참조하는 계획 진입점 (현재 501, 저장 없음)')
def create_plan(body: PlanCommand):
    modules.require_planning()


@router.post('/plans/what-if', response_model=PlanningOutput,
             summary='저장된 기준 계획의 What-if 진입점 (현재 501)')
def what_if(body: PlanCommand):
    modules.require_planning()
