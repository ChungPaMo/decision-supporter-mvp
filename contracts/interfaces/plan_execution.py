"""Persistence envelope, separate from read-only preview and calculation policy."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import Field
from .base import StrictModel, Code
from .planning import PlanCommand, PlanningInput, PlanningOutput, PlanCandidate


class PlanExecutionCreate(PlanCommand):
    pass


class PlanDecisionRequest(StrictModel):
    plan_id: Code
    action: Literal['REVIEW','APPROVE','REJECT']
    actor_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{1,59}$')
    reason: str = Field(min_length=1,max_length=1000)
    expected_version: int = Field(ge=1)
    expected_input_digest: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    # Exception approval policy is deliberately not exposed.


class PlanDecisionEvent(StrictModel):
    decision_id: UUID
    execution_id: UUID
    plan_id: Code
    action: Literal['REVIEW','APPROVE','REJECT']
    status_before: str
    status_after: str
    actor_id: str
    auth_verified: bool
    reason: str
    input_digest: str
    decided_at: datetime
    exception_codes: list[str]


class PlanDecisionHistory(StrictModel):
    items: list[PlanDecisionEvent]


class PlanCandidateDetail(PlanCandidate):
    pass


class PlanExecutionSummary(StrictModel):
    execution_id: UUID
    forecast_execution_id: UUID
    base_plan_execution_id: UUID | None
    scenario_type: Literal['BASE','WHAT_IF']
    target_month: str
    as_of_date: str
    status: Literal['COMPLETED','PARTIAL','FAILED']
    input_digest: str
    result_digest: str
    engine_version: str
    policy_version: str | None
    runtime_identity: dict
    created_at: datetime
    completed_at: datetime
    error_code: str | None
    data_origin: Literal['REAL_ENGINE','TEST_DOUBLE']
    decision_status: Literal['DRAFT','REVIEW','APPROVED','REJECTED']
    selected_plan_id: Code | None
    version: int


class PlanExecutionDetail(PlanExecutionSummary):
    input_snapshot: PlanningInput
    result_snapshot: PlanningOutput
    decisions: list[PlanDecisionEvent] = Field(default_factory=list)


class PlanExecutionReply(StrictModel):
    execution: PlanExecutionDetail
    reused: bool


class PlanExecutionList(StrictModel):
    items: list[PlanExecutionSummary]
    total: int
    limit: int
    offset: int


class PlanExportMetadata(StrictModel):
    execution_id: UUID
    plan_id: Code
    input_digest: str
    result_digest: str
    engine_version: str
    export_status: Literal['APPROVED'] = 'APPROVED'
