import { useEffect, useMemo, useState } from 'react';
import { Empty, failure, FeasSt, forecastLabel, forecastMonths, go, Icon, monthLabel, Name, Notice, num, pctText, shortMonth, Tag, when } from '../app/core';
import { demandOf, groupIssues, loadGrid, Names, planMonths, planProducts, PlanResult, PlanSummary, summarizePlan, sumMonth, useLoad } from '../app/data';
import { HeatLegend, LoadMap, ShortLegend, ShortMap } from '../app/widgets';
import { apiClient } from '../services/api';
import { ForecastExecution, ForecastExecutionSummary } from '../types/engine';
import { PlanExecutionDetail } from '../types/modules';

const short = (label: string) => label.split(' ')[0];
const basis = (label: string) => label.replace(/^\S+\s*/, '').replace(/[()]/g, '');

export default function PlanPage({ focus, names, onChanged }: { focus?: string; names: Names; onChanged: () => void }) {
  const base = useLoad(async () => {
    const [forecasts, plans] = await Promise.all([apiClient.forecastHistory(50, 0), apiClient.planExecutions(50, 0)]);
    return { forecasts: forecasts.items.filter((f) => f.status === 'OK' || f.status === 'PARTIAL'), plans: plans.items };
  });
  const forecasts = base.data?.forecasts ?? [];
  const stored = base.data?.plans ?? [];
  const [forecastId, setForecastId] = useState(focus ?? '');
  const [forecastDetail, setForecastDetail] = useState<ForecastExecution | null>(null);
  const [month, setMonth] = useState('');
  const [execution, setExecution] = useState<PlanExecutionDetail | null>(null);
  const [alt, setAlt] = useState<PlanResult | null>(null);
  const [showAlt, setShowAlt] = useState(false);
  const [planId, setPlanId] = useState('');
  const [view, setView] = useState<'load' | 'products' | 'materials'>('load');
  const [cell, setCell] = useState<{ id: string; kind: string; month: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'warn' | 'bad'; text: string } | null>(null);
  const [multiplier, setMultiplier] = useState(1);
  const [overtime, setOvertime] = useState<Record<string, string>>({});
  const [otHours, setOtHours] = useState('40');

  const forecast: ForecastExecutionSummary | undefined = forecasts.find((f) => f.execution_id === forecastId);
  const months = forecast ? forecastMonths(forecast) : [];
  useEffect(() => { if (!forecastId && forecasts.length) setForecastId(forecasts[0].execution_id); }, [forecasts, forecastId]);
  useEffect(() => { if (months.length && !months.includes(month)) setMonth(months[0]); }, [months, month]);
  useEffect(() => { setForecastDetail(null); if (forecastId) void apiClient.getForecast(forecastId).then(setForecastDetail).catch(() => undefined); }, [forecastId]);

  const adopt = (detail: PlanExecutionDetail) => {
    setExecution(detail); setAlt(null); setShowAlt(false); setOvertime({}); setMultiplier(1); setCell(null);
    const plans = detail.result_snapshot.plans;
    setPlanId((id) => (plans.some((p) => p.plan_id === id) ? id : (plans.find((p) => p.feasibility !== 'INFEASIBLE') ?? plans[0])?.plan_id ?? ''));
  };
  // 같은 예측·같은 달로 저장된 계획이 있으면 다시 계산하지 않고 불러온다.
  useEffect(() => {
    if (!forecastId || !month) return;
    const found = stored.find((p) => p.forecast_execution_id === forecastId && p.target_month === month && p.scenario_type === 'BASE' && p.status !== 'FAILED');
    if (!found) { setExecution(null); setAlt(null); return; }
    if (found.execution_id === execution?.execution_id) return;
    void apiClient.getPlanExecution(found.execution_id).then(adopt).catch((e) => setMessage({ tone: 'bad', text: failure(e) }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forecastId, month, stored]);

  async function calculate() {
    if (!forecast) return;
    setBusy(true); setMessage(null);
    try {
      const detail = forecastDetail ?? await apiClient.getForecast(forecast.execution_id);
      const products = [...new Set((detail.result?.forecasts ?? []).map((r) => r.product_id))].sort();
      const reply = await apiClient.createPlanExecution({ forecast_execution_id: forecast.execution_id, product_ids: products, target_month: month, as_of_date: forecast.parameters.trained_until, scenario: 'BASE' });
      adopt(reply.execution);
      setMessage({ tone: 'ok', text: reply.reused ? '같은 조건으로 저장된 계획을 불러왔습니다.' : '계획을 계산해 저장했습니다.' });
      await base.reload(); onChanged();
    } catch (error) { setMessage({ tone: 'bad', text: failure(error) }); }
    finally { setBusy(false); }
  }

  const overrides = useMemo(() => ({ ...(multiplier !== 1 ? { demand_multiplier: multiplier.toFixed(2) } : {}), ...overtime }), [multiplier, overtime]);
  async function recalc() {
    if (!execution) return;
    setBusy(true); setMessage(null);
    try {
      const reply = await apiClient.whatIf({ forecast_execution_id: execution.forecast_execution_id, product_ids: planProducts(execution.result_snapshot), target_month: execution.target_month, as_of_date: execution.as_of_date, base_plan_execution_id: execution.execution_id }, overrides);
      setAlt(reply.result); setShowAlt(true);
    } catch (error) { setMessage({ tone: 'bad', text: failure(error) }); }
    finally { setBusy(false); }
  }
  const resetWhatIf = () => { setMultiplier(1); setOvertime({}); setAlt(null); setShowAlt(false); };

  const baseResult = execution?.result_snapshot ?? null;
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
  const overrideText = Object.entries(overrides).map(([k, v]) => (k === 'demand_multiplier' ? `수요 ×${v}` : `${names[k.split('.')[1]] ?? k.split('.')[1]} ${shortMonth(k.split('.')[2])} 잔업 ${v}시간`)).join(', ');

  const fact = (label: string, v: number, unit: string) => <span className={`fact${v ? ' bad' : ''}`}>{label} <b>{v ? `${v}${unit}` : '없음'}</b></span>;

  return <>
    <section className="panel"><div className="body">
      {forecasts.length === 0 ? <Empty action={<button type="button" className="btn primary sm" onClick={() => go('forecast')}>수요 예측하러 가기</button>}>{base.loading ? '읽는 중…' : '먼저 수요 예측을 실행해야 합니다.'}</Empty> :
        <div className="formrow">
          <label className="field" style={{ flex: '2 1 300px' }}>어떤 예측으로 계획을 세울까요<select value={forecastId} onChange={(e) => setForecastId(e.target.value)}>{forecasts.map((f) => <option key={f.execution_id} value={f.execution_id}>{forecastLabel(f)} · {when(f.created_at)} 실행</option>)}</select></label>
          <div className="field" style={{ flex: '2 1 260px' }}>계획을 시작할 달 <div className="chips">{months.map((m) => <button key={m} type="button" className="chip" aria-pressed={m === month} onClick={() => setMonth(m)}>{monthLabel(m)}</button>)}</div></div>
          <button type="button" className="btn primary lg" disabled={busy || !forecast || !month} onClick={() => void calculate()}>{busy ? '계산 중…' : execution ? '다시 계산' : '계획 계산하기'}<Icon name="play" /></button>
        </div>}
      {forecast && <p className="small">{monthLabel(forecast.parameters.trained_until.slice(0, 7))} 말까지의 자료로 만든 예측입니다. 계획도 그 시점에 알고 있던 재고만 씁니다.{execution && ` 이 계획은 ${when(execution.created_at)} 저장됐습니다.`}</p>}
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
      {base.error && <Notice tone="bad">{base.error}</Notice>}
    </div></section>

    {!result ? <section className="panel"><Empty>{forecast ? '"계획 계산"을 누르면 세 안과 설비 부하 지도가 나옵니다.' : '예측을 고르세요.'}</Empty></section> : <>
      {issues.map((g) => <Notice key={g.code} tone={g.level}><Icon name="alert" /><span>{g.text}{g.count > 1 && <b> ({g.count}건{g.refs.length ? `: ${g.refs.slice(0, 5).map((r) => names[r] ?? r).join(', ')}${g.refs.length > 5 ? ' 외' : ''}` : ''})</b>}</span></Notice>)}

      <div className="cols c31">
        <div className="stack">
          <div className="plans" role="group" aria-label="세 안">{summaries.map((s) => { const cover = demandTotal ? (s.total / demandTotal) * 100 : null;
            return <button type="button" key={s.plan.plan_id} className={`plan${s.plan.plan_id === selected?.plan.plan_id ? ' selected' : ''}`} aria-pressed={s.plan.plan_id === selected?.plan.plan_id} onClick={() => { setPlanId(s.plan.plan_id); setCell(null); }}>
              <div className="top"><b>{short(s.plan.label)}</b><FeasSt value={s.plan.feasibility} /></div>
              <span className="total num">{num(s.total)} <small>EA</small></span><span className="small muted">{basis(s.plan.label)} · 수요의 {pctText(cover)}</span>
              <div className="facts">{s.maxUtil !== null && <span className={`fact${s.maxUtil > 1 ? ' bad' : s.maxUtil >= 0.9 ? ' warn' : ''}`}>최대 부하 <b>{pctText(s.maxUtil * 100)}</b></span>}
                {fact('설비 초과', s.equipOver, '칸')}{fact('수요 미충족', s.demandMiss, '건')}{fact('안전 재고 미달', s.safetyMiss, '건')}{fact('자재 부족', s.shortages, '건')}</div>
            </button>; })}</div>

          <div className="tabs" role="group" aria-label="자세히 볼 것" style={{ alignSelf: 'flex-start' }}><button type="button" aria-pressed={view === 'load'} onClick={() => setView('load')}>설비·인력 부하</button><button type="button" aria-pressed={view === 'products'} onClick={() => setView('products')}>제품별 생산량</button><button type="button" aria-pressed={view === 'materials'} onClick={() => setView('materials')}>자재 부족{selected?.shortages ? ` ${selected.shortages}` : ''}</button></div>

          {view === 'load' && <section className="panel"><header><div><h2>설비·인력 부하 지도 · {selected ? short(selected.plan.label) : ''}</h2><p>달마다 한도의 몇 %를 쓰는지. 칸을 누르면 자세히 봅니다.</p></div><HeatLegend /></header>
            <div className="body">{grid && <LoadMap months={grid.months} rows={grid.rows} names={names} selected={cell} onPick={setCell} />}
              {cell && picked && <Notice tone={picked.pct !== null && picked.pct > 100 ? 'bad' : picked.pct !== null && picked.pct >= 90 ? 'warn' : 'info'}>
                <span><b>{names[cell.id] ?? cell.id} · {monthLabel(cell.month)}</b> — {picked.limit === null ? `필요 ${num(picked.used, 1)}${picked.unit}, 한도 자료가 없습니다.` : `필요 ${num(picked.used, 1)}${picked.unit} / 한도 ${num(picked.limit, 0)}${picked.unit}. ${picked.used > picked.limit ? `${num(picked.used - picked.limit, 1)}${picked.unit} 모자랍니다.` : `여유 ${num(picked.limit - picked.used, 1)}${picked.unit}.`}`}
                  {' '}<button type="button" className="btn sm" onClick={() => { setOvertime({ ...overtime, [`overtime_hours_limit.${cell.id}.${cell.month}`]: String(Number(otHours) || 0) }); }}>이 칸에 잔업 {otHours}시간 넣기</button></span></Notice>}</div>
          </section>}

          {view === 'products' && <section className="panel"><header><div><h2>제품별 생산량 · {selected ? short(selected.plan.label) : ''}</h2><p>칸 아래 막대는 예상 수요에 비해 얼마나 만드는지입니다 (가득 차면 수요만큼)</p></div></header>
            <div className="body flush"><div className="tablewrap"><table className="tbl"><thead><tr><th>제품</th>{viewMonths.map((m) => <th key={m} className="r">{monthLabel(m)}</th>)}<th className="r">합계</th><th className="r">수요 대비</th></tr></thead>
              <tbody>{products.map((pid) => { let sum = 0, need = 0;
                return <tr key={pid}><td><Name code={pid} names={names} /></td>{viewMonths.map((m) => { const q = qty(pid, m), d = (fdemand[m]?.[pid]?.p50 ?? 0) * factor; sum += q; need += d; const ratio = d ? q / d : null;
                  return <td key={m} className="r num">{num(q)}<span className={`cellbar ${ratio !== null && ratio < 0.95 ? 'over' : ''}`} title={d ? `예상 수요 ${num(d)}` : undefined}><i style={{ width: `${Math.min((ratio ?? 0) * 100, 100)}%` }} /></span></td>; })}
                  <td className="r num"><b>{num(sum)}</b></td><td className="r num" style={need && sum / need < 0.95 ? { color: 'var(--bad)', fontWeight: 600 } : undefined}>{need ? pctText((sum / need) * 100) : '-'}</td></tr>; })}</tbody>
              <tfoot><tr><td>합계</td>{viewMonths.map((m) => <td key={m} className="r num">{num(selected?.byMonth[m] ?? 0)}</td>)}<td className="r num">{num(selected?.total ?? 0)}</td><td className="r num">{demandTotal ? pctText(((selected?.total ?? 0) / demandTotal) * 100) : '-'}</td></tr></tfoot></table></div></div>
          </section>}

          {view === 'materials' && <section className="panel"><header><div><h2>자재 부족 지도 · {selected ? short(selected.plan.label) : ''}</h2><p>칸이 진할수록 필요한 양에 비해 많이 모자랍니다. 많이 모자라는 자재가 위에 옵니다.</p></div><div className="actions"><ShortLegend /><Tag tone={selected?.shortages ? 'bad' : 'ok'}>{selected?.shortages ? `${selected.shortages}건` : '부족 없음'}</Tag></div></header>
            <div className="body">{selected?.shortageList.length ? <ShortMap months={viewMonths} list={selected.shortageList} names={names} /> : <Empty>이 안에서는 모자라는 자재가 없습니다.</Empty>}</div>
          </section>}
        </div>

        <div className="stack sticky">
          <section className="panel"><header><div><h2>조건 바꿔 다시 계산</h2><p>저장하지 않고 원래 계획과 비교만 합니다</p></div></header>
            <div className="body">
              <label className="field">수요를 몇 배로 볼까요 <b className="num" style={{ color: 'var(--ink)', fontSize: '0.9rem' }}>×{multiplier.toFixed(2)}{multiplier !== 1 && ` (${multiplier > 1 ? '+' : ''}${Math.round((multiplier - 1) * 100)}%)`}</b>
                <input type="range" min="0.7" max="1.4" step="0.05" value={multiplier} onChange={(e) => setMultiplier(Number(e.target.value))} /></label>
              <div className="formrow"><label className="field">잔업 한도 (시간)<input type="number" min="0" step="10" value={otHours} onChange={(e) => setOtHours(e.target.value)} /></label>
                <span className="small muted" style={{ flex: '2 1 150px' }}>부하 지도의 칸을 누른 뒤 "잔업 넣기"를 누르면 그 설비·달에 추가됩니다.</span></div>
              {Object.keys(overtime).length > 0 && <div className="chips">{Object.entries(overtime).map(([k, v]) => <button key={k} type="button" className="chip" title="눌러서 빼기" onClick={() => { const next = { ...overtime }; delete next[k]; setOvertime(next); }}>{names[k.split('.')[1]] ?? k.split('.')[1]} {shortMonth(k.split('.')[2])} +{v}h ✕</button>)}</div>}
              <div className="actions"><button type="button" className="btn primary lg" disabled={busy || !Object.keys(overrides).length} onClick={() => void recalc()}><Icon name="refresh" />{busy ? '계산 중…' : '이 조건으로 다시 계산'}</button>
                <button type="button" className="btn" disabled={busy || (!alt && !Object.keys(overrides).length)} onClick={resetWhatIf}>처음으로</button></div>
              {alt && <><div className="tabs" role="group" aria-label="볼 결과"><button type="button" aria-pressed={!showAlt} onClick={() => setShowAlt(false)}>원래 계획</button><button type="button" aria-pressed={showAlt} onClick={() => setShowAlt(true)}>바꾼 결과</button></div>
                <p className="small">{showAlt ? `왼쪽 화면이 바꾼 결과를 보여 줍니다: ${overrideText}` : '왼쪽 화면이 저장된 원래 계획을 보여 줍니다.'}</p></>}
            </div>
          </section>

          {alt && <section className="panel"><header><h2>바꾸기 전 → 후</h2></header>
            <div className="body flush"><table className="tbl"><thead><tr><th>안</th><th className="r">생산 합계</th><th>실행 가능성</th></tr></thead>
              <tbody>{baseSummaries.map((b) => { const a = altSummaries.find((s) => s.plan.plan_id === b.plan.plan_id); if (!a) return null; const diff = a.total - b.total;
                return <tr key={b.plan.plan_id}><td><b>{short(b.plan.label)}</b></td><td className="r num">{num(a.total)}<br /><span className="small muted">{diff > 0 ? '+' : ''}{num(diff)}</span></td>
                  <td><FeasSt value={b.plan.feasibility} /><br /><span className="small muted">→ </span><FeasSt value={a.plan.feasibility} /></td></tr>; })}</tbody></table>
              <table className="tbl"><thead><tr><th>무엇이 달라졌나</th>{baseSummaries.map((b) => <th key={b.plan.plan_id} className="r">{short(b.plan.label)}</th>)}</tr></thead>
                <tbody>{([['설비·인력 초과', (x: PlanSummary) => x.equipOver], ['수요를 못 채움', (x: PlanSummary) => x.demandMiss], ['안전 재고 미달', (x: PlanSummary) => x.safetyMiss], ['자재 부족', (x: PlanSummary) => x.shortages]] as Array<[string, (x: PlanSummary) => number]>).map(([label, pick]) =>
                  <tr key={label}><td>{label}</td>{baseSummaries.map((b) => { const a = altSummaries.find((s) => s.plan.plan_id === b.plan.plan_id); const before = pick(b), after = a ? pick(a) : before;
                    return <td key={b.plan.plan_id} className="r num">{before} → <b className={after > before ? 'delta-up' : after < before ? 'delta-down' : ''}>{after}</b></td>; })}</tr>)}</tbody></table></div>
          </section>}
        </div>
      </div>
    </>}
  </>;
}
