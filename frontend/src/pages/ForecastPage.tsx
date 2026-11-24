import { useEffect, useMemo, useState } from 'react';
import { addMonths, Empty, failure, forecastLabel, go, Icon, Kpi, monthEnd, monthLabel, Notice, num, pctText, shortMonth, St, when } from '../app/core';
import { DemandRow, Names, useLoad } from '../app/data';
import { C, Legend, LineChart, Num } from '../app/widgets';
import { apiClient } from '../services/api';
import { ForecastExecution } from '../types/engine';

const ALL = '__all__';

export default function ForecastPage({ focus, names, onChanged }: { focus?: string; names: Names; onChanged: () => void }) {
  const base = useLoad(async () => {
    const [history, demand] = await Promise.all([apiClient.forecastHistory(50, 0), apiClient.demandAll().catch(() => [] as DemandRow[])]);
    return { history: history.items, demand };
  });
  const [detail, setDetail] = useState<ForecastExecution | null>(null);
  const [product, setProduct] = useState(ALL);
  const [trainedUntil, setTrainedUntil] = useState('');
  const [horizon, setHorizon] = useState(3);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'warn' | 'bad'; text: string } | null>(null);

  const demand = base.data?.demand ?? [];
  const history = base.data?.history ?? [];
  const lastMonth = useMemo(() => demand.reduce((max, row) => (row.period > max ? row.period : max), ''), [demand]);
  // 기준일 기본값: 승인된 월별 수요의 마지막 달 말일. 재고·설비 자료의 시점과 맞추기 쉽다.
  useEffect(() => { if (lastMonth && !trainedUntil) setTrainedUntil(monthEnd(lastMonth)); }, [lastMonth, trainedUntil]);

  async function open(id: string) {
    setMessage(null);
    try { setDetail(await apiClient.getForecast(id)); } catch (error) { setMessage({ tone: 'bad', text: failure(error) }); }
  }
  useEffect(() => {
    if (detail || !history.length) return;
    const pick = history.find((item) => item.execution_id === focus) ?? history.find((item) => item.status === 'OK' || item.status === 'PARTIAL');
    if (pick) void open(pick.execution_id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history, focus]);

  async function run() {
    setBusy(true); setMessage(null);
    try {
      const reply = await apiClient.runForecast({ trained_until: trainedUntil, horizon_months: horizon, p50_method: 'MA12', min_history_months: 12, random_seed: 42 });
      setMessage({ tone: reply.execution.status === 'OK' ? 'ok' : 'warn', text: reply.reused ? '같은 조건의 예측이 이미 있어 저장된 결과를 불러왔습니다.' : `예측을 실행했습니다. ${reply.execution.forecast_count}행이 저장됐습니다.` });
      await base.reload(); await open(reply.execution.execution_id); onChanged();
    } catch (error) { setMessage({ tone: 'bad', text: failure(error) }); }
    finally { setBusy(false); }
  }

  const rows = detail?.result?.forecasts ?? [];
  const products = useMemo(() => [...new Set(rows.map((r) => r.product_id))].sort(), [rows]);
  const months = useMemo(() => [...new Set(rows.map((r) => r.target_month))].sort(), [rows]);
  const baseMonth = detail?.parameters.trained_until.slice(0, 7) ?? '';
  const first = months[0];
  const pick = (pid: string) => (product === ALL || product === pid);

  const chart = useMemo(() => {
    const totals = new Map<string, number>();
    for (const d of demand) if (pick(d.product_id) && (!baseMonth || d.period <= baseMonth)) totals.set(d.period, (totals.get(d.period) ?? 0) + Number(d.demand_qty));
    const past = [...totals.keys()].sort().slice(-24);
    const fut = new Map<string, { p50: number; p80: number; p90: number }>();
    for (const r of rows) if (pick(r.product_id)) { const v = fut.get(r.target_month) ?? { p50: 0, p80: 0, p90: 0 }; v.p50 += Number(r.p50); v.p80 += Number(r.p80); v.p90 += Number(r.p90); fut.set(r.target_month, v); }
    const all = [...past, ...months];
    const join = (i: number, m: string) => (i === past.length - 1 ? totals.get(m)! : null);
    return { months: all, split: past.length,
      actual: all.map((m) => (past.includes(m) ? totals.get(m)! : null)),
      p50: all.map((m, i) => fut.get(m)?.p50 ?? join(i, m)), p90: all.map((m, i) => fut.get(m)?.p90 ?? join(i, m)) };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demand, rows, product, baseMonth, months]);

  // 제품별 한 줄 요약: 다음 달 예측과 작년 같은 달 대비
  const table = useMemo(() => products.map((pid) => {
    const next = rows.find((r) => r.product_id === pid && r.target_month === first);
    const last = first ? demand.find((d) => d.product_id === pid && d.period === addMonths(first, -12)) : undefined;
    const p50 = Number(next?.p50 ?? 0), prev = last ? Number(last.demand_qty) : null;
    return { pid, p50, p80: Number(next?.p80 ?? 0), p90: Number(next?.p90 ?? 0), yoy: prev ? ((p50 - prev) / prev) * 100 : null,
      total: rows.filter((r) => r.product_id === pid).reduce((a, r) => a + Number(r.p50), 0) };
  }).sort((a, b) => b.p50 - a.p50), [products, rows, demand, first]);
  const sum = (key: 'p50' | 'p80' | 'p90' | 'total') => table.reduce((a, r) => a + r[key], 0);
  const prevTotal = first ? demand.filter((d) => d.period === addMonths(first, -12)).reduce((a, d) => a + Number(d.demand_qty), 0) : 0;
  const yoyAll = prevTotal ? ((sum('p50') - prevTotal) / prevTotal) * 100 : null;
  const spread = sum('p50') ? ((sum('p90') - sum('p50')) / sum('p50')) * 100 : null;

  return <>
    <section className="panel"><div className="body">
      <div className="formrow">
        <label className="field">언제까지의 자료로 예측할까요 (월말)<input type="date" value={trainedUntil} onChange={(e) => setTrainedUntil(e.target.value)} /></label>
        <label className="field">몇 달을 예측할까요<select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>{Array.from({ length: 12 }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}개월</option>)}</select></label>
        <button type="button" className="btn lg" disabled={busy || !trainedUntil} onClick={() => void run()}><Icon name="play" />{busy ? '예측 중…' : '예측 실행'}</button>
        <button type="button" className="btn primary lg" disabled={!detail || !rows.length} onClick={() => detail && go('plan', { f: detail.execution_id })}>이 예측으로 계획 세우기<Icon name="arrow" /></button>
      </div>
      <p className="small">{lastMonth ? <>승인된 월별 수요는 <b style={{ color: 'var(--ink-2)' }}>{monthLabel(lastMonth)}</b>까지 있습니다. {trainedUntil && <>이 설정이면 <b style={{ color: 'var(--ink-2)' }}>{monthLabel(addMonths(trainedUntil.slice(0, 7), 1))}</b>부터 {horizon}개월을 예측합니다. </>}</> : '승인된 월별 수요가 없습니다. 먼저 자료를 넣으세요. '}
        {horizon > 3 && '4개월 이상은 검증된 범위 밖입니다.'}</p>
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
      {base.error && <Notice tone="bad">{base.error}</Notice>}
    </div></section>

    {!detail ? <section className="panel"><Empty>{base.loading ? '읽는 중…' : '위에서 예측을 실행하면 그래프와 제품별 표가 나옵니다.'}</Empty></section> : <>
      <section className="kpis" aria-label="예측 요약">
        <Kpi label="보고 있는 예측" value={`${monthLabel(baseMonth)} 말`} note={`${when(detail.created_at)} 실행 · ${months.length}개월`} />
        <Kpi label={first ? `${monthLabel(first)} 예상 수요` : '예상 수요'} value={<Num value={sum('p50')} />} unit="EA" note={yoyAll === null ? '작년 같은 달 자료 없음' : `작년 ${shortMonth(first)} 대비 ${yoyAll > 0 ? '+' : ''}${num(yoyAll, 1)}%`} />
        <Kpi label="많이 팔릴 때" value={<Num value={sum('p90')} />} unit="EA" note={spread === null ? '' : `가운데 값보다 +${num(spread, 1)}%`} />
        {((detail.result?.skipped.length ?? 0) > 0 || (detail.result?.warnings.length ?? 0) > 0) && <Kpi label="건너뛴 제품 · 경고" value={`${detail.result?.skipped.length ?? 0} · ${detail.result?.warnings.length ?? 0}`} note={detail.status === 'OK' ? '정상 완료' : detail.status} tone={detail.result?.skipped.length || detail.result?.warnings.length ? 'warn' : 'ok'} />}
      </section>

      <div className="cols c21">
        <section className="panel"><header><div><h2>{product === ALL ? '전체 제품 수요' : names[product] ?? product}</h2><p>옅은 구간이 예측입니다. 마우스를 올리면 값이 나옵니다.</p></div>
          <Legend items={[['실제 수요', C.actual], ['예측 가운데 값', C.forecast, true], ['많이 팔릴 때까지의 범위', '#cfe0fb']]} /></header>
          <div className="body bare"><LineChart months={chart.months} split={chart.split} height={340} unit=" EA" band={{ name: '범위', lo: chart.p50, hi: chart.p90, color: C.forecast }}
            series={[{ name: '실제 수요', color: C.actual, values: chart.actual }, { name: '예측 가운데 값', color: C.forecast, values: chart.p50, dash: true, dots: true }]} /></div>
        </section>

        <section className="panel"><header><div><h2>제품별 {first ? shortMonth(first) : ''} 예측</h2><p>줄을 누르면 왼쪽 그래프가 그 제품으로 바뀝니다</p></div>
          {product !== ALL && <button type="button" className="btn sm" onClick={() => setProduct(ALL)}>전체 보기</button>}</header>
          <div className="body flush"><div className="tablewrap"><table className="tbl fit"><thead><tr><th>제품</th><th className="r nw">가운데 값</th><th className="r nw">작년 대비</th></tr></thead>
            <tbody>{table.map((r) => <tr key={r.pid} className={`clickable${r.pid === product ? ' selected' : ''}`} onClick={() => setProduct(r.pid === product ? ALL : r.pid)}>
              <td><span className="name" title={`${names[r.pid] ?? r.pid} (${r.pid})`}><b>{names[r.pid] ?? r.pid}</b><span className="code">{r.pid}</span></span></td>
              <td className="r num nw" style={{ minWidth: 84 }}><b><Num value={r.p50} /></b><span className="cellbar"><i style={{ width: `${(r.p50 / (table[0]?.p50 || 1)) * 100}%` }} /></span></td>
              <td className={`r num nw ${r.yoy === null ? 'muted' : r.yoy > 0 ? 'delta-up' : 'delta-down'}`} style={r.yoy !== null && r.yoy > 0 ? { color: 'var(--ink-2)' } : undefined}>{r.yoy === null ? '-' : `${r.yoy > 0 ? '+' : ''}${pctText(r.yoy)}`}</td></tr>)}</tbody>
            <tfoot><tr><td>합계</td><td className="r num"><Num value={sum('p50')} /></td><td className="r num">{yoyAll === null ? '-' : `${yoyAll > 0 ? '+' : ''}${pctText(yoyAll)}`}</td></tr></tfoot></table></div></div>
        </section>
      </div>
    </>}

    <section className="panel"><header><div><h2>지난 예측</h2><p>언제 기준으로 어느 달을 예측했는지로 구분합니다</p></div></header>
      <div className="body flush">{history.length ? <div className="tablewrap"><table className="tbl"><thead><tr><th>예측</th><th>상태</th><th className="r">행</th><th>실행한 때</th><th>할 수 있는 일</th></tr></thead>
        <tbody>{history.map((item) => <tr key={item.execution_id} className={item.execution_id === detail?.execution_id ? 'selected' : ''}>
          <td><b>{forecastLabel(item)}</b></td>
          <td><St tone={item.status === 'OK' ? 'ok' : item.status === 'PARTIAL' ? 'warn' : 'bad'}>{item.status === 'OK' ? '완료' : item.status === 'PARTIAL' ? '일부 완료' : '실패'}</St></td>
          <td className="r num">{item.forecast_count}</td><td className="small muted nw">{when(item.created_at)}</td>
          <td><div className="actions"><button type="button" className="btn sm" onClick={() => void open(item.execution_id)}>보기</button>
            {(item.status === 'OK' || item.status === 'PARTIAL') && <button type="button" className="btn sm" onClick={() => go('plan', { f: item.execution_id })}>이걸로 계획 세우기</button>}</div></td></tr>)}</tbody></table></div>
        : <Empty>{base.loading ? '읽는 중…' : '저장된 예측이 없습니다.'}</Empty>}</div>
    </section>
  </>;
}
