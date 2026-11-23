from app.errors import ApiError, ErrorCode
from contracts.interfaces.modules import ClassificationInput, ClassificationOutput, RegistrationHint


def descriptor(parsed, sample_row_limit=0):
    """Use identical bounded descriptors for classification and ingestion assistance."""
    return ClassificationInput(filename=parsed.filename, sha256=parsed.sha256, format=parsed.format, sheets=[
        {'name': sheet.name or None, 'columns': [col.display for col in sheet.header],
         'sample_rows': [[cell.value for cell in row.cells] for row in sheet.rows[:sample_row_limit]]}
        for sheet in parsed.sheets])


def registration_route(request: ClassificationInput) -> tuple[RegistrationHint | None, bool]:
    """Identify exact registration templates using the existing capacity DTOs."""
    from app.batches.capacity import MODELS

    sections = set()
    other_sheet = False
    for sheet in request.sheets:
        if not sheet.columns and not sheet.sample_rows:
            # The registration path validates all visible sheets, even blank ones.
            other_sheet = True
            continue
        headers = set(sheet.columns)
        matches = []
        if len(headers) == len(sheet.columns):
            for section, model in MODELS.items():
                fields = model.model_fields
                required = {name for name, field in fields.items() if field.is_required()}
                if required <= headers <= fields.keys():
                    matches.append(section)
        if len(matches) != 1 or (sheet.name in MODELS and sheet.name != matches[0]):
            other_sheet = True
            continue
        sections.add(matches[0])
    if not sections:
        return None, False
    if other_sheet or ('routing_steps' in sections and len(sections) > 1):
        return None, True
    entity = 'routing' if 'routing_steps' in sections else 'capacity'
    return RegistrationHint(entity=entity, sections=sorted(sections)), False


def classify(request: ClassificationInput) -> ClassificationOutput:
    try:
        import file_classifier
    except ImportError:
        file_classifier = None
    if file_classifier is None or not getattr(file_classifier, 'AVAILABLE', False):
        raise ApiError(501, ErrorCode.MODULE_NOT_IMPLEMENTED,
                       '파일 자동 분류는 아직 구현되지 않았습니다. 파일 유형을 직접 선택하세요.') from None
    try:
        result = ClassificationOutput.model_validate(file_classifier.classify(request))
        hint, mixed = registration_route(request)
        if hint or mixed:
            # The existing mapping UI can still use the five standard entities.
            # A separate registration hint never selects a batch entity for it.
            return ClassificationOutput(module_version=result.module_version, recommended_entity=None,
                candidates=result.candidates, hold=True, hold_kind='OTHER_ROUTE' if hint else 'AMBIGUOUS',
                registration_hint=hint, reasons=[*result.reasons,
                    '정확한 양식 헤더를 찾았습니다. 기존 등록 화면에서 유형을 직접 선택해 검증하세요.' if hint else
                    '등록 양식과 다른 시트가 함께 있습니다. 유형별로 파일을 분리해 확인하세요.'])
        return result
    except NotImplementedError:
        raise ApiError(501, ErrorCode.MODULE_NOT_IMPLEMENTED,
                       '파일 자동 분류는 아직 구현되지 않았습니다. 파일 유형을 직접 선택하세요.') from None
    except Exception:
        raise ApiError(500, ErrorCode.MODULE_ERROR, '파일 분류 모듈 실행 또는 출력 검증에 실패했습니다.') from None
