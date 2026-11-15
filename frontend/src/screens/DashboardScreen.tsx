import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../services/api';
import { BatchSummary, Entity } from '../types/api';
import { ENTITY_ORDER, Step, useProductionStore } from '../store/productionStore';
import { BatchBadge, ENTITY_LABEL, Notice, ScreenHeader, errorMessage } from '../components/ui';

type Count = { value: number | null; error: string };
const EMPTY: Count = { value: null, error: '' };
const message = (failure: unknown) => {
  const detail = (failure as { detail?: { code?: string; message?: string } })?.detail;
  return detail?.code ? `${detail.message ?? '요청 실패'} (${detail.code})` : errorMessage(failure);
};

const PIPELINE: Array<{ step: Step; title: string; detail: string }> = [
  { step: 'data', title: '파일 업로드·유형 분류', detail: 'CSV/XLSX 등록, 유형 추천 확인' },
  { step: 'verify', title: '검증·승인·등록', detail: '검증 결과 확인 후 담당자가 승인' },
  { step: 'forecast', title: '수요예측', detail: '승인 수요로 P50/P80/P90 예측' },
  { step: 'plans', title: '생산계획 비교', detail: 'MPS 대안·RCCP·MRP 검토' },
  { step: 'whatif', title: 'What-if·최종 선택', detail: '조건 조정 후 담당자가 결정' },
];

export default function DashboardScreen() {
  const { datasetId, datasets, setStep } = useProductionStore();
  const alive = useRef(true);
  const [batches, setBatches] = useState<BatchSummary[] | null>(null);
  const [batchError, setBatchError] = useState('');
  const [forecasts, setForecasts] = useState<Count>(EMPTY);
  const [plans, setPlans] = useState<Count>(EMPTY);
  const dataset = datasets?.find((item) => item.dataset_id === datasetId);

  useEffect(() => {
    alive.current = true;
    const guard = (failure: unknown) => alive.current && (failure as { detail?: { code?: string } })?.detail?.code !== 'DATASET_CHANGED';
    apiClient.allBatches().then((list) => { if (alive.current) setBatches(list); }).catch((failure) => { if (guard(failure)) setBatchError(message(failure)); });
    apiClient.forecastHistory(1, 0).then((page) => { if (alive.current) setForecasts({ value: page.total, error: '' }); }).catch((failure) => { if (guard(failure)) setForecasts({ value: null, error: message(failure) }); });
    apiClient.planExecutions(1, 0).then((page) => { if (alive.current) setPlans({ value: page.total, error: '' }); }).catch((failure) => { if (guard(failure)) setPlans({ value: null, error: message(failure) }); });
    return () => { alive.current = false; };
  }, []);

  const latest = (entity: Entity) => batches?.find((item) => item.entity === entity && item.status === 'APPROVED') ?? batches?.find((item) => item.entity === entity);
  return <div className="screen">
    <ScreenHeader title="데이터셋 현황" description="선택한 데이터셋의 등록·승인·예측·계획 상태를 서버에서 읽어 보여줍니다. 조회에 실패한 항목은 비워 두며 예시 값으로 채우지 않습니다." />
    <section className="panel stack" aria-label="선택한 데이터셋">
      <div className="panel-heading"><div><h3>{dataset?.dataset_name ?? datasetId}</h3><p className="muted">{dataset?.description ?? '데이터셋 상세를 읽지 못했습니다. 상단의 데이터셋 목록 상태를 확인하세요.'}</p></div>
        {dataset && <span className={`badge badge-${dataset.status === 'ACTIVE' ? 'ok' : 'muted'}`}>{dataset.status === 'ACTIVE' ? '사용 중' : '보관됨'}</span>}</div>
      <dl className="meta-grid">
        <div><dt>데이터셋 ID</dt><dd>{datasetId}</dd></div>
        <div><dt>데이터 구분</dt><dd>{dataset ? (dataset.source_type === 'SYNTHETIC' ? '합성 데이터' : dataset.source_type) : '미확인'}</dd></div>
        <div><dt>저장된 예측 실행</dt><dd>{forecasts.value == null ? '미확인' : `${forecasts.value}건`}</dd></div>
        <div><dt>저장된 계획 실행</dt><dd>{plans.value == null ? '미확인' : `${plans.value}건`}</dd></div>
      </dl>
      {forecasts.error && <Notice tone="warn">예측 이력: {forecasts.error}</Notice>}
      {plans.error && <Notice tone="warn">계획 실행 이력: {plans.error}</Notice>}
    </section>
    <section className="panel stack" aria-label="등록·승인 현황"><h3>등록·승인 현황</h3>
      {batchError && <Notice tone="bad">{batchError}</Notice>}
      {!batches && !batchError && <p className="muted">서버에서 배치 목록을 읽는 중입니다…</p>}
      {batches && <div className="table-scroll"><table><thead><tr><th>데이터 종류</th><th>상태</th><th>파일</th><th>등록 배치 수</th></tr></thead>
        <tbody>{ENTITY_ORDER.map((entity) => { const item = latest(entity); return <tr key={entity}><td>{ENTITY_LABEL[entity]}</td>
          <td>{item ? <BatchBadge status={item.status} /> : '미등록'}</td><td>{item?.file.name ?? '-'}</td><td>{batches.filter((row) => row.entity === entity).length}</td></tr>; })}</tbody></table></div>}
    </section>
    <section className="panel stack" aria-label="업무 흐름"><h3>업무 흐름</h3>
      <ol className="pipeline">{PIPELINE.map((item, i) => <li key={item.step}><button type="button" onClick={() => setStep(item.step)}>
        <b>{i + 1}</b><strong>{item.title}</strong><span>{item.detail}</span></button></li>)}</ol>
      <p className="muted">계획을 대신 확정하지 않습니다. 추천과 근거는 시스템이 제시하고, 최종 판단은 담당자가 합니다. 화면 시안 전체 흐름은 왼쪽 아래 ‘예시 시나리오’에서 볼 수 있습니다.</p>
    </section>
  </div>;
}
