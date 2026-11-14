"""Typed, read-only planning handoff v0.2. Business formulas remain undecided."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from .base import Code, Month, DecimalValue, StrictModel
from .capacity import CapacityRegistrationDraft


class PlanCommand(StrictModel):
    contract_version: Literal['planning-integration-0.1-draft'] = 'planning-integration-0.1-draft'
    forecast_execution_id: UUID
    product_ids: list[Code] = Field(min_length=1)
    target_month: Month
    as_of_date: date
    scenario: Literal['BASE', 'WHAT_IF'] = 'BASE'
    base_plan_execution_id: UUID | None = None
    overrides: dict[str, DecimalValue] = Field(default_factory=dict)

    @model_validator(mode='after')
    def explicit_scenario(self):
        if len(self.product_ids) != len(set(self.product_ids)): raise ValueError('Duplicate products')
        if self.scenario == 'BASE' and (self.overrides or self.base_plan_execution_id):
            raise ValueError('BASE does not accept what-if overrides')
        if self.scenario == 'WHAT_IF' and self.base_plan_execution_id is None:
            raise ValueError('WHAT_IF requires a saved base plan')
        return self


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


class PlanningInput(StrictModel):
    contract_version: Literal['planning-handoff-0.2-draft'] = 'planning-handoff-0.2-draft'
    command: PlanCommand
    forecast_input_digest: str
    forecast_model_version: str | None = None
    forecast_runtime_identity: dict = Field(default_factory=dict)
    forecast_rows: list[ForecastFact]
    approved_inputs: ApprovedInputs
    capacity_snapshot: CapacityRegistrationDraft | None = None
    routing_snapshot: CapacityRegistrationDraft | None = None
    policy_snapshot: dict[str, str] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)
    base_plan_snapshot: dict | None = None


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
    required_qty: DecimalValue | None
    available_qty: DecimalValue | None
    shortage_qty: DecimalValue | None
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
            if plan.feasibility == 'FEASIBLE' and (not checks or plan.policy_ref is None or plan.unverified
                    or any(e.status == 'UNVERIFIED' for e in checks)):
                raise ValueError('FEASIBLE needs policy and completed checks')
        return self


class PlanningReply(StrictModel):
    contract_version: Literal['planning-preview-0.2-draft'] = 'planning-preview-0.2-draft'
    forecast_execution_id: UUID
    input_digest: str
    result: PlanningOutput
    persisted: Literal[False] = False
    approval_available: Literal[False] = False
