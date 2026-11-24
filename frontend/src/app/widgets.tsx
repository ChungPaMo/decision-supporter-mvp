// 그림으로 보여 주는 부품: 선 그래프, 묶음 막대, 링 게이지, 추세선, 가로 막대, 설비 부하 지도, 자재 부족 지도.
import { ReactNode, RefObject, useEffect, useId, useRef, useState } from 'react';
import { monthLabel, num, shortMonth } from './core';
import { LoadCell, Names } from './data';

export const C = { actual: '#5b6672', forecast: '#007f63', teal: '#4fb59c', plan: '#7fa8ee', alt: '#f2bd7a', demand: '#d3e0de', ok: '#4fb59c', warn: '#f0b45c', bad: '#e8857a' };
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
  const max = Math.max(...all) * 1.06, min = Math.min(...all) * 0.9;
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
      {[0, 1, 2, 3].map((k) => { const v = min + ((max - min) * k) / 3; return <g key={k}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="#ebf1f0" strokeDasharray={k ? '3 4' : undefined} /><text x={L - 8} y={y(v) + 4} textAnchor="end">{num(v)}</text></g>; })}
      {split !== undefined && split > 0 && split < months.length && <><rect x={x(split - 1)} y={T} width={W - R - x(split - 1)} height={H - T - B} rx="6" fill="#e8f1f0" fillOpacity="0.75" /><text x={x(split - 1) + 8} y={T + 14} style={{ fontWeight: 700, fill: '#007f63' }}>예측 구간</text></>}
      {bandPoints && <polygon points={bandPoints} fill={band!.color} fillOpacity="0.12" />}
      {series.filter((s) => s.area).map((s, i) => <path key={s.name} d={areaPath(s.values)} fill={`url(#${gid}a${i})`} />)}
      {series.map((s) => <g key={s.name}><polyline className={s.dash ? undefined : 'line'} points={path(s.values)} fill="none" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash ? '6 5' : undefined} strokeLinejoin="round" strokeLinecap="round" />
        {s.dots && s.values.map((v, i) => v !== null && <circle key={i} cx={x(i)} cy={y(v)} r="4" fill="#fff" stroke={s.color} strokeWidth="2.5" />)}</g>)}
      {months.map((m, i) => (i % every === 0 || i === months.length - 1) && <text key={m} x={x(i)} y={H - 6} textAnchor="middle">{axisMonth(m, i === 0)}</text>)}
      {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="#23282f" strokeOpacity="0.3" strokeDasharray="3 3" />}
      {hover !== null && series.map((s) => s.values[hover] !== null && <circle key={s.name} cx={x(hover)} cy={y(s.values[hover]!)} r="5" fill={s.color} stroke="#fff" strokeWidth="2.5" />)}
    </svg>
    {hover !== null && <div className="tip" style={{ left: `${Math.min(88, Math.max(12, (x(hover) / W) * 100))}%`, top: `${(T / H) * 100}%` }}><b>{monthLabel(months[hover])}</b>
      {series.map((s) => s.values[hover] !== null && <div key={s.name}><i style={{ background: s.color }} />{s.name} {num(s.values[hover])}{unit}</div>)}
      {band && band.hi[hover] !== null && band.hi[hover] !== band.lo[hover] && <div><i style={{ background: band.color, opacity: 0.5 }} />{band.name} {num(band.lo[hover])} ~ {num(band.hi[hover])}{unit}</div>}</div>}
  </div>;
}
export const Legend = ({ items }: { items: Array<[string, string, boolean?]> }) => <div className="legend">{items.map(([name, color, dash]) => <span key={name}><i style={{ background: dash ? 'transparent' : color, border: dash ? `2px dashed ${color}` : undefined }} />{name}</span>)}</div>;

// 달마다 여러 값을 나란히 세운 막대 (예: 예상 수요와 세 안의 생산량). 막대는 0에서 시작한다.
export function GroupBars({ months, groups, height = 230, unit = '' }: { months: string[]; groups: Array<{ name: string; color: string; values: number[] }>; height?: number; unit?: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const W = useWidth(box, 520);
  const H = height, L = 46, R = 8, T = 20, B = 24;
  const all = groups.flatMap((g) => g.values);
  if (!months.length || !all.some((v) => v > 0)) return <div className="empty" ref={box}>그릴 자료가 없습니다.</div>;
  const max = Math.max(...all) * 1.12;
  const band = (W - L - R) / months.length;
  const bw = Math.min(46, (band * 0.72) / groups.length), gap = 3;
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const start = (i: number) => L + band * i + (band - (bw * groups.length + gap * (groups.length - 1))) / 2;
  const compact = (v: number) => (v >= 10000 ? `${num(v / 1000, 1)}천` : num(v));
  return <div className="chart" ref={box} onMouseLeave={() => setHover(null)}>
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: H, display: 'block' }} role="img" aria-label={`${groups.map((g) => g.name).join(', ')}을 달마다 견준 막대 그래프`}>
      {[0, 0.5, 1].map((k) => <g key={k}><line x1={L} x2={W - R} y1={y((max / 1.12) * k)} y2={y((max / 1.12) * k)} stroke="#ebf1f0" strokeDasharray={k ? '3 4' : undefined} /><text x={L - 8} y={y((max / 1.12) * k) + 4} textAnchor="end">{compact((max / 1.12) * k)}</text></g>)}
      {months.map((m, i) => <g key={m} onMouseEnter={() => setHover(i)}>
        <rect x={L + band * i} y={T - 8} width={band} height={H - T - B + 8} fill={hover === i ? '#e8f1f0' : 'transparent'} rx="8" />
        {groups.map((g, k) => { const v = g.values[i] ?? 0; const bx = start(i) + k * (bw + gap);
          return <g key={g.name}><rect className="bar" x={bx} y={y(v)} width={bw} height={Math.max(0, H - B - y(v))} rx={Math.min(5, bw / 3)} fill={g.color} style={{ animationDelay: `${(i * groups.length + k) * 40}ms` }} />
            {bw >= 30 && <text x={bx + bw / 2} y={y(v) - 5} textAnchor="middle" style={{ fontSize: 10, fontWeight: 700, fill: '#383e47' }}>{compact(v)}</text>}</g>; })}
        <text x={L + band * (i + 0.5)} y={H - 6} textAnchor="middle" style={{ fontWeight: 700 }}>{monthLabel(m)}</text></g>)}
    </svg>
    {hover !== null && <div className="tip" style={{ left: `${((L + band * (hover + 0.5)) / W) * 100}%`, top: `${(T / H) * 100}%` }}><b>{monthLabel(months[hover])}</b>
      {groups.map((g) => <div key={g.name}><i style={{ background: g.color }} />{g.name} {num(g.values[hover])}{unit}</div>)}</div>}
  </div>;
}

// 링 게이지: 한도나 목표에 견준 비율 하나를 크게 보여 준다.
export function Ring({ value, label, sub, center, size = 92, stroke = 10, tone, dark }: { value: number | null; label?: ReactNode; sub?: ReactNode; center?: string; size?: number; stroke?: number; tone?: 'ok' | 'warn' | 'bad'; dark?: boolean }) {
  const [on, setOn] = useState(false);
  useEffect(() => { const t = requestAnimationFrame(() => setOn(true)); return () => cancelAnimationFrame(t); }, []);
  const r = (size - stroke) / 2, len = 2 * Math.PI * r;
  const shown = value === null ? 0 : Math.max(0, Math.min(100, value));
  const color = tone === 'bad' ? (dark ? '#ff8d82' : C.bad) : tone === 'warn' ? (dark ? '#ffc766' : C.warn) : dark ? '#7cf0cf' : C.teal;
  const text = center ?? (value === null ? '-' : `${num(value, 0)}%`);
  return <div className="ring" role="img" aria-label={`${typeof label === 'string' ? label : ''} ${text}`}>
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={dark ? 'rgba(255,255,255,0.16)' : '#ebf1f0'} strokeWidth={stroke} />
      <circle className="arc" cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={len} strokeDashoffset={on ? len * (1 - shown / 100) : len} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" style={{ fontSize: size * (text.length > 4 ? 0.2 : 0.25) }}>{text}</text>
    </svg>
    {label && <span className="lab">{label}</span>}{sub && <span className="sub">{sub}</span>}
  </div>;
}

// 작은 추세선: 숫자 옆에 "어떻게 움직여 왔는지"를 곁들인다.
export function Spark({ values, color = C.forecast, width = 96, height = 40 }: { values: number[]; color?: string; width?: number; height?: number }) {
  const gid = useId().replace(/:/g, '');
  if (values.length < 2) return null;
  const max = Math.max(...values), min = Math.min(...values), pad = 4;
  const x = (i: number) => pad + (i / (values.length - 1)) * (width - pad * 2);
  const y = (v: number) => pad + (1 - (v - min) / (max - min || 1)) * (height - pad * 2);
  const line = values.map((v, i) => `${x(i)},${y(v)}`).join(' ');
  return <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
    <defs><linearGradient id={gid} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity="0.28" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
    <path d={`M${x(0)},${height} L${line.replace(/ /g, ' L')} L${x(values.length - 1)},${height} Z`} fill={`url(#${gid})`} />
    <polyline points={line} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    <circle cx={x(values.length - 1)} cy={y(values[values.length - 1])} r="3.2" fill="#fff" stroke={color} strokeWidth="2" />
  </svg>;
}
// 작은 세로 막대 묶음 (달별 값 서너 개)
export function MiniBars({ values, color = C.plan, width = 84, height = 40 }: { values: number[]; color?: string; width?: number; height?: number }) {
  if (!values.length) return null;
  const max = Math.max(...values, 1), bw = Math.min(18, (width - (values.length - 1) * 5) / values.length);
  const total = bw * values.length + 5 * (values.length - 1);
  return <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" className="chart">
    {values.map((v, i) => { const h = Math.max(3, (v / max) * (height - 4)); return <rect className="bar" key={i} x={width - total + i * (bw + 5)} y={height - h} width={bw} height={h} rx="4" fill={color} fillOpacity={i === values.length - 1 ? 1 : 0.55} />; })}
  </svg>;
}
// 몇 개 중 몇 개 (점으로)
export function Dots({ total, on, color = C.teal }: { total: number; on: number; color?: string }) {
  return <svg width={total * 20} height={40} viewBox={`0 0 ${total * 20} 40`} aria-hidden="true">{Array.from({ length: total }, (_, i) => <circle key={i} cx={10 + i * 20} cy={20} r="7" fill={i < on ? color : '#dbe5e3'} />)}</svg>;
}

// 가로 막대: 목표(검은 눈금)에 견줘 얼마나 채웠는지. 줄마다 자기 목표에 맞춘다.
export function TargetBars({ rows, narrow }: { rows: Array<{ key: string; label: ReactNode; value: number; target: number; unit?: string }>; narrow?: boolean }) {
  if (!rows.length) return <div className="empty">그릴 자료가 없습니다.</div>;
  const SCALE = 1.12;        // 목표의 112%까지 그린다. 눈금은 100% 자리에 선다.
  return <div className={`hbars${narrow ? ' narrow' : ''}`}>{rows.map((r, i) => { const ratio = r.target > 0 ? r.value / r.target : null;
    return <div className="row" key={r.key}><div style={{ minWidth: 0 }}>{r.label}</div>
      <div className="track" title={`목표 ${num(r.target)}${r.unit ?? ''}`}><i className={ratio === null || ratio >= 0.995 ? '' : ratio >= 0.9 ? 'short' : 'bad'} style={{ width: `${Math.min(100, ((ratio ?? 0) / SCALE) * 100)}%`, animationDelay: `${i * 40}ms` }} />{ratio !== null && <u style={{ left: `${100 / SCALE}%` }} />}</div>
      <div className="val num">{ratio === null ? '-' : `${num(ratio * 100, 0)}%`} <small>{num(r.value)} / {num(r.target)}</small></div></div>; })}</div>;
}

// 사용률에 따른 색 단계: 여유 → 보통 → 높음 → 빠듯 → 초과
export const heatLevel = (pct: number | null) => (pct === null ? 'na' : pct > 100 ? 'l4' : pct >= 90 ? 'l3' : pct >= 70 ? 'l2' : pct >= 40 ? 'l1' : '');
export function HeatLegend() {
  return <div className="legend"><span><i style={{ background: 'var(--h0)' }} />40% 미만</span><span><i style={{ background: 'var(--h1)' }} />40~70%</span><span><i style={{ background: 'var(--h2)' }} />70~90%</span><span><i style={{ background: 'var(--h3)' }} />90~100% 빠듯</span><span><i style={{ background: 'var(--h4)' }} />100% 초과</span></div>;
}
// 설비·인력(행) × 달(열) 부하 지도. 막히는 칸이 색으로 바로 보인다.
export function LoadMap({ months, rows, names, selected, onPick, compact }: {
  months: string[]; rows: Array<{ id: string; kind: string; cells: Record<string, LoadCell> }>; names: Names;
  selected?: { id: string; kind: string; month: string } | null; onPick?: (pick: { id: string; kind: string; month: string }) => void; compact?: boolean;
}) {
  if (!rows.length) return <div className="empty">설비·인력 부하 자료가 없습니다.</div>;
  return <div className="heat" role="table" aria-label="설비와 인력의 달별 사용률" style={{ gridTemplateColumns: `minmax(120px, ${compact ? '1.2fr' : '1.6fr'}) repeat(${months.length}, minmax(64px, 1fr))` }}>
    <div className="hd" style={{ textAlign: 'left' }}>설비·인력</div>{months.map((m) => <div className="hd" key={m}>{monthLabel(m)}</div>)}
    {rows.map((row) => { const key = `${row.id}|${row.kind}`;
      return [<div className="rl" key={key} title={`${names[row.id] ?? row.id} (${row.id})`}><b>{names[row.id] ?? row.id}</b><span className="code">{row.id}{row.kind === 'WORK_HOURS' ? ' · 인력' : ' · 설비'}</span></div>,
        ...months.map((m) => { const cell = row.cells[m];
          const body: ReactNode = !cell ? '-' : cell.pct === null ? <>자료 없음</> : <>{num(cell.pct, 0)}%{!compact && <small>{num(cell.used, 0)} / {num(cell.limit, 0)}{cell.unit}</small>}</>;
          const fill = cell && cell.pct !== null ? <u><b style={{ width: `${Math.min(100, cell.pct)}%` }} /></u> : null;
          const cls = `cl ${cell ? heatLevel(cell.pct) : 'na'}${selected && selected.id === row.id && selected.kind === row.kind && selected.month === m ? ' sel' : ''}`;
          const label = `${names[row.id] ?? row.id} ${monthLabel(m)} ${cell?.pct == null ? '자료 없음' : `사용률 ${num(cell.pct, 0)}%`}`;
          return onPick && cell ? <button type="button" key={`${key}-${m}`} className={cls} aria-label={label} onClick={() => onPick({ id: row.id, kind: row.kind, month: m })}><span>{body}</span>{fill}</button>
            : <div key={`${key}-${m}`} className={cls} aria-label={label}><span>{body}</span>{fill}</div>; })]; })}
  </div>;
}

// 자재(행) × 달(열) 부족 지도. 칸이 진할수록 필요한 양에 비해 많이 모자란다.
export function ShortMap({ months, list, names }: { months: string[]; list: Array<{ material_id: string; period: string; shortage: number; required: number; unit: string }>; names: Names }) {
  const ids = [...new Set(list.map((m) => m.material_id))];
  const worst = (id: string) => Math.max(...list.filter((m) => m.material_id === id).map((m) => m.shortage / (m.required || 1)));
  ids.sort((a, b) => worst(b) - worst(a));
  const level = (ratio: number) => (ratio >= 0.7 ? 's4' : ratio >= 0.35 ? 's3' : ratio >= 0.1 ? 's2' : 's1');
  return <div className="shortmap" role="table" aria-label="자재별 달별 부족량" style={{ gridTemplateColumns: `minmax(130px, 1.6fr) repeat(${months.length}, minmax(70px, 1fr))` }}>
    <div className="hd" style={{ textAlign: 'left' }}>자재</div>{months.map((m) => <div className="hd" key={m}>{monthLabel(m)}</div>)}
    {ids.map((id) => [<div className="name" key={id} style={{ justifyContent: 'center' }} title={`${names[id] ?? id} (${id})`}><b>{names[id] ?? id}</b><span className="code">{id}</span></div>,
      ...months.map((m) => { const hit = list.find((x) => x.material_id === id && x.period === m);
        if (!hit) return <div className="cl" key={`${id}-${m}`} aria-label={`${names[id] ?? id} ${monthLabel(m)} 부족 없음`}>·</div>;
        const ratio = hit.shortage / (hit.required || 1);
        return <div className={`cl ${level(ratio)}`} key={`${id}-${m}`} title={`필요 ${num(hit.required)}${hit.unit} 중 ${num(hit.shortage)}${hit.unit} 부족`} aria-label={`${names[id] ?? id} ${monthLabel(m)} ${num(hit.shortage)}${hit.unit} 부족`}><span>-{num(hit.shortage)}<small>필요량의 {num(ratio * 100, 0)}%</small></span></div>; })])}
  </div>;
}
export function ShortLegend() {
  return <div className="legend"><span><i style={{ background: 'var(--h0)' }} />부족 없음</span><span><i style={{ background: '#fdf1dc' }} />10% 미만</span><span><i style={{ background: '#fbdcc0' }} />10~35%</span><span><i style={{ background: '#f7c1ba' }} />35~70%</span><span><i style={{ background: '#ee9a90' }} />70% 이상</span></div>;
}
