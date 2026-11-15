// 예시 시나리오(화장지 제조기업 CHUNGPAMO-2027) 합성 데이터.
// 기획 PDF "06. 예시 시나리오"의 9개 화면 시안을 위한 고정 설명값이며
// 서버 저장값·예측 엔진·계획 엔진의 결과가 아니다.

export const DATASET = 'CHUNGPAMO-2027';
export const PRODUCT = { id: 'CP-N3-3030', name: '천연펄프 3겹 30m' };
export const PRODUCT_LABEL = `${PRODUCT.id} (${PRODUCT.name})`;
export const PERIOD = { from: '2027-01', to: '2027-03', months: ['2027-01', '2027-02', '2027-03'] };
export const STOCK_PACKS = 22400;

export const UPLOAD_FILES = [
  { name: '판매현황_2022.csv', rows: 17240, size: '2.8 MB' },
  { name: '판매현황_2023.csv', rows: 16980, size: '2.7 MB' },
  { name: '판매현황_2024.csv', rows: 17120, size: '2.8 MB' },
  { name: '판매현황_2025.csv', rows: 16940, size: '2.7 MB' },
  { name: '판매현황_2026.csv', rows: 17934, size: '2.9 MB' },
];
export const MERGED_FILE = { name: '판매현황_2022~2026.csv', rows: 86214, size: '13.9 MB' };

export type RowKind = '정상' | '취소' | '반품';
export const RAW_PREVIEW: Array<{ date: string; product: string; qty: number; kind: RowKind }> = [
  { date: '2026-03-01', product: 'CP-N3-3030', qty: 150, kind: '정상' },
  { date: '2026-03-02', product: 'CP-N3-2730', qty: 200, kind: '정상' },
  { date: '2026-03-03', product: 'CP-N3-3030', qty: 50, kind: '취소' },
  { date: '2026-03-04', product: 'CP-N3-3030', qty: 120, kind: '정상' },
  { date: '2026-03-05', product: 'CP-N3-3030', qty: 80, kind: '반품' },
];

export const CLASSIFICATION_EVIDENCE = [
  { label: '파일명', detail: '"판매현황" 키워드가 판매 거래 데이터와 일치' },
  { label: '컬럼 구성', detail: '주문일자 · 제품코드 · 수량 · 구분 — 거래 단위 행 구조' },
  { label: '샘플 값', detail: '일 단위 날짜와 정상/취소/반품 상태값 확인' },
  { label: '다른 후보', detail: '월별 수요(낮음) — 날짜가 일 단위라 제외' },
];

export interface MappingRow { source: string; options: string[]; recommended: string; needsReview: boolean }
export const MAPPING: MappingRow[] = [
  { source: '주문일자', options: ['order_date 또는 period 기준', '매핑 안 함'], recommended: 'order_date 또는 period 기준', needsReview: false },
  { source: '제품코드', options: ['product_id', '매핑 안 함'], recommended: 'product_id', needsReview: false },
  { source: '수량', options: ['quantity / demand_qty', '매핑 안 함'], recommended: 'quantity / demand_qty', needsReview: false },
  { source: '구분', options: ['상태 필터 (정상만 포함)', '상태 필터 (정상 + 반품 차감)', '매핑 안 함'], recommended: '상태 필터 (정상만 포함)', needsReview: true },
];

export const TRANSFORM_RULES = [
  { label: '정상 거래만 포함', tone: 'ok' },
  { label: '취소 제외', tone: 'bad' },
  { label: '반품 별도 집계', tone: 'violet' },
  { label: '월 단위 합산', tone: 'info' },
  { label: '팩 → EA 표준화', tone: 'muted' },
] as const;

export const TRANSFORM_SUMMARY = { source: 86214, normal: 83984, cancelled: 887, returned: 1343, result: 498 };

export const TRANSFORM_PREVIEW = [
  { product_id: 'CP-N3-3030', period: '2026-01', demand_qty: 12540, unit: 'EA' },
  { product_id: 'CP-N3-3030', period: '2026-02', demand_qty: 14210, unit: 'EA' },
  { product_id: 'CP-N3-3030', period: '2026-03', demand_qty: 13860, unit: 'EA' },
];

export const VALIDATION_TOTAL = 498;
export const VALIDATION_SUMMARY = [
  { key: 'required', label: '필수값 누락', rows: 12, tone: 'bad' },
  { key: 'format', label: '형식 오류', rows: 7, tone: 'warn' },
  { key: 'reference', label: '참조 불일치', rows: 5, tone: 'violet' },
  { key: 'duplicate', label: '중복 여부', rows: 3, tone: 'info' },
  { key: 'approvable', label: '최종 승인 가능', rows: 471, tone: 'ok' },
] as const;

export type Severity = '치명' | '경고' | '정보';
export const ISSUES: Array<{ severity: Severity; row: number; field: string; message: string; action: string }> = [
  { severity: '치명', row: 278, field: 'quantity', message: '필수값이 누락되었습니다.', action: '수량을 입력하거나 행을 제외' },
  { severity: '경고', row: 315, field: 'demand_qty', message: '숫자 형식이 아닙니다. (값: "N/A")', action: '숫자 형식으로 수정 (예: 0 또는 결측 처리)' },
  { severity: '경고', row: 342, field: 'product_id', message: '참조 제품코드에 존재하지 않습니다. (값: CP-X999)', action: '유효한 제품코드로 수정 또는 마스터 갱신' },
  { severity: '정보', row: 366, field: 'order_date', message: '날짜 형식이 기준과 다릅니다. (값: 2026/03/05)', action: 'YYYY-MM-DD 형식으로 변환 (→ 2026-03-05)' },
  { severity: '정보', row: 401, field: '(행 전체)', message: '중복된 데이터가 존재합니다. (키: CP-N3-3030, 2026-03)', action: '중복 행 확인 후 하나만 유지' },
];

export const PASSED_CHECKS = [
  { title: '단위 정규화', detail: 'EA, 개 등 3개 단위를 기준(EA)으로 통일' },
  { title: '날짜 형식 정규화', detail: '모든 날짜를 YYYY-MM-DD 형식으로 변환' },
  { title: '데이터셋 연계 검증', detail: '제품·거래처 마스터와의 참조 연계 정상' },
];

export const SNAPSHOT = {
  entity: 'monthly_demand',
  snapshotDigest: 'a7c3e9f4b2d0e6d1c9b8f3e0a4d7c1b2',
  sourceSha: '9f3e7a2d8c4e9b1d6f0e3c7a5b2d9e8f',
  policyDigest: 'd5c9a1e7f6b3c0d8e2a4b7f9c1e6d3a0',
  author: '김대영',
};

export const LINEAGE = [
  { title: '원본 파일', lines: ['판매현황_2022~2026.csv', '(86,214행 · 13.9 MB)'] },
  { title: '변환 규칙', lines: ['매핑/변환 v1.0', '(5개 규칙 적용)'] },
  { title: '검증 결과', lines: ['오류·경고 27행', '(승인 가능 471행)'] },
  { title: '등록 snapshot', lines: ['CHUNGPAMO-2027:v1', '(498행 · 승인 후 생성)'] },
];

// 월별 실수요(팩). 2025-01 ~ 2026-12, 24개월 평균 8,562팩 · 전년 대비 +8.4%.
const HISTORY_VALUES = [
  7600, 7900, 7750, 8000, 8350, 8050, 8250, 7950, 8300, 8500, 8900, 9053,
  8300, 8600, 8450, 8700, 9000, 8750, 8950, 8700, 9100, 9300, 9500, 9535,
];
export const HISTORY = HISTORY_VALUES.map((value, i) => ({
  month: `${2025 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`,
  value,
}));

const sum = (values: number[]) => values.reduce((a, b) => a + b, 0);
export const HISTORY_AVG = Math.round(sum(HISTORY_VALUES) / HISTORY_VALUES.length);
export const LAST12_TOTAL = sum(HISTORY_VALUES.slice(12));
export const YOY_PCT = Math.round((LAST12_TOTAL / sum(HISTORY_VALUES.slice(0, 12)) - 1) * 1000) / 10;

export type Quantile = 'p50' | 'p80' | 'p90';
export const QUANTILES: Array<{ key: Quantile; label: string; short: string; color: string; values: number[]; meaning: string; usage: string; plan: string; planDetail: string }> = [
  {
    key: 'p50', label: 'P50 (기준)', short: 'P50', color: '#1d5fd6', values: [9600, 9800, 10000],
    meaning: '가장 가능성이 높은(중앙값) 수요 수준으로, 예측의 기준이 되는 값',
    usage: '특별한 변동이 없을 때의 기본 생산계획 수립(기준형 계획)에 활용',
    plan: '기준형 계획', planDetail: '통상적인 수요 수준으로 계획 수립',
  },
  {
    key: 'p80', label: 'P80 (안정)', short: 'P80', color: '#0f9d6b', values: [10300, 10600, 10900],
    meaning: '실제 수요가 이 값 이하일 가능성이 약 80%인, 여유가 있는 수요 수준',
    usage: '수요 증가 리스크를 일부 반영해 안전 재고 확보 및 운영 안정성을 높이는 계획(안정형 계획)에 활용',
    plan: '안정형 계획', planDetail: '수요 증가에 대비한 여유 계획',
  },
  {
    key: 'p90', label: 'P90 (상한)', short: 'P90', color: '#8b46d9', values: [10800, 11200, 11600],
    meaning: '높은 수요 발생까지 고려한 상한 수준(약 90%)으로, 일시적 급증이나 피크 수요를 반영한 값',
    usage: '프로모션, 계절성, 거래처 증대 등으로 수요 급증이 예상될 때 상한 대응 점검(추가 생산·재고 확보 검토)에 활용',
    plan: '상한 대응 점검', planDetail: '피크 수요 대비 추가 생산·재고 검토',
  },
];
export const quantileAvg = (key: Quantile) => {
  const values = QUANTILES.find((q) => q.key === key)!.values;
  return Math.round(sum(values) / values.length);
};

export type PlanId = 'BASELINE' | 'STABLE' | 'COST_SAVING';
export interface Plan {
  id: PlanId; name: string; color: string; description: string; strategy: string; effect: string;
  production: number; utilization: number; overtime: number; materialKg: number; spareStock: number;
  demandFill: number; materialOk: boolean; saw1: number[]; lb1: number[]; labor: number[]; reasons: string[];
}
export const RECOMMENDED: PlanId = 'BASELINE';
export const PLANS: Plan[] = [
  {
    id: 'BASELINE', name: '기준형', color: '#1d5fd6', description: '예측 수요를 기준으로 한 기본 계획',
    strategy: '수요 기준 운영, 표준 가동', effect: '수요 충족, 재고 안정화',
    production: 29400, utilization: 87, overtime: 0, materialKg: 12740, spareStock: 4200, demandFill: 100, materialOk: true,
    saw1: [85, 87, 89], lb1: [84, 86, 88], labor: [74, 76, 78],
    reasons: ['예측 수요를 안정적으로 충족 (수요 충족률 100 %)', '설비 가동률이 적정 수준 (87 %)', '잔업 없이 운영 가능 (0 시간/월)', '주요 자재 모두 원활히 확보 가능'],
  },
  {
    id: 'STABLE', name: '안정형', color: '#0f9d6b', description: '수요 변동 대응을 고려한 여유 계획',
    strategy: 'P80 수요 대응, 여유 재고 확보', effect: '수요 급증 대응력, 결품 위험 완화',
    production: 30800, utilization: 91, overtime: 1, materialKg: 13350, spareStock: 5600, demandFill: 100, materialOk: true,
    saw1: [89, 91, 93], lb1: [88, 90, 92], labor: [78, 80, 82],
    reasons: ['P80 수요까지 대응할 여유 재고 확보 (기간 말 5,600 팩)', '설비 가동률이 높은 편 (91 %) — 2027-03 SAW1 93 %', '월 1시간 수준의 잔업 필요', '주요 자재 확보 가능하나 여유 폭이 작음'],
  },
  {
    id: 'COST_SAVING', name: '비용절감형', color: '#8b46d9', description: '가동률을 낮춰 비용을 절감하는 계획',
    strategy: '가동 축소, 기존 재고 활용', effect: '운영비 절감, 재고 축소',
    production: 27600, utilization: 82, overtime: 0, materialKg: 11970, spareStock: 3100, demandFill: 94, materialOk: false,
    saw1: [80, 82, 84], lb1: [79, 81, 83], labor: [70, 72, 74],
    reasons: ['가동률을 낮춰 운영비 절감 (82 %)', '잔업 없이 운영 가능 (0 시간/월)', '생산만으로는 예측 수요의 94 % — 부족분은 기존 재고로 충당', '포장재 일부 품목의 입고 일정 확인 필요'],
  },
];
export const planById = (id: PlanId) => PLANS.find((plan) => plan.id === id)!;

export const ASSUMPTIONS = [
  '설비 가용 시간: 8 시간/일, 20 일/월',
  '유지보수: 계획 기간 내 1 회 (2027-02, 8 시간)',
  '자재 공급: 기존 계약 기준, 리드타임 3 일',
  '운영 제약: 최대 가동률 95 %, 잔업 한도 2 시간/일',
];

// What-if 설명용 단순 환산식 (계획 엔진 아님).
export const PULP_AVAILABLE_KG = 13400;
export const UTILIZATION_LIMIT = 95;
export const UTILIZATION_WATCH = 90;
export type Priority = 'STANDARD' | 'BALANCED' | 'COST';
export interface WhatIf { adjustPct: number; overtime: number; priority: Priority }
export const WHATIF_DEFAULT: WhatIf = { adjustPct: 8, overtime: 1.5, priority: 'STANDARD' };
export const PRIORITIES: Array<{ id: Priority; label: string; note: string }> = [
  { id: 'STANDARD', label: '표준 (수요 충족 우선)', note: '월별 수요 흐름을 따라 생산' },
  { id: 'BALANCED', label: '가동률 균형 (설비 부하 최소화)', note: '월별·설비별 부하를 평준화' },
  { id: 'COST', label: '비용 절감 (운영비 최소화)', note: '잔업을 사용하지 않음' },
];

export interface WhatIfResult {
  production: number; materialKg: number; pulpGap: number; overtime: number;
  saw1: number[]; lb1: number[]; labor: number[]; avgUtilization: number; peak: { month: string; value: number };
}
export function applyWhatIf(plan: Plan, w: WhatIf): WhatIfResult {
  const overtime = w.priority === 'COST' ? 0 : w.overtime;
  const factor = (1 + w.adjustPct / 100) * (8 / (8 + overtime));
  const scale = (values: number[]) => values.map((v) => Math.round(v * factor));
  let saw1 = scale(plan.saw1);
  let lb1 = scale(plan.lb1);
  if (w.priority === 'BALANCED') {
    const level = Math.round(sum([...saw1, ...lb1]) / 6);
    saw1 = saw1.map(() => level);
    lb1 = lb1.map(() => level);
  }
  const production = Math.round(plan.production * (1 + w.adjustPct / 100) / 100) * 100;
  const materialKg = Math.round(plan.materialKg * production / plan.production / 10) * 10;
  const peakValue = Math.max(...saw1);
  return {
    production, materialKg, pulpGap: PULP_AVAILABLE_KG - materialKg, overtime,
    saw1, lb1, labor: scale(plan.labor),
    avgUtilization: Math.round(sum(saw1) / saw1.length),
    peak: { month: PERIOD.months[saw1.indexOf(peakValue)], value: peakValue },
  };
}

export const SCREENS = [
  { no: 1, nav: 'upload', crumb: ['데이터 업로드', '파일 업로드 및 분류'], title: '파일 업로드 및 분류', short: '업로드' },
  { no: 2, nav: 'upload', crumb: ['데이터 업로드', '파일 업로드 및 변환'], title: '파일 업로드 및 변환', short: '매핑·변환' },
  { no: 3, nav: 'verify', crumb: ['데이터 검증', '검증·승인·등록'], title: '검증·승인·등록', short: '검증' },
  { no: 4, nav: 'forecast', crumb: ['수요예측', '수요예측 설정'], title: '수요예측 설정', short: '예측 설정' },
  { no: 5, nav: 'forecast', crumb: ['수요예측', '수요예측 결과'], title: '수요예측 결과', short: '예측 결과' },
  { no: 6, nav: 'forecast', crumb: ['수요예측', '예측 근거와 활용'], title: '예측 근거와 활용 방식', short: '예측 해석' },
  { no: 7, nav: 'plan', crumb: ['생산계획', '생산계획 추천안 비교'], title: '생산계획 추천안 비교', short: '계획안 비교' },
  { no: 8, nav: 'whatif', crumb: ['시나리오 분석', 'What-if 및 제약 검토'], title: 'What-if 및 제약 검토', short: 'What-if' },
  { no: 9, nav: 'whatif', crumb: ['시나리오 분석', '최종 계획 검토'], title: '최종 계획 검토 (MPS 후보 선정)', short: '최종 검토' },
] as const;

export const fmt = (value: number) => value.toLocaleString('ko-KR');

export function downloadCsv(filename: string, rows: Array<Array<string | number>>) {
  const csv = String.fromCharCode(0xfeff) + rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join(String.fromCharCode(13, 10));
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url; link.download = filename; link.click();
  URL.revokeObjectURL(url);
}
