import { LineChart, Series } from '../charts';
import {
  DATASET, fmt, HISTORY, HISTORY_AVG, LAST12_TOTAL, MERGED_FILE, PERIOD, PRODUCT_LABEL, Quantile, quantileAvg, QUANTILES, STOCK_PACKS, YOY_PCT,
} from '../data';
import Icon, { IconName } from '../icons';
import { Card, Caution, Chip, Facts, Kpi } from '../parts';
import { useScenario } from '../store';

const ACTUAL_COLOR = '#334155';
const shortMonth = (label: string) => label.slice(2).replace('-', '.');
const PERIOD_TEXT = `${PERIOD.from} ~ ${PERIOD.to}`;

function Controls({ action, onAction, withQuantiles }: { action: string; onAction: () => void; withQuantiles?: boolean }) {
  const { quantiles, toggleQuantile } = useScenario();
  const none = withQuantiles && !Object.values(quantiles).some(Boolean);
  return <div className="sc-controls">
    <label><span>제품 선택</span><select aria-label="제품 선택" value={PRODUCT_LABEL} onChange={() => undefined}><option>{PRODUCT_LABEL}</option></select></label>
    <label><span>예측 기간</span><select aria-label="예측 기간" value={PERIOD_TEXT} onChange={() => undefined}><option>{PERIOD_TEXT}</option></select></label>
    {withQuantiles && <fieldset><legend>예측 분위수</legend>{QUANTILES.map((q) => <label key={q.key} className="sc-tick">
      <input type="checkbox" checked={quantiles[q.key]} onChange={() => toggleQuantile(q.key)} />{q.short}</label>)}</fieldset>}
    <span className="sc-spacer" />
    {none && <span className="sc-muted" role="status">분위수를 하나 이상 선택하세요.</span>}
    <button type="button" className="sc-btn primary" disabled={none} onClick={onAction}><Icon name="play" size={15} />{action}</button>
  </div>;
}

function ForecastChart({ height, only }: { height?: number; only?: Record<Quantile, boolean> }) {
  const labels = [...HISTORY.map((point) => point.month), ...PERIOD.months];
  const joint = HISTORY.length - 1;
  const series: Series[] = [
    { key: 'actual', label: '실제 수요(과거)', color: ACTUAL_COLOR, values: labels.map((_, i) => (i <= joint ? HISTORY[i].value : null)) },
    ...QUANTILES.filter((q) => !only || only[q.key]).map((q) => ({
      key: q.key, label: q.label, color: q.color, dashed: true,
      values: labels.map((_, i) => (i < joint ? null : i === joint ? HISTORY[joint].value : q.values[i - joint - 1])),
    })),
  ];
  return <LineChart title="수요 추이 및 예측" unit="팩" labels={labels} series={series} yMax={12000} yStep={2000} height={height}
    labelEvery={3} tick={shortMonth} bandFrom={joint} bandLabel="예측 구간" />;
}

function KpiRow() {
  return <div className="sc-grid cols-3">
    <Kpi icon="bars" label="과거 월평균 수요" sub={`(${HISTORY[0].month} ~ ${HISTORY[HISTORY.length - 1].month})`} value={`${fmt(HISTORY_AVG)} 팩`} />
    <Kpi icon="box" tone="ok" label="현재 재고" sub="(가용재고)" value={`${fmt(STOCK_PACKS)} 팩`} />
    <Kpi icon="calendar" label="예측 기간" sub={PERIOD_TEXT} value={`${PERIOD.months.length}개월`} />
  </div>;
}

function Summary({ only }: { only: Record<Quantile, boolean> }) {
  return <ul className="sc-quantiles">{QUANTILES.filter((q) => only[q.key]).map((q) => <li key={q.key}>
    <span><i style={{ background: q.color }} />{q.label}</span><strong>{fmt(quantileAvg(q.key))} 팩</strong></li>)}</ul>;
}

/* 04. 수요예측 개요 */
const FLOW: Array<{ icon: IconName; title: string; detail: string }> = [
  { icon: 'db', title: '승인 데이터 불러오기', detail: '승인된 월별 수요 및 입력 설정을 조회' },
  { icon: 'search', title: '시계열 특징 확인', detail: '수요 추세 · 계절성 · 변동성 점검' },
  { icon: 'bars', title: '예측 시나리오 계산', detail: '선택한 분위수(P50/P80/P90)로 예측 실행' },
  { icon: 'save', title: '결과 저장', detail: '예측 결과를 데이터셋에 저장하고 후속 단계(생산계획)에 활용' },
];

export function ForecastSetupScreen() {
  const { go, runForecast, quantiles, approvedAt } = useScenario();
  const picked = QUANTILES.filter((q) => quantiles[q.key]).map((q) => q.label).join(', ') || '선택 없음';
  const recent = HISTORY.slice(12);
  return <div className="sc-screen">
    <header className="sc-title"><h2>수요예측 설정</h2><p>승인된 월별 수요 데이터를 바탕으로 예측을 실행하는 단계입니다.</p></header>
    <Controls withQuantiles action="예측 실행" onAction={() => { runForecast(); go(5); }} />
    <Card title="예측 실행 준비">
      <div className="sc-grid setup">
        <div className="sc-stack">
          <Facts rows={[
            { icon: 'db', label: '과거 데이터 출처', value: MERGED_FILE.name },
            { icon: 'box', label: '현재 재고', value: <>{fmt(STOCK_PACKS)} 팩 <Chip tone="ok">정상</Chip></> },
            { icon: 'sliders', label: '예측 분위수', value: picked },
            { icon: 'file', label: '승인된 입력 스냅샷', value: approvedAt ? `승인: ${approvedAt}` : `${DATASET}:v1 (화면 3에서 승인 전)` },
          ]} />
          <ul className="sc-ticks">
            <li><Icon name="checkCircle" size={16} />월별 수요 데이터(2022-01 ~ 2026-12) {approvedAt ? '승인됨' : '승인 예정'}</li>
            <li><Icon name="checkCircle" size={16} />분위수 설정(P50/P80/P90) 확인됨</li>
            <li><Icon name="checkCircle" size={16} />제품 기준: {PRODUCT_LABEL.split(' ')[0]} 확인됨</li>
          </ul>
        </div>
        <div className="sc-subcard"><h4>과거 월별 수요 추이 (실수요, 최근 12개월)</h4>
          <LineChart title="과거 월별 수요 추이" unit="팩" labels={recent.map((p) => p.month)} tick={shortMonth}
            series={[{ key: 'actual', label: '실제 수요(과거)', color: ACTUAL_COLOR, values: recent.map((p) => p.value) }]} yMax={12000} yStep={3000} height={210} width={520} labelEvery={2} /></div>
        <div className="sc-stack tight">
          <Kpi icon="bars" label="최근 12개월 실수요" value={`${fmt(LAST12_TOTAL)} 팩`} aside={<Chip tone="ok">▲ +{YOY_PCT}%<small> 전년 대비</small></Chip>} />
          <Kpi icon="box" tone="ok" label="현재 재고" value={`${fmt(STOCK_PACKS)} 팩`} aside={<Chip tone="ok">정상</Chip>} />
          <Kpi icon="calendar" label="예측 기간" value={`${PERIOD_TEXT} (${PERIOD.months.length}개월)`} />
          <Kpi icon="logo" label="원본 데이터 출처" value={MERGED_FILE.name} />
        </div>
      </div>
    </Card>
    <Card title="예측 실행 흐름"><ol className="sc-flow">{FLOW.map((step, i) => <li key={step.title}>
      <span className="sc-step-no">{i + 1}</span><div><strong><Icon name={step.icon} size={18} />{step.title}</strong><small>{step.detail}</small></div></li>)}</ol></Card>
    <Caution compact title="본 화면은 계획 수립을 위한 예측 근거를 제공하며, 계획을 자동으로 결정하지 않습니다." />
  </div>;
}

/* 05. 수요예측 결과 대시보드 */
export function ForecastResultScreen() {
  const { go, quantiles, runForecast, forecastRan } = useScenario();
  return <div className="sc-screen">
    <header className="sc-title"><h2>수요예측 결과</h2><p>제품별 수요 추이와 예측 결과를 범위(P50/P80/P90)로 확인하는 화면입니다.</p></header>
    <Controls action="예측 재실행" onAction={runForecast} />
    {!forecastRan && <div className="sc-inline-note" role="status"><Icon name="info" size={18} />화면 4에서 예측을 실행하지 않아, 시안에 준비된 예시 결과를 표시합니다.</div>}
    <div className="sc-grid result">
      <div className="sc-stack">
        <Card title="수요 추이 및 예측" aside={<span className="sc-muted">수요량 (팩)</span>}><ForecastChart height={270} only={quantiles} /></Card>
        <KpiRow />
      </div>
      <div className="sc-stack">
        <Card title={`예측 요약 (${PERIOD.from} ~ ${PERIOD.to.slice(5)})`} aside={<span className="sc-muted">월평균</span>}><Summary only={quantiles} /></Card>
        <Card title="데이터 출처 및 근거">
          <Facts rows={[
            { icon: 'calendar', label: '학습 대상 기간', value: '2022-01 ~ 2026-12' },
            { icon: 'db', label: '데이터셋', value: DATASET },
            { icon: 'file', label: '관련 데이터', value: '승인된 월별 수요 (판매현황 변환)' },
          ]} />
          <button type="button" className="sc-link" onClick={() => go(6)}>상세 근거 보기<Icon name="arrowRight" size={15} /></button>
        </Card>
      </div>
    </div>
  </div>;
}

/* 06. 예측 근거와 활용 방식 */
const MEANING_ICON: Record<Quantile, IconName> = { p50: 'bars', p80: 'shield', p90: 'logo' };
const MEANING_TONE = { p50: 'info', p80: 'ok', p90: 'violet' } as const;

export function ForecastMeaningScreen() {
  const go = useScenario((state) => state.go);
  const all = { p50: true, p80: true, p90: true };
  return <div className="sc-screen">
    <header className="sc-title"><h2>예측 근거와 활용 방식</h2><p>예측 결과를 해석하고 생산계획 추천의 입력값으로 활용하는 방식입니다.</p></header>
    <div className="sc-grid meaning">
      <div className="sc-stack">
        <Card title="과거 추세 및 수요 예측" aside={<span className="sc-muted">{PRODUCT_LABEL}</span>}><ForecastChart height={230} /></Card>
        <Card title={`예측 요약 (${PERIOD.from} ~ ${PERIOD.to.slice(5)})`} aside={<span className="sc-muted">월평균</span>}><Summary only={all} /></Card>
      </div>
      <ul className="sc-meanings">{QUANTILES.map((q) => <li key={q.key} className="sc-card">
        <div className={`sc-meaning-badge sc-tone-${MEANING_TONE[q.key]}`}><Icon name={MEANING_ICON[q.key]} size={30} /><strong>{q.label.replace(' ', '')}</strong></div>
        <dl><div><dt>의미</dt><dd>{q.meaning}</dd></div><div><dt>활용 시점</dt><dd>{q.usage}</dd></div></dl>
      </li>)}</ul>
    </div>
    <Card title="활용 예시"><ol className="sc-usage">{QUANTILES.map((q) => <li key={q.key}>
      <span className={`sc-pill sc-tone-${MEANING_TONE[q.key]}`}>{q.short}</span><div><strong>{q.plan}</strong><small>{q.planDetail}</small></div></li>)}</ol></Card>
    <div className="sc-grid cols-2">
      <Card title="사용자 판단 지원"><ul className="sc-bullets">
        <li>예측 수치를 그대로 확정하지 않고 비교 기준으로 사용</li>
        <li>예측 근거와 데이터 출처를 함께 확인 후 계획 단계로 이동</li></ul></Card>
      <Caution title="추천안은 시스템이 제시하고, 최종 판단은 사용자" />
    </div>
    <div className="sc-action-row end">
      <button type="button" className="sc-btn" onClick={() => go(5)}><Icon name="arrowLeft" size={16} />예측 결과로</button>
      <button type="button" className="sc-btn primary" onClick={() => go(7)}>생산계획 추천안 비교로<Icon name="chevronRight" size={16} /></button>
    </div>
  </div>;
}
