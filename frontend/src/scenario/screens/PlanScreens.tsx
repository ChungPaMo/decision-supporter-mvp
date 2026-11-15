import { useEffect, useRef, useState } from 'react';
import { BarChart, LineChart } from '../charts';
import {
  applyWhatIf, ASSUMPTIONS, DATASET, downloadCsv, fmt, PERIOD, Plan, planById, PLANS, PRIORITIES, PRODUCT, PRODUCT_LABEL, PULP_AVAILABLE_KG,
  QUANTILES, RECOMMENDED, UTILIZATION_LIMIT, UTILIZATION_WATCH, WhatIf, WhatIfResult,
} from '../data';
import Icon, { IconName } from '../icons';
import { Card, Caution, Chip, Facts } from '../parts';
import { useScenario } from '../store';

const PERIOD_TEXT = `${PERIOD.from} ~ ${PERIOD.to}`;
const NO_CHANGE: WhatIf = { adjustPct: 0, overtime: 0, priority: 'STANDARD' };
const signed = (value: number) => `${value > 0 ? '+' : ''}${value}`;
const DraftTag = () => <span className="sc-draft-tag">화면 시안 · 계획 계산 마무리</span>;

function PlanCards({ rows, name }: { rows: (plan: Plan) => Array<{ icon: IconName; label: string; value: string }>; name: string }) {
  const { planId, selectPlan } = useScenario();
  return <div className="sc-plan-cards" role="radiogroup" aria-label={name}>{PLANS.map((plan) => <label key={plan.id} className={`sc-plan-card${plan.id === planId ? ' selected' : ''}`}>
    <input type="radio" name={name} checked={plan.id === planId} onChange={() => selectPlan(plan.id)} />
    <span className="sc-plan-head"><strong><i style={{ background: plan.color }} />{plan.name}</strong>{plan.id === RECOMMENDED && <Chip tone="solid">추천</Chip>}</span>
    <small>{plan.description}</small>
    <dl>{rows(plan).map((row) => <div key={row.label}><dt><Icon name={row.icon} size={15} />{row.label}</dt><dd>{row.value}</dd></div>)}</dl>
  </label>)}</div>;
}

/* 07. 생산계획 추천안 비교 */
const TABS = ['요약', '수요', '생산능력', '자재', '제약조건'] as const;
const METRICS: Array<{ icon: IconName; label: string; value: (plan: Plan) => string }> = [
  { icon: 'bars', label: '생산량', value: (p) => `${fmt(p.production)} 팩` },
  { icon: 'gear', label: '설비 가동률', value: (p) => `${p.utilization} %` },
  { icon: 'box', label: '여유 재고 (기간 말)', value: (p) => `${fmt(p.spareStock)} 팩` },
  { icon: 'clock', label: '잔업 시간 (평균/월)', value: (p) => `${p.overtime} 시간` },
];

function exportComparison() {
  downloadCsv(`생산계획_추천안비교_${DATASET}_시안.csv`, [
    ['구분', ...PLANS.map((plan) => plan.name)],
    ...METRICS.map((metric) => [metric.label, ...PLANS.map((plan) => metric.value(plan))]),
    ['총 자재 소요량', ...PLANS.map((plan) => `${fmt(plan.materialKg)} kg`)],
    ['자재 부족 여부', ...PLANS.map((plan) => (plan.materialOk ? '문제 없음' : '일부 자재 주의'))],
    ['비고', '합성 데이터 기반 UX 시안 — 계획 엔진 계산 결과 아님', '', ''],
  ]);
}

function Evidence({ plan }: { plan: Plan }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>('요약');
  return <Card title="계획 근거 상세" className="sc-evidence">
    <div className="sc-tabs" role="tablist" aria-label="계획 근거">{TABS.map((item) => <button key={item} type="button" role="tab" aria-selected={tab === item} onClick={() => setTab(item)}>{item}</button>)}</div>
    <div role="tabpanel" aria-label={tab} className="sc-stack tight">
      {tab === '요약' && <>
        <div className="sc-subcard"><h4><Icon name="file" size={16} />계획 요약</h4><ul className="sc-bullets">
          <li>제품: {PRODUCT_LABEL}</li><li>계획 기간: {PERIOD_TEXT} (3개월)</li><li>추천 기준: 수요 충족, 설비 효율, 자재 가용성, 운영 비용</li></ul></div>
        <div className="sc-subcard"><h4><Icon name="scale" size={16} />{plan.id === RECOMMENDED ? '추천 사유' : '검토 포인트'} ({plan.name})</h4>
          <ul className="sc-ticks boxed">{plan.reasons.map((reason) => <li key={reason}><Icon name="checkCircle" size={16} />{reason}</li>)}</ul></div>
        <div className="sc-subcard"><h4><Icon name="gear" size={16} />주요 가정 및 제약조건</h4><ul className="sc-bullets">{ASSUMPTIONS.map((item) => <li key={item}>{item}</li>)}</ul></div>
      </>}
      {tab === '수요' && <><table className="sc-table"><caption>월별 예측 수요 (팩)</caption>
        <thead><tr><th>대상월</th>{QUANTILES.map((q) => <th key={q.key} className="num">{q.short}</th>)}</tr></thead>
        <tbody>{PERIOD.months.map((month, i) => <tr key={month}><td>{month}</td>{QUANTILES.map((q) => <td key={q.key} className="num">{fmt(q.values[i])}</td>)}</tr>)}</tbody></table>
        <p className="sc-muted">{plan.name} 생산량 {fmt(plan.production)} 팩 · P50 합계 대비 수요 충족률 {plan.demandFill} %</p></>}
      {tab === '생산능력' && <><table className="sc-table"><caption>{plan.name} 설비 가동률 (%)</caption>
        <thead><tr><th>대상월</th><th className="num">SAW1</th><th className="num">LB1</th></tr></thead>
        <tbody>{PERIOD.months.map((month, i) => <tr key={month}><td>{month}</td><td className="num">{plan.saw1[i]}</td><td className="num">{plan.lb1[i]}</td></tr>)}</tbody></table>
        <p className="sc-muted">운영 한도 {UTILIZATION_LIMIT} % · {UTILIZATION_WATCH} % 이상은 여유 재검토 대상</p></>}
      {tab === '자재' && <><Facts rows={[
        { icon: 'logo', label: '펄프 소요량', value: `${fmt(plan.materialKg)} kg` },
        { icon: 'box', label: '펄프 가용량', value: `${fmt(PULP_AVAILABLE_KG)} kg` },
        { icon: 'scale', label: '여유', value: `${fmt(PULP_AVAILABLE_KG - plan.materialKg)} kg` },
        { icon: 'checkCircle', label: '부자재', value: plan.materialOk ? '문제 없음' : '포장재 일부 입고 일정 확인 필요' },
      ]} /></>}
      {tab === '제약조건' && <ul className="sc-bullets">{ASSUMPTIONS.map((item) => <li key={item}>{item}</li>)}</ul>}
    </div>
  </Card>;
}

export function PlanCompareScreen() {
  const { go, planId } = useScenario();
  const plan = planById(planId);
  const utilSeries = (key: 'saw1' | 'lb1') => PLANS.map((p) => ({ key: p.id, label: p.name, color: p.color, values: p[key] }));
  return <div className="sc-screen">
    <header className="sc-title with-tag"><div><h2>생산계획 추천안 비교</h2><p>수요·재고·설비 조건을 반영한 복수의 생산계획을 비교하고, 검토할 계획을 선택합니다.</p></div><DraftTag /></header>
    <div className="sc-controls">
      <label><span>계획 기간</span><select aria-label="계획 기간" value={PERIOD_TEXT} onChange={() => undefined}><option>{PERIOD_TEXT}</option></select></label>
      <label><span>제품</span><select aria-label="제품" value={PRODUCT_LABEL} onChange={() => undefined}><option>{PRODUCT_LABEL}</option></select></label>
    </div>
    <div className="sc-grid compare">
      <div className="sc-stack">
        <Card title="추천 시나리오"><PlanCards name="추천 시나리오" rows={(p) => [
          { icon: 'bars', label: '총 생산량', value: `${fmt(p.production)} 팩` },
          { icon: 'gear', label: '설비 가동률', value: `${p.utilization} %` },
          { icon: 'clock', label: '예상 잔업', value: `${p.overtime} 시간/월` },
          { icon: 'logo', label: '총 자재 소요량', value: `${fmt(p.materialKg)} kg` },
        ]} /></Card>
        <div className="sc-grid cols-2 wide-left">
          <Card title="주요 지표 비교"><div className="sc-table-wrap"><table className="sc-table plans">
            <thead><tr><th>구분</th>{PLANS.map((p) => <th key={p.id} className={p.id === planId ? 'picked' : ''}>{p.name}</th>)}</tr></thead>
            <tbody>{METRICS.map((metric) => <tr key={metric.label}><th scope="row"><Icon name={metric.icon} size={15} />{metric.label}</th>
              {PLANS.map((p) => <td key={p.id} className={`num${p.id === planId ? ' picked' : ''}`}>{metric.value(p)}</td>)}</tr>)}
              <tr><th scope="row"><Icon name="logo" size={15} />자재 부족 여부</th>{PLANS.map((p) => <td key={p.id} className={p.id === planId ? 'picked' : ''}>
                {p.materialOk ? <Chip tone="ok" icon="checkCircle">문제 없음</Chip> : <Chip tone="warn" icon="warn">일부 자재 주의</Chip>}</td>)}</tr>
            </tbody></table></div></Card>
          <Card title="주요 자원 가동률 추이">
            <h4 className="sc-chart-title">설비 가동률 (SAW1)</h4>
            <LineChart title="SAW1 설비 가동률" unit="%" labels={PERIOD.months} series={utilSeries('saw1')} yMax={100} yStep={25} height={150} width={460} />
            <h4 className="sc-chart-title">설비 가동률 (LB1)</h4>
            <LineChart title="LB1 설비 가동률" unit="%" labels={PERIOD.months} series={utilSeries('lb1')} yMax={100} yStep={25} height={150} width={460} />
          </Card>
        </div>
      </div>
      <Evidence plan={plan} />
    </div>
    <div className="sc-action-row">
      <Caution compact title="최종 계획은 자동으로 승인되지 않으며, 추천안은 사용자가 검토 후 선택합니다." />
      <button type="button" className="sc-btn" onClick={exportComparison}><Icon name="download" size={16} />비교 결과 내보내기 (CSV)</button>
      <button type="button" className="sc-btn primary" onClick={() => go(8)}><Icon name="checkCircle" size={16} />선택안 검토 ({plan.name})</button>
    </div>
  </div>;
}

/* 08. What-if 및 제약 검토 */
function alerts(result: WhatIfResult, plan: Plan) {
  const list: Array<{ tone: 'bad' | 'warn'; title: string; lines: string[] }> = [];
  if (result.peak.value > UTILIZATION_LIMIT) list.push({ tone: 'bad', title: 'SAW1 가동률 한도 초과', lines: [`${result.peak.month}에 가동률 ${result.peak.value}% (한도 ${UTILIZATION_LIMIT}%)`, '생산량을 줄이거나 잔업 시간을 늘려 재검토 필요'] });
  else if (result.peak.value >= UTILIZATION_WATCH) list.push({ tone: 'warn', title: 'SAW1 일부 구간 가동률 상승', lines: [`${result.peak.month}에 가동률 ${result.peak.value}%로 상승 예상`, '연속 가동에 따른 설비 여유 재검토 필요'] });
  if (result.pulpGap < 0) list.push({ tone: 'warn', title: '원재료 PULP 부족 가능성', lines: [`소요 ${fmt(result.materialKg)} kg 대비 가용 재고 ${fmt(result.pulpGap)} kg`, '조달 일정 조정 또는 대체 공급 검토 필요'] });
  if (!plan.materialOk) list.push({ tone: 'warn', title: '포장재 입고 일정 확인', lines: ['일부 포장재의 입고 예정일이 계획 기간과 겹침'] });
  return list;
}

export function WhatIfScreen() {
  const { go, planId, whatIfDraft: draft, setWhatIfDraft, whatIf, applyDraft, resetWhatIf } = useScenario();
  const applied = whatIf ?? NO_CHANGE;
  const plan = planById(planId);
  const result = applyWhatIf(plan, applied);
  const dirty = draft.adjustPct !== applied.adjustPct || draft.overtime !== applied.overtime || draft.priority !== applied.priority;
  const found = alerts(result, plan);
  return <div className="sc-screen">
    <header className="sc-title with-tag"><div><h2>What-if 및 제약 검토</h2><p>조건을 직접 조정하며 계획 대안을 다시 검토하는 화면입니다. 자동 의사결정이 아니라 검토 보조가 목적입니다.</p></div><DraftTag /></header>
    <div className="sc-grid whatif">
      <Card title="계획 조건 (What-if)" className="sc-whatif-form">
        <div className="sc-slider"><label htmlFor="sc-adjust">생산 수량 조정 <small>(기준 대비)</small></label>
          <div><input id="sc-adjust" type="range" min={-10} max={20} step={1} value={draft.adjustPct} onChange={(e) => setWhatIfDraft({ adjustPct: Number(e.target.value) })} />
            <output htmlFor="sc-adjust">{signed(draft.adjustPct)} %</output></div>
          <small>적용 범위: {PRODUCT.id} 계획 기간 전체</small></div>
        <div className="sc-slider"><label htmlFor="sc-overtime">잔업 시간 추가</label>
          <div><input id="sc-overtime" type="range" min={0} max={2} step={0.5} value={draft.overtime} disabled={draft.priority === 'COST'} onChange={(e) => setWhatIfDraft({ overtime: Number(e.target.value) })} />
            <output htmlFor="sc-overtime">{draft.priority === 'COST' ? '0' : draft.overtime.toFixed(1)} 시간/일</output></div>
          <small>적용 범위: 전체 라인 (SAW1, LB1) · 한도 2 시간/일</small></div>
        <fieldset className="sc-radio-list"><legend>설비 우선순위</legend>{PRIORITIES.map((item) => <label key={item.id}>
          <input type="radio" name="sc-priority" checked={draft.priority === item.id} onChange={() => setWhatIfDraft({ priority: item.id })} />
          <span>{item.label}<small>{item.note}</small></span></label>)}</fieldset>
        {dirty && <p className="sc-inline-note" role="status"><Icon name="info" size={16} />조건이 바뀌었습니다. 다시 계산해야 결과에 반영됩니다.</p>}
        <button type="button" className="sc-btn accent full" disabled={!dirty} onClick={applyDraft}><Icon name="refresh" size={16} />시나리오 다시 계산</button>
        <button type="button" className="sc-link" disabled={!whatIf} onClick={resetWhatIf}>기준 조건으로 되돌리기</button>
      </Card>
      <div className="sc-stack">
        <Card title="시나리오 대안" aside={<span className="sc-muted">적용 조건: 생산 {signed(applied.adjustPct)} % · 잔업 {applyWhatIf(plan, applied).overtime} 시간/일</span>}>
          <PlanCards name="시나리오 대안" rows={(p) => { const r = applyWhatIf(p, applied); return [
            { icon: 'calendar', label: '총 생산량', value: `${fmt(r.production)} 팩` },
            { icon: 'bars', label: '평균 가동률', value: `${r.avgUtilization} %` },
            { icon: 'clock', label: '잔업 시간', value: `${r.overtime} 시간/일` },
          ]; }} />
        </Card>
        <div className="sc-grid cols-2">
          <Card title={<>핵심 설비 가동률 <small>(SAW1, LB1 · {plan.name})</small></>}>
            <BarChart title="핵심 설비 가동률" unit="%" labels={PERIOD.months} yMin={0} yMax={120} yStep={20} height={210} limit={{ value: UTILIZATION_LIMIT, label: `한도 ${UTILIZATION_LIMIT}%` }}
              series={[{ key: 'saw1', label: 'SAW1', color: '#1d5fd6', values: result.saw1 }, { key: 'lb1', label: 'LB1', color: '#0f9d6b', values: result.lb1 }]} /></Card>
          <Card title={<>노무 가동률 <small>(전체 · {plan.name})</small></>}>
            <LineChart title="노무 가동률" unit="%" labels={PERIOD.months} yMax={100} yStep={25} height={210} width={420}
              series={[{ key: 'labor', label: '노무 가동률', color: '#1d5fd6', values: result.labor }]} /></Card>
        </div>
      </div>
      <div className="sc-stack">
        <Card title="제약 및 검토 알림">
          {found.length === 0 && <div className="sc-inline-ok" role="status"><Icon name="checkCircle" size={18} />현재 조건에서 확인된 제약 위반이 없습니다.</div>}
          <ul className="sc-alerts">{found.map((item) => <li key={item.title} className={`sc-tone-${item.tone}`}>
            <strong><Icon name="warn" size={18} />{item.title}</strong><ul>{item.lines.map((line) => <li key={line}>{line}</li>)}</ul></li>)}</ul>
        </Card>
        <Card title="근거 및 연계 자료"><ul className="sc-links">
          <li><button type="button" onClick={() => go(5)}><Icon name="file" size={16} />수요예측 결과 ({PRODUCT.id})<Icon name="external" size={15} /></button></li>
          <li><button type="button" onClick={() => go(7)}><Icon name="file" size={16} />설비·자재 기준 (계획 근거 상세)<Icon name="external" size={15} /></button></li>
          <li><button type="button" onClick={() => go(3)}><Icon name="file" size={16} />승인 데이터 snapshot<Icon name="external" size={15} /></button></li>
        </ul></Card>
        <button type="button" className="sc-btn primary full" onClick={() => go(9)}><Icon name="checkCircle" size={16} />선택안 검토 ({plan.name})</button>
      </div>
    </div>
  </div>;
}

/* 09. 최종 선택 구조 */
const STAGES: Array<{ icon: IconName; label: string; screen: number }> = [
  { icon: 'file', label: '파일 입력', screen: 1 }, { icon: 'shield', label: '검증/등록', screen: 3 }, { icon: 'chart', label: '수요예측', screen: 5 },
  { icon: 'logo', label: '추천안 비교', screen: 7 }, { icon: 'sliders', label: 'What-if', screen: 8 }, { icon: 'checkCircle', label: '최종 선택', screen: 9 },
];

export function FinalReviewScreen() {
  const { go, planId, whatIf, reviewedAt, markReviewed } = useScenario();
  const plan = planById(planId);
  const applied = whatIf ?? NO_CHANGE;
  const result = applyWhatIf(plan, applied);
  const found = alerts(result, plan);
  const [confirming, setConfirming] = useState(false);
  const cancel = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (confirming) cancel.current?.focus(); }, [confirming]);
  const close = () => { setConfirming(false); opener.current?.focus(); };
  const rows: Array<{ icon: IconName; label: string; value: (p: Plan) => string }> = [
    { icon: 'bars', label: '예상 생산량', value: (p) => `${fmt(p.production)} 팩` },
    { icon: 'target', label: '수요 충족률', value: (p) => `${p.demandFill} %` },
    { icon: 'gear', label: '설비 가동률', value: (p) => `${p.utilization} %` },
    { icon: 'box', label: '여유 재고 (기간 말)', value: (p) => `${fmt(p.spareStock)} 팩` },
    { icon: 'clock', label: '잔업 시간(평균)', value: (p) => `${p.overtime} 시간/월` },
  ];
  return <div className="sc-screen">
    <header className="sc-title"><h2>최종 계획 검토 (MPS 후보 선정)</h2><p>추천 시나리오와 비교 결과, 제약 검토 및 주요 지표를 종합하여 최종 생산계획을 선택합니다.</p></header>
    <div className="sc-grid final">
      <Card title="선택된 시나리오 요약" aside={<Chip tone="solid">선택안</Chip>}>
        <div className="sc-picked"><span style={{ color: plan.color }}><Icon name="logo" size={30} /></span>
          <div><strong>{plan.name}{plan.id === RECOMMENDED ? ' (추천)' : ''}</strong><small>{plan.description}</small></div></div>
        <Facts rows={[
          { label: '계획 기간', value: PERIOD_TEXT }, { label: '대상 제품', value: PRODUCT_LABEL },
          { label: '생산 전략', value: plan.strategy }, { label: '핵심 효과', value: plan.effect },
        ]} />
      </Card>
      <Card title="최종 비교 (핵심 지표)"><div className="sc-table-wrap"><table className="sc-table plans">
        <thead><tr><th>지표</th>{PLANS.map((p) => <th key={p.id} className={p.id === planId ? 'picked' : ''}>{p.name}{p.id === planId && <small>(선택안)</small>}</th>)}</tr></thead>
        <tbody>{rows.map((row) => <tr key={row.label}><th scope="row"><Icon name={row.icon} size={15} />{row.label}</th>
          {PLANS.map((p) => <td key={p.id} className={`num${p.id === planId ? ' picked' : ''}`}>{row.value(p)}</td>)}</tr>)}
          <tr><th scope="row"><Icon name="logo" size={15} />주요 제약 충족</th>{PLANS.map((p) => <td key={p.id} className={p.id === planId ? 'picked' : ''}>
            {p.materialOk ? <Chip tone="ok" icon="checkCircle">충족</Chip> : <Chip tone="warn" icon="warn">자재 주의</Chip>}</td>)}</tr>
        </tbody></table></div>
        <p className="sc-muted">표는 조건 조정 전 기준값입니다. What-if 적용 결과는 오른쪽 요약에 표시됩니다.</p></Card>
      <Card title="최종 검토 요약">
        <Facts rows={[
          { icon: 'tag', label: '선택안', value: <Chip tone="info">{plan.name} ({PRODUCT.id})</Chip> },
          { icon: 'sliders', label: 'What-if 조건', value: whatIf ? `생산 ${signed(applied.adjustPct)} % · 잔업 ${result.overtime} 시간/일` : '조정 없음 (기준 조건)' },
          { icon: 'bars', label: '예상 생산량', value: <><b>{fmt(result.production)} 팩</b> (계획 기간 합계)</> },
          { icon: 'gear', label: '설비 가동률', value: `평균 ${result.avgUtilization} % · 최고 ${result.peak.value} % (${result.peak.month})` },
          { icon: 'logo', label: '펄프 소요', value: `${fmt(result.materialKg)} kg (가용 ${fmt(PULP_AVAILABLE_KG)} kg)` },
          { icon: 'warn', label: '주요 제약', value: found.length ? <span className="sc-warn-text">{found.map((item) => item.title).join(' · ')}</span> : `가동률 ≤ ${UTILIZATION_LIMIT} %, 자재 가용 (충족)` },
        ]} />
        <div className="sc-evidence-links"><Icon name="link" size={16} /><span>근거 링크</span>
          <button type="button" className="sc-link" onClick={() => go(5)}>예측 결과 상세</button>
          <button type="button" className="sc-link" onClick={() => go(8)}>제약 검토 결과</button>
          <button type="button" className="sc-link" onClick={() => go(7)}>시나리오 비교</button></div>
      </Card>
    </div>
    {reviewedAt && <div className="sc-inline-ok" role="status"><Icon name="checkCircle" size={18} />{reviewedAt} · 담당자가 {plan.name}을(를) MPS 후보로 검토 완료했습니다. 시안이므로 서버에 저장되거나 승인되지 않습니다.</div>}
    <div className="sc-action-row">
      <Caution compact title="최종 계획은 자동으로 승인되지 않습니다.">제시된 추천안과 근거를 바탕으로 사용자가 최종 선택 후 승인(등록)을 수행합니다.</Caution>
      <button type="button" className="sc-btn" onClick={() => go(7)}><Icon name="file" size={16} />계획 상세 보기</button>
      <button type="button" className="sc-btn primary" ref={opener} disabled={!!reviewedAt} onClick={() => setConfirming(true)}><Icon name="check" size={16} />{reviewedAt ? '검토 완료됨' : '최종 MPS 검토'}</button>
    </div>
    <Card label="전체 흐름"><ol className="sc-stages">{STAGES.map((stage) => <li key={stage.label}>
      <button type="button" className={stage.screen === 9 ? 'active' : ''} onClick={() => go(stage.screen)}><Icon name={stage.icon} size={18} />{stage.label}</button></li>)}</ol>
      <p className="sc-muted">데이터 입력부터 최종 선택까지 하나의 흐름으로 연결되며, 추천안과 근거를 함께 제시해 의사결정을 돕습니다.</p></Card>
    {confirming && <div className="sc-modal" onClick={(e) => { if (e.target === e.currentTarget) close(); }}>
      <section role="dialog" aria-modal="true" aria-labelledby="sc-confirm-title" onKeyDown={(e) => { if (e.key === 'Escape') close(); }}>
        <h3 id="sc-confirm-title">{plan.name}을(를) MPS 후보로 선정할까요?</h3>
        <p>예상 생산량 {fmt(result.production)} 팩 · 평균 가동률 {result.avgUtilization} %{found.length ? ` · 확인 필요 ${found.length}건` : ''}</p>
        {found.length > 0 && <ul className="sc-bullets">{found.map((item) => <li key={item.title}>{item.title}</li>)}</ul>}
        <p className="sc-muted">화면 시안의 검토 완료 표시이며, 정식 승인·등록은 수행되지 않습니다.</p>
        <div className="sc-action-row end"><button type="button" className="sc-btn" ref={cancel} onClick={close}>취소</button>
          <button type="button" className="sc-btn primary" onClick={() => { markReviewed(); close(); }}>검토 완료로 표시</button></div>
      </section></div>}
  </div>;
}
