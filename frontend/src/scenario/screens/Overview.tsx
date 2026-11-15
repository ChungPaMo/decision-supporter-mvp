import { DATASET, PRODUCT_LABEL, SCREENS } from '../data';
import Icon from '../icons';
import { Card, Caution } from '../parts';
import { useScenario } from '../store';

const INPUTS = [`가상 기업: ${DATASET}`, `대상 품목: ${PRODUCT_LABEL}`, '판매 거래 2022~2026년 자료', '제품·BOM·재고·CAPA·Routing 활용'];
const QUESTIONS = ['원본 파일을 어떤 컬럼으로 해석할까?', '앞으로 3개월간 수요는 어느 범위일까?', '어떤 생산계획이 자재·설비 제약에 맞을까?', '잔업·생산량을 바꾸면 결과가 어떻게 달라질까?'];
const DESCRIPTIONS = [
  '원본 파일을 업로드하고 데이터 유형을 판별',
  '원본 컬럼을 표준 구조로 연결하고 규칙 기반으로 정제',
  '오류를 검토하고 승인 가능한 데이터만 등록',
  '승인된 월별 수요 데이터를 바탕으로 예측 실행',
  '제품별 수요 추이와 예측 결과를 확인',
  '예측 결과를 해석하고 계획의 입력값으로 활용',
  '수요·재고·설비 조건을 반영한 복수안 비교',
  '조건을 조정하며 계획 대안을 재검토',
  '근거를 확인하고 담당자가 최종 선택',
];

export default function Overview() {
  const go = useScenario((state) => state.go);
  return <div className="sc-screen">
    <header className="sc-title"><h2>예시 시나리오 — 화장지 제조기업</h2>
      <p>2027년 1~3월 운영계획을 세우는 담당자의 화면 흐름입니다. 파일 입력부터 계획 선택까지 9개 화면으로 이어집니다.</p></header>
    <div className="sc-grid cols-2">
      <Card title="상황과 입력 자료"><ul className="sc-bullets">{INPUTS.map((item) => <li key={item}>{item}</li>)}</ul></Card>
      <Card title="사용자가 검토할 질문"><ul className="sc-bullets">{QUESTIONS.map((item) => <li key={item}>{item}</li>)}</ul></Card>
    </div>
    <Card title="9개 화면 흐름">
      <ol className="sc-flow-grid">{SCREENS.map((item, i) => <li key={item.no}>
        <button type="button" onClick={() => go(item.no)}>
          <b>{String(item.no).padStart(2, '0')}</b><strong>{item.title}</strong><span>{DESCRIPTIONS[i]}</span>
        </button></li>)}</ol>
    </Card>
    <div className="sc-action-row">
      <Caution compact title="계획을 대신 확정하지 않습니다.">추천안과 근거는 시스템이 제시하고, 최종 판단은 담당자가 합니다.</Caution>
      <button type="button" className="sc-btn primary" onClick={() => go(1)}>시나리오 시작<Icon name="arrowRight" size={16} /></button>
    </div>
  </div>;
}
