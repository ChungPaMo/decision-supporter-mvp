import { useEffect, useRef, useState } from 'react';
import { Notice, ScreenHeader, errorMessage } from '../components/ui';
import { apiClient } from '../services/api';
import { planResponses } from '../services/fixtures';
import { Step, useProductionStore } from '../store/productionStore';
import LivePlanningPanel from '../components/LivePlanningPanel';
import PlanExecutionPanel from '../components/PlanExecutionPanel';
import UsageMeter from '../components/UsageMeter';
import { DEMO_PLANS, DEMO_RESOURCES, DEMO_MATERIALS } from '../services/planningDemo';

type Stage = 'plans' | 'diagnosis' | 'mrp' | 'whatif' | 'approval';
const STAGES: Array<[Stage, string]> = [['plans', 'MPS 3안'], ['diagnosis', 'RCCP 능력 검토'], ['mrp', 'MRP 자재 검토'], ['whatif', 'What-if'], ['approval', '최종 MPS']];
// PPT slides 5,10-12: fixed illustrative facts, never computed by a planning engine.
const PLANS = DEMO_PLANS;

export default function PlanningWorkspace({ stage }: { stage: Stage }) {
  const setStep = useProductionStore(s => s.setStep);
  const { demoPlanIndex: selected, setDemoPlanIndex: setSelected, planningView, setPlanningView } = useProductionStore();
  const opener = useRef<HTMLButtonElement | null>(null);
  const [quantity, setQuantity] = useState(8000);
  const [error, setError] = useState('');
  const [overtime, setOvertime] = useState(false);
  const [dialog, setDialog] = useState(false);
  useEffect(() => { if (!dialog) opener.current?.focus(); }, [dialog]);
  return <div className="screen">
    <ScreenHeader title={STAGES.find(([id]) => id === stage)![1]} description={planningView === 'DEMO' ? '가상 휴지 제조기업 · TP-10R · 10롤 1팩 · 2027년 1월 · PPT 설명용 합성 사례' : '저장된 예측 실행을 선택해 서버 계산 모듈을 호출합니다. 읽기 전용 결과이며 저장·승인되지 않습니다.'} />
    <div className="workflow-tabs" aria-label="계획 데이터 모드"><button aria-pressed={planningView === 'DEMO'} onClick={() => setPlanningView('DEMO')}>합성 설명 사례</button><button aria-pressed={planningView === 'LIVE'} onClick={() => setPlanningView('LIVE')}>실제 모듈 연결</button></div>
    {planningView === 'DEMO' && <Notice tone="warn">DEMO / UNVERIFIED — 고정 합성 설명값입니다. 실제 예측·계산·승인 기록과 연결되지 않았습니다. 화면의 비율은 이 설명값을 시각화합니다.</Notice>}
    <nav className="workflow-tabs" aria-label="계획 상세 단계">{STAGES.map(([id, label]) => <button key={id} className={stage === id ? 'active' : ''} aria-current={stage === id ? 'page' : undefined} onClick={() => setStep(id as Step)}>{label}</button>)}</nav>
    {error && <div role="alert"><Notice tone="bad">{error}</Notice></div>}
    {planningView === 'LIVE' ? <><LivePlanningPanel stage={stage} /><PlanExecutionPanel /></> : <>
    {stage === 'plans' && <>
      <div className="dashboard-grid"><aside className="panel"><h3>기준 조건 · 설명값</h3><dl className="fact-list"><dt>기초 완제품</dt><dd>2,000팩</dd><dt>목표 안전재고</dt><dd>1,000팩</dd><dt>월 수량 한도</dt><dd>10,500팩</dd><dt>포장 설비</dt><dd>160h + 잔업 20h</dd><dt>작업 인력</dt><dd>170 + 잔업 20인시</dd></dl><p className="muted">목적함수·KPI·동시 적용 방식은 계약 미확정입니다.</p></aside>
      <section className="panel"><h3>MPS 초안 시나리오 비교</h3><div className="table-scroll"><table><caption>PPT 합성 사례 — 계산 결과 아님</caption><thead><tr><th>구분</th>{PLANS.map(p => <th key={p.name}>{p.name}</th>)}</tr></thead><tbody>
        <tr><th>월 생산량</th>{PLANS.map(p => <td key={p.name}>{p.qty}팩</td>)}</tr><tr><th>CAPA 검토</th>{PLANS.map(p => <td key={p.name}>{p.capacity}</td>)}</tr><tr><th>자재 검토</th>{PLANS.map(p => <td key={p.name}>{p.material}</td>)}</tr>
        <tr><th>설명 수요 기준</th>{PLANS.map(p => <td key={p.name}>{p.basis}</td>)}</tr><tr><th>기말 재고 설명값</th>{PLANS.map(p => <td key={p.name}>{p.stock}</td>)}</tr>
        <tr><th>화면 선택</th>{PLANS.map((p, i) => <td key={p.name}><button aria-pressed={selected === i} onClick={() => setSelected(i)}>{selected === i ? '선택됨' : `${p.name} 선택`}</button></td>)}</tr>
      </tbody></table></div><p>선택한 설명 사례: {PLANS[selected].name}. 이 선택은 서버에 저장되지 않습니다.</p>
      <p className="muted">정식 목적함수·KPI·추천 순위는 미확정입니다. 실제 모듈 연결 탭에서 서버 응답을 별도로 확인합니다.</p></section></div>
    </>}
    {stage === 'diagnosis' && <>
      <section className="panel"><h3>{PLANS[selected].name} · 합성 자원 사용량</h3><p>개별 수량·설비시간·인시를 각각 보존한 설명값입니다. 상세 일정과 공유 자원 배분은 미검증입니다.</p><div className="resource-grid">{DEMO_RESOURCES.map((r, i) => <UsageMeter key={r.resource} label={`${r.label} · ${r.resource}`} used={PLANS[selected].usage[i]} limit={r.limit} unit={r.unit} status={selected === 1 ? '합성 한도 초과 사례 · 미검증' : '합성 설명값 · 미검증'} />)}</div></section>
      <Notice tone="warn">공유 설비 M1의 제품별 기여·셋업·대체 설비·일별 동시성은 계산 모듈과 정책 확정 후 검증합니다. 그래프만으로 실행 가능 판정을 내리지 않습니다.</Notice>
      <section className="panel"><table><caption>RCCP 제약 상세 · 합성 설명값</caption><thead><tr><th>자원</th><th>소요</th><th>한도</th><th>상태</th></tr></thead><tbody>{DEMO_RESOURCES.map((r, i) => <tr key={r.resource}><td>{r.resource} · {r.label}</td><td>{PLANS[selected].usage[i]} {r.unit}</td><td>{r.limit} {r.unit}</td><td>미검증</td></tr>)}</tbody></table></section>
    </>}
    {stage === 'mrp' && <div className="dashboard-grid"><section className="panel"><h3>BOM 구조 · 설명용</h3><details open><summary>TP-10R · 화장지 10롤 1팩</summary><ul className="bom-tree">{DEMO_MATERIALS.map(m => <li key={m.id}>{m.name} · {m.coefficient}</li>)}</ul></details><p className="muted">입고예정·리드타임은 합성 사례에 포함되지 않았습니다.</p></section><section className="panel"><h3>{PLANS[selected].name} · 합성 자재 검토</h3><div className="table-scroll"><table><caption>수기 설명값 · 실제 MRP 계산 결과 아님</caption><thead><tr><th>자재</th><th>소요</th><th>가용</th><th>부족</th></tr></thead><tbody>{DEMO_MATERIALS.map((m, i) => <tr key={m.id}><td>{m.name}</td><td>{PLANS[selected].required[i]}</td><td>{m.available}</td><td className={Number(PLANS[selected].shortage[i]) > 0 ? 'shortage-cell' : ''}>{PLANS[selected].shortage[i]} EA</td></tr>)}</tbody></table></div><Notice tone={selected === 2 ? 'info' : 'warn'}>{PLANS[selected].material} · 이 사례의 조달·납기는 미검증입니다.</Notice></section></div>}
    {stage === 'whatif' && <section className="panel stack"><h3>생산량 조정 조건 · 미저장</h3><label className="field"><span>월 생산량 후보 (팩)</span><input aria-label="월 생산량 후보" type="range" min={7000} max={12000} step={100} value={quantity} onChange={e => setQuantity(Number(e.target.value))} /></label><output aria-live="polite">{quantity.toLocaleString()}팩</output><label><input type="checkbox" checked={overtime} onChange={e => setOvertime(e.target.checked)} /> 잔업 검토 요청 (미적용 조건)</label><p>변경 후보: {quantity.toLocaleString()}팩 · 잔업 검토 {overtime ? '요청' : '미요청'} · 재계산 전</p><button className="button primary" disabled>재검증 — 기준 계획 실행 미구현</button><Notice>슬라이더는 입력 후보만 변경합니다. 부하·자재·실행 가능성 결과를 새로 계산한 것처럼 표시하지 않습니다.</Notice></section>}
    {stage === 'approval' && <section className="panel stack"><h3>최종 MPS 선택·승인</h3><dl className="fact-list"><dt>화면 검토 대상</dt><dd>{PLANS[selected].name}</dd><dt>합성 생산수량</dt><dd>{PLANS[selected].qty}팩</dd><dt>기말 재고 설명값</dt><dd>{PLANS[selected].stock}</dd></dl><Notice tone="warn">서버 계획 실행·정식 승인·감사 이력이 없어 승인할 수 없습니다. UNVERIFIED 예외 승인도 아직 업무 결정 전입니다.</Notice><button className="button primary" disabled>최종 MPS 승인 (미구현)</button><button className="button" onClick={e => { opener.current = e.currentTarget; setDialog(true); }}>기존 DEMO Excel 출력 안내</button></section>}
    </>}
    {dialog && <div className="modal-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="export-title" className="panel stack" onKeyDown={e => {
      if (e.key === 'Escape') { setDialog(false); return; }
      if (e.key === 'Tab') { const buttons = e.currentTarget.querySelectorAll<HTMLButtonElement>('button'); const first = buttons[0]; const last = buttons[buttons.length - 1]; if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); } }
    }}><h3 id="export-title">기존 출력 계약 확인</h3><p>휴지 계획의 정식 출력이 아닙니다. 기존 독립 Fixture를 DEMO/UNVERIFIED Excel로 변환합니다. 승인·검증 증거가 아닙니다.</p><button className="button primary" onClick={() => void apiClient.downloadPlanXlsx(planResponses.BASE.export).catch(failure => { setError(errorMessage(failure)); setDialog(false); })}>기존 Fixture DEMO Excel 다운로드</button><button autoFocus className="button" onClick={() => setDialog(false)}>닫기</button></section></div>}
  </div>;
}
