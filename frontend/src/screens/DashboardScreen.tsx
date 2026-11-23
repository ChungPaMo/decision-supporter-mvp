import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../services/api';
import { BatchSummary, Entity } from '../types/api';
import { ForecastExecutionSummary } from '../types/engine';
import { ENTITY_ORDER, Step, useProductionStore } from '../store/productionStore';
import { BatchBadge, ENTITY_LABEL, Notice, ScreenHeader, errorMessage, qty } from '../components/ui';

// 담당자용 첫 화면. 지표를 나열하지 않고 "지금 처리할 일"을 한 줄에 하나씩 보여준다.
// 모든 내용은 서버에서 읽은 상태로만 만든다. 읽지 못한 항목은 비워 두고 예시 값으로 채우지 않는다.

type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'muted';
type Task = { key: string; tone: Tone; state: string; title: string; reason: string; action?: { label: string; go: () => void }; blocked?: string };
type Load<T> = { value: T | null; error: string };
const EMPTY = { value: null, error: '' };
const message = (failure: unknown) => {
  const detail = (failure as { detail?: { code?: string; message?: string } })?.detail;
  return detail?.code ? `${detail.message ?? '요청 실패'} (${detail.code})` : errorMessage(failure);
};
const when = (iso?: string | null) => {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};
const MASTERS: Entity[] = ['product', 'material'];

export default function DashboardScreen() {
  const { datasetId, datasets, setStep, setActiveEntity } = useProductionStore();
  const alive = useRef(true);
  const [batches, setBatches] = useState<Load<BatchSummary[]>>(EMPTY);
  const [forecast, setForecast] = useState<Load<{ total: number; latest: ForecastExecutionSummary | null }>>(EMPTY);
  const [plans, setPlans] = useState<Load<number>>(EMPTY);
  const [readAt, setReadAt] = useState('');
  const [busy, setBusy] = useState(false);
  const dataset = datasets?.find((item) => item.dataset_id === datasetId);

  async function load() {
    setBusy(true);
    const keep = (failure: unknown) => alive.current && (failure as { detail?: { code?: string } })?.detail?.code !== 'DATASET_CHANGED';
    await Promise.all([
      apiClient.allBatches().then((list) => { if (alive.current) setBatches({ value: list, error: '' }); }).catch((failure) => { if (keep(failure)) setBatches({ value: null, error: message(failure) }); }),
      apiClient.forecastHistory(1, 0).then((page) => { if (alive.current) setForecast({ value: { total: page.total, latest: page.items[0] ?? null }, error: '' }); }).catch((failure) => { if (keep(failure)) setForecast({ value: null, error: message(failure) }); }),
      apiClient.planExecutions(1, 0).then((page) => { if (alive.current) setPlans({ value: page.total, error: '' }); }).catch((failure) => { if (keep(failure)) setPlans({ value: null, error: message(failure) }); }),
    ]);
    if (alive.current) { setReadAt(when(new Date().toISOString())); setBusy(false); }
  }
  useEffect(() => { alive.current = true; void load(); return () => { alive.current = false; }; }, []);

  const openData = (entity: Entity, step: Step = 'data') => { setActiveEntity(entity); setStep(step); };
  const list = batches.value;
  const of = (entity: Entity) => list?.filter((item) => item.entity === entity) ?? [];
  const approvedOf = (entity: Entity) => of(entity).filter((item) => item.status === 'APPROVED');
  const mastersReady = MASTERS.every((entity) => approvedOf(entity).length > 0);
  const approvedCount = ENTITY_ORDER.filter((entity) => approvedOf(entity).length > 0).length;
  const demandApprovedAt = approvedOf('monthly_demand').map((item) => item.approved_at ?? '').sort().pop() ?? '';
  const latest = forecast.value?.latest ?? null;
  const forecastOk = !!latest && (latest.status === 'OK' || latest.status === 'PARTIAL');
  // 예측을 만든 뒤에 월별 수요가 새로 승인됐으면, 그 예측은 최신 수요를 반영하지 않는다.
  const forecastStale = forecastOk && !!demandApprovedAt && new Date(demandApprovedAt).getTime() > new Date(latest!.created_at).getTime();

  const tasks: Task[] = [];
  if (list) {
    for (const entity of ENTITY_ORDER) {
      const label = ENTITY_LABEL[entity];
      const pending = of(entity).find((item) => item.status === 'READY_FOR_APPROVAL' || item.status === 'HAS_ERRORS' || item.status === 'MAPPING_HOLD');
      const needsMasters = !MASTERS.includes(entity) && !mastersReady;
      if (pending?.status === 'HAS_ERRORS') tasks.push({ key: entity, tone: 'bad', state: '오류', title: `${label} 파일의 오류를 고쳐 다시 등록`, reason: `${pending.file.name} — ${pending.approval_blockers.map((item) => item.message).join(' ') || '검증 오류가 있어 승인할 수 없습니다.'}`, action: { label: '오류 보기', go: () => openData(entity, 'verify') } });
      else if (pending?.status === 'MAPPING_HOLD') tasks.push({ key: entity, tone: 'warn', state: '확인 필요', title: `${label}의 열을 지정하고 재검증`, reason: `${pending.file.name} — 필수 열을 자동으로 정하지 못했습니다.`, action: { label: '열 지정하기', go: () => openData(entity, 'verify') } });
      else if (pending?.status === 'READY_FOR_APPROVAL') tasks.push({ key: entity, tone: 'info', state: '승인 대기', title: `${label} 검증 결과를 확인하고 승인`, reason: `${pending.file.name} — 검증을 통과했습니다. 담당자 승인이 필요합니다.`, action: { label: '검토·승인', go: () => openData(entity, 'verify') } });
      else if (!approvedOf(entity).length) tasks.push({ key: entity, tone: 'muted', state: '미등록', title: `${label} 파일 등록`, reason: needsMasters ? '제품과 자재를 먼저 승인해야 등록할 수 있습니다.' : '아직 등록된 파일이 없습니다.', blocked: needsMasters ? '제품·자재 승인 후' : undefined, action: needsMasters ? undefined : { label: '등록하기', go: () => openData(entity) } });
    }
    const hasDemand = approvedOf('monthly_demand').length > 0;
    if (forecast.value) {
      if (!hasDemand) tasks.push({ key: 'forecast', tone: 'muted', state: '대기', title: '수요예측 실행', reason: '월별 수요가 승인되어야 예측할 수 있습니다.', blocked: '월별 수요 승인 후' });
      else if (!latest) tasks.push({ key: 'forecast', tone: 'info', state: '실행 필요', title: '수요예측 실행', reason: '승인된 월별 수요가 있고, 저장된 예측이 없습니다.', action: { label: '예측하기', go: () => setStep('forecast') } });
      else if (!forecastOk) tasks.push({ key: 'forecast', tone: 'bad', state: '실패', title: '수요예측 다시 실행', reason: `최근 예측이 완료되지 않았습니다 (${latest.status}).`, action: { label: '예측 화면', go: () => setStep('forecast') } });
      else if (forecastStale) tasks.push({ key: 'forecast', tone: 'warn', state: '다시 필요', title: '수요예측 다시 실행', reason: `월별 수요가 ${when(demandApprovedAt)}에 새로 승인됐습니다. 최근 예측(${when(latest.created_at)})은 그 이전 자료 기준입니다.`, action: { label: '예측하기', go: () => setStep('forecast') } });
    }
  }
  const actionable = tasks.filter((task) => task.action);
  const waiting = tasks.filter((task) => !task.action);

  const stages: Array<{ label: string; state: string; tone: Tone; detail: string; go: () => void }> = [
    { label: '데이터 준비', state: !list ? '미확인' : approvedCount === ENTITY_ORDER.length ? '완료' : `${approvedCount} / ${ENTITY_ORDER.length} 승인`, tone: !list ? 'muted' : approvedCount === ENTITY_ORDER.length ? 'ok' : 'info', detail: '등록 → 검증 → 승인', go: () => setStep('data') },
    { label: '수요예측', state: !forecast.value ? '미확인' : !latest ? '예측 없음' : !forecastOk ? '실패' : forecastStale ? '다시 필요' : '완료', tone: !forecast.value || !latest ? 'muted' : !forecastOk ? 'bad' : forecastStale ? 'warn' : 'ok', detail: latest ? `기준일 ${latest.parameters.trained_until} · ${latest.parameters.horizon_months}개월` : '승인된 월별 수요로 예측', go: () => setStep('forecast') },
    { label: '생산계획', state: plans.value == null ? '미확인' : plans.value > 0 ? `저장 ${plans.value}건` : '계산 엔진 연결 전', tone: plans.value ? 'ok' : 'muted', detail: 'MPS·능력·자재 검토', go: () => setStep('plans') },
  ];

  return <div className="screen dashboard">
    <ScreenHeader title="오늘 할 일" description="이 데이터셋에서 지금 처리할 일과 자료의 기준 시점을 보여줍니다. 서버에서 읽은 상태만 표시하며, 읽지 못한 항목은 비워 둡니다." />
    <div className="dash-meta">
      <p><strong>{dataset?.dataset_name ?? datasetId}</strong>{dataset && <span className={`badge badge-${dataset.status === 'ACTIVE' ? 'ok' : 'muted'}`}>{dataset.status === 'ACTIVE' ? '사용 중' : '보관됨'}</span>}
        <span className="muted">{datasetId}{dataset ? ` · ${dataset.source_type === 'SYNTHETIC' ? '합성 데이터' : dataset.source_type}` : ''}</span></p>
      <p className="muted" role="status">{busy ? '서버에서 읽는 중…' : `${readAt} 기준`} <button type="button" className="button" disabled={busy} onClick={() => void load()}>새로고침</button></p>
    </div>

    <ol className="dash-stages" aria-label="진행 단계">{stages.map((stage, i) => <li key={stage.label}><button type="button" onClick={stage.go}>
      <span className="dash-stage-no">{i + 1}</span><span className="dash-stage-text"><strong>{stage.label}</strong><small>{stage.detail}</small></span>
      <span className={`badge badge-${stage.tone}`}>{stage.state}</span></button></li>)}</ol>

    <section className="panel stack" aria-label="지금 처리할 일">
      <div className="panel-heading"><h3>지금 처리할 일 {list && <span className="dash-count">{actionable.length}건</span>}</h3></div>
      {batches.error && <Notice tone="bad">등록·승인 현황을 읽지 못했습니다. {batches.error}</Notice>}
      {forecast.error && <Notice tone="warn">예측 이력을 읽지 못했습니다. {forecast.error}</Notice>}
      {!list && !batches.error && <p className="muted">서버에서 읽는 중입니다…</p>}
      {list && actionable.length === 0 && <Notice tone="ok">지금 처리할 일이 없습니다. 등록·승인과 예측이 모두 끝났습니다.</Notice>}
      {actionable.length > 0 && <ul className="dash-tasks">{actionable.map((task, index) => <li key={task.key}>
        <span className={`badge badge-${task.tone}`}>{task.state}</span>
        <div><strong>{task.title}</strong><small>{task.reason}</small></div>
        <button type="button" className={`button${index === 0 ? ' primary' : ''}`} onClick={task.action!.go}>{task.action!.label}</button></li>)}</ul>}
      {waiting.length > 0 && <details><summary>앞 단계가 끝나야 할 수 있는 일 {waiting.length}건</summary>
        <ul className="dash-tasks waiting">{waiting.map((task) => <li key={task.key}><span className="badge badge-muted">{task.blocked ?? task.state}</span>
          <div><strong>{task.title}</strong><small>{task.reason}</small></div></li>)}</ul></details>}
    </section>

    <section className="panel stack" aria-label="자료 기준"><h3>자료 기준 — 어떤 파일이 언제 승인됐는가</h3>
      {list && <div className="table-scroll full"><table><thead><tr><th>데이터 종류</th><th>상태</th><th>승인된 파일</th><th>반영 건수</th><th>승인 시각</th><th>승인자</th><th>보기</th></tr></thead>
        <tbody>{ENTITY_ORDER.map((entity) => { const approved = approvedOf(entity); const first = approved[0] ?? of(entity)[0];
          const count = approved.reduce((sum, item) => sum + (item.approved_record_count ?? 0), 0);
          const last = approved.map((item) => item.approved_at ?? '').sort().pop();
          return <tr key={entity}><td>{ENTITY_LABEL[entity]}</td><td>{first ? <BatchBadge status={approved.length ? 'APPROVED' : first.status} /> : '미등록'}</td>
            <td>{approved.length ? `${approved[0].file.name}${approved.length > 1 ? ` 외 ${approved.length - 1}개` : ''}` : '-'}</td>
            <td>{approved.length ? `${qty(count)}건` : '-'}</td><td>{when(last)}</td><td>{approved[0]?.approved_by ?? '-'}</td>
            <td><button type="button" onClick={() => openData(entity, 'verify')}>열기</button></td></tr>; })}</tbody></table></div>}
      {!list && !batches.error && <p className="muted">서버에서 읽는 중입니다…</p>}
    </section>

    <section className="panel stack" aria-label="최근 수요예측"><h3>최근 수요예측</h3>
      {forecast.value && !latest && <p className="muted">저장된 예측이 없습니다.</p>}
      {latest && <>
        <dl className="meta-grid">
          <div><dt>상태</dt><dd>{forecastOk ? (forecastStale ? '완료 (이후 수요 변경됨)' : '완료') : latest.status}</dd></div>
          <div><dt>학습 기준일</dt><dd>{latest.parameters.trained_until}</dd></div>
          <div><dt>예측 기간</dt><dd>{latest.parameters.horizon_months}개월</dd></div>
          <div><dt>입력 → 예측</dt><dd>{qty(latest.input_row_count)}행 → {qty(latest.forecast_count)}행</dd></div>
          <div><dt>실행 시각</dt><dd>{when(latest.created_at)}</dd></div>
          <div><dt>저장된 예측</dt><dd>{forecast.value?.total ?? '-'}건</dd></div>
        </dl>
        <div className="actions start"><button type="button" className="button" onClick={() => setStep('forecast')}>예측 결과 보기</button></div>
      </>}
    </section>

    <section className="panel stack" aria-label="생산계획 상태"><h3>생산계획</h3>
      {plans.error ? <Notice tone="warn">계획 실행 이력을 읽지 못했습니다. {plans.error}</Notice>
        : <p>{plans.value == null ? '서버에서 읽는 중입니다…' : plans.value > 0 ? `저장된 계획 실행 ${plans.value}건이 있습니다.` : '저장된 계획 실행이 없습니다. 계획 계산 엔진이 아직 연결되지 않아 계획을 만들 수 없습니다.'}</p>}
      <div className="actions start"><button type="button" className="button" onClick={() => setStep('plans')}>생산계획 화면 열기</button></div>
    </section>
  </div>;
}
