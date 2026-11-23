import { DragEvent, useMemo, useRef, useState } from 'react';
import { apiClient, DocumentVerdict } from '../services/api';
import { Badge, Notice, errorMessage } from './ui';

const CHUNK = 25; // 서버가 한 번에 받는 파일 수(50) 안에서 진행 상황이 보이도록 나눠 보낸다
const ACCEPT = /\.(xlsx|xlsm|csv)$/i;
const ORDER = ['BOM', 'MPS', 'MRP', 'RCCP', 'CRP', 'MES', 'ERP', '미분류', '확인 필요'];
const MEANING: Record<string, string> = {
  BOM: '자재명세서', MPS: '주생산계획', MRP: '자재소요계획', RCCP: '개략 능력 검토', CRP: '작업장 부하',
  MES: '현장 실적', ERP: '기준정보·거래', 미분류: '해당 없음', '확인 필요': '사람이 확인',
};

type Entry = { isFile: boolean; isDirectory: boolean; file?: (ok: (f: File) => void, fail: () => void) => void; createReader?: () => { readEntries: (ok: (e: Entry[]) => void, fail: () => void) => void } };

// 탐색기에서 폴더를 통째로 끌어다 놓아도 안의 파일을 모두 꺼낸다
async function filesFromEntry(entry: Entry): Promise<File[]> {
  if (entry.isFile && entry.file) return new Promise(resolve => entry.file!(f => resolve([f]), () => resolve([])));
  if (!entry.isDirectory || !entry.createReader) return [];
  const reader = entry.createReader();
  const all: File[] = [];
  for (;;) {
    const batch = await new Promise<Entry[]>(resolve => reader.readEntries(resolve, () => resolve([])));
    if (!batch.length) break;
    for (const child of batch) all.push(...await filesFromEntry(child));
  }
  return all;
}

function tone(category: string): 'ok' | 'warn' | 'muted' | 'info' {
  if (category === '확인 필요') return 'warn';
  if (category === '미분류') return 'muted';
  return 'info';
}

export default function DocumentSortPanel() {
  const [files, setFiles] = useState<File[]>([]);
  const [skipped, setSkipped] = useState(0);
  const [results, setResults] = useState<DocumentVerdict[]>([]);
  const [version, setVersion] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(0);
  const [over, setOver] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  function accept(list: File[]) {
    const ok = list.filter(f => ACCEPT.test(f.name) && !f.name.startsWith('~$'));
    const names = new Set(files.map(f => f.name));
    const fresh = ok.filter(f => !names.has(f.name));
    setFiles([...files, ...fresh]);
    setSkipped(skipped + list.length - fresh.length);
    setResults([]); setDone(0); setError(''); setFilter(null);
  }

  async function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault(); setOver(false);
    if (busy) return;
    const items = Array.from(event.dataTransfer.items ?? []);
    const entries = items.map(item => (item as unknown as { webkitGetAsEntry?: () => Entry | null }).webkitGetAsEntry?.()).filter(Boolean) as Entry[];
    if (entries.length) {
      const nested = await Promise.all(entries.map(filesFromEntry));
      accept(nested.flat());
    } else accept(Array.from(event.dataTransfer.files));
  }

  async function start() {
    setBusy(true); setError(''); setResults([]); setDone(0); setFilter(null);
    const collected: DocumentVerdict[] = [];
    try {
      for (let i = 0; i < files.length; i += CHUNK) {
        const reply = await apiClient.classifyDocuments(files.slice(i, i + CHUNK));
        collected.push(...reply.results);
        setVersion(reply.module_version);
        setResults([...collected]); setDone(Math.min(i + CHUNK, files.length));
      }
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }

  function clear() { setFiles([]); setResults([]); setSkipped(0); setDone(0); setError(''); setFilter(null); }

  function download() {
    const quote = (v: string) => `"${v.replace(/"/g, '""')}"`;
    const lines = ['파일명,분류,확신도,근거', ...results.map(r => [r.file, r.category, r.confidence, r.reason].map(quote).join(','))];
    const url = URL.createObjectURL(new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url; a.download = '문서종류_분류결과.csv'; a.click();
    URL.revokeObjectURL(url);
  }

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of results) map.set(r.category, (map.get(r.category) ?? 0) + 1);
    return ORDER.filter(c => map.has(c)).map(c => [c, map.get(c)!] as const);
  }, [results]);
  const shown = filter ? results.filter(r => r.category === filter) : results;
  const finished = !busy && results.length > 0 && results.length === files.length;

  return <section className="panel stack docsort" aria-label="문서 종류 일괄 분류">
    <div className="panel-heading"><div><h3>엑셀 문서 종류 일괄 분류</h3>
      <p className="muted">엑셀을 종류 구분 없이 한꺼번에 넣으면 BOM · MPS · MRP · RCCP · CRP · MES · ERP 로 나눕니다. 파일은 저장하지 않으며, 등록·승인과는 별개입니다.</p></div>
      <span className="badge badge-info">추천 전용</span></div>

    <div className={`dropzone${over ? ' over' : ''}${busy ? ' disabled' : ''}`} role="button" tabIndex={0} aria-label="엑셀 파일을 끌어다 놓거나 눌러서 선택"
      onDragOver={e => { e.preventDefault(); if (!busy) setOver(true); }} onDragLeave={() => setOver(false)} onDrop={e => void drop(e)}
      onClick={() => !busy && input.current?.click()} onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && !busy) input.current?.click(); }}>
      <strong>{files.length ? `파일 ${files.length}개 준비됨` : '여기에 엑셀 파일이나 폴더를 끌어다 놓으세요'}</strong>
      <span className="muted">{files.length ? '파일을 더 끌어다 놓으면 추가됩니다' : '또는 눌러서 파일 선택 (.xlsx, .xlsm, .csv · 여러 개 가능)'}</span>
      <input ref={input} type="file" accept=".xlsx,.xlsm,.csv" multiple hidden
        onChange={e => { accept(Array.from(e.target.files ?? [])); e.target.value = ''; }} />
    </div>
    {skipped > 0 && <p className="muted">엑셀·CSV가 아니거나 이름이 같은 파일 {skipped}개는 제외했습니다.</p>}

    <div className="actions">
      <button className="button primary" disabled={busy || !files.length} onClick={() => void start()}>{busy ? `분류 중… ${done} / ${files.length}` : '분류 시작'}</button>
      <button className="button" disabled={busy || !files.length} onClick={clear}>비우기</button>
      {finished && <button className="button" onClick={download}>결과 CSV 내려받기</button>}
    </div>
    {busy && <progress value={done} max={files.length} aria-label="분류 진행 상황" />}
    {error && <div role="alert"><Notice tone="bad">{error} 분류된 {results.length}개까지는 아래에 표시합니다.</Notice></div>}

    {results.length > 0 && <>
      <div className="docsort-summary" role="group" aria-label="분류별 파일 수">
        <button className={`docsort-chip${filter === null ? ' active' : ''}`} onClick={() => setFilter(null)}><strong>{results.length}</strong><span>전체</span></button>
        {counts.map(([category, n]) => <button key={category} className={`docsort-chip${filter === category ? ' active' : ''}`}
          onClick={() => setFilter(filter === category ? null : category)}><strong>{n}</strong><span>{category}</span><small>{MEANING[category] ?? ''}</small></button>)}
      </div>
      <div className="table-scroll docsort-table"><table><caption>분류 결과 {shown.length}개{filter ? ` · ${filter}` : ''} · {version}</caption>
        <thead><tr><th>파일명</th><th>분류</th><th>확신도</th><th>근거</th></tr></thead>
        <tbody>{shown.map(r => <tr key={r.file}><td>{r.file}</td><td><Badge tone={tone(r.category)}>{r.category}</Badge></td><td>{r.confidence}</td><td>{r.reason}</td></tr>)}</tbody>
      </table></div>
      <p className="muted">낱말 사전으로 판단한 추천입니다. "확인 필요"와 "미분류"는 사람이 직접 열어 확인하세요. 확신도는 확률이 아닙니다.</p>
    </>}
  </section>;
}
