import { useRef, useState } from 'react';
import {
  CLASSIFICATION_EVIDENCE, DATASET, downloadCsv, fmt, ISSUES, LINEAGE, MAPPING, MERGED_FILE, PASSED_CHECKS, RAW_PREVIEW, RowKind, Severity,
  SNAPSHOT, TRANSFORM_PREVIEW, TRANSFORM_RULES, TRANSFORM_SUMMARY, UPLOAD_FILES, VALIDATION_SUMMARY, VALIDATION_TOTAL,
} from '../data';
import Icon, { IconName } from '../icons';
import { Card, Caution, Chip, Facts, Stepper, Tone } from '../parts';
import { useScenario } from '../store';

const KIND_TONE: Record<RowKind, Tone> = { 정상: 'ok', 취소: 'bad', 반품: 'violet' };

function RawPreview() {
  return <div className="sc-table-wrap"><table className="sc-table">
    <thead><tr><th>주문일자</th><th>제품코드</th><th className="num">수량</th><th>구분</th></tr></thead>
    <tbody>{RAW_PREVIEW.map((row) => <tr key={row.date}><td>{row.date}</td><td>{row.product}</td><td className="num">{row.qty}</td>
      <td><Chip tone={KIND_TONE[row.kind]}>{row.kind}</Chip></td></tr>)}</tbody>
  </table></div>;
}

/* 01. 파일 업로드 및 분류 */
export function UploadScreen() {
  const go = useScenario((state) => state.go);
  const [detail, setDetail] = useState(false);
  const [added, setAdded] = useState<Array<{ name: string; size: string }>>([]);
  const picker = useRef<HTMLInputElement>(null);
  const addFiles = (list: FileList | null) => setAdded((current) => [...current, ...Array.from(list ?? []).map((file) => ({ name: file.name, size: `${(file.size / 1024 / 1024).toFixed(1)} MB` }))]);
  return <div className="sc-screen">
    <header className="sc-title"><h2>파일 업로드 및 분류</h2><p>원본 파일을 업로드하고 데이터 유형을 판별하는 첫 단계입니다.</p></header>
    <Stepper steps={['파일 선택', '파일 유형 판정', '변환 규칙 확인', '승인 및 등록']} current={2} />
    <div className="sc-grid upload">
      <Card title={<>업로드 파일 <small>({UPLOAD_FILES.length + added.length}개)</small></>}
        aside={<><button type="button" className="sc-btn small outline" onClick={() => picker.current?.click()}><Icon name="plus" size={14} />파일 추가</button>
          <input ref={picker} type="file" accept=".csv,.xlsx" multiple hidden aria-label="추가할 파일" onChange={(event) => { addFiles(event.target.files); event.target.value = ''; }} /></>}>
        <ul className="sc-files">{UPLOAD_FILES.map((file) => <li key={file.name}>
          <span className="sc-file-icon">CSV</span><div><strong>{file.name}</strong><small>{fmt(file.rows)}행 · {file.size}</small></div></li>)}
          {added.map((file, i) => <li key={`${file.name}-${i}`}><span className="sc-file-icon pending">NEW</span><div><strong>{file.name}</strong><small>{file.size} · 유형 판정 전 (시안에서는 서버로 전송하지 않음)</small></div></li>)}</ul>
      </Card>
      <div className="sc-stack">
        <Card className="sc-verdict" label="파일 유형 판정 결과">
          <div className="sc-verdict-file"><span className="sc-file-icon big"><Icon name="file" size={22} /></span>
            <div><strong>{MERGED_FILE.name}</strong><small>총 {fmt(MERGED_FILE.rows)}행 · {MERGED_FILE.size} ({UPLOAD_FILES.length}개 파일 병합)</small></div></div>
          <dl className="sc-verdict-facts">
            <div><dt>파일 유형</dt><dd><Chip tone="ok" icon="db">판매 거래 데이터</Chip></dd></div>
            <div><dt>변환 대상</dt><dd><Chip tone="info" icon="bars">월별 수요</Chip></dd></div>
            <div><dt>분류 신뢰도</dt><dd><Chip tone="ok" icon="checkCircle">높음</Chip></dd></div>
          </dl>
        </Card>
        <div className="sc-grid preview-note">
          <Card title={<>원본 데이터 미리보기 <small>(일부, 5행)</small></>} aside={<span className="sc-muted">전체 {fmt(MERGED_FILE.rows)}행</span>}><RawPreview /></Card>
          <Caution title="자동 승인되지 않습니다.">파일 유형 및 분류 결과를 확인한 후 사용자가 직접 내용을 확인하고 승인해야 등록이 완료됩니다.</Caution>
        </div>
        {detail && <Card title="분류 근거" label="분류 결과 상세">
          <Facts rows={CLASSIFICATION_EVIDENCE.map((item) => ({ label: item.label, value: item.detail }))} />
        </Card>}
      </div>
    </div>
    <div className="sc-action-row">
      <button type="button" className="sc-btn" onClick={() => go(0)}><Icon name="arrowLeft" size={16} />이전 단계</button>
      <span className="sc-spacer" />
      <button type="button" className="sc-btn" aria-expanded={detail} onClick={() => setDetail(!detail)}><Icon name="eye" size={16} />{detail ? '분류 근거 접기' : '분류 결과 상세보기'}</button>
      <button type="button" className="sc-btn primary" onClick={() => go(2)}>확인 후 다음 단계로<Icon name="chevronRight" size={16} /></button>
    </div>
  </div>;
}

/* 02. 컬럼 매핑·정제·변환 */
const RULE_ICON: IconName[] = ['checkCircle', 'ban', 'refresh', 'calendar', 'box'];

export function MappingScreen() {
  const { go, mapping, setMapping, mappingReviewed, setMappingReviewed } = useScenario();
  const [editing, setEditing] = useState(false);
  const [ranAt, setRanAt] = useState(0);
  const includeReturns = mapping['구분'] === '상태 필터 (정상 + 반품 차감)';
  const unmapped = MAPPING.filter((row) => mapping[row.source] === '매핑 안 함').map((row) => row.source);
  const s = TRANSFORM_SUMMARY;
  return <div className="sc-screen">
    <header className="sc-title"><h2>파일 업로드 및 변환</h2><p>원본 컬럼을 표준 구조로 연결하고 규칙 기반으로 정제하는 단계입니다.</p></header>
    <Stepper steps={['파일 선택', '컬럼 매핑 및 변환', '결과 확인', '승인 및 등록']} current={2} />
    <Card className="sc-verdict" label="분석 대상 파일">
      <div className="sc-verdict-file"><span className="sc-file-icon">CSV</span>
        <div><strong>{MERGED_FILE.name}</strong><small>{fmt(MERGED_FILE.rows)}행 · {MERGED_FILE.size} · CSV</small></div></div>
      <dl className="sc-verdict-facts">
        <div><dt>파일 유형(예상)</dt><dd><Chip tone="ok" icon="db">판매 거래 데이터</Chip></dd></div>
        <div><dt>분석 상태</dt><dd><Chip tone="ok" icon="checkCircle">분석 완료</Chip></dd></div>
      </dl>
    </Card>
    <div className="sc-grid mapping-row">
      <Card title="원본 데이터 미리보기" aside={<span className="sc-muted">상위 5행 (전체 {fmt(MERGED_FILE.rows)}행)</span>}><RawPreview /></Card>
      <Card title="컬럼 매핑 추천" aside={<Chip tone="info">자동 추천 (3건)</Chip>}>
        <div className="sc-table-wrap"><table className="sc-table mapping">
          <thead><tr><th>원본 컬럼</th><th>매핑 대상(표준 필드)</th><th>매핑 상태</th></tr></thead>
          <tbody>{MAPPING.map((row) => {
            const changed = mapping[row.source] !== row.recommended;
            const hold = row.needsReview && !mappingReviewed;
            return <tr key={row.source}><th scope="row">{row.source}</th>
              <td><select aria-label={`${row.source} 매핑 대상`} value={mapping[row.source]} disabled={!editing && !row.needsReview}
                onChange={(event) => setMapping(row.source, event.target.value)}>{row.options.map((option) => <option key={option}>{option}</option>)}</select></td>
              <td>{hold ? <Chip tone="warn" icon="info">검토 필요</Chip> : changed || row.needsReview ? <Chip tone="info" icon="user">사용자 확인</Chip> : <Chip tone="ok" icon="checkCircle">추천</Chip>}</td>
            </tr>;
          })}</tbody>
        </table></div>
        <label className="sc-check"><input type="checkbox" checked={mappingReviewed} onChange={(event) => setMappingReviewed(event.target.checked)} />
          <span><strong>‘구분’ 컬럼 처리 방식을 확인했습니다.</strong><small>의미가 모호한 컬럼은 HOLD 상태로 두며, 확인 전에는 다음 단계로 넘어가지 않습니다.</small></span></label>
      </Card>
      <Card title="변환 미리보기 (월별 수요)" aside={<span className="sc-muted">{ranAt ? `다시 실행 ${ranAt}회` : '규칙 기반'}</span>}>
        <div className="sc-table-wrap"><table className="sc-table">
          <thead><tr><th>product_id</th><th>period</th><th className="num">demand_qty</th><th>unit</th></tr></thead>
          <tbody>{TRANSFORM_PREVIEW.map((row) => <tr key={row.period}><td>{row.product_id}</td><td>{row.period}</td>
            <td className="num">{fmt(row.demand_qty - (includeReturns ? Math.round(row.demand_qty * 0.016) : 0))}</td><td>{row.unit}</td></tr>)}</tbody>
        </table></div>
        <p className="sc-muted">{includeReturns ? '반품 수량을 차감한 값입니다.' : '정상 거래만 월 단위로 합산한 값입니다.'}</p>
      </Card>
    </div>
    <div className="sc-grid cols-2 wide-right">
      <Card title="변환 규칙"><ul className="sc-chips">{TRANSFORM_RULES.map((rule, i) => <li key={rule.label}>
        <Chip tone={rule.tone} icon={RULE_ICON[i]}>{i === 2 && includeReturns ? '반품 차감' : rule.label}</Chip></li>)}</ul>
        <p className="sc-muted">AI는 매핑 후보만 추천하고, 실제 변환은 재현 가능한 규칙으로 수행합니다.</p></Card>
      <Card title="변환 요약"><dl className="sc-tally">
        <div><dt>원본 행수</dt><dd>{fmt(s.source)}</dd></div>
        <div className="sc-tone-ok"><dt>정상 (포함)</dt><dd>{fmt(s.normal)}</dd></div>
        <div className="sc-tone-bad"><dt>취소 제외</dt><dd>{fmt(s.cancelled)}</dd></div>
        <div className="sc-tone-violet"><dt>{includeReturns ? '반품 차감' : '반품 별도'}</dt><dd>{fmt(s.returned)}</dd></div>
        <div className="sc-tone-info total"><dt>최종 결과 (변환 후)</dt><dd>{fmt(s.result)}행</dd></div>
      </dl></Card>
    </div>
    {unmapped.length > 0 && <div className="sc-inline-alert" role="alert"><Icon name="warn" size={18} />필수 컬럼({unmapped.join(', ')})이 매핑되지 않아 변환할 수 없습니다.</div>}
    <div className="sc-action-row">
      <Caution compact title="사용자 확인이 필요합니다. 자동으로 승인하거나 DB에 등록되지 않습니다." />
      <button type="button" className="sc-btn" aria-pressed={editing} onClick={() => setEditing(!editing)}><Icon name="edit" size={16} />{editing ? '매핑 수정 완료' : '매핑 수정'}</button>
      <button type="button" className="sc-btn" onClick={() => setRanAt(ranAt + 1)}><Icon name="refresh" size={16} />변환 미리보기 다시 실행</button>
      <button type="button" className="sc-btn primary" disabled={!mappingReviewed || unmapped.length > 0} onClick={() => go(3)}>확인 후 결과 확인<Icon name="chevronRight" size={16} /></button>
    </div>
  </div>;
}

/* 03. 검증·승인·등록 */
const SEVERITY: Record<Severity, { tone: Tone; icon: IconName }> = { 치명: { tone: 'bad', icon: 'warn' }, 경고: { tone: 'warn', icon: 'warn' }, 정보: { tone: 'info', icon: 'info' } };
const SUMMARY_ICON: IconName[] = ['warn', 'file', 'link', 'box', 'checkCircle'];
const LINEAGE_ICON: IconName[] = ['file', 'gear', 'checkCircle', 'logo'];

const downloadReport = () => downloadCsv(`검증보고서_${DATASET}_시안.csv`, [
  ['No', '심각도', '행 번호', '필드', '이슈 내용', '권장 조치'],
  ...ISSUES.map((issue, n) => [n + 1, issue.severity, issue.row, issue.field, issue.message, issue.action]),
]);

export function ValidationScreen() {
  const { go, approvedAt, approve } = useScenario();
  const flagged = VALIDATION_TOTAL - VALIDATION_SUMMARY[4].rows;
  return <div className="sc-screen">
    <header className="sc-title"><h2>검증·승인·등록</h2><p>오류를 검토하고 승인 가능한 데이터만 등록하는 단계입니다.</p></header>
    <Stepper steps={['파일 선택', '매핑·변환 완료', '검증 결과', '승인 및 등록']} current={approvedAt ? 4 : 3} />
    <div className="sc-grid verify">
      <div className="sc-stack">
        <Card title="검증 결과 요약">
          <ul className="sc-summary">{VALIDATION_SUMMARY.map((item, i) => <li key={item.key} className={`sc-tone-${item.tone}`}>
            <span><Icon name={SUMMARY_ICON[i]} size={18} />{item.label}</span><strong>{item.rows}<small>행</small></strong>
            <em>({(item.rows / VALIDATION_TOTAL * 100).toFixed(1)}%)</em></li>)}</ul>
        </Card>
        <Card title={<>발견된 이슈 <small>(상위 5건)</small></>}>
          <div className="sc-table-wrap"><table className="sc-table">
            <thead><tr><th>No.</th><th>심각도</th><th className="num">행 번호</th><th>필드(컬럼)</th><th>이슈 내용</th><th>권장 조치</th></tr></thead>
            <tbody>{ISSUES.map((issue, i) => <tr key={issue.row}><td>{i + 1}</td>
              <td><Chip tone={SEVERITY[issue.severity].tone} icon={SEVERITY[issue.severity].icon}>{issue.severity}</Chip></td>
              <td className="num">{issue.row}</td><td><code>{issue.field}</code></td><td>{issue.message}</td><td>{issue.action}</td></tr>)}</tbody>
          </table></div>
        </Card>
        <Card title="검증 통과 항목"><ul className="sc-passed">{PASSED_CHECKS.map((item) => <li key={item.title}>
          <span className="sc-tone-ok"><Icon name="check" size={16} /></span><div><strong>{item.title}</strong><small>{item.detail}</small></div></li>)}</ul></Card>
        <Card title="데이터 추적(계보)"><ol className="sc-lineage">{LINEAGE.map((item, i) => <li key={item.title}>
          <Icon name={LINEAGE_ICON[i]} size={20} /><div><strong>{item.title}</strong>{item.lines.map((line) => <small key={line}>{i === 3 && approvedAt ? line.replace('승인 후 생성', approvedAt) : line}</small>)}</div></li>)}</ol></Card>
      </div>
      <div className="sc-stack">
        <Card title="승인 및 등록">
          <Facts rows={[
            { icon: 'db', label: '데이터셋', value: DATASET },
            { icon: 'logo', label: '엔티티', value: <code>{SNAPSHOT.entity}</code> },
            { icon: 'tag', label: 'snapshot digest', value: <code>{SNAPSHOT.snapshotDigest}</code> },
            { icon: 'file', label: '원본 SHA-256', value: <code>{SNAPSHOT.sourceSha}</code> },
            { icon: 'shield', label: '정책 digest', value: <code>{SNAPSHOT.policyDigest}</code> },
          ]} />
        </Card>
        <Caution title="승인 후 등록 · 자동 등록 없음">검증을 통과한 데이터만 승인 후 등록됩니다. 승인 전까지는 데이터셋에 반영되지 않습니다.</Caution>
        <Card title={approvedAt ? '등록 이력' : '등록 이력(예정)'}>
          <Facts rows={[
            { icon: 'db', label: '등록 대상', value: <><b>{VALIDATION_TOTAL}행</b> (승인 가능 {VALIDATION_SUMMARY[4].rows}행 + 보정 반영 {flagged}행)</> },
            { icon: 'user', label: '작성자', value: SNAPSHOT.author },
            { icon: 'checkCircle', label: '검토 상태', value: approvedAt ? <Chip tone="ok" icon="checkCircle">승인됨</Chip> : <Chip tone="warn" icon="clock">승인 대기</Chip> },
            { icon: 'calendar', label: '등록 시점', value: approvedAt ?? '- (승인 후 생성)' },
          ]} />
        </Card>
        {approvedAt && <div className="sc-inline-ok" role="status"><Icon name="checkCircle" size={18} />승인되어 등록 snapshot({DATASET}:v1)이 생성된 것으로 표시합니다. 시안이므로 서버에는 저장되지 않습니다.</div>}
        <div className="sc-action-row end">
          <button type="button" className="sc-btn" onClick={downloadReport}><Icon name="download" size={16} />검증 보고서 다운로드</button>
          {approvedAt
            ? <button type="button" className="sc-btn primary" onClick={() => go(4)}>수요예측으로 이동<Icon name="chevronRight" size={16} /></button>
            : <button type="button" className="sc-btn primary" onClick={approve}><Icon name="checkCircle" size={16} />승인 후 등록</button>}
        </div>
      </div>
    </div>
  </div>;
}
