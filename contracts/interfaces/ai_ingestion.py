"""Optional AI review results, separate from registration and approval commands."""
from typing import Literal

from pydantic import Field

from .base import StrictModel
from .dataset import DatasetId
from .ingestion import MappingReply
from .xlsx import Column, Row, Sha256, XlsxTableSelection


AI_VERSION = 'ingestion-ai-review-0.1'
ReviewStatus = Literal['DISABLED', 'BLOCKED', 'NOT_NEEDED', 'REVIEW', 'HOLD', 'PARTIAL', 'UNAVAILABLE']


class ProviderUsage(StrictModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    pages: int | None = Field(default=None, ge=0)
    standard_pages: int | None = Field(default=None, ge=0)
    enhanced_pages: int | None = Field(default=None, ge=0)


class ReviewRun(StrictModel):
    request_id: str
    model: str
    snapshot: str | None = None
    elapsed_ms: int = Field(ge=0)
    usage: ProviderUsage
    prompt_version: str | None = None
    prompt_sha256: Sha256 | None = None
    knowledge_version: str | None = None
    knowledge_sha256: Sha256 | None = None


class AIColumnReview(StrictModel):
    source_id: str
    col: Column
    source_column: str
    target_field: str | None = None
    source: Literal['AI_SOLAR', 'EXACT', 'RAPIDFUZZ', 'USER_CONFIRMED', 'LOCAL_PROFILE'] | None = None
    business_concept: str | None = None
    reason: str
    validation: Literal['REVIEWABLE', 'HOLD', 'PRESERVED']
    hold_reason: str | None = None
    conflict: bool = False
    requires_user_confirmation: Literal[True] = True


class AIMappingReply(StrictModel):
    contract_version: Literal['ingestion-ai-review-0.1'] = AI_VERSION
    baseline: MappingReply
    status: ReviewStatus
    issue: str | None = None
    error_request_id: str | None = None
    retry_after_seconds: int | None = Field(default=None, ge=0, le=3600)
    sheet: str | None = None
    strategy: str
    columns: list[AIColumnReview] = Field(default_factory=list, max_length=64)
    run: ReviewRun | None = None
    persisted: Literal[False] = False
    auto_approve: Literal[False] = False


class PagePoint(StrictModel):
    x: float = Field(ge=0, le=1, strict=True, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, strict=True, allow_inf_nan=False)


class DocumentTable(StrictModel):
    element_id: int
    page: int = Field(ge=1, le=100)
    coordinates: list[PagePoint] = Field(max_length=4)
    headers: list[str] = Field(max_length=64)
    row_count: int = Field(ge=1)
    column_count: int = Field(ge=1, le=64)
    range_status: Literal['HOLD', 'USER_RANGE_MATCH'] = 'HOLD'
    reason: str
    source_sheet: str | None = None
    source_header_row: Row | None = None
    source_first_col: Column | None = None


class AIDocumentReply(StrictModel):
    contract_version: Literal['ingestion-ai-review-0.1'] = AI_VERSION
    dataset_id: DatasetId
    source_sha256: Sha256
    status: ReviewStatus
    issue: str | None = None
    error_request_id: str | None = None
    retry_after_seconds: int | None = Field(default=None, ge=0, le=3600)
    mode: Literal['standard', 'enhanced', 'auto']
    table_selection: XlsxTableSelection | None = None
    element_count: int = Field(default=0, ge=0)
    tables: list[DocumentTable] = Field(default_factory=list, max_length=100)
    run: ReviewRun | None = None
    user_selection_required: Literal[True] = True
    persisted: Literal[False] = False
    auto_approve: Literal[False] = False
