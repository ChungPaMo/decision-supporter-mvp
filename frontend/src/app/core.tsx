// 운영 화면 공통: 주소(해시) 이동, 표시 형식, 아이콘, 작은 UI 조각.
import { ReactNode, useEffect, useState } from 'react';
import { BatchStatus, Entity } from '../types/api';
import { ForecastExecutionSummary } from '../types/engine';

export type PageId = 'home' | 'ingest' | 'forecast' | 'plan' | 'history';
export const PAGES: Array<{ id: PageId; label: string; icon: IconName; hint: string }> = [
  { id: 'home', label: '홈', icon: 'home', hint: '지금 상태와 할 일' },
  { id: 'ingest', label: '자료 넣기', icon: 'upload', hint: '파일을 올려 승인까지' },
  { id: 'forecast', label: '수요 예측', icon: 'trend', hint: '승인된 자료로 예측' },
  { id: 'plan', label: '생산계획', icon: 'calendar', hint: '세 안 계산과 비교' },
  { id: 'history', label: '기록', icon: 'clock', hint: '자료·예측·계획 이력' },
];

export interface Route { page: PageId; params: Record<string, string> }

function parse(hash: string): Route {
  const [name, query = ''] = hash.replace(/^#\/?/, '').split('?');
  const page = (PAGES.find((p) => p.id === name)?.id ?? 'home') as PageId;
  return { page, params: Object.fromEntries(new URLSearchParams(query)) };
}

// 주소의 # 뒤를 바꿔 이동한다. 브라우저 기록에 쌓이므로 뒤로가기·앞으로가기가 그대로 동작한다.
export function go(page: PageId, params: Record<string, string | undefined> = {}) {
  const clean = Object.entries(params).filter(([, v]) => v) as Array<[string, string]>;
  const next = `#${page}${clean.length ? `?${new URLSearchParams(clean)}` : ''}`;
  if (window.location.hash !== next) window.location.hash = next;
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const sync = () => setRoute(parse(window.location.hash));
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);
  return route;
}

// ── 표시 형식 ──
export function num(value: string | number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || value === '') return '-';
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString('ko-KR', { maximumFractionDigits: digits }) : String(value);
}
export const monthLabel = (month: string) => { const [y, m] = month.split('-'); return `${y}년 ${Number(m)}월`; };
export const shortMonth = (month: string) => `${Number(month.split('-')[1])}월`;
export function addMonths(month: string, n: number): string {
  const [y, m] = month.split('-').map(Number);
  const d = new Date(Date.UTC(y, m - 1 + n, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}
export function monthEnd(month: string): string {
  const [y, m] = month.split('-').map(Number);
  return `${month}-${String(new Date(Date.UTC(y, m, 0)).getUTCDate()).padStart(2, '0')}`;
}
// 예측을 번호가 아니라 "언제 기준으로 어느 달을 예측했는지"로 읽게 한다.
export function forecastMonths(item: ForecastExecutionSummary): string[] {
  const base = item.parameters.trained_until.slice(0, 7);
  return Array.from({ length: item.parameters.horizon_months }, (_, i) => addMonths(base, i + 1));
}
export function forecastLabel(item: ForecastExecutionSummary): string {
  const months = forecastMonths(item);
  const base = item.parameters.trained_until.slice(0, 7);
  return `${monthLabel(base)} 말 기준 · ${monthLabel(months[0])}${months.length > 1 ? ` ~ ${shortMonth(months[months.length - 1])}` : ''}`;
}
export function when(iso: string | null | undefined): string {
  if (!iso) return '-';
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 60000;
  if (diff < 1) return '방금';
  if (diff < 60) return `${Math.floor(diff)}분 전`;
  if (diff < 60 * 24) return `${Math.floor(diff / 60)}시간 전`;
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
// 서버가 꺼진 것(응답 없음)과 서버는 켜져 있는데 DB 를 못 쓰는 것을 다른 말로 알린다.
const CONNECT_TEXT: Record<string, string> = {
  NETWORK_ERROR: '서버에 연결할 수 없습니다. 서버가 켜져 있는지 확인하세요.',
  DB_UNAVAILABLE: '서버는 켜져 있지만 DB에 연결하지 못했습니다. DB를 켠 뒤 다시 시도하세요.',
  PERSISTENCE_DISABLED: '서버의 DB 저장 기능이 꺼져 있어 저장·조회를 할 수 없습니다.',
  BATCH_SOURCE_MISMATCH: '고른 파일과 승인하려는 자료의 원본이 다릅니다. 승인하지 않았습니다. 파일을 다시 올려 확인하세요.',
};
export function failure(error: unknown): string {
  const detail = (error as { detail?: { code?: string; message?: string } | string })?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.code && CONNECT_TEXT[detail.code]) return `${CONNECT_TEXT[detail.code]} (${detail.code})`;
  if (detail?.message) return `${detail.message}${detail.code ? ` (${detail.code})` : ''}`;
  if (error instanceof Error) return error.message;
  return '서버에 연결할 수 없습니다. 서버가 켜져 있는지 확인하세요.';
}
export const failureCode = (error: unknown) => (error as { detail?: { code?: string } })?.detail?.code ?? '';

export const ENTITY_NAME: Record<Entity, string> = { product: '제품', material: '자재', bom: 'BOM', inventory: '재고', capacity: 'CAPA', routing: 'Routing', monthly_demand: '월별 수요', scheduled_receipt: '예정 입고' };
// 예측·계획에 꼭 필요한 일곱 가지. 예정 입고는 있으면 쓰는 선택 자료라 여기에 넣지 않는다.
export const ENTITY_ORDER: Array<Exclude<Entity, 'scheduled_receipt'>> = ['product', 'material', 'bom', 'inventory', 'capacity', 'routing', 'monthly_demand'];
export const SECTION_NAME: Record<string, string> = { resources: '자원', quantity_limits: '수량 한도', hours_budgets: '시간 예산', routing_steps: '공정 순서' };
export const BATCH_TONE: Record<BatchStatus, { label: string; tone: Tone }> = {
  MAPPING_HOLD: { label: '열 지정 필요', tone: 'warn' }, HAS_ERRORS: { label: '오류 있음', tone: 'bad' },
  READY_FOR_APPROVAL: { label: '승인 대기', tone: 'info' }, APPROVED: { label: '승인됨', tone: 'ok' }, REJECTED: { label: '반려됨', tone: 'muted' },
};
// 서버가 주는 코드를 사람이 읽는 말로 바꾼다. 모르는 코드는 서버 문구를 그대로 쓴다.
export const ISSUE_TEXT: Record<string, string> = {
  RECEIPT_SOURCE_UNAVAILABLE: '입고 예정 자료가 없어 앞으로 들어올 자재를 0으로 계산했습니다.',
  INVENTORY_MISSING: '재고 자료가 계획 시점에 없어 재고를 0으로 계산했습니다.',
  INVENTORY_COVERAGE: '재고 자료의 기준일이 계획 시점보다 뒤입니다.',
  HOURS_COVERAGE: '해당 월의 설비 가동 시간 자료가 없습니다.',
  QUANTITY_COVERAGE: '해당 월의 생산 수량 한도 자료가 없습니다.',
};

// ── 작은 UI 조각 ──
export type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'muted';
// 상태는 색 점 + 글자로 말한다. 색 딱지(Tag)는 개수를 셀 때만 쓴다.
export const St = ({ tone = 'muted', children }: { tone?: Tone; children: ReactNode }) => <span className={`st ${tone === 'muted' ? '' : tone}`}>{children}</span>;
export const Tag = ({ tone = 'muted', children }: { tone?: Tone; children: ReactNode }) => <span className={`tag ${tone === 'muted' ? '' : tone}`}>{children}</span>;
export const BatchSt = ({ status }: { status: BatchStatus }) => <St tone={BATCH_TONE[status].tone}>{BATCH_TONE[status].label}</St>;
export const FEAS: Record<string, { label: string; tone: Tone }> = { FEASIBLE: { label: '실행 가능', tone: 'ok' }, UNVERIFIED: { label: '확인 필요', tone: 'warn' }, INFEASIBLE: { label: '실행 불가', tone: 'bad' } };
export const FeasSt = ({ value }: { value: string }) => <St tone={FEAS[value]?.tone ?? 'muted'}>{FEAS[value]?.label ?? value}</St>;
export const Notice = ({ tone = 'info', children }: { tone?: 'info' | 'warn' | 'bad' | 'ok'; children: ReactNode }) => <div className={`notice ${tone === 'info' ? '' : tone}`} role={tone === 'bad' ? 'alert' : undefined}>{children}</div>;
export function Empty({ children, action }: { children: ReactNode; action?: ReactNode }) { return <div className="empty"><span>{children}</span>{action}</div>; }

// 핵심 숫자 한 칸. 숫자만 두지 않고 "무엇에 비해 얼마인지"를 아래에 붙인다.
export function Kpi({ label, value, unit, note, tone, viz }: { label: string; value: ReactNode; unit?: string; note?: ReactNode; tone?: 'ok' | 'warn' | 'bad'; viz?: ReactNode }) {
  return <div className={`kpi ${tone ?? ''}`}>{viz && <div className="viz">{viz}</div>}<span>{label}</span><strong className="num">{value}{unit && <small> {unit}</small>}</strong><em className={tone ?? ''}>{note ?? ' '}</em></div>;
}
// 코드 대신 이름을 보여 주고, 코드는 작게 곁들인다.
export function Name({ code, names }: { code: string; names: Record<string, string> }) {
  const name = names[code];
  return <span className="name" title={`${name ?? code} (${code})`}><b>{name ?? code}</b>{name && <span className="code">{code}</span>}</span>;
}
export function Meter({ label, used, limit, unit }: { label: ReactNode; used: number; limit: number | null; unit?: string }) {
  const pct = limit && limit > 0 ? (used / limit) * 100 : null;
  const tone = pct === null ? '' : pct > 100 ? 'bad' : pct >= 90 ? 'warn' : '';
  return <div className={`meter ${tone}`}><header><span>{label}</span><span className="num muted">{pct === null ? '한도 자료 없음' : `${num(used, 0)} / ${num(limit, 0)}${unit ?? ''} · ${num(pct, 0)}%`}</span></header>
    <div className="track"><i style={{ width: `${Math.min(pct ?? 0, 100)}%` }} /></div></div>;
}
export const pctText = (value: number | null) => (value === null || !Number.isFinite(value) ? '-' : `${num(value, 0)}%`);

// ── 아이콘 (선으로 그린 단순한 모양) ──
const PATHS = {
  home: 'M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10',
  upload: 'M12 16V4m0 0l-4 4m4-4l4 4M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3',
  trend: 'M3 17l6-6 4 4 8-8M15 7h6v6',
  calendar: 'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4',
  clock: 'M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2',
  menu: 'M4 6h16M4 12h16M4 18h16',
  refresh: 'M20 11a8 8 0 10-2.3 5.7M20 5v6h-6',
  check: 'M5 12l5 5 9-10',
  alert: 'M12 4l9 16H3zM12 10v4M12 17v.5',
  box: 'M3 8l9-5 9 5v8l-9 5-9-5zM3 8l9 5 9-5M12 13v8',
  file: 'M6 3h8l4 4v14H6zM14 3v4h4',
  play: 'M7 5l12 7-12 7z',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  layers: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5',
  x: 'M6 6l12 12M18 6L6 18',
  bolt: 'M13 3L5 14h6l-1 7 8-11h-6z',
} as const;
export type IconName = keyof typeof PATHS;
export const Icon = ({ name }: { name: IconName }) => <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={PATHS[name]} /></svg>;
