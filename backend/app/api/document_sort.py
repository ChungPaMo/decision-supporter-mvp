"""여러 엑셀 파일의 문서 종류(BOM/MPS/MRP/RCCP/CRP/MES/ERP/미분류)를 한 번에 분류한다.

업로드용 테이블 분류(/classifications, /classifications/file)와 별개다. 파일을 저장하지 않고 DB 를 쓰지 않으며,
결과는 추천일 뿐 등록·승인과 무관하다. 분류 알고리즘은 modules/file_classifier(이훤)의 doctype 모듈이다.
"""
from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from app.errors import ERROR_RESPONSES, ApiError, ErrorCode

router = APIRouter(tags=['module-integration'], responses=ERROR_RESPONSES)
MAX_FILES = 50                      # 요청 하나에 담는 파일 수. 화면은 이 크기로 나눠 여러 번 보낸다.
MAX_FILE_BYTES = 10 * 1024 * 1024


class DocumentVerdict(BaseModel):
    file: str
    category: str
    confidence: str
    score: float
    runner_up: str | None
    reason: str
    evidence: list[str]
    readable: bool


class DocumentSortReply(BaseModel):
    module_version: str
    categories: list[str]
    results: list[DocumentVerdict]


@router.post('/classifications/documents', response_model=DocumentSortReply,
             summary='여러 엑셀의 문서 종류 분류 (저장 없음, 사전 기반, 추천 전용)')
async def classify_documents(files: list[UploadFile] = File(...)):
    try:
        from file_classifier import doctype, doctype_io
    except ImportError:
        raise ApiError(501, ErrorCode.MODULE_NOT_IMPLEMENTED, '문서 종류 분류 모듈을 불러올 수 없습니다.') from None
    if len(files) > MAX_FILES:
        raise ApiError(422, ErrorCode.REQUEST_INVALID, f'한 번에 {MAX_FILES}개까지 보낼 수 있습니다. 나눠서 보내 주세요.')
    results = []
    for upload in files:
        name = (upload.filename or '이름 없는 파일').replace('\\', '/').split('/')[-1][:200]
        data = await upload.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            results.append({'file': name, 'category': doctype_io.REVIEW, 'confidence': '낮음', 'score': 0.0, 'runner_up': None,
                            'reason': '파일이 10MB를 넘어 분류하지 않았습니다.', 'evidence': [], 'readable': False})
            continue
        if not name.lower().endswith(('.xlsx', '.xlsm', '.csv')):
            results.append({'file': name, 'category': doctype_io.REVIEW, 'confidence': '낮음', 'score': 0.0, 'runner_up': None,
                            'reason': '엑셀(.xlsx, .xlsm) 또는 CSV 파일만 분류합니다.', 'evidence': [], 'readable': False})
            continue
        results.append(doctype_io.classify_bytes(name, data))
    return {'module_version': doctype.VERSION, 'categories': [*doctype.CATEGORIES, doctype.UNKNOWN, doctype_io.REVIEW], 'results': results}
