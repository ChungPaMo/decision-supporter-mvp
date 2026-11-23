import { useEffect, useRef, useState } from 'react';
import { BatchDetail, BatchSummary, Entity, ValidationResult } from '../types/api';
import { apiClient } from '../services/api';
import { CORE_ENTITIES, ENTITY_ORDER, scopedKey, useProductionStore } from '../store/productionStore';
import { BatchBadge, ENTITY_LABEL, errorMessage, Notice, qty, ROLE_CODE, ScreenHeader } from '../components/ui';
import ClassificationPanel from '../components/ClassificationPanel';
import IngestAssistPanel from '../components/IngestAssistPanel';
import SalesTransformPanel from '../components/SalesTransformPanel';
import XlsxRangePicker, { isXlsx } from '../components/XlsxRangePicker';
import { XlsxTableSelection } from '../types/ingestion';

const HIDDEN_COLUMNS = new Set(['location', 'review_required', 'batch_id', 'source_type', 'lines']);
const SELECTION_KEY = 'chungpamo.batch-selection.v1';

// 선택 배치 ID는 데이터셋별로 따로 기억한다. 다른 데이터셋의 UUID를 재사용하지 않는다.
const selectionKey = () => scopedKey(SELECTION_KEY, useProductionStore.getState().datasetId);

function selections(): Partial<Record<Entity, string>> {
  try {
    const value = JSON.parse(localStorage.getItem(selectionKey()) || '{}');
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  } catch { return {}; }
}

function remember(entity: Entity, id: string) {
  // 승인 상태는 저장하지 않는다. ID는 재조회 대상 선택에만 사용한다.
  try { localStorage.setItem(selectionKey(), JSON.stringify({ ...selections(), [entity]: id })); } catch { /* 저장소가 막혀도 서버 재조회 가능 */ }
}

function RowsTable({ rows, caption }: { rows: Array<Record<string, unknown>>; caption: string }) {
  const columns = Object.keys(rows[0] ?? {}).filter((key) => !HIDDEN_COLUMNS.has(key));
  if (!rows.length) return <p className="muted">조회된 데이터가 없습니다.</p>;
  return <div className="table-scroll"><table><caption>{caption}</caption>
    <thead><tr>{columns.map((key) => <th key={key}>{key}</th>)}</tr></thead>
    <tbody>{rows.map((row, i) => <tr key={i}>{columns.map((key) => <td key={key}>{row[key] == null ? '-' : String(row[key])}</td>)}</tr>)}</tbody>
  </table></div>;
}

function ValidationView({ validation }: { validation: ValidationResult }) {
  return <>{validation.sheets.map((sheet, i) => <div key={i} className="stack">
    <h4>{sheet.name}</h4>
    {sheet.issues.length > 0 && <div className="table-scroll"><table>
      <caption>검증 결과 {sheet.issues.length} / 전체 {qty(sheet.issues_total)}건</caption>
      <thead><tr><th>구분</th><th>위치</th><th>코드</th><th>내용</th><th>원본값</th></tr></thead>
      <tbody>{sheet.issues.map((issue, j) => <tr key={j}>
        <td>{issue.severity === 'ERROR' ? '오류' : '경고'}</td><td>{issue.location?.cell_ref ?? (issue.location?.row ? `${issue.location.row}행` : '파일 전체')}</td>
        <td>{issue.code}</td><td>{issue.message}</td><td>{issue.raw_value || '-'}</td>
      </tr>)}</tbody>
    </table></div>}
    <RowsTable rows={sheet.records.slice(0, 10)} caption={`레코드 미리보기 (전체 ${qty(sheet.records_total)}건)`} />
  </div>)}</>;
}

function failureMessage(error: unknown) {
  const detail = (error as { detail?: { code?: string; details?: Array<{ loc?: string[]; message?: string }> } })?.detail;
  const code = detail?.code;
  const base = errorMessage(error);
  if (code === 'REQUEST_INVALID' && Array.isArray(detail?.details)) {
    return `${base} ${detail.details.map((item) => `${item.loc?.join('.') ?? ''}: ${item.message ?? ''}`).join(' / ')}`;
  }
  if (code === 'RESULT_CHANGED' || code === 'VERSION_CONFLICT') return `${base} 최신 상태를 다시 확인한 뒤 재요청하세요.`;
  if (code === 'PERSISTENCE_DISABLED') return `${base} 서버의 저장 기능이 꺼져 있습니다. 승인은 처리되지 않았습니다.`;
  if (code === 'DB_UNAVAILABLE') return `${base} DB 연결 복구 후 다시 조회하세요.`;
  return base;
}

// 등록 순서(제품→자재→BOM→재고→CAPA→Routing→월별 수요)에서 아직 승인되지 않은 첫 항목을 다음 할 일로 안내한다.
function nextAction(batches: Partial<Record<Entity, BatchDetail>>, approved: Partial<Record<Entity, boolean>>, synced: boolean): { text: string; entity?: Entity } {
  if (!synced) return { text: '서버 상태를 먼저 확인하세요.' };
  const entity = ENTITY_ORDER.find((item) => !approved[item]);
  if (!entity) return { text: '모든 데이터가 승인됐습니다. 승인 수요 예측으로 진행하세요.' };
  const label = ENTITY_LABEL[entity];
  const status = batches[entity]?.status;
  if (status === 'READY_FOR_APPROVAL') return { entity, text: `${label} 검증 결과를 확인하고 승인하세요.` };
  if (status === 'HAS_ERRORS') return { entity, text: `${label} 파일의 오류를 고쳐 다시 등록하세요.` };
  if (status === 'MAPPING_HOLD') return { entity, text: `${label}의 열 지정을 확인하고 재검증하세요.` };
  return { entity, text: `${label} 파일을 등록하세요.` };
}

type Action = (operation: () => Promise<BatchDetail>) => Promise<void>;

function BatchPanel({ batch, disabled, act, linked }: { batch: BatchDetail; disabled: boolean; act: Action; linked: boolean }) {
  const [overrides, setOverrides] = useState({ ...batch.settings.column_overrides });
  const [unit, setUnit] = useState(batch.settings.default_unit ?? '');
  const [sheet, setSheet] = useState(batch.settings.sheet ?? '');
  const [actor, setActor] = useState('REVIEWER-01');
  const [reason, setReason] = useState('');
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  const [readError, setReadError] = useState('');
  const finished = batch.status === 'APPROVED' || batch.status === 'REJECTED';
  const holds = batch.validation?.sheets.flatMap((s) => s.holds) ?? [];
  const actorValid = ROLE_CODE.test(actor);

  useEffect(() => {
    let current = true;
    if (batch.status === 'APPROVED') {
      apiClient.approvedData(batch.entity).then((data) => {
        if (current) setRows(data.filter((row) => row.batch_id === batch.batch_id));
      }).catch((error) => { if (current) setReadError(failureMessage(error)); });
    }
    return () => { current = false; };
  }, [batch.batch_id, batch.entity, batch.status]);

  return <section className="panel stack" aria-label={`${ENTITY_LABEL[batch.entity]} 배치`}>
    <div className="panel-heading"><div><h3>{batch.file.name}</h3>
      <p className="muted">버전 {batch.version} · 배치 {batch.batch_id}</p>
      {batch.result_digest && <p className="muted">배치 지문(승인에 사용) <span className="code">{batch.result_digest.slice(0, 16)}…</span>{linked && ' · 판매 원장 변환으로 만든 배치'}</p>}</div><BatchBadge status={batch.status} /></div>
    {batch.status === 'HAS_ERRORS' && <Notice tone="bad">
      {batch.approval_blockers.map((item) => item.message).join(' ')} 원본 오류는 파일을 수정해 다시 등록하세요. 마스터 승인 후에는 이 배치를 재검증할 수 있습니다.
    </Notice>}
    {batch.validation ? <ValidationView validation={batch.validation} /> : <Notice tone="warn">검증 요약이 없습니다. 서버 상태를 다시 조회하세요.</Notice>}
    {batch.status === 'APPROVED' && <>
      <Notice tone="ok">{batch.approved_by} 승인 완료 · {qty(batch.approved_record_count)}건 반영</Notice>
      {readError ? <Notice tone="bad">{readError}</Notice> : <RowsTable rows={rows} caption="서버 승인 데이터 조회 (최대 100개 항목 중 선택 배치)" />}
    </>}
    {batch.status === 'REJECTED' && <Notice tone="muted">{batch.rejected_by} 반려 · 사유: {batch.reject_reason}</Notice>}
    {!finished && <fieldset className="stack review-fields" disabled={disabled}>
      <legend>재검증 설정</legend>
      {linked ? <>
        <Notice tone="muted">판매 원장 변환으로 만든 배치는 열 설정을 바꿀 수 없습니다. 범위나 열을 바꾸려면 변환 미리보기와 저장을 새로 하세요. 제품 등 기준정보를 승인한 뒤에는 같은 설정으로 다시 검증할 수 있습니다.</Notice>
        <button className="button" type="button" onClick={() => void act(() => apiClient.revalidateBatch(batch.batch_id, {
          expected_version: batch.version, column_overrides: {}, default_unit: null, sheet: null,
        }))}>서버 재검증</button></> : <>
      {holds.map((hold, i) => <label className="field" key={`${hold.field}-${i}`}><span>{hold.message}</span>
        <input aria-label={`${hold.field} 매핑 열`} list={`columns-${i}`} value={overrides[hold.field] ?? ''}
          onChange={(e) => setOverrides({ ...overrides, [hold.field]: e.target.value })} placeholder="원본 헤더 또는 열 문자" />
        <datalist id={`columns-${i}`}>{hold.candidates.map((c) => <option key={c} value={c} />)}</datalist>
      </label>)}
      <label className="field"><span>기본 단위 (선택)</span><input value={unit} onChange={(e) => setUnit(e.target.value)} /></label>
      <label className="field"><span>시트 (비우면 전체)</span><input value={sheet} onChange={(e) => setSheet(e.target.value)} /></label>
      <button className="button" type="button" onClick={() => void act(() => apiClient.revalidateBatch(batch.batch_id, {
        expected_version: batch.version, column_overrides: Object.fromEntries(Object.entries(overrides).filter(([, value]) => value.trim())),
        default_unit: unit.trim() || null, sheet: sheet.trim() || null,
      }))}>서버 재검증</button></>}
      <h4 className="decision-title">승인·반려</h4>
      <label className="field"><span>승인자 역할 코드</span><input value={actor} onChange={(e) => setActor(e.target.value)} aria-invalid={!actorValid} /></label>
      <label className="field"><span>반려 사유</span><input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} /></label>
      <div className="actions">
        <button type="button" className="button" disabled={!actorValid || !reason.trim()}
          onClick={() => void act(() => apiClient.rejectBatch(batch.batch_id, actor, reason))}>반려</button>
        <button type="button" className="button primary"
          disabled={!actorValid || batch.status !== 'READY_FOR_APPROVAL' || batch.approval_blockers.length > 0 || !batch.result_digest || !batch.validation}
          onClick={() => void act(() => apiClient.approveBatch(batch.batch_id, actor, batch.result_digest!))}>검증 결과 승인</button>
      </div>
    </fieldset>}
  </section>;
}

export default function DataUploadScreen({ view = 'upload' }: { view?: 'upload' | 'verify' }) {
  const { activeEntity, setActiveEntity, batches, setBatch, setWorkspace, approvedEntities, synced, setSynced, setStep } = useProductionStore();
  const [history, setHistory] = useState<BatchSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [source, setSource] = useState('CLIENT_UPLOAD');
  const [sourceNote, setSourceNote] = useState('');
  // 분류·컬럼 분석·등록이 함께 쓰는 원본 파일. 고르는 것만으로는 서버에 올리지 않는다.
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  // 등록 전 확인에서 사용자가 고른 열 (표준 필드 → 원본 헤더). 파일이나 유형이 바뀌면 버린다.
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  // 사용자가 고른 XLSX 표 범위. 분류·분석·후보에만 쓰이며 표준 등록(/batches)에는 보내지 않는다.
  const [range, setRange] = useState<XlsxTableSelection | null>(null);
  const [demandMode, setDemandMode] = useState<'standard' | 'sales'>('standard');
  const [linkedBatches, setLinkedBatches] = useState<Set<string>>(new Set());
  const datasetId = useProductionStore((state) => state.datasetId);
  const alive = useRef(true);
  const working = useRef(false);
  const batch = batches[activeEntity];
  const verify = view === 'verify';
  const locked = activeEntity !== 'product' && activeEntity !== 'material' && !(approvedEntities.product && approvedEntities.material);

  async function load() {
    const list = await apiClient.allBatches();
    const ids = selections();
    const details: Partial<Record<Entity, BatchDetail>> = {};
    const approved: Partial<Record<Entity, boolean>> = {};
    await Promise.all(ENTITY_ORDER.map(async (entity) => {
      const candidates = list.filter((item) => item.entity === entity);
      approved[entity] = candidates.some((item) => item.status === 'APPROVED');
      const selected = candidates.find((item) => item.batch_id === ids[entity]) ?? candidates[0];
      if (selected) details[entity] = await apiClient.getBatch(selected.batch_id);
    }));
    // 판매 원장 변환으로 만든 배치 목록. 저장 기능이 꺼져 있으면 비워 둔다.
    let linked = new Set<string>();
    try { linked = new Set((await apiClient.transformations(200, 0)).items.map((item) => item.batch_id)); } catch { /* 이력 조회 실패는 변환 패널에서 안내한다 */ }
    if (alive.current) { setHistory(list); setLinkedBatches(linked); setWorkspace(details, approved, true); }
  }

  async function refresh() {
    if (working.current) return;
    working.current = true; setBusy(true); setSynced(false); setMessage('');
    try { await load(); } catch (error) { if (alive.current) setMessage(failureMessage(error)); }
    finally { working.current = false; if (alive.current) setBusy(false); }
  }

  useEffect(() => {
    alive.current = true;
    void refresh();
    return () => { alive.current = false; };
  }, []);

  const act: Action = async (operation) => {
    if (working.current || !synced) return;
    working.current = true; setBusy(true); setMessage('');
    try {
      const updated = await operation();
      remember(updated.entity, updated.batch_id);
      if (alive.current) setBatch(updated.entity, updated);
      await load();
    } catch (error) {
      const code = (error as { detail?: { code?: string } })?.detail?.code;
      if (code === 'VERSION_CONFLICT' || code === 'RESULT_CHANGED' || code === 'ALREADY_APPROVED' || code === 'BATCH_FINALIZED') {
        try { await load(); } catch { if (alive.current) setSynced(false); }
      } else if (code === 'PERSISTENCE_DISABLED' || code === 'DB_UNAVAILABLE' || code === 'NETWORK_ERROR' || !code) {
        if (alive.current) setSynced(false);
      }
      if (alive.current) setMessage(failureMessage(error));
    } finally { working.current = false; if (alive.current) setBusy(false); }
  };

  const pickFile = (file: File | null) => { setSourceFile(file); setOverrides({}); setRange(null); };
  // 범위가 바뀌면 그 범위를 기준으로 고른 열 선택도 버린다.
  const pickRange = (next: XlsxTableSelection | null) => { setRange(next); setOverrides({}); };
  const pickEntity = (entity: Entity) => { if (entity !== activeEntity) setOverrides({}); setActiveEntity(entity); };
  const noteMissing = source !== 'CLIENT_UPLOAD' && !sourceNote.trim();
  // 명시적 등록: 버튼을 눌렀을 때만 서버에 올린다. 등록은 승인이 아니다.
  const register = () => {
    if (!sourceFile) return;
    const file = sourceFile;
    const chosen = Object.keys(overrides).length ? overrides : undefined;
    void act(async () => {
      const created = await apiClient.uploadBatch(file, activeEntity, { source_type: source, source_note: sourceNote, column_overrides: chosen });
      if (alive.current) { setSourceFile(null); setOverrides({}); setRange(null); }
      return created;
    });
  };
  const supportsAssist = CORE_ENTITIES.includes(activeEntity);
  const salesMode = activeEntity === 'monthly_demand' && demandMode === 'sales';
  const useApprovedMaster = !!(approvedEntities.product && approvedEntities.material);

  async function selectBatch(id: string) {
    if (working.current || !id) return;
    working.current = true; setBusy(true); setMessage('');
    try {
      const detail = await apiClient.getBatch(id);
      if (alive.current) { remember(detail.entity, id); setBatch(detail.entity, detail); }
    } catch (error) { if (alive.current) { setMessage(failureMessage(error)); setSynced(false); } }
    finally { working.current = false; if (alive.current) setBusy(false); }
  }

  const next = nextAction(batches, approvedEntities, synced);
  const approvedCount = ENTITY_ORDER.filter((entity) => approvedEntities[entity]).length;
  return <div className="screen data-screen">
    {verify
      ? <ScreenHeader title="검증·승인·등록" description="등록된 배치의 검증 결과를 확인하고, 승인 가능한 데이터만 승인합니다. 자동으로 승인되지 않습니다." />
      : <ScreenHeader title="데이터 등록·승인" description="파일을 서버에 등록하고 검증 결과를 확인해 승인합니다. 제품·자재 승인 후 BOM·재고·CAPA·Routing·월별 수요를 등록하세요." />}
    <div className="actions sync-row"><button className="button" disabled={busy} onClick={() => void refresh()}>서버 상태 다시 조회</button>
      <span role="status">{busy ? '서버 처리 중…' : synced ? '서버 상태 조회 완료' : '서버 상태 확인 필요'}</span></div>
    {message && <div role="alert"><Notice tone="bad">{message}</Notice></div>}
    {!synced && !busy && <Notice tone="warn">서버 연결을 확인한 후 다시 조회하세요. 확인 전에는 등록·승인을 할 수 없습니다.</Notice>}
    <section className="next-step" aria-label="다음 할 일">
      <p><b>다음 할 일</b>{next.text}<small>승인 {approvedCount} / {ENTITY_ORDER.length}</small></p>
      {next.entity && next.entity !== activeEntity && <button type="button" className="button" disabled={busy} onClick={() => pickEntity(next.entity!)}>{ENTITY_LABEL[next.entity]} 열기</button>}
      <button className={`button${next.entity ? '' : ' primary'}`} disabled={busy || !synced || !approvedEntities.monthly_demand}
        onClick={() => setStep('forecast')}>승인 수요 예측</button>
    </section>
    <div className="data-layout"><aside className="entity-list" aria-label="데이터 종류"><ul>
      {ENTITY_ORDER.map((entity) => <li key={entity}><button type="button" disabled={busy} className={entity === activeEntity ? 'active' : ''}
        aria-current={entity === activeEntity ? 'true' : undefined} onClick={() => pickEntity(entity)}>
        <span>{ENTITY_LABEL[entity]}</span>{batches[entity] ? <BatchBadge status={batches[entity]!.status} /> : <small>미등록</small>}
      </button></li>)}
    </ul></aside><div className={`data-columns${verify ? '' : ' with-rail'}`}><div className="stack">
      {!verify && activeEntity === 'monthly_demand' && <div className="workflow-tabs" aria-label="월별 수요 등록 방식">
        <button type="button" aria-pressed={demandMode === 'standard'} disabled={busy} onClick={() => setDemandMode('standard')}>표준 월별 수요 파일 등록</button>
        <button type="button" aria-pressed={demandMode === 'sales'} disabled={busy} onClick={() => setDemandMode('sales')}>판매 원장 변환 (합성 전용)</button>
      </div>}
      {!verify && salesMode && <SalesTransformPanel key={datasetId} canUseMaster={useApprovedMaster} disabled={busy || !synced || locked}
        onBatch={(id) => { void selectBatch(id).then(() => refresh()); }} />}
      {!verify && !salesMode && <section className="panel stack"><h3>{ENTITY_LABEL[activeEntity]} 파일 등록</h3>
        {locked && <Notice tone="warn">제품과 자재를 먼저 승인해야 등록할 수 있습니다.</Notice>}
        {activeEntity === 'capacity' && <Notice tone="muted">CAPA는 파일 3개를 각각 등록·승인합니다. 순서: 자원 → 수량한도 → 시간예산. 수량·설비시간·인시는 합치거나 환산하지 않습니다.</Notice>}
        {activeEntity === 'routing' && <Notice tone="muted">Routing은 CAPA의 자원이 승인된 뒤에 등록합니다. 한 공정이 여러 자원을 동시에 요구할 수 있습니다.</Notice>}
        <fieldset disabled={busy || !synced || locked} className="stack upload-fields"><legend>CSV/XLSX 업로드</legend>
          <label className="field"><span>데이터 출처</span><select aria-label="데이터 출처" value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="CLIENT_UPLOAD">기업 업로드</option><option value="SYNTHETIC">합성 데이터</option><option value="PUBLIC_DEMAND">공개 수요 데이터</option>
          </select></label>
          <label className="field"><span>출처 설명</span><input value={sourceNote} onChange={(e) => setSourceNote(e.target.value)} /></label>
          <label className="field file-field"><span>등록 파일 (CSV/XLSX)</span><input type="file" accept=".csv,.xlsx"
            onChange={(e) => { pickFile(e.target.files?.[0] ?? null); e.target.value = ''; }} disabled={noteMissing} /></label>
          <div className="suggested-file">
            <p><b>선택한 원본</b><span>{sourceFile ? sourceFile.name : '아직 선택한 파일이 없습니다'}</span></p>
            <button type="button" className="button primary" disabled={!sourceFile || noteMissing || !!range} onClick={register}>이 파일 등록</button>
            {sourceFile && <button type="button" className="button" onClick={() => pickFile(null)}>선택 취소</button>}
            <small>{range ? '표준 등록은 표 범위를 지원하지 않아, 범위를 적용한 상태에서는 등록할 수 없습니다. 범위를 해제하면 파일 전체로 등록합니다. 범위를 쓰는 저장은 판매 원장 변환에서만 지원합니다.' : noteMissing ? '합성·공개 데이터는 출처 설명을 먼저 입력해야 등록할 수 있습니다.' : '파일을 고르는 것만으로는 서버에 저장되지 않습니다. "이 파일 등록"을 눌러야 등록되며, 등록은 승인이 아닙니다.'}</small>
          </div>
          {sourceFile && isXlsx(sourceFile) && <div className="range-slot"><XlsxRangePicker key={`${sourceFile.name}-${sourceFile.size}-${sourceFile.lastModified}`} file={sourceFile} value={range} onChange={pickRange} disabled={busy || !synced} /></div>}
        </fieldset>
      </section>}
      {!verify && !salesMode && sourceFile && supportsAssist && <IngestAssistPanel key={`${datasetId}-${activeEntity}-${sourceFile.name}-${sourceFile.size}-${sourceFile.lastModified}-${JSON.stringify(range)}`}
        selection={range} file={sourceFile} entity={activeEntity} overrides={overrides} onOverrides={setOverrides} useApprovedMaster={useApprovedMaster} disabled={busy || !synced} />}
      {!verify && !salesMode && sourceFile && !supportsAssist && <Notice tone="muted">{ENTITY_LABEL[activeEntity]}는 컬럼 후보 추천을 지원하지 않습니다. 표준 헤더 그대로 등록하고, 등록 후 검증 결과에서 열을 확인하세요.</Notice>}
      <label className="field"><span>배치 이력</span><select aria-label="배치 이력" disabled={busy || !synced} value={batch?.batch_id ?? ''} onChange={(e) => void selectBatch(e.target.value)}>
        <option value="">등록된 배치 선택</option>{history.filter((item) => item.entity === activeEntity).map((item) =>
          <option key={item.batch_id} value={item.batch_id}>{item.file.name} · {item.status} · v{item.version} · {item.batch_id.slice(0, 8)}</option>)}
      </select></label>
      {verify && !batch && !busy && <Notice tone="muted">이 데이터 종류에는 등록된 배치가 없습니다. 데이터 업로드에서 파일을 먼저 등록하세요.</Notice>}
      {batch && <BatchPanel key={`${batch.batch_id}-${batch.version}`} batch={batch} disabled={busy || !synced} act={act} linked={linkedBatches.has(batch.batch_id)} />}
    </div>{!verify && <ClassificationPanel file={sourceFile} onFile={pickFile} onChoose={pickEntity} selection={range} disabled={busy}
      onTransform={() => { pickEntity('monthly_demand'); setDemandMode('sales'); }} />}</div></div>
    <Notice tone="info">승인된 월별 수요는 실제 예측에 사용됩니다. 계획·진단은 별도 예시입니다.</Notice>
  </div>;
}
