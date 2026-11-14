"""Draft handoff contracts. They do not define planning formulas or approval policy."""
from typing import Annotated, Literal, Protocol
from pydantic import Field, model_validator
from .base import StrictModel, Code, DecimalValue

Entity = Literal['product', 'material', 'bom', 'inventory', 'monthly_demand']
class SheetSample(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=200)] | None
    columns: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=100)]
    sample_rows: Annotated[list[list[Annotated[str | None, Field(max_length=500)]]], Field(max_length=20)] = []

    @model_validator(mode='after')
    def bounded_width(self):
        if any(len(row) > len(self.columns) for row in self.sample_rows):
            raise ValueError('Sample row width exceeds the supplied columns')
        return self


class ClassificationInput(StrictModel):
    contract_version: Literal['classification-0.1-draft'] = 'classification-0.1-draft'
    filename: Annotated[str, Field(min_length=1, max_length=200, pattern=r'^[^/\\:\x00-\x1f]+$')]
    sha256: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    format: Literal['csv', 'xlsx'] | None = None
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
    module_version: str = Field(min_length=1, max_length=80)

    @model_validator(mode='after')
    def recommendation_is_candidate(self):
        entities = [c.entity for c in self.candidates]
        if len(entities) != len(set(entities)) or (self.recommended_entity and self.recommended_entity not in entities):
            raise ValueError('Recommendation must reference a unique candidate')
        if self.recommended_entity is None and not self.hold:
            raise ValueError('Missing recommendation requires HOLD')
        if self.hold and not self.reasons:
            raise ValueError('HOLD requires reasons')
        return self


from .planning import PlanCommand, PlanningInput, PlanningOutput, PlanningReply


class Classifier(Protocol):
    def classify(self, request: ClassificationInput) -> ClassificationOutput: ...


class Planner(Protocol):
    def run(self, request: PlanningInput) -> PlanningOutput: ...
