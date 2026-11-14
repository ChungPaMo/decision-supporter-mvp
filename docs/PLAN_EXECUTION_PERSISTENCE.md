# 생산계획 실행 저장·검토·출력 기반

2026-11-15. **저장 시스템 기반 구현이며 실제 계산·인증·정식 승인 활성화 완료가 아니다.** engine.planning.run은 AVAILABLE=False다. frontend와 알고리즘 담당 폴더는 변경하지 않았다.

## API와 예시

기존 POST /plans와 POST /plans/what-if는 저장하지 않는 Preview로 유지한다. 신규 영구 실행 API는 다음과 같다.

| API | 계약·현재 상태 |
|---|---|
| POST /plan-executions | PlanExecutionCreate → PlanExecutionReply. 현재 501 MODULE_NOT_IMPLEMENTED, Fixture 대체 없음 |
| GET /plan-executions | limit(1~100)/offset → items/total/limit/offset. REAL_ENGINE만 조회, 현재 0건 |
| GET /plan-executions/{execution_id} | 입력·결과 전체 Snapshot, digest·버전·검토 상태·이력. 없음/TEST_DOUBLE이면 404 |
| GET /plan-executions/{execution_id}/candidates | 실행에 속한 후보 목록 |
| GET /plan-executions/{execution_id}/decisions | 결정 이벤트 목록 |
| POST /plan-executions/{execution_id}/decisions | REVIEW/REJECT 기록. APPROVE는 인증·정책 미연결로 501 PLAN_APPROVAL_DISABLED |
| GET /plan-executions/{execution_id}/export.xlsx | 인증·정책 검증을 거친 승인 저장 후보만 출력. 현재 출력 가능한 실제 계획 없음 |

생성 요청(아래 UUID는 형식 예시이며 실제 저장 예측 UUID를 사용해야 한다):

```json
{"forecast_execution_id":"00000000-0000-4000-8000-000000000001","product_ids":["TP-10R"],"target_month":"2027-01","as_of_date":"2026-12-31","scenario":"BASE"}
```

검토 요청:

```json
{"plan_id":"BASE","action":"REVIEW","actor_id":"REVIEWER-01","reason":"검토 시작","expected_version":1,"expected_input_digest":"sha256:0000000000000000000000000000000000000000000000000000000000000000"}
```

실제로는 조회 응답의 version/input_digest를 그대로 보낸다. actor_id는 **미인증 역할 코드 주장**이며 신원 증명이 아니다. REVIEW/REJECT의 auth_verified=false를 명시한다. 요청 JSON에 role/auth_verified/exception_codes를 넣으면 거부한다.

생성 응답은 `{execution: PlanExecutionDetail, reused: boolean}`이다. 성공 201, 동일 성공/PARTIAL 재사용 200. 검증된 엔진 INPUT_INVALID/UNSUPPORTED는 FAILED 실행으로 보존하고 HTTP 422, FAILED 출력은 HTTP 500이다. 예외/잘못된 DTO/DB 오류는 후보를 저장하지 않고 안전한 오류를 반환한다. PERSISTENCE 비활성 501, DB 불가 503, DB 저장 오류 500이며 부분 저장을 성공으로 반환하지 않는다. 실제 응답 형식은 생성된 contracts/examples/responses/40~42 예시를 참고한다. 이는 테스트 대역/차단 응답이며 엔진 성공 증명이 아니다.

## DB — Alembic 0007

기존 0001~0006을 보존하는 추가 migration이다. 기존 source·forecast·CAPA·Routing 데이터를 변경하지 않는다.

| 테이블 | 컬럼·관계 |
|---|---|
| plan_execution | execution_id PK, forecast_execution_id→forecast_run, base_plan_execution_id 자기참조, scenario_type, target_month, as_of_date, status, input_digest, result_digest, dedup_key, input_snapshot/result_snapshot JSONB, engine_version, policy_version, runtime_identity, data_origin, created_at, completed_at, error_code, created_txid |
| plan_candidate | (execution_id,plan_id) PK, plan_type, label, feasibility, production_rows JSONB, policy_ref, unverified, payload |
| plan_constraint_evaluation | (execution_id,plan_id,constraint_id) PK와 후보 FK. dimension, period, resource_id/product_id/step_id, status, limit_value/used_value, unit, time_basis, strength, application_state, input_refs, reason_codes, payload |
| plan_material_requirement | (execution_id,plan_id,material_id,period) PK와 후보 FK. required_qty/available_qty/shortage_qty, unit, input_refs, payload |
| plan_execution_input | 실행/배치 복합 PK, batch_version, source_sha256, result_digest, approved_at. import_batch FK와 승인 버전 대조 trigger |
| plan_review | execution_id PK, selected_plan_id 후보 FK, status, version |
| plan_decision | decision_id PK, 실행/후보 FK, action, status_before/status_after, review_version, actor_id, auth_verified, reason, input_digest, decided_at, exception_codes. 실행별 review_version UNIQUE |

수량/시간은 NUMERIC(20,6), JSON은 Decimal 문자열로 보존한다. null을 0으로 바꾸지 않는다. 실행·후보·평가·출처·이벤트 UPDATE/DELETE 금지, 후보/평가는 실행 생성 트랜잭션에서만 INSERT 가능하다. deferred trigger가 JSON과 relational 후보/평가/자재/출처 행 수를 비교한다. 읽을 때 DTO·범위/단위·digest·relational payload를 재검증한다. 부모 FK는 forecast UUID와 data_origin도 묶어 다른 예측/TEST_DOUBLE 계보 연결을 차단한다.

## 상태·원자 저장·중복

동기 실행으로 최종 COMPLETED/PARTIAL/FAILED만 원자 저장한다. 기존 forecast처럼 완료 중심이며 RUNNING을 선커밋하지 않는다. OK→COMPLETED, PARTIAL→PARTIAL, INPUT_INVALID/UNSUPPORTED/FAILED→FAILED로 기록하고 원본 출력 상태·오류도 보존한다. 예외/중단은 이번 트랜잭션을 rollback한다.

서버가 승인 출처를 REPEATABLE READ·READ ONLY로 읽고 PlanningInput을 구성한다. 정렬 키·UTF-8·compact JSON 전체의 SHA-256(`sha256:` 접두사)을 input_digest로 저장한다. 결과도 별도 result_digest로 보존한다. 예측 지문·모델 버전·원본 배치 version/SHA/digest는 입력에 포함된다. 엔진에는 깊은 복사본을 넘긴다.

입력 전체+runtime_identity(엔진 버전·계획 엔진 Python 소스 해시)의 SHA가 dedup_key다. 같은 키 advisory transaction lock과 부분 UNIQUE로 완료/PARTIAL을 재사용한다. FAILED는 재시도한다. 입력·엔진 소스가 달라지면 새 실행이다. 클라이언트 결과/Snapshot 업로드 API는 없다.

## What-if

기본 정책은 **저장 당시 입력 재사용**이다. 현재 기준정보로 몰래 갱신하지 않는다. 실제 부모의 forecast UUID·제품 집합·대상 월·기준일이 같아야 한다. 새 승인 자료를 쓰려면 새 BASE를 만든다.

허용 Override는 `production_qty.<선택 제품>`와 `overtime_hours_limit.<저장된 hours capacity_id>`, 값은 DecimalValue 비음수 문자열이다. 이는 시나리오 요청일 뿐 승인 원본을 수정하거나 계산식을 실행하지 않는다. 적용 정책 미확정은 WHAT_IF_OVERRIDE_POLICY_UNCONFIRMED로 남긴다. Forecast/배치/결과 변경 키는 422다.

base_plan_snapshot에 실제 부모 ID·forecast UUID·input/result digest·전체 부모 결과를 넣고, 자식 실행에 원본 입력 사실과 새 command를 보존한다. 원본/변경 조건/각 평가 결과를 비교할 수 있으며 KPI 차이 공식을 발명하지 않는다. 기준 계획이 있어도 엔진 미구현이면 계산은 501이다.

## 검토·정식 승인·출력

계산과 별도 상태 `DRAFT → REVIEW → APPROVED 또는 REJECTED`. REVIEW에서 후보를 선택하고 해당 후보만 최종 결정한다. 최종 상태는 되돌리지 않고 새 실행으로 처리한다. 검토 행 FOR UPDATE와 expected_version/digest를 검사하고, DB decision trigger가 이벤트 INSERT와 상태 갱신을 함께 수행한다. 오래된/중복 결정은 409다.

**공개 APPROVE는 항상 501이다.** 내부 ApprovalContext는 미래 서버 인증 연동용으로 요청 DTO에 없다. 신뢰된 주체·PLAN_APPROVER 역할·정책 활성화가 필요하다. 그 후에도 실패/타 실행 후보, INFEASIBLE/UNVERIFIED, 정책 버전·근거 없음, 미확인 입력/제약, TEST_DOUBLE은 차단한다. 예외 승인 정책은 구현하지 않았다. 미인증 REVIEW/REJECT를 공식 승인으로 표현하지 않는다.

정식 XLSX는 저장된 APPROVED/REAL_ENGINE 후보와 인증된 승인 이벤트·정책·FEASIBLE·완료 제약을 확인한다. 미승인은 409 PLAN_EXPORT_BLOCKED, 없음/격리 대역은 404다. Overview/Forecast/MPS/RCCP/MRP/Exceptions/Audit 7시트에 예측 UUID·P50/P80/P90·생산수량·제약·자재·경고·승인/출처·digest·엔진 버전을 표시한다. 기존 safe_text/_put_number를 재사용해 수식 주입과 Excel 15자리 정밀도 손실을 막고 null은 미산출로 표시한다.

기존 DEMO 출력은 유지한다. test_double_export는 HTTP 경로가 없고 TEST_DOUBLE만 받아 모든 시트/속성에 SYNTHETIC / TEST-DOUBLE-ONLY / UNAPPROVED를 표시한다. 대역은 공개 이력·상세·What-if 기준·정식 승인/출력에 들어가지 못한다.

## 안전·검증·미완료

전용 chungpamo-monorepo/127.0.0.1:55433/chungpamo, 사용자 chungpamo_app, 기존 0006·승인 배치 7개·테이블 행 수를 확인 후 0007을 적용했다. 기존 데이터와 배치 상태는 보존했다. scripts/verify_plan_storage.py는 신규 TEST_DOUBLE만 외부 트랜잭션에 넣고 모두 rollback한다. 가짜 정식 계획은 개발 DB에 남기지 않는다.

초기화가 필요한 기존 DB 55개 pytest·migration 왕복·파괴적 E2E는 미실행이다. 실제 계산·정식 승인·What-if 재계산, 인증·역할·H-/N- 정책·UI 연동은 후속이다. 대역 검증을 실제 계산 또는 정식 운영 승인 검증으로 표현하지 않는다.

### 이번 실행 결과

- 비DB 전체 pytest **510 passed / 0 failed / 55 skipped**. 새 단위 시험 31개 포함. Starlette/httpx deprecation warning 1건. 기존 테스트 삭제·skip 전환 없이 신규 API/lookup 동작에 맞춘 기대값만 갱신했다.
- PostgreSQL 비파괴 스크립트 **11개 항목 통과 / 0 실패**: 전체 Snapshot·후보·RCCP·MRP·출처 roundtrip, Decimal/null 보존, 대역 격리, 부모/What-if 계보, 중복 UNIQUE, scenario CHECK, 원본 불변, 검토/반려·오래된 버전 충돌·미인증 승인 차단·감사 append-only, 중간 저장 오류 rollback, FK, 두 연결 advisory lock, 실제 API 501/빈 이력. 검증 중 대역 기록은 모두 rollback했다.
- TypeScript·Vite 빌드·OpenAPI/Schema/응답 예시 동기화·의존성·보안·문서 링크 검사 통과. 실제 계획은 0건이며 기존 승인 배치 7개와 기존 업무 테이블 행 수를 보존했다.
- **미실행:** 초기화 DB pytest 55개, migration downgrade/왕복, 브라우저 E2E, 두 HTTP 최종 승인 요청의 완전한 병렬 경합, 실제 인증 성공 및 실제 엔진 기반 정식 Excel 발급. 잠금 primitive/오래된 버전 검증을 전체 병렬 승인 E2E로 표현하지 않는다.

구현 파일: backend/app/plans/{repository,service,approval,exports}.py, backend/app/api/plan_executions.py, contracts/interfaces/plan_execution.py, 신규 0007, backend/tests/test_plan_executions.py, scripts/verify_plan_storage.py. 공통 어댑터·라우터·오류·계약 생성기와 팀 문서를 함께 갱신했다. 소유권 경계와 기존 Preview/DEMO는 유지했다.
