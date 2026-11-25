import { useEffect, useState } from 'react';
import { ENTITY_NAME, failure, failureCode, FeasSt, go, monthLabel, Notice, num, when } from '../app/core';
import { Names } from '../app/data';
import { apiClient } from '../services/api';
import { Entity } from '../types/api';
import { PlanDecisionAction, PlanDecisionEvent, PlanExecutionDetail } from '../types/modules';

const ROLE = /^[A-Za-z0-9][A-Za-z0-9_.-]{1,59}$/;
const DECISION: Record<string, string> = { DRAFT: '검토 전', REVIEW: '검토 중', APPROVED: '승인됨', REJECTED: '반려됨' };
const ACTION: Record<string, string> = { REVIEW: '검토 시작', APPROVE: '승인', REJECT: '반려' };
const STATUS: Record<string, string> = { COMPLETED: '계산 완료', PARTIAL: '일부만 계산', FAILED: '계산 실패' };
type Source = { batch_id: string; batch_version?: number; entity: Entity; source_sha256?: string; approved_at?: string };
type Receipt = { po_id?: string; receipt_key?: string; material_id?: string; expected_date?: string; open_qty?: string; ordered_qty?: string; unit?: string };

// 조건을 사람이 읽는 말로. 키 형태는 서버 계약의 네 가지뿐이다.
function overrideLine(key: string, value: string, names: Names): string {
  const [head, a, b] = key.split('.');
  if (head === 'demand_multiplier') return a ? `${names[a] ?? a} 수요 ×${value}` : `전체 수요 ×${value}`;
  if (head === 'overtime_hours_limit') return `${names[a] ?? a} ${b ? monthLabel(b) : ''} 잔업 한도 ${value}시간`;
  if (head === 'receipt_qty') return `발주 ${key.slice('receipt_qty.'.length)} 입고 수량 ${num(value, 3)}`;
  return `${key} = ${value}`;
}

// 저장된 계획 실행 한 건: 무엇으로(승인 자료·예측·기간) 계산했고, 누가 어떻게 검토했는지.
export default function PlanRecord({ executionId, names, onClose, onChanged }: { executionId: string; names: Names; onClose: () => void; onChanged: () => void }) {
  const [detail, setDetail] = useState<PlanExecutionDetail | null>(null);
  const [decisions, setDecisions] = useState<PlanDecisionEvent[]>([]);
  const [planId, setPlanId] = useState('');
  const [actor, setActor] = useState('planner01');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState<{ tone: 'ok' | 'warn' | 'bad'; text: string } | null>(null);

  useEffect(() => {
    let live = true;
    setDetail(null); setDecisions([]); setError(''); setNote(null);
    void Promise.all([apiClient.getPlanExecution(executionId), apiClient.planDecisions(executionId)]).then(([execution, history]) => {
      if (!live) return;
      setDetail(execution); setDecisions(history.items);
      setPlanId(execution.selected_plan_id ?? execution.result_snapshot.plans.find((p) => p.feasibility !== 'INFEASIBLE')?.plan_id ?? execution.result_snapshot.plans[0]?.plan_id ?? '');
    }).catch((e) => { if (live) setError(failureCode(e) === 'PLAN_NOT_FOUND' ? '이 데이터셋에 없는 계획입니다. 다른 데이터셋에서 대신 찾지 않습니다. (PLAN_NOT_FOUND)' : failure(e)); });
    return () => { live = false; };
  }, [executionId]);

  async function decide(action: PlanDecisionAction) {
    if (!detail || !planId) return;
    setBusy(true); setNote(null);
    try {
      const updated = await apiClient.decidePlan(detail.execution_id, { plan_id: planId, action, actor_id: actor, reason, expected_version: detail.version, expected_input_digest: detail.input_digest });
      setDetail(updated); setDecisions(updated.decisions); setReason('');
      setNote({ tone: 'ok', text: `${ACTION[action]} 기록을 남겼습니다. 담당자 코드는 로그인으로 확인한 값이 아닙니다.` });
      onChanged();
    } catch (e) {
      setNote(failureCode(e) === 'PLAN_APPROVAL_DISABLED'
        ? { tone: 'warn', text: '정식 승인은 로그인·승인 정책이 아직 연결되지 않아 쓸 수 없습니다. 승인된 것으로 표시하지 않습니다. (PLAN_APPROVAL_DISABLED)' }
        : { tone: 'bad', text: failure(e) });
    } finally { setBusy(false); }
  }

  const command = detail?.input_snapshot?.command;
  const approved = (detail?.input_snapshot?.approved_inputs ?? {}) as { sources?: Source[]; products?: unknown[]; materials?: unknown[]; boms?: unknown[]; inventory?: unknown[] };
  const receipts = ((detail?.input_snapshot?.scheduled_receipts ?? []) as Receipt[]);
  const overrides = Object.entries(command?.overrides ?? {});
  const horizon = command?.horizon_months ?? detail?.horizon_months;
  const final = detail?.decision_status === 'APPROVED' || detail?.decision_status === 'REJECTED';
  const canDecide = !!detail && !!planId && ROLE.test(actor) && !!reason.trim() && !busy && !final;
  const total = (id: string) => detail!.result_snapshot.plans.find((p) => p.plan_id === id)?.production.reduce((a, r) => a + Number(r.production_qty), 0) ?? 0;

  return <section className="panel" aria-label="계획 실행 상세"><header><div><h2>계획 실행 상세</h2>
    <p>{detail ? `${monthLabel(detail.target_month)}부터${horizon ? ` ${horizon}개월 치` : ''} · ${detail.scenario_type === 'WHAT_IF' ? '조건을 바꾼 계획' : '기준 계획'} · ${when(detail.created_at)} 저장` : '읽는 중…'}</p></div>
    <div className="actions">{detail && <button type="button" className="btn sm" onClick={() => go('plan', { f: detail.forecast_execution_id, t: detail.target_month })}>계획 화면에서 열기</button>}
      <button type="button" className="btn sm" onClick={onClose}>닫기</button></div></header>
    {error && <div className="body"><Notice tone="bad">{error}</Notice></div>}
    {detail && <div className="body">
      {note && <Notice tone={note.tone}>{note.text}</Notice>}
      <dl className="kv">
        <dt>계산 상태</dt><dd>{STATUS[detail.status] ?? detail.status}{detail.error_code ? ` · ${detail.error_code}` : ''}</dd>
        <dt>검토 상태</dt><dd>{DECISION[detail.decision_status] ?? detail.decision_status} (변경 {detail.version}회차)</dd>
        <dt>기간</dt><dd>{monthLabel(detail.target_month)}부터 {horizon ?? '?'}개월 · {detail.as_of_date} 기준</dd>
        <dt>제품</dt><dd>{command?.product_ids?.length ?? '-'}종</dd>
        {detail.base_plan_execution_id && <><dt>원래 계획</dt><dd><button type="button" className="btn sm" onClick={() => go('history', { kind: 'plan', x: detail.base_plan_execution_id! })}>원래 계획 보기</button></dd></>}
        <dt>계산 규칙</dt><dd>{detail.engine_version}</dd>
        <dt>입력 지문</dt><dd className="small">{detail.input_digest.replace('sha256:', '').slice(0, 16)}…</dd>
      </dl>
      {detail.scenario_type === 'WHAT_IF' && <><h3>바꾼 조건</h3>
        {overrides.length ? <div className="chips">{overrides.map(([k, v]) => <span key={k} className="chip static">{overrideLine(k, String(v), names)}</span>)}</div> : <p className="small muted">저장된 조건이 없습니다.</p>}</>}

      <h3>세 안</h3>
      <div className="tablewrap"><table className="tbl tight"><thead><tr><th>검토 대상</th><th>안</th><th>실행 가능성</th><th className="r">생산 합계</th></tr></thead>
        <tbody>{detail.result_snapshot.plans.map((p) => <tr key={p.plan_id}><td><input type="radio" name="plan-record-candidate" aria-label={`${p.label} 검토 대상`} checked={planId === p.plan_id} disabled={final} onChange={() => setPlanId(p.plan_id)} /></td>
          <td>{p.label}{detail.selected_plan_id === p.plan_id && <b> · 선택됨</b>}</td><td><FeasSt value={p.feasibility} /></td><td className="r num">{num(total(p.plan_id))} EA</td></tr>)}
          {!detail.result_snapshot.plans.length && <tr><td colSpan={4} className="muted">계산된 안이 없습니다.</td></tr>}</tbody></table></div>
      {detail.result_snapshot.errors.length > 0 && <Notice tone="bad">{detail.result_snapshot.errors.map((e) => `${e.message} (${e.code})`).join(' · ')}</Notice>}

      <h3>이 계획이 쓴 승인 자료</h3>
      <p className="small muted">계산할 때 읽은 승인 자료를 그대로 보관한 것입니다. 이후에 자료를 새로 승인해도 이 계획의 입력은 바뀌지 않습니다.
        {` 제품 ${approved.products?.length ?? 0} · 자재 ${approved.materials?.length ?? 0} · BOM ${approved.boms?.length ?? 0} · 재고 ${approved.inventory?.length ?? 0}행, 예정 입고 ${receipts.length}건.`}</p>
      <div className="tablewrap scrollbox" style={{ maxHeight: 240 }}><table className="tbl tight"><thead><tr><th>자료</th><th>승인 시각</th><th>자료 번호</th><th>원본 지문</th></tr></thead>
        <tbody>{(approved.sources ?? []).map((s) => <tr key={s.batch_id}><td>{ENTITY_NAME[s.entity] ?? s.entity}</td><td className="small nw">{when(s.approved_at)}</td><td className="small"><span className="code">{s.batch_id.slice(0, 8)}{s.batch_version ? ` v${s.batch_version}` : ''}</span></td><td className="small"><span className="code">{s.source_sha256 ? `${s.source_sha256.slice(0, 12)}…` : '-'}</span></td></tr>)}
          {!(approved.sources ?? []).length && <tr><td colSpan={4} className="muted">보관된 승인 자료 목록이 없습니다.</td></tr>}</tbody></table></div>
      {receipts.length > 0 && <div className="tablewrap scrollbox" style={{ maxHeight: 200 }}><table className="tbl tight"><thead><tr><th>적용된 예정 입고</th><th>자재</th><th>입고 예정</th><th className="r">수량</th></tr></thead>
        <tbody>{receipts.map((r, i) => <tr key={r.receipt_key ?? r.po_id ?? i}><td className="small">{r.receipt_key ?? r.po_id ?? '-'}</td><td className="small">{names[r.material_id ?? ''] ?? r.material_id ?? '-'}</td><td className="small nw">{r.expected_date ?? '-'}</td><td className="r num small">{num(r.open_qty ?? r.ordered_qty, 3)} {r.unit ?? ''}</td></tr>)}</tbody></table></div>}

      <h3>검토 이력</h3>
      {decisions.length === 0 ? <p className="small muted">아직 기록된 검토가 없습니다.</p> :
        <div className="tablewrap"><table className="tbl tight"><thead><tr><th>언제</th><th>한 일</th><th>대상 안</th><th>상태</th><th>담당자</th><th>사유</th></tr></thead>
          <tbody>{decisions.map((d) => <tr key={d.decision_id}><td className="small nw">{when(d.decided_at)}</td><td>{ACTION[d.action] ?? d.action}</td><td className="small">{detail.result_snapshot.plans.find((p) => p.plan_id === d.plan_id)?.label ?? d.plan_id}</td>
            <td className="small nw">{DECISION[d.status_before] ?? d.status_before} → {DECISION[d.status_after] ?? d.status_after}</td><td className="small">{d.actor_id}{d.auth_verified ? '' : ' (미확인)'}</td><td className="small" style={{ whiteSpace: 'normal' }}>{d.reason}</td></tr>)}</tbody></table></div>}
      {final ? <p className="small muted">검토가 끝난 계획입니다. 더 기록할 수 없습니다.</p> : <>
        <div className="formrow"><label className="field">담당자 코드<input value={actor} onChange={(e) => setActor(e.target.value)} aria-invalid={!ROLE.test(actor)} /></label>
          <label className="field" style={{ flex: '2 1 240px' }}>검토·반려 사유<input value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} placeholder="예: 설비 초과 구간 확인 필요" /></label></div>
        <div className="actions"><button type="button" className="btn" disabled={!canDecide} onClick={() => void decide('REVIEW')}>검토 시작 기록</button>
          <button type="button" className="btn danger" disabled={!canDecide} onClick={() => void decide('REJECT')}>반려 기록</button>
          <button type="button" className="btn primary" disabled={!canDecide} onClick={() => void decide('APPROVE')}>정식 승인 요청</button></div>
        <p className="small muted">검토·반려는 기록만 남기는 것이고 공식 승인이 아닙니다. 정식 승인은 로그인·승인 정책이 연결될 때까지 서버가 거절합니다.</p></>}
    </div>}
  </section>;
}
