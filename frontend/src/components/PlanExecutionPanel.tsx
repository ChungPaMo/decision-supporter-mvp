import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../services/api';
import { ForecastExecutionSummary } from '../types/engine';
import { PlanCandidate, PlanDecisionAction, PlanDecisionEvent, PlanExecutionDetail, PlanExecutionSummary } from '../types/modules';
import { useProductionStore } from '../store/productionStore';
import { Notice, ROLE_CODE, errorMessage } from './ui';

type Failure = { detail?: { code?: string; message?: string } };
const codeOf = (failure: unknown) => (failure as Failure)?.detail?.code ?? '';

// 엔진·인증이 연결되기 전까지 정상적으로 돌아오는 미구현 응답. 오류가 아니라 현재 상태로 안내한다.
const NOT_IMPLEMENTED: Record<string, string> = {
  MODULE_NOT_IMPLEMENTED: '계획 엔진(MPS·RCCP·MRP)이 아직 연결되지 않아 계획을 생성할 수 없습니다. 정상적인 미구현 상태(501)이며, 예시 계획으로 대체하지 않습니다.',
  PLAN_APPROVAL_DISABLED: '정식 승인은 인증·승인 정책이 아직 구현되지 않아 사용할 수 없습니다. 정상적인 미구현 상태(501)이며, 승인된 것으로 표시하지 않습니다.',
  PLAN_HISTORY_NOT_IMPLEMENTED: '계획 이력 저장 기능이 아직 연결되지 않았습니다 (501).',
  PERSISTENCE_DISABLED: '서버 저장 기능이 꺼져 있어 계획 실행을 저장·조회할 수 없습니다 (501).',
};
const DATASET_CODES = new Set(['DATASET_NOT_FOUND', 'DATASET_INVALID', 'DATASET_INACTIVE', 'DATASET_MISMATCH']);

function describe(failure: unknown, datasetId: string): { tone: 'info' | 'bad'; text: string } | null {
  const code = codeOf(failure);
  if (code === 'DATASET_CHANGED') return null;
  if (NOT_IMPLEMENTED[code]) return { tone: 'info', text: `${NOT_IMPLEMENTED[code]} [${code}]` };
  if (DATASET_CODES.has(code)) return { tone: 'bad', text: `데이터셋 ${datasetId} 요청이 거부되었습니다 (${code}). 다른 데이터셋에서 대신 찾지 않습니다.` };
  if (code === 'PLAN_NOT_FOUND') return { tone: 'bad', text: `이 데이터셋(${datasetId})에 없는 계획 실행입니다 (PLAN_NOT_FOUND). 다른 데이터셋에서 찾지 않습니다.` };
  return { tone: 'bad', text: errorMessage(failure) };
}

export default function PlanExecutionPanel() {
  const datasetId = useProductionStore((state) => state.datasetId);
  const alive = useRef(true);
  const [forecasts, setForecasts] = useState<ForecastExecutionSummary[]>([]);
  const [forecastId, setForecastId] = useState('');
  const [items, setItems] = useState<PlanExecutionSummary[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [detail, setDetail] = useState<PlanExecutionDetail | null>(null);
  const [candidates, setCandidates] = useState<PlanCandidate[]>([]);
  const [decisions, setDecisions] = useState<PlanDecisionEvent[]>([]);
  const [planId, setPlanId] = useState('');
  const [actor, setActor] = useState('REVIEWER-01');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [historyNote, setHistoryNote] = useState<ReturnType<typeof describe>>(null);
  const [note, setNote] = useState<ReturnType<typeof describe>>(null);

  async function loadHistory() {
    setHistoryNote(null);
    try {
      const page = await apiClient.planExecutions(20, 0);
      if (alive.current) { setItems(page.items); setTotal(page.total); }
    } catch (failure) { if (alive.current) { setItems([]); setTotal(null); setHistoryNote(describe(failure, datasetId)); } }
  }

  useEffect(() => {
    alive.current = true;
    void loadHistory();
    apiClient.forecastHistory(20, 0).then((page) => {
      if (alive.current) setForecasts(page.items.filter((row) => row.status === 'OK' || row.status === 'PARTIAL'));
    }).catch(() => { /* 예측 이력 오류는 위 '실제 예측 실행 선택'에서 안내한다 */ });
    return () => { alive.current = false; };
  }, []);

  async function open(executionId: string) {
    setDetail(null); setCandidates([]); setDecisions([]); setPlanId(''); setNote(null);
    if (!executionId) return;
    setBusy(true);
    try {
      const [execution, plans, history] = await Promise.all([apiClient.getPlanExecution(executionId), apiClient.planCandidates(executionId), apiClient.planDecisions(executionId)]);
      if (!alive.current) return;
      setDetail(execution); setCandidates(plans); setDecisions(history.items); setPlanId(execution.selected_plan_id ?? plans[0]?.plan_id ?? '');
    } catch (failure) { if (alive.current) setNote(describe(failure, datasetId)); }
    finally { if (alive.current) setBusy(false); }
  }

  async function create() {
    if (!forecastId) return;
    setBusy(true); setNote(null);
    try {
      const forecast = await apiClient.getForecast(forecastId);
      const rows = forecast.result?.forecasts ?? [];
      if (!rows.length) { if (alive.current) setNote({ tone: 'bad', text: '선택한 예측 실행에 계획에 사용할 예측 결과가 없습니다.' }); return; }
      const month = rows[0].target_month;
      const reply = await apiClient.createPlanExecution({
        forecast_execution_id: forecastId, target_month: month, as_of_date: forecast.parameters.trained_until, scenario: 'BASE',
        product_ids: [...new Set(rows.filter((row) => row.target_month === month).map((row) => row.product_id))],
      });
      if (!alive.current) return;
      await loadHistory();
      await open(reply.execution.execution_id);
    } catch (failure) { if (alive.current) setNote(describe(failure, datasetId)); }
    finally { if (alive.current) setBusy(false); }
  }

  async function decide(action: PlanDecisionAction) {
    if (!detail || !planId) return;
    setBusy(true); setNote(null);
    try {
      const updated = await apiClient.decidePlan(detail.execution_id, { plan_id: planId, action, actor_id: actor, reason, expected_version: detail.version, expected_input_digest: detail.input_digest });
      if (!alive.current) return;
      setDetail(updated); setDecisions(updated.decisions); setReason('');
      await loadHistory();
    } catch (failure) { if (alive.current) setNote(describe(failure, datasetId)); }
    finally { if (alive.current) setBusy(false); }
  }

  const final = detail?.decision_status === 'APPROVED' || detail?.decision_status === 'REJECTED';
  const canDecide = !!detail && !!planId && ROLE_CODE.test(actor) && !!reason.trim() && !busy && !final;
  return <section className="panel stack" aria-label="저장 계획 실행">
    <div className="panel-heading"><div><h3>저장 계획 실행 · 이력·후보·검토</h3>
      <p className="muted">데이터셋 {datasetId}의 /plan-executions 를 조회합니다. 실제 엔진 실행만 표시하며, 서버 오류를 예시 데이터로 대체하지 않습니다.</p></div>
      <span className="badge badge-muted">엔진·정식 승인 미연결</span></div>

    <div className="stack">
      <label className="field"><span>계획 입력으로 쓸 저장 예측 실행</span><select aria-label="저장 계획 입력 예측 실행" value={forecastId} disabled={busy} onChange={(event) => setForecastId(event.target.value)}>
        <option value="">예측 실행을 선택하세요</option>{forecasts.map((row) => <option key={row.execution_id} value={row.execution_id}>{row.created_at} · {row.status} · {row.execution_id}</option>)}</select></label>
      <div className="actions start"><button type="button" className="button" disabled={busy || !forecastId} onClick={() => void create()}>{busy ? '요청 중…' : '저장 계획 실행 생성 요청'}</button>
        <button type="button" className="button" disabled={busy} onClick={() => void loadHistory()}>계획 실행 이력 새로고침</button></div>
    </div>
    {note && <div aria-live="polite"><Notice tone={note.tone}>{note.text}</Notice></div>}

    {historyNote && <Notice tone={historyNote.tone}>{historyNote.text}</Notice>}
    {total === 0 && <Notice tone="muted">이 데이터셋에 저장된 계획 실행이 없습니다 (0건). 계획 엔진이 연결되면 생성된 실행이 여기에 표시됩니다.</Notice>}
    {items.length > 0 && <label className="field"><span>저장된 계획 실행 (전체 {total}건)</span><select aria-label="저장된 계획 실행" disabled={busy} value={detail?.execution_id ?? ''} onChange={(event) => void open(event.target.value)}>
      <option value="">실행을 선택하세요</option>{items.map((row) => <option key={row.execution_id} value={row.execution_id}>{row.created_at} · {row.scenario_type} · {row.status} · 검토 {row.decision_status} · {row.execution_id}</option>)}</select></label>}

    {detail && <div className="stack">
      <dl className="meta-grid">
        <div><dt>실행 ID</dt><dd>{detail.execution_id}</dd></div><div><dt>대상 월</dt><dd>{detail.target_month}</dd></div>
        <div><dt>계산 상태</dt><dd>{detail.status}{detail.error_code ? ` · ${detail.error_code}` : ''}</dd></div><div><dt>검토 상태</dt><dd>{detail.decision_status} (v{detail.version})</dd></div>
        <div><dt>엔진 버전</dt><dd>{detail.engine_version}</dd></div><div><dt>선택 후보</dt><dd>{detail.selected_plan_id ?? '없음'}</dd></div>
      </dl>
      <p className="muted">입력 지문 <span className="code">{detail.input_digest}</span></p>
      <div className="table-scroll"><table><caption>후보 계획 (/candidates)</caption><thead><tr><th>검토 대상</th><th>안</th><th>실행 가능성</th><th>제품·월·수량</th></tr></thead>
        <tbody>{candidates.map((plan) => <tr key={plan.plan_id}><td><input type="radio" name="plan-candidate" aria-label={`${plan.label} 검토 대상`} checked={planId === plan.plan_id} disabled={final} onChange={() => setPlanId(plan.plan_id)} /></td>
          <td>{plan.label}</td><td>{plan.feasibility}</td><td>{plan.production.map((row) => `${row.product_id} / ${row.period} / ${row.production_qty} ${row.unit}`).join(' · ')}</td></tr>)}
          {!candidates.length && <tr><td colSpan={4}>반환된 후보가 없습니다.</td></tr>}</tbody></table></div>
      <div className="table-scroll"><table><caption>결정 이력 (/decisions)</caption><thead><tr><th>시각</th><th>행동</th><th>후보</th><th>상태 변화</th><th>역할 코드</th><th>사유</th></tr></thead>
        <tbody>{decisions.map((event) => <tr key={event.decision_id}><td>{event.decided_at}</td><td>{event.action}</td><td>{event.plan_id}</td><td>{event.status_before} → {event.status_after}</td>
          <td>{event.actor_id}{event.auth_verified ? '' : ' (미인증)'}</td><td>{event.reason}</td></tr>)}
          {!decisions.length && <tr><td colSpan={6}>기록된 결정이 없습니다.</td></tr>}</tbody></table></div>
      <fieldset className="stack" disabled={busy || final}><legend>검토 기록</legend>
        <label className="field"><span>검토자 역할 코드 (미인증 주장값)</span><input value={actor} onChange={(event) => setActor(event.target.value)} aria-invalid={!ROLE_CODE.test(actor)} /></label>
        <label className="field"><span>검토·반려 사유</span><input value={reason} maxLength={1000} onChange={(event) => setReason(event.target.value)} /></label>
        <div className="actions"><button type="button" className="button" disabled={!canDecide} onClick={() => void decide('REJECT')}>후보 반려 기록</button>
          <button type="button" className="button" disabled={!canDecide} onClick={() => void decide('REVIEW')}>검토 시작 기록</button>
          <button type="button" className="button primary" disabled={!canDecide} onClick={() => void decide('APPROVE')}>정식 승인 요청</button></div>
      </fieldset>
    </div>}
    <Notice tone="info">정식 승인(APPROVE)과 승인 Excel 출력은 인증·정책이 구현될 때까지 501(PLAN_APPROVAL_DISABLED)로 응답합니다. 검토·반려 기록은 미인증 역할 코드로 남으며 공식 승인이 아닙니다.</Notice>
  </section>;
}
