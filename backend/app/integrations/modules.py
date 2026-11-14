from app.errors import ApiError, ErrorCode
from contracts.interfaces.modules import ClassificationInput, ClassificationOutput


def classify(request: ClassificationInput) -> ClassificationOutput:
    try:
        from file_classifier import classify as execute
        return ClassificationOutput.model_validate(execute(request))
    except (ImportError, NotImplementedError):
        raise ApiError(501, ErrorCode.MODULE_NOT_IMPLEMENTED,
                       '파일 자동 분류는 아직 구현되지 않았습니다. 파일 유형을 직접 선택하세요.') from None
    except Exception:
        raise ApiError(500, ErrorCode.MODULE_ERROR, '파일 분류 모듈 실행 또는 출력 검증에 실패했습니다.') from None
