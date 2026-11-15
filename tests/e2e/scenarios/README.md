# 데이터셋 브라우저 E2E — 실행 보류

현재 frontend에는 데이터셋 선택 UI가 없다. dataset-selection.scenario.ts는 후속 수용 시나리오 함수이며 `.spec.ts`로 자동 등록하지 않았다. 기존 테스트를 skip으로 바꾸거나 브라우저 검증을 통과한 것으로 보고하지 않는다.

정마나미 담당 후속: 접근성 이름 ‘데이터셋’ combobox, 수요예측/실행·계획 버튼, forecast-results / forecast-execution-select 표시 계약을 협의한다. 이 이름은 제안이며 실제 UI에 존재한다고 주장하지 않는다.

준비된 8단계: 데이터셋 목록 → CP 선택 → 9제품 → 예측 실행/결과 → CAPA/Routing → 미구현 계획 501 안내 → Legacy 전환 → 이전 데이터셋 UUID/화면 상태 비재사용.

실행 재개 시 승인된 회귀 DB용 API와 독립 포트를 사용한다. 개발 DB를 향한 업로드/예측 생성/초기화는 금지한다. 새 함수는 TypeScript 정적 검사만 수행하며 UI 연동·실행은 보류한다.
