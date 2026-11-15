"""파일 유형 분류 모듈 (담당: 이훤). 규칙 기반이며 외부 서비스·DB·원본 파일을 쓰지 않는다."""
from contracts.interfaces.modules import ClassificationInput, ClassificationOutput

from .rules import MODULE_VERSION, classify_sheets

AVAILABLE = True


def classify(request: ClassificationInput) -> ClassificationOutput:
    """추천은 사용자 확인용 제안이다. 승인 단계를 대신하지 않으며, 구분할 수 없으면 보류한다."""
    verdict = classify_sheets([(s.name, s.columns, s.sample_rows) for s in request.sheets])
    return ClassificationOutput(module_version=MODULE_VERSION, **verdict)
