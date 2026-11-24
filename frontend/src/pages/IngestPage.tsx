import { DragEvent, useEffect, useMemo, useRef, useState } from 'react';
import { BatchSt, Empty, ENTITY_NAME, failure, failureCode, go, Icon, Kpi, Notice, num, St, Tag, when } from '../app/core';
import { Ring } from '../app/widgets';
import { apiClient, DocumentVerdict } from '../services/api';
import { BatchDetail, BatchSummary, Entity } from '../types/api';
import { ClassificationResult } from '../types/modules';

const ACCEPT = /\.(xlsx|xlsm|csv)$/i;
const SORT_ONLY_OVER = 20;        // 이보다 많이 넣으면 등록하지 않고 문서 종류만 나눠 보여 준다
const ROLE = /^[A-Za-z0-9][A-Za-z0-9_.-]{1,59}$/;
const DOC_ORDER = ['BOM', 'MPS', 'MRP', 'RCCP', 'CRP', 'MES', 'ERP', '미분류', '확인 필요'];
const DOC_COLOR: Record<string, string> = { BOM: '#00a896', MPS: '#2f6ea5', MRP: '#6b5bb5', RCCP: '#a8650e', CRP: '#c0392f', MES: '#17835f', ERP: '#52625f', 미분류: '#b9c2c0', '확인 필요': '#e0a93b' };

// 등록 순서. 파일 하나가 한 줄을 채운다. 제품·자재가 먼저 승인돼야 뒤의 것을 검증할 수 있다.
interface Slot { key: string; entity: Entity; section: string | null; label: string; tech: string; hint: RegExp | null }
const SLOTS: Slot[] = [
  { key: 'product', entity: 'product', section: null, label: '제품 목록', tech: '제품', hint: null },
  { key: 'material', entity: 'material', section: null, label: '자재 목록', tech: '자재', hint: null },
  { key: 'bom', entity: 'bom', section: null, label: '제품 구성표', tech: 'BOM', hint: null },
  { key: 'inventory', entity: 'inventory', section: null, label: '재고 현황', tech: '재고', hint: null },
  { key: 'capacity.resources', entity: 'capacity', section: 'resources', label: '설비·인력 목록', tech: 'CAPA · 자원', hint: /resource|자원|설비목록/i },
  { key: 'capacity.quantity_limits', entity: 'capacity', section: 'quantity_limits', label: '생산 수량 한도', tech: 'CAPA · 수량 한도', hint: /quantity|limit|한도/i },
  { key: 'capacity.hours_budgets', entity: 'capacity', section: 'hours_budgets', label: '설비 가동 시간', tech: 'CAPA · 시간 예산', hint: /hour|budget|시간/i },
  { key: 'routing', entity: 'routing', section: 'routing_steps', label: '공정 순서', tech: 'Routing', hint: null },
  { key: 'monthly_demand', entity: 'monthly_demand', section: null, label: '월별 수요', tech: '월별 수요', hint: null },
];
const slotFor = (entity: Entity | null, section: string | null, name: string): string | null => {
  if (!entity) return null;
  const same = SLOTS.filter((s) => s.entity === entity);
  return (same.find((s) => s.section === section) ?? same.find((s) => s.hint?.test(name)) ?? same[0])?.key ?? null;
};

const KIND: Record<Entity, string> = { product: '제품 목록', material: '자재 목록', bom: '제품 구성표', inventory: '재고 현황', capacity: '설비·생산능력', routing: '공정 순서', monthly_demand: '월별 수요' };
const UNKNOWN = '알아보지 못함';
interface Item { id: string; file: File; slot: string | null; kind: string; note: string; manual: boolean; batch: BatchDetail | BatchSummary | null; busy: boolean; error: string }
type FsEntry = { isFile: boolean; isDirectory: boolean; file?: (ok: (f: File) => void, fail: () => void) => void; createReader?: () => { readEntries: (ok: (e: FsEntry[]) => void, fail: () => void) => void } };
async function filesFromEntry(entry: FsEntry): Promise<File[]> {
  if (entry.isFile && entry.file) return new Promise((resolve) => entry.file!((f) => resolve([f]), () => resolve([])));
  if (!entry.isDirectory || !entry.createReader) return [];
  const reader = entry.createReader();
  const all: File[] = [];
  for (;;) {
    const batch = await new Promise<FsEntry[]>((resolve) => reader.readEntries(resolve, () => resolve([])));
    if (!batch.length) break;
    for (const child of batch) all.push(...await filesFromEntry(child));
  }
  return all;
}
// 분류기 결과를 등록 줄로 옮긴다. 다섯 유형은 추천을, CAPA·Routing은 서버가 알려 주는 등록 경로를 쓴다.
function decide(result: ClassificationResult, name: string): Pick<Item, 'slot' | 'note' | 'kind'> {
  if (result.recommended_entity) return { slot: slotFor(result.recommended_entity, null, name), kind: KIND[result.recommended_entity], note: result.reasons[0] ?? '' };
  if (result.registration_hint) return { slot: slotFor(result.registration_hint.entity, result.registration_hint.sections[0] ?? null, name), kind: KIND[result.registration_hint.entity], note: '등록 양식의 열 이름과 정확히 일치합니다.' };
  return { slot: null, kind: UNKNOWN, note: result.reasons[0] ?? '무슨 자료인지 알아보지 못했습니다.' };
}
const isDetail = (batch: Item['batch']): batch is BatchDetail => !!batch && 'validation' in batch;

export default function IngestPage({ onChanged }: { onChanged: () => void }) {
  const [items, setItems] = useState<Item[]>([]);
  const [staged, setStaged] = useState<File[]>([]);   // 올렸지만 아직 분류하지 않은 파일
  const [sorting, setSorting] = useState(false);
  const [server, setServer] = useState<BatchSummary[]>([]);
  const [selected, setSelected] = useState<string>('product');
  const [over, setOver] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'warn' | 'bad'; text: string } | null>(null);
  const [running, setRunning] = useState(false);
  const [source, setSource] = useState('SYNTHETIC');
  const [note, setNote] = useState('충파모 공식 합성 자료');
  const [actor, setActor] = useState('planner01');
  const [reason, setReason] = useState('');
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [docs, setDocs] = useState<{ total: number; results: DocumentVerdict[]; busy: boolean; filter: string | null } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const alive = useRef(true);
  const itemsRef = useRef<Item[]>([]);
  itemsRef.current = items;

  const loadServer = async () => { const list = await apiClient.allBatches(); if (alive.current) setServer(list); return list; };
  useEffect(() => { alive.current = true; void loadServer().catch((e) => setMessage({ tone: 'bad', text: failure(e) })); return () => { alive.current = false; }; }, []);
  const patch = (id: string, change: Partial<Item>) => setItems((list) => list.map((item) => (item.id === id ? { ...item, ...change } : item)));
  const slotOf = (key: string | null) => SLOTS.find((s) => s.key === key) ?? null;
  // 같은 이름·같은 유형으로 이미 서버에 있는 자료 (반려된 것은 뺀 가장 최근 것)
  const match = (list: BatchSummary[], name: string, entity: Entity | undefined) => list.find((b) => b.file.name === name && b.entity === entity && b.status !== 'REJECTED') ?? null;

  // 파일을 올리지 않았어도 서버에 이미 있는 자료를 줄에 붙여 보여 준다.
  const rows = useMemo(() => {
    const used = new Set<string>();
    return SLOTS.map((slot) => {
      const item = items.find((i) => i.slot === slot.key) ?? null;
      let batch: Item['batch'] = item?.batch ?? null;
      if (!item) {
        const pool = server.filter((b) => b.entity === slot.entity && b.status !== 'REJECTED' && !used.has(b.batch_id) && !items.some((i) => i.batch?.batch_id === b.batch_id));
        batch = (slot.hint ? pool.find((b) => slot.hint!.test(b.file.name)) : pool.find((b) => !SLOTS.some((s) => s.entity === slot.entity && s.key !== slot.key && s.hint?.test(b.file.name)))) ?? null;
      }
      if (batch) used.add(batch.batch_id);
      return { slot, item, batch };
    });
  }, [items, server]);
  const loose = items.filter((i) => !i.slot);
  const current = rows.find((r) => r.slot.key === selected) ?? rows[0];

  async function sortDocuments(files: File[]) {
    setDocs({ total: files.length, results: [], busy: true, filter: null });
    const collected: DocumentVerdict[] = [];
    try {
      for (let i = 0; i < files.length; i += 25) {
        collected.push(...(await apiClient.classifyDocuments(files.slice(i, i + 25))).results);
        if (alive.current) setDocs({ total: files.length, results: [...collected], busy: i + 25 < files.length, filter: null });
      }
    } catch (error) { setMessage({ tone: 'bad', text: failure(error) }); if (alive.current) setDocs((d) => (d ? { ...d, busy: false } : d)); }
  }
  async function accept(raw: File[]) {
    const files = raw.filter((f) => ACCEPT.test(f.name) && !f.name.startsWith('~$'));
    setMessage(null);
    if (!files.length) { setMessage({ tone: 'warn', text: '엑셀(.xlsx, .xlsm)이나 CSV 파일을 넣어 주세요.' }); return; }
    // 올리기만 한다. 분류는 "분류하기"를 눌러야 시작한다.
    setStaged((list) => { const known = new Set([...list.map((f) => f.name), ...itemsRef.current.map((i) => i.file.name)]); return [...list, ...files.filter((f) => !known.has(f.name))]; });
  }
  async function classify() {
    const files = staged;
    if (!files.length || sorting) return;
    setSorting(true); setMessage(null);
    try {
      if (files.length > SORT_ONLY_OVER) { await sortDocuments(files); return; }
      setDocs(null);
      await place(files);
    } finally { if (alive.current) { setStaged([]); setSorting(false); } }
  }
  async function place(files: File[]) {
    const fresh: Item[] = files.map((file) => ({ id: `${file.name}-${file.size}-${file.lastModified}`, file, slot: null, kind: '', note: '', manual: false, batch: null, busy: true, error: '' }));
    setItems((list) => [...list, ...fresh]);
    const list = await loadServer().catch(() => server);
    const taken = new Set(itemsRef.current.map((i) => i.slot));
    for (const item of fresh) {
      try {
        const verdict = decide(await apiClient.classifyFile(item.file, false), item.file.name);
        const slot = verdict.slot && !taken.has(verdict.slot) ? verdict.slot : null;
        if (slot) taken.add(slot);
        patch(item.id, { slot, kind: verdict.kind, note: verdict.slot && !slot ? `${slotOf(verdict.slot)?.label} 줄에 이미 다른 파일이 있습니다.` : verdict.note, busy: false, batch: slot ? match(list, item.file.name, slotOf(slot)?.entity) : null });
      } catch (error) { patch(item.id, { busy: false, kind: UNKNOWN, error: failure(error) }); }
    }
  }
  async function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault(); setOver(false);
    const entries = Array.from(event.dataTransfer.items ?? []).map((it) => (it as unknown as { webkitGetAsEntry?: () => FsEntry | null }).webkitGetAsEntry?.()).filter(Boolean) as FsEntry[];
    void accept(entries.length ? (await Promise.all(entries.map(filesFromEntry))).flat() : Array.from(event.dataTransfer.files));
  }

  const actorOk = ROLE.test(actor);
  const noteOk = source === 'CLIENT_UPLOAD' || note.trim().length > 0;
  const finish = async () => { await loadServer().catch(() => undefined); onChanged(); };

  async function register(item: Item): Promise<BatchDetail | null> {
    const slot = slotOf(item.slot);
    if (!slot) return null;
    patch(item.id, { busy: true, error: '' });
    try {
      const created = await apiClient.uploadBatch(item.file, slot.entity, { source_type: source, source_note: note, created_by: actorOk ? actor : undefined });
      patch(item.id, { busy: false, batch: created });
      return created;
    } catch (error) {
      if (failureCode(error) === 'DUPLICATE_UPLOAD') {
        const found = match(await loadServer(), item.file.name, slot.entity);
        const detail = found ? await apiClient.getBatch(found.batch_id).catch(() => null) : null;
        patch(item.id, { busy: false, batch: detail ?? found, error: detail || found ? '' : '같은 파일이 이미 등록돼 있습니다.' });
        return detail;
      }
      patch(item.id, { busy: false, error: failure(error) });
      return null;
    }
  }
  async function approve(item: Item | null, batch: BatchDetail | BatchSummary): Promise<boolean> {
    if (!batch.result_digest) { setMessage({ tone: 'bad', text: '승인할 검증 결과가 없습니다.' }); return false; }
    if (item) patch(item.id, { busy: true, error: '' });
    try { const done = await apiClient.approveBatch(batch.batch_id, actor, batch.result_digest); if (item) patch(item.id, { busy: false, batch: done }); return true; }
    catch (error) { if (item) patch(item.id, { busy: false, error: failure(error) }); else setMessage({ tone: 'bad', text: failure(error) }); return false; }
  }
  async function reject(item: Item | null, batch: BatchDetail | BatchSummary) {
    if (!reason.trim()) { setMessage({ tone: 'warn', text: '반려 사유를 적어 주세요.' }); return; }
    try { const done = await apiClient.rejectBatch(batch.batch_id, actor, reason); if (item) patch(item.id, { batch: done }); setReason(''); setMessage({ tone: 'ok', text: `${batch.file.name}을 반려했습니다.` }); await finish(); }
    catch (error) { setMessage({ tone: 'bad', text: failure(error) }); }
  }
  async function revalidate(item: Item | null, batch: BatchDetail | BatchSummary) {
    const chosen = Object.fromEntries(Object.entries(overrides).filter(([, v]) => v.trim()));
    try { const done = await apiClient.revalidateBatch(batch.batch_id, { expected_version: batch.version, column_overrides: { ...batch.settings.column_overrides, ...chosen } }); if (item) patch(item.id, { batch: done }); setOverrides({}); await finish(); }
    catch (error) { setMessage({ tone: 'bad', text: failure(error) }); }
  }

  // 위에서부터 차례로 등록하고, 검증에 문제가 없으면 승인한다. 문제가 나오면 그 줄에서 멈춘다.
  async function runAll() {
    if (!actorOk) { setMessage({ tone: 'warn', text: '담당자 코드를 영문·숫자 2자 이상으로 적어 주세요.' }); return; }
    setRunning(true); setMessage(null);
    let count = 0;
    for (const slot of SLOTS) {
      const item = itemsRef.current.find((i) => i.slot === slot.key);
      if (!item) continue;
      setSelected(slot.key);
      let batch = item.batch;
      if (batch?.status === 'APPROVED') continue;
      if (!batch || batch.status === 'REJECTED') batch = await register(item);
      if (!batch) { setMessage({ tone: 'bad', text: `${slot.label}(${item.file.name})에서 멈췄습니다. 오른쪽에서 원인을 확인하세요.` }); break; }
      if (batch.status === 'APPROVED') continue;
      if (batch.status !== 'READY_FOR_APPROVAL') { setMessage({ tone: 'warn', text: `${slot.label}(${item.file.name})은 사람이 확인해야 합니다. 오른쪽에서 고친 뒤 다시 누르세요.` }); break; }
      if (!(await approve(item, batch))) { setMessage({ tone: 'bad', text: `${slot.label} 승인에서 멈췄습니다.` }); break; }
      count += 1;
    }
    await finish(); setRunning(false);
    if (count) setMessage((m) => m ?? { tone: 'ok', text: `${count}개 파일을 승인했습니다.` });
  }

  async function open(key: string) {
    setSelected(key); setOverrides({});
    const row = rows.find((r) => r.slot.key === key);
    if (row?.item && row.batch && !isDetail(row.batch)) { try { patch(row.item.id, { batch: await apiClient.getBatch(row.batch.batch_id) }); } catch { /* 요약만 보여 준다 */ } }
  }
  const [peek, setPeek] = useState<BatchDetail | null>(null);
  useEffect(() => {
    setPeek(null);
    if (current && !current.item && current.batch) void apiClient.getBatch(current.batch.batch_id).then((d) => { if (alive.current) setPeek(d); }).catch(() => undefined);
  }, [current?.batch?.batch_id, current?.item]);

  const done = rows.filter((r) => r.batch?.status === 'APPROVED').length;
  const pending = rows.filter((r) => r.item && r.batch?.status !== 'APPROVED');
  const stuck = rows.filter((r) => r.item?.error || r.batch?.status === 'MAPPING_HOLD' || r.batch?.status === 'HAS_ERRORS');
  const nextRow = rows.find((r) => r.batch?.status !== 'APPROVED');
  const orphans = server.filter((b) => (b.status === 'MAPPING_HOLD' || b.status === 'HAS_ERRORS') && !rows.some((r) => r.batch?.batch_id === b.batch_id));
  const docCounts = useMemo(() => { const map = new Map<string, number>(); for (const r of docs?.results ?? []) map.set(r.category, (map.get(r.category) ?? 0) + 1); return DOC_ORDER.filter((c) => map.has(c)).map((c) => [c, map.get(c)!] as const); }, [docs]);
  const batch = current?.batch ?? null;
  const detail = isDetail(batch) ? batch : peek && peek.batch_id === batch?.batch_id ? peek : null;
  const holds = detail?.validation?.sheets.flatMap((sheet) => sheet.holds) ?? [];
  const issues = detail?.validation?.sheets.flatMap((sheet) => sheet.issues) ?? [];
  const busyAny = running || sorting || items.some((i) => i.busy);
  const kindCounts = useMemo(() => { const map = new Map<string, number>(); for (const i of items) if (i.kind) map.set(i.kind, (map.get(i.kind) ?? 0) + 1); return [...Object.values(KIND), UNKNOWN].filter((k) => map.has(k)).map((k) => [k, map.get(k)!] as const); }, [items]);
  const sorted = items.filter((i) => i.kind).length;

  return <>
    <div className={`drop${over ? ' over' : ''}`} role="button" tabIndex={0} aria-label="엑셀이나 CSV 파일을 끌어다 놓거나 눌러서 선택"
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={(e) => void drop(e)}
      onClick={() => input.current?.click()} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') input.current?.click(); }}>
      <Icon name="upload" /><div><b>엑셀·CSV 파일이나 폴더를 여기에 놓으세요</b><span>올린 뒤 "분류하기"를 누르면 무슨 자료가 몇 개인지 나눠 보여 줍니다. {SORT_ONLY_OVER}개보다 많으면 등록하지 않고 문서 종류만 나눕니다.</span></div>
      <span className="btn primary lg"><Icon name="upload" />파일 고르기</span>
      <input ref={input} type="file" accept=".xlsx,.xlsm,.csv" multiple hidden onChange={(e) => { void accept(Array.from(e.target.files ?? [])); e.target.value = ''; }} />
    </div>
    {staged.length > 0 && <section className="panel"><header><div><h2>올린 파일 {staged.length}개</h2><p>{sorting ? '분류하는 중입니다…' : staged.length > SORT_ONLY_OVER ? `아직 분류하지 않았습니다. ${SORT_ONLY_OVER}개보다 많아 문서 종류만 나눠 보여 줍니다.` : '아직 분류하지 않았습니다. 분류하면 아래 등록 순서에 맞춰 넣습니다.'}</p></div>
      <div className="actions"><button type="button" className="btn" disabled={sorting} onClick={() => setStaged([])}>비우기</button>
        <button type="button" className="btn primary cta" disabled={sorting} onClick={() => void classify()}>{sorting ? '분류 중…' : `${staged.length}개 분류하기`}<Icon name="play" /></button></div></header>
      <div className="body"><div className="chips">{staged.slice(0, 14).map((f) => <span key={f.name} className="chip static">{f.name}</span>)}{staged.length > 14 && <span className="chip static">외 {staged.length - 14}개</span>}</div></div></section>}
    {message && <Notice tone={message.tone}>{message.text}</Notice>}
    {items.length > 0 && <section className="panel"><header><div><h2>분류 결과</h2><p>{sorted < items.length ? `분류 중 ${sorted} / ${items.length}` : `파일 ${items.length}개를 분류해 아래 등록 순서에 넣었습니다.`}</p></div>
      <button type="button" className="btn sm" disabled={busyAny} onClick={() => { setItems([]); setMessage(null); }}>결과 비우기</button></header>
      <div className="body"><div className="tally">{kindCounts.map(([k, n]) => <div key={k} className={`count${k === UNKNOWN ? ' warn' : ''}`}><strong className="num">{n}<small>개</small></strong><span>{k}</span></div>)}</div></div></section>}
    {done === SLOTS.length && <Notice tone="ok"><Icon name="check" /><span><b>자료가 모두 준비됐습니다.</b> 이제 수요를 예측할 수 있습니다. <button type="button" className="btn sm" onClick={() => go('forecast')}>수요 예측으로<Icon name="arrow" /></button></span></Notice>}

    <section className="kpis" aria-label="자료 현황">
      <Kpi label="승인된 자료" value={`${done} / ${SLOTS.length}`} unit="개" note={done === SLOTS.length ? '모두 준비됨' : `${SLOTS.length - done}개 남음`} tone={done === SLOTS.length ? 'ok' : 'warn'} viz={<Ring size={52} stroke={7} value={(done / SLOTS.length) * 100} tone={done === SLOTS.length ? undefined : 'warn'} />} />
      <Kpi label="다음에 넣을 자료" value={nextRow ? nextRow.slot.label : '없음'} note={nextRow ? (nextRow.item ? `${nextRow.item.file.name} 대기 중` : '파일을 놓으세요') : '모두 승인됨'} />
      <Kpi label="지금 올린 파일" value={`${items.length + staged.length}`} unit="개" note={staged.length ? `${staged.length}개 분류 전` : items.length ? `순서에 맞춘 것 ${items.filter((i) => i.slot).length}개` : '아직 없음'} />
      <Kpi label="손봐야 하는 것" value={`${stuck.length + loose.length + orphans.length}`} unit="건" note={stuck[0] ? stuck[0].slot.label : loose[0] ? `${loose[0].file.name} 유형 미정` : orphans[0] ? `${orphans[0].file.name} 정리 필요` : '없음'} tone={stuck.length + loose.length + orphans.length ? 'warn' : 'ok'} />
    </section>

    {docs && <section className="panel"><header><div><h2>문서 종류 분류 결과</h2><p>파일 {docs.total}개를 종류별로 나눴습니다. 보기만 하는 기능이고 등록되지 않습니다.</p></div>
      <div className="actions">{docs.busy ? <St tone="info">분류 중 {docs.results.length} / {docs.total}</St> : <St tone="ok">{docs.results.length}개 완료</St>}<button type="button" className="btn sm" onClick={() => setDocs(null)}>닫기</button></div></header>
      <div className="body">
        <div className="distbar" role="img" aria-label={docCounts.map(([c, n]) => `${c} ${n}개`).join(', ')}>{docCounts.map(([c, n]) => <i key={c} style={{ width: `${(n / (docs.results.length || 1)) * 100}%`, background: DOC_COLOR[c] }} title={`${c} ${n}개`} />)}</div>
        <div className="tally">{docCounts.map(([c, n]) => <button key={c} type="button" className={`count${c === '미분류' || c === '확인 필요' ? ' warn' : ''}`} aria-pressed={docs.filter === c} title="누르면 이 종류만 봅니다" onClick={() => setDocs({ ...docs, filter: docs.filter === c ? null : c })}>
          <strong className="num">{n}<small>개</small></strong><span><i style={{ background: DOC_COLOR[c] }} />{c}</span></button>)}</div>
        <div className="tablewrap scrollbox" style={{ maxHeight: 320 }}><table className="tbl"><thead><tr><th>파일</th><th>분류</th><th>확신</th><th>근거</th></tr></thead>
          <tbody>{docs.results.filter((r) => !docs.filter || r.category === docs.filter).map((r) => <tr key={r.file}><td className="nw">{r.file}</td><td className="nw"><b>{r.category}</b></td><td className="nw">{r.confidence}</td><td className="small muted">{r.reason}</td></tr>)}</tbody></table></div>
      </div></section>}

    <div className="cols c21">
      <section className="panel"><header><div><h2>등록 순서</h2><p>위에서부터 차례로 승인합니다. 제품과 자재가 먼저입니다.</p></div>
        <div className="actions">{(pending.length > 0 || running) && <button type="button" className="btn primary lg" disabled={busyAny} onClick={() => void runAll()}><Icon name="check" />{running ? '진행 중…' : `문제없는 ${pending.length}개 모두 승인`}</button>}</div></header>
        <div className="body" style={{ paddingBottom: 6 }}><div className="steps" role="group" aria-label="등록 진행">{rows.map(({ slot, item, batch: b }) => <button type="button" key={slot.key} title={slot.label} className={`${b?.status === 'APPROVED' ? 'done' : item?.error || b?.status === 'MAPPING_HOLD' || b?.status === 'HAS_ERRORS' ? 'stuck' : item || b ? 'wait' : ''}${slot.key === current?.slot.key ? ' on' : ''}`} onClick={() => void open(slot.key)}><i /><span>{slot.label}</span></button>)}</div></div>
        <div className="body flush"><div className="tablewrap"><table className="tbl"><thead><tr><th className="c">순서</th><th>자료</th><th>파일</th><th>상태</th><th>할 수 있는 일</th></tr></thead>
          <tbody>{rows.map(({ slot, item, batch: b }, i) => <tr key={slot.key} className={`clickable${slot.key === current?.slot.key ? ' selected' : ''}`} onClick={() => void open(slot.key)}>
            <td className="c num muted">{i + 1}</td>
            <td><span className="name"><b>{slot.label}</b><span className="code">{slot.tech}</span></span></td>
            <td>{item ? <span className="name"><b>{item.file.name}</b><span className="code">{num(item.file.size / 1024, 0)} KB · {item.manual ? '직접 고름' : '자동 인식'}</span></span> : b ? <span className="name"><b>{b.file.name}</b><span className="code">이전에 등록함</span></span> : <span className="faint">파일을 놓으세요</span>}</td>
            <td className="nw">{item?.error ? <St tone="bad">문제 있음</St> : item?.busy ? <St tone="info">처리 중</St> : b ? <BatchSt status={b.status} /> : item ? <St>등록 전</St> : <St>없음</St>}</td>
            <td onClick={(e) => e.stopPropagation()}><div className="actions">
              {item && (!b || b.status === 'REJECTED') && <button type="button" className="btn sm" disabled={item.busy || running || !noteOk} onClick={() => void register(item).then(finish)}>등록</button>}
              {b?.status === 'READY_FOR_APPROVAL' && <button type="button" className="btn primary sm" disabled={busyAny || !actorOk} onClick={() => void approve(item, b).then(finish)}>승인</button>}
              {b?.status === 'APPROVED' && <span className="small muted">{when(b.approved_at)}</span>}
              {(b?.status === 'MAPPING_HOLD' || b?.status === 'HAS_ERRORS') && <button type="button" className="btn sm" onClick={() => void open(slot.key)}>확인하기</button>}
            </div></td></tr>)}</tbody></table></div>
          {loose.length > 0 && <div className="alerts">{loose.map((item) => <div className="alert warn" key={item.id}><i /><div><b>{item.file.name}</b><br /><span>{item.error || item.note || '유형을 정하지 못했습니다.'}</span></div>
            <select className="select" aria-label={`${item.file.name}의 자료 종류`} value="" onChange={(e) => patch(item.id, { slot: e.target.value, manual: true, error: '', batch: match(server, item.file.name, slotOf(e.target.value)?.entity) })}>
              <option value="">자료 종류 고르기</option>{SLOTS.filter((s) => !rows.find((r) => r.slot.key === s.key)?.item).map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</select></div>)}</div>}
          {orphans.length > 0 && <div className="alerts">{orphans.map((b) => <div className="alert warn" key={b.batch_id}><i /><div><b>{b.file.name}</b> <span>· {ENTITY_NAME[b.entity]}로 올라가 있지만 양식이 맞지 않습니다</span></div>
            <button type="button" className="btn danger sm" disabled={!actorOk} onClick={() => { if (!reason.trim()) setReason('잘못 올린 파일'); void apiClient.rejectBatch(b.batch_id, actor, reason.trim() || '잘못 올린 파일').then(() => { setMessage({ tone: 'ok', text: `${b.file.name}을 반려했습니다.` }); return finish(); }).catch((e) => setMessage({ tone: 'bad', text: failure(e) })); }}>반려</button></div>)}</div>}
        </div>
      </section>

      <div className="stack">
        <section className="panel"><header><div><h2>{current.slot.label}</h2><p>{current.item?.file.name ?? batch?.file.name ?? '아직 파일이 없습니다'}</p></div>{batch && <BatchSt status={batch.status} />}</header>
          <div className="body">
            {!current.item && !batch && <Empty>{current.slot.label} 파일을 위 영역에 놓으세요. 다른 파일과 함께 넣어도 알아서 이 줄에 넣습니다.</Empty>}
            {current.item?.note && <p className="small"><b style={{ color: 'var(--ink-2)' }}>{current.item.manual ? '직접 고른 자료입니다. ' : '이렇게 판단했습니다: '}</b>{current.item.note}</p>}
            {current.item?.error && <Notice tone="bad">{current.item.error}</Notice>}
            {detail?.validation && <dl className="kv">
              <dt>읽은 행</dt><dd className="num">{num(detail.validation.sheets.reduce((a, s) => a + s.records_total, 0))}</dd>
              <dt>문제없는 행</dt><dd className="num">{num(detail.validation.sheets.reduce((a, s) => a + s.valid_records, 0))}</dd>
              <dt>오류 · 경고</dt><dd className="num" style={detail.validation.blocking_error_count ? { color: 'var(--bad)' } : undefined}>{detail.validation.blocking_error_count} · {detail.validation.warning_count}</dd>
              {detail.approved_at && <><dt>승인</dt><dd>{when(detail.approved_at)} · {detail.approved_by}</dd></>}</dl>}
            {holds.length > 0 && <><h3>열을 지정해야 합니다</h3>
              {holds.slice(0, 8).map((hold, i) => <label className="field" key={`${hold.field}-${i}`}>{hold.message}
                {hold.field ? <input list={`cand-${i}`} value={overrides[hold.field] ?? ''} onChange={(e) => setOverrides({ ...overrides, [hold.field]: e.target.value })} placeholder="원본의 열 이름 또는 열 문자 (예: B)" /> : null}
                <datalist id={`cand-${i}`}>{hold.candidates.map((c) => <option key={c} value={c} />)}</datalist></label>)}
              {holds.some((h) => h.field) ? <div className="actions"><button type="button" className="btn sm" onClick={() => void revalidate(current.item, batch!)}>다시 검증</button></div>
                : <Notice tone="warn">이 자료의 양식과 열 이름이 맞지 않습니다. 다른 종류의 파일을 올렸다면 반려하고 맞는 줄에 다시 넣으세요.</Notice>}</>}
            {issues.length > 0 && <div className="tablewrap scrollbox" style={{ maxHeight: 200 }}><table className="tbl"><thead><tr><th>위치</th><th>문제</th></tr></thead>
              <tbody>{issues.slice(0, 30).map((issue, i) => <tr key={i}><td className="small num nw">{issue.location?.cell_ref ?? (issue.location?.row ? `${issue.location.row}행` : '-')}</td><td className="small"><Tag tone={issue.severity === 'ERROR' ? 'bad' : 'warn'}>{issue.severity === 'ERROR' ? '오류' : '경고'}</Tag> {issue.message}</td></tr>)}</tbody></table></div>}
            <div className="actions">
              {current.item && (!batch || batch.status === 'REJECTED') && <button type="button" className="btn" disabled={current.item.busy || !noteOk} onClick={() => void register(current.item!).then(finish)}>등록</button>}
              {batch?.status === 'READY_FOR_APPROVAL' && <button type="button" className="btn primary" disabled={busyAny || !actorOk} onClick={() => void approve(current.item, batch).then(finish)}><Icon name="check" />승인</button>}
              {current.item && batch?.status !== 'APPROVED' && <button type="button" className="btn" onClick={() => patch(current.item!.id, { slot: null, manual: true, batch: null })}>다른 종류로 옮기기</button>}
            </div>
            {batch && batch.status !== 'APPROVED' && batch.status !== 'REJECTED' && <div className="formrow">
              <label className="field">반려 사유<input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="예: 잘못된 파일" /></label>
              <button type="button" className="btn danger" disabled={!actorOk} onClick={() => void reject(current.item, batch)}>반려</button></div>}
          </div>
        </section>
        <section className="panel"><header><div><h2>등록할 때 남기는 정보</h2><p>승인 기록에 함께 저장됩니다</p></div></header>
          <div className="body"><div className="formrow">
            <label className="field">자료 출처<select value={source} onChange={(e) => setSource(e.target.value)}><option value="SYNTHETIC">합성 데이터</option><option value="CLIENT_UPLOAD">기업 업로드</option><option value="PUBLIC_DEMAND">공개 수요 데이터</option></select></label>
            <label className="field">담당자 코드<input value={actor} onChange={(e) => setActor(e.target.value)} aria-invalid={!actorOk} placeholder="planner01" /></label></div>
            <label className="field">출처 설명<input value={note} onChange={(e) => setNote(e.target.value)} aria-invalid={!noteOk} placeholder="예: 2026년 12월 말 ERP 내려받기" /></label>
            {!actorOk && <p className="small" style={{ color: 'var(--bad)' }}>담당자 코드는 영문·숫자로 2자 이상이어야 승인할 수 있습니다.</p>}</div>
        </section>
      </div>
    </div>
  </>;
}
