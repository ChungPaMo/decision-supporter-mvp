import { create } from 'zustand';
import { MAPPING, PlanId, Quantile, RECOMMENDED, WHATIF_DEFAULT, WhatIf } from './data';

// 시나리오 시안 전용 화면 상태. 서버에 저장되지 않으며 새로고침하면 초기화된다.
interface ScenarioState {
  screen: number; // 0 = 대시보드(개요), 1~9 = 시안 화면
  go: (screen: number) => void;
  mapping: Record<string, string>;
  setMapping: (source: string, target: string) => void;
  mappingReviewed: boolean;
  setMappingReviewed: (reviewed: boolean) => void;
  approvedAt: string | null;
  approve: () => void;
  quantiles: Record<Quantile, boolean>;
  toggleQuantile: (key: Quantile) => void;
  forecastRan: boolean;
  runForecast: () => void;
  planId: PlanId;
  selectPlan: (id: PlanId) => void;
  whatIfDraft: WhatIf;
  setWhatIfDraft: (patch: Partial<WhatIf>) => void;
  whatIf: WhatIf | null; // 마지막으로 "다시 계산"한 조건
  applyDraft: () => void;
  resetWhatIf: () => void;
  reviewedAt: string | null;
  markReviewed: () => void;
  reset: () => void;
}

const stamp = () => {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
};

const initial = () => ({
  mapping: Object.fromEntries(MAPPING.map((row) => [row.source, row.recommended])),
  mappingReviewed: false,
  approvedAt: null,
  quantiles: { p50: true, p80: true, p90: true },
  forecastRan: false,
  planId: RECOMMENDED,
  whatIfDraft: WHATIF_DEFAULT,
  whatIf: null,
  reviewedAt: null,
});

export function screenFromHash(hash: string): number | null {
  const match = /^#scenario(?:\/(\d))?$/.exec(hash);
  if (!match) return null;
  return match[1] ? Number(match[1]) : 0;
}

export const useScenario = create<ScenarioState>((set) => ({
  screen: screenFromHash(typeof window === 'undefined' ? '' : window.location.hash) ?? 0,
  go: (screen) => {
    const hash = screen ? `#scenario/${screen}` : '#scenario';
    if (window.location.hash !== hash) window.history.pushState(null, '', hash);
    set({ screen });
    window.scrollTo(0, 0);
  },
  ...initial(),
  setMapping: (source, target) => set((state) => ({
    mapping: { ...state.mapping, [source]: target },
    mappingReviewed: MAPPING.find((row) => row.source === source)?.needsReview ? false : state.mappingReviewed,
  })),
  setMappingReviewed: (mappingReviewed) => set({ mappingReviewed }),
  approve: () => set({ approvedAt: stamp() }),
  toggleQuantile: (key) => set((state) => ({ quantiles: { ...state.quantiles, [key]: !state.quantiles[key] } })),
  runForecast: () => set({ forecastRan: true }),
  selectPlan: (planId) => set({ planId, reviewedAt: null }),
  setWhatIfDraft: (patch) => set((state) => ({ whatIfDraft: { ...state.whatIfDraft, ...patch } })),
  applyDraft: () => set((state) => ({ whatIf: state.whatIfDraft, reviewedAt: null })),
  resetWhatIf: () => set({ whatIfDraft: WHATIF_DEFAULT, whatIf: null, reviewedAt: null }),
  markReviewed: () => set({ reviewedAt: stamp() }),
  reset: () => set(initial()),
}));
