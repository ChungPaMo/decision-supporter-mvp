"""Read-only ingestion assistance; approval remains exclusively in /batches."""
import json
from typing import Annotated
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import ValidationError

from app.api.datasets import dataset_context
from app.api.batches import get_service
from app.ingest.parsing import MAX_BYTES, FileError
from app.ingest.profiling import ScopedMaster, parse_analysis_file, profile
from app.ingest.recommendation import recommend
from app.ingest.transformation import MAX_FILES, MAX_TOTAL_BYTES, transform
from app.ingest.validation import MasterData
from app.errors import ERROR_RESPONSES
from contracts.interfaces.ingestion import ClassifiedMappingReply, Entity, MappingReply, ProfileReply, SalesTransformPolicy, TransformReply

router = APIRouter(prefix='/ingest', tags=['ingest-assistance'], responses=ERROR_RESPONSES)


def load_master(dataset_id: str = Depends(dataset_context), use_approved_master: bool = Form(False)) -> ScopedMaster | None:
    if not use_approved_master:
        return None
    service = get_service(dataset_id)
    with service._tx() as tx:
        return ScopedMaster(dataset_id, MasterData(
            {product.product_id: product for product in tx.list_known_products()},
            {material.material_id: material for material in tx.list_known_materials()}))


Master = Annotated[ScopedMaster | None, Depends(load_master)]
Dataset = Annotated[str, Depends(dataset_context)]


def file_error(exc):
    return HTTPException(exc.http_status, {'code': exc.code, 'message': exc.message})


def parse_json_object(value, code):
    if len(value.encode('utf-8')) > 16_384:
        raise HTTPException(413, {'code': 'ANALYSIS_LIMIT', 'message': 'JSON settings exceed 16 KiB.'})
    try:
        def unique_keys(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError('Duplicate JSON key')
                result[key] = item
            return result
        parsed = json.loads(value, object_pairs_hook=unique_keys)
        if not isinstance(parsed, dict):
            raise ValueError
        return parsed
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(422, {'code': code, 'message': 'A JSON object is required.'}) from None


@router.post('/profile', response_model=ProfileReply, summary='Bounded column profile; no persistence or approval')
async def profile_file(dataset_id: Dataset, master: Master, file: UploadFile = File(...), include_samples: bool = Form(False)):
    data = await file.read(MAX_BYTES + 1)
    try:
        return profile(parse_analysis_file(file.filename or '', data), dataset_id, master, include_samples=include_samples)
    except FileError as exc:
        raise file_error(exc) from None


@router.post('/mapping-suggestions', response_model=MappingReply, summary='Reviewable top-3 mapping candidates; never auto-applied')
async def mapping_suggestions(dataset_id: Dataset, master: Master, file: UploadFile = File(...),
                              entity: Entity = Form('monthly_demand'), column_overrides: str = Form('{}')):
    overrides = parse_json_object(column_overrides, 'BAD_COLUMN_OVERRIDES')
    if not all(isinstance(key, str) and isinstance(value, str) and len(value) <= 200 for key, value in overrides.items()):
        raise HTTPException(422, {'code': 'BAD_COLUMN_OVERRIDES', 'message': 'Mapping values must be bounded column names/letters.'})
    data = await file.read(MAX_BYTES + 1)
    try:
        return recommend(parse_analysis_file(file.filename or '', data), entity, dataset_id, master, overrides)
    except FileError as exc:
        raise file_error(exc) from None


@router.post('/transform-preview', response_model=TransformReply, summary='Synthetic sales policy preview; no batch creation or approval')
async def transform_preview(dataset_id: Dataset, master: Master, policy: str = Form(...), files: list[UploadFile] = File(...),
                            offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=500)):
    body = parse_json_object(policy, 'TRANSFORM_POLICY_INVALID')
    try:
        recipe = SalesTransformPolicy.model_validate(body)
    except ValidationError:
        raise HTTPException(422, {'code': 'TRANSFORM_POLICY_INVALID', 'message': 'Unsupported or invalid synthetic transformation policy.'}) from None
    if recipe.dataset_id != dataset_id:
        raise HTTPException(409, {'code': 'DATASET_MISMATCH', 'message': 'Policy and selected dataset must agree.'})
    if len(files) > MAX_FILES:
        raise HTTPException(413, {'code': 'ANALYSIS_LIMIT', 'message': 'At most 8 source files.'})
    data, total = [], 0
    for file in files:
        content = await file.read(MAX_BYTES + 1)
        total += len(content)
        if len(content) > MAX_BYTES or total > MAX_TOTAL_BYTES:
            raise HTTPException(413, {'code': 'FILE_TOO_LARGE', 'message': '10 MiB per file / 50 MiB combined maximum.'})
        data.append((file.filename or '', content))
    try:
        return transform(data, recipe, master, offset=offset, limit=limit)
    except FileError as exc:
        raise file_error(exc) from None


@router.post('/classified-mapping', response_model=ClassifiedMappingReply,
             summary='Classify then suggest columns; HOLD requires explicit entity selection or sales transformation')
async def classified_mapping(dataset_id: Dataset, master: Master, file: UploadFile = File(...),
                             entity: Entity | None = Form(None), column_overrides: str = Form('{}'),
                             sample_row_limit: int = Form(0, ge=0, le=20)):
    from app.integrations import modules
    overrides = parse_json_object(column_overrides, 'BAD_COLUMN_OVERRIDES')
    if not all(isinstance(value, str) and len(value) <= 200 for value in overrides.values()):
        raise HTTPException(422, {'code': 'BAD_COLUMN_OVERRIDES', 'message': 'Bounded column references required.'})
    try:
        parsed = parse_analysis_file(file.filename or '', await file.read(MAX_BYTES + 1))
        try:
            classification = modules.classify(modules.descriptor(parsed, sample_row_limit))
        except ValidationError:
            raise HTTPException(422, {'code': 'REQUEST_INVALID', 'message': 'Classification descriptor exceeds bounded limits.'}) from None
        selected = entity or (classification.recommended_entity if not classification.hold else None)
        if selected is None and overrides:
            raise HTTPException(422, {'code': 'BAD_COLUMN_OVERRIDES', 'message': 'Choose an entity before specifying columns.'})
        mapping = recommend(parsed, selected, dataset_id, master, overrides) if selected else None
        return ClassifiedMappingReply(dataset_id=dataset_id, source_sha256=parsed.sha256, classification=classification,
            selected_entity=selected, selection_method='USER_SELECTION' if entity else 'CLASSIFIER_RECOMMENDATION' if selected else 'REQUIRED',
            mapping=mapping, next_action='REVIEW_MAPPING' if selected else 'SELECT_ENTITY_OR_TRANSFORM')
    except FileError as exc:
        raise file_error(exc) from None
