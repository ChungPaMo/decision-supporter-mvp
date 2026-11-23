import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../services/api';
import { useProductionStore } from '../store/productionStore';
import { SalesColumnKey, SalesColumns, SalesTransformPolicy, TransformationDetail, TransformationSummary, TransformReply, XlsxTableSelection } from '../types/ingestion';
import XlsxRangePicker, { columnLetter, describeSelection, isXlsx, rangeFailure } from './XlsxRangePicker';
import { Notice, ROLE_CODE, errorMessage, qty } from './ui';

const COLUMN_FIELDS: Array<{ key: SalesColumnKey; label: string; hint: string }> = [
  { key: 'order_date', label: '주문일', hint: '출고일과 구분' },
  { key: 'product_id', label: '제품 코드', hint: '' },
  { key: 'quantity', label: '수량', hint: '단가·금액과 구분' },
  { key: 'unit', label: '단위', hint: '' },
  { key: 'status', label: '상태', hint: '정상·취소·반품' },
  { key: 'order_id', label: '주문번호', hint: '' },
  { key: 'line_id', label: '행번호', hint: '' },
];
const DEFAULT_COLUMNS: SalesColumns = { order_date: '주문일자', product_id: '제품코드', quantity: '수량', unit: '단위', status: '구분', order_id: '주문번호', line_id: '행번호' };
const STATUS: Record<TransformReply['status'], { label: string; tone: 'warn' | 'bad' | 'ok' }> = {
  POLICY_REVIEW_REQUIRED: { label: '정책 확인 필요 — 저장할 수 없습니다', tone: 'warn' },
  HAS_ERRORS: { label: '오류 있음 — 저장할 수 없습니다', tone: 'bad' },
  TRANSFORMED_PREVIEW: { label: '변환 미리보기 완료 — 아직 저장되지 않았습니다', tone: 'ok' },
};
const COUNT_LABEL: Record<string, string> = {
  source_rows: '원본 행', normal_included: '정상 (포함)', cancelled_excluded: '취소 (제외)', returns_separate: '반품 (별도)',
  error_rows: '오류 행', aggregation_errors: '집계 오류', monthly_demand_rows: '월별 수요 행',
};
const short = (digest: string) => `${digest.slice(0, 16)}…`;
const failure = (error: unknown) => {
  const detail = (error as { detail?: { code?: string; message?: string } })?.detail;
  if (detail?.code === 'PERSISTENCE_DISABLED') return `서버 저장 기능이 꺼져 있어 저장·이력 조회를 할 수 없습니다. 저장된 것으로 표시하지 않습니다. (${detail.code})`;
  if (detail?.code === 'RESULT_CHANGED') return `원본·범위·정책·승인 마스터 중 하나가 검토한 미리보기와 다릅니다. 변환 미리보기를 다시 실행하고 확인한 뒤 저장하세요. (${detail.code})`;
  if (detail?.code === 'TRANSFORM_BLOCKED') return `정책을 확인하지 않았거나, 오류가 있거나, 정상 월별 수요가 없어 저장할 수 없습니다. (${detail.code})`;
  if (detail?.code === 'DUPLICATE_UPLOAD') return `같은 월별 수요 결과가 이미 등록되어 있습니다. 변환 이력에서 기존 배치를 확인하세요. (${detail.code})`;
  if (detail?.code === 'TRANSFORM_MAPPING_HOLD') return `필수 열을 찾지 못했습니다. 열 지정을 확인하세요. 범위를 지정했다면 그 범위의 헤더 이름이나 열 문자(예: C)를 입력합니다. (${detail.code})`;
  if (/^XLSX_|ANALYSIS_LIMIT|FILE_TOO_LARGE|UNSUPPORTED_TYPE/.test(detail?.code ?? '')) return rangeFailure(error);
  return detail?.code ? `${detail.message ?? '요청이 거부되었습니다.'} (${detail.code})` : errorMessage(error);
};
// 원본 셀 좌표 (예: E6). 열 번호가 없으면 행만 표시한다.
const cellRef = (row: number, col?: number | null) => (col ? `${columnLetter(col)}${row}` : `${row}행`);

function Review({ preview }: { preview: TransformReply }) {
  const status = STATUS[preview.status];
  return <div className="stack">
    <Notice tone={status.tone}>{status.label}</Notice>
    <dl className="meta-grid">{Object.entries(preview.counts).map(([key, value]) => <div key={key}><dt>{COUNT_LABEL[key] ?? key}</dt><dd>{qty(value)}</dd></div>)}</dl>
    <div className="table-scroll"><table><caption>수량 대조</caption><thead><tr><th>항목</th><th>값</th></tr></thead>
      <tbody>{Object.entries(preview.quantity_reconciliation).map(([key, value]) => <tr key={key}><td>{key}</td><td>{typeof value === 'boolean' ? (value ? '일치' : '불일치') : qty(value)}</td></tr>)}</tbody></table></div>
    {preview.issues_total > 0 && <div className="table-scroll"><table><caption>오류 {preview.issues.length} / 전체 {qty(preview.issues_total)}건 — 유효한 일부만으로 저장하지 않습니다</caption>
      <thead><tr><th>코드</th><th>파일</th><th>시트</th><th>원본 셀</th><th>항목</th></tr></thead>
      <tbody>{preview.issues.map((issue, i) => { const source = preview.sources.find((item) => item.source_index === issue.location.source_index);
        const col = issue.location.col ?? (issue.field ? source?.resolved_columns?.[issue.field] : undefined);
        return <tr key={i}><td>{issue.code}</td><td>{source?.filename ?? issue.location.source_index + 1}</td><td>{issue.location.sheet || '-'}</td><td>{cellRef(issue.location.row, col)}</td><td>{issue.field ?? '-'}</td></tr>; })}</tbody></table></div>}
    {preview.warnings.length > 0 && <div><h4>경고</h4><ul>{preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
    <div className="table-scroll"><table><caption>변환된 월별 수요 {preview.records.length} / 전체 {qty(preview.total)}행 (일부 표시)</caption>
      <thead><tr><th>제품</th><th>월</th><th>수요 수량</th><th>단위</th><th>원본 행 수</th></tr></thead>
      <tbody>{preview.records.slice(0, 12).map((row) => <tr key={`${row.product_id}-${row.period}`}><td>{row.product_id}</td><td>{row.period}</td><td>{qty(row.demand_qty)}</td><td>{row.unit}</td><td>{qty(row.source_row_count)}</td></tr>)}</tbody></table></div>
    {preview.returns_total > 0 && <div className="table-scroll"><table><caption>별도 집계한 반품 {Math.min(12, preview.returns.length)} / 전체 {qty(preview.returns_total)}행 — 수요에서 차감하지 않습니다</caption>
      <thead><tr><th>제품</th><th>월</th><th>반품 수량</th><th>단위</th></tr></thead>
      <tbody>{preview.returns.slice(0, 12).map((row) => <tr key={`${row.product_id}-${row.period}`}><td>{row.product_id}</td><td>{row.period}</td><td>{qty(row.return_qty)}</td><td>{row.unit}</td></tr>)}</tbody></table></div>}
    <details><summary>원본 파일·연산·지문</summary>
      <div className="table-scroll"><table><caption>원본 파일</caption><thead><tr><th>순번</th><th>파일</th><th>행 수</th><th>사용한 범위</th><th>SHA-256</th></tr></thead>
        <tbody>{preview.sources.map((source) => <tr key={source.source_index}><td>{source.source_index + 1}</td><td>{source.filename}</td><td>{qty(source.row_count)}</td><td>{source.table_selection ? describeSelection(source.table_selection) : '파일 전체'}</td><td className="code">{short(source.sha256)}</td></tr>)}</tbody></table></div>
      <ul>{preview.operations.map((operation, i) => <li key={i}>{operation.operation} <span className="code">{JSON.stringify(operation.parameters)}</span></li>)}</ul>
      <p className="muted">정책 지문 <span className="code">{short(preview.policy_digest)}</span> · 입력 지문 <span className="code">{short(preview.input_digest)}</span> · 변환 결과 지문 <span className="code">{short(preview.result_digest)}</span></p>
      <p className="muted">변환 결과 지문은 배치 승인에 쓰는 배치 지문과 다릅니다.</p>
    </details>
  </div>;
}

// 합성 판매 원장 → 월별 수요 변환. CHUNGPAMO_SYNTHETIC_SALES v1.0 (SYNTHETIC_ONLY) 정책만 지원한다.
export default function SalesTransformPanel({ canUseMaster, disabled, onBatch }: { canUseMaster: boolean; disabled: boolean; onBatch: (batchId: string) => void }) {
  const datasetId = useProductionStore((state) => state.datasetId);
  const alive = useRef(true);
  const seq = useRef(0);
  const [files, setFiles] = useState<File[]>([]);
  // 파일 순번(0부터) → 사용자가 고른 XLSX 표 범위
  const [ranges, setRanges] = useState<Record<string, XlsxTableSelection>>({});
  const [columns, setColumns] = useState<SalesColumns>(DEFAULT_COLUMNS);
  const [headerOptions, setHeaderOptions] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [useMaster, setUseMaster] = useState(canUseMaster);
  const [preview, setPreview] = useState<TransformReply | null>(null);
  const [createdBy, setCreatedBy] = useState('INGEST-REVIEWER');
  const [sourceNote, setSourceNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState<{ detail: TransformationDetail; reused: boolean } | null>(null);
  const [history, setHistory] = useState<TransformationSummary[] | null>(null);
  const [historyError, setHistoryError] = useState('');
  const [detail, setDetail] = useState<TransformationDetail | null>(null);

  useEffect(() => { alive.current = true; void loadHistory(); return () => { alive.current = false; }; }, []);

  // 파일·열·확인·마스터 옵션 중 하나라도 바뀌면 이전 미리보기와 지문을 버린다.
  const invalidate = () => { seq.current += 1; setPreview(null); setSaved(null); setError(''); };
  const policy = (): SalesTransformPolicy => ({ dataset_id: datasetId, policy_id: 'CHUNGPAMO_SYNTHETIC_SALES', version: '1.0', columns, user_confirmed: confirmed });
  const distinct = new Set(Object.values(columns).map((value) => value.trim())).size === COLUMN_FIELDS.length && Object.values(columns).every((value) => value.trim());

  async function guarded(job: (ticket: number) => Promise<void>) {
    const ticket = ++seq.current;
    setBusy(true); setError('');
    try { await job(ticket); }
    catch (problem) { if (alive.current && ticket === seq.current && (problem as { detail?: { code?: string } })?.detail?.code !== 'DATASET_CHANGED') { setError(failure(problem)); if (['RESULT_CHANGED', 'XLSX_SOURCE_CHANGED'].includes((problem as { detail?: { code?: string } })?.detail?.code ?? '')) setPreview(null); } }
    finally { if (alive.current && ticket === seq.current) setBusy(false); }
  }
  async function loadHistory() {
    setHistoryError('');
    try { const page = await apiClient.transformations(50, 0); if (alive.current) setHistory(page.items); }
    catch (problem) { if (alive.current && (problem as { detail?: { code?: string } })?.detail?.code !== 'DATASET_CHANGED') { setHistory(null); setHistoryError(failure(problem)); } }
  }
  const readHeaders = () => guarded(async (ticket) => {
    const reply = await apiClient.profileFile(files[0], false, ranges['0']);
    if (alive.current && ticket === seq.current) setHeaderOptions(reply.sheets.flatMap((sheet) => sheet.columns.map((column) => column.column)));
  });
  const runPreview = () => guarded(async (ticket) => {
    setPreview(null); setSaved(null);
    const reply = await apiClient.transformPreview(files, policy(), useMaster, ranges);
    if (alive.current && ticket === seq.current) setPreview(reply);
  });
  const save = () => guarded(async (ticket) => {
    if (!preview) return;
    const result = await apiClient.createTransformation(files, policy(), useMaster, preview.result_digest, createdBy, sourceNote, ranges);
    if (!alive.current || ticket !== seq.current) return;
    setSaved(result);
    await loadHistory();
    onBatch(result.detail.batch_id);
  });
  const openDetail = (id: string) => guarded(async (ticket) => { setDetail(null); const reply = await apiClient.getTransformation(id); if (alive.current && ticket === seq.current) setDetail(reply); });

  const canSave = !!preview && preview.status === 'TRANSFORMED_PREVIEW' && preview.issues_total === 0 && preview.total > 0 && preview.policy.user_confirmed && ROLE_CODE.test(createdBy) && !!sourceNote.trim() && !saved;
  return <section className="panel stack" aria-label="판매 원장 변환">
    <div className="panel-heading"><div><h3>판매 원장 → 월별 수요 변환</h3>
      <p className="muted">합성 판매 원장 전용 정책(CHUNGPAMO_SYNTHETIC_SALES v1.0, SYNTHETIC_ONLY)입니다. 다른 기업의 원장에 자동으로 적용하지 않습니다.</p></div>
      <span className="badge badge-muted">합성 전용</span></div>
    <Notice tone="warn">표준 월별 수요 파일 등록과 판매 원장 변환 중 한 가지만 승인하세요. 둘 다 승인하면 같은 제품·월 중복으로 거부됩니다.</Notice>

    <fieldset className="stack" disabled={disabled || busy}><legend>1. 원본 파일 (1~8개, 선택한 순서대로 전송)</legend>
      <label className="field file-field"><span>판매 원장 파일 (CSV/XLSX)</span><input type="file" accept=".csv,.xlsx" multiple
        onChange={(event) => { setFiles(Array.from(event.target.files ?? []).sort((a, b) => a.name.localeCompare(b.name))); setRanges({}); setHeaderOptions([]); invalidate(); }} /></label>
      {files.length > 0 && <p className="muted">선택한 파일 {files.length}개: {files.map((file) => file.name).join(', ')}</p>}
      {files.length > 8 && <Notice tone="bad">파일은 최대 8개입니다.</Notice>}
      {files.slice(0, 8).map((file, index) => isXlsx(file) && <details key={`${file.name}-${file.size}-${file.lastModified}`} className="range-slot" open={!!ranges[String(index)]}>
        <summary>{index + 1}번 파일 {file.name} — {ranges[String(index)] ? '범위 적용됨' : '표 범위 선택 (선택 사항)'}</summary>
        <XlsxRangePicker file={file} value={ranges[String(index)] ?? null} disabled={disabled || busy} label={`${index + 1}번 파일 표 범위 선택`}
          onChange={(next) => { const copy = { ...ranges }; if (next) copy[String(index)] = next; else delete copy[String(index)]; setRanges(copy); setHeaderOptions([]); invalidate(); }} />
      </details>)}
    </fieldset>

    <fieldset className="stack" disabled={disabled || busy || !files.length}><legend>2. 원장의 열 지정 (policy.columns)</legend>
      <p className="muted">월별 수요의 열 매핑(period, demand_qty)과 다른 설정입니다. 7개 의미에 원장의 열 이름을 각각 지정합니다.</p>
      <div className="actions start"><button type="button" className="button" onClick={() => void readHeaders()}>첫 파일에서 열 이름 불러오기</button>
        {headerOptions.length > 0 && <span className="muted">열 {headerOptions.length}개: {headerOptions.join(', ')}</span>}</div>
      <div className="sales-columns">{COLUMN_FIELDS.map((field) => <label className="field" key={field.key}><span>{field.label}{field.hint && <small> ({field.hint})</small>}</span>
        <input aria-label={`${field.label} 열`} list="sales-headers" value={columns[field.key]} onChange={(event) => { setColumns({ ...columns, [field.key]: event.target.value }); invalidate(); }} /></label>)}</div>
      <datalist id="sales-headers">{headerOptions.map((header) => <option key={header} value={header} />)}</datalist>
      {!distinct && <Notice tone="bad">7개 항목에 서로 다른 열을 지정해야 합니다.</Notice>}
    </fieldset>

    <fieldset className="stack" disabled={disabled || busy || !files.length}><legend>3. 변환 정책 확인</legend>
      <ul className="policy-list"><li>날짜 기준: 주문일 (YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD)</li><li>"정상"만 수요에 포함</li><li>"취소"는 제외</li>
        <li>"반품"은 절댓값으로 별도 집계 (수요에서 차감하지 않음)</li><li>단위: 팩·EA → EA (환산 계수 1)</li><li>제품·월 단위로 합산</li><li>거래 키(주문번호·행번호) 중복은 오류</li></ul>
      <label><input type="checkbox" checked={useMaster} disabled={!canUseMaster} onChange={(event) => { setUseMaster(event.target.checked); invalidate(); }} /> 승인된 제품 마스터로 제품 코드를 검증합니다.{!canUseMaster && ' (제품·자재 승인 후 사용할 수 있습니다. 지금은 참조 검증 미완료로 표시됩니다.)'}</label>
      <label><input type="checkbox" checked={confirmed} onChange={(event) => { setConfirmed(event.target.checked); invalidate(); }} /> 위 열 지정과 변환 정책을 확인했습니다.</label>
      <div className="actions start"><button type="button" className="button primary" disabled={!files.length || files.length > 8 || !distinct} onClick={() => void runPreview()}>{busy ? '요청 중…' : '변환 미리보기'}</button>
        <span className="muted">{confirmed ? '확인한 정책으로 계산합니다.' : '확인 전에는 "정책 확인 필요"로 응답하며 저장할 수 없습니다.'}</span></div>
    </fieldset>
    {error && <Notice tone="bad">{error} 예시 결과로 대체하지 않습니다.</Notice>}

    {preview && <div className="stack"><h4>4. 변환 결과 검토</h4><Review preview={preview} /></div>}

    {preview && <fieldset className="stack" disabled={disabled || busy}><legend>5. 변환 이력 저장 · 승인 전 배치 생성</legend>
      <p className="muted">저장하면 원본·정책·결과가 이력으로 남고 승인 전 월별 수요 배치가 만들어집니다. 저장은 승인이 아닙니다. 별도로 다시 등록할 필요가 없습니다.</p>
      <div className="sales-columns"><label className="field"><span>작성자 역할 코드</span><input value={createdBy} onChange={(event) => setCreatedBy(event.target.value)} aria-invalid={!ROLE_CODE.test(createdBy)} /></label>
        <label className="field"><span>출처 설명</span><input value={sourceNote} maxLength={1000} onChange={(event) => setSourceNote(event.target.value)} /></label></div>
      <button type="button" className="button primary" disabled={!canSave} onClick={() => void save()}>변환 이력 저장 · 배치 생성</button>
      {(preview.status !== 'TRANSFORMED_PREVIEW' || preview.issues_total > 0 || preview.total === 0) && <p className="muted">상태가 "변환 미리보기 완료"이고 오류가 0건이며 월별 수요가 1행 이상일 때만 저장할 수 있습니다.</p>}
    </fieldset>}
    {saved && <Notice tone="ok">변환 이력 저장 완료 ({saved.reused ? '같은 이력 재사용 · 200' : '신규 · 201'}). 배치 {saved.detail.batch_id} · 상태 {saved.detail.batch_status}. {saved.detail.batch_status === 'APPROVED' ? '이 배치는 이미 승인되어 있습니다.' : saved.detail.batch_status === 'REJECTED' ? '이 배치는 반려된 상태입니다.' : '아직 승인되지 않았습니다. 아래 배치에서 검증 결과를 확인하고 승인하세요.'}</Notice>}

    <div className="stack"><div className="panel-heading"><h4>변환 이력</h4><button type="button" className="button" disabled={disabled || busy} onClick={() => void loadHistory()}>변환 이력 새로고침</button></div>
      {historyError && <Notice tone="warn">{historyError}</Notice>}
      {history && history.length === 0 && <p className="muted">이 데이터셋에 저장된 변환 이력이 없습니다.</p>}
      {history && history.length > 0 && <div className="table-scroll"><table><caption>데이터셋 {datasetId}의 변환 이력</caption>
        <thead><tr><th>저장 시각</th><th>작성자</th><th>배치 상태</th><th>변환 ID</th><th>동작</th></tr></thead>
        <tbody>{history.map((item) => <tr key={item.transformation_id}><td>{item.created_at}</td><td>{item.created_by}</td><td>{item.batch_status}</td><td className="code">{item.transformation_id.slice(0, 8)}</td>
          <td><button type="button" disabled={disabled || busy} onClick={() => void openDetail(item.transformation_id)}>상세</button>{' '}
            <button type="button" disabled={disabled || busy} onClick={() => onBatch(item.batch_id)}>배치 검토</button></td></tr>)}</tbody></table></div>}
      {detail && <div className="stack"><p><strong>변환 {detail.transformation_id.slice(0, 8)}</strong> · 배치 {detail.batch_id} · 현재 배치 상태 {detail.batch_status} · 정책 확인 {detail.preview.policy.user_confirmed ? '됨' : '안 됨'}</p>
        <p className="muted">승인 여부는 배치 상태로 확인합니다. 아래는 저장 당시의 계산 내용입니다.</p><Review preview={detail.preview} /></div>}
    </div>
  </section>;
}
