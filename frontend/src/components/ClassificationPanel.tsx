import { useState } from 'react';
import { Entity } from '../types/api';
import { ClassificationResult } from '../types/modules';
import { apiClient } from '../services/api';
import { ENTITY_LABEL, Notice, errorMessage } from './ui';

export default function ClassificationPanel({ onChoose, disabled = false }: { onChoose: (entity: Entity) => void; disabled?: boolean }) {
  const [file, setFile] = useState<File | null>(null);
  const [samples, setSamples] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ClassificationResult | null>(null);
  const [error, setError] = useState('');
  async function classify() {
    if (!file) return;
    setBusy(true); setError(''); setResult(null);
    try { setResult(await apiClient.classifyFile(file, samples)); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  return <section className="panel stack" aria-label="파일 유형 자동 분류">
    <div className="panel-heading"><div><h3>파일 유형 추천</h3><p>유형 추천과 데이터 승인은 별도입니다. 추천을 확인한 뒤 등록할 유형을 직접 선택합니다.</p></div><span className="badge badge-info">승인 전</span></div>
    <label className="field"><span>분류할 파일 (CSV/XLSX)</span><input type="file" accept=".csv,.xlsx" disabled={busy || disabled}
      onChange={e => { setFile(e.target.files?.[0] ?? null); setResult(null); setError(''); }} /></label>
    <label><input type="checkbox" checked={samples} disabled={busy || disabled} onChange={e => setSamples(e.target.checked)} /> 샘플 최대 5행을 분류 모듈에 전달하는 데 동의합니다. 미선택 시 헤더만 전달합니다.</label>
    <button className="button" disabled={busy || disabled || !file} onClick={() => void classify()}>{busy ? '추천 요청 중…' : '파일 유형 추천 요청'}</button>
    {error && <div role="alert"><Notice tone="warn">{error} 왼쪽 데이터 종류를 직접 선택해 등록할 수 있습니다. 자동 승인이나 예시 추천으로 대체하지 않습니다.</Notice></div>}
    {result && <>
      <Notice tone={result.hold ? 'warn' : 'info'}>{result.hold ? 'HOLD — 분류가 모호합니다. 후보와 원본을 확인하고 수동 선택하세요.' : '추천 검토가 필요합니다.'} {result.reasons.join(' · ')}</Notice>
      <table><caption>서버 분류 후보 · {result.module_version}</caption><thead><tr><th>유형</th><th>점수</th><th>근거</th></tr></thead><tbody>{result.candidates.map(c => <tr key={c.entity}><td>{ENTITY_LABEL[c.entity]}</td><td>{c.score.toFixed(3)}</td><td>{c.reasons.join(' · ')}</td></tr>)}</tbody></table>
      <button className="button primary" disabled={disabled || result.hold || !result.recommended_entity} onClick={() => { if (result.recommended_entity) onChoose(result.recommended_entity); }}>검토한 추천 유형 선택</button>
      <p className="muted">유형 선택만 변경합니다. 원본 등록·검증·승인은 아래 기존 절차로 진행합니다.</p>
    </>}
    <details><summary>CAPA·라우팅 등록 준비</summary><p>현재 등록 가능한 유형은 제품·자재·BOM·재고·수요입니다. CAPA·라우팅의 월 수량·인시·설비시간·공정 참조 계약은 검토 중이며 저장·승인은 아직 제공하지 않습니다.</p></details>
  </section>;
}
