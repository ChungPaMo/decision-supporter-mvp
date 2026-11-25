import { useRef, useState } from 'react';
import { apiClient } from '../services/api';
import { Entity } from '../types/api';
import { ClassifiedMappingReply, MappingReply, ProfileReply, XlsxTableSelection } from '../types/ingestion';
import { columnLetter, describeSelection, rangeFailure } from './XlsxRangePicker';
import { ENTITY_LABEL, Notice, errorMessage } from './ui';

const SHEET_STATUS: Record<string, string> = { MAPPED: '매핑됨', HOLD: 'HOLD — 열 확인 필요', IGNORED: '사용 안 함' };
const SELECTION: Record<string, string> = { USER_SELECTION: '사용자가 유형 선택', CLASSIFIER_RECOMMENDATION: '분류 추천 유형', REQUIRED: '유형 선택 필요' };
const pct = (value: number) => `${(value * 100).toFixed(1)}%`;
const failure = (error: unknown) => {
  const detail = (error as { detail?: { code?: string; message?: string } })?.detail;
  return detail?.code ? `${detail.message ?? '요청이 거부되었습니다.'} (${detail.code})` : errorMessage(error);
};

interface Props {
  file: File; entity: Entity; overrides: Record<string, string>;
  onOverrides: (next: Record<string, string>) => void; useApprovedMaster: boolean; disabled: boolean;
  // 사용자가 고른 XLSX 표 범위. 없으면 파일 전체를 읽는다.
  selection: XlsxTableSelection | null;
}

// 등록 전 확인 단계: 컬럼 구조 분석과 매핑 후보(Top-3). 저장하지 않으며, 후보를 자동 적용하지 않는다.
// 부모가 key 에 파일·유형·데이터셋을 넣어, 그중 하나가 바뀌면 이전 결과를 버린다.
export default function IngestAssistPanel({ file, entity, overrides, onOverrides, useApprovedMaster, disabled, selection: range }: Props) {
  const [profile, setProfile] = useState<ProfileReply | null>(null);
  const [mapping, setMapping] = useState<MappingReply | null>(null);
  const [selection, setSelection] = useState<Pick<ClassifiedMappingReply, 'selection_method' | 'source_sha256'> | null>(null);
  const [checkedWith, setCheckedWith] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const seq = useRef(0);
  const overrideKey = JSON.stringify(overrides);
  const hasOverrides = Object.keys(overrides).length > 0;

  async function run(job: () => Promise<void>) {
    const ticket = ++seq.current;
    setBusy(true); setError('');
    try { await job(); }
    catch (problem) { if (ticket === seq.current && (problem as { detail?: { code?: string } })?.detail?.code !== 'DATASET_CHANGED') setError((range ? /^XLSX_|ANALYSIS_LIMIT|FILE_TOO_LARGE|UNSUPPORTED_TYPE/ : /^XLSX_|ANALYSIS_LIMIT|FILE_TOO_LARGE/).test((problem as { detail?: { code?: string } })?.detail?.code ?? '') ? rangeFailure(problem) : failure(problem)); }
    finally { if (ticket === seq.current) setBusy(false); }
  }
  const analyze = () => run(async () => { const ticket = seq.current; const reply = await apiClient.profileFile(file, useApprovedMaster, range); if (ticket === seq.current) setProfile(reply); });
  const suggest = () => run(async () => {
    const ticket = seq.current;
    if (mapping) {
      const reply = await apiClient.mappingSuggestions(file, entity, overrides, useApprovedMaster, range);
      if (ticket === seq.current) { setMapping(reply); setCheckedWith(overrideKey); }
    } else {
      const reply = await apiClient.classifiedMapping(file, entity, overrides, useApprovedMaster, range);
      if (ticket === seq.current) { setMapping(reply.mapping); setSelection(reply); setCheckedWith(overrideKey); }
    }
  });
  const choose = (target: string, sourceColumn: string) => {
    const next = Object.fromEntries(Object.entries(overrides).filter(([field, column]) => field !== target && column !== sourceColumn));
    if (target) next[target] = sourceColumn;
    onOverrides(next);
  };
  const chosenFor = (sourceColumn: string) => Object.entries(overrides).find(([, column]) => column === sourceColumn)?.[0] ?? '';
  const stale = mapping !== null && checkedWith !== overrideKey;

  return <section className="panel stack" aria-label="컬럼 분석과 매핑 후보">
    <div className="panel-heading"><div><h3>등록 전 확인 · 컬럼 분석과 매핑 후보</h3>
      <p className="muted">{file.name} · {ENTITY_LABEL[entity]}. 서버에 저장하지 않습니다. 후보는 검토용이며 자동으로 적용되지 않습니다.</p></div>
      <span className="badge badge-info">저장 전</span></div>
    <div className="actions start">
      <button type="button" className="button" disabled={disabled || busy} onClick={() => void analyze()}>컬럼 구조 분석</button>
      <button type="button" className="button" disabled={disabled || busy} onClick={() => void suggest()}>{mapping ? '선택한 열로 다시 확인' : '컬럼 후보 보기'}</button>
      {busy && <span className="muted">서버에 요청 중…</span>}
    </div>
    {range && <Notice tone="info">선택한 범위만 분석합니다: {describeSelection(range)}. 열 번호는 원본 기준입니다.</Notice>}
    {!useApprovedMaster && <Notice tone="muted">제품·자재가 아직 승인되지 않아 참조 검증 없이 분석합니다 (참조 검증 미완료).</Notice>}
    {error && <Notice tone="bad">{error} 이전 결과나 예시로 대체하지 않습니다.</Notice>}

    {profile && profile.sheets.map((sheet) => <div key={`p-${sheet.sheet}`} className="table-scroll"><table>
      <caption>컬럼 구조{sheet.sheet ? ` · ${sheet.sheet}` : ''} · {sheet.row_count.toLocaleString()}행 (예시 값 미포함)</caption>
      <thead><tr><th>열</th><th>열 이름</th><th>형식 후보</th><th>빈값 비율</th><th>확인 필요</th></tr></thead>
      <tbody>{sheet.columns.map((column) => <tr key={column.col}>
        <td>{range ? `${columnLetter(column.col)} (${column.col})` : column.col}</td><td>{column.column}</td><td>{column.type_candidates.join(', ') || '-'}</td><td>{pct(column.empty_ratio)}</td>
        <td>{[...column.uncertainty_reasons, ...column.anomalies].join(' · ') || '-'}</td></tr>)}</tbody>
    </table></div>)}

    {selection && <p className="muted">유형 결정: {SELECTION[selection.selection_method]} · 원본 SHA-256 <span className="code">{selection.source_sha256.slice(0, 16)}…</span></p>}
    {mapping && mapping.sheets.map((sheet) => <div key={`m-${sheet.sheet}`} className="stack">
      <p>{sheet.sheet && <><strong>{sheet.sheet}</strong> · </>}<span className={`badge badge-${sheet.status === 'MAPPED' ? 'ok' : sheet.status === 'HOLD' ? 'warn' : 'muted'}`}>{SHEET_STATUS[sheet.status]}</span></p>
      {sheet.holds.length > 0 && <Notice tone="warn">필수 열이 확정되지 않았습니다: {sheet.holds.join(' · ')}. 아래에서 원본 열을 직접 선택한 뒤 다시 확인하세요.</Notice>}
      {Object.keys(sheet.existing_mapping).length > 0 && <p className="muted">현재 매핑: {Object.entries(sheet.existing_mapping).map(([field, col]) => `${field} ← ${col}번 열`).join(' · ')}</p>}
      {sheet.suggestions.length > 0 && <div className="table-scroll"><table>
        <caption>매핑 후보 (최대 3순위) — 순서는 확률이 아니며 검토가 필요합니다</caption>
        <thead><tr><th>원본 열</th><th>후보 표준 필드 · 방식</th><th>근거</th><th>이 열을 사용할 표준 필드</th></tr></thead>
        <tbody>{sheet.suggestions.map((item) => <tr key={item.col}>
          <td>{range ? `${columnLetter(item.col)}열` : `${item.col}.`} {item.source_column}</td>
          <td>{item.suggestions.map((candidate, i) => <div key={candidate.target_field}>{i + 1}. {candidate.target_field} · {candidate.method}</div>)}
            {!item.suggestions.length && <span className="muted">후보 없음 {item.unresolved_reasons.join(' · ')}</span>}</td>
          <td>{item.suggestions.map((candidate) => <div key={candidate.target_field} className="muted">{candidate.evidence.join(', ')}</div>)}</td>
          <td><select aria-label={`${item.source_column} 열의 표준 필드`} disabled={disabled || !item.suggestions.length} value={chosenFor(item.source_column)}
            onChange={(event) => choose(event.target.value, item.source_column)}>
            <option value="">선택 안 함</option>{item.suggestions.map((candidate) => <option key={candidate.target_field} value={candidate.target_field}>{candidate.target_field}</option>)}
          </select></td></tr>)}</tbody>
      </table></div>}
    </div>)}
    {hasOverrides && <p>내가 선택한 열: {Object.entries(overrides).map(([field, column]) => `${field} ← ${column}`).join(' · ')}
      {' '}<button type="button" className="button" disabled={disabled} onClick={() => onOverrides({})}>선택 모두 지우기</button></p>}
    {stale && <Notice tone="warn">열 선택이 바뀌었습니다. "선택한 열로 다시 확인"을 눌러 결과를 갱신하세요.</Notice>}
    {hasOverrides && <p className="muted">선택한 열은 위의 "이 파일 등록"을 누를 때 함께 전달됩니다. 등록 전까지 서버에 저장되지 않습니다.</p>}
  </section>;
}
