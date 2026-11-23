import { useEffect, useRef, useState } from 'react';
import { Entity } from '../types/api';
import { ClassificationResult } from '../types/modules';
import { apiClient } from '../services/api';
import { ENTITY_LABEL, Notice, errorMessage } from './ui';

interface Props {
  // 등록 영역과 공유하는 원본 파일. 여기서 고르면 등록·컬럼 분석에서도 같은 파일을 쓴다.
  file: File | null;
  onFile: (file: File | null) => void;
  onChoose: (entity: Entity) => void;
  disabled?: boolean;
}

export default function ClassificationPanel({ file, onFile, onChoose, disabled = false }: Props) {
  const [samples, setSamples] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ClassificationResult | null>(null);
  const [error, setError] = useState('');
  const seq = useRef(0);
  // 파일이 바뀌면 이전 분류 결과를 버린다.
  useEffect(() => { seq.current += 1; setResult(null); setError(''); setBusy(false); }, [file]);

  async function classify() {
    if (!file) return;
    const ticket = ++seq.current;
    setBusy(true); setError(''); setResult(null);
    try { const reply = await apiClient.classifyFile(file, samples); if (ticket === seq.current) setResult(reply); }
    catch (failure) { if (ticket === seq.current) setError(errorMessage(failure)); }
    finally { if (ticket === seq.current) setBusy(false); }
  }
  const hinted = result?.registration_hint?.entity === 'capacity' || result?.registration_hint?.entity === 'routing' ? result.registration_hint.entity as Entity : null;
  return <section className="panel stack" aria-label="파일 유형 자동 분류">
    <div className="panel-heading"><div><h3>파일 유형 추천</h3><p>유형 추천과 데이터 승인은 별도입니다. 추천을 확인한 뒤 등록할 유형을 직접 선택합니다.</p></div><span className="badge badge-info">승인 전</span></div>
    <label className="field"><span>분류할 파일 (CSV/XLSX)</span><input type="file" accept=".csv,.xlsx" disabled={busy || disabled}
      onChange={e => onFile(e.target.files?.[0] ?? null)} /></label>
    {file && <p className="muted">선택한 원본: {file.name} — 등록 영역과 같은 파일을 사용합니다.</p>}
    <label><input type="checkbox" checked={samples} disabled={busy || disabled} onChange={e => setSamples(e.target.checked)} /> 샘플 최대 5행을 분류 모듈에 전달하는 데 동의합니다. 미선택 시 헤더만 전달합니다.</label>
    <button className="button" disabled={busy || disabled || !file} onClick={() => void classify()}>{busy ? '추천 요청 중…' : '파일 유형 추천 요청'}</button>
    {error && <div role="alert"><Notice tone="warn">{error} 왼쪽 데이터 종류를 직접 선택해 등록할 수 있습니다. 자동 승인이나 예시 추천으로 대체하지 않습니다.</Notice></div>}
    {result && <>
      <Notice tone={result.hold ? 'warn' : 'info'}>{result.hold ? 'HOLD — 분류가 모호합니다. 후보와 원본을 확인하고 수동 선택하세요.' : '추천 검토가 필요합니다.'} {result.reasons.join(' · ')}</Notice>
      <table><caption>서버 분류 후보 · {result.module_version}</caption><thead><tr><th>유형</th><th>점수</th><th>근거</th></tr></thead><tbody>{result.candidates.map(c => <tr key={c.entity}><td>{ENTITY_LABEL[c.entity]}</td><td>{c.score.toFixed(3)}</td><td>{c.reasons.join(' · ')}</td></tr>)}</tbody></table>
      <p className="muted">점수는 확률이 아닙니다.</p>
      <button className="button primary" disabled={disabled || result.hold || !result.recommended_entity} onClick={() => { if (result.recommended_entity) onChoose(result.recommended_entity); }}>검토한 추천 유형 선택</button>
      {hinted && <button className="button" disabled={disabled} onClick={() => onChoose(hinted)}>{ENTITY_LABEL[hinted]} 유형으로 직접 선택</button>}
      <p className="muted">유형 선택만 변경합니다. 같은 파일이 등록 영역에 유지되며, "이 파일 등록"을 누르기 전에는 서버에 저장하지 않습니다.</p>
    </>}
    <details><summary>CAPA·Routing 등록 안내</summary><p>CAPA(설비 능력)와 Routing(공정)도 같은 등록·검증·승인 절차로 등록합니다. 이 두 유형은 분류에서 HOLD로 나오는 것이 정상이며, 왼쪽 데이터 종류에서 직접 선택합니다. 순서는 자원 → 수량한도·시간예산 → Routing입니다. 수량·설비시간·인시는 서로 합치거나 환산하지 않습니다.</p></details>
  </section>;
}
