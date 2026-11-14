# CAPA·Routing 데이터 사전 — 등록 구현 v1

2026-11-15. 저장·검증·승인 계약이며 MPS/RCCP/MRP/What-if 계산 정책은 아니다. 모든 기준 시드는 **SYNTHETIC / TISSUE-CAPACITY-BASE-01**, 통합 검증용 고정값이며 실제 제조기업 측정값이나 이희원의 정식 계산 데이터셋이 아니다.

## 공식 설계 근거와 단순화

- [Microsoft Dynamics 365 Routes and operations](https://learn.microsoft.com/en-us/dynamics365/supply-chain/production-control/routes-operations): Route·Operation·자원 요구·setup/run time·버전 개념을 참고했다. 충파모는 하나의 공정에 여러 자원 소요를 연결하며 작업 일정이나 병목 계산을 구현하지 않는다.
- [SAP Work Center and Routing](https://learning.sap.com/courses/applying-business-processes-in-production-planning-and-manufacturing-operations/work-center-and-routing_c518340f-3688-4656-b74b-81372ed62925): 작업장·설비/인력·가용시간과 공정의 구분을 참고했다. SAP의 일정/비용 공식을 충파모 계산식으로 채택하지 않는다.
- [Odoo 19 Work Centers](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/advanced_configuration/using_work_centers.html): 요청받은 근무시간·효율·대체 작업장 참고 링크다. 이번 확인에서 페이지 조회가 반복 timeout되어 본문 검증은 미완료다. 효율·대체설비 공식을 확정하는 근거로 사용하지 않았다.

이 문서의 컬럼명·정밀도·수치는 위 ERP와 동일한 스키마가 아니다. 달력·효율·대체설비·셋업 정책 저장 및 계산은 미구현이다.

## 파일·승인 단위

예제 위치: [tissue_capacity](../contracts/examples/tissue_capacity/README.md).

- `entity=capacity`: resources / quantity_limits / hours_budgets 중 하나 이상의 시트를 **전부 함께** 검증·승인. CSV는 헤더로 구분한다. 부분 시트 승인은 지원하지 않는다.
- `entity=routing`: routing_steps 시트의 전체 공정·자원 요구량을 원자 승인한다. 제품과 자원은 선행 승인돼 있어야 한다.
- 모든 시트가 든 `tissue_capacity_template.xlsx`는 전체 입력 양식이다. 승인에는 `capacity_upload.xlsx`와 `routing_upload.xlsx`를 순서대로 사용한다. 전체 양식을 capacity로 보내 Routing까지 묵시적으로 승인하지 않는다.
- 컬럼명은 아래 영문과 일치해야 한다. 모호한/누락 헤더는 MAPPING_HOLD, 행·참조·정책 오류는 HAS_ERRORS. `column_overrides`는 기존 API의 `{표준필드: 원본헤더}`로 지정한다. 누락 값은 원본을 수정해 새 파일로 올린다.
- `predecessor_step_ids`, `resource_requirements`는 CSV 셀 안의 JSON 배열. XLSX에서도 JSON 문자열이다. 빈 선택 셀은 null이며 0과 구별한다. 숫자는 10진 문자열로 검증하고 NUMERIC(20,6)에 저장한다. 자동 단위 환산이나 float 계산은 없다.

## 컬럼 정의

모든 코드: 1~40자 영문/숫자로 시작, 이후 영문/숫자/`_.-`. 월: YYYY-MM, 날짜: ISO YYYY-MM-DD. 정수부 최대 14자리, 소수 최대 6자리 비음수 문자열. 참조수량과 run_time은 양수.

| 묶음 | 컬럼 | 필수·타입 | 단위·의미·예시 및 검증 |
|---|---|---|---|
| resources | resource_id | 필수 Code | M1, 중복/기존 코드 재등록 금지 |
| resources | resource_name | 필수 text | 합성 포장기; 빈 이름 거부 |
| resources | kind | 필수 enum | WORKCENTER / LABOR_POOL / EQUIPMENT / EQUIPMENT_POOL |
| resources | time_basis | 필수 enum | ELAPSED / PERSON_HOUR / MACHINE_HOUR |
| resources | parallel_units | 필수 integer≥1 | L1=2; 가용 인시를 다시 곱하는 계산 근거가 아님 |
| quantity_limits | capacity_id | 필수 Code | Q-TP; (ID, 월) PK |
| quantity_limits | product_id | 필수 Code | 승인 TP-10R; FK product |
| quantity_limits | period | 필수 Month | 2027-01 |
| quantity_limits | limit_qty | 필수 Decimal | 10500; 명시적 0 허용 |
| quantity_limits | unit | 필수 Code | EA=10롤 1팩, 승인 제품 기본 단위와 일치 |
| quantity_limits | accounting_point | 필수 enum | FINISHED_OUTPUT / OPERATION_OUTPUT |
| quantity_limits | operation_id | 조건부 Code | OPERATION_OUTPUT에 필수. 공정 범위 정책 미확정이므로 현재 서비스는 OPERATION_OUTPUT 등록 거부 |
| hours_budgets | capacity_id | 필수 Code | H-M1; (ID, 월) PK |
| hours_budgets | resource_id | 필수 Code | 승인 자원 FK. 같은 capacity 배치의 자원도 함께 승인 가능 |
| hours_budgets | period | 필수 Month | 자원·월 유일 |
| hours_budgets | regular_hours | 필수 Decimal | M1=160, L1=170 |
| hours_budgets | overtime_hours_limit | 선택 Decimal/null | 20; null은 미제공이지 0이 아님 |
| hours_budgets | unit | 필수 enum | h / min; 정규·잔업 모두 같은 단위 |
| hours_budgets | time_basis | 필수 enum | 자원 마스터 의미와 일치 |
| hours_budgets | availability_basis | 필수 enum | GROSS / NET, 임의 차감·효율 환산하지 않음 |
| hours_budgets | calendar_ref | 선택 Code/null | 달력 승인 마스터 미구현, 값이 있으면 현재 거부 |
| routing_steps | routing_id / routing_version / step_id | 필수 Code | RT-TP / V1 / PACK, 복합 PK |
| routing_steps | product_id | 필수 Code | 버전별 제품 하나, 승인 제품 FK |
| routing_steps | operation_id | 필수 Code | PACK. 별도 글로벌 공정 마스터 대신 버전 내 공정 식별 |
| routing_steps | predecessor_step_ids | 필수 Code[] | `[]`; 같은 버전의 실제 step 참조, DAG 순환 거부 |
| routing_steps | valid_from / valid_to | 필수 date / 선택 date | 2025-01-01 / null; 양 끝 포함, 종료≥시작 |
| routing_steps 및 추가 요구량 | resource_id | 필수 Code | M1 또는 L1, 승인 자원 FK |
| 위와 같음 | reference_qty / quantity_unit | 필수 Decimal / Code | M1:60 EA, L1:1000 EA; 승인 제품 단위와 일치 |
| 위와 같음 | run_time / time_unit | 필수 Decimal / enum | M1:1 h, L1:18 h |
| 위와 같음 | time_basis | 필수 enum | M1 MACHINE_HOUR, L1 PERSON_HOUR; 자원과 의미 일치 |
| 위와 같음 | concurrent_units | 조건부 integer≥1 | ELAPSED에 필수, 집계 인시/설비시간이면 null |
| 위와 같음 | setup_time / setup_policy_ref | 선택 Decimal / Code | 명시적 0에도 정책 필수. 정책 마스터 미구현으로 현재 정책 참조 포함 등록 거부 |
| 위와 같음 | alternative_group_ref | 선택 Code | 대체 자원 정책 미확정, 현재 값 있으면 거부 |
| routing_steps | resource_requirements | 선택 ResourceRequirement[] | 기본 `[]`, 기존 주 자원 외 **같은 공정의 동시 추가 소요** |

기존 RoutingStep의 단일 주 자원 필드를 보존하고 `resource_requirements`를 추가했다. PACK의 M1은 60 EA당 1 설비시간, 추가 L1은 1000 EA당 18인시(0.018인시/EA)다. 선행 공정이나 별도 순차 공정이 아니며 시간 합산·최대값·자원 배정·일정 공식은 결정하지 않았다. L1의 170은 총 인시이며 parallel_units=2로 다시 곱하지 않는다.

## 실제 PostgreSQL 구조

Alembic **0006**, 기존 0001~0005 원문 보존. 신규 여섯 테이블:

| 테이블 | 실제 컬럼 |
|---|---|
| production_resource | resource_id, resource_name, kind, time_basis, parallel_units, batch_id, payload |
| production_quantity_limit | capacity_id, product_id, period, limit_qty, unit, accounting_point, operation_id, batch_id, payload |
| production_hours_budget | capacity_id, resource_id, period, regular_hours, overtime_hours_limit, unit, time_basis, availability_basis, calendar_ref, batch_id, payload |
| production_routing | routing_id, routing_version, product_id, valid_from, valid_to, batch_id |
| production_routing_step | routing_id, routing_version, step_id, product_id, operation_id, valid_from, valid_to, batch_id, payload |
| production_routing_resource_requirement | routing_id, routing_version, step_id, resource_id, reference_qty, quantity_unit, run_time, time_unit, time_basis, concurrent_units, setup_time, setup_policy_ref, alternative_group_ref, is_primary, batch_id |

모든 테이블의 batch_id는 import_batch FK다. 제품 FK·자원 FK·routing→step→requirement 복합 FK를 유지한다. 주 자원과 추가 자원은 requirement 테이블에 각각 한 행 저장한다. payload는 검증된 DTO 원본으로 배열·날짜·소수 문자열의 재현용이며 relational 열은 참조·제약용이다.

기존 승인 트리거를 확장해 matching entity·같은 승인 트랜잭션에서만 INSERT 가능하고 업무 행 UPDATE/DELETE는 금지한다. deferred 행 수 대조는 CAPA의 세 묶음 합계, Routing의 공정 수와 공정별 자원 요구 행 수를 확인한다. 승인 count에 파생 routing 헤더/requirement 행을 중복 합산하지 않는다.

DB는 PK/FK·enum·양수/비음수·유효기간·월별 자원 유일·제품/월/회계점 유일·제품별 라우팅 유효기간 배타성을 강제한다. 기간은 양 끝 포함이며 연속 버전은 1/15 종료 → 1/16 시작으로 등록한다. 겹치는 대체 라우팅은 현재 보수적으로 거부하며 운영 최적화 정책을 의미하지 않는다. DAG·제품 단위·집계 시간 의미·셋업 정책·버전 내 기간 일치는 서비스에서 검증한다.

## 승인·조회·계획 입력

기존 `POST /batches`, `GET /batches`, `GET /batches/{id}`, `POST /batches/{id}/revalidate|approve|reject`를 재사용한다. 승인에는 서버 `result_digest`를 `expected_result_digest`로 되돌려 보내고, 재검증에는 서버 version을 사용한다. 경합 시 409, 입력 422, 저장 비활성 501, DB 불가 503. 승인 직전 원본 재파싱·참조 재검증·행 잠금·결과 지문 비교와 전체 rollback을 유지한다. 서로 다른 CAPA/Routing 승인도 advisory transaction lock으로 직렬화한다.

`GET /capacity`와 `GET /routings`: limit(1~1000)/offset, items/total/limit/offset. items는 section/payload/batch_id/version/result_digest/source_sha256/approved_at를 반환한다. 현재 제품·월 필터는 없으며 조회된 전체 승인 자료에서 provider가 요청 범위를 선택한다.

PlanningSourceProvider는 같은 REPEATABLE READ·READ ONLY 트랜잭션 안에서 승인된 CAPA와 요청 제품·월에 겹치는 모든 Routing 버전을 읽는다. 원본 배치 ID·승인 version·SHA·digest를 approved_inputs.sources에 추가한다. null 잔업·개별 제약·설비/인시 구분을 보존한다. 월중 버전을 임의로 하나 선택하지 않고 `ROUTING_VERSION_POLICY_REQUIRED`를 남긴다. 미등록은 CAPACITY_NOT_REGISTERED/ROUTING_NOT_REGISTERED, 자료 누락은 coverage, 계산 정책은 POLICY_NOT_CONFIRMED로 남는다. 계획 알고리즘 501과 What-if 기준 계획 미구현은 유지된다.

## 실행·확장

전용 `chungpamo-monorepo`, 127.0.0.1:55433, 개발 DB chungpamo만 대상으로 한다. 테스트 DB 초기화는 이 작업에 허용되지 않았다. 원격 개발·기업 데이터가 발견되면 시드를 중단한다.

```powershell
# 대상 확인 후 신규 비파괴 migration만 적용. 개발 DB를 초기화하지 않음.
cd backend
../.venv/Scripts/python.exe -m alembic upgrade head
cd ..
./.venv/Scripts/python.exe scripts/seed_tissue_capacity.py
./.venv/Scripts/python.exe scripts/verify_capacity.py
```

seed는 Docker/DB 대상을 재검증하고 기존 배치 SHA가 같으면 재사용한다. 같은 entity에 다른 원본·비합성 자료가 있으면 중단한다. 기존 자료를 삭제·승인 상태 조작하지 않는다. verify는 실제 승인 수요 예측 1건을 생성/재사용하고 신규 오류 탐침은 외부 트랜잭션 rollback으로 제거한다. 두 스크립트는 DB 초기화를 하지 않는다.

희원은 독립 계산 fixture로 예제 JSON을 확장한다. 승인 자원·제품을 새 코드로 먼저 등록하고 새로운 월/겹치지 않는 버전으로 후속 업로드한다. 승인본 교체/수정은 지원하지 않는다. 단위·셋업·대체설비·공유 자원·목적함수·최종 승인 정책의 변경은 H-/N- 결정 후 김대영에게 계약 변경을 요청한다. 프론트 타입·신규 entity 업로드 UI는 정마나미의 후속 작업이며 이번에는 수정하지 않았다.
