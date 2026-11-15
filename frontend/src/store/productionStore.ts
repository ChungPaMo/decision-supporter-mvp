import { create } from 'zustand';
import { BatchDetail, Entity } from '../types/api';
import { PlanApproval } from '../types/engine';
import { ScenarioId } from '../services/fixtures';
import { DatasetDetail, PlanningReply } from '../types/modules';

export type Step = 'dashboard' | 'data' | 'verify' | 'forecast' | 'plans' | 'diagnosis' | 'mrp' | 'whatif' | 'approval';

export const ENTITY_ORDER: Entity[] = ['product', 'material', 'bom', 'inventory', 'monthly_demand'];

export const LEGACY_DATASET = 'TISSUE-LEGACY';
const DATASET_KEY = 'chungpamo.dataset.v1';
function storedDataset() {
  try {
    const value = localStorage.getItem(DATASET_KEY) || '';
    return /^[A-Z][A-Z0-9_-]{0,39}$/.test(value) ? value : LEGACY_DATASET;
  } catch { return LEGACY_DATASET; }
}
// 데이터셋별 localStorage 키. 기존 TISSUE-LEGACY 키는 그대로 유지한다.
export const scopedKey = (key: string, datasetId: string) => (datasetId === LEGACY_DATASET ? key : `${key}.${datasetId}`);

interface ProductionState {
  datasetId: string;
  datasets: DatasetDetail[] | null;
  setDatasets: (datasets: DatasetDetail[] | null) => void;
  setDataset: (datasetId: string) => void;
  planningView: 'DEMO' | 'LIVE';
  setPlanningView: (view: 'DEMO' | 'LIVE') => void;
  planningPreview: PlanningReply | null;
  setPlanningPreview: (preview: PlanningReply | null) => void;
  previewPlanId: string | null;
  setPreviewPlanId: (id: string) => void;
  demoPlanIndex: number;
  setDemoPlanIndex: (index: number) => void;
  step: Step;
  activeEntity: Entity;
  batches: Partial<Record<Entity, BatchDetail>>;
  approvedEntities: Partial<Record<Entity, boolean>>;
  synced: boolean;
  setWorkspace: (batches: Partial<Record<Entity, BatchDetail>>, approvedEntities: Partial<Record<Entity, boolean>>, synced: boolean) => void;
  setSynced: (synced: boolean) => void;
  scenario: ScenarioId;
  selectedPlanId: string | null;
  approvals: PlanApproval[];
  setStep: (step: Step) => void;
  setActiveEntity: (entity: Entity) => void;
  setBatch: (entity: Entity, batch: BatchDetail | undefined) => void;
  setScenario: (scenario: ScenarioId) => void;
  selectPlan: (planId: string) => void;
  addApproval: (approval: PlanApproval) => void;
}

export const useProductionStore = create<ProductionState>((set) => ({
  datasetId: storedDataset(),
  datasets: null,
  setDatasets: (datasets) => set({ datasets }),
  // 데이터셋을 바꾸면 이전 데이터셋의 배치·승인 상태·계획 미리보기·선택을 모두 버린다.
  setDataset: (datasetId) => {
    try { localStorage.setItem(DATASET_KEY, datasetId); } catch { /* 선택 저장은 선택 사항 */ }
    set({ datasetId, batches: {}, approvedEntities: {}, synced: false, planningPreview: null, previewPlanId: null, selectedPlanId: null, approvals: [], demoPlanIndex: 0, activeEntity: 'product' });
  },
  planningView: 'DEMO', setPlanningView: (planningView) => set({ planningView }),
  planningPreview: null, setPlanningPreview: (planningPreview) => set({ planningPreview, previewPlanId: planningPreview?.result.plans[0]?.plan_id ?? null }),
  previewPlanId: null, setPreviewPlanId: (previewPlanId) => set({ previewPlanId }),
  demoPlanIndex: 0, setDemoPlanIndex: (demoPlanIndex) => set({ demoPlanIndex }),
  step: typeof window !== 'undefined' && window.location.hash === '#forecast' ? 'forecast' : 'data',
  activeEntity: 'product',
  batches: {},
  approvedEntities: {},
  synced: false,
  setWorkspace: (batches, approvedEntities, synced) => set({ batches, approvedEntities, synced }),
  setSynced: (synced) => set({ synced }),
  scenario: 'BASE',
  selectedPlanId: null,
  approvals: [],
  setStep: (step) => {
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${step === 'forecast' ? '#forecast' : ''}`);
    set({ step });
  },
  setActiveEntity: (activeEntity) => set({ activeEntity }),
  setBatch: (entity, batch) => set((state) => ({ batches: { ...state.batches, [entity]: batch } })),
  setScenario: (scenario) => set({ scenario }),
  selectPlan: (selectedPlanId) => set({ selectedPlanId }),
  addApproval: (approval) => set((state) => ({ approvals: [approval, ...state.approvals] })),
}));

export const allApproved = (batches: Partial<Record<Entity, BatchDetail>>) =>
  ENTITY_ORDER.every((entity) => batches[entity]?.status === 'APPROVED');

export const mastersApproved = (batches: Partial<Record<Entity, BatchDetail>>) =>
  batches.product?.status === 'APPROVED' && batches.material?.status === 'APPROVED';
