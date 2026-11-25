import { useEffect, useMemo, useState } from 'react';
import { BatchSt, Empty, ENTITY_NAME, failure, forecastLabel, go, monthLabel, Notice, St, Tag, when } from '../app/core';
import { Overview } from '../app/data';
import { apiClient } from '../services/api';
import { BatchSummary } from '../types/api';
import PlanRecord from './PlanRecord';

type Kind = 'all' | 'batch' | 'forecast' | 'plan';
const KINDS: Array<[Kind, string]> = [['all', '전체'], ['batch', '자료'], ['forecast', '예측'], ['plan', '계획']];
const ROLE = /^[A-Za-z0-9][A-Za-z0-9_.-]{1,59}$/;
const DECISION: Record<string, string> = { DRAFT: '검토 전', REVIEW: '검토 중', APPROVED: '승인됨', REJECTED: '반려됨' };

export default function HistoryPage({ overview, kind, focus, onReload }: { overview: Overview; kind?: string; focus?: string; onReload: () => void }) {
  const [filter, setFilter] = useState<Kind>((KINDS.find(([k]) => k === kind)?.[0] ?? 'all') as Kind);
  const [query, setQuery] = useState('');
  const [rejecting, setRejecting] = useState<BatchSummary | null>(null);
  const [actor, setActor] = useState('planner01');
  const [reason, setReason] = useState('잘못 올린 파일');
  const [message, setMessage] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [openPlan, setOpenPlan] = useState(focus ?? '');
  useEffect(() => { if (focus) { setOpenPlan(focus); setFilter('plan'); } }, [focus]);

  const rows = useMemo(() => [
    ...overview.batches.map((b) => ({ kind: 'batch' as const, at: b.created_at, key: b.batch_id, title: b.file.name, sub: `${ENTITY_NAME[b.entity]}${b.approved_record_count ? ` · ${b.approved_record_count}행 승인` : ''}${b.reject_reason ? ` · 반려 사유: ${b.reject_reason}` : ''}`, batch: b })),
    ...overview.forecasts.map((f) => ({ kind: 'forecast' as const, at: f.created_at, key: f.execution_id, title: forecastLabel(f), sub: `${f.forecast_count}행 예측`, forecast: f })),
    ...overview.plans.map((p) => ({ kind: 'plan' as const, at: p.created_at, key: p.execution_id, title: `${monthLabel(p.target_month)}부터${p.horizon_months ? ` ${p.horizon_months}개월` : ''}의 생산계획${p.scenario_type === 'WHAT_IF' ? ' (조건 변경)' : ''}`, sub: `${monthLabel(p.as_of_date.slice(0, 7))} 말 기준 · ${DECISION[p.decision_status] ?? p.decision_status}`, plan: p })),
  ].sort((a, b) => (a.at < b.at ? 1 : -1)), [overview]);
  const shown = rows.filter((r) => (filter === 'all' || r.kind === filter) && (!query.trim() || `${r.title} ${r.sub}`.toLowerCase().includes(query.trim().toLowerCase())));

  async function reject() {
    if (!rejecting) return;
    setBusy(true); setMessage(null);
    try { await apiClient.rejectBatch(rejecting.batch_id, actor, reason); setMessage({ tone: 'ok', text: `${rejecting.file.name}을 반려했습니다.` }); setRejecting(null); onReload(); }
    catch (error) { setMessage({ tone: 'bad', text: failure(error) }); }
    finally { setBusy(false); }
  }

  return <>
    {message && <Notice tone={message.tone}>{message.text}</Notice>}
    {overview.problems.map((p) => <Notice key={p} tone="warn">{p}</Notice>)}
    {rejecting && <section className="panel"><header><div><h2>자료 반려</h2><p>{rejecting.file.name} ({ENTITY_NAME[rejecting.entity]})을 반려합니다. 반려한 자료는 예측과 계획에 쓰이지 않습니다.</p></div></header>
      <div className="body"><div className="formrow"><label className="field">담당자 코드<input value={actor} onChange={(e) => setActor(e.target.value)} aria-invalid={!ROLE.test(actor)} /></label>
        <label className="field" style={{ flex: '2 1 240px' }}>반려 사유<input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <button type="button" className="btn danger" disabled={busy || !ROLE.test(actor) || !reason.trim()} onClick={() => void reject()}>{busy ? '반려 중…' : '반려 확정'}</button>
        <button type="button" className="btn" disabled={busy} onClick={() => setRejecting(null)}>취소</button></div></div></section>}

    {openPlan && <PlanRecord key={openPlan} executionId={openPlan} names={overview.names} onClose={() => setOpenPlan('')} onChanged={onReload} />}

    <section className="panel"><header><div className="tabs" role="group" aria-label="종류">{KINDS.map(([k, label]) => <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>{label} {k === 'all' ? rows.length : rows.filter((r) => r.kind === k).length}</button>)}</div>
      <label className="field" style={{ minWidth: 240 }}><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="파일 이름이나 내용으로 찾기" aria-label="찾기" /></label></header>
      <div className="body flush">{shown.length === 0 ? <Empty>표시할 기록이 없습니다.</Empty> :
        <div className="tablewrap"><table className="tbl"><thead><tr><th>언제</th><th>종류</th><th>내용</th><th>상태</th><th>할 수 있는 일</th></tr></thead>
          <tbody>{shown.map((r) => <tr key={`${r.kind}-${r.key}`}>
            <td className="small muted nw">{when(r.at)}</td>
            <td><Tag>{r.kind === 'batch' ? '자료' : r.kind === 'forecast' ? '예측' : '계획'}</Tag></td>
            <td><span className="name"><b>{r.title}</b><span className="code">{r.sub}</span></span></td>
            <td className="nw">{'batch' in r ? <BatchSt status={r.batch.status} /> : 'forecast' in r ? <St tone={r.forecast.status === 'OK' ? 'ok' : r.forecast.status === 'PARTIAL' ? 'warn' : 'bad'}>{r.forecast.status === 'OK' ? '완료' : r.forecast.status}</St> : <St tone={r.plan.status === 'COMPLETED' ? 'ok' : 'warn'}>{r.plan.status === 'COMPLETED' ? '저장됨' : r.plan.status}</St>}</td>
            <td><div className="actions">
              {'batch' in r && r.batch.status !== 'APPROVED' && r.batch.status !== 'REJECTED' && <button type="button" className="btn danger sm" onClick={() => { setRejecting(r.batch); window.scrollTo({ top: 0, behavior: 'smooth' }); }}>반려</button>}
              {'batch' in r && r.batch.status !== 'APPROVED' && r.batch.status !== 'REJECTED' && <button type="button" className="btn sm" onClick={() => go('ingest')}>자료 넣기로</button>}
              {'forecast' in r && <button type="button" className="btn sm" onClick={() => go('forecast', { f: r.forecast.execution_id })}>열기</button>}
              {'forecast' in r && (r.forecast.status === 'OK' || r.forecast.status === 'PARTIAL') && <button type="button" className="btn sm" onClick={() => go('plan', { f: r.forecast.execution_id })}>계획 세우기</button>}
              {'plan' in r && <button type="button" className="btn sm" aria-pressed={openPlan === r.plan.execution_id} onClick={() => { setOpenPlan(r.plan.execution_id); window.scrollTo({ top: 0, behavior: 'smooth' }); }}>자세히</button>}
              {'plan' in r && r.plan.scenario_type === 'BASE' && <button type="button" className="btn sm" onClick={() => go('plan', { f: r.plan.forecast_execution_id, t: r.plan.target_month })}>계획 화면</button>}
            </div></td></tr>)}</tbody></table></div>}</div>
    </section>
  </>;
}
