import { useEffect, useRef, useState } from 'react';
import { fmt } from './data';

// 차트를 실제 표시 폭으로 그려 글자가 축소되지 않게 한다.
function useWidth(fallback: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () => { const next = Math.round(node.clientWidth); if (next > 0) setWidth(next); };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

export interface Series { key: string; label: string; color: string; dashed?: boolean; values: Array<number | null> }

interface LineProps {
  title: string; labels: string[]; series: Series[]; unit: string;
  yMin?: number; yMax: number; yStep: number; height?: number; width?: number;
  labelEvery?: number; tick?: (label: string) => string; bandFrom?: number; bandLabel?: string; endLabels?: boolean;
}

// 시안용 선 차트. 한 개의 y축, 범례 + 호버 십자선/툴팁, 표 대체 텍스트 제공.
export function LineChart({ title, labels, series, unit, yMin = 0, yMax, yStep, height = 260, width = 720, labelEvery = 1, tick, bandFrom, bandLabel, endLabels }: LineProps) {
  const [hover, setHover] = useState<number | null>(null);
  const [plot, W] = useWidth(width);
  const left = 56, right = endLabels ? 52 : 18, top = 14, bottom = 30;
  const plotW = W - left - right, plotH = height - top - bottom;
  const x = (i: number) => left + (labels.length === 1 ? plotW / 2 : (i * plotW) / (labels.length - 1));
  const y = (v: number) => top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
  const ticks: number[] = [];
  for (let v = yMin; v <= yMax + 1e-9; v += yStep) ticks.push(v);
  const path = (values: Array<number | null>) => values.map((v, i) => (v == null ? '' : `${values[i - 1] == null ? 'M' : 'L'}${x(i)},${y(v)}`)).join(' ');
  const move = (event: React.MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * W;
    const index = Math.round(((px - left) / plotW) * (labels.length - 1));
    setHover(Math.min(labels.length - 1, Math.max(0, index)));
  };
  const tipLeft = hover == null ? 0 : (x(hover) / W) * 100;
  return <figure className="sc-chart">
    {series.length > 1 && <ul className="sc-legend">{series.map((s) => <li key={s.key}>
      <svg width="26" height="10" aria-hidden="true"><line x1="1" x2="25" y1="5" y2="5" stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? '4 3' : undefined} /><circle cx="13" cy="5" r="3.2" fill={s.dashed ? '#fff' : s.color} stroke={s.color} strokeWidth="1.6" /></svg>{s.label}</li>)}</ul>}
    <div className="sc-chart-plot" ref={plot}>
      <svg viewBox={`0 0 ${W} ${height}`} width={W} height={height} role="img" aria-label={`${title} (${unit})`} onMouseMove={move} onMouseLeave={() => setHover(null)}>
        {bandFrom != null && <g><rect x={x(bandFrom)} y={top} width={x(labels.length - 1) - x(bandFrom)} height={plotH} fill="#1d5fd6" opacity="0.07" />
          <line x1={x(bandFrom)} x2={x(bandFrom)} y1={top} y2={top + plotH} stroke="#94a3b8" strokeDasharray="3 3" />
          {bandLabel && <text x={(x(bandFrom) + x(labels.length - 1)) / 2} y={top + 13} textAnchor="middle" className="sc-chart-note">{bandLabel}</text>}</g>}
        {ticks.map((t) => <g key={t}><line x1={left} x2={W - right} y1={y(t)} y2={y(t)} stroke={t === yMin ? '#94a3b8' : '#e5eaf1'} />
          <text x={left - 8} y={y(t) + 4} textAnchor="end" className="sc-chart-tick">{fmt(t)}</text></g>)}
        {labels.map((label, i) => i % labelEvery === 0 && <text key={label} x={x(i)} y={height - 9} textAnchor="middle" className="sc-chart-tick">{tick ? tick(label) : label}</text>)}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={top} y2={top + plotH} stroke="#64748b" strokeWidth="1" />}
        {series.map((s) => <g key={s.key}>
          <path d={path(s.values)} fill="none" stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? '5 4' : undefined} strokeLinejoin="round" />
          {s.values.map((v, i) => v != null && <circle key={i} cx={x(i)} cy={y(v)} r={hover === i ? 5 : 3.6} fill={s.dashed ? '#fff' : s.color} stroke={s.dashed ? s.color : '#fff'} strokeWidth="1.6" />)}
          {endLabels && (() => { const i = s.values.length - 1; const v = s.values[i]; return v == null ? null : <text x={x(i) + 9} y={y(v) + 4} className="sc-chart-end">{s.label}</text>; })()}
        </g>)}
      </svg>
      {hover != null && <div className={`sc-tip${tipLeft > 60 ? ' flip' : ''}`} style={{ left: `${tipLeft}%` }} role="presentation">
        <strong>{labels[hover]}</strong>
        {series.filter((s) => s.values[hover] != null).map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}<b>{fmt(s.values[hover]!)} {unit}</b></span>)}
      </div>}
    </div>
    <figcaption className="visually-hidden">{series.map((s) => `${s.label}: ${s.values.map((v, i) => (v == null ? '' : `${labels[i]} ${fmt(v)}${unit}`)).filter(Boolean).join(', ')}`).join(' / ')}</figcaption>
  </figure>;
}

interface BarProps { title: string; labels: string[]; series: Array<{ key: string; label: string; color: string; values: number[] }>; unit: string; yMin: number; yMax: number; yStep: number; limit?: { value: number; label: string }; height?: number }

// 묶음 막대 차트. 모든 막대에 값 라벨(막대 수가 적음), 한도선 표시.
export function BarChart({ title, labels, series, unit, yMin, yMax, yStep, limit, height = 240 }: BarProps) {
  const [hover, setHover] = useState<string | null>(null);
  const [plot, W] = useWidth(420);
  const left = 44, right = 14, top = 22, bottom = 30;
  const plotW = W - left - right, plotH = height - top - bottom;
  const group = plotW / labels.length;
  const barW = Math.min(34, (group - 24) / series.length - 2);
  const y = (v: number) => top + plotH - ((Math.min(yMax, Math.max(yMin, v)) - yMin) / (yMax - yMin)) * plotH;
  const ticks: number[] = [];
  for (let v = yMin; v <= yMax; v += yStep) ticks.push(v);
  return <figure className="sc-chart">
    <ul className="sc-legend">{series.map((s) => <li key={s.key}><i style={{ background: s.color }} />{s.label}</li>)}
      {limit && <li><svg width="22" height="10" aria-hidden="true"><line x1="0" x2="22" y1="5" y2="5" stroke="#b42318" strokeWidth="1.5" strokeDasharray="4 3" /></svg>{limit.label}</li>}</ul>
    <div className="sc-chart-plot" ref={plot}>
      <svg viewBox={`0 0 ${W} ${height}`} width={W} height={height} role="img" aria-label={`${title} (${unit})`}>
        {ticks.map((t) => <g key={t}><line x1={left} x2={W - right} y1={y(t)} y2={y(t)} stroke={t === yMin ? '#94a3b8' : '#e5eaf1'} />
          <text x={left - 8} y={y(t) + 4} textAnchor="end" className="sc-chart-tick">{t}{unit}</text></g>)}
        {labels.map((label, gi) => <g key={label}>
          <text x={left + group * gi + group / 2} y={height - 9} textAnchor="middle" className="sc-chart-tick">{label}</text>
          {series.map((s, si) => {
            const bx = left + group * gi + group / 2 - (series.length * (barW + 2)) / 2 + si * (barW + 2) + 1;
            const value = s.values[gi];
            const id = `${s.key}-${gi}`;
            return <g key={s.key} onMouseEnter={() => setHover(id)} onMouseLeave={() => setHover(null)}>
              <rect x={bx - 1} y={top} width={barW + 2} height={plotH} fill="transparent" />
              <path d={`M${bx},${y(yMin)} V${y(value) + 4} Q${bx},${y(value)} ${bx + 4},${y(value)} H${bx + barW - 4} Q${bx + barW},${y(value)} ${bx + barW},${y(value) + 4} V${y(yMin)} Z`} fill={s.color} opacity={hover && hover !== id ? 0.55 : 1} />
              <text x={bx + barW / 2} y={y(value) - 5} textAnchor="middle" className="sc-chart-value">{value}{unit}</text>
              <title>{label} {s.label}: {value}{unit}</title>
            </g>;
          })}
        </g>)}
        {limit && <line x1={left} x2={W - right} y1={y(limit.value)} y2={y(limit.value)} stroke="#b42318" strokeWidth="1.5" strokeDasharray="4 3" />}
      </svg>
    </div>
    <figcaption className="visually-hidden">{series.map((s) => `${s.label}: ${s.values.map((v, i) => `${labels[i]} ${v}${unit}`).join(', ')}`).join(' / ')}</figcaption>
  </figure>;
}
