"""Opt-in AI review endpoints; supplied files are never persisted."""
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.ingest_assistance import Dataset, file_error, parse_json_object, parse_table_selection
from app.config import Settings, get_settings
from app.errors import ERROR_RESPONSES
from app.ingest.ai_documents import parse_document
from app.ingest.ai_mapping import mapping_review
from app.ingest.parsing import MAX_BYTES, FileError
from app.ingest.profiling import parse_analysis_file
from app.ingest.recommendation import recommend
from app.integrations.upstage import ApprovedSource, MIME, UpstageClient
from contracts.interfaces.ai_ingestion import AIDocumentReply, AIMappingReply
from contracts.interfaces.ingestion import Entity


router = APIRouter(prefix='/ingest', tags=['ingest-ai-review'], responses=ERROR_RESPONSES)
Config = Annotated[Settings, Depends(get_settings)]


def get_upstage_client(request: Request, settings: Config) -> UpstageClient:
    return UpstageClient(settings, getattr(request.app.state, 'upstage_cost_tracker', None))


Provider = Annotated[UpstageClient, Depends(get_upstage_client)]


async def require_unambiguous_opt_in(request):
    if len((await request.form()).getlist('external_review')) > 1:
        raise HTTPException(422, {'code': 'REQUEST_INVALID', 'message': 'Provide a single external_review value.'})


def review_mapping_file(settings, provider, dataset_id, filename, content, selection, entity, overrides, requested):
    parsed = parse_analysis_file(filename, content, selection)
    baseline = recommend(parsed, entity, dataset_id, overrides=overrides)
    return mapping_review(settings, provider, parsed, baseline, requested=requested, overrides=overrides)


@router.post('/ai-mapping-review', response_model=AIMappingReply, summary='Optional column review alongside local mapping')
async def ai_mapping_review(request: Request, dataset_id: Dataset, settings: Config, provider: Provider,
                            file: UploadFile = File(...), entity: Entity = Form(...), external_review: bool = Form(False),
                            column_overrides: str = Form('{}'),
                            table_selection: str | None = Form(None, description='JSON XlsxTableSelection')):
    await require_unambiguous_opt_in(request)
    overrides = parse_json_object(column_overrides, 'BAD_COLUMN_OVERRIDES')
    if not all(isinstance(value, str) and len(value) <= 200 for value in overrides.values()):
        raise HTTPException(422, {'code': 'BAD_COLUMN_OVERRIDES', 'message': 'Bounded column references required.'})
    selection = await parse_table_selection(request, table_selection)
    try:
        return await run_in_threadpool(review_mapping_file, settings, provider, dataset_id, file.filename or '',
            await file.read(MAX_BYTES + 1), selection, entity, overrides, external_review)
    except FileError as exc:
        raise file_error(exc) from None


@router.post('/ai-document-analysis', response_model=AIDocumentReply, summary='Optional document layout review')
async def ai_document_analysis(request: Request, dataset_id: Dataset, settings: Config, provider: Provider,
                               file: UploadFile = File(...), external_review: bool = Form(False),
                               table_selection: str | None = Form(None, description='JSON XlsxTableSelection')):
    await require_unambiguous_opt_in(request)
    selection = await parse_table_selection(request, table_selection)
    name = file.filename or ''
    kind = PurePosixPath(name.replace('\\', '/')).suffix.lower().lstrip('.')
    kind = 'jpg' if kind == 'jpeg' else kind
    if kind not in MIME:
        raise HTTPException(415, {'code': 'UNSUPPORTED_DOCUMENT', 'message': 'Use XLSX, PDF, PNG or JPEG.'})
    limit = settings.upstage_document_max_input_bytes
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, {'code': 'UPSTAGE_INPUT_LIMIT', 'message': 'Document exceeds the configured byte limit.'})
    try:
        if selection:
            await run_in_threadpool(parse_analysis_file, name, content, selection)
        source = ApprovedSource(dataset_id, sha256(content).hexdigest())
        return await run_in_threadpool(parse_document, settings, provider, source, content, kind, selection,
                                       requested=external_review)
    except FileError as exc:
        raise file_error(exc) from None
