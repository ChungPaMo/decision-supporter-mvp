"""Draft handoff contracts. They do not define planning formulas or approval policy."""
from datetime import date
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Entity = Literal['product', 'material', 'bom', 'inventory', 'monthly_demand']
Code = Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$')]
DecimalValue = Annotated[str, Field(pattern=r'^[0-9]{1,14}(\.[0-9]{1,6})?$')]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SheetSample(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    columns: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=100)]
    sample_rows: Annotated[list[list[Annotated[str | None, Field(max_length=500)]]], Field(max_length=20)] = []

    @model_validator(mode='after')
    def bounded_width(self):
        if any(len(row) > len(self.columns) for row in self.sample_rows):
            raise ValueError('Sample row width exceeds the supplied columns')
        return self


class ClassificationInput(StrictModel):
    contract_version: Literal['classification-0.1-draft'] = 'classification-0.1-draft'
    filename: Annotated[str, Field(min_length=1, max_length=200, pattern=r'^[^/\\]+$')]
    sha256: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    sheets: Annotated[list[SheetSample], Field(min_length=1, max_length=20)]


class ClassificationCandidate(StrictModel):
    entity: Entity
    score: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    reasons: list[str]


class ClassificationOutput(StrictModel):
    contract_version: Literal['classification-0.1-draft'] = 'classification-0.1-draft'
    recommended_entity: Entity | None
    candidates: list[ClassificationCandidate]
    hold: bool
    reasons: list[str]
    module_version: str

    @model_validator(mode='after')
    def recommendation_is_candidate(self):
        entities = [c.entity for c in self.candidates]
        if len(entities) != len(set(entities)) or (self.recommended_entity and self.recommended_entity not in entities):
            raise ValueError('Recommendation must reference a unique candidate')
        if self.recommended_entity is None and not self.hold:
            raise ValueError('Missing recommendation requires HOLD')
        return self


class PlanCommand(StrictModel):
    contract_version: Literal['planning-integration-0.1-draft'] = 'planning-integration-0.1-draft'
    forecast_execution_id: UUID
    product_ids: Annotated[list[Code], Field(min_length=1)]
    target_month: Annotated[str, Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')]
    as_of_date: date
    scenario: Literal['BASE', 'WHAT_IF'] = 'BASE'
    base_plan_execution_id: UUID | None = None
    overrides: dict[str, DecimalValue] = Field(default_factory=dict)

    @model_validator(mode='after')
    def explicit_scenario(self):
        if len(self.product_ids) != len(set(self.product_ids)):
            raise ValueError('Duplicate products')
        if self.scenario == 'BASE' and (self.overrides or self.base_plan_execution_id):
            raise ValueError('BASE does not accept what-if overrides')
        if self.scenario == 'WHAT_IF' and self.base_plan_execution_id is None:
            raise ValueError('WHAT_IF requires a saved base plan')
        return self


class PlanningInput(StrictModel):
    command: PlanCommand
    forecast_input_digest: str
    forecast_rows: list[dict]
    approved_inputs: dict[str, list[dict]]
    capacity_snapshot: dict
    routing_snapshot: dict
    policy_snapshot: dict


class PlanningOutput(StrictModel):
    contract_version: Literal['planning-integration-0.1-draft'] = 'planning-integration-0.1-draft'
    status: Literal['OK', 'PARTIAL', 'INPUT_INVALID', 'UNSUPPORTED', 'FAILED']
    plans: list[dict]
    constraint_evaluations: list[dict]
    material_requirements: list[dict]
    evidence: list[dict]
    warnings: list[dict]
    unverified: list[dict]
    errors: list[dict]
    module_version: str


class Classifier(Protocol):
    def classify(self, request: ClassificationInput) -> ClassificationOutput: ...


class Planner(Protocol):
    def run(self, request: PlanningInput) -> PlanningOutput: ...
