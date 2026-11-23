// 데이터 입력 보조·변환·이력 응답 타입. 기준: contracts/interfaces/ingestion.py, ingestion_history.py
import { CoreEntity } from './api';
import { ClassificationResult } from './modules';

export interface ColumnProfile {
  col: number; column: string; normalized_column: string; total_rows: number;
  empty_count: number; empty_ratio: number; non_null_ratio: number; distinct_count: number;
  type_candidates: string[]; format_match_rates: Record<string, number>;
  unit_candidates: string[]; anomalies: string[]; uncertainty_reasons: string[];
}
export interface ProfileReply {
  dataset_id: string; source_sha256: string; master_scope: string | null; master_digest: string | null;
  samples_included: boolean; sheets: Array<{ sheet: string; row_count: number; columns: ColumnProfile[] }>;
  persisted: false;
}

// 후보에는 점수·확률 필드가 없다. 순서는 검토용 순위일 뿐이다.
export interface MappingCandidate { target_field: string; method: string; evidence: string[]; requires_review: true }
export interface ColumnSuggestion { col: number; source_column: string; suggestions: MappingCandidate[]; unresolved_reasons: string[] }
export interface MappingSheetReply {
  sheet: string; status: 'MAPPED' | 'HOLD' | 'IGNORED'; existing_mapping: Record<string, number>;
  suggestions: ColumnSuggestion[]; holds: string[];
}
export interface MappingReply {
  dataset_id: string; entity: CoreEntity; source_sha256: string; master_scope: string | null;
  sheets: MappingSheetReply[]; persisted: false;
}
export interface ClassifiedMappingReply {
  dataset_id: string; source_sha256: string; classification: ClassificationResult;
  selected_entity: CoreEntity | null; selection_method: 'CLASSIFIER_RECOMMENDATION' | 'USER_SELECTION' | 'REQUIRED';
  mapping: MappingReply | null; next_action: 'REVIEW_MAPPING' | 'SELECT_ENTITY_OR_TRANSFORM';
}

// 판매 원장의 7개 의미. 월별 수요의 column_overrides(period, demand_qty)와 다른 역할이다.
export type SalesColumnKey = 'order_date' | 'product_id' | 'quantity' | 'unit' | 'status' | 'order_id' | 'line_id';
export type SalesColumns = Record<SalesColumnKey, string>;
export interface SalesTransformPolicy {
  dataset_id: string; policy_id: 'CHUNGPAMO_SYNTHETIC_SALES'; version: '1.0';
  columns: SalesColumns; user_confirmed: boolean;
  source_scope?: 'SYNTHETIC_ONLY'; date_formats?: string[]; unit_mapping?: Record<string, string>;
  included_status?: string; excluded_status?: string; separate_status?: string;
}
export interface SourceLocation { source_index: number; sheet: string; row: number; col?: number | null }
export interface TransformReply {
  dataset_id: string; status: 'POLICY_REVIEW_REQUIRED' | 'HAS_ERRORS' | 'TRANSFORMED_PREVIEW';
  policy: SalesTransformPolicy; policy_digest: string; input_digest: string; result_digest: string;
  sources: Array<{ source_index: number; filename: string; sha256: string; row_count: number; table_selection?: XlsxTableSelection; resolved_columns?: Record<string, number> }>;
  operations: Array<{ operation: string; parameters: Record<string, unknown> }>;
  master_scope: string | null; master_digest: string | null;
  counts: Record<string, number>; quantity_reconciliation: Record<string, string | boolean>;
  records: Array<{ product_id: string; period: string; demand_qty: string; unit: string; source_row_count: number }>;
  returns: Array<{ product_id: string; period: string; return_qty: string; unit: string }>;
  // TransformIssue 에는 message·raw_value 가 없다. code 를 표시한다.
  issues: Array<{ code: string; location: SourceLocation; field?: string | null }>;
  issues_total: number; warnings: string[]; total: number; offset: number; limit: number; returns_total: number;
  persisted: false;
}
export interface TransformationSummary {
  transformation_id: string; dataset_id: string; batch_id: string; batch_status: string;
  created_at: string; created_by: string; engine_version: string;
  input_digest: string; result_digest: string; policy_digest: string; manifest_digest: string; output_sha256: string;
  persisted: true;
}
export interface TransformationDetail extends TransformationSummary { preview: TransformReply }

// contracts/interfaces/xlsx.py — 좌표는 원본 통합문서 기준 1부터 시작하며 끝을 포함한다.
export interface XlsxTableSelection {
  source_sha256: string; sheet: string; header_row: number; data_start_row: number; data_end_row: number; first_col: number; last_col: number;
}
export interface XlsxLayoutReply {
  source_sha256: string; filename: string;
  sheets: Array<{ name: string; visibility: 'visible' | 'hidden' | 'veryHidden'; max_row: number; max_col: number }>;
  window: null | {
    sheet: string; first_row: number; last_row: number; first_col: number; last_col: number;
    hidden_columns: number[]; merged_ranges: string[]; merges_truncated: boolean;
    cells: Array<{ row: number; col: number; kind: 'text' | 'number' | 'date' | 'bool' | 'formula' | 'error' | 'merged' | 'empty'; value: string | null }>;
  };
}
