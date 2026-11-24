"""Typed planning handoff for approved inputs and actual engine outputs."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError
from .base import Code, Month, DecimalValue, StrictModel
from .capacity import CapacityRegistrationDraft
from .dataset import DatasetId,LEGACY_DATASET


class PlanCommand(StrictModel):
    dataset_id: DatasetId = LEGACY_DATASET
    contract_version: Literal['planning-integration-0.1-draft'] = 'planning-integration-0.1-draft'
    forecast_execution_id: UUID
    product_ids: list[Code] = Field(min_length=1)
    target_month: Month
    horizon_months: int = Field(default=3, strict=True, ge=1, le=12,
                                description='Number of consecutive months from target_month.')
    as_of_date: date
    scenario: Literal['BASE', 'WHAT_IF'] = 'BASE'
    base_plan_execution_id: UUID | None = None
    overrides: dict[str, DecimalValue] = Field(default_factory=dict)

    @field_validator('overrides', mode='wrap')
    @classmethod
    def validate_override_values(cls, value, handler):
        try:
            return handler(value)
        except ValidationError:
            raise PydanticCustomError('whatif_invalid', 'WHATIF_INVALID: overrides require non-negative decimal strings') from None

    @model_validator(mode='after')
    def explicit_scenario(self):
        year, month = map(int, self.target_month.split('-'))
        if year * 12 + month + self.horizon_months - 1 > 9999 * 12 + 12:
            raise ValueError('Planning horizon exceeds the supported calendar')
        if len(self.product_ids) != len(set(self.product_ids)): raise ValueError('Duplicate products')
        if self.scenario == 'BASE' and (self.overrides or self.base_plan_execution_id):
            raise ValueError('BASE does not accept what-if overrides')
        if self.scenario == 'WHAT_IF' and self.base_plan_execution_id is None:
            raise ValueError('WHAT_IF requires a saved base plan')
        return self

    @property
    def months(self) -> tuple[str, ...]:
        year, month = map(int, self.target_month.split('-'))
        return tuple(f'{year + offset // 12:04d}-{offset % 12 + 1:02d}'
                     for offset in range(month - 1, month - 1 + self.horizon_months))


class LegacyPlanPreviewCommand(PlanCommand):
    horizon_months: int = Field(default=1, strict=True, ge=1, le=12,
                                description='Legacy preview defaults to one month. Send the desired horizon explicitly.')


class ApprovedSource(StrictModel):
    batch_id: UUID
    batch_version: int = Field(ge=1)
    entity: str
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    result_digest: str | None = Field(pattern=r'^[0-9a-f]{64}$')
    approved_at: datetime


class ProductFact(StrictModel):
    product_id: Code
    product_name: str
    base_unit: Code
    product_type: str | None
    safety_stock_qty: DecimalValue
    source_type: str
    batch_id: UUID


class MaterialFact(StrictModel):
    material_id: Code
    material_name: str
    base_unit: Code
    safety_stock_qty: DecimalValue
    source_type: str
    batch_id: UUID


class BomHeaderFact(StrictModel):
    bom_id: Code
    product_id: Code
    bom_version: Code
    status: str
    is_active: bool
    valid_from: date
    valid_to: date | None
    base_qty: DecimalValue


class BomLineFact(StrictModel):
    bom_id: Code
    line_no: int = Field(ge=1)
    component_type: Literal['PRODUCT', 'MATERIAL']
    component_id: Code
    qty_per: DecimalValue
    unit: Code
    scrap_rate: DecimalValue


class BomFact(StrictModel):
    header: BomHeaderFact
    lines: list[BomLineFact]
    source_type: str
    batch_id: UUID


class InventoryFact(StrictModel):
    item_type: Literal['PRODUCT', 'MATERIAL']
    item_id: Code
    as_of_date: date
    on_hand_qty: DecimalValue
    allocated_qty: DecimalValue
    unit: Code
    source_type: str
    batch_id: UUID


class ApprovedInputs(StrictModel):
    products: list[ProductFact]
    materials: list[MaterialFact]
    boms: list[BomFact]
    inventory: list[InventoryFact]
    sources: list[ApprovedSource]


class ForecastFact(StrictModel):
    product_id: Code
    target_month: Month
    p50: DecimalValue
    p80: DecimalValue
    p90: DecimalValue
    unit: Code

    @model_validator(mode='after')
    def quantile_order(self):
        if not Decimal(self.p50) <= Decimal(self.p80) <= Decimal(self.p90):
            raise ValueError('Forecast quantiles must preserve P50 <= P80 <= P90')
        return self


class ScheduledReceipt(StrictModel):
    po_id: Code
    material_id: Code
    open_qty: DecimalValue
    unit: Code
    expected_date: date
    supplier_id: Code | None = None
    batch_id: UUID = Field(description='Reference to the approved receipt source in approved_inputs.sources.')

    @model_validator(mode='after')
    def positive_open_quantity(self):
        if Decimal(self.open_qty) <= 0:
            raise ValueError('An open receipt must have positive outstanding quantity')
        return self

    def period(self, command: PlanCommand) -> str | None:
        if self.expected_date <= command.as_of_date:
            return command.target_month
        month = self.expected_date.isoformat()[:7]
        return max(month, command.target_month) if month <= command.months[-1] else None


class PlanningInput(StrictModel):
    dataset_id: DatasetId = LEGACY_DATASET
    contract_version: Literal['planning-handoff-0.2-draft'] = 'planning-handoff-0.2-draft'
    command: PlanCommand
    forecast_input_digest: str
    forecast_model_version: str | None = None
    forecast_runtime_identity: dict = Field(default_factory=dict)
    forecast_rows: list[ForecastFact]
    approved_inputs: ApprovedInputs
    scheduled_receipts: list[ScheduledReceipt] | None = Field(
        default=None, description='Null means no approved receipt feed. Empty means a checked feed with no applicable open receipts.')
    capacity_snapshot: CapacityRegistrationDraft | None = None
    routing_snapshot: CapacityRegistrationDraft | None = None
    policy_snapshot: dict[str, str] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list, description=(
        'Unresolved required input codes, distinct from policy advisories. Successful calculations report '
        'these in unverified and cannot claim FEASIBLE while any are present.'))
    base_plan_snapshot: dict | None = None

    @model_validator(mode='after')
    def dataset_scope_matches(self):
        if self.dataset_id!=self.command.dataset_id:
            raise ValueError('PlanningInput and command must identify the same dataset')
        return self


class PlanningInputCoverage(StrictModel):
    ready: bool
    row_count: int = Field(ge=0)


class PlanningInputDiagnostics(StrictModel):
    dataset_id: DatasetId
    forecast_execution_id: UUID
    target_month: Month
    as_of_date: date
    horizon_months: int = Field(ge=1, le=12)
    scope: Literal['SINGLE_MONTH', 'MULTI_MONTH'] = 'SINGLE_MONTH'
    status: Literal['INPUTS_PRESENT', 'NEEDS_REVIEW']
    inputs: dict[Literal['forecast', 'products', 'materials', 'bom', 'inventory',
                         'resources', 'quantity_limits', 'hours_budgets', 'routing', 'scheduled_receipts'], PlanningInputCoverage]
    missing_inputs: list[Code]
    warning_codes: list[Code]
    approved_sources: list[ApprovedSource]
    forecast_input_digest: str
    input_digest: str
    engine_available: bool
    persisted: Literal[False] = False


class PlanningIssue(StrictModel):
    code: Code
    message: str
    input_refs: list[str] = Field(default_factory=list)


class ProductionRow(StrictModel):
    product_id: Code
    period: Month
    production_qty: DecimalValue
    unit: Code


class ConstraintEvaluation(StrictModel):
    constraint_id: Code
    plan_id: Code
    dimension: Literal['QUANTITY', 'WORK_HOURS', 'EQUIPMENT_HOURS', 'MATERIAL', 'SAFETY_STOCK', 'OTHER']
    period: Month
    resource_id: Code | None = None
    product_id: Code | None = None
    step_id: Code | None = None
    status: Literal['SATISFIED', 'VIOLATED', 'UNVERIFIED']
    limit_value: DecimalValue | None
    used_value: DecimalValue | None
    unit: Code | None
    time_basis: Literal['ELAPSED', 'PERSON_HOUR', 'MACHINE_HOUR'] | None = None
    strength: Literal['HARD', 'SOFT'] | None = None
    application_state: Literal['APPLIED', 'MISSING_INPUT', 'UNSUPPORTED'] = 'APPLIED'
    input_refs: list[str]
    reason_codes: list[Code]


class MaterialRequirement(StrictModel):
    plan_id: Code
    material_id: Code
    period: Month
    required_qty: DecimalValue | None = Field(description='Gross requirement for this month.')
    available_qty: DecimalValue | None = Field(description='Opening on-hand stock plus scheduled receipts for this month.')
    shortage_qty: DecimalValue | None = Field(description='New purchasing requirement for this month.')
    unit: Code
    input_refs: list[str]


class PlanCandidate(StrictModel):
    plan_id: Code
    plan_type: Literal['BASELINE', 'STABLE', 'COST_SAVING', 'CUSTOM']
    label: str
    feasibility: Literal['FEASIBLE', 'UNVERIFIED', 'INFEASIBLE']
    production: list[ProductionRow] = Field(min_length=1)
    policy_ref: str | None
    unverified: list[PlanningIssue]

    @model_validator(mode='after')
    def unique_production_rows(self):
        keys = [(r.product_id, r.period) for r in self.production]
        if len(keys) != len(set(keys)): raise ValueError('Duplicate product-period production row')
        return self


class PlanningOutput(StrictModel):
    contract_version: Literal['planning-handoff-0.2-draft'] = 'planning-handoff-0.2-draft'
    status: Literal['OK', 'PARTIAL', 'INPUT_INVALID', 'UNSUPPORTED', 'FAILED']
    plans: list[PlanCandidate]
    constraint_evaluations: list[ConstraintEvaluation]
    material_requirements: list[MaterialRequirement]
    evidence: list[PlanningIssue]
    warnings: list[PlanningIssue]
    unverified: list[PlanningIssue]
    errors: list[PlanningIssue]
    module_version: str = Field(min_length=1, max_length=80)

    @model_validator(mode='after')
    def references_and_cardinality(self):
        ids = [p.plan_id for p in self.plans]
        if len(ids) != len(set(ids)): raise ValueError('Duplicate plan ID')
        if self.status in ('OK', 'PARTIAL') and not 2 <= len(ids) <= 3:
            raise ValueError('Successful draft generation requires 2-3 candidates')
        if self.status in ('INPUT_INVALID', 'UNSUPPORTED', 'FAILED') and self.plans:
            raise ValueError('Failed calculation cannot contain successful candidates')
        if self.status in ('INPUT_INVALID', 'FAILED') and not self.errors:
            raise ValueError('Failure requires errors')
        if any(row.plan_id not in ids for row in [*self.constraint_evaluations, *self.material_requirements]):
            raise ValueError('Evaluation refers to an unknown plan')
        if len({(e.plan_id, e.constraint_id) for e in self.constraint_evaluations}) != len(self.constraint_evaluations):
            raise ValueError('Duplicate constraint evaluation')
        # Do not invent a feasibility aggregation policy; reject only contradictory claims.
        for plan in self.plans:
            checks = [e for e in self.constraint_evaluations if e.plan_id == plan.plan_id]
            if plan.feasibility != 'FEASIBLE':
                continue
            if any(e.strength == 'HARD' and e.status == 'VIOLATED' for e in checks):
                raise ValueError('FEASIBLE contradicts a violated hard constraint')
            if (not checks or not (plan.policy_ref or '').strip() or plan.unverified or self.unverified
                    or any(e.strength != 'SOFT' and (e.status != 'SATISFIED' or e.application_state != 'APPLIED')
                           for e in checks)):
                raise ValueError('FEASIBLE needs policy and completed checks')
        return self


class PlanningReply(StrictModel):
    contract_version: Literal['planning-preview-0.2-draft'] = 'planning-preview-0.2-draft'
    forecast_execution_id: UUID
    input_digest: str
    result: PlanningOutput
    persisted: Literal[False] = False
    approval_available: Literal[False] = False
