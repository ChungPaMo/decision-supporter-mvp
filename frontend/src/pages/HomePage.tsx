import { useMemo, useState } from 'react';
import { addMonths, BatchSt, Empty, ENTITY_NAME, ENTITY_ORDER, FeasSt, forecastLabel, go, Icon, Kpi, monthLabel, num, pctText, shortMonth, St, Tag, when } from '../app/core';
import { alerts, approvedEntities, demandOf, loadGrid, nextAction, Overview, sumMonth, summarizePlan } from '../app/data';
import { C, Dots, GroupBars, HeatLegend, Legend, LineChart, LoadMap, MiniBars, Ring, Spark, TargetBars } from '../app/widgets';

const short = (label: string) => label.split(' ')[0];

export default function HomePage({ overview, onReload }: { overview: Overview; onReload: () => void }) {
  const { batches, latestPlan, planForecast, latestForecast, demand, names } = overview;
  const next = useMemo(() => nextAction(overview), [overview]);
  const notes = useMemo(() => alerts(overview), [overview]);
  const result = latestPlan?.result_snapshot ?? null;
  const summaries = useMemo(() => (result ? result.plans.map((p) => summarizePlan(result, p)) : []), [result]);
  const [planId, setPlanId] = useState('');
  const picked = summaries.find((s) => s.plan.plan_id === planId) ?? summaries.find((s) => s.plan.plan_type === 'BASELINE') ?? summaries[0];
  const month = latestPlan?.target_month ?? null;
  const forecast = planForecast ?? latestForecast;
  const fdemand = useMemo(() => demandOf(forecast), [forecast]);
  const grid = useMemo(() => (result && picked ? loadGrid(result, picked.plan.plan_id) : null), [result, picked]);
  const approved = approvedEntities(batches);

  // 가장 바쁜 설비·인력 칸
  const busiest = useMemo(() => {
    let best: { id: string; month: string; pct: number } | null = null;
    for (const row of grid?.rows ?? []) for (const [m, cell] of Object.entries(row.cells)) if (cell.pct !== null && (!best || cell.pct > best.pct)) best = { id: row.id, month: m, pct: cell.pct };
    return best;
  }, [grid]);

  const totals = useMemo(() => { const map = new Map<string, number>(); for (const row of demand) map.set(row.period, (map.get(row.period) ?? 0) + Number(row.demand_qty)); return map; }, [demand]);
  const demandNext = month ? sumMonth(fdemand[month]) : 0;
  const lastYear = month ? totals.get(addMonths(month, -12)) : undefined;
  const yoy = demandNext && lastYear ? ((demandNext - lastYear) / lastYear) * 100 : null;
  const produced = picked && month ? picked.byMonth[month] ?? 0 : 0;
  const cover = demandNext ? (produced / demandNext) * 100 : null;
  const runnable = summaries.filter((s) => s.plan.feasibility !== 'INFEASIBLE');
  const planMonths = picked ? Object.keys(picked.byMonth).sort() : [];
  const demandAll = planMonths.reduce((a, m) => a + sumMonth(fdemand[m]), 0);
  const coverAll = picked && demandAll ? (picked.total / demandAll) * 100 : null;

  const chart = useMemo(() => {
    const base = forecast?.parameters.trained_until.slice(0, 7) ?? [...totals.keys()].sort().pop() ?? '';
    const past = [...totals.keys()].sort().filter((m) => !base || m <= base).slice(-18);
    const future = Object.keys(fdemand).sort();
    const months = [...past, ...future];
    const actual = months.map((m) => (past.includes(m) ? totals.get(m)! : null));
    const p50 = months.map((m, i) => (future.includes(m) ? sumMonth(fdemand[m]) : i === past.length - 1 ? totals.get(m)! : null));
    const hi = months.map((m, i) => (future.includes(m) ? Object.values(fdemand[m]).reduce((a, v) => a + v.p90, 0) : i === past.length - 1 ? totals.get(m)! : null));
    return { months, actual, p50, hi, split: past.length, recent: past.slice(-12).map((m) => totals.get(m)!) };
  }, [totals, fdemand, forecast]);
  const shortByMonth = planMonths.map((m) => picked?.shortageList.filter((s) => s.period === m).length ?? 0);

  const activity = useMemo(() => [
    ...batches.map((b) => ({ at: b.approved_at ?? b.created_at, text: b.file.name, sub: ENTITY_NAME[b.entity], node: <BatchSt status={b.status} /> })),
    ...overview.forecasts.map((f) => ({ at: f.created_at, text: '수요 예측', sub: forecastLabel(f), node: <St tone={f.status === 'OK' ? 'ok' : 'warn'}>{f.status === 'OK' ? '완료' : f.status}</St> })),
    ...overview.plans.map((p) => ({ at: p.created_at, text: '생산계획', sub: `${monthLabel(p.target_month)}부터`, node: <St tone={p.status === 'COMPLETED' ? 'ok' : 'warn'}>{p.status === 'COMPLETED' ? '저장됨' : p.status}</St> })),
  ].sort((a, b) => (a.at < b.at ? 1 : -1)).slice(0, 6), [batches, overview.forecasts, overview.plans]);

  return <>
    <section className={`hero ${next.tone === 'info' ? '' : next.tone}`} aria-label="다음에 할 일">
      <div>
        <span className="eyebrow"><i />다음에 할 일</span>
        <h2>{next.title}</h2><p>{next.text}</p>
        <div className="actions"><button type="button" className="btn primary cta" onClick={() => go(next.page, next.params)}>{next.button}<Icon name="arrow" /></button>
          <button type="button" className="btn lg ghost" onClick={onReload}><Icon name="refresh" />새로고침</button></div>
      </div>
      <div className="rings">
        <Ring size={100} value={(approved.length / ENTITY_ORDER.length) * 100} center={`${approved.length}/${ENTITY_ORDER.length}`} label="자료 승인" sub={approved.length === ENTITY_ORDER.length ? '모두 준비됨' : '더 넣어야 함'} tone={approved.length === ENTITY_ORDER.length ? undefined : 'warn'} />
        <Ring size={100} value={coverAll} label="수요 충족" sub={picked ? `${short(picked.plan.label)} · 3개월` : '계획 없음'} tone={coverAll === null ? undefined : coverAll < 90 ? 'bad' : coverAll < 99.5 ? 'warn' : undefined} />
        <Ring size={100} value={busiest?.pct ?? null} label="가장 바쁜 설비" sub={busiest ? `${names[busiest.id] ?? busiest.id}` : '계획 없음'} tone={busiest ? (busiest.pct > 100 ? 'bad' : busiest.pct >= 90 ? 'warn' : undefined) : undefined} />
      </div>
    </section>

    <section className="kpis" aria-label="핵심 현황">
      <Kpi label={month ? `${monthLabel(month)} 예상 수요` : '예상 수요'} value={demandNext ? num(demandNext) : '-'} unit={demandNext ? 'EA' : ''}
        note={yoy === null ? (forecast ? '작년 같은 달 자료 없음' : '예측을 실행하세요') : `작년 ${shortMonth(month!)} 대비 ${yoy > 0 ? '+' : ''}${num(yoy, 1)}%`} viz={<Spark values={chart.recent} color={C.actual} />} />
      <Kpi label={picked && month ? `${shortMonth(month)} 계획 생산량 · ${short(picked.plan.label)}` : '계획 생산량'} value={picked ? num(produced) : '-'} unit={picked ? 'EA' : ''}
        note={cover === null ? '계획을 계산하세요' : `예상 수요의 ${pctText(cover)}`} tone={cover === null ? undefined : cover < 95 ? 'warn' : 'ok'} viz={picked ? <MiniBars values={planMonths.map((m) => picked.byMonth[m])} /> : undefined} />
      <Kpi label="자재 부족" value={picked ? `${picked.shortages}` : '-'} unit={picked ? '건' : ''} note={picked?.shortageList[0] ? `${shortMonth(picked.shortageList[0].period)} ${names[picked.shortageList[0].material_id] ?? picked.shortageList[0].material_id}부터` : picked ? '부족 없음' : ''} tone={picked ? (picked.shortages ? 'bad' : 'ok') : undefined}
        viz={picked?.shortages ? <MiniBars values={shortByMonth} color={C.bad} /> : undefined} />
      <Kpi label="실행할 수 있는 안" value={summaries.length ? `${runnable.length} / ${summaries.length}` : '-'} note={runnable.length ? runnable.map((s) => short(s.plan.label)).join(', ') : summaries.length ? '모두 실행 불가' : ''} tone={summaries.length ? (runnable.length ? 'ok' : 'bad') : undefined}
        viz={summaries.length ? <Dots total={summaries.length} on={runnable.length} /> : undefined} />
    </section>

    <div className="cols c31">
      <div className="stack">
        <section className="panel"><header><div><h2>설비·인력 부하 지도</h2><p>달마다 한도의 몇 %를 쓰는지. 주황은 빠듯한 곳, 빨강은 막히는 곳입니다.</p></div>
          {summaries.length > 0 && <div className="tabs" role="group" aria-label="볼 안">{summaries.map((s) => <button key={s.plan.plan_id} type="button" aria-pressed={s.plan.plan_id === picked?.plan.plan_id} onClick={() => setPlanId(s.plan.plan_id)}>{short(s.plan.label)}</button>)}</div>}</header>
          <div className="body">{grid ? <><LoadMap months={grid.months} rows={grid.rows} names={names} onPick={() => go('plan')} /><HeatLegend /></>
            : <Empty action={<button type="button" className="btn primary" onClick={() => go('plan')}>계획 계산하러 가기<Icon name="arrow" /></button>}>계획을 계산하면 설비와 인력의 달별 부하가 여기에 나옵니다.</Empty>}</div>
        </section>

        <div className="cols c11">
          <section className="panel"><header><div><h2>달별 수요와 생산</h2><p>예상 수요에 견줘 {picked ? short(picked.plan.label) : '계획'}이 얼마나 만드는지</p></div>
            <Legend items={[['예상 수요', C.demand], ['계획 생산량', C.plan]]} /></header>
            <div className="body">{picked ? <GroupBars months={planMonths} unit=" EA" groups={[{ name: '예상 수요', color: C.demand, values: planMonths.map((m) => sumMonth(fdemand[m])) }, { name: '계획 생산량', color: C.plan, values: planMonths.map((m) => picked.byMonth[m]) }]} /> : <Empty>아직 계획이 없습니다.</Empty>}</div>
          </section>
          <section className="panel"><header><div><h2>수요 흐름</h2><p>전 제품 합계 · 마우스를 올리면 값이 나옵니다</p></div>
            <Legend items={[['실제 수요', C.actual], ['예측', C.forecast, true]]} /></header>
            <div className="body"><LineChart months={chart.months} split={chart.split} height={230} unit=" EA" band={{ name: '많이 팔릴 때까지', lo: chart.p50, hi: chart.hi, color: C.forecast }}
              series={[{ name: '실제 수요', color: C.actual, values: chart.actual, area: true }, { name: '예측 가운데 값', color: C.forecast, values: chart.p50, dash: true, dots: true }]} /></div>
          </section>
        </div>

        <section className="panel"><header><h2>최근 활동</h2><button type="button" className="btn sm" onClick={() => go('history')}>기록 전체<Icon name="arrow" /></button></header>
          <div className="body flush">{activity.length ? <table className="tbl"><tbody>{activity.map((a, i) => <tr key={i}><td><span className="name"><b>{a.text}</b><span className="code">{a.sub}</span></span></td><td className="nw">{a.node}</td><td className="r nw small muted">{when(a.at)}</td></tr>)}</tbody></table> : <Empty>아직 활동이 없습니다.</Empty>}</div>
        </section>
      </div>

      <div className="stack">
        <section className="panel"><header><h2>확인할 것</h2><Tag tone={notes.some((n) => n.tone === 'bad') ? 'bad' : notes.length ? 'warn' : 'ok'}>{notes.length ? `${notes.length}` : '없음'}</Tag></header>
          <div className="body flush">{notes.length ? <div className="alerts">{notes.map((n, i) => <button type="button" key={i} className={`alert ${n.tone === 'info' ? '' : n.tone}`} onClick={() => go(n.page, n.params)}>
            <i /><div><b>{n.title}</b>{n.text && <><br /><span>{n.text}</span></>}</div><Icon name="arrow" /></button>)}</div> : <Empty>확인할 것이 없습니다.</Empty>}</div>
        </section>

        <section className="panel"><header><div><h2>세 안 비교</h2><p>{latestPlan ? `${monthLabel(latestPlan.target_month)}부터 3개월 · 검은 눈금이 예상 수요` : '저장된 계획 없음'}</p></div>
          <button type="button" className="btn primary sm" onClick={() => go('plan')}>자세히<Icon name="arrow" /></button></header>
          <div className="body">{summaries.length ? <TargetBars narrow rows={summaries.map((s) => ({ key: s.plan.plan_id, value: s.total, target: demandAll, label: <span className="name"><b>{short(s.plan.label)}</b><FeasSt value={s.plan.feasibility} /></span> }))} /> : <Empty>아직 계획이 없습니다.</Empty>}</div>
        </section>

        <section className="panel"><header><h2>자료 기준 시점</h2><Tag tone={approved.length === ENTITY_ORDER.length ? 'ok' : 'warn'}>{approved.length} / {ENTITY_ORDER.length}</Tag></header>
          <div className="body flush"><table className="tbl"><tbody>{ENTITY_ORDER.map((entity) => { const items = batches.filter((b) => b.entity === entity && b.status === 'APPROVED');
            return <tr key={entity}><td className="nw"><b>{ENTITY_NAME[entity]}</b></td><td className="small muted">{items.length ? `파일 ${items.length}개` : '아직 없음'}</td>
              <td className="r nw">{items.length ? <St tone="ok">{when(items[0].approved_at)}</St> : <St tone="warn">필요</St>}</td></tr>; })}</tbody></table></div>
        </section>
      </div>
    </div>
  </>;
}
