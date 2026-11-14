import { useState } from 'react';
import { Notice, ScreenHeader, errorMessage } from '../components/ui';
import { apiClient } from '../services/api';
import { planResponses } from '../services/fixtures';
import { Step, useProductionStore } from '../store/productionStore';

type Stage = 'plans' | 'diagnosis' | 'mrp' | 'whatif' | 'approval';
const STAGES: Array<[Stage, string]> = [['plans', 'MPS 3안'], ['diagnosis', 'RCCP 능력 검토'], ['mrp', 'MRP 자재 검토'], ['whatif', 'What-if'], ['approval', '최종 MPS']];
// PPT slides 5,10-12: fixed illustrative facts, never computed by a planning engine.
const PLANS = [{ name: '기준형', qty: '9,000', capacity: '검토 필요', material: '롤 5,000개 부족' },
  { name: '안정형', qty: '11,000', capacity: '한도 초과 예시', material: '롤 25,000개 부족 외' },
  { name: '비용절감형', qty: '8,000', capacity: '월 총량 예시', material: '필수 자재 충분 예시' }];

export default function PlanningWorkspace({ stage }: { stage: Stage }) {
  const setStep = useProductionStore(s => s.setStep);
  const [selected, setSelected] = useState(0);
  const [quantity, setQuantity] = useState(8000);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState(false);
  async function requestPlanning() {
    setBusy(true); setError('');
    try {
      const history = await apiClient.forecastHistory(1, 0);
      const execution = history.items[0];
      if (!execution) throw new Error('먼저 승인 수요로 실제 예측을 실행하세요.');
      await apiClient.requestPlan(execution.execution_id);
    } catch (failure) { setError(failure instanceof Error ? failure.message : errorMessage(failure)); }
    finally { setBusy(false); }
  }
  return <div className="screen">
    <ScreenHeader title={STAGES.find(([id]) => id === stage)![1]} description="가상 휴지 제조기업 · TP-10R · 10롤 1팩 · 2027년 1월 · PPT 설명용 합성 사례" />
    <Notice tone="warn">DEMO / UNVERIFIED — 아래 수치는 PPT의 고정 설명값입니다. 실제 예측·계획 계산·승인 기록과 연결되지 않았습니다. PPT 이미지가 아닌 React 표·그래프입니다.</Notice>
    <nav className="workflow-tabs" aria-label="계획 상세 단계">{STAGES.map(([id, label]) => <button key={id} className={stage === id ? 'active' : ''} aria-current={stage === id ? 'page' : undefined} onClick={() => setStep(id as Step)}>{label}</button>)}</nav>
    {error && <div role="alert"><Notice tone="bad">{error}</Notice></div>}
    {stage === 'plans' && <>
      <div className="dashboard-grid"><aside className="panel"><h3>기준 조건 · 설명값</h3><dl className="fact-list"><dt>기초 완제품</dt><dd>2,000팩</dd><dt>목표 안전재고</dt><dd>1,000팩</dd><dt>월 수량 한도</dt><dd>10,500팩</dd><dt>포장 설비</dt><dd>160h + 잔업 20h</dd><dt>작업 인력</dt><dd>170 + 잔업 20인시</dd></dl><p className="muted">목적함수·KPI·동시 적용 방식은 계약 미확정입니다.</p></aside>
      <section className="panel"><h3>MPS 초안 시나리오 비교</h3><div className="table-scroll"><table><caption>PPT 합성 사례 — 계산 결과 아님</caption><thead><tr><th>구분</th>{PLANS.map(p => <th key={p.name}>{p.name}</th>)}</tr></thead><tbody>
        <tr><th>월 생산량</th>{PLANS.map(p => <td key={p.name}>{p.qty}팩</td>)}</tr><tr><th>CAPA 검토</th>{PLANS.map(p => <td key={p.name}>{p.capacity}</td>)}</tr><tr><th>자재 검토</th>{PLANS.map(p => <td key={p.name}>{p.material}</td>)}</tr>
        <tr><th>화면 선택</th>{PLANS.map((p, i) => <td key={p.name}><button aria-pressed={selected === i} onClick={() => setSelected(i)}>{selected === i ? '선택됨' : `${p.name} 선택`}</button></td>)}</tr>
      </tbody></table></div><p>선택한 설명 사례: {PLANS[selected].name}. 이 선택은 서버에 저장되지 않습니다.</p>
      <button className="button primary" disabled={busy} onClick={() => void requestPlanning()}>실제 계획 API 연결 확인</button><p className="muted">최근 서버 예측 ID를 참조해 요청합니다. 계획 모듈은 501로 미구현을 알리며 DEMO로 대체하지 않습니다.</p></section></div>
    </>}
    {stage === 'diagnosis' && <>
      <section className="panel"><h3>자원별 한도 · 고정 입력 예시</h3><div className="resource-grid">{[{ name: '월 생산수량', value: '10,500팩', width: 84 }, { name: '포장 설비', value: '180 설비시간', width: 72 }, { name: '작업 인력', value: '190 인시', width: 76 }].map(r => <article key={r.name} className="resource-card"><h4>{r.name}</h4><strong>{r.value}</strong><div className="capacity-track"><span style={{ width: `${r.width}%` }} /></div><small>장식 막대 · 가동률 미산출</small></article>)}</div></section>
      <section className="panel"><h3>독립 제약과 공유 설비</h3><table><caption>RCCP 입력 확인 — 실제 부하 미산출</caption><thead><tr><th>차원</th><th>소요 기준</th><th>평가 상태</th></tr></thead><tbody><tr><td>수량</td><td>월 10,500팩 한도</td><td>미검증</td></tr><tr><td>포장 설비</td><td>60팩/h, 동일 설비 사용량 합산 필요</td><td>미검증</td></tr><tr><td>인력</td><td>0.018인시/팩</td><td>미검증</td></tr></tbody></table><Notice>시간·설비 제약을 단일 수량으로 환산해 공유 자원의 병목 정보를 버리지 않습니다.</Notice></section>
    </>}
    {stage === 'mrp' && <div className="dashboard-grid"><section className="panel"><h3>BOM 구조 · 설명용</h3><details open><summary>TP-10R · 화장지 10롤 1팩</summary><ul className="bom-tree"><li>휴지 롤 · 10롤/팩</li><li>포장필름 · 1장/팩</li><li>외박스 · 0.1개/팩</li></ul></details><p className="muted">입고예정·리드타임은 합성 사례에 포함되지 않았습니다.</p></section><section className="panel"><h3>자재 가용량</h3><table><caption>고정 입력 예시 — 소요·부족 계산 전</caption><thead><tr><th>자재</th><th>가용량</th><th>계산 상태</th></tr></thead><tbody><tr><td>휴지 롤</td><td>85,000롤</td><td>미구현</td></tr><tr><td>포장필름</td><td>9,500장</td><td>미구현</td></tr><tr><td>외박스</td><td>1,000개</td><td>미구현</td></tr></tbody></table></section></div>}
    {stage === 'whatif' && <section className="panel stack"><h3>생산량 조정 조건 · 미저장</h3><label className="field"><span>월 생산량 후보 (팩)</span><input aria-label="월 생산량 후보" type="range" min={7000} max={12000} step={100} value={quantity} onChange={e => setQuantity(Number(e.target.value))} /></label><output aria-live="polite">{quantity.toLocaleString()}팩</output><button className="button primary" disabled>재검증 — 기준 계획 실행 미구현</button><Notice>슬라이더는 입력 후보만 변경합니다. 부하·자재·실행 가능성 결과를 새로 계산한 것처럼 표시하지 않습니다.</Notice></section>}
    {stage === 'approval' && <section className="panel stack"><h3>최종 MPS 선택·승인</h3><Notice tone="warn">서버 계획 실행·정식 승인·감사 이력이 없어 승인할 수 없습니다. UNVERIFIED 예외 승인도 아직 업무 결정 전입니다.</Notice><button className="button primary" disabled>최종 MPS 승인 (미구현)</button><button className="button" onClick={() => setDialog(true)}>기존 DEMO Excel 출력 안내</button></section>}
    {dialog && <div className="modal-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="export-title" className="panel stack"><h3 id="export-title">기존 출력 계약 확인</h3><p>휴지 계획의 정식 출력이 아닙니다. 기존 독립 Fixture를 DEMO/UNVERIFIED Excel로 변환합니다. 승인·검증 증거가 아닙니다.</p><button className="button primary" onClick={() => void apiClient.downloadPlanXlsx(planResponses.BASE.export).catch(failure => { setError(errorMessage(failure)); setDialog(false); })}>기존 Fixture DEMO Excel 다운로드</button><button autoFocus className="button" onClick={() => setDialog(false)}>닫기</button></section></div>}
  </div>;
}
