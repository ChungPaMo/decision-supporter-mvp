// 그림으로 보여 주는 부품: 선 그래프, 설비·인력 부하 지도, 자재 부족 지도.
import { CSSProperties, ReactNode, RefObject, useEffect, useId, useRef, useState } from 'react';
import { monthLabel, num, shortMonth } from './core';
import { LoadCell, Names } from './data';

export const C = { actual: '#6b7684', forecast: '#2563eb', teal: '#2563eb', plan: '#191f28', alt: '#b0b8c1', demand: '#d1d6db', ok: '#087a4e', warn: '#f5a524', bad: '#d92d3a' };
export interface Series { name: string; color: string; values: Array<number | null>; dash?: boolean; dots?: boolean; area?: boolean }
export interface Band { name: string; lo: Array<number | null>; hi: Array<number | null>; color: string }

// 값이 바뀌면 이전 값에서 새 값으로 부드럽게 옮겨 간다 (안을 바꾸거나 다시 계산했을 때 그래프와 숫자가 스윽 움직인다).
// 값이 없는 자리는 NaN 으로 받아 움직이지 않고 바로 바꾼다. "움직임 줄이기" 설정이 켜져 있으면 바로 바꾼다.
export function useTween(target: number[], ms = 560, groups = 1): number[] {
  const [shown, setShown] = useState(target);
  const current = useRef(target);
  const key = target.join(',');
  useEffect(() => {
    let start = current.current;
    // 점 개수가 달라졌으면 이전 모양을 새 개수에 맞게 늘이거나 줄여서, 끊기지 않고 이어지게 한다.
    if (start !== target && start.length !== target.length && groups > 0 && start.length % groups === 0 && target.length % groups === 0 && start.length >= groups * 2 && target.length >= groups * 2) {
      const from = start, a = from.length / groups, b = target.length / groups;
      start = target.map((_, i) => from[Math.floor(i / b) * a + Math.round(((i % b) / (b - 1)) * (a - 1))]);
    }
    const still = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (still || start.length !== target.length || start === target) { current.current = target; setShown(target); return; }
    let frame = 0;
    const began = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - began) / ms), eased = 1 - Math.pow(1 - k, 4);
      const next = target.map((v, i) => (Number.isFinite(v) && Number.isFinite(start[i]) ? start[i] + (v - start[i]) * eased : v));
      current.current = next; setShown(next);
      if (k < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return shown.length === target.length ? shown : target;
}
// 숫자 하나가 바뀔 때 굴러가듯 바뀐다.
export function Num({ value, digits = 0 }: { value: number; digits?: number }) { const [v] = useTween([value]); return <>{num(v, digits)}</>; }

// 그림을 놓인 칸의 실제 너비로 그려, 화면이 좁거나 넓어도 글자 크기가 변하지 않게 한다.
function useWidth(ref: RefObject<HTMLDivElement>, fallback = 760) {
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const fit = () => setW(Math.max(280, Math.round(el.clientWidth)));
    fit();
    const ro = new ResizeObserver(fit); ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}
const axisMonth = (m: string, first: boolean) => (m.endsWith('-01') || first ? `${m.slice(2, 4)}.${m.slice(5)}` : shortMonth(m));

// x 는 달(YYYY-MM) 목록. 값이 없는 달은 null 로 둔다. 구분선(split)은 "여기부터 예측"을 표시한다.
export function LineChart({ months, series, band, split, height = 240, unit = '' }: { months: string[]; series: Series[]; band?: Band; split?: number; height?: number; unit?: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const W = useWidth(box);
  const gid = useId().replace(/:/g, '');
  const H = height, L = 50, R = 14, T = 12, B = 24;
  const flat = [...series.flatMap((s) => s.values), ...(band ? [...band.lo, ...band.hi] : [])];
  const all = flat.filter((v): v is number => v !== null);
  const has = months.length >= 2 && all.length > 0;
  // 세로 눈금은 딱 떨어지는 값(25,000 / 30,000 …)으로 잡는다.
  const rawMax = has ? Math.max(...all) : 1, rawMin = has ? Math.min(...all) : 0;
  const rough = (rawMax - rawMin || rawMax || 1) / 3, pow = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * pow).find((k) => k >= rough) ?? 10 * pow;
  const min = Math.floor(rawMin / step) * step, max = Math.max(Math.ceil(rawMax / step) * step, min + step);
  const ticks = Array.from({ length: Math.round((max - min) / step) + 1 }, (_, k) => min + k * step);
  const x = (i: number) => L + (i / Math.max(1, months.length - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - min) / (max - min || 1)) * (H - T - B);
  // 값이 아니라 "그려지는 높이"를 이전 자리에서 새 자리로 옮긴다.
  // 그래서 눈금이 바뀌어도 선이 위아래에서 날아오지 않고, 제자리에서 모양만 바뀐다.
  const groups = series.length + (band ? 2 : 0);
  const heights = useTween(flat.map((v) => (v === null ? NaN : y(v))), 620, groups);
  const cut = (k: number) => heights.slice(k * months.length, (k + 1) * months.length).map((v) => (Number.isFinite(v) ? v : null));
  const drawn = series.map((s, k) => ({ ...s, ys: cut(k) }));
  const bandHi = band ? cut(series.length + 1) : [], bandLo = band ? cut(series.length) : [];
  if (!has) return <div className="empty" ref={box}>그릴 자료가 없습니다.</div>;
  const pts = (ys: Array<number | null>) => ys.map((v, i) => (v === null ? null : [x(i), v] as const)).filter((q): q is readonly [number, number] => q !== null);
  const path = (ys: Array<number | null>) => pts(ys).map((q) => q.join(',')).join(' ');
  const areaPath = (ys: Array<number | null>) => { const q = pts(ys); return q.length < 2 ? '' : `M${q[0][0]},${H - B} ${q.map((r) => `L${r[0]},${r[1]}`).join(' ')} L${q[q.length - 1][0]},${H - B} Z`; };
  const bandPoints = band ? [...bandHi.map((v, i) => (v === null ? null : `${x(i)},${v}`)), ...bandLo.map((v, i) => (v === null ? null : `${x(i)},${v}`)).reverse()].filter(Boolean).join(' ') : '';
  const every = Math.max(1, Math.ceil(months.length / Math.max(4, Math.floor(W / 70))));
  const move = (clientX: number) => {
    const rect = box.current?.getBoundingClientRect(); if (!rect) return;
    const px = ((clientX - rect.left) / rect.width) * W;
    setHover(Math.max(0, Math.min(months.length - 1, Math.round(((px - L) / (W - L - R)) * (months.length - 1)))));
  };
  return <div className="chart" ref={box} onMouseMove={(e) => move(e.clientX)} onMouseLeave={() => setHover(null)}>
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: H, display: 'block' }} role="img" aria-label={`${series.map((s) => s.name).join(', ')} 그래프. ${monthLabel(months[0])}부터 ${monthLabel(months[months.length - 1])}까지`}>
      <defs>{series.filter((s) => s.area).map((s, i) => <linearGradient key={i} id={`${gid}a${i}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={s.color} stopOpacity="0.12" /><stop offset="1" stopColor={s.color} stopOpacity="0" /></linearGradient>)}</defs>
      {ticks.map((v, k) => { return <g key={k}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="#f0f2f4" strokeDasharray={k ? '3 4' : undefined} /><text x={L - 8} y={y(v) + 4} textAnchor="end">{num(v)}</text></g>; })}
      {split !== undefined && split > 0 && split < months.length && <><rect x={x(split - 1)} y={T} width={W - R - x(split - 1)} height={H - T - B} rx="6" fill="#f7f8fa" /><text x={x(split - 1) + 8} y={T + 14} style={{ fontWeight: 500 }}>예측</text></>}
      {bandPoints && <polygon points={bandPoints} fill={band!.color} fillOpacity="0.12" />}
      {drawn.filter((s) => s.area).map((s, i) => <path key={s.name} d={areaPath(s.ys)} fill={`url(#${gid}a${i})`} />)}
      {drawn.map((s) => <g key={s.name}><polyline points={path(s.ys)} fill="none" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash ? '6 5' : undefined} strokeLinejoin="round" strokeLinecap="round" />
        {s.dots && s.ys.map((v, i) => v !== null && <circle key={i} cx={x(i)} cy={v} r="4" fill="#fff" stroke={s.color} strokeWidth="2.5" />)}</g>)}
      {months.map((m, i) => ((i % every === 0 && months.length - 1 - i >= every / 2) || i === months.length - 1) && <text key={m} x={x(i)} y={H - 6} textAnchor={i === months.length - 1 ? 'end' : 'middle'}>{axisMonth(m, i === 0)}</text>)}
      {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="#23282f" strokeOpacity="0.3" strokeDasharray="3 3" />}
      {hover !== null && series.map((s) => s.values[hover] !== null && <circle key={s.name} cx={x(hover)} cy={y(s.values[hover]!)} r="5" fill={s.color} stroke="#fff" strokeWidth="2.5" />)}
    </svg>
    {hover !== null && <div className="tip" style={{ left: `${Math.min(88, Math.max(12, (x(hover) / W) * 100))}%`, top: `${(T / H) * 100}%` }}><b>{monthLabel(months[hover])}</b>
      {series.map((s) => s.values[hover] !== null && <div key={s.name}><i style={{ background: s.color }} />{s.name} {num(s.values[hover])}{unit}</div>)}
      {band && band.hi[hover] !== null && band.hi[hover] !== band.lo[hover] && <div><i style={{ background: band.color, opacity: 0.5 }} />{band.name} {num(band.lo[hover])} ~ {num(band.hi[hover])}{unit}</div>}</div>}
  </div>;
}
export const Legend = ({ items }: { items: Array<[string, string, boolean?]> }) => <div className="legend">{items.map(([name, color, dash]) => <span key={name}><i style={{ background: dash ? 'transparent' : color, border: dash ? `2px dashed ${color}` : undefined }} />{name}</span>)}</div>;

// 사용률에 따른 색 단계: 여유 있음 → 빠듯(90% 이상) → 한도 도달·초과(99.5% 이상)
export const heatLevel = (pct: number | null) => (pct === null ? 'na' : pct >= 99.5 ? 'l4' : pct >= 90 ? 'l3' : '');
export function HeatLegend() {
  return <div className="legend"><span><i style={{ background: 'var(--h2)' }} />90% 미만</span><span><i style={{ background: 'var(--h3)' }} />90~100% 빠듯</span><span><i style={{ background: 'var(--h4)' }} />한도 도달·초과</span></div>;
}
// 설비·인력(행) × 달(열) 부하 지도. 막히는 칸이 색으로 바로 보인다.
export function LoadMap({ months, rows, names, selected, onPick, compact }: {
  months: string[]; rows: Array<{ id: string; kind: string; cells: Record<string, LoadCell> }>; names: Names;
  selected?: { id: string; kind: string; month: string } | null; onPick?: (pick: { id: string; kind: string; month: string }) => void; compact?: boolean;
}) {
  if (!rows.length) return <div className="empty">설비·인력 부하 자료가 없습니다.</div>;
  return <div className="heat" role="table" aria-label="설비와 인력의 달별 사용률" style={{ '--n': months.length } as CSSProperties}>
    <div className="hd">설비·인력</div>{months.map((m) => <div className="hd" key={m}><span className="wide">{monthLabel(m)}</span><span className="tiny">{shortMonth(m)}</span></div>)}
    {rows.map((row) => { const key = `${row.id}|${row.kind}`;
      return [<div className="rl" key={key} title={`${names[row.id] ?? row.id} (${row.id})`}><b>{names[row.id] ?? row.id}</b><span className="code">{row.id}{row.kind === 'WORK_HOURS' ? ' · 인력' : ' · 설비'}</span></div>,
        ...months.map((m) => { const cell = row.cells[m];
          const body: ReactNode = !cell ? '-' : cell.pct === null ? <>자료 없음</> : <><Num value={cell.pct} />%{!compact && <small><Num value={cell.used} /> / {num(cell.limit, 0)}{cell.unit}</small>}</>;
          const cls = `cl ${cell ? heatLevel(cell.pct) : 'na'}${selected && selected.id === row.id && selected.kind === row.kind && selected.month === m ? ' sel' : ''}`;
          const label = `${names[row.id] ?? row.id} ${monthLabel(m)} ${cell?.pct == null ? '자료 없음' : `사용률 ${num(cell.pct, 0)}%`}`;
          return onPick && cell ? <button type="button" key={`${key}-${m}`} className={cls} aria-label={label} onClick={() => onPick({ id: row.id, kind: row.kind, month: m })}><span>{body}</span></button>
            : <div key={`${key}-${m}`} className={cls} aria-label={label}><span>{body}</span></div>; })]; })}
  </div>;
}

// 자재(행) × 달(열) 부족 지도. 칸이 진할수록 필요한 양에 비해 많이 모자란다.
export function ShortMap({ months, list, names }: { months: string[]; list: Array<{ material_id: string; period: string; shortage: number; required: number; unit: string }>; names: Names }) {
  const ids = [...new Set(list.map((m) => m.material_id))];
  const worst = (id: string) => Math.max(...list.filter((m) => m.material_id === id).map((m) => m.shortage / (m.required || 1)));
  ids.sort((a, b) => worst(b) - worst(a));
  const level = (ratio: number) => (ratio >= 0.7 ? 's4' : ratio >= 0.35 ? 's3' : ratio >= 0.1 ? 's2' : 's1');
  return <div className="shortmap" role="table" aria-label="자재별 달별 부족량" style={{ '--n': months.length } as CSSProperties}>
    <div className="hd">자재</div>{months.map((m) => <div className="hd" key={m}><span className="wide">{monthLabel(m)}</span><span className="tiny">{shortMonth(m)}</span></div>)}
    {ids.map((id) => [<div className="name" key={id} style={{ justifyContent: 'center' }} title={`${names[id] ?? id} (${id})`}><b>{names[id] ?? id}</b><span className="code">{id}</span></div>,
      ...months.map((m) => { const hit = list.find((x) => x.material_id === id && x.period === m);
        if (!hit) return <div className="cl" key={`${id}-${m}`} aria-label={`${names[id] ?? id} ${monthLabel(m)} 부족 없음`}>·</div>;
        const ratio = hit.shortage / (hit.required || 1);
        return <div className={`cl ${level(ratio)}`} key={`${id}-${m}`} title={`필요 ${num(hit.required)}${hit.unit} 중 ${num(hit.shortage)}${hit.unit} 부족`} aria-label={`${names[id] ?? id} ${monthLabel(m)} ${num(hit.shortage)}${hit.unit} 부족`}><span>-{num(hit.shortage)}<small>필요량의 {num(ratio * 100, 0)}%</small></span></div>; })])}
  </div>;
}
export function ShortLegend() {
  return <div className="legend"><span><i style={{ background: 'var(--h0)' }} />부족 없음</span><span><i style={{ background: '#fff3d6' }} />10% 미만</span><span><i style={{ background: '#ffe3c2' }} />10~35%</span><span><i style={{ background: '#ffd0d4' }} />35~70%</span><span><i style={{ background: '#ffb3ba' }} />70% 이상</span></div>;
}
