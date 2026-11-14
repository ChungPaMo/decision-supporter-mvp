"""Server-side transition rules. No authentication adapter is installed."""
from dataclasses import dataclass
from app.errors import ApiError,ErrorCode


@dataclass(frozen=True)
class ApprovalContext:
    # Created by a future trusted server auth adapter, never from request JSON.
    subject: str
    roles: frozenset[str]
    verified: bool = False
    policy_enabled: bool = False


def approval_allowed(execution,candidate,context):
    if context is None or not context.verified or not context.policy_enabled or 'PLAN_APPROVER' not in context.roles:
        raise ApiError(501,ErrorCode.PLAN_APPROVAL_DISABLED,'Formal approval requires server authentication, role and confirmed policy integration.')
    if (execution.data_origin!='REAL_ENGINE' or execution.status not in ('COMPLETED','PARTIAL') or
        candidate.feasibility!='FEASIBLE' or not execution.policy_version or not candidate.policy_ref or
        execution.input_snapshot.missing_inputs or execution.result_snapshot.unverified or candidate.unverified or
        not execution.result_snapshot.evidence or execution.result_snapshot.errors):
        raise ApiError(409,ErrorCode.PLAN_DECISION_BLOCKED,'Plan is not eligible for formal approval.')
    checks=[c for c in execution.result_snapshot.constraint_evaluations if c.plan_id==candidate.plan_id]
    if not checks or any(c.status!='SATISFIED' or c.application_state!='APPLIED' for c in checks):
        raise ApiError(409,ErrorCode.PLAN_DECISION_BLOCKED,'Unverified or violated constraints block formal approval.')


def transition(execution,request,context=None):
    if request.action=='APPROVE' and context is None:
        raise ApiError(501,ErrorCode.PLAN_APPROVAL_DISABLED,'Formal approval is disabled until authentication and policy integration.')
    if request.expected_version!=execution.version or request.expected_input_digest!=execution.input_digest:
        raise ApiError(409,ErrorCode.VERSION_CONFLICT,'Review version or input digest changed.')
    candidate=next((p for p in execution.result_snapshot.plans if p.plan_id==request.plan_id),None)
    if candidate is None or execution.status not in ('COMPLETED','PARTIAL'):
        raise ApiError(409,ErrorCode.PLAN_DECISION_BLOCKED,'Candidate does not belong to a successful execution.')
    if request.action=='APPROVE': approval_allowed(execution,candidate,context)
    allowed={('DRAFT','REVIEW'):'REVIEW',('REVIEW','APPROVE'):'APPROVED',('REVIEW','REJECT'):'REJECTED'}
    target=allowed.get((execution.decision_status,request.action))
    if not target or (execution.decision_status=='REVIEW' and execution.selected_plan_id!=request.plan_id):
        raise ApiError(409,ErrorCode.PLAN_DECISION_BLOCKED,'Finalized review or different selected candidate; create a new execution.')
    return target
