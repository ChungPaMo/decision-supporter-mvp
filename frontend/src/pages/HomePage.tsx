import { useMemo, useState } from 'react';
import { Empty, FeasSt, go, Icon, monthLabel, num, pctText, shortMonth } from '../app/core';
import { alerts, demandOf, loadGrid, nextAction, Overview, sumMonth, summarizePlan } from '../app/data';
import { C, HeatLegend, Legend, LineChart, LoadMap } from '../app/widgets';

const short = (label: string) => label.split(' ')[0];
const plain = (name: string) => name.replace(/\s*\(.*\)\s*$/, '');
// 받침에 따라 조사를 고른다 ("절단기가", "작업자 풀이").
const josa = (word: string, withFinal: string, without: string) => { const code = word.charCodeAt(word.length - 1) - 0xac00; return code >= 0 && code <= 11171 && code % 28 !== 0 ? withFinal : without; };

export default function HomePage({ overview }: { overview: Overview; onReload: () => void }) {
  const { latestPlan, planForecast, latestForecast, demand, names } = overview;
  const next = useMemo(() => nextAction(overview), [overview]);
  const notes = useMemo(() => alerts(overview), [overview]);
  const result = latestPlan?.result_snapshot ?? null;
  const summaries = useMemo(() => (result ? result.plans.map((p) => summarizePlan(result, p)) : []), [result]);
  const [planId, setPlanId] = useState('');
  const picked = summaries.find((s) => s.plan.plan_id === planId) ?? summaries.find((s) => s.plan.plan_type === 'BASELINE') ?? summaries[0];
  const forecast = planForecast ?? latestForecast;
  const fdemand = useMemo(() => demandOf(forecast), [forecast]);
  const grid = useMemo(() => (result && picked ? loadGrid(result, picked.plan.plan_id) : null), [result, picked]);
  const planMonths = picked ? Object.keys(picked.byMonth).sort() : [];
  const demandAll = planMonths.reduce((a, m) => a + sumMonth(fdemand[m]), 0);

  // 가장 빠듯한 설비·인력 칸이 이 화면의 첫 문장이 된다.
  const tightest = useMemo(() => {
    let best: { id: string; kind: string; month: string; pct: number; used: number; limit: number | null; unit: string } | null = null;
    for (const row of grid?.rows ?? []) for (const [m, cell] of Object.entries(row.cells)) if (cell.pct !== null && (!best || cell.pct > best.pct)) best = { id: row.id, kind: row.kind, month: m, pct: cell.pct, used: cell.used, limit: cell.limit, unit: cell.unit };
    return best;
  }, [grid]);
  const sortedRows = useMemo(() => [...(grid?.rows ?? [])].sort((a, b) => Math.max(...Object.values(b.cells).map((c) => c.pct ?? 0)) - Math.max(...Object.values(a.cells).map((c) => c.pct ?? 0))), [grid]);

  const totals = useMemo(() => { const map = new Map<string, number>(); for (const row of demand) map.set(row.period, (map.get(row.period) ?? 0) + Number(row.demand_qty)); return map; }, [demand]);
  const chart = useMemo(() => {
    const base = forecast?.parameters.trained_until.slice(0, 7) ?? [...totals.keys()].sort().pop() ?? '';
    const past = [...totals.keys()].sort().filter((m) => !base || m <= base).slice(-18);
    const future = Object.keys(fdemand).sort();
    const months = [...past, ...future];
    const actual = months.map((m) => (past.includes(m) ? totals.get(m)! : null));
    const p50 = months.map((m, i) => (future.includes(m) ? sumMonth(fdemand[m]) : i === past.length - 1 ? totals.get(m)! : null));
    const hi = months.map((m, i) => (future.includes(m) ? Object.values(fdemand[m]).reduce((a, v) => a + v.p90, 0) : i === past.length - 1 ? totals.get(m)! : null));
    const plan = months.map((m) => (picked && picked.byMonth[m] !== undefined ? picked.byMonth[m] : null));
    return { months, actual, p50, hi, plan, split: past.length };
  }, [totals, fdemand, forecast, picked]);

  const lead = (() => {
    if (!picked || !tightest) return null;
    const name = plain(names[tightest.id] ?? tightest.id);
    const monthDemand = sumMonth(fdemand[tightest.month]);
    const cover = monthDemand ? ((picked.byMonth[tightest.month] ?? 0) / monthDemand) * 100 : null;
    const verb = tightest.pct > 100 ? '한도를 넘습니다' : tightest.pct >= 99.5 ? '한도를 다 씁니다' : tightest.pct >= 90 ? '가장 빠듯합니다' : '가장 바쁩니다';
    const tone = tightest.pct >= 99.5 ? '' : tightest.pct >= 90 ? 'warn' : 'ok';
    return { name, verb, tone, cover };
  })();

  return <>
    {lead && tightest && picked ? <section className={`lead ${lead.tone}`} aria-label="지금 막히는 곳">
      <h2>{shortMonth(tightest.month)}, <mark>{lead.name}</mark>{josa(lead.name, '이', '가')} {lead.verb}</h2>
      <p>{tightest.limit === null ? `${num(tightest.used, 0)}${tightest.unit}이 필요합니다.` : `가동 한도 ${num(tightest.limit, 0)}시간 중 ${num(tightest.used, 0)}시간을 씁니다.`}
        {lead.cover !== null && ` ${short(picked.plan.label)}으로는 ${shortMonth(tightest.month)} 생산량이 예상 수요의 ${pctText(lead.cover)}입니다.`}</p>
      <div className="actions"><button type="button" className="btn primary lg" onClick={() => go('plan', { f: latestPlan?.forecast_execution_id, t: latestPlan?.target_month, p: picked.plan.plan_id, r: tightest.id, k: tightest.kind, m: tightest.month })}>잔업 한도를 바꿔 다시 계산<Icon name="arrow" /></button></div>
    </section> : <section className={`lead ${next.tone === 'info' ? 'ok' : next.tone}`} aria-label="다음에 할 일">
      <h2>{next.title}</h2><p>{next.text}</p>
      <div className="actions"><button type="button" className="btn primary lg" onClick={() => go(next.page, next.params)}>{next.button}<Icon name="arrow" /></button></div>
    </section>}

    {picked && grid && <div className="cols c31">
      <section className="panel"><header><div><h2>설비·인력 사용률</h2><p>{short(picked.plan.label)} · 달마다 한도의 몇 %를 쓰는지, 빠듯한 순서입니다. 테두리 친 칸이 가장 빠듯한 곳입니다.</p></div></header>
        <div className="body bare"><LoadMap months={grid.months} rows={sortedRows} names={names} selected={tightest} onPick={(pick) => go('plan', { f: latestPlan?.forecast_execution_id, t: latestPlan?.target_month, p: picked.plan.plan_id, r: pick.id, k: pick.kind, m: pick.month })} /><HeatLegend /></div>
      </section>

      <section className="panel"><header><div><h2>세 안</h2><p>{latestPlan ? `${monthLabel(latestPlan.target_month)}부터 3개월 · 예상 수요 대비. 누르면 왼쪽 표가 그 안으로 바뀝니다.` : ''}</p></div></header>
        <div className="body bare"><div className="rows">{summaries.map((s) => { const cover = demandAll ? (s.total / demandAll) * 100 : null;
          const detail = [s.equipOver ? `설비 초과 ${s.equipOver}칸` : '', s.demandMiss ? `수요 미충족 ${s.demandMiss}건` : '', s.safetyMiss ? `안전 재고 미달 ${s.safetyMiss}건` : '', s.shortages ? `자재 부족 ${s.shortages}건` : ''].filter(Boolean).join(' · ');
          return <button type="button" key={s.plan.plan_id} onClick={() => setPlanId(s.plan.plan_id)} aria-pressed={s.plan.plan_id === picked.plan.plan_id}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}><b>{short(s.plan.label)}</b><FeasSt value={s.plan.feasibility} /></span><strong>{pctText(cover)}</strong>
            <small>{num(s.total)} EA{detail && ` · ${detail}`}</small></button>; })}</div></div>
      </section>
    </div>}

    <div className="cols c31">
      <section className="panel"><header><div><h2>수요와 계획</h2><p>전 제품 합계입니다. 마우스를 올리면 값이 나옵니다.</p></div>
        <Legend items={[['실제 수요', C.actual], ['예측', C.forecast, true], ...(picked ? [['계획 생산량', C.plan] as [string, string]] : [])]} /></header>
        <div className="body bare"><LineChart months={chart.months} split={chart.split} height={260} unit=" EA" band={{ name: '많이 팔릴 때까지', lo: chart.p50, hi: chart.hi, color: C.forecast }}
          series={[{ name: '실제 수요', color: C.actual, values: chart.actual }, { name: '예측 가운데 값', color: C.forecast, values: chart.p50, dash: true }, ...(picked ? [{ name: '계획 생산량', color: C.plan, values: chart.plan, dots: true }] : [])]} /></div>
      </section>

      <section className="panel"><header><h2>확인할 것</h2></header>
        <div className="body flush">{notes.length ? <div className="alerts">{notes.map((n, i) => <button type="button" key={i} className={`alert ${n.tone === 'info' ? '' : n.tone}`} onClick={() => go(n.page, n.params)}>
          <i /><div><b>{n.title}</b>{n.text && <><br /><span>{n.text}</span></>}</div><Icon name="arrow" /></button>)}</div> : <Empty>확인할 것이 없습니다.</Empty>}</div>
      </section>
    </div>
  </>;
}
