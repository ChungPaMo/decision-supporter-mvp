import { useRef, useState } from 'react';
import { apiClient } from '../services/api';
import { XlsxLayoutReply, XlsxTableSelection } from '../types/ingestion';
import { Notice, errorMessage } from './ui';

export const isXlsx = (file: File | null) => !!file && /\.xlsx$/i.test(file.name);
export function columnLetter(col: number): string {
  let n = col; let text = '';
  while (n > 0) { const rest = (n - 1) % 26; text = String.fromCharCode(65 + rest) + text; n = Math.floor((n - 1) / 26); }
  return text;
}
export const describeSelection = (selection: XlsxTableSelection) =>
  `시트 "${selection.sheet}" · 헤더 ${selection.header_row}행 · 데이터 ${selection.data_start_row}~${selection.data_end_row}행 · ${columnLetter(selection.first_col)}~${columnLetter(selection.last_col)}열`;

const RANGE_ERRORS: Record<string, string> = {
  XLSX_SOURCE_CHANGED: '파일이 바뀌었습니다. 시트 목록을 다시 읽고 범위를 다시 선택하세요.',
  XLSX_SHEET_INVALID: '정확한 이름의 보이는 시트를 선택하세요.',
  XLSX_RANGE_INVALID: '범위를 확인하세요. 헤더 행 < 데이터 시작 행 ≤ 데이터 끝 행, 첫 열 ≤ 끝 열이어야 하고 시트 안에 있어야 합니다.',
  XLSX_MERGED_RANGE: '병합된 셀이 선택 범위에 닿습니다. 병합되지 않은 헤더 행이나 범위를 지정하세요.',
  XLSX_HEADER_INVALID: '헤더 행을 확인하세요. 열 이름이 겹치거나, 수식·오류 셀이거나, 헤더가 비어 있습니다.',
  UNSUPPORTED_TYPE: 'XLSX 파일만 범위를 선택할 수 있습니다.',
  ANALYSIS_LIMIT: '분석 한도(8개 시트, 64열, 시트당 100,000행)를 넘었습니다.',
  FILE_TOO_LARGE: '파일이 10MiB를 넘습니다.',
};
export function rangeFailure(error: unknown): string {
  const detail = (error as { detail?: { code?: string; message?: string } })?.detail;
  if (detail?.code && RANGE_ERRORS[detail.code]) return `${RANGE_ERRORS[detail.code]} (${detail.code})`;
  return detail?.code ? `${detail.message ?? '요청이 거부되었습니다.'} (${detail.code})` : errorMessage(error);
}

const VISIBILITY: Record<string, string> = { visible: '', hidden: ' (숨김 — 선택 불가)', veryHidden: ' (숨김 — 선택 불가)' };
const WINDOW_ROWS = 20; const WINDOW_COLS = 16;
type Draft = { header_row: string; data_start_row: string; data_end_row: string; first_col: string; last_col: string };
const EMPTY: Draft = { header_row: '', data_start_row: '', data_end_row: '', first_col: '', last_col: '' };

interface Props { file: File; value: XlsxTableSelection | null; onChange: (selection: XlsxTableSelection | null) => void; disabled?: boolean; label?: string }

// XLSX 의 시트와 표 범위를 사용자가 직접 고른다. 좌표는 원본 기준 1부터 시작하며 끝을 포함한다.
// 범위를 고르지 않으면 기존 방식(파일 전체 파싱)을 그대로 쓴다.
export default function XlsxRangePicker({ file, value, onChange, disabled = false, label }: Props) {
  const [layout, setLayout] = useState<XlsxLayoutReply | null>(null);
  const [sheet, setSheet] = useState('');
  const [origin, setOrigin] = useState({ row: 1, col: 1 });
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const seq = useRef(0);

  async function load(nextSheet?: string, row = 1, col = 1) {
    const ticket = ++seq.current;
    setBusy(true); setError('');
    try {
      const reply = await apiClient.xlsxLayout(file, nextSheet ? { sheet: nextSheet, row_start: row, row_limit: WINDOW_ROWS, col_start: col, col_limit: WINDOW_COLS } : undefined);
      if (ticket !== seq.current) return;
      setLayout(reply); setOrigin({ row, col });
    } catch (problem) { if (ticket === seq.current && (problem as { detail?: { code?: string } })?.detail?.code !== 'DATASET_CHANGED') setError(rangeFailure(problem)); }
    finally { if (ticket === seq.current) setBusy(false); }
  }
  const chooseSheet = (name: string) => { setSheet(name); setDraft(EMPTY); if (value) onChange(null); if (name) void load(name, 1, 1); };
  const edit = (key: keyof Draft, text: string) => { setDraft({ ...draft, [key]: text }); if (value) onChange(null); };
  const info = layout?.sheets.find((item) => item.name === sheet);
  const numbers = { header: Number(draft.header_row), start: Number(draft.data_start_row), end: Number(draft.data_end_row), first: Number(draft.first_col), last: Number(draft.last_col) };
  const filled = Object.values(draft).every((text) => /^\d+$/.test(text));
  const ordered = filled && numbers.header >= 1 && numbers.header < numbers.start && numbers.start <= numbers.end && numbers.first >= 1 && numbers.first <= numbers.last
    && (!info || (numbers.end <= info.max_row && numbers.last <= info.max_col));
  const apply = () => {
    if (!layout || !sheet || !ordered) return;
    onChange({ source_sha256: layout.source_sha256, sheet, header_row: numbers.header, data_start_row: numbers.start, data_end_row: numbers.end, first_col: numbers.first, last_col: numbers.last });
  };
  const win = layout?.window ?? null;
  const cellAt = new Map((win?.cells ?? []).map((cell) => [`${cell.row}:${cell.col}`, cell]));
  const rows = win ? Array.from({ length: win.last_row - win.first_row + 1 }, (_, i) => win.first_row + i) : [];
  const cols = win ? Array.from({ length: win.last_col - win.first_col + 1 }, (_, i) => win.first_col + i) : [];
  const inCols = (col: number) => filled && col >= numbers.first && col <= numbers.last;
  const cellClass = (row: number, col: number) => !inCols(col) ? '' : row === numbers.header ? 'range-header' : row >= numbers.start && row <= numbers.end ? 'range-body' : '';

  return <div className="range-picker stack" role="group" aria-label={label ?? `${file.name} 표 범위 선택`}>
    <div className="actions start">
      <button type="button" className="button" disabled={disabled || busy} onClick={() => void load()}>{layout ? '시트 목록 다시 읽기' : '시트·표 범위 선택'}</button>
      {value && <button type="button" className="button" disabled={disabled} onClick={() => { onChange(null); }}>범위 해제 (파일 전체 사용)</button>}
      {busy && <span className="muted">서버에 요청 중…</span>}
    </div>
    {value ? <Notice tone="ok">적용한 범위: {describeSelection(value)}</Notice>
      : <p className="muted">범위를 지정하지 않으면 기존 방식대로 파일 전체를 읽습니다. 제목·결재란이 있거나 표가 여러 개인 엑셀은 범위를 지정하세요.</p>}
    {error && <Notice tone="bad">{error}</Notice>}
    {layout && <>
      <label className="field"><span>시트</span><select aria-label="시트" value={sheet} disabled={disabled || busy} onChange={(event) => chooseSheet(event.target.value)}>
        <option value="">시트를 선택하세요</option>
        {layout.sheets.map((item) => <option key={item.name} value={item.name} disabled={item.visibility !== 'visible'}>{item.name}{VISIBILITY[item.visibility]} · {item.max_row}행 × {item.max_col}열</option>)}
      </select></label>
      {win && <>
        <div className="actions start">
          <button type="button" className="button" disabled={disabled || busy || origin.row <= 1} onClick={() => void load(sheet, Math.max(1, origin.row - WINDOW_ROWS), origin.col)}>위 {WINDOW_ROWS}행</button>
          <button type="button" className="button" disabled={disabled || busy || !info || win.last_row >= info.max_row} onClick={() => void load(sheet, origin.row + WINDOW_ROWS, origin.col)}>아래 {WINDOW_ROWS}행</button>
          <button type="button" className="button" disabled={disabled || busy || origin.col <= 1} onClick={() => void load(sheet, origin.row, Math.max(1, origin.col - WINDOW_COLS))}>왼쪽 열</button>
          <button type="button" className="button" disabled={disabled || busy || !info || win.last_col >= info.max_col} onClick={() => void load(sheet, origin.row, origin.col + WINDOW_COLS)}>오른쪽 열</button>
          <span className="muted">{win.first_row}~{win.last_row}행 · {columnLetter(win.first_col)}~{columnLetter(win.last_col)}열 표시 중</span>
        </div>
        <div className="table-scroll"><table className="range-grid"><caption>셀 미리보기 (원본 좌표 · 값은 최대 80자, 이메일·전화는 가려짐)</caption>
          <thead><tr><th>행</th>{cols.map((col) => <th key={col} className={win.hidden_columns.includes(col) ? 'hidden-col' : ''}>{columnLetter(col)} ({col}){win.hidden_columns.includes(col) ? ' 숨김' : ''}</th>)}</tr></thead>
          <tbody>{rows.map((row) => <tr key={row}><th>{row}</th>{cols.map((col) => { const cell = cellAt.get(`${row}:${col}`);
            return <td key={col} className={cellClass(row, col)}>{!cell || cell.kind === 'empty' ? '' : cell.kind === 'formula' ? '(수식)' : cell.kind === 'merged' ? '(병합)' : cell.kind === 'error' ? '(오류)' : cell.value}</td>; })}</tr>)}</tbody>
        </table></div>
        {win.merged_ranges.length > 0 && <p className="muted">병합 영역: {win.merged_ranges.slice(0, 12).join(', ')}{win.merges_truncated || win.merged_ranges.length > 12 ? ' …' : ''} — 병합이 닿는 헤더·데이터는 선택할 수 없습니다.</p>}
        <div className="range-inputs">
          <label className="field"><span>헤더 행</span><input inputMode="numeric" aria-label="헤더 행" value={draft.header_row} disabled={disabled} onChange={(event) => edit('header_row', event.target.value)} /></label>
          <label className="field"><span>데이터 시작 행</span><input inputMode="numeric" aria-label="데이터 시작 행" value={draft.data_start_row} disabled={disabled} onChange={(event) => edit('data_start_row', event.target.value)} /></label>
          <label className="field"><span>데이터 끝 행</span><input inputMode="numeric" aria-label="데이터 끝 행" value={draft.data_end_row} disabled={disabled} onChange={(event) => edit('data_end_row', event.target.value)} /></label>
          <label className="field"><span>첫 열 번호</span><input inputMode="numeric" aria-label="첫 열 번호" value={draft.first_col} disabled={disabled} onChange={(event) => edit('first_col', event.target.value)} /></label>
          <label className="field"><span>끝 열 번호</span><input inputMode="numeric" aria-label="끝 열 번호" value={draft.last_col} disabled={disabled} onChange={(event) => edit('last_col', event.target.value)} /></label>
        </div>
        <p className="muted">열은 번호로 입력합니다 (A=1, B=2, C=3 …). 행·열은 원본 기준 1부터이며 끝을 포함합니다.{info ? ` 이 시트는 ${info.max_row}행 × ${info.max_col}열입니다.` : ''}</p>
        {filled && !ordered && <Notice tone="warn">헤더 행 &lt; 데이터 시작 행 ≤ 데이터 끝 행, 첫 열 ≤ 끝 열이어야 하며 시트 범위 안이어야 합니다.</Notice>}
        <div className="actions start"><button type="button" className="button primary" disabled={disabled || !ordered || !!value} onClick={apply}>이 범위 적용</button>
          {value && <span className="muted">범위가 적용됐습니다. 값을 바꾸면 적용이 해제되고 이전 분석·후보·미리보기 결과를 버립니다.</span>}</div>
      </>}
    </>}
  </div>;
}
