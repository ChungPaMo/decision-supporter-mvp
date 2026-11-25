import { useEffect, useMemo, useRef, useState } from 'react';
import { Empty, failure, FeasSt, forecastLabel, forecastMonths, go, Icon, monthLabel, Name, Notice, num, pctText, shortMonth, when } from '../app/core';
import { demandOf, groupIssues, loadGrid, Names, planMonths, planProducts, PlanResult, PlanSummary, summarizePlan, sumMonth, useLoad } from '../app/data';
import { HeatLegend, LoadMap, Num, ShortLegend, ShortMap } from '../app/widgets';
import { apiClient } from '../services/api';
import { ForecastExecution, ForecastExecutionSummary } from '../types/engine';
import { PlanExecutionDetail, ReceiptPage } from '../types/modules';

const short = (label: string) => label.split(' ')[0];
const basis = (label: string) => label.replace(/^\S+\s*/, '').replace(/[()]/g, '');

type CellPick = { id: string; kind: string; month: string };
const QTY = /^\d+(\.\d+)?$/;
// 계획 계산이 거절되면 서버가 이유를 detail 이 아니라 결과의 errors 에 담아 줄 때가 있다. 둘 다 읽는다.
function planFailure(error: unknown): string {
  const body = error as { result?: { errors?: Array<{ code: string; message: string }> }; execution?: { result_snapshot?: { errors?: Array<{ code: string; message: string }> } } };
  const errors = body?.result?.errors ?? body?.execution?.result_snapshot?.errors ?? [];
  return errors.length ? errors.map((e) => `${e.message} (${e.code})`).join(' · ') : failure(error);
}
// What-if 는 저장된 부모 계획의 입력(command)을 그대로 복사한다. 결과 표에서 범위를 다시 추정하지 않는다.
function parentCommand(e: PlanExecutionDetail) {
  const c = e.input_snapshot?.command;
  return { forecast_execution_id: c?.forecast_execution_id ?? e.forecast_execution_id, product_ids: c?.product_ids ?? planProducts(e.result_snapshot), target_month: c?.target_month ?? e.target_month,
    horizon_months: c?.horizon_months ?? e.horizon_months ?? planMonths(e.result_snapshot).length, as_of_date: c?.as_of_date ?? e.as_of_date };
}

export default function PlanPage({ focus, pick, startMonth, startPlan, names, onChanged }: { focus?: string; pick?: CellPick; startMonth?: string; startPlan?: string; names: Names; onChanged: () => void }) {
  const base = useLoad(async () => {
    const [forecasts, plans, capacity] = await Promise.all([apiClient.forecastHistory(50, 0), apiClient.planExecutions(50, 0), apiClient.approvedData('capacity').catch(() => [] as Array<Record<string, unknown>>)]);
    const budgets: Record<string, { regular: number; overtime: number }> = {};
    for (const row of capacity) if (row.section === 'hours_budgets' && row.resource_id && row.period) budgets[`${String(row.resource_id)}.${String(row.period).slice(0, 7)}`] = { regular: Number(row.regular_hours ?? 0), overtime: Number(row.overtime_hours_limit ?? 0) };
    return { forecasts: forecasts.items.filter((f) => f.status === 'OK' || f.status === 'PARTIAL'), plans: plans.items, budgets };
  });
  const forecasts = base.data?.forecasts ?? [];
  const stored = base.data?.plans ?? [];
  const [forecastId, setForecastId] = useState(focus ?? '');
  const [forecastDetail, setForecastDetail] = useState<ForecastExecution | null>(null);
  const [month, setMonth] = useState(startMonth ?? '');
  const [execution, setExecution] = useState<PlanExecutionDetail | null>(null);
  const [alt, setAlt] = useState<PlanResult | null>(null);
  const [showAlt, setShowAlt] = useState(false);
  const [planId, setPlanId] = useState(startPlan ?? '');
  const [view, setView] = useState<'load' | 'products' | 'materials'>('load');
  const [cell, setCell] = useState<CellPick | null>(null);
  const [pending, setPending] = useState<CellPick | null>(pick ?? null);   // 홈에서 들고 온 칸. 계획이 뜨면 한 번 연다.
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'warn' | 'bad'; text: string } | null>(null);
  const [multiplier, setMultiplier] = useState(1);
  const [overtime, setOvertime] = useState<Record<string, string>>({});
  const [otHours, setOtHours] = useState('40');
  const [span, setSpan] = useState(0);                                       // 0 = 예측이 덮는 마지막 달까지
  const [draft, setDraft] = useState<PlanResult | null>(null);              // 저장하지 않은 미리보기
  const [receipts, setReceipts] = useState<Record<string, string>>({});     // receipt_key → 바꿀 입고 수량
  const [ledger, setLedger] = useState<ReceiptPage | null>(null);
  const [ledgerError, setLedgerError] = useState('');
  const [altKey, setAltKey] = useState('');                                  // 지금 보고 있는 "바꾼 결과"를 만든 조건
  const [savedAlt, setSavedAlt] = useState('');                              // 그 조건으로 저장한 계획 실행

  const forecast: ForecastExecutionSummary | undefined = forecasts.find((f) => f.execution_id === forecastId);
  const months = forecast ? forecastMonths(forecast) : [];
  useEffect(() => { if (!forecastId && forecasts.length) setForecastId(forecasts[0].execution_id); }, [forecasts, forecastId]);
  useEffect(() => { if (months.length && !months.includes(month)) setMonth(months[0]); }, [months, month]);
  // 계획 기간은 시작 달부터 예측이 있는 달까지만 고를 수 있다. 예측이 없는 달을 넣으면 서버가 409 로 거절한다.
  const maxSpan = months.includes(month) ? Math.min(12, months.length - months.indexOf(month)) : 0;
  const horizon = span && span <= maxSpan ? span : maxSpan;
  useEffect(() => { setForecastDetail(null); if (forecastId) void apiClient.getForecast(forecastId).then(setForecastDetail).catch(() => undefined); }, [forecastId]);

  const adopt = (detail: PlanExecutionDetail) => {
    setExecution(detail); setDraft(null); setAlt(null); setShowAlt(false); setOvertime({}); setReceipts({}); setSavedAlt(''); setAltKey(''); setMultiplier(1); setCell(null);
    const plans = detail.result_snapshot.plans;
    setPlanId((id) => (plans.some((p) => p.plan_id === id) ? id : (plans.find((p) => p.feasibility !== 'INFEASIBLE') ?? plans[0])?.plan_id ?? ''));
  };
  // 같은 예측·같은 달로 저장된 계획이 있으면 다시 계산하지 않고 불러온다.
  useEffect(() => {
    if (!forecastId || !month || !horizon) return;
    const found = stored.find((p) => p.forecast_execution_id === forecastId && p.target_month === month && (p.horizon_months === undefined || p.horizon_months === horizon) && p.scenario_type === 'BASE' && p.status !== 'FAILED');
    setDraft(null);
    if (!found) { setExecution(null); setAlt(null); return; }
    if (found.execution_id === execution?.execution_id) return;
    void apiClient.getPlanExecution(found.execution_id).then(adopt).catch((e) => setMessage({ tone: 'bad', text: failure(e) }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forecastId, month, horizon, stored]);

  // 기준 계획의 요청. 기간(horizon_months)을 항상 명시한다.
  async function command() {
    const detail = forecastDetail ?? await apiClient.getForecast(forecast!.execution_id);
    const products = [...new Set((detail.result?.forecasts ?? []).map((r) => r.product_id))].sort();
    return { forecast_execution_id: forecast!.execution_id, product_ids: products, target_month: month, horizon_months: horizon, as_of_date: forecast!.parameters.trained_until };
  }
  async function calculate() {
    if (!forecast || !horizon) return;
    setBusy(true); setMessage(null);
    try {
      const reply = await apiClient.createPlanExecution({ ...(await command()), scenario: 'BASE' });
      adopt(reply.execution);
      setMessage({ tone: 'ok', text: reply.reused ? '같은 조건으로 저장된 계획을 불러왔습니다.' : '계획을 계산해 저장했습니다.' });
      await base.reload(); onChanged();
    } catch (error) { setMessage({ tone: 'bad', text: planFailure(error) }); }
    finally { setBusy(false); }
  }
  // 저장하지 않고 결과만 본다. 기록에 남지 않는다.
  async function preview() {
    if (!forecast || !horizon) return;
    setBusy(true); setMessage(null);
    try {
      const reply = await apiClient.planPreview(await command());
      setDraft(reply.result); setCell(null);
      setPlanId((id) => (reply.result.plans.some((p) => p.plan_id === id) ? id : (reply.result.plans.find((p) => p.feasibility !== 'INFEASIBLE') ?? reply.result.plans[0])?.plan_id ?? ''));
      setMessage({ tone: 'warn', text: '저장하지 않은 미리보기입니다. 기록에 남기거나 조건을 바꿔 비교하려면 "계획 계산하기"를 누르세요.' });
    } catch (error) { setMessage({ tone: 'bad', text: planFailure(error) }); }
    finally { setBusy(false); }
  }

  const overrides = useMemo(() => ({ ...(multiplier !== 1 ? { demand_multiplier: multiplier.toFixed(2) } : {}), ...overtime,
    ...Object.fromEntries(Object.entries(receipts).filter(([, v]) => QTY.test(v)).map(([k, v]) => [`receipt_qty.${k}`, v])) }), [multiplier, overtime, receipts]);
  const overridesKey = JSON.stringify(overrides);
  async function recalc() {
    if (!execution) return;
    setBusy(true); setMessage(null);
    try {
      const reply = await apiClient.whatIf({ ...parentCommand(execution), base_plan_execution_id: execution.execution_id }, overrides);
      setAlt(reply.result); setShowAlt(true); setAltKey(overridesKey); setSavedAlt('');
    } catch (error) { setMessage({ tone: 'bad', text: planFailure(error) }); }
    finally { setBusy(false); }
  }
  // 비교해 본 조건을 그대로 저장한다. 부모(원래 계획)는 바뀌지 않고, 조건을 바꾼 계획이 기록에 따로 남는다.
  async function saveAlt() {
    if (!execution || !alt || altKey !== overridesKey) return;
    setBusy(true); setMessage(null);
    try {
      const reply = await apiClient.createPlanExecution({ ...parentCommand(execution), scenario: 'WHAT_IF', base_plan_execution_id: execution.execution_id, overrides });
      setSavedAlt(reply.execution.execution_id);
      setMessage({ tone: 'ok', text: reply.reused ? '같은 조건으로 이미 저장된 계획이 있습니다. 기록에서 볼 수 있습니다.' : '조건을 바꾼 계획을 저장했습니다. 기록에서 볼 수 있습니다.' });
      await base.reload(); onChanged();
    } catch (error) { setMessage({ tone: 'bad', text: planFailure(error) }); }
    finally { setBusy(false); }
  }
  const resetWhatIf = () => { setMultiplier(1); setOvertime({}); setReceipts({}); setAlt(null); setShowAlt(false); setAltKey(''); setSavedAlt(''); };
  // 원래 계획의 기준일까지 승인된 예정 입고. 발주별 입고 수량을 바꿔 볼 때 쓴다.
  useEffect(() => {
    setLedger(null); setLedgerError('');
    if (!execution) return;
    let live = true;
    void apiClient.scheduledReceipts(execution.as_of_date).then((page) => { if (live) setLedger(page); }).catch((e) => { if (live) setLedgerError(failure(e)); });
    return () => { live = false; };
  }, [execution?.execution_id]);
  const openReceipts = ledger?.source_state === 'AVAILABLE' ? ledger.items.filter((r) => r.state === 'OPEN' || r.state === 'PARTIALLY_RECEIVED') : [];

  const baseResult = execution?.result_snapshot ?? draft;
  const result = showAlt && alt ? alt : baseResult;
  const summaries = useMemo(() => (result ? result.plans.map((p) => summarizePlan(result, p)) : []), [result]);
  const baseSummaries = useMemo(() => (baseResult ? baseResult.plans.map((p) => summarizePlan(baseResult, p)) : []), [baseResult]);
  const altSummaries = useMemo(() => (alt ? alt.plans.map((p) => summarizePlan(alt, p)) : []), [alt]);
  const selected = summaries.find((s) => s.plan.plan_id === planId) ?? summaries[0];
  const viewMonths = result ? planMonths(result) : [];
  const products = result ? planProducts(result) : [];
  const issues = result ? groupIssues(result) : [];
  const grid = useMemo(() => (result && selected ? loadGrid(result, selected.plan.plan_id) : null), [result, selected]);
  const fdemand = useMemo(() => demandOf(forecastDetail), [forecastDetail]);
  const factor = showAlt && alt ? multiplier : 1;       // 조건을 바꾼 결과를 볼 때는 수요도 같은 배수로 견준다
  const demandTotal = viewMonths.reduce((a, m) => a + sumMonth(fdemand[m]) * factor, 0);
  const qty = (pid: string, m: string) => Number(selected?.plan.production.find((r) => r.product_id === pid && r.period === m)?.production_qty ?? 0);
  const picked = cell && grid ? grid.rows.find((r) => r.id === cell.id && r.kind === cell.kind)?.cells[cell.month] : null;
  const sortedRows = useMemo(() => [...(grid?.rows ?? [])].sort((x, y) => Math.max(...Object.values(y.cells).map((c) => c.pct ?? 0)) - Math.max(...Object.values(x.cells).map((c) => c.pct ?? 0))), [grid]);
  const noticeRef = useRef<HTMLDivElement>(null);
  // 홈에서 칸을 들고 왔으면 그 칸을 열고, 잔업 한도를 바꾸는 자리가 보이게 내려간다.
  const arrived = useRef(false);
  useEffect(() => {
    if (!pending || cell || !grid?.rows.some((r) => r.id === pending.id && r.kind === pending.kind && r.cells[pending.month])) return;
    setCell(pending); setView('load');
    if (!arrived.current) { arrived.current = true; window.setTimeout(() => noticeRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 120); }
  }, [pending, grid, cell]);
  // 조건을 바꾼 결과를 볼 때, 같은 칸의 원래 한도를 함께 보여 주기 위한 원래 계획의 부하.
  const baseGrid = useMemo(() => (showAlt && alt && baseResult && selected ? loadGrid(baseResult, selected.plan.plan_id) : null), [showAlt, alt, baseResult, selected]);
  const basePicked = cell && baseGrid ? baseGrid.rows.find((r) => r.id === cell.id && r.kind === cell.kind)?.cells[cell.month] : null;
  const otKey = cell ? `overtime_hours_limit.${cell.id}.${cell.month}` : '';
  const budget = cell ? base.data?.budgets[`${cell.id}.${cell.month}`] : undefined;
  // 칸을 고르면 입력값을 그 칸의 지금 잔업 한도보다 40시간 많게 맞춰 둔다. 같은 값을 넣어 아무 변화가 없는 일을 막는다.
  useEffect(() => { if (budget && !overtime[otKey]) setOtHours(String(budget.overtime + 40)); }, [cell?.id, cell?.month, budget?.overtime]);
  const overrideText = Object.entries(overrides).map(([k, v]) => (k === 'demand_multiplier' ? `수요 ×${v}` : k.startsWith('receipt_qty.') ? `발주 ${k.slice('receipt_qty.'.length)} 입고 ${num(v, 3)}` : `${names[k.split('.')[1]] ?? k.split('.')[1]} ${shortMonth(k.split('.')[2])} 잔업 한도 ${v}시간`)).join(', ');

  const fact = (label: string, v: number, unit: string) => <span className={`fact${v ? ' bad' : ''}`}>{label} <b>{v ? `${v}${unit}` : '없음'}</b></span>;

  return <>
    <section className="panel"><div className="body">
      {forecasts.length === 0 ? <Empty action={<button type="button" className="btn primary sm" onClick={() => go('forecast')}>수요 예측하러 가기</button>}>{base.loading ? '읽는 중…' : '먼저 수요 예측을 실행해야 합니다.'}</Empty> :
        <div className="formrow">
          <label className="field" style={{ flex: '2 1 300px' }}>어떤 예측으로 계획을 세울까요<select value={forecastId} onChange={(e) => setForecastId(e.target.value)}>{forecasts.map((f) => <option key={f.execution_id} value={f.execution_id}>{forecastLabel(f)} · {when(f.created_at)} 실행</option>)}</select></label>
          <div className="field" style={{ flex: '2 1 260px' }}>계획을 시작할 달 <div className="chips">{months.map((m) => <button key={m} type="button" className="chip" aria-pressed={m === month} onClick={() => setMonth(m)}>{monthLabel(m)}</button>)}</div></div>
          <label className="field" style={{ flex: '0 1 120px' }}>계획 기간<select value={horizon} disabled={!maxSpan} onChange={(e) => setSpan(Number(e.target.value))}>{Array.from({ length: maxSpan }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}개월</option>)}</select></label>
          {!execution && <button type="button" className="btn lg" disabled={busy || !forecast || !horizon} title="저장하지 않고 결과만 봅니다" onClick={() => void preview()}>미리보기</button>}
          <button type="button" className={`btn lg${execution ? '' : ' primary'}`} disabled={busy || !forecast || !horizon} onClick={() => void calculate()}>{busy ? '계산 중…' : execution ? '저장된 계획 다시 계산' : '계획 계산하기'}<Icon name="play" /></button>
        </div>}
      {forecast && <p className="small">{monthLabel(forecast.parameters.trained_until.slice(0, 7))} 말까지의 자료로 만든 예측입니다. 계획도 그 시점에 알고 있던 재고만 씁니다.{execution ? ` 이 계획은 ${monthLabel(execution.target_month)}부터 ${parentCommand(execution).horizon_months}개월 치이며 ${when(execution.created_at)} 저장됐습니다.` : draft ? ' 지금 보이는 결과는 저장하지 않은 미리보기입니다.' : horizon ? ` ${monthLabel(month)}부터 ${horizon}개월 치를 계산합니다.` : ''}</p>}
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
      {base.error && <Notice tone="bad">{base.error}</Notice>}
    </div></section>

    {!result ? <section className="panel"><Empty>{forecast ? '"계획 계산"을 누르면 세 안과 설비 부하 지도가 나옵니다.' : '예측을 고르세요.'}</Empty></section> : <>
      {issues.map((g) => <Notice key={g.code} tone={g.level}><Icon name="alert" /><span>{g.text}{g.count > 1 && <b> ({g.count}건{g.refs.length ? `: ${g.refs.slice(0, 5).map((r) => names[r] ?? r).join(', ')}${g.refs.length > 5 ? ' 외' : ''}` : ''})</b>}</span></Notice>)}

      <div className="cols c31">
        <div className="stack">
          <div className="plans" role="group" aria-label="세 안">{summaries.map((s) => { const cover = demandTotal ? (s.total / demandTotal) * 100 : null;
            return <button type="button" key={s.plan.plan_id} className={`plan${s.plan.plan_id === selected?.plan.plan_id ? ' selected' : ''}`} aria-pressed={s.plan.plan_id === selected?.plan.plan_id} onClick={() => { setPlanId(s.plan.plan_id); setPending(null); setCell(null); }}>
              <div className="top"><b>{short(s.plan.label)}</b><FeasSt value={s.plan.feasibility} /></div>
              <span className="total num"><Num value={s.total} /> <small>EA</small></span><span className="small muted">{basis(s.plan.label)} · 수요의 {pctText(cover)}</span>
              <div className="facts">{s.maxUtil !== null && <span className={`fact${s.maxUtil >= 0.995 ? ' bad' : s.maxUtil >= 0.9 ? ' warn' : ''}`}>최대 부하 <b>{pctText(s.maxUtil * 100)}</b></span>}
                {fact('설비 초과', s.equipOver, '칸')}{fact('수요 미충족', s.demandMiss, '건')}{fact('안전 재고 미달', s.safetyMiss, '건')}{fact('자재 부족', s.shortages, '건')}</div>
            </button>; })}</div>

          <div className="tabs" role="group" aria-label="자세히 볼 것" style={{ alignSelf: 'flex-start' }}><button type="button" aria-pressed={view === 'load'} onClick={() => setView('load')}>설비·인력 부하</button><button type="button" aria-pressed={view === 'products'} onClick={() => setView('products')}>제품별 생산량</button><button type="button" aria-pressed={view === 'materials'} onClick={() => setView('materials')}>자재 부족{selected?.shortages ? ` ${selected.shortages}` : ''}</button></div>

          {view === 'load' && <section className="panel"><header><div><h2>설비·인력 부하 지도 · {selected ? short(selected.plan.label) : ''}</h2><p>달마다 한도의 몇 %를 쓰는지, 빠듯한 순서입니다. 칸을 누르면 그 칸의 잔업 한도를 바꿀 수 있습니다.</p></div><HeatLegend /></header>
            <div className="body bare">{grid && <LoadMap months={grid.months} rows={sortedRows} names={names} selected={cell} onPick={(next) => { setPending(null); setCell(next); }} />}
              {cell && picked && <div ref={noticeRef}><Notice tone={picked.pct !== null && picked.pct >= 99.5 ? 'bad' : picked.pct !== null && picked.pct >= 90 ? 'warn' : 'info'}>
                <span><b>{names[cell.id] ?? cell.id} · {monthLabel(cell.month)}</b> — {picked.limit === null ? `필요 ${num(picked.used, 1)}${picked.unit}, 한도 자료가 없습니다.` : `필요 ${num(picked.used, 1)}${picked.unit} / 한도 ${num(picked.limit, 0)}${picked.unit}. ${picked.used > picked.limit ? `${num(picked.used - picked.limit, 1)}${picked.unit} 모자랍니다.` : `여유 ${num(picked.limit - picked.used, 1)}${picked.unit}.`}`}
                  {budget && ` 정규 ${num(budget.regular, 0)}시간 + 잔업 한도 ${num(budget.overtime, 0)}시간.`}{' '}{overtime[otKey] ? <><b>잔업 한도를 {budget ? `${num(budget.overtime, 0)}시간에서 ` : ''}{overtime[otKey]}시간으로 바꿨습니다.</b>{basePicked && basePicked.limit !== null && picked.limit !== null && basePicked.limit !== picked.limit && ` 전체 한도 ${num(basePicked.limit, 0)}${picked.unit} → ${num(picked.limit, 0)}${picked.unit}.`} <button type="button" className="btn sm" onClick={() => { const rest = { ...overtime }; delete rest[otKey]; setOvertime(rest); }}>되돌리기</button></>
                    : <button type="button" className="btn sm" onClick={() => { setOvertime({ ...overtime, [otKey]: String(Number(otHours) || 0) }); }}>이 칸의 잔업 한도를 {otHours}시간으로</button>}</span></Notice></div>}</div>
          </section>}

          {view === 'products' && <section className="panel"><header><div><h2>제품별 생산량 · {selected ? short(selected.plan.label) : ''}</h2><p>칸 아래 막대는 예상 수요에 비해 얼마나 만드는지입니다 (가득 차면 수요만큼)</p></div></header>
            <div className="body flush"><div className="tablewrap"><table className="tbl"><thead><tr><th>제품</th>{viewMonths.map((m) => <th key={m} className="r">{monthLabel(m)}</th>)}<th className="r">합계</th><th className="r">수요 대비</th></tr></thead>
              <tbody>{products.map((pid) => { let sum = 0, need = 0;
                return <tr key={pid}><td><Name code={pid} names={names} /></td>{viewMonths.map((m) => { const q = qty(pid, m), d = (fdemand[m]?.[pid]?.p50 ?? 0) * factor; sum += q; need += d; const ratio = d ? q / d : null;
                  return <td key={m} className="r num">{num(q)}<span className={`cellbar ${ratio !== null && Math.round(ratio * 100) < 95 ? 'over' : ''}`} title={d ? `예상 수요 ${num(d)}` : undefined}><i style={{ width: `${Math.min((ratio ?? 0) * 100, 100)}%` }} /></span></td>; })}
                  <td className="r num"><b>{num(sum)}</b></td><td className="r num" style={need && Math.round((sum / need) * 100) < 95 ? { color: 'var(--bad)', fontWeight: 600 } : undefined}>{need ? pctText((sum / need) * 100) : '-'}</td></tr>; })}</tbody>
              <tfoot><tr><td>합계</td>{viewMonths.map((m) => <td key={m} className="r num">{num(selected?.byMonth[m] ?? 0)}</td>)}<td className="r num">{num(selected?.total ?? 0)}</td><td className="r num">{demandTotal ? pctText(((selected?.total ?? 0) / demandTotal) * 100) : '-'}</td></tr></tfoot></table></div></div>
          </section>}

          {view === 'materials' && <section className="panel"><header><div><h2>자재 부족 지도 · {selected ? short(selected.plan.label) : ''}</h2><p>칸이 진할수록 필요한 양에 비해 많이 모자랍니다. 많이 모자라는 자재가 위에 옵니다.</p></div><ShortLegend /></header>
            <div className="body bare">{selected?.shortageList.length ? <ShortMap months={viewMonths} list={selected.shortageList} names={names} /> : <Empty>이 안에서는 모자라는 자재가 없습니다.</Empty>}</div>
          </section>}
        </div>

        <div className="stack sticky">
          <section className="panel"><header><div><h2>조건 바꿔 다시 계산</h2><p>먼저 저장 없이 비교하고, 남길 결과만 저장합니다</p></div></header>
            <div className="body">
              {!execution && <Notice tone="warn">미리보기는 저장된 계획이 아니라 조건을 바꿔 비교할 수 없습니다. "계획 계산하기"로 저장한 뒤 쓰세요.</Notice>}
              <label className="field">수요를 몇 배로 볼까요 <b className="num" style={{ color: 'var(--ink)', fontSize: '0.9rem' }}>×{multiplier.toFixed(2)}{multiplier !== 1 && ` (${multiplier > 1 ? '+' : ''}${Math.round((multiplier - 1) * 100)}%)`}</b>
                <input type="range" min="0.7" max="1.4" step="0.05" value={multiplier} onChange={(e) => setMultiplier(Number(e.target.value))} /></label>
              <div className="formrow"><label className="field">바꿀 잔업 한도 (시간)<input type="number" min="0" step="10" value={otHours} onChange={(e) => setOtHours(e.target.value)} /></label>
                <span className="small muted" style={{ flex: '2 1 150px' }}>부하 지도의 칸을 누르면 그 설비·달의 잔업 한도를 이 값으로 바꿉니다. 원래 잔업 한도에 더하는 것이 아니라 대신합니다.</span></div>
              {Object.keys(overtime).length > 0 && <div className="chips">{Object.entries(overtime).map(([k, v]) => <button key={k} type="button" className="chip" title="눌러서 빼기" onClick={() => { const next = { ...overtime }; delete next[k]; setOvertime(next); }}>{names[k.split('.')[1]] ?? k.split('.')[1]} {shortMonth(k.split('.')[2])} 잔업 한도 {v}h<Icon name="x" /></button>)}</div>}
              <h3>발주별 입고 수량</h3>
              {ledgerError ? <Notice tone="bad">{ledgerError}</Notice> : !execution ? null : !ledger ? <p className="small muted">예정 입고를 읽는 중…</p>
                : ledger.source_state === 'UNAVAILABLE' ? <p className="small muted">예정 입고 원장이 아직 연결되지 않았습니다 ({ledger.reason_code}).</p>
                : openReceipts.length === 0 ? <p className="small muted">{monthLabel(ledger.as_of_date.slice(0, 7))} 말까지 승인된 예정 입고 중 아직 들어올 발주가 없습니다. "자료 넣기"에서 예정 입고 파일을 승인하면 여기서 발주별 수량을 바꿔 볼 수 있습니다.</p>
                : <><div className="tablewrap scrollbox" style={{ maxHeight: 220 }}><table className="tbl tight"><thead><tr><th>발주</th><th>자재</th><th>입고 예정</th><th className="r">남은 수량</th><th className="r">바꿀 수량</th></tr></thead>
                    <tbody>{openReceipts.map((r) => <tr key={r.receipt_key}><td className="small nw">{r.receipt_key}</td><td className="small">{names[r.material_id] ?? r.material_id}</td><td className="small nw">{r.expected_date}</td><td className="r num small">{num(r.open_qty, 3)} {r.unit}</td>
                      <td className="r"><input type="number" min="0" step="any" style={{ width: 96 }} aria-label={`${r.receipt_key} 바꿀 입고 수량`} placeholder={String(Number(r.open_qty))} value={receipts[r.receipt_key] ?? ''} onChange={(e) => { const next = { ...receipts }; if (e.target.value === '') delete next[r.receipt_key]; else next[r.receipt_key] = e.target.value; setReceipts(next); }} /></td></tr>)}</tbody></table></div>
                  <p className="small muted">비워 두면 원래 수량 그대로입니다. 0을 넣으면 그 발주가 들어오지 않는 것으로 계산합니다. 원래 계획을 만들 때 쓰이지 않은 발주는 서버가 거절합니다.</p></>}
              <div className="actions"><button type="button" className="btn primary lg" disabled={busy || !execution || !Object.keys(overrides).length} onClick={() => void recalc()}><Icon name="refresh" />{busy ? '계산 중…' : '이 조건으로 다시 계산'}</button>
                {alt && <button type="button" className="btn" disabled={busy || !!savedAlt || altKey !== overridesKey} title={altKey !== overridesKey ? '조건이 바뀌었습니다. 다시 계산한 뒤 저장하세요.' : undefined} onClick={() => void saveAlt()}>{savedAlt ? '저장됨' : '바꾼 결과 저장'}</button>}
                {savedAlt && <button type="button" className="btn" onClick={() => go('history', { kind: 'plan', x: savedAlt })}>기록에서 보기</button>}
                <button type="button" className="btn" disabled={busy || (!alt && !Object.keys(overrides).length)} onClick={resetWhatIf}>처음으로</button></div>
              {alt && <><div className="tabs" role="group" aria-label="볼 결과"><button type="button" aria-pressed={!showAlt} onClick={() => setShowAlt(false)}>원래 계획</button><button type="button" aria-pressed={showAlt} onClick={() => setShowAlt(true)}>바꾼 결과</button></div>
                <p className="small">{showAlt ? `왼쪽 화면이 바꾼 결과를 보여 줍니다: ${overrideText}` : '왼쪽 화면이 저장된 원래 계획을 보여 줍니다.'}</p></>}
            </div>
          </section>

          {alt && <section className="panel"><header><h2>바꾸기 전 → 후</h2></header>
            <div className="body flush"><table className="tbl tight"><thead><tr><th>안</th><th className="r">생산 합계</th><th>실행 가능성</th></tr></thead>
              <tbody>{baseSummaries.map((b) => { const a = altSummaries.find((s) => s.plan.plan_id === b.plan.plan_id); if (!a) return null; const diff = a.total - b.total;
                return <tr key={b.plan.plan_id}><td><b>{short(b.plan.label)}</b></td><td className="r num">{num(a.total)}<br /><span className="small muted">{diff > 0 ? '+' : ''}{num(diff)}</span></td>
                  <td><FeasSt value={b.plan.feasibility} /><br /><span className="small muted">→ </span><FeasSt value={a.plan.feasibility} /></td></tr>; })}</tbody></table>
              <table className="tbl tight"><thead><tr><th>달라진 것</th>{baseSummaries.map((b) => <th key={b.plan.plan_id} className="r">{short(b.plan.label)}</th>)}</tr></thead>
                <tbody>{([['설비 초과', (x: PlanSummary) => x.equipOver], ['수요 미충족', (x: PlanSummary) => x.demandMiss], ['안전 재고 미달', (x: PlanSummary) => x.safetyMiss], ['자재 부족', (x: PlanSummary) => x.shortages]] as Array<[string, (x: PlanSummary) => number]>).map(([label, pick]) =>
                  <tr key={label}><td>{label}</td>{baseSummaries.map((b) => { const a = altSummaries.find((s) => s.plan.plan_id === b.plan.plan_id); const before = pick(b), after = a ? pick(a) : before;
                    return <td key={b.plan.plan_id} className={`r num${after === before ? ' same' : ''}`}>{before}→<b className={after > before ? 'delta-up' : after < before ? 'delta-down' : ''}>{after}</b></td>; })}</tr>)}</tbody></table></div>
          </section>}
        </div>
      </div>
    </>}
  </>;
}
