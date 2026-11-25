# C02 승인 예정 입고 조회 API 구현 계획

2026-11-25 (KST) · 담당 김대영 · 기준 [`7ed160f`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/7ed160fe19b11774fffe76f666e529798a44d2a6)

2026-11-25 기준 코드 구현 및 비DB 검증이 완료됐다. 실제 PostgreSQL 검증은 메인 PC에서 진행한다. 아래는 구현 전 수립한 범위와 인수 기준이다. [프론트엔드 인계 및 응답 예시](FRONTEND_BACKEND_CONTRACT_FOLLOWUP_20261125.md#c02-승인-입고-원장-읽기-api-설계) · [메인 PC 실DB 절차](PLANNING_POSTGRESQL_INTEGRATION_VERIFICATION_20261124.md#c02-읽기-api--메인-pc-실db-검증)

## 재사용할 코드

| 구성 | 현재 위치와 역할 | 적용 계획 |
| --- | --- | --- |
| 데이터셋과 저장소 | `dataset_context`와 `get_dataset_engine`이 등록·활성 상태를 확인하고 현 데이터셋의 SQL 스키마를 선택한다. `SqlBatchRepository`는 배치 등록·승인 트랜잭션을 제공한다. [라우터 의존성](../backend/app/api/datasets.py) · [데이터셋 엔진](../backend/app/datasets.py) · [배치 저장소](../backend/app/batches/sql_repository.py) | 스코프 해석과 엔진을 재사용한다. 조회는 계획 provider의 읽기 전용 트랜잭션 패턴을 따른다. |
| 원장 SQL | `APPROVED_RECEIPTS`가 배치 ID·데이터셋 조인, 승인 상태·오류·승인 출처를 검증한다. `installed`는 0009의 공급 미연결과 스키마 정합성 오류를 구분한다. `read_approved_receipts`는 기준일별 최신 승인 개정을 읽는다. [승인 규칙](../backend/app/batches/receipts.py) · [계획 reader](../backend/app/integrations/planning_receipts.py) · [계획 provider](../backend/app/integrations/planning.py) | 승인 조건과 기준일별 최신 개정 선택을 공유한다. 쓰기 전 개정 검증의 `_current`와 계획 기간·입고 투영은 기존 경로에 둔다. |
| DTO와 물리 스키마 | `ReceiptRevisionInput`은 업로드 계약이다. 내부 `ReceiptLedgerRow`는 계획 공급에 필요한 행만 읽고 `po_id`에 `receipt_key`를 담는다. 0010 원장은 발주·라인·개정과 원본 행 출처를 이미 저장한다. [등록 DTO](../contracts/interfaces/receipts.py) · [0010 테이블 정의](../backend/app/dataset_schema_v3.py) | 공개 응답에 `receipt_key`와 원본 `po_id`, `po_line_id`를 각각 전달할 DTO를 추가한다. 기존 DTO의 의미와 저장 구조를 유지한다. |

## 구현 순서

1. **조회 계약** — `contracts/interfaces/receipts.py`에 공개 행·출처·페이지 DTO를 추가한다. 페이지는 `source_state`로 구분하고, 정상 빈 원장은 `items: []`, `total: 0`, 0009 미연결은 `items: null`, `total: null`, `reason_code: "RECEIPT_SOURCE_UNAVAILABLE"`로 표현한다. 저장 상태 `ledger_status`와 조회 상태 `state`를 구분한다. 취소, 전량, 일부, 미입고 순으로 분류하고 취소·완료의 잔량은 `"0"`이다. 수량을 10진 문자열로 전달한다.
2. **SQL reader** — 백엔드 입고 조회 reader에서 공통 승인 조인과 `effective_date <= :as_of` 조건을 사용한다. `receipt_key`별 최대 개정을 선택한 뒤 바깥 쿼리에서 발주·자재·표시 상태 필터를 적용한다. `receipt_key`로 정렬하고 페이지 전 전체 건수를 별도 집계해 범위 밖 offset에서도 총건수를 유지한다. 두 쿼리는 동일한 데이터셋 스코프의 `REPEATABLE READ` 읽기 전용 트랜잭션에서 실행한다. 모든 필터 값은 바인딩한다. 기존 제약과 인덱스로 시작한다.
3. **API와 출처** — `backend/app/api/`에 GET 라우터를 추가하고 `main.py`에 등록한다. 필수 `as_of_date`, 선택 `po_id`·`material_id`·`state`, 기본 `limit=50`(1–100)·`offset=0`를 검증한다. 배치 ID·원본 파일명·파일 SHA·결과 digest·승인 시각·원본 시트·행 번호·행 SHA만 출처로 투영한다. 404·409 데이터셋 오류, 422 입력 오류, 501 저장 비활성, 503 저장소 연결 실패, 500 스키마 불일치를 기존 오류 형식으로 매핑한다. 조회 행의 효력일을 기준으로 선택하며 승인 시각은 감사 정보로 제공한다.
4. **계약 동기화** — `backend/generate_api_examples.py`와 `backend/export_contract_schema.py`의 생성 경로에 조회 응답과 합성 예시를 연결한다. 연결된 원장, 정상 빈 원장, 공급 미연결을 모두 문서화한다. What-if 입력은 계속 부모 계획 스냅샷의 입고 키를 검증한다. [API·스키마 생성](../backend/generate_api_examples.py) · [공통 DTO 내보내기](../backend/export_contract_schema.py)

## 검증 순서와 인수 기준

| 범위 | 검증 항목 |
| --- | --- |
| 비DB reader 회귀 | [입고 SQL 대역 테스트](../backend/tests/test_scheduled_receipts.py)를 활용해 데이터셋·효력일 바인딩, 승인 조인, 상태 필터의 개정 선택 이후 적용, 동일 읽기 스냅샷의 목록·건수 집계를 검증한다. 기준일 당일 포함, 미래 효력일 제외, 최신 취소가 이전 OPEN을 숨기는 사례, 부분·완료 잔량, 페이지 경계와 원본 출처를 포함한다. |
| 비DB API·계약 | TestClient 대역에서 정상 빈 원장과 미연결, 422·404·409·501·503·500, 같은 입고 키가 있는 데이터셋 격리, 페이지·출처 응답과 원본 바이트 비노출을 확인한다. OpenAPI·생성 예시·JSON Schema 동기화와 전체 `pytest --no-db`를 실행한다. [API 예시 회귀](../backend/tests/test_frontend_fixtures.py) · [스키마 회귀](../backend/tests/test_contract_schema_sync.py) |
| 메인 PC의 별도 실DB 검증 | 0009에서 공급 미연결, 0010에서 빈 원장 및 승인 데이터 조회, 동일 키의 스키마 격리, GET 전후 업무 행 수·지문 일치를 실제 SQL로 대조한다. 합성 승인 개정 시드가 필요하면 별도 승인 후 전용 회귀 DB에서만 준비한다. 기존 CSV 출처 수정 후 승인 반영·부모 What-if 재검증의 완료 여부를 별도로 기록한다. [기존 실DB 테스트](../backend/tests/test_db_scheduled_receipts.py) · [P3 결과 및 P4 조건](PLANNING_POSTGRESQL_INTEGRATION_VERIFICATION_20261124.md#p3--회귀-postgresql-0010-적용과-c02-승인-결함-확인) |
