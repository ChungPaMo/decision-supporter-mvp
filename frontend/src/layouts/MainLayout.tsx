import { ReactNode, useEffect, useState } from 'react';
import { apiClient } from '../services/api';
import { LEGACY_DATASET, Step, useProductionStore } from '../store/productionStore';
import Shell, { NAV_ITEMS, NavItem } from './Shell';

// 사이드바 항목 → 실제 업무 단계. '생산계획'은 기존 접근성 이름(생산계획 비교)을 유지한다.
const NAV: NavItem[] = NAV_ITEMS.map((item) => (item.id === 'plan' ? { ...item, name: '생산계획 비교' } : item));
const FIRST_STEP: Record<string, Step> = { dashboard: 'dashboard', upload: 'data', verify: 'verify', forecast: 'forecast', plan: 'plans', whatif: 'whatif' };
const STEP_META: Record<Step, { nav: string; crumb: string[] }> = {
  dashboard: { nav: 'dashboard', crumb: ['대시보드', '데이터셋 현황'] },
  data: { nav: 'upload', crumb: ['데이터 업로드', '파일 등록·승인'] },
  verify: { nav: 'verify', crumb: ['데이터 검증', '검증·승인·등록'] },
  forecast: { nav: 'forecast', crumb: ['수요예측', '승인 수요 예측'] },
  plans: { nav: 'plan', crumb: ['생산계획', 'MPS 3안'] },
  diagnosis: { nav: 'plan', crumb: ['생산계획', 'RCCP 능력 검토'] },
  mrp: { nav: 'plan', crumb: ['생산계획', 'MRP 자재 검토'] },
  whatif: { nav: 'whatif', crumb: ['시나리오 분석', 'What-if'] },
  approval: { nav: 'whatif', crumb: ['시나리오 분석', '최종 MPS'] },
};

const DATASET_ERRORS: Record<string, string> = {
  PERSISTENCE_DISABLED: '서버 저장 기능이 꺼져 있어 데이터셋 목록을 읽을 수 없습니다.',
  DB_UNAVAILABLE: 'DB에 연결할 수 없어 데이터셋 목록을 읽을 수 없습니다.',
  NETWORK_ERROR: '서버에 연결할 수 없어 데이터셋 목록을 읽지 못했습니다.',
};

function DatasetSelect({ onError }: { onError: (message: string) => void }) {
  const { datasetId, datasets, setDatasets, setDataset } = useProductionStore();
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true); onError('');
    try {
      const list = await apiClient.listDatasets();
      setDatasets(list);
      const current = list.find((item) => item.dataset_id === useProductionStore.getState().datasetId);
      if (!current) onError(`선택한 데이터셋 ${useProductionStore.getState().datasetId}이(가) 서버 목록에 없습니다. 다른 데이터셋을 선택하세요. 다른 데이터셋의 자료로 대신 조회하지 않습니다.`);
      else if (current.status !== 'ACTIVE') onError(`${current.dataset_id}은(는) 보관된 데이터셋이라 조회·등록할 수 없습니다 (DATASET_INACTIVE).`);
    } catch (failure) {
      const code = (failure as { detail?: { code?: string; message?: string } })?.detail?.code ?? 'NETWORK_ERROR';
      setDatasets(null);
      onError(`${DATASET_ERRORS[code] ?? (failure as { detail?: { message?: string } })?.detail?.message ?? '데이터셋 목록을 읽지 못했습니다.'} (${code}) 예시 목록으로 대체하지 않습니다.`);
    } finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  const known = datasets?.some((item) => item.dataset_id === datasetId);
  const current = datasets?.find((item) => item.dataset_id === datasetId);
  return <div className="sc-dataset">
    <label htmlFor="dataset-select">데이터셋</label>
    <select id="dataset-select" value={datasetId} disabled={loading} onChange={(event) => setDataset(event.target.value)}>
      {!known && <option value={datasetId}>{datasetId}{datasets ? ' (목록에 없음)' : ''}</option>}
      {datasets?.map((item) => <option key={item.dataset_id} value={item.dataset_id} disabled={item.status !== 'ACTIVE'}>
        {item.dataset_id}{item.status !== 'ACTIVE' ? ' (보관됨)' : ''}</option>)}
      {!datasets && datasetId !== LEGACY_DATASET && <option value={LEGACY_DATASET}>{LEGACY_DATASET}</option>}
    </select>
    {current && <span className="sc-dataset-meta" title={current.description}>{current.dataset_name} · {current.source_type === 'SYNTHETIC' ? '합성 데이터' : current.source_type}</span>}
    {!datasets && !loading && <button type="button" className="sc-btn small" onClick={() => void load()}>목록 다시 읽기</button>}
  </div>;
}

export default function MainLayout({ children }: { children: ReactNode }) {
  const { step, setStep } = useProductionStore();
  const [datasetError, setDatasetError] = useState('');
  const meta = STEP_META[step];

  return <Shell mode="real" nav={NAV} active={meta.nav} onNav={(id) => setStep(FIRST_STEP[id])} crumb={meta.crumb}
    dataset={<DatasetSelect onError={setDatasetError} />}
    topEnd={<span className="sc-draft-tag" title="데이터 등록·승인·예측은 실제 서버에 저장됩니다. 계획 계산·정식 승인은 아직 연결되지 않았습니다.">실제 서버 연결</span>}
    notice={datasetError ? <p className="sc-top-notice" aria-live="polite">{datasetError}</p> : undefined}>
    <div className={`app-main app-main-${step}`}>{children}</div>
  </Shell>;
}
