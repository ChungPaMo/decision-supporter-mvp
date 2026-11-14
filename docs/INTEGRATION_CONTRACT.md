# Module integration · draft 0.1

이 문서는 실행 가능한 연결 **경계**다. 미구현 계산이나 API 저장 완료를 의미하지 않는다. 기존 데이터 계약·승인 gate·0001~0005는 바꾸지 않았다.

## 실제 API 유지

기존 `/health`, `/ingest/preview`, `/batches*`, `/products`, `/materials`, `/boms`, `/inventory`, `/demand/monthly`, `/dev/forecasts`, `/forecasts*`, `/exports/plans/xlsx`를 유지한다. 개발용 합성 JSON 예측은 정식 승인 수요 예측과 별도다. OpenAPI는 contracts/openapi.json, 기존 JSON Schema는 contracts/ 루트다.

## 파일 분류

`POST /classifications`: ClassificationInput → ClassificationOutput. 원본 bytes가 아닌 파일명·SHA256·시트별 컬럼과 명시적으로 허용된 샘플만 전달한다. 최대 20시트, 시트당 100컬럼/20행, 셀 500자. 로컬 절대 경로는 거부한다. 제한 초과는 422이며 자동으로 샘플을 잘라 전송하지 않는다. 개인정보 제거·허용 범위 확인은 호출자 책임이다.

출력은 recommended_entity, candidates[{entity,score,reasons}], hold, reasons, module_version. 점수는 확률 보장을 의미하지 않는다. 추천이 없으면 HOLD. 분류 결과는 추천일 뿐 기존 승인 gate를 통과시키지 않는다. 현재 구현은 **501 MODULE_NOT_IMPLEMENTED**, 런타임/응답 계약 실패는 **500 MODULE_ERROR**이고 원문·예외 문자열은 노출하지 않는다. 수동 파일 유형 선택은 계속 가능하다.

이훤의 연결점: `file_classifier.classify(ClassificationInput) -> ClassificationOutput`. 실제 알고리즘·불명확성 임계값·정확도 검증은 담당자가 제공한다. backend 어댑터는 DB를 분류기에 넘기지 않는다.

## 계획

`POST /plans`: PlanCommand, `POST /plans/what-if`: 같은 명령 DTO를 받되 WHAT_IF는 기존 계획 실행 ID가 필요하다. UUID forecast_execution_id, 제품 코드 목록, 기준일·대상 월, 명시적 시나리오를 받는다. 원시 예측 rows를 클라이언트가 덮어쓰는 API는 아니다.

현재 두 경로 모두 501이다. 엔진의 AVAILABLE만 True로 바꿔도 저장·승인 어댑터를 우회해 결과를 발행하지 않는다. 계획 실행 저장·정식 승인·출력 API는 아직 없으며 담당자 계산을 받으면 통합 담당이 추가한다.

이희원의 연결점: `engine.planning.run(PlanningInput) -> PlanningOutput`. PlanningInput은 서버가 실제 forecast UUID/digest/rows와 승인 제품·BOM·재고·CAPA·라우팅·정책 스냅샷으로 구성할 **미확정 핸드오프 초안**이다. forecast UUID는 수요 입력의 승인 출처를 가리키며 예측 자체의 정식 계획 승인을 뜻하지 않는다.

출력은 plans, constraint_evaluations, material_requirements, evidence, warnings, unverified, errors, module_version. 내부 행은 다중 CAPA 계약 결정 전에는 dict 슬롯이다. 계획안별 생산량·독립 수량/인시/설비시간 평가·원본 버전·공유 자원 기여·제외/누락·시나리오 계보를 보존하는 최종 타입은 신규 버전으로 확정한다. 현재 이 슬롯을 안정된 운영 Schema로 간주하지 않는다.

FEASIBLE/UNVERIFIED/INFEASIBLE, HARD/SOFT 결합, 목적함수·KPI·비용·결측·예외 승인은 [CAPA 초안](multi_capacity_contract_draft.md)과 [질문](multi_capacity_decision_questions.md)에서 미결정이다. PPT 숫자/경고를 구현 규칙으로 승격하지 않는다.

## 스키마·오류·프론트

모델은 contracts/interfaces/modules.py, 생성물은 contracts/schemas/module_interfaces_draft.json이다. `backend/export_contract_schema.py`, `backend/generate_api_examples.py`로 갱신하고 동기화 테스트를 실행한다. 공유 모델 변경은 김대영 검토가 필요하다.

정마나미는 API 클라이언트로 서버 응답을 표시한다. 네트워크·409·422·501·503 시 Fixture로 대체하지 않는다. DEMO는 별도 React 컴포넌트와 명시 배너로 구별하며 승인 기록·정식 출력과 섞지 않는다. 기존 plan-export-0.1-draft는 extra=forbid이므로 신규 CAPA 상세를 덧붙여 보내지 않는다.
