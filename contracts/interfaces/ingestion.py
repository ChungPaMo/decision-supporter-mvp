"""Ingestion recommendations/previews. Never approval commands or executable code."""
from typing import Literal
from pydantic import Field, model_validator
from .base import StrictModel
from .dataset import DatasetId
from .modules import ClassificationOutput
from .xlsx import Column, XlsxTableSelection

INGESTION_VERSION = 'ingestion-assistance-0.1'
Entity = Literal['product', 'material', 'monthly_demand', 'bom', 'inventory']


class ValueExample(StrictModel):
    value: str = Field(max_length=48)
    count: int


class ColumnProfile(StrictModel):
    col: int
    column: str
    normalized_column: str
    total_rows: int
    empty_count: int
    empty_ratio: float
    non_null_ratio: float
    distinct_count: int
    distinct_count_is_exact: bool
    example_values: list[ValueExample]
    type_candidates: list[str]
    format_match_rates: dict[str, float]
    known_product_match_ratio: float | None
    known_material_match_ratio: float | None
    date_formats: dict[str, int]
    unit_candidates: list[str]
    anomalies: list[str]
    uncertainty_reasons: list[str]


class ProfileSheet(StrictModel):
    sheet: str
    row_count: int
    columns: list[ColumnProfile]


class ProfileReply(StrictModel):
    contract_version: str = INGESTION_VERSION
    dataset_id: DatasetId
    source_sha256: str
    master_scope: DatasetId | None
    master_digest: str | None
    samples_included: bool
    sheets: list[ProfileSheet]
    table_selection: XlsxTableSelection | None = Field(default=None, exclude_if=lambda value: value is None)
    approval_required: Literal[True] = True
    auto_approve: Literal[False] = False
    persisted: Literal[False] = False


class MappingCandidate(StrictModel):
    target_field: str
    method: str
    evidence: list[str]
    requires_review: Literal[True] = True


class ColumnSuggestion(StrictModel):
    col: int
    source_column: str
    suggestions: list[MappingCandidate] = Field(max_length=3)
    unresolved_reasons: list[str]


class MappingSheetReply(StrictModel):
    sheet: str
    status: Literal['MAPPED', 'HOLD', 'IGNORED']
    existing_mapping: dict[str, int]
    suggestions: list[ColumnSuggestion]
    holds: list[str]


class MappingReply(StrictModel):
    contract_version: str = INGESTION_VERSION
    dataset_id: DatasetId
    entity: Entity
    source_sha256: str
    master_scope: DatasetId | None
    master_digest: str | None
    sheets: list[MappingSheetReply]
    table_selection: XlsxTableSelection | None = Field(default=None, exclude_if=lambda value: value is None)
    saved_rule_storage: Literal['NOT_IMPLEMENTED'] = 'NOT_IMPLEMENTED'
    approval_required: Literal[True] = True
    auto_approve: Literal[False] = False
    persisted: Literal[False] = False


class ClassifiedMappingReply(StrictModel):
    contract_version: str = 'classified-mapping-0.1'
    dataset_id: DatasetId
    source_sha256: str
    classification: ClassificationOutput
    selected_entity: Entity | None
    selection_method: Literal['CLASSIFIER_RECOMMENDATION', 'USER_SELECTION', 'REQUIRED']
    mapping: MappingReply | None
    next_action: Literal['REVIEW_MAPPING', 'SELECT_ENTITY_OR_TRANSFORM']
    transform_preview_url: Literal['/ingest/transform-preview'] = '/ingest/transform-preview'
    approval_required: Literal[True] = True
    auto_approve: Literal[False] = False
    persisted: Literal[False] = False


class SavedMappingRuleDraft(StrictModel):
    """Future storage interface only; not accepted as an applied rule by current APIs."""
    rule_id: str
    version: str
    dataset_id: DatasetId
    entity: Entity
    header_signature: str
    column_overrides: dict[str, str]
    confirmed_by: str


class SalesColumns(StrictModel):
    order_date: str = Field(default='주문일자', min_length=1, max_length=100)
    product_id: str = Field(default='제품코드', min_length=1, max_length=100)
    quantity: str = Field(default='수량', min_length=1, max_length=100)
    unit: str = Field(default='단위', min_length=1, max_length=100)
    status: str = Field(default='구분', min_length=1, max_length=100)
    order_id: str = Field(default='주문번호', min_length=1, max_length=100)
    line_id: str = Field(default='행번호', min_length=1, max_length=100)


class SalesTransformPolicy(StrictModel):
    policy_id: Literal['CHUNGPAMO_SYNTHETIC_SALES'] = 'CHUNGPAMO_SYNTHETIC_SALES'
    version: Literal['1.0'] = '1.0'
    dataset_id: DatasetId
    source_scope: Literal['SYNTHETIC_ONLY'] = 'SYNTHETIC_ONLY'
    columns: SalesColumns = Field(default_factory=SalesColumns)
    date_basis: Literal['ORDER_DATE'] = 'ORDER_DATE'
    date_formats: list[Literal['YYYY-MM-DD', 'YYYY/MM/DD', 'YYYYMMDD']] = Field(
        default_factory=lambda: ['YYYY-MM-DD', 'YYYY/MM/DD', 'YYYYMMDD'], min_length=1, max_length=3)
    included_status: Literal['정상'] = '정상'
    excluded_status: Literal['취소'] = '취소'
    separate_status: Literal['반품'] = '반품'
    return_handling: Literal['SEPARATE_ABSOLUTE_NOT_NETTED'] = 'SEPARATE_ABSOLUTE_NOT_NETTED'
    unit_mapping: dict[str, str] = Field(default_factory=lambda: {'팩': 'EA', 'EA': 'EA'})
    unit_factor: Literal['1'] = '1'
    group_by: Literal['PRODUCT_MONTH'] = 'PRODUCT_MONTH'
    duplicate_policy: Literal['ERROR_TRANSACTION_KEY'] = 'ERROR_TRANSACTION_KEY'
    user_confirmed: bool = Field(default=False, strict=True)

    @model_validator(mode='after')
    def supported_policy(self):
        if self.unit_mapping != {'팩': 'EA', 'EA': 'EA'}:
            raise ValueError('Only the explicitly documented synthetic pack-to-EA rule is supported')
        if len(set(self.columns.model_dump().values())) != len(SalesColumns.model_fields):
            raise ValueError('Each semantic field needs a distinct source column')
        return self


OperationName = Literal['SELECT_COLUMNS', 'RENAME_COLUMNS', 'NORMALIZE_DATE', 'NORMALIZE_UNIT',
                        'FILTER_ROWS', 'GROUP_BY', 'SUM_DECIMAL', 'VALIDATE_REFERENCE']


class TransformOperation(StrictModel):
    operation: OperationName
    parameters: dict


class SourceLocation(StrictModel):
    source_index: int
    sheet: str
    row: int
    col: int | None = None


class TransformIssue(StrictModel):
    code: str
    location: SourceLocation
    field: str | None = None


class TransformSource(StrictModel):
    source_index: int
    filename: str
    sha256: str
    row_count: int
    table_selection: XlsxTableSelection | None = Field(default=None, exclude_if=lambda value: value is None)
    resolved_columns: dict[str, Column] | None = Field(default=None, exclude_if=lambda value: value is None)


class TransformedDemand(StrictModel):
    product_id: str
    period: str
    demand_qty: str
    unit: Literal['EA'] = 'EA'
    source_row_count: int
    source_locations: list[SourceLocation] = Field(max_length=5)


class SeparateReturns(StrictModel):
    product_id: str
    period: str
    return_qty: str
    unit: Literal['EA'] = 'EA'


class TransformReply(StrictModel):
    contract_version: str = INGESTION_VERSION
    dataset_id: DatasetId
    status: Literal['POLICY_REVIEW_REQUIRED', 'HAS_ERRORS', 'TRANSFORMED_PREVIEW']
    policy: SalesTransformPolicy
    policy_digest: str
    input_digest: str
    result_digest: str
    sources: list[TransformSource]
    operations: list[TransformOperation]
    master_scope: DatasetId | None
    master_digest: str | None
    counts: dict[str, int]
    quantity_reconciliation: dict[str, str | bool]
    records: list[TransformedDemand]
    returns: list[SeparateReturns]
    issues: list[TransformIssue] = Field(max_length=100)
    issues_total: int
    warnings: list[str]
    total: int
    offset: int
    limit: int
    returns_total: int
    approval_required: Literal[True] = True
    auto_approve: Literal[False] = False
    persisted: Literal[False] = False
