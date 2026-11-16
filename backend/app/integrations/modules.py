from app.errors import ApiError, ErrorCode
from contracts.interfaces.modules import ClassificationInput, ClassificationOutput


def descriptor(parsed, sample_row_limit=0):
    """Use identical bounded descriptors for classification and ingestion assistance."""
    return ClassificationInput(filename=parsed.filename, sha256=parsed.sha256, format=parsed.format, sheets=[
        {'name': sheet.name or None, 'columns': [col.display for col in sheet.header],
         'sample_rows': [[cell.value for cell in row.cells] for row in sheet.rows[:sample_row_limit]]}
        for sheet in parsed.sheets])


def classify(request: ClassificationInput) -> ClassificationOutput:
    try:
        import file_classifier
    except ImportError:
        file_classifier = None
    if file_classifier is None or not getattr(file_classifier, 'AVAILABLE', False):
        raise ApiError(501, ErrorCode.MODULE_NOT_IMPLEMENTED,
                       '파일 자동 분류는 아직 구현되지 않았습니다. 파일 유형을 직접 선택하세요.') from None
    try:
        return ClassificationOutput.model_validate(file_classifier.classify(request))
    except NotImplementedError:
        raise ApiError(501, ErrorCode.MODULE_NOT_IMPLEMENTED,
                       '파일 자동 분류는 아직 구현되지 않았습니다. 파일 유형을 직접 선택하세요.') from None
    except Exception:
        raise ApiError(500, ErrorCode.MODULE_ERROR, '파일 분류 모듈 실행 또는 출력 검증에 실패했습니다.') from None
