# Module integration · draft 0.2

> 2026-11-18: `POST /planning-inputs/preview`가 기존 `PlanCommand`와 dataset scope의 단일 월 승인 입력을 진단한다. 계획 계산·저장과 별도로 사용하며 기존 엔진 게이트와 정책 미확인 상태를 유지한다. [진단 계약·B03 합의 명세](PLANNING_INPUT_DIAGNOSTICS_VERIFICATION.md) · [11/17 기존 개발 PC의 0009 적용 기록](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md)

> 2026-11-16: 업로드 분류기 AVAILABLE=True/rules-0.2.0으로 두 분류 API는 실제 추천 또는 HOLD를 반환한다. 비활성/미구현만 501이며 기존 아래 미구현 설명은 초기 기록이다. [분류·매핑·이력 연계](INGESTION_INTEGRATION_HISTORY.md)는 기존 DTO·승인 gate를 재사용한다. 신규 0009는 이번 PC에서 PostgreSQL 미적용이다. 별도 문서 분류/임베딩 도구는 API에 연결하지 않았다.

> **입력 보조 확장 (2026-11-15):** [ingestion-assistance-0.1](AI_MAPPING_INTEGRATION_DESIGN.md)은 backend 소유의 profile/컬럼 후보/합성 판매 변환 preview 계약이다. [DTO](../contracts/interfaces/ingestion.py)를 사용하며 분류·계획 모듈 계약을 교체하지 않는다. DB migration·AI 호출·자동 승인·frontend 변경은 없다. 분류 entity는 이훤 담당 연결점을 유지하고, 정상 업로드·검증·승인은 기존 batch 경로를 거친다.

> **데이터셋 격리 확장:** [DATASET_ISOLATION](DATASET_ISOLATION.md)을 따른다. API의 dataset_id query는 요청 저장소·예측·계획·What-if·출력 전체를 같은 소속으로 제한한다. 기존 생략 호출은 TISSUE-LEGACY만 사용한다. PlanningInput/PlanCommand는 dataset_id를 포함하며 엔진 알고리즘은 변경하지 않았다. 기존 예측 input_digest는 엔진 계약을 보존하고 별도 dataset_input_digest와 실행 소유권으로 데이터셋을 식별한다. 신규 migration은 0008이다.

> **2026-11-15 계획 영구 저장 확장:** [계획 실행 계약](PLAN_EXECUTION_PERSISTENCE.md)의 별도 `/plan-executions`를 추가했다. 기존 `/plans*`는 읽기 전용 Preview를 유지한다. What-if provider는 저장된 실제 입력/부모 결과를 읽지만 계산 모듈 미구현 501은 유지한다. 저장·계보·검토/반려·승인 조건부 XLSX 기반은 구현됐으며 정식 승인은 인증/정책 미연결로 비활성이다. 아래 PLAN_HISTORY_NOT_IMPLEMENTED와 ‘계획 저장소 없음’ 설명은 초기 기록으로 대체된다. 0001~0006을 보존하고 신규 0007만 추가했다.

> **2026-11-15 등록 확장:** CAPA/Routing은 더 이상 미등록 전용 경로가 아니다. `POST /batches`의 capacity/routing 승인 자료를 0006 테이블에 저장하고 `/capacity`, `/routings`로 조회한다. SQL provider는 실제 승인 자료가 있으면 capacity_snapshot/routing_snapshot과 출처 목록을 채운다. 아래 ‘null 스냅샷’ 설명은 해당 자료가 없는 경우에 적용된다. RoutingStep의 기존 필드는 유지하고 `resource_requirements`에 같은 공정의 추가 동시 자원 소요를 보존한다. [데이터 사전](CAPACITY_ROUTING_DATA_DICTIONARY.md)을 따른다. 새 마이그레이션은 0006이며 0001~0005는 보존했다. 분류기의 추천 entity와 엔진 알고리즘은 변경하지 않았다. 계획·What-if의 501과 미확정 정책 표시는 유지한다.

이 문서는 실행 가능한 연결 **경계**다. 분류/계획 알고리즘은 미구현이며, 계획 저장·승인이 구현됐다는 뜻이 아니다. 기존 데이터 계약·승인 gate·0001~0005는 바꾸지 않았다. 세부 담당 파일·독립 명령은 [TEAM_HANDOFF](TEAM_HANDOFF.md)를 따른다.

## 실제 API 유지

기존 `/health`, `/ingest/preview`, `/batches*`, `/products`, `/materials`, `/boms`, `/inventory`, `/demand/monthly`, `/dev/forecasts`, `/forecasts*`, `/exports/plans/xlsx`를 유지한다. 개발용 합성 JSON 예측은 정식 승인 수요 예측과 별도다. OpenAPI는 contracts/openapi.json, 기존 JSON Schema는 contracts/ 루트다.

## 파일 분류

`POST /classifications`: 기존 JSON 경로 유지. ClassificationInput → ClassificationOutput. 파일명·SHA256·format(csv/xlsx/null)·시트별 컬럼과 허용된 샘플을 전달한다. 최대 20시트, 시트당 100컬럼/20행, 셀 500자. CSV의 시트명은 null이며 가짜 Excel 시트명을 만들지 않는다. 경로·제어문자는 파일명에서 거부한다. 제한 초과는 422이고 열/시트를 조용히 누락하지 않는다.

`POST /classifications/file`: multipart file + sample_row_limit(0~20, 기본 0). 기존 CSV/XLSX 파서를 재사용해 같은 DTO를 만들고 같은 어댑터를 호출한다. UI는 사용자 선택 시에만 최대 5행을 허용한다. 파일을 배치/DB에 저장하지 않는다. 원본 10MiB 제한·기존 파일 오류도 유지한다. 개인정보 제거와 샘플 허용 범위 확인은 호출자 책임이다.

출력은 recommended_entity, candidates[{entity,score,reasons}], hold, reasons, module_version. 점수는 확률 보장을 의미하지 않는다. 추천이 없으면 HOLD. 분류 결과는 추천일 뿐 기존 승인 gate를 통과시키지 않는다. 현재 구현은 **501 MODULE_NOT_IMPLEMENTED**, 런타임/응답 계약 실패는 **500 MODULE_ERROR**이고 원문·예외 문자열은 노출하지 않는다. 수동 파일 유형 선택은 계속 가능하다.

이훤의 연결점: `file_classifier.classify(ClassificationInput) -> ClassificationOutput`. 실제 알고리즘·불명확성 임계값·정확도 검증은 담당자가 제공한다. 자기 모듈의 AVAILABLE=True는 기능 메타데이터에 반영된다. 함수/계약을 유지하면 backend 구조 변경 없이 두 API가 연결된다. HOLD에는 이유가 필요하며 점수 임계값은 통합 담당이 임의로 정하지 않았다. backend는 DB를 분류기에 넘기지 않는다.

## 계획

`POST /plans`: PlanCommand, `POST /plans/what-if`: 같은 명령 DTO를 받되 WHAT_IF는 기존 계획 실행 ID가 필요하다. UUID forecast_execution_id, 제품 코드 목록, 기준일·대상 월, 명시적 시나리오를 받는다. 원시 예측 rows를 클라이언트가 덮어쓰는 API는 아니다.

현재 모듈의 AVAILABLE=False이므로 두 경로는 **501 MODULE_NOT_IMPLEMENTED**다. 이희원이 자기 모듈에서 AVAILABLE=True와 run을 구현하면 동일 API가 읽기 전용 어댑터를 통해 호출한다. 성공 응답은 **PlanningReply**이며 persisted=false, approval_available=false다. 읽기 전용 결과를 계획 실행 ID나 승인 이력으로 위장하지 않는다. 저장·정식 승인·정식 출력 API는 아직 없다.

이희원의 연결점: `engine.planning.run(PlanningInput) -> PlanningOutput`. 명령 본문은 기존 planning-integration-0.1-draft를 유지하고 내부 입출력은 **planning-handoff-0.2-draft**, HTTP envelope는 **planning-preview-0.2-draft**로 구체화했다. DTO는 contracts/interfaces/planning.py, 기존 modules.py import는 재수출로 유지한다.

기본 SqlPlanningSourceProvider는 REPEATABLE READ + READ ONLY 연결에서 실제 forecast UUID·지문·결과와 승인된 제품·자재·BOM·재고·출처 버전을 읽는다. 선택 제품/월이 예측에 없거나 실패 예측이면 409 PLAN_INPUT_UNAVAILABLE이며 0 수요로 보충하지 않는다. 기준일 이후 재고는 제외하고 대상 월과 겹치는 활성 BOM 후보·재고 이력은 보존한다. 최신 재고/BOM의 선택·월중 버전 변경 규칙을 임의 확정하지 않는다.

승인 CAPA·라우팅 저장 경로가 아직 없으므로 기본 provider는 null 스냅샷과 CAPACITY_NOT_REGISTERED/ROUTING_NOT_REGISTERED/POLICY_NOT_CONFIRMED를 전달한다. 없는 데이터로 FEASIBLE을 주장하면 출력 오류다. CAPA DTO를 client의 승인 선언으로 받아들이지 않는다. 추가 승인 경로가 구현되면 김대영이 provider를 채우고 엔진은 같은 입력 계약을 사용한다. 새 SQL provider는 이번 비DB 시험에서 orchestration/test double로 검증했으며 실제 PostgreSQL 재검증은 별도 승인 후 필요하다.

What-if는 WHAT_IF 명령과 저장된 base_plan_execution_id가 필요하다. 기본 provider는 아직 계획 저장소가 없어 501 PLAN_HISTORY_NOT_IMPLEMENTED다. 향후 provider가 반환한 기준 계획의 execution_id/forecast_execution_id가 명령과 일치해야 엔진에 전달한다. 주입 provider 시험으로 호출·원본 분리·실패 계약을 확인하지만 실제 계획 저장 완료를 의미하지 않는다.

출력은 2~3개 PlanCandidate, 제품/월/단위/수량 ProductionRow, 독립 자원 ConstraintEvaluation, MaterialRequirement, 근거·경고·미확인·오류 PlanningIssue로 타입을 정의했다. 실패 결과에는 후보가 없고, INPUT_INVALID/FAILED는 오류 이유가 필요하다. 중복 후보/생산 행/평가 참조, 요청 범위 밖 결과, 승인 단위 변경을 거부한다. 엔진의 업무 판정을 재계산하거나 새로운 HARD/SOFT 집계식을 만들지는 않는다.

OK/PARTIAL은 200, INPUT_INVALID/UNSUPPORTED는 422, FAILED는 500이며 모듈 예외/계약 위반은 안전한 500 MODULE_ERROR다. 이력 부족·필수 자료 결측을 성공한 승인 계획처럼 표시하지 않는다. 원문/예외/비밀을 로그·응답에 넣지 않는다. 입력 전체 스냅샷을 hash한 input_digest와 실제 forecast UUID를 서버가 응답에 바인딩한다.

FEASIBLE/UNVERIFIED/INFEASIBLE, HARD/SOFT 결합, 목적함수·KPI·비용·결측·예외 승인은 [CAPA 초안](multi_capacity_contract_draft.md)과 [질문](multi_capacity_decision_questions.md)에서 미결정이다. PPT 숫자/경고를 구현 규칙으로 승격하지 않는다.

## 스키마·오류·프론트

모델은 contracts/interfaces/modules.py, 생성물은 contracts/schemas/module_interfaces_draft.json이다. `backend/export_contract_schema.py`, `backend/generate_api_examples.py`로 갱신하고 동기화 테스트를 실행한다. 공유 모델 변경은 김대영 검토가 필요하다.

구체 모델은 base.py/capacity.py/planning.py로 나누되 modules.py import 경로를 보존한다. CAPA 등록 DTO·향후 API·검증 구분은 [CAPACITY_REGISTRATION_PLAN](CAPACITY_REGISTRATION_PLAN.md)에 정리했다. 새 entity·DB 테이블·마이그레이션은 추가하지 않았다.

정마나미는 API 클라이언트로 서버 응답을 표시한다. 네트워크·409·422·501·503 시 Fixture로 대체하지 않는다. DEMO는 별도 React 컴포넌트와 명시 배너로 구별하며 승인 기록·정식 출력과 섞지 않는다. 기존 plan-export-0.1-draft는 extra=forbid이므로 신규 CAPA 상세를 덧붙여 보내지 않는다.

계획 화면의 합성 설명 사례와 실제 모듈 연결은 명시적으로 전환한다. 실제 결과는 Zustand 메모리에만 보관하며 새로고침 복원을 위한 서버 저장이 있다고 주장하지 않는다. 데이터 등록/예측의 기존 DB 복원은 유지한다. 분류/계획 성공 fixture는 TEST-DOUBLE-ONLY이며 UI·경계 시험 전용이다.
