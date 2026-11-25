import { useEffect, useState } from 'react';
import { apiClient } from '../services/api';
import { ForecastExecution, ForecastExecutionSummary } from '../types/engine';
import { PlanningReply } from '../types/modules';
import { useProductionStore } from '../store/productionStore';
import { Notice, errorMessage } from './ui';
import UsageMeter from './UsageMeter';

export default function LivePlanningPanel({ stage }: { stage: 'plans' | 'diagnosis' | 'mrp' | 'whatif' | 'approval' }) {
  const { planningPreview: preview, setPlanningPreview, previewPlanId, setPreviewPlanId } = useProductionStore();
  const [history, setHistory] = useState<ForecastExecutionSummary[]>([]);
  const [execution, setExecution] = useState<ForecastExecution | null>(null);
  const [id, setId] = useState(preview?.forecast_execution_id ?? '');
  const [month, setMonth] = useState('');
  const [products, setProducts] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    apiClient.forecastHistory(20, 0).then(page => { if (alive) setHistory(page.items.filter(r => r.status === 'OK' || r.status === 'PARTIAL')); })
      .catch(failure => { if (alive) setError(errorMessage(failure)); });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    if (!id) return;
    let alive = true;
    apiClient.getForecast(id).then(detail => {
      if (!alive) return;
      setExecution(detail); setMonth(detail.result?.forecasts[0]?.target_month ?? '');
      setProducts([...new Set(detail.result?.forecasts.map(r => r.product_id) ?? [])]);
    }).catch(failure => { if (alive) { setExecution(null); setError(errorMessage(failure)); } });
    return () => { alive = false; };
  }, [id]);
  async function run() {
    if (!id || !month || !products.length) return;
    setBusy(true); setError(''); setPlanningPreview(null);
    try { const detail = await apiClient.getForecast(id); setPlanningPreview(await apiClient.planPreview({ forecast_execution_id: id, product_ids: products, target_month: month, horizon_months: 1, as_of_date: detail.parameters.trained_until })); }
    catch (failure) {
      if ((failure as Partial<PlanningReply>)?.result) setPlanningPreview(failure as PlanningReply);
      else setError(failure instanceof Error ? failure.message : errorMessage(failure));
    } finally { setBusy(false); }
  }
  const result = preview?.result;
  const selected = result?.plans.find(p => p.plan_id === previewPlanId) ?? result?.plans[0];
  const months = [...new Set(execution?.result?.forecasts.map(row => row.target_month) ?? [])];
  const checks = result?.constraint_evaluations.filter(e => e.plan_id === selected?.plan_id) ?? [];
  return <section className="stack" aria-label="실제 계획 모듈 연결">
    <Notice>서버 입력으로 계산 모듈을 호출하는 읽기 전용 미리보기입니다. 결과는 저장·승인되지 않습니다. 모듈 미구현·입력 부족·연결 실패 시 합성 사례로 전환하지 않습니다.</Notice>
    {error && <div role="alert"><Notice tone="bad">{error}</Notice></div>}
    <section className="panel stack"><h3>실제 예측 실행 선택</h3>
      <label className="field"><span>최근 성공·부분 성공 실행 20개 중 선택</span><select aria-label="계획 입력 예측 실행" value={id} disabled={busy} onChange={e => { setId(e.target.value); setPlanningPreview(null); setExecution(null); setError(''); }}><option value="">실행을 선택하세요</option>{history.map(r => <option key={r.execution_id} value={r.execution_id}>{r.created_at} · {r.status} · {r.execution_id}</option>)}</select></label>
      <label className="field"><span>대상 월</span><select aria-label="계획 대상 월" disabled={busy || !execution} value={month} onChange={e => { setMonth(e.target.value); setPlanningPreview(null); }}>{months.map(m => <option key={m}>{m}</option>)}</select></label>
      <fieldset disabled={busy || !execution}><legend>계획 대상 제품</legend>{[...new Set(execution?.result?.forecasts.filter(r => r.target_month === month).map(r => r.product_id) ?? [])].map(p => <label key={p}><input type="checkbox" checked={products.includes(p)} onChange={e => { setProducts(e.target.checked ? [...products, p] : products.filter(v => v !== p)); setPlanningPreview(null); }} /> {p} </label>)}</fieldset>
      <button className="button primary" disabled={busy || !execution || !products.length || !month} onClick={() => void run()}>{busy ? '계산 요청 중…' : '읽기 전용 계획 계산 요청'}</button>
    </section>
    {!result && <Notice tone="warn">아직 계획 결과가 없습니다. 계산 모듈은 미구현 상태에서는 501을 반환합니다.</Notice>}
    {result && <section className="panel stack" aria-label="서버 계획 미리보기">
      <h3>계산 상태: {result.status}</h3><p>예측 실행 {preview?.forecast_execution_id} · 모듈 {result.module_version}</p><p className="muted">입력 지문 {preview?.input_digest} · 미저장 · 승인 불가</p>
      {[...result.errors, ...result.unverified, ...result.warnings].map((item, i) => <Notice key={i} tone="warn">{item.code} · {item.message}</Notice>)}
      {!!result.plans.length && <label className="field"><span>검토할 계획안</span><select aria-label="서버 계획안" value={selected?.plan_id ?? ''} onChange={e => setPreviewPlanId(e.target.value)}>{result.plans.map(p => <option key={p.plan_id} value={p.plan_id}>{p.label} · {p.feasibility}</option>)}</select></label>}
      {stage === 'plans' && <table><caption>서버가 반환한 계획안 · 미저장</caption><thead><tr><th>안</th><th>실행 가능성</th><th>제품·월·수량</th></tr></thead><tbody>{result.plans.map(p => <tr key={p.plan_id}><td>{p.label}</td><td>{p.feasibility}</td><td>{p.production.map(r => `${r.product_id} / ${r.period} / ${r.production_qty} ${r.unit}`).join(' · ')}</td></tr>)}</tbody></table>}
      {stage === 'diagnosis' && <div className="resource-grid">{checks.map(c => <UsageMeter key={c.constraint_id} label={`${c.resource_id ?? c.product_id ?? c.constraint_id} · ${c.period}`} used={c.used_value} limit={c.limit_value} unit={c.time_basis ?? c.unit} status={c.status} />)}{!checks.length && <p>반환된 제약 평가가 없습니다. 충족으로 간주하지 않습니다.</p>}</div>}
      {stage === 'mrp' && <table><caption>서버 자재 소요·부족량</caption><thead><tr><th>자재·월</th><th>소요</th><th>가용</th><th>부족</th></tr></thead><tbody>{result.material_requirements.filter(r => r.plan_id === selected?.plan_id).map(r => <tr key={`${r.material_id}-${r.period}`}><td>{r.material_id} · {r.period}</td><td>{r.required_qty ?? '미확인'}</td><td>{r.available_qty ?? '미확인'}</td><td>{r.shortage_qty ?? '미확인'} {r.unit}</td></tr>)}</tbody></table>}
      {(stage === 'whatif' || stage === 'approval') && <Notice tone="warn">읽기 전용 미리보기에는 저장된 기준 계획 실행이 없습니다. What-if 재계산·정식 승인은 계획 저장 기능이 연결된 후 가능합니다.</Notice>}
      {stage === 'approval' && <button className="button primary" disabled>최종 MPS 승인 (저장 기능 미연결)</button>}
      <details><summary>계산 근거와 출처</summary>{result.evidence.map((item, i) => <p key={i}>{item.code}: {item.message} · {item.input_refs.join(', ')}</p>)}</details>
    </section>}
  </section>;
}
