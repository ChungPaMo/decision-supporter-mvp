# 생산계획 엔진 현황 및 백엔드 통합 준비

확인일: **2026-11-17 (KST)**. 조사 기준은 fetch/pull 후 일치한 main [`77067f128ea0531f24855584f9ccfa41f2b84d3b`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/77067f128ea0531f24855584f9ccfa41f2b84d3b)다. 아래 구현 판단은 이 코드 기준이며, 제안·변경 요청은 아직 구현하거나 합의하지 않았다.

**결론:** 실제 승인 자료와 저장된 예측 UUID로 **단일 월 PlanningInput을 조립할 수 있다.** 그러나 `engine.planning.run`은 `AVAILABLE=False`/`NotImplementedError`이고 MPS/RCCP/MRP/What-if 계산은 미구현이다. 실행 저장·계보·검토·출력 기반을 다시 만들 필요는 없다. 먼저 기간·예정 입고·What-if·판정 계약을 맞추고, 기존 입력 서비스의 진단·검증과 화면 인계를 독립적으로 준비해야 한다.

이번 변경은 이 보고서와 PROJECT_PROGRESS/DEVELOPMENT_CHANGELOG뿐이다. 알고리즘·프론트엔드·공식 생성기/정답·서비스 코드·migration은 수정하지 않았다. 개발 DB는 강제 읽기 전용으로만 조회했고 새 계획이나 승인 기록을 만들지 않았다.

## 1. 계획 엔진 구현 상태

아래 상태는 구성요소별로 구분한다. DTO 테스트 통과나 손계산 문서 존재를 계산 구현 완료로 해석하지 않는다.

| 항목·구성요소 | 분류 | 실제 근거·한계 |
| --- | --- | --- |
| 예측 P50/P80/P90 입력·직렬화 | **구현 및 실행 검증 완료** | `ForecastFact` 분위수 순서 검사, 저장 예측 UUID→월별 9행 입력 조립을 실제 PostgreSQL 읽기로 확인. 예측 계산 자체는 기존 완료 기능이며 이번에 재학습하지 않음 |
| MPS 후보 생성 알고리즘 | **미구현** | `engine/planning.py:run`이 예외를 발생시킴. `mps/__init__.py`는 설명문만 존재 |
| RCCP 설비·인력·수량/시간 계산 | **미구현** | `rccp/__init__.py`에 계산 함수 없음. 승인 자원·한도·공정 DTO는 별도 구현됨 |
| MRP BOM 전개·재고/부족량 계산 | **미구현** | `mrp/__init__.py`에 계산 함수 없음. BOM·재고 전달 가능성과 계산 성공은 별개 |
| What-if 재계산 알고리즘 | **미구현** | `what_if/__init__.py` 설명문과 미구현 공통 진입점. 저장 부모/입력 재사용 기능은 백엔드에 존재 |
| MPS/RCCP/MRP 계산 규칙과 HC-01~12 정답 | **설계·손계산 사례만 존재** | `PLANNING_RULES.md` v0.3와 `tests/hand_calc/SMALL_CASES.md`, `small_cases.json`. 엔진 실행 결과와 정답을 비교하는 계산 테스트 없음 |
| 진단·판정·근거의 계산 | **설계·손계산 사례만 존재** | HARD/SOFT·결품·조달 필요량 판정 규칙은 초안. 실제 결과 산출 함수 없음 |
| 계획 출력 DTO | **인터페이스·계약만 존재** | `PlanningOutput`, `PlanCandidate`, `ConstraintEvaluation`, `MaterialRequirement`, `PlanningIssue`. JSON 직렬화/참조 검사는 실행되지만 실제 엔진 출력 없음 |
| 모듈 경계·CAPA 구조 검증 테스트 | **구현 및 실행 검증 완료** | `modules/planning_engine/tests/`의 10개: 2개 경계 + CAPA 구조 8개. 합성 대역 출력임을 명시하며 계산 정답 테스트가 아님 |
| 백엔드→계산→실제 결과 원자 저장·재조회 | **구현됐지만 통합 검증 필요** | 어댑터·저장 서비스/DB 기반은 존재. 실제 계산 모듈이 없어 REAL_ENGINE 계획 생성 E2E는 실행 불가 |

핵심 소스: [공통 진입점(고정 SHA)](https://github.com/ChungPaMo/decision-supporter-mvp/blob/77067f128ea0531f24855584f9ccfa41f2b84d3b/modules/planning_engine/engine/planning.py#L4), [모듈 README](../modules/planning_engine/README.md), [MPS](../modules/planning_engine/mps/README.md), [RCCP](../modules/planning_engine/rccp/README.md), [MRP](../modules/planning_engine/mrp/README.md), [What-if](../modules/planning_engine/what_if/README.md), [규칙 초안](../modules/planning_engine/PLANNING_RULES.md), [손계산](../modules/planning_engine/tests/hand_calc/SMALL_CASES.md), [모듈 경계 시험](../modules/planning_engine/tests/test_planning_boundary.py).

`synthetic/bottleneck_check.py`는 설비/자재 어림 점검 스크립트이며 계획 엔진 정답이 아니다. 실행 시 owner 자료 폴더에 보고서를 쓰므로 이번에는 실행하지 않았다. 로컬 `data/forecast/bottleneck_check.md`도 없었다. 설계의 “절단기 병목” 설명만으로 실제 계획의 생산량·가동률·실행 가능성을 확정하지 않는다.

## 2. 현재 연결 구조와 API

현재 경로는 PostgreSQL 승인 view/배치 → `SqlPlanningSourceProvider.load` → `PlanningInput`까지 실제로 확인했다. 그다음 `engine.planning.run`에서 계산이 막힌다. 저장 기능은 별도 `PlanService.create` → `PlanRepository.save`에 이미 준비돼 있다. Preview는 저장하지 않으며 영구 실행과 혼용하지 않는다.

| 기존 연결점 | 구현 내용 | 이번 확인 / 추가 필요 |
| --- | --- | --- |
| `GET /integrations/modules` | 실제 AVAILABLE와 기능 게이트 표시 | planning=NOT_IMPLEMENTED, plan_persistence=ENGINE_GATED, formal_plan_approval=DISABLED_AUTH_POLICY 확인 |
| `POST /plans` | BASE 읽기 전용 Preview | 유효한 실제 예측 요청도 **501 MODULE_NOT_IMPLEMENTED**. 게이트가 source 조회보다 먼저 작동하므로 이 응답만으로 입력 준비 완료라고 판단하면 안 됨 |
| `POST /plans/what-if` | WHAT_IF·부모 실행 UUID 필수, Preview | **501** 확인. 실제 부모 계획이 없으므로 재계산 불가 |
| `POST /plan-executions` | BASE/WHAT_IF 영구 실행, 원자 저장·중복 재사용 | 실제 요청 **501** 확인. 엔진 대역으로 성공시키지 않음 |
| `GET /plan-executions` 및 `/{execution_id}` | REAL_ENGINE만 목록·상세, digest/관계 재검증 | 공식 dataset 목록 200/0건. TEST_DOUBLE은 공개 조회 제외 |
| `/{execution_id}/candidates`, `/decisions` GET | 저장 후보·결정 이력 조회 | 라우트/DTO 존재. 실제 계획이 없어 실결과 조회 검증은 미완료 |
| `/{execution_id}/decisions` POST | REVIEW/REJECT 이력·버전 충돌 처리 기반 | APPROVE는 **501 PLAN_APPROVAL_DISABLED** 확인. 요청 actor_id는 인증 신원이 아님 |
| `/{execution_id}/export.xlsx` GET | APPROVED/REAL_ENGINE·검증된 승인 이벤트 기반 7시트 출력 구현 | 실제 승인 가능한 실행이 없어 정식 출력 E2E 미완료. 게이트를 풀면 안 됨 |
| `POST /exports/plans/xlsx` | 요청 기반 기존 DEMO Excel | 정식 승인 출력과 별도. DEMO/UNVERIFIED 자료를 실제 저장 결과로 사용 금지 |

Preview 응답은 `PlanningReply {forecast_execution_id,input_digest,result,persisted:false,approval_available:false}`다. 영구 생성은 `PlanExecutionReply {execution,reused}`이며 HTTP 201(신규)/200(재사용), typed INPUT_INVALID/UNSUPPORTED는 FAILED 기록과 422, typed FAILED는 500이다. 모듈 예외·잘못된 출력·DB 저장 실패는 안전한 오류/rollback 경로다. 이 저장 동작의 **현재 실엔진 성공 검증은 없다.**

코드: [API 라우터](../backend/app/api/integrations.py), [영구 실행 라우터](../backend/app/api/plan_executions.py), [SQL provider·어댑터(고정 SHA)](https://github.com/ChungPaMo/decision-supporter-mvp/blob/77067f128ea0531f24855584f9ccfa41f2b84d3b/backend/app/integrations/planning.py#L49), [계획 저장 계약](PLAN_EXECUTION_PERSISTENCE.md), [OpenAPI](../contracts/openapi.json), [공통 모듈 DTO](../contracts/interfaces/modules.py).

### 입력 조회·승인·데이터셋 경계

- BASE 입력은 REPEATABLE READ + READ ONLY에서 성공/PARTIAL 저장 예측과 승인 마스터를 읽는다. 선택 제품·월의 예측이 없으면 409이며 0 수요를 만들지 않는다.
- 제품/자재/BOM/재고는 승인 조회 경로를 사용하고, CAPA/Routing도 승인 행만 가져온다. 출처 배치의 APPROVED·blocking_error_count=0·version/SHA/digest/승인시각을 확인한다. 공식 dataset은 예측 원본 수요 배치까지 9개 출처에 포함한다.
- `dataset_id` query와 명시적 command 소속이 다르면 409다. 같은 스키마의 forecast·배치·계획 UUID만 읽으며 다른 dataset/public으로 fallback하지 않는다. 새 CP 스키마의 FK·view·trigger도 로컬 참조다. 이번 실제 조회에서 타 dataset 예측 UUID는404, provider command 소속 불일치는409였다.
- 기존 LEGACY는 호환성을 위해 예측 원본 수요 출처 추가 방식이 CP와 다르다. “모든 dataset 출처 목록이 동일하다”는 계약을 만들지 말고 저장 예측 자체의 provenance도 함께 유지한다.
- 소속 격리는 인증·사용자별 접근 권한 구현을 의미하지 않는다. 추가 권한 설계가 필요하다.
- as_of_date는 현재 재고 조회 상한이다. 모든 마스터를 그 날짜 당시 승인 상태로 복원하는 시간 여행 조회가 아니다. BASE는 조회 당시 승인된 마스터를 읽고 그 Snapshot을 저장하는 구조이므로, 과거 계획의 마스터 기준시점 의미는 별도 확인해야 한다.

근거: [dataset 서비스](../backend/app/datasets.py), [격리 계약](DATASET_ISOLATION.md), [승인 CAPA 조회](../backend/app/batches/capacity.py), [직전 실제 SQL 검증](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md).

### 이미 있는 저장·재현성·What-if 구조

Alembic **0007**이 `plan_execution`, `plan_candidate`, `plan_constraint_evaluation`, `plan_material_requirement`, `plan_execution_input`, `plan_review`, `plan_decision` **7개 테이블**을 만들었고 0008은 dataset 로컬 구조, 0009는 입력 변환 이력을 확장했다. 새 계획 이력 테이블을 처음부터 제안할 필요가 없다. 현재 개발 revision0009와 공식 dataset 계획0건을 읽기로 확인했다.

- 입력/결과 JSON 전체와 관계형 projection, forecast UUID, 부모 UUID, 배치 version/SHA/digest/승인시각을 보존하고 조회 시 대조한다. immutable/FK/승인 출처 gate가 존재한다.
- input_digest/result_digest, module_version, policy_version, runtime_identity를 저장한다. dedup_key는 입력 전체 + Python 소스 해시 등의 runtime_identity다. advisory transaction lock/부분 UNIQUE로 같은 성공·PARTIAL을 재사용하고 FAILED는 재시도한다. 해당 실제 계획 동시성은 엔진 구현 후 격리 테스트 DB에서 확인해야 한다.
- 현재 policy_snapshot은 `{}`이고 CAPA snapshot과 missing_inputs에 POLICY_NOT_CONFIRMED가 남는다. 이 상태를 FEASIBLE로 바꾸는 출력은 저장 검증에서 거부한다. 정책 버전 전달은 아직 완료가 아니다.
- WHAT_IF는 저장된 REAL_ENGINE 부모의 입력/결과/digest를 재사용하며 forecast·제품집합·월·기준일·dataset을 고정한다. 원본 승인 사실은 수정하지 않는다. 입력 당시 자료를 현재 마스터로 자동 교체하지 않는다.
- REVIEW/REJECT와 최종 APPROVE는 별도다. 현재 공개 APPROVE는 항상 차단하며, 정식 출력도 서버 인증·역할·정책이 연결되기 전 실제 사용 가능하다고 표시할 수 없다.

근거: [저장 서비스](../backend/app/plans/service.py), [저장소](../backend/app/plans/repository.py), [승인 gate](../backend/app/plans/approval.py), [정식 XLSX](../backend/app/plans/exports.py), [0007](../backend/migrations/versions/0007_plan_execution.py), [0008](../backend/migrations/versions/0008_dataset_isolation.py), [0009](../backend/migrations/versions/0009_ingestion_history.py).

## 3. 공식 CHUNGPAMO-2027 데이터 대조

공식 원본·정답은 기존 owner `synthetic/data`를 **읽기만** 했고 [14파일 SHA manifest](../contracts/examples/ingestion_e2e_source_manifest.json)를 전후 재검사했다. 생성기를 실행하거나 다른 성공 데이터로 대체하지 않았다. 개발 DB의 498행은 제품/월/Decimal 수량/단위별로 공식 `05_monthly_demand.csv`와 일치했다.

실제 저장 예측 UUID를 조회해 기준일 `2026-12-31`, 제품 전체9개, 대상 월을 각각 `2027-01`, `2027-02`, `2027-03`으로 바꿔 **기존 provider**를 호출했다. 이는 세 개의 단일 월 입력 검사이지, 하나의 3개월 계획 실행이 아니다.

| 자료 | 실제 저장/전달 확인 | 호환성·남은 판단 |
| --- | --- | --- |
| 제품9 / 자재9 | master와 월별 예측 제품집합 일치. 제품·예측·Routing 수량 EA, 자재 kg/EA | SKU별 EA는 제품 포장 단위다. 롤·팩·kg를 수치만으로 서로 바꾸지 않음 |
| 월수요498 / 예측27 | 저장 forecast1건, 9제품×3개월. 월별 전달9행, P50≤P80≤P90, 모델 버전·runtime identity 포함 | P90도 입력에 보존. v0.3 기준형/안정형은 P50/P80만 사용; P90 선택 정책은 확인 필요 |
| BOM9 / line27 | 승인 활성 V1·base_qty·qty_per·unit·scrap_rate 보존 | 공식 자료는 직접 MATERIAL 구성. 다단계 PRODUCT BOM의 실제 계산 검증은 아님 |
| 재고18 | 완제품9+자재9, 기준일2026-12-31, on_hand/allocated 별도 전달 | 여러 재고 시점이 있으면 provider는 기준일 이전을 모두 전달. 품목별 최신 시점 선택·노후재고 정책을 엔진과 합의해야 함 |
| 자원6 | RW1/RW2/SAW1/PK1/PK2 설비와 LB1 작업 인력 | 공유 resource_id 보존. LB1은 PERSON_HOUR이며 이미 합산된 인시를 인원6으로 재곱하지 않음 |
| 시간 예산18 | 6자원×3개월 저장. 단일 월 input에는6행, h/NET·정규·잔업 별도 | 작업일을 다시 곱하지 않음. GROSS/ELAPSED·셋업·대체 설비는 별도 확정 필요 |
| 수량 한도3 | CP-GIFT-12 월별 FINISHED_OUTPUT 한도2500 EA, 단일 월1행 | 다른 제품에 수량 한도가 없다는 것과 자원 한도가 없다는 것은 다름 |
| Routing27 | 제품당3공정. SAW1은 전제품9개 공유, 포장9공정에 LB1 동시 인시 소요 추가 | 추가 인력 소요는 후속 공정이 아님. 설비 사용시간으로 단순 환산해 합치면 병목 손실 |
| 승인 출처9 | 각 월 input 모두9개, 승인시각·version·SHA/digest 및 수요 출처 유지 | missing_inputs는 POLICY_NOT_CONFIRMED, policy_snapshot은 비어 있음 |
| 예정 입고 / 비용 | owner `derived/scheduled_receipts.csv` 1행, `costs.csv`21행 존재 | DTO·승인 업로드·계획 SQL 입력에는 **미연결**. 파일 존재는 승인 자료가 아님 |

예를 들어 공식 BOM-CP-B2-JUMBO는 제품1 EA 기준 MR-N2 `14.4 kg`와 scrap `0.03`, MC-CORE `16 EA`, MP-JUMBOBOX `1 EA`를 전달한다. 이것은 소요 계산에 필요한 사실이며, 이번에 MRP를 계산한 것이 아니다.

공식 1월 NET 예산은 RW1 400+잔업40, RW2 140+20, SAW1 500+40, PK1 370+40, PK2 110+20 MACHINE_HOUR, LB1 690+60 PERSON_HOUR다. 수요량과 생산 가능량을 비교하려면 **후보 생산량**, 각 Routing의 `run_time/reference_qty`, 공유 자원의 합산 부하, 월별 한도·재고·안전재고를 함께 계산해야 한다. 현재 DTO가 필요한 원시 사실은 보존하지만 계산은 없으므로, 위 예산이나 예측27행만으로 수요 충족·병목 해소·FEASIBLE를 선언할 수 없다.

## 4. 계약 불일치 및 변경 요청

아래는 발견 사실과 제안이다. 김대영이 공통 계약을 검토하고 이희원이 계산 의미를 확인하기 전, 현행 DTO·업무 규칙을 교체하지 않는다.

| ID / 우선순위 | 현행 코드와 설계의 차이 | 필요한 합의·변경 범위 |
| --- | --- | --- |
| C01 / P0 기간 | PlanCommand는 target_month 하나. SQL provider·CAPA helper는 그 월만 선택, 어댑터/저장 validate_pair는 출력 기간도 같은 월로 제한. v0.3은 시작 월부터3개월·선행생산 | 명시 horizon/기간 배열·지원 범위를 버전 계약으로 확정. provider, 출력 검증, 저장 envelope/DB CHECK, What-if, 출력·FE 타입·Schema 동시 검토. 세 번 단일 월 호출로 재고 이월을 대체하지 않음 |
| C02 / P0 예정 입고 | v0.3 R(k,m)을 사용하나 PlanningInput에 칸이 없음. 해당 추가 필드는 extra_forbidden. CSV는 po_id/material_id/qty/unit/expected_date/supplier_id이며 미승인 | 일정/단위/미입고·부분입고·취소·중복·월말/기준일 의미, 승인·dataset·배치 출처 계약 필요. 파일을 engine에서 직접 읽는 방식 금지. 필요 migration은 별도 개발/승인 |
| C03 / P0 What-if | 백엔드 허용은 production_qty.<product>, overtime_hours_limit.<capacity_id>뿐. v0.3은 수요배수·잔업·재고·예정 입고 변경 | 허용 키·제품/자원/월 범위·Decimal 정밀도·취소 표현을 확정. capacity_id는 여러 월에 재사용되므로 현재 키로3개월 구분 불가. 음수 delta 대신 절대값 여부도 결정. BASE 원본·forecast는 불변 |
| C04 / P0 정책 | v0.2 product_id 순 배분과 v0.3 비례 축소, 선행생산·비용절감형/결품 허용이 다름. policy_snapshot={}·정책 미확인 표시가 항상 남음 | 희원 계산 제안과 팀 합의를 구분. policy_version과 적용 범위·예외/셋업·대체/공유 자원 의미를 결정한 뒤 서버가 전달. AVAILABLE만 True로 바꾸지 않음 |
| C05 / P0 자재 수량 의미 | v0.3 available=AV(m)-AV(m-1)은 안전재고 부족 시 음수 가능. shortage=SH(m)-SH(m-1)은 후속 입고로 누적 부족 감소 시 음수 가능. DTO 두 필드는 비음수 DecimalValue이고 DB도 음수를 허용하지 않음 | 누적 부족/신규 조달 필요/해소량/순증감 중 무엇인지 합의. 비음수로 몰래 clamp하지 않음. DTO·NUMERIC 제약·Excel·화면 명칭·손계산 정답을 함께 검토 |
| C06 / P0 판정 | v0.3은 SOFT 위반을 FEASIBLE와 양립시킴. 현행 formal approval는 모든 체크 SATISFIED/APPLIED 요구. 한편 PlanningOutput 자체는 FEASIBLE+HARD VIOLATED를 거부하지 않는 검증 공백 존재 | 계산 feasibility와 승인 자격 규칙을 각각 확정. HARD 모순 차단 및 SOFT 승인 조건은 계약/회귀 테스트로 보강할 후속. 현재 승인501은 유지 |
| C07 / P1 누락 제품 | v0.3은 예측 누락 제품 제외/PARTIAL, provider는 선택 제품 중 하나라도 해당 월 예측 없으면409 | 사용자가 선택한 제품/예측 제외 제품 처리·실제 계획 범위를 합의. 0 수요 변환 금지 유지. missing inputs→UNVERIFIED와 요청 자체 거절을 구분 |
| C08 / P1 BOM·재고·라우팅 | provider는 월과 겹치는 BOM 후보, 기준일 이전 모든 재고를 보존. v0.3 BOM은 월1일 선택. Routing 다중버전/월중 유효기간은 미확인 플래그 | 최신 재고 선택·BOM 다단계/제품 구성·월중 변경·라우팅 버전/인력 단위를 명시. 공식 자료의 단일 버전/동일 시점만으로 일반 정책을 검증했다고 하지 않음 |
| C09 / P1 추천·KPI·비용 | 기존 plan-export draft의 kpis/comparison/ranking 구조와 typed PlanningOutput이 다름. typed output에 KPI·추천 plan_id 없음. 비용21행도 미연결 | 비용절감형을 실제 비용 최적화로 부르지 않음. 비교 지표·식·통화/미산출 null·추천과 최종 선택 차이를 합의한 뒤 별도 버전 확장 |
| C10 / P1 식별·후보 선택 | 후보 plan_id는 execution 내부 문자열, DB 키는 execution_id+plan_id. What-if는 부모 execution 전체만 지정하며 base_plan_id 없음 | 후보별 조정인지3개 후보 전체 재생성인지 확인. plan_id 문자열만 전역 UUID처럼 사용 금지. 선택 후보·추천·APPROVED 상태는 별개 |
| C11 / P1 검증 일관성 | Preview run_snapshot은 생산행 월/단위 등을 확인하지만 저장 validate_pair의 자재·자원·평가 범위 검증보다 좁음 | 공통 입력/출력 범위 검증 재사용 계획 수립. 기간 확장 시 Preview만 통과하고 저장은 거부하는 차이를 없앨 것 |

C05/C06은 **소규모 DTO 실험으로 확인**했다. 음수 available_qty/shortage_qty는 거부됐으며, 기존 TEST-DOUBLE-ONLY fixture의 후보를 FEASIBLE·정책참조 있음·미확인 없음으로 바꾸고 HARD VIOLATED 평가를 주면 PlanningOutput 검증은 통과했다. 이 실험은 메모리 DTO 검사만 수행했고 엔진 성공/DB 저장/정식 승인으로 취급하지 않았다. 현재 API/정책 게이트를 우회하지 않았다.

### 기존 문서와 최신 코드의 차이

- [INTEGRATION_CONTRACT](INTEGRATION_CONTRACT.md)의 상단 “0009 미적용”은 11/16 기록이다. 현재 개발 DB0009는 [11/17 실DB 보고서](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md)가 최신이다. 초기 본문의 분류 미구현·계획 저장소 없음 표현도 후속 확장 안내/코드와 구분한다.
- [engine_forecast_plan_contract](engine_forecast_plan_contract.md)의 `engine.plan.run(dict)`, 일별 시간×근무일 중심 입력, routing 신규 요청, kpis/comparison/export 응답은 예전 설계다. 실제 진입점은 `engine.planning.run(PlanningInput)`이며 승인 월별 CAPA/Routing·계획 저장 기반이 이미 있다. 이 문서를 그대로 API DTO로 구현하지 않는다.
- [PLANNING_RULES v0.3](../modules/planning_engine/PLANNING_RULES.md) §9는 희원 제안/대영 확인 필요 항목을 명시한다. 최신 설계라는 이유만으로 공통 계약을 변경하지 않는다.
- [PLAN_EXECUTION_PERSISTENCE](PLAN_EXECUTION_PERSISTENCE.md)의 510/55 등은 당시 검증 기록이다. 직전 전체1015/2제외와 이번 집중71개를 서로 대체하지 않는다. [DATASET_ISOLATION](DATASET_ISOLATION.md)의0008 역시 작성 시점 기록이다.

이번 요청의 수정 범위에 맞춰 위 원문은 보존하고 이 차이 목록과 최신 진행 문서에 정정 관계를 기록했다.

## 5. 김대영 후속 작업 — 독립 작업과 의존 작업

아래 파일은 **수정 예상 위치**이며 이번에 변경하지 않았다. 경로가 없는 신규 파일/라우트는 제안임을 표시했다. 전체 신규 provider·저장소·테이블·승인 API를 중복 생성하지 않는다.

| ID / 우선순위 / 담당 | 현재 상태·필요 변경 | 예상 파일 | 선행 조건·완료 기준 |
| --- | --- | --- | --- |
| B01 / P0 / 김대영, 즉시 독립 가능 | 단일 월 source provider는 실제 조립 가능하나 미구현 gate 앞에서 입력 준비 상태를 볼 공개 API 없음. 계산 없는 입력 진단 API/DTO를 기존 load 위에 추가하는 설계·개발 | `backend/app/integrations/planning.py`, `backend/app/api/integrations.py`, `contracts/interfaces/planning.py`, `backend/tests/test_planning_sources.py`; 신규 `POST /planning-inputs/preview` **경로 제안** | 엔진 호출·실행/승인 저장 없음, UUID/dataset/월별 coverage·출처·정책 미확인·입력 digest 표시. raw 전체 자료의 노출 범위는 UI와 합의. 404/409/422/503·미구현 모듈에서도 진단 가능함을 검사. 현행 단일 월 범위 먼저 가능 |
| B02 / P0 / 김대영, 즉시 독립 가능 | 범위/출처 검증과 Preview·저장 검증 차이를 분리하고 실패 사례를 고정. 기존 provider/validate_pair 재사용 | `backend/app/plans/service.py`, `backend/app/integrations/planning.py`, 관련 기존 tests, `contracts/examples/integration/` | 계약을 바꾸지 않는 명백한 참조/단위/월 오류부터 검증. 기간 확대·HARD/SOFT 업무 판정은 C01/C06 후. 타 dataset·예측 누락·잘못된 자원·원본 변조·사실 누락을 성공 처리하지 않을 것 |
| B03 / P0 / 김대영+이희원, 합의 문서부터 독립 가능 | 버전별 차이/fixture 목록/엔진 인수 테스트 명세 작성, C01~C06 확정 요청 | `docs/INTEGRATION_CONTRACT.md`, `docs/engine_forecast_plan_contract.md`, `contracts/interfaces/planning.py`, `contracts/examples/integration/`, 기존 schema/OpenAPI 생성기 | v0.3는 초안으로 유지. 기간/입고/부호/정책/What-if 합의 후 DTO·생성 Schema·예시 동시 변경. 희원 알고리즘 수정 대신 승인된 계약 전달 |
| B04 / P1 / 김대영, C01/C08 의존 | 기존 단일 월 입력 조회를 명시적 horizon으로 확장. 월별 forecast/CAPA/BOM/재고 후보·원본 출처 보존 | `backend/app/integrations/planning.py`, `backend/app/batches/capacity.py`, `backend/app/plans/service.py`, 계약/관련 tests | 기간 계약 확정. 9제품×3월27행 + 자원6×3월18예산 + 월별 수량3행, 재고 이월 입력과 공유 자원을 하나의 Snapshot에 보존. 부분 기간 부족 오류/미확인 규칙 검증 |
| B05 / P1 / 김대영, C02 의존 | 예정 입고의 승인 등록·조회·dataset provenance는 없음. 기존 batch gate를 재사용하는 별도 설계 | `contracts/interfaces/`, `backend/app/batches/`, `backend/app/integrations/planning.py`, 미래 신규 migration, `backend/app/dataset_schema_v2.py` 후속 버전 | 입고 정의/승인 순서 합의 및 별도 migration 작업 범위 필요. 개발 DB 적용은 별도 승인. 미승인·취소·중복/다른 dataset 제외, 배치 지문/버전 재현 가능 |
| B06 / P1 / 김대영, C03/C10 의존 | 저장 부모 조회·계보·입력 불변 이미 구현. override DTO를 월별 명시 구조로 확장 | `contracts/interfaces/planning.py`, `backend/app/plans/service.py:what_if_snapshot`, 관련 tests | 허용 조정과 후보 범위 합의. 실제 부모·forecast·dataset 일치, BASE/부모 불변, 조건별 새 digest·계보·재조회 검증. 엔진 재계산 자체는 희원 담당 |
| B07 / P1 / 김대영, C04/C06·실엔진 의존 | 실행 이력7테이블·원자 저장·중복/오류 구조 존재. 정책 registry/버전 전달 및 실결과 저장 검증 보강 | `backend/app/plans/service.py`, `backend/app/plans/repository.py`, `backend/tests/test_db_dataset_e2e.py`, `backend/tests/test_plan_executions.py`; 필요 시 신규 실엔진 SQL 시험 파일 | 정책 합의·실엔진 제공·격리DB 사용 승인. typed 실패 저장/예외 rollback/동시 재사용/엔진 버전 변경 새실행/REAL_ENGINE만 공개를 실제SQL로 확인. 기존 migration 재작성 금지 |
| B08 / P2 / 김대영, 인증·업무 정책 의존 | REVIEW/REJECT와 formal_export 존재, APPROVE501. 서버 인증·역할/최종 승인 정책 연결 | `backend/app/plans/approval.py`, `service.py`, `api/plan_executions.py`, `exports.py`, 계약/DB tests | 서버 권한·정책·예외 승인 여부 결정. 요청 actor_id만으로 승인 불가. 버전/digest409, 저장된 선택 후보만 승인/7시트 출력, 변경 이력·위험·정밀도 보존 |
| B09 / P1 / 김대영+정마나미, API 명세 인계는 즉시 가능 | FE API client에는 영구 실행 메서드가 있으나 실제 패널은 Preview만 호출. 기존 client/types를 재사용하도록 인계 | `docs/TEAM_HANDOFF.md`, `docs/INTEGRATION_CONTRACT.md`; FE 변경은 나미 소유 | Preview/저장·계산상태/승인상태/DEMO를 분리한 명세 전달. 구현/검증은 정마나미 담당, 실제 결과 준비 전 성공 화면 활성화 금지 |

기존 실제 SQL의 계획 경계 시험은 [test_db_dataset_e2e.py:test_plan_dedup_lineage_concurrent_review_and_audit](../backend/tests/test_db_dataset_e2e.py)에 있다. TEST_DOUBLE 결과를 SQL에 저장해 중복/계보/동시 검토·격리를 검사하며 실엔진 계산 시험은 아니다. [verify_plan_storage.py](../scripts/verify_plan_storage.py)도 대역의 rollback 검증이다. 둘 다 이번에 실행하지 않았다. 후속 DB 검증은 fixture의 초기화/downgrade 동작부터 읽고 해당 실행의 별도 허가를 받아야 한다.

## 6. 이희원에게 확인·요청할 사항

1. v0.3/HC-01~12가 구현 기준인지, 기존 v0.2 대비 변경에 대한 팀 확인 상태는 무엇인가? 기간3개월·비례 배분·잔업 우선·모든 안 선행생산·비용절감형 결품 허용을 각각 확정 요청한다.
2. `run(PlanningInput)->PlanningOutput` 및 AVAILABLE 계약을 유지하고, DB/파일 접근 없이 주어진 Snapshot만으로 계산 가능한가? 공식 CSV를 런타임에서 직접 읽지 않고, 필요한 필드를 C01~C03 요청으로 전달해 달라.
3. 예정 입고는 기준일 이전 미입고와 일부 입고/취소를 어떻게 판별하며 월중 입고를 월 전체 사용 가능으로 보는가? lead time 없이 PROCUREMENT_REQUIRED를 표시할 경우 사용자 해석을 명시해 달라.
4. C05의 음수 가용·부족량 감소를 어떤 필드로 표현할 것인가? 누적과 당월 조달 필요량/해소량을 구분한 손계산 예시와 반올림/직렬화 정밀도를 요청한다.
5. 예측 누락/재고 누락/다중 BOM/라우팅 일부 누락·공유 인력의 정책과 INPUT_INVALID/PARTIAL/UNSUPPORTED/FAILED 경계를 확정해 달라. 없는 입력을 0 또는 무한으로 처리하는 경우에도 UNVERIFIED 근거를 보존해야 한다.
6. SOFT 위반 FEASIBLE, HARD VIOLATED INFEASIBLE, HARD UNVERIFIED의 합성 규칙과 공식 승인 가능 조건을 구분해 달라. 김대영 검증/승인 gate와 일치시키되 승인 권한은 엔진이 만들지 않는다.
7. What-if는 부모 후보 하나 조정인지 전체 후보 재생성인지, 수요배수·재고·입고·잔업의 월별 적용 범위를 요청한다. 조건 변경은 승인 원본을 바꾸지 않는다.
8. 후보 ID/정책 버전/근거 code/input_refs를 결정적으로 반환하고, HC-01~12→실제 run 자동 비교와 공식9제품×3월 테스트를 owner 폴더에서 제공해 달라. 계산 테스트 없이 AVAILABLE만 켜지 않는다.
9. 다단계 BOM·ELAPSED/min·셋업·대체 설비·GROSS·P90 안정형 지원 범위를 명시해 달라. 미지원은 명시적 오류/미확인으로 반환하고 일반 지원으로 포장하지 않는다.

## 7. 정마나미에게 전달할 API 요구사항

이번에는 frontend를 수정하지 않았다. [PlanningWorkspace](../frontend/src/screens/PlanningWorkspace.tsx)는 DEMO와 LIVE를 분리하고, [LivePlanningPanel](../frontend/src/components/LivePlanningPanel.tsx)은 실제 예측 이력/상세를 고른 뒤 `apiClient.requestPlan`으로 **Preview**만 호출한다. 현재 What-if/승인 단계도 미연결 안내다. [api client](../frontend/src/services/api.ts)에 영구 생성/목록/상세/후보/결정 메서드는 이미 있으므로 다시 생성하지 않는다.

- dataset 변경 시 이전 요청/선택 forecast/plan/preview를 무효화하고 모든 영구 API에 같은 dataset_id를 명시한다. 현재 client의 dataset scope·기존 store를 재사용한다.
- 실작업은 `POST /plan-executions`의 execution UUID로 이력/상세를 복원하는 흐름이며 `/plans`는 저장 이력이 없는 Preview임을 유지한다. 기존 최근20개 예측 선택의 페이지 탐색, 기준일 입력, 기간 UI는 확정 계약에 맞춰 확장한다.
- `status=COMPLETED/PARTIAL/FAILED`, 후보 `feasibility=FEASIBLE/UNVERIFIED/INFEASIBLE`, `decision_status`는 서로 다른 축이다. PARTIAL이나 결품·조달 미확인을 성공 승인처럼 표시하지 않는다.
- 후보 식별은 execution_id+plan_id, What-if는 실제 부모 execution_id를 사용한다. 제약의 resource_id/period/unit/time_basis/strength/application_state·reason_codes·input_refs, 자재별 required/available/shortage와 null을 보존한다.
- 501 미구현/승인 비활성, 409 소속/버전/결과 충돌, 422 입력·모듈 입력 오류, 503 연결 실패, 500 계산/저장 오류를 구분한다. 생성 오류가 `PlanExecutionReply` 또는 `ErrorResponse`일 수 있으므로 보존된 FAILED 실행도 상세 표시 가능하게 한다. 네트워크 실패를 DEMO로 전환하지 않는다.
- What-if 컨트롤은 C03/C10 합의 범위만 제공하고 비교 지표·추천 순위·비용 KPI를 임의 계산하지 않는다. 수기 예시 값과 실제 반환 값의 차트를 섞지 않는다.
- REVIEW/REJECT와 APPROVE를 분리하고 정식 승인 버튼은 서버 기능/권한 정책 준비 전 비활성이다. 실제 출력은 `/{execution_id}/export.xlsx`, DEMO 출력은 별도 명시한다.
- 향후 브라우저 인수 기준: 승인 dataset→성공 forecast 선택→진단→실제 계획 저장/후보·제약·자재 표시→부모 What-if→새로고침 복원→정책 준비 후 검토/승인/출력. 현재 완료 항목으로 보고하지 않는다.

## 8. 단계별 통합 순서와 완료 기준

1. **즉시:** 김대영 B01/B02/B03/B09. 기존 단일 월 입력 조립/진단과 오류/출처 명세부터 준비한다. 계산 모듈 미완료와 무관하게 진행 가능하다.
2. **공통 계약 결정:** 김대영 검토 + 희원 계산 의미 + 나미 업무/표시 확인으로 C01~C06·C10 결정. horizon·부족량·정책·What-if 버전 DTO/Schema/OpenAPI·작은 fixture를 먼저 일치시킨다.
3. **입력 확장:** 김대영 B04~B06. 기존 approval/dataset gate를 재사용하고 예정 입고의 저장 설계는 별도 범위로 진행한다. migration 필요 시 새 이력을 작성하고 개발 DB 적용은 별도 승인한다.
4. **실제 계산 제공:** 이희원이 owner 폴더에서 MPS/RCCP/MRP/What-if와 손계산 대비 자동 테스트를 완성한다. 안전한 backend boundary와 결합해 실결과 범위/단위/판정/근거를 검증한다.
5. **격리 SQL 통합:** 새 실행 승인 범위의 테스트 DB에서 B07. 공식 자료→27행 horizon→2~3후보→저장/재조회→동시 재사용·실패 rollback→What-if 계보와 원본 불변을 확인한다. 개발 자료는 초기화하지 않는다.
6. **실제 화면:** 정마나미가 기존 LIVE 패널/client를 영구 실행에 연결하고 복원·오류·DEMO 분리 브라우저 E2E를 검증한다.
7. **정식 승인·출력:** 팀 업무 정책/서버 인증을 갖춘 후 B08. 추천은 사용자 승인과 별개이며 UNVERIFIED 예외 승인을 임의로 열지 않는다.

제조 전체 E2E 완료 기준은 실제 엔진으로 산출한 후보·자원/자재 평가와 재현 가능한 저장 결과가 있고, What-if 및 사용자 최종 승인/출력이 서버 정책에 따라 동작하는 것이다. 지금의 자료 준비/예측 성공·저장 기반만으로 완료 처리하지 않는다.

## 9. 이번 실행 검증과 데이터 보존

실행일/환경: 2026-11-17, 기존 개발 PC의 `.venv`/Python·FastAPI TestClient. 브라우저·모델 재학습·서비스 변경은 수행하지 않았다.

```powershell
.\.venv\Scripts\python.exe -m pytest --no-db modules/planning_engine/tests backend/tests/test_planning_adapter.py backend/tests/test_planning_sources.py backend/tests/test_plan_executions.py backend/tests/test_module_integration.py backend/tests/test_contract_schema_sync.py -q
```

결과: **71 passed / 0 failed / 0 skipped**. Starlette/httpx deprecation warning1건. 모듈10개/어댑터·source·저장·capability/Schema 경계를 검증했다. 기존 대역 기반 검사는 대역임을 유지하며 실제 SQL 계산 저장 성공으로 보고하지 않았다.

별도 비파괴 확인:

- 전용 Docker 프로젝트/container/volume/network/127.0.0.1:55433 확인, 실제 `chungpamo`/`chungpamo_app`/revision0009와 `transaction_read_only=on` 확인. 55432·다른 프로젝트 DB 접근 없음. Docker는 전용 컨테이너 inspect만 수행했다.
- 기존 실제 SQL provider로 공식 3개 월 입력 조립, 월별9제품·9승인출처·분위수 순서 확인. 타 dataset forecast404, provider dataset 불일치409, 모르는 제품409 확인.
- 실제 `engine.planning.run(공식 입력)`은 NotImplementedError. 실제 FastAPI TestClient capabilities/세 생성 API501/실행 목록200·0건/APPROVE501 확인. **결과 계산·DB 쓰기·모듈 성공 대역 주입 없음.** 접속 설정만 강제 읽기 전용 엔진으로 교체했다.
- 공식 수요498행 정답 일치, manifest14파일 SHA 전후 일치. 개발 DB **60테이블 행 수·행 전체 SHA, 스키마 객체735개 정의 SHA, dataset registry, 승인7+9배치, 예측 각1건, revision, Docker 자원 identity 모두 동일**. 개발 DB·테스트 DB·회귀 DB를 초기화하지 않았고 migration도 실행하지 않았다.
- DTO 실험: 추가 horizon/입고 필드 거부, 음수 가용/부족량 거부, HARD VIOLATED+FEASIBLE 검증 공백 확인. 이는 발견 결과이며 업무 계약/서비스 코드는 이번에 변경하지 않았다.

검사 과정에서 일회성 읽기 스크립트의 날짜 직렬화 차이(datetime↔JSON 문자열)로 보존 비교가 한 번 실패했다. 동일 JSON 직렬화 후 전체 지문이 일치해 DB 변경이 아님을 확인했다. 추가 정답 조회도 임의 컬럼명(month/quantity)으로 한 번 실패했으며 실제 모델의 period/demand_qty로 수정해 통과했다. 둘은 검사 도구 오류이고 서비스 코드 결함/테스트 통과로 숨기지 않는다.

로컬 상세 증거는 Git 제외 `.artifacts/planning-readiness-20261117/`의 `development-before.json`, `development-after.json`, `readiness.json`, `contract-probes.json`이다. 비밀 접속값·백업·공식 원본 파일은 Commit에 포함하지 않는다. 이 보고서의 확정 수치와 고정 SHA 코드 링크로 검토할 수 있다.

전체 pytest/파괴적 PostgreSQL 회귀·migration 왕복·브라우저 E2E·TypeScript/build는 이번 분석에서 **미실행**이다. 직전 `77067f1`의 1015 passed/2 deselected를 이번 재실행 결과로 사용하지 않는다. 변경 문서3개의 **로컬 Markdown 링크107개 경로 검사**, `git diff --check`, `scripts/security_check.py` 검사(**텍스트435파일·findings0**)를 통과했다. 보안 검사는 알려진 로컬 비밀값/토큰·개인 경로 등의 휴리스틱 검사이며 모든 정보 노출을 보증하는 감사는 아니다.

## 10. 잔여 위험과 인수 조건

- **P0:** 계산 함수 부재, 단일 월↔3개월, 예정 입고 provenance 부재, What-if 범위, 정책 미확정, 음수 자재 의미와 판정 검증 차이. 희원과의 합의/실제 구현 전 성공 계획 API를 활성화할 수 없다.
- **P1:** 재고·버전 선택/미지원 단위·다단계 BOM, 정책 버전 재현성, 동기 계산의 시간/동시성·원자 저장, 부분 결과와 근거, FE 영구 실행·복원. 공식 자료의 단순 버전만으로 일반 사례를 보장하지 않는다.
- **최종 단계:** 서버 인증·역할·최종 승인/예외 정책·비용/KPI를 별도로 결정한다. 현재501을 제거하는 것만으로 승인/운영 검증 완료가 되지 않는다.

이번 준비 단계의 완료 기준은 실제 입력 가능 범위·미구현 경계·계약 차이·담당/의존 작업을 근거와 함께 기록하고 기존 자료를 보존하는 것이다. 후속 엔진/서비스 개발 완료와 구분한다.
