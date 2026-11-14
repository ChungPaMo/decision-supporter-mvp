from app.errors import ApiError, ErrorCode
from contracts.interfaces.modules import ClassificationInput, ClassificationOutput


def classify(request: ClassificationInput) -> ClassificationOutput:
    from file_classifier import classify as execute
    try:
        return ClassificationOutput.model_validate(execute(request))
    except NotImplementedError:
        raise ApiError(501, ErrorCode.MODULE_NOT_IMPLEMENTED,
                       '파일 자동 분류는 아직 구현되지 않았습니다. 파일 유형을 직접 선택하세요.') from None
    except Exception:
        raise ApiError(500, ErrorCode.MODULE_ERROR, '파일 분류 모듈 실행 또는 출력 검증에 실패했습니다.') from None


def require_planning():
    from engine import planning
    if not planning.AVAILABLE:
        raise ApiError(501, ErrorCode.MODULE_NOT_IMPLEMENTED,
                       'MPS·RCCP·MRP·What-if 계산 및 정식 계획 저장·승인은 아직 구현되지 않았습니다.')
    # Enabling a module alone must not bypass snapshot, persistence or approval integration.
    raise ApiError(501, ErrorCode.MODULE_NOT_IMPLEMENTED,
                   '계획 엔진 구현 후 승인 입력 스냅샷·저장 어댑터의 통합 검증이 필요합니다.')
