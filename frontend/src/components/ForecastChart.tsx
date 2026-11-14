import { useState } from 'react';
import { ForecastRow } from '../types/engine';

const SERIES = [{ key: 'p50', label: 'P50 중앙값', color: '#148359' }, { key: 'p80', label: 'P80', color: '#2563eb' }, { key: 'p90', label: 'P90', color: '#db4771' }] as const;

export default function ForecastChart({ rows }: { rows: ForecastRow[] }) {
  const products = [...new Set(rows.map(row => row.product_id))];
  const [product, setProduct] = useState(products[0]);
  const [visible, setVisible] = useState<string[]>(['p50', 'p80', 'p90']);
  const selected = products.includes(product) ? product : products[0];
  const data = rows.filter(row => row.product_id === selected).sort((a, b) => a.target_month.localeCompare(b.target_month));
  const max = Math.max(1, ...data.flatMap(row => SERIES.map(s => Number(row[s.key]))));
  const x = (i: number) => 70 + i * 760 / Math.max(1, data.length - 1);
  const y = (v: number) => 255 - v / max * 215;
  return <section className="panel chart-panel" aria-label="실제 저장 예측 차트">
    <div className="panel-heading"><h3>월별 수요예측 · 서버 저장 결과</h3>
      <label>제품 <select aria-label="차트 제품" value={selected} onChange={e => setProduct(e.target.value)}>{products.map(p => <option key={p}>{p}</option>)}</select></label></div>
    <div className="chart-legend">{SERIES.map(s => <button type="button" key={s.key} aria-pressed={visible.includes(s.key)} style={{ color: s.color }}
      onClick={() => setVisible(visible.includes(s.key) ? visible.filter(k => k !== s.key) : [...visible, s.key])}>{s.label}</button>)}</div>
    <svg viewBox="0 0 900 300" role="img" aria-label={`${selected} 월별 P50 P80 P90 예측`}>
      {[0, .25, .5, .75, 1].map(t => <g key={t}><line x1="60" x2="850" y1={y(t * max)} y2={y(t * max)} stroke="#dce5ef" /><text x="52" y={y(t * max) + 5} textAnchor="end" fontSize="12">{Math.round(t * max).toLocaleString()}</text></g>)}
      {data.map((row, i) => <text key={row.target_month} x={x(i)} y="282" textAnchor="middle" fontSize="12">{row.target_month}</text>)}
      {SERIES.filter(s => visible.includes(s.key)).map(s => <g key={s.key}>
        <polyline fill="none" stroke={s.color} strokeWidth="3" points={data.map((row, i) => `${x(i)},${y(Number(row[s.key]))}`).join(' ')} />
        {data.map((row, i) => <circle key={row.target_month} cx={x(i)} cy={y(Number(row[s.key]))} r="5" fill="white" stroke={s.color} strokeWidth="2"><title>{row.target_month} {s.label}: {row[s.key]}</title></circle>)}
      </g>)}
    </svg>
    <p className="muted">저장된 예측값만 표시합니다. 원인 분석·납기 보장·계획 추천을 의미하지 않습니다. 수량 단위는 해당 제품의 승인 기준 단위를 확인하세요.</p>
  </section>;
}
