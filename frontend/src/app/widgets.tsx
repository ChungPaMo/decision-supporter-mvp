// 그림으로 보여 주는 부품: 선 그래프, 설비·인력 부하 지도, 자재 부족 지도.
import { CSSProperties, ReactNode, RefObject, useEffect, useId, useRef, useState } from 'react';
import { monthLabel, num, shortMonth } from './core';
import { LoadCell, Names } from './data';

export const C = { actual: '#6b7684', forecast: '#2563eb', teal: '#2563eb', plan: '#191f28', alt: '#b0b8c1', demand: '#d1d6db', ok: '#087a4e', warn: '#f5a524', bad: '#d92d3a' };
export interface Series { name: string; color: string; values: Array<number | null>; dash?: boolean; dots?: boolean; area?: boolean }
export interface Band { name: string; lo: Array<number | null>; hi: Array<number | null>; color: string }

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
  const all = [...series.flatMap((s) => s.values), ...(band ? [...band.lo, ...band.hi] : [])].filter((v): v is number => v !== null);
  if (months.length < 2 || !all.length) return <div className="empty" ref={box}>그릴 자료가 없습니다.</div>;
  // 세로 눈금은 딱 떨어지는 값(25,000 / 30,000 …)으로 잡는다.
  const rawMax = Math.max(...all), rawMin = Math.min(...all);
  const rough = (rawMax - rawMin || rawMax || 1) / 3, pow = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * pow).find((k) => k >= rough) ?? 10 * pow;
  const min = Math.floor(rawMin / step) * step, max = Math.max(Math.ceil(rawMax / step) * step, min + step);
  const ticks = Array.from({ length: Math.round((max - min) / step) + 1 }, (_, k) => min + k * step);
  const x = (i: number) => L + (i / (months.length - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - min) / (max - min || 1)) * (H - T - B);
  const pts = (values: Array<number | null>) => values.map((v, i) => (v === null ? null : [x(i), y(v)] as const)).filter((p): p is readonly [number, number] => p !== null);
  const path = (values: Array<number | null>) => pts(values).map((p) => p.join(',')).join(' ');
  const areaPath = (values: Array<number | null>) => { const p = pts(values); return p.length < 2 ? '' : `M${p[0][0]},${H - B} ${p.map((q) => `L${q[0]},${q[1]}`).join(' ')} L${p[p.length - 1][0]},${H - B} Z`; };
  const bandPoints = band ? [...band.hi.map((v, i) => (v === null ? null : `${x(i)},${y(v)}`)), ...band.lo.map((v, i) => (v === null ? null : `${x(i)},${y(v)}`)).reverse()].filter(Boolean).join(' ') : '';
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
      {series.filter((s) => s.area).map((s, i) => <path key={s.name} d={areaPath(s.values)} fill={`url(#${gid}a${i})`} />)}
      {series.map((s) => <g key={s.name}><polyline points={path(s.values)} fill="none" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash ? '6 5' : undefined} strokeLinejoin="round" strokeLinecap="round" />
        {s.dots && s.values.map((v, i) => v !== null && <circle key={i} cx={x(i)} cy={y(v)} r="4" fill="#fff" stroke={s.color} strokeWidth="2.5" />)}</g>)}
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
          const body: ReactNode = !cell ? '-' : cell.pct === null ? <>자료 없음</> : <>{num(cell.pct, 0)}%{!compact && <small>{num(cell.used, 0)} / {num(cell.limit, 0)}{cell.unit}</small>}</>;
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
