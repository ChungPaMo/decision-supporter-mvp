import { useEffect, useRef, useState } from 'react';
import { Entity } from '../types/api';
import { ClassificationResult } from '../types/modules';
import { apiClient } from '../services/api';
import { ENTITY_LABEL, Notice, errorMessage } from './ui';
import { XlsxTableSelection } from '../types/ingestion';
import { describeSelection, rangeFailure } from './XlsxRangePicker';

// 보류 종류별 안내. 어떤 경우에도 자동 등록·승인하지 않는다.
const HOLD_GUIDE: Record<string, { title: string; next: string }> = {
  NEEDS_TRANSFORM: { title: '데이터 변환 필요', next: '이 파일은 그대로 등록할 수 없습니다. 판매 원장이라면 "월별 수요 → 판매 원장 변환"에서 변환 정책을 확인하세요.' },
  OTHER_ROUTE: { title: '별도 등록 경로 이용', next: '이 파일은 유형 추천 대상이 아닙니다. 아래 안내한 등록 경로에서 직접 등록하세요.' },
  AMBIGUOUS: { title: '사용자 확인 필요', next: '후보가 여러 개이거나 구분이 불명확합니다. 후보와 원본을 확인하고 왼쪽 데이터 종류에서 유형을 직접 선택하세요.' },
  UNKNOWN: { title: '분류 근거 부족', next: '유형을 판단할 근거가 부족합니다. 엑셀이라면 시트·표 범위를 지정해 다시 요청하거나, 유형을 직접 선택하세요.' },
};
const SECTION_LABEL: Record<string, string> = { resources: '자원', quantity_limits: '수량한도', hours_budgets: '시간예산', routing_steps: '공정' };

interface Props {
  // 등록 영역과 공유하는 원본 파일. 여기서 고르면 등록·컬럼 분석에서도 같은 파일을 쓴다.
  file: File | null;
  onFile: (file: File | null) => void;
  onChoose: (entity: Entity) => void;
  // 월별 수요의 판매 원장 변환으로 이동
  onTransform: () => void;
  // 등록 영역에서 고른 XLSX 표 범위. 있으면 그 범위로만 분류한다.
  selection: XlsxTableSelection | null;
  disabled?: boolean;
}

export default function ClassificationPanel({ file, onFile, onChoose, onTransform, selection, disabled = false }: Props) {
  const [samples, setSamples] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ClassificationResult | null>(null);
  const [error, setError] = useState('');
  const seq = useRef(0);
  // 파일이나 선택 범위가 바뀌면 이전 분류 결과를 버린다.
  useEffect(() => { seq.current += 1; setResult(null); setError(''); setBusy(false); }, [file, selection]);

  async function classify() {
    if (!file) return;
    const ticket = ++seq.current;
    setBusy(true); setError(''); setResult(null);
    try { const reply = await apiClient.classifyFile(file, samples, selection); if (ticket === seq.current) setResult(reply); }
    catch (failure) { if (ticket === seq.current) setError(/^XLSX_/.test((failure as { detail?: { code?: string } })?.detail?.code ?? '') ? rangeFailure(failure) : errorMessage(failure)); }
    finally { if (ticket === seq.current) setBusy(false); }
  }
  const hint = result?.registration_hint ?? null;
  const guide = result?.hold ? HOLD_GUIDE[result.hold_kind ?? ''] : undefined;
  return <section className="panel stack" aria-label="파일 유형 자동 분류">
    <div className="panel-heading"><div><h3>파일 유형 추천</h3><p>유형 추천과 데이터 승인은 별도입니다. 추천을 확인한 뒤 등록할 유형을 직접 선택합니다.</p></div><span className="badge badge-info">승인 전</span></div>
    <label className="field"><span>분류할 파일 (CSV/XLSX)</span><input type="file" accept=".csv,.xlsx" disabled={busy || disabled}
      onChange={e => { onFile(e.target.files?.[0] ?? null); e.target.value = ''; }} /></label>
    {file && <p className="muted">선택한 원본: {file.name} — 등록 영역과 같은 파일을 사용합니다.</p>}
    {selection && <p className="muted">선택한 범위로만 분류합니다: {describeSelection(selection)}</p>}
    <label><input type="checkbox" checked={samples} disabled={busy || disabled} onChange={e => setSamples(e.target.checked)} /> 샘플 최대 5행을 분류 모듈에 전달하는 데 동의합니다. 미선택 시 헤더만 전달합니다.</label>
    <button className="button" disabled={busy || disabled || !file} onClick={() => void classify()}>{busy ? '추천 요청 중…' : '파일 유형 추천 요청'}</button>
    {error && <div role="alert"><Notice tone="warn">{error} 왼쪽 데이터 종류를 직접 선택해 등록할 수 있습니다. 자동 승인이나 예시 추천으로 대체하지 않습니다.</Notice></div>}
    {result && <>
      <Notice tone={result.hold ? 'warn' : 'info'}>{result.hold ? `HOLD — ${guide ? guide.title : '분류가 모호합니다. 후보와 원본을 확인하고 수동 선택하세요.'}` : '추천 검토가 필요합니다.'} {result.reasons.join(' · ')}</Notice>
      {guide && <p>{guide.next}</p>}
      {result.hold && result.hold_kind === 'NEEDS_TRANSFORM' && <button className="button" disabled={disabled} onClick={onTransform}>판매 원장 변환으로 이동</button>}
      {hint && <p><strong>등록 경로:</strong> {ENTITY_LABEL[hint.entity]} · 구분 {hint.sections.map((section) => SECTION_LABEL[section] ?? section).join(', ')}</p>}
      {hint && <button className="button" disabled={disabled} onClick={() => onChoose(hint.entity)}>{ENTITY_LABEL[hint.entity]} 등록으로 이동</button>}
      {result.candidates.length > 0 && <table><caption>서버 분류 후보 · {result.module_version}</caption><thead><tr><th>유형</th><th>점수</th><th>근거</th></tr></thead><tbody>{result.candidates.map(c => <tr key={c.entity}><td>{ENTITY_LABEL[c.entity]}</td><td>{c.score.toFixed(3)}</td><td>{c.reasons.join(' · ')}</td></tr>)}</tbody></table>}
      <p className="muted">분류 모듈 {result.module_version}. 점수는 확률이 아닙니다.</p>
      <button className="button primary" disabled={disabled || result.hold || !result.recommended_entity} onClick={() => { if (result.recommended_entity) onChoose(result.recommended_entity); }}>검토한 추천 유형 선택</button>
      <p className="muted">유형 선택만 변경합니다. 같은 파일이 등록 영역에 유지되며, "이 파일 등록"을 누르기 전에는 서버에 저장하지 않습니다.</p>
    </>}
    <details><summary>CAPA·Routing 등록 안내</summary><p>CAPA(설비 능력)와 Routing(공정)도 같은 등록·검증·승인 절차로 등록합니다. 이 두 유형은 분류에서 HOLD로 나오는 것이 정상이며, 왼쪽 데이터 종류에서 직접 선택합니다. 순서는 자원 → 수량한도·시간예산 → Routing입니다. 수량·설비시간·인시는 서로 합치거나 환산하지 않습니다.</p></details>
  </section>;
}
