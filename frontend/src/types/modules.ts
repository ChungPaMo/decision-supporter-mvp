// Mirrored transport types. Source of truth: contracts/interfaces and generated JSON Schema.
export type ClassificationResult = {
  contract_version: 'classification-0.1-draft'; recommended_entity: import('./api').Entity | null;
  candidates: Array<{ entity: import('./api').Entity; score: number; reasons: string[] }>;
  hold: boolean; reasons: string[]; module_version: string;
};
// contracts/interfaces/dataset.py — schema_name 은 서버 내부 값이라 응답에 없다.
export type DatasetDetail = {
  dataset_id: string; dataset_name: string; description: string; source_type: 'SYNTHETIC';
  status: 'ACTIVE' | 'ARCHIVED'; created_at: string; created_by: string | null;
};
// contracts/interfaces/plan_execution.py
export type PlanDecisionAction = 'REVIEW' | 'APPROVE' | 'REJECT';
export type PlanDecisionEvent = {
  decision_id: string; execution_id: string; plan_id: string; action: PlanDecisionAction;
  status_before: string; status_after: string; actor_id: string; auth_verified: boolean;
  reason: string; input_digest: string; decided_at: string; exception_codes: string[];
};
export type PlanExecutionSummary = {
  dataset_id: string; execution_id: string; forecast_execution_id: string; base_plan_execution_id: string | null;
  scenario_type: 'BASE' | 'WHAT_IF'; target_month: string; as_of_date: string; status: 'COMPLETED' | 'PARTIAL' | 'FAILED';
  input_digest: string; result_digest: string; engine_version: string; policy_version: string | null;
  created_at: string; completed_at: string; error_code: string | null; data_origin: 'REAL_ENGINE' | 'TEST_DOUBLE';
  decision_status: 'DRAFT' | 'REVIEW' | 'APPROVED' | 'REJECTED'; selected_plan_id: string | null; version: number;
};
export type PlanExecutionDetail = PlanExecutionSummary & { result_snapshot: PlanningReply['result']; decisions: PlanDecisionEvent[] };
export type PlanExecutionReply = { execution: PlanExecutionDetail; reused: boolean };
export type PlanExecutionCommand = { forecast_execution_id: string; product_ids: string[]; target_month: string; as_of_date: string; scenario: 'BASE' };
export type PlanDecisionRequest = { plan_id: string; action: PlanDecisionAction; actor_id: string; reason: string; expected_version: number; expected_input_digest: string };
export type PlanningIssue ={ code: string; message: string; input_refs: string[] };
export type PlanCandidate = {
  plan_id: string; plan_type: 'BASELINE' | 'STABLE' | 'COST_SAVING' | 'CUSTOM'; label: string;
  feasibility: 'FEASIBLE' | 'UNVERIFIED' | 'INFEASIBLE'; policy_ref: string | null;
  production: Array<{ product_id: string; period: string; production_qty: string; unit: string }>;
  unverified: PlanningIssue[];
};
export type ConstraintEvaluation = {
  constraint_id: string; plan_id: string; dimension: string; period: string; resource_id: string | null;
  product_id: string | null; step_id: string | null; status: 'SATISFIED' | 'VIOLATED' | 'UNVERIFIED';
  limit_value: string | null; used_value: string | null; unit: string | null;
  time_basis: string | null; input_refs: string[]; reason_codes: string[];
};
export type PlanningReply = {
  contract_version: 'planning-preview-0.2-draft'; forecast_execution_id: string; input_digest: string;
  persisted: false; approval_available: false;
  result: { contract_version: 'planning-handoff-0.2-draft'; status: 'OK' | 'PARTIAL' | 'INPUT_INVALID' | 'UNSUPPORTED' | 'FAILED';
    plans: PlanCandidate[]; constraint_evaluations: ConstraintEvaluation[];
    material_requirements: Array<{ plan_id: string; material_id: string; period: string; required_qty: string | null; available_qty: string | null; shortage_qty: string | null; unit: string; input_refs: string[] }>;
    evidence: PlanningIssue[]; warnings: PlanningIssue[]; unverified: PlanningIssue[]; errors: PlanningIssue[]; module_version: string;
  };
};
