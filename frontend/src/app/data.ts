// 화면들이 함께 쓰는 서버 조회와 계획 결과 요약.
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../services/api';
import { BatchSummary, Entity } from '../types/api';
import { ForecastExecution, ForecastExecutionSummary } from '../types/engine';
import { ConstraintEvaluation, PlanCandidate, PlanExecutionDetail, PlanExecutionSummary, PlanningIssue, PlanningReply } from '../types/modules';
import { ENTITY_NAME, ENTITY_ORDER, failure, ISSUE_TEXT, monthLabel, PageId } from './core';

export type PlanResult = PlanningReply['result'];
export type DemandRow = { product_id: string; period: string; demand_qty: string; unit: string };
export type Names = Record<string, string>;

// 비동기 조회 하나를 화면 상태로 다룬다.
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);
  const run = useCallback(async () => {
    setLoading(true); setError('');
    try { const value = await loader(); if (alive.current) setData(value); }
    catch (reason) { if (alive.current) setError(failure(reason)); }
    finally { if (alive.current) setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { alive.current = true; void run(); return () => { alive.current = false; }; }, [run]);
  return { data, error, loading, reload: run, setData };
}

export interface Overview {
  batches: BatchSummary[]; forecasts: ForecastExecutionSummary[]; plans: PlanExecutionSummary[];
  latestForecast: ForecastExecution | null; latestPlan: PlanExecutionDetail | null; planForecast: ForecastExecution | null;
  demand: DemandRow[]; names: Names; problems: string[];
}
export const EMPTY_OVERVIEW: Overview = { batches: [], forecasts: [], plans: [], latestForecast: null, latestPlan: null, planForecast: null, demand: [], names: {}, problems: [] };

// 승인된 기준정보에서 코드 → 이름을 만든다 (제품, 자재, 설비·인력). 화면은 코드 대신 이름을 보여 준다.
export async function loadNames(): Promise<Names> {
  const names: Names = {};
  const take = async (entity: Exclude<Entity, 'scheduled_receipt'>, id: string, name: string) => {
    try { for (const row of await apiClient.approvedData(entity)) if (row[id] && row[name]) names[String(row[id])] = String(row[name]); } catch { /* 이름이 없으면 코드를 그대로 쓴다 */ }
  };
  await Promise.all([take('product', 'product_id', 'product_name'), take('material', 'material_id', 'material_name'), take('capacity', 'resource_id', 'resource_name')]);
  return names;
}

// 홈·기록·상단 진행 표시가 함께 쓰는 전체 현황. 한 조회가 실패해도 나머지는 보여 준다.
export async function loadOverview(): Promise<Overview> {
  const problems: string[] = [];
  const safe = async <T,>(label: string, fn: () => Promise<T>, fallback: T): Promise<T> => {
    try { return await fn(); } catch (reason) { problems.push(`${label}: ${failure(reason)}`); return fallback; }
  };
  const [batches, forecastPage, planPage, demand, names] = await Promise.all([
    safe('자료 목록', () => apiClient.allBatches(), [] as BatchSummary[]),
    safe('예측 이력', () => apiClient.forecastHistory(50, 0), { items: [] as ForecastExecutionSummary[], total: 0, limit: 50, offset: 0 }),
    safe('계획 이력', () => apiClient.planExecutions(50, 0), { items: [] as PlanExecutionSummary[], total: 0, limit: 50, offset: 0 }),
    safe('월별 수요', () => apiClient.demandAll(), [] as DemandRow[]),
    loadNames(),
  ]);
  const ok = forecastPage.items.filter((item) => item.status === 'OK' || item.status === 'PARTIAL');
  const basePlan = planPage.items.find((item) => item.scenario_type === 'BASE' && item.status !== 'FAILED');
  const [latestForecast, latestPlan] = await Promise.all([
    ok[0] ? safe('최근 예측', () => apiClient.getForecast(ok[0].execution_id), null as ForecastExecution | null) : null,
    basePlan ? safe('최근 계획', () => apiClient.getPlanExecution(basePlan.execution_id), null as PlanExecutionDetail | null) : null,
  ]);
  const planForecast = !latestPlan ? null : latestPlan.forecast_execution_id === latestForecast?.execution_id ? latestForecast
    : await safe('계획에 쓴 예측', () => apiClient.getForecast(latestPlan.forecast_execution_id), null as ForecastExecution | null);
  return { batches, forecasts: forecastPage.items, plans: planPage.items, latestForecast, latestPlan, planForecast, demand, names, problems };
}

export const approvedEntities = (batches: BatchSummary[]) => ENTITY_ORDER.filter((entity) => batches.some((b) => b.entity === entity && b.status === 'APPROVED'));

// ── 계획 결과 요약 ──
const isEquip = (c: ConstraintEvaluation) => (c.dimension === 'EQUIPMENT_HOURS' || c.dimension === 'WORK_HOURS') && !!c.resource_id;
export interface PlanSummary {
  plan: PlanCandidate; total: number; byMonth: Record<string, number>;
  equipOver: number; maxUtil: number | null; demandMiss: number; safetyMiss: number; otherOver: number;
  shortages: number; shortageList: Array<{ material_id: string; period: string; shortage: number; required: number; unit: string }>;
}
export function summarizePlan(result: PlanResult, plan: PlanCandidate): PlanSummary {
  const byMonth: Record<string, number> = {};
  for (const row of plan.production) byMonth[row.period] = (byMonth[row.period] ?? 0) + Number(row.production_qty);
  const cs = result.constraint_evaluations.filter((c) => c.plan_id === plan.plan_id);
  const violated = cs.filter((c) => c.status === 'VIOLATED');
  const utils = cs.filter(isEquip).filter((c) => c.limit_value !== null && Number(c.limit_value) > 0).map((c) => Number(c.used_value ?? 0) / Number(c.limit_value));
  const shortageList = result.material_requirements.filter((m) => m.plan_id === plan.plan_id && Number(m.shortage_qty ?? 0) > 0)
    .map((m) => ({ material_id: m.material_id, period: m.period, shortage: Number(m.shortage_qty), required: Number(m.required_qty ?? 0), unit: m.unit }))
    .sort((a, b) => a.period.localeCompare(b.period) || b.shortage - a.shortage);
  const equipOver = violated.filter(isEquip).length, demandMiss = violated.filter((c) => c.constraint_id.startsWith('DEM-')).length, safetyMiss = violated.filter((c) => c.dimension === 'SAFETY_STOCK').length;
  return {
    plan, byMonth, total: Object.values(byMonth).reduce((a, b) => a + b, 0), equipOver, demandMiss, safetyMiss,
    otherOver: violated.length - equipOver - demandMiss - safetyMiss, maxUtil: utils.length ? Math.max(...utils) : null, shortages: shortageList.length, shortageList,
  };
}
export const planMonths = (result: PlanResult) => [...new Set(result.plans.flatMap((p) => p.production.map((row) => row.period)))].sort();
export const planProducts = (result: PlanResult) => [...new Set(result.plans.flatMap((p) => p.production.map((row) => row.product_id)))].sort();

// 설비·인력 × 달 부하 지도에 넣을 값.
export interface LoadCell { used: number; limit: number | null; pct: number | null; status: string; unit: string }
export function loadGrid(result: PlanResult, planId: string) {
  const months = planMonths(result);
  const rows = new Map<string, { id: string; kind: string; cells: Record<string, LoadCell> }>();
  for (const c of result.constraint_evaluations) {
    if (c.plan_id !== planId || !isEquip(c)) continue;
    const key = `${c.resource_id}|${c.dimension}`;
    const row = rows.get(key) ?? { id: c.resource_id!, kind: c.dimension, cells: {} };
    const limit = c.limit_value === null ? null : Number(c.limit_value), used = Number(c.used_value ?? 0);
    row.cells[c.period] = { used, limit, pct: limit && limit > 0 ? (used / limit) * 100 : null, status: c.status, unit: c.unit ?? 'h' };
    rows.set(key, row);
  }
  return { months, rows: [...rows.values()].sort((a, b) => a.kind.localeCompare(b.kind) || a.id.localeCompare(b.id)) };
}

// 예측 가운데 값(P50)의 제품·월별 수요. 계획 생산량과 견줄 기준이다.
export function demandOf(forecast: ForecastExecution | null): Record<string, Record<string, { p50: number; p80: number; p90: number }>> {
  const out: Record<string, Record<string, { p50: number; p80: number; p90: number }>> = {};
  for (const r of forecast?.result?.forecasts ?? []) (out[r.target_month] ??= {})[r.product_id] = { p50: Number(r.p50), p80: Number(r.p80), p90: Number(r.p90) };
  return out;
}
export const sumMonth = (map: Record<string, { p50: number }> | undefined) => Object.values(map ?? {}).reduce((a, v) => a + v.p50, 0);

// 같은 코드의 알림을 한 줄로 묶는다 (예: 재고 없음 18건 → 한 줄).
export function groupIssues(result: PlanResult): Array<{ code: string; text: string; count: number; refs: string[]; level: 'warn' | 'bad' }> {
  const groups = new Map<string, { text: string; refs: Set<string>; count: number; level: 'warn' | 'bad' }>();
  const add = (issue: PlanningIssue, level: 'warn' | 'bad') => {
    const g = groups.get(issue.code) ?? { text: ISSUE_TEXT[issue.code] ?? issue.message, refs: new Set<string>(), count: 0, level };
    g.count += 1; issue.input_refs.forEach((ref) => g.refs.add(ref)); groups.set(issue.code, g);
  };
  result.errors.forEach((issue) => add(issue, 'bad'));
  [...result.unverified, ...result.warnings].forEach((issue) => add(issue, 'warn'));
  return [...groups].map(([code, g]) => ({ code, text: g.text, count: g.count, refs: [...g.refs], level: g.level }));
}

// ── 진행 단계와 "다음에 할 일 한 가지" ──
export type StageState = 'done' | 'now' | 'wait';
export interface Stage { id: PageId; label: string; state: StageState; note: string }
export function stages(o: Overview): Stage[] {
  const approved = approvedEntities(o.batches).length;
  const dataDone = approved === ENTITY_ORDER.length, hasForecast = o.forecasts.some((f) => f.status === 'OK' || f.status === 'PARTIAL'), hasPlan = !!o.latestPlan;
  return [
    { id: 'ingest', label: '자료', state: dataDone ? 'done' : 'now', note: dataDone ? '모두 승인됨' : `${ENTITY_ORDER.length - approved}종 남음` },
    { id: 'forecast', label: '예측', state: hasForecast ? 'done' : dataDone ? 'now' : 'wait', note: o.latestForecast ? `${monthLabel(o.latestForecast.parameters.trained_until.slice(0, 7))} 말 기준` : '아직 없음' },
    { id: 'plan', label: '계획', state: hasPlan ? 'done' : hasForecast ? 'now' : 'wait', note: o.latestPlan ? `${monthLabel(o.latestPlan.target_month)}부터` : '아직 없음' },
  ];
}
export interface NextAction { tone: 'ok' | 'warn' | 'bad' | 'info'; title: string; text: string; button: string; page: PageId; params?: Record<string, string> }
export function nextAction(o: Overview): NextAction {
  const broken = o.batches.filter((b) => b.status === 'MAPPING_HOLD' || b.status === 'HAS_ERRORS');
  const ready = o.batches.filter((b) => b.status === 'READY_FOR_APPROVAL');
  const approved = new Set(approvedEntities(o.batches));
  const missing = ENTITY_ORDER.filter((e) => !approved.has(e));
  if (missing.length) return { tone: 'warn', title: `${ENTITY_NAME[missing[0]]} 자료부터 넣으세요`, text: `아직 승인되지 않은 자료: ${missing.map((e) => ENTITY_NAME[e]).join(', ')}. 파일을 한꺼번에 놓으면 순서대로 처리합니다.`, button: '자료 넣기', page: 'ingest' };
  if (ready.length) return { tone: 'info', title: `승인을 기다리는 자료 ${ready.length}건`, text: `${ready[0].file.name} 등. 검증 결과를 확인하고 승인하세요.`, button: '승인하러 가기', page: 'ingest' };
  if (!o.forecasts.some((f) => f.status === 'OK' || f.status === 'PARTIAL')) return { tone: 'info', title: '수요 예측을 실행하세요', text: '자료가 모두 준비됐습니다. 승인된 월별 수요로 앞으로의 수요를 예측합니다.', button: '수요 예측', page: 'forecast' };
  if (!o.latestPlan) return { tone: 'info', title: '생산계획을 계산하세요', text: '예측이 준비됐습니다. 세 안을 계산해 설비와 자재를 검토합니다.', button: '계획 계산', page: 'plan' };
  const result = o.latestPlan.result_snapshot;
  const s = result.plans.map((p) => summarizePlan(result, p));
  const base = s.find((x) => x.plan.plan_type === 'BASELINE') ?? s[0];
  const runnable = s.filter((x) => x.plan.feasibility !== 'INFEASIBLE');
  if (broken.length) return { tone: 'warn', title: `잘못 올라간 자료 ${broken.length}건을 정리하세요`, text: `${broken[0].file.name} (${ENTITY_NAME[broken[0].entity]}). 계획에는 쓰이지 않지만 목록에 남아 있습니다.`, button: '기록에서 반려', page: 'history', params: { kind: 'batch' } };
  if (!runnable.length) return { tone: 'bad', title: '세 안 모두 실행할 수 없습니다', text: '설비 능력이나 수요를 채우지 못합니다. 잔업 한도나 수요 가정을 바꿔 다시 계산해 보세요.', button: '조건 바꿔 보기', page: 'plan' };
  if (base && base.shortages) return { tone: 'warn', title: `${monthLabel(o.latestPlan.target_month)} 계획: 자재 ${base.shortages}건이 부족합니다`, text: `실행 가능한 안은 ${runnable.map((x) => x.plan.label.split(' ')[0]).join(', ')}입니다. 부족한 자재와 달을 확인하세요.`, button: '계획 검토', page: 'plan' };
  return { tone: 'ok', title: `${monthLabel(o.latestPlan.target_month)} 계획이 준비됐습니다`, text: `실행 가능한 안: ${runnable.map((x) => x.plan.label.split(' ')[0]).join(', ')}. 조건을 바꿔 비교해 볼 수 있습니다.`, button: '계획 보기', page: 'plan' };
}

// 홈의 알림: 같은 종류는 한 줄로 합친다 (안별로 반복하지 않는다).
export interface Alert { tone: 'bad' | 'warn' | 'info'; title: string; text: string; page: PageId; params?: Record<string, string> }
export function alerts(o: Overview): Alert[] {
  const out: Alert[] = [];
  const broken = o.batches.filter((b) => b.status === 'MAPPING_HOLD' || b.status === 'HAS_ERRORS');
  if (broken.length) out.push({ tone: 'warn', title: `정리할 자료 ${broken.length}건`, text: broken.map((b) => `${b.file.name} (${ENTITY_NAME[b.entity]})`).join(', '), page: 'history', params: { kind: 'batch' } });
  if (o.latestPlan) {
    const result = o.latestPlan.result_snapshot;
    const s = result.plans.map((p) => summarizePlan(result, p));
    const short = (x: PlanSummary) => x.plan.label.split(' ')[0];
    const line = (pick: (x: PlanSummary) => number, unit: string) => s.filter((x) => pick(x) > 0).map((x) => `${short(x)} ${pick(x)}${unit}`).join(' · ');
    const add = (tone: Alert['tone'], title: string, pick: (x: PlanSummary) => number, unit: string) => { const text = line(pick, unit); if (text) out.push({ tone, title, text, page: 'plan' }); };
    add('bad', '설비 초과', (x) => x.equipOver, '칸');
    add('bad', '수요 미충족', (x) => x.demandMiss, '건');
    add('warn', '안전 재고 미달', (x) => x.safetyMiss, '건');
    add('warn', '자재 부족', (x) => x.shortages, '건');
    for (const g of groupIssues(result)) out.push({ tone: 'info', title: g.count > 1 ? `${g.text} (${g.count}건)` : g.text, text: '', page: 'plan' });
  }
  return out;
}
