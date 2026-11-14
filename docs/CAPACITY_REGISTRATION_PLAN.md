# CAPA·라우팅 등록 뼈대 — 검토용, 미구현 API

> **2026-11-15 구현 갱신:** 아래 본문은 초기 설계 기록이다. 현재 `entity=capacity|routing`의 기존 배치 업로드·재검증·승인·반려와 `GET /capacity`, `GET /routings`, 신규 Alembic 0006 및 승인 PlanningInput 스냅샷이 구현됐다. 현재 계약·컬럼·제한·등록 절차는 [데이터 사전](CAPACITY_ROUTING_DATA_DICTIONARY.md)이 우선한다. 미확정 계산 정책은 여전히 미확정이다. CAPA UI와 계산 엔진은 이 작업에 포함하지 않았다.

기존 승인 흐름은 재사용할 수 있지만 **entity 문자열만 추가해서는 안 된다**. BatchService/pipeline, 저장소 DTO·SQL, import_batch entity CHECK, 행 수/deferred trigger, 원본 보관, 승인 단위·참조 조회, UI 타입을 함께 검토해야 한다. 현재 `/batches`는 제품·자재·BOM·재고·수요 다섯 종류만 지원한다. 이번에는 DB/마이그레이션을 변경하지 않았다.

## 구조 검증 가능한 초안 DTO

`contracts/interfaces/capacity.py`의 CapacityRegistrationDraft, 버전 capacity-registration-0.1-draft. 예시는 contracts/examples/integration/capacity_registration.json의 payload다. 합성 자료이며 승인된 DB 자료가 아니다.

| 묶음 | 필수 필드 | 선택·조건부 필드 | 단위·검증 |
|---|---|---|---|
| resources | resource_id/name, kind, time_basis, parallel_units≥1 | 없음 | WORKCENTER/LABOR_POOL/EQUIPMENT/EQUIPMENT_POOL. 물리 동시 수를 모르면 임의로 1을 채우지 않음 |
| quantity_limits | capacity_id, product_id, period, limit_qty, unit, accounting_point | OPERATION_OUTPUT이면 operation_id | 월 YYYY-MM, 명시 0과 행 부재 구별, (capacity_id,period) 중복 금지 |
| hours_budgets | capacity_id, resource_id, period, regular_hours, unit, time_basis, availability_basis | overtime_hours_limit, calendar_ref | h/min, ELAPSED/PERSON_HOUR/MACHINE_HOUR와 GROSS/NET 구분. 미입력 잔업은 0이 아님 |
| routing_steps | routing_id/version, step_id, product_id, operation_id, resource_id, predecessor_step_ids, reference_qty, quantity_unit, run_time, time_unit, time_basis, valid_from | valid_to, setup_time/policy_ref, alternative_group_ref, concurrent_units | 수량·시간 >0. ELAPSED에는 투입 수 필수, 이미 집계한 인시/설비시간에는 다시 곱하지 않음 |
| unresolved_policy_refs | 없음 | 미확정 정책 코드 목록 | 실행 가능한 계산 정책이나 승인 증명이 아님 |

ID/단위 코드는 1~40자, 10진 값은 비음수 문자열(정수부 최대 14자리·소수 최대 6자리의 신규 초안)이다. run_time/reference_qty는 양수다. 기존 data_contract_v1의 수량/DB 정밀도를 바꾸지 않았으며 신규 저장 정밀도는 추후 계약 확정 때 검토한다.

DTO는 자원 참조/시간 의미 차원/라우팅 버전별 제품 단일성/선행 공정 참조·순환/유효기간 역전/중복 키/셋업 정책 근거를 검사한다. check_approved_products는 승인 제품 집합과의 대조 지점이다. 단위 환산표·공정/달력 마스터·승인 출처·기간 coverage·동시성의 실제 검증은 등록 서비스 연결 후 필요하다. DTO 통과를 READY_FOR_APPROVAL로 표현하지 않는다.

## 미래 API 명세 제안 — 아직 라우터에 등록하지 않음

1. `POST /batches`에 entity=capacity 또는 routing을 **새 계약 버전에서** 추가한다. filename/raw SHA/source_type/source_note는 기존 원본 보관 절차를 따른다.
2. 매핑 불명은 MAPPING_HOLD, 구조/참조 오류는 HAS_ERRORS. 제품·자원·공정 마스터·기간·단위가 확인돼 오류 0일 때만 READY_FOR_APPROVAL.
3. `POST /batches/{id}/revalidate`는 서버 version을 그대로 사용하고, 승인/반려는 기존 result_digest와 명시적 역할 코드를 유지한다. 409 충돌/결과 변경을 무시하지 않는다.
4. 승인 데이터 조회용 `GET /capacity` / `GET /routings`는 경로 후보다. 페이지·기간·제품·자원 필터, 원본 배치/버전·검증 지문·승인 시각을 제공해야 한다. 아직 endpoint가 있다고 사용하지 않는다.
5. 별도 신규 migration에서 제약·FK·승인 transaction gate·행 수 대조·원본 append-only를 설계한다. 기존 0001~0005를 다시 쓰지 않는다. migration 적용·테스트 DB 초기화는 별도 승인 대상이다.
6. 김대영의 PlanningSourceProvider가 승인 스냅샷을 읽도록 연결한다. client JSON의 APPROVED 선언, 미승인 행, 다른 기간 자료를 우회 입력으로 쓰지 않는다.

resource와 routing을 어떤 배치 단위로 등록할지, resources를 별도 entity로 분리할지는 미결정이다. 한 파일 여러 시트의 원자 승인/부분 승인 정책도 팀 결정이 필요하다.

## 이희원과 확인할 계산 규칙

- 여러 CAPA의 동시 적용/강도/필수 제약과 공유 자원 부하 합산·배분.
- 경과시간·인시·설비시간, 달력/순가용/효율의 권위 출처와 중복 차감 방지.
- 셋업 횟수·묶음·교체 기준, 대체/병렬 설비, 공정 선후·재작업 지원 범위.
- 월중 버전·반올림·허용 오차, 미입력 시간/재고/안전재고의 거부 또는 UNVERIFIED 처리.
- 기준형·안정형·비용형의 목적함수·KPI·비용 입력, 최종 FEASIBLE 판단 범위.

정마나미와는 필수/선택 CAPA UI, 부족 자료 표시·수동 보완, 비교 기준, UNVERIFIED 예외 승인 가능 여부를 따로 확인한다. 기존 multi_capacity_decision_questions.md의 H-/N- 결정 기록을 재사용한다.

## 후속 테스트 계획

현재 비DB 시험: 독립 수량/인시/설비시간 보존, 중복/알 수 없는 자원/의미 차원 불일치/선행 순환/0 소요/근거 없는 셋업/ELAPSED 투입 수 누락 거부, 승인 제품 집합 대조.

등록 구현 후: 매핑 HOLD→수정→재검증→승인, 제품/자원/공정/달력 승인 순서, 미승인 조회 차단, 기간 겹침·coverage 누락, 단위 환산·집계 인시 24h 오적용 방지, 공유 설비의 복수 제품 사용량, 버전/digest 충돌·동시 승인·전체 rollback, 입력 스냅샷 재현성, UI 실제 API·새로고침 복원. PostgreSQL 시험은 전용 테스트 DB 식별·별도 승인 후 수행한다.
