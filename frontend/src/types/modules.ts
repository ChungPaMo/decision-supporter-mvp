// Mirrored transport types. Source of truth: contracts/interfaces and generated JSON Schema.
export type ClassificationResult = {
  contract_version: 'classification-0.1-draft'; recommended_entity: import('./api').Entity | null;
  candidates: Array<{ entity: import('./api').Entity; score: number; reasons: string[] }>;
  hold: boolean; reasons: string[]; module_version: string;
};
export type PlanningIssue = { code: string; message: string; input_refs: string[] };
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
