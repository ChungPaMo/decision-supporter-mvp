"""Explicit staging command. No approval or generated credentials."""
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import ValidationError
from app.api.datasets import dataset_context
from app.api.ingest_assistance import parse_json_object
from app.config import get_settings
from app.datasets import get_dataset_engine
from app.errors import ApiError, ErrorCode, ERROR_RESPONSES
from app.ingest.history import TransformationService
from app.ingest.history_repository import SqlTransformationRepository
from app.ingest.parsing import MAX_BYTES
from app.ingest.transformation import MAX_FILES, MAX_TOTAL_BYTES
from contracts.interfaces.ingestion import SalesTransformPolicy
from contracts.interfaces.ingestion_history import TransformationDetail, TransformationPage

router = APIRouter(prefix='/ingest/transformations', tags=['ingest-history'], responses=ERROR_RESPONSES)


def get_history_service(dataset_id: str = Depends(dataset_context)):
    if get_settings().persistence != 'postgres':
        raise ApiError(501, ErrorCode.PERSISTENCE_DISABLED, 'Transformation persistence is disabled.')
    return TransformationService(SqlTransformationRepository(get_dataset_engine(dataset_id)))


Service = Annotated[TransformationService, Depends(get_history_service)]


@router.post('', response_model=TransformationDetail, status_code=201,
             summary='Explicitly preserve source evidence and create an unapproved monthly-demand batch atomically')
async def create_transformation(svc: Service, response: Response, files: list[UploadFile] = File(...),
        policy: str = Form(...), expected_result_digest: str = Form(..., pattern=r'^[a-f0-9]{64}$'),
        source_note: str = Form(..., min_length=1, max_length=1000), created_by: str = Form(...),
        use_approved_master: bool = Form(False)):
    try:
        recipe = SalesTransformPolicy.model_validate(parse_json_object(policy, 'TRANSFORM_POLICY_INVALID'))
    except ValidationError:
        raise HTTPException(422, {'code': 'TRANSFORM_POLICY_INVALID', 'message': 'Unsupported synthetic transformation policy.'}) from None
    if not 1 <= len(files) <= MAX_FILES:
        raise ApiError(413, ErrorCode.ANALYSIS_LIMIT, 'At most 8 source files.')
    sources, total = [], 0
    for file in files:
        filename = file.filename or ''
        # Preserve exact display filenames and extensions so stored sources can be replayed.
        if len(filename) > 200 or not filename or any(ord(char) < 32 for char in filename) or '/' in filename or '\\' in filename:
            raise ApiError(422, ErrorCode.REQUEST_INVALID, 'Bounded plain source filenames are required.')
        content = await file.read(MAX_BYTES + 1)
        total += len(content)
        if len(content) > MAX_BYTES or total > MAX_TOTAL_BYTES:
            raise ApiError(413, ErrorCode.FILE_TOO_LARGE, '10 MiB per source / 50 MiB combined maximum.')
        sources.append((filename, content))
    result, reused = svc.create(sources, recipe, expected_result_digest, source_note, created_by, use_approved_master)
    if reused:
        response.status_code = 200
    return result


@router.get('', response_model=TransformationPage, summary='Transformation metadata in the selected dataset only')
def list_transformations(svc: Service, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return svc.list(limit, offset)


@router.get('/{transformation_id}', response_model=TransformationDetail,
            summary='Verified transformation evidence and paged results; raw source bytes are never returned')
def get_transformation(transformation_id: UUID, svc: Service, offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=500)):
    return svc.get(transformation_id, offset, limit)
