# 프론트엔드 통합 후속 계약

2026-11-25 KST · 보조 PC · 기준 [a4e2396](https://github.com/ChungPaMo/decision-supporter-mvp/commit/a4e2396c0250c537902bc89a25aa760ae2b2642d)

## 중복 파일과 승인 대상 확인

`POST /batches?dataset_id=CHUNGPAMO-2027`에서 반려되지 않은 동일 파일은 **같은 데이터셋·엔터티·원본 SHA-256**으로 식별한다. 파일 이름은 표시용이다. 새 파일과 이름이 같아도 내용이 다르면 별도 배치에 등록한다.

일반 중복과 고유 제약 경합은 모두 409 `DUPLICATE_UPLOAD`다. 경합 시 실패한 쓰기를 롤백한 뒤 같은 데이터셋의 새 트랜잭션으로 조회한다. 일치하는 활성 배치를 확인한 경우 다음 세부 정보를 제공한다. 경합 직후 배치가 반려됐거나 재조회에 실패하면 409 본문에서 `details`가 생략된다. [자동 생성 응답 예시](../contracts/examples/responses/16_error_duplicate_upload.json)

```json
{
  "detail": {
    "code": "DUPLICATE_UPLOAD",
    "message": "같은 파일이 이미 업로드되어 있습니다.",
    "details": {
      "batch_id": "00000000-0000-4000-8000-000000000010",
      "status": "READY_FOR_APPROVAL",
      "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "dataset_id": "CHUNGPAMO-2027",
      "entity": "monthly_demand"
    }
  }
}
```

파일을 선택한 흐름에서 화면은 브라우저에서 계산한 원본 SHA 또는 같은 파일의 파싱·업로드 응답에 있는 원본 SHA를 보관한다. 중복 응답의 ID로 동일 데이터셋의 `GET /batches/{batch_id}`를 호출한 뒤 파일 SHA와 현재 배치 상태를 대조한다. 세부 정보가 없거나 일치하지 않으면 선택을 해제하고 사용자에게 다시 확인하도록 안내한다. 이 경로에서 파일명으로 배치를 찾거나 중복 응답을 승인으로 간주하면 안 된다.

`POST /batches/{batch_id}/approve?dataset_id=CHUNGPAMO-2027` 요청 예시

```json
{
  "approved_by": "REVIEWER-01",
  "expected_result_digest": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "expected_source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

`expected_source_sha256`는 기존 소비자를 위해 선택 필드다. 새 파일에서 시작한 개별·일괄 승인에서는 선택 원본의 SHA를 전송한다. 승인 대상 배치의 SHA를 복사하면 잘못 연결된 파일을 감지할 수 없다. 잘못된 형식은 422, 원본 불일치는 409 `BATCH_SOURCE_MISMATCH`, 검증 결과 불일치는 409 `RESULT_CHANGED`다. 서버는 배치 잠금 안에서 검사하며, 승인 가능 상태·검증 digest·저장 원본 재검증 및 승인 트랜잭션을 적용한다.

## 배치 재검증

`POST /batches/{batch_id}/revalidate?dataset_id=CHUNGPAMO-2027`에서 버전 4의 열 지정만 교체하는 요청이다.

```json
{"expected_version": 4, "column_overrides": {"demand_qty": "D"}}
```

- `sheet`와 `default_unit`을 각각 생략하면 잠긴 배치의 해당 설정을 유지한다.
- 해당 필드에 JSON `null`을 보내면 기존 제한이나 기본값을 지운다. 문자열은 새 값으로 교체한다.
- `column_overrides`의 전체 교체 계약은 유지된다. 기존 매핑을 보존할 때는 합친 전체 객체를 보내고, 모두 지울 때는 `{}`를 보낸다. 이 필드를 생략하면 이전과 동일하게 `{}`가 적용된다.
- 200 응답에서 최신 `version`, `settings`와 `result_digest`를 갱신한다. 409 `VERSION_CONFLICT`는 배치 재조회로 해결한다. 변환 결과의 설정 변경 차단과 승인·반려 후 재검증 차단은 유지한다.

## 계획 Preview·저장과 부모 범위

| 동작 | 경로 | 기간 |
| --- | --- | --- |
| BASE Preview | `POST /plans` | 생략 시 기존 단일 월 기본값 1. 화면에서 명시 |
| BASE 저장 | `POST /plan-executions` | 생략 시 3. 화면에서 예측이 실제로 덮는 기간을 명시 |
| WHAT_IF Preview | `POST /plans/what-if` | 생략 시 3. 부모 기간을 명시 |
| WHAT_IF 저장 | `POST /plan-executions` | 생략 시 3. 부모 기간을 명시 |

쿼리의 `dataset_id`를 모든 계획 요청과 상세 조회에서 유지한다. `horizon_months`는 정수 1~12이며 시작 월부터 연속된 개월 수다. 선택한 제품 각각에 대해 전체 계획 기간의 승인 예측이 있어야 한다. 예측이 1개월뿐이면 기간은 1이다. `/planning-inputs/preview`로 BASE 입력 범위를 점검할 수 있다.

1개월 BASE 요청 예시

```json
{
  "forecast_execution_id": "00000000-0000-4000-8000-000000000001",
  "product_ids": ["CP-GIFT-12"],
  "target_month": "2027-01",
  "horizon_months": 1,
  "as_of_date": "2026-12-31",
  "scenario": "BASE"
}
```

부모는 같은 데이터셋의 저장된 실제 실행이며 `COMPLETED` 또는 `PARTIAL`이어야 한다. 화면은 `GET /plan-executions/{execution_id}`의 `input_snapshot.command`에서 예측 UUID, 제품 집합, 시작 월, 기간과 기준일을 복사한다. 결과 표나 현재 선택에서 부모 범위를 다시 추정하지 않는다. `base_plan_execution_id`에는 예측 UUID나 후보 ID가 아닌 부모 실행 UUID를 쓴다. 화면에서 기본 비교 대상은 BASE로 지정한다. 이전 What-if 자체를 누적 편집하는 동작은 별도 계약 범위다.

```json
{
  "forecast_execution_id": "00000000-0000-4000-8000-000000000001",
  "product_ids": ["CP-GIFT-12"],
  "target_month": "2027-01",
  "horizon_months": 1,
  "as_of_date": "2026-12-31",
  "scenario": "WHAT_IF",
  "base_plan_execution_id": "00000000-0000-4000-8000-000000000010",
  "overrides": {"demand_multiplier": "1.05", "overtime_hours_limit.SAW1.2027-01": "80"}
}
```

Preview는 200 `{result, persisted: false, approval_available: false, …}`다. 저장 성공은 201 `{execution, reused: false}`, 동일 성공 실행 재사용은 200과 `reused: true`다. 기록 링크에는 `execution.execution_id`를 쓴다. 부모 범위 불일치는 409 `PLAN_INPUT_UNAVAILABLE`, 찾을 수 없는 부모나 예측은 404다. 잘못된 override는 422다. 일반 `detail` 오류 외에 Preview 422/500의 `result.errors`와 저장 422/500의 `execution.result_snapshot.errors`도 표시한다. 정식 계획 승인 게이트는 그대로 적용된다. [계획 계약 인계](PLANNING_CONTRACT_V04_HANDOFF.md#c03-what-if-계약)

## 서버 상태

`GET /health`의 HTTP 503은 서버에서 받은 응답이다. 다음 본문과 응답이 도달하지 못한 연결 오류를 화면에서 구분한다. 200에서는 `status: "ok"`와 `database.status: "ok"`, `database.server_version`이 제공된다.

```json
{"status": "degraded", "version": "0.1.0", "database": {"status": "unavailable"}}
```

## C02 승인 입고 원장 읽기 API 설계

**2026-11-25에 구현하고 TestClient와 SQL 대역으로 검증했다.** 새 조회의 실DB 검증과 0010 승인·부모 What-if 재검증은 메인 PC에서 진행한다. 등록은 기존 `POST /batches`의 `entity=scheduled_receipt`와 재검증·승인 경로를 이용한다. [메인 PC 실DB 검증 절차](PLANNING_POSTGRESQL_INTEGRATION_VERIFICATION_20261124.md#c02-읽기-api--메인-pc-실db-검증)

`GET /scheduled-receipts?dataset_id=CHUNGPAMO-2027&as_of_date=2027-01-05&limit=50&offset=0`로 호출한다. `as_of_date`는 필수 업무 효력일이다. 동일 데이터셋의 승인 원장 중 `effective_date <= as_of_date`인 행에서 `receipt_key`별 가장 큰 개정을 고른다. `approved_at`은 감사 시각이다.

- 요청은 기존 데이터셋 해석과 `get_dataset_engine`을 사용한다. 누락 시 기존 레거시 기본값이 적용되므로 화면은 데이터셋을 명시한다. 목록과 전체 건수는 같은 읽기 전용 스냅샷에서 읽는다. 안정 정렬은 `receipt_key`이며 `limit`은 1~100, 기본 50이다. 페이지 사이에 새 승인이 있으면 첫 페이지부터 새로 읽는다.
- 계획 reader와 동일한 `APPROVED_RECEIPTS`의 조인·필터 및 `installed` 스키마 확인을 재사용한다. 원장 조회는 계획 기간으로 필터링하지 않는다. 선택 필터 `po_id`, `material_id`, `state`는 최신 개정 선택 후 적용해 취소된 발주의 이전 OPEN 개정이 나타나지 않게 한다.
- `ledger_status`는 저장된 `OPEN` 또는 `CANCELLED`다. 표시용 `state`는 취소 우선, 다음으로 전량 입고 `COMPLETED`, 일부 입고 `PARTIALLY_RECEIVED`, 미입고 `OPEN`이다. `open_qty`는 OPEN·부분 입고의 `ordered_qty - received_qty`이고 취소·완료는 `"0"`이다. 수량을 10진 문자열로 전달한다.
- `receipt_key`는 발주 전체면 `po_id`, 행 단위는 `po_id--po_line_id`다. What-if의 `receipt_qty.<receipt_key>`에는 현재 조회 목록과 별개로 **저장된 부모의 적용 입고 스냅샷**에 있는 키만 사용한다.
- 출처에는 승인 배치 ID, 배치의 원본 이름·SHA와 결과 digest, 승인 시각, 시트, 원본 행 번호·SHA를 담는다. CSV 원장 출처의 `source_sheet`는 `"CSV"`이며 XLSX는 실제 시트명이다. 원본 파일 바이트는 반환하지 않는다.

요청·응답 예시는 합성 원장과 조회 대역으로 생성했다. 부분 입고 예시의 주문 `"1000.000000"`과 누적 입고 `"400.000000"`에서 잔량은 `"600.000000"`이다. 화면에서는 수량 문자열을 그대로 표시하거나 10진 연산을 사용한다. [연결된 원장](../contracts/examples/responses/43_scheduled_receipts_available.json) · [정상 빈 원장](../contracts/examples/responses/44_scheduled_receipts_empty.json) · [원장 미연결](../contracts/examples/responses/45_scheduled_receipts_unavailable.json) · [OpenAPI](../contracts/openapi.json)

| 상황 | 응답 |
| --- | --- |
| 0010에서 정상 조회했으나 해당 행 없음 | 200 `source_state: "AVAILABLE", reason_code: null, items: [], total: 0` |
| 0009에서 원장 미연결이 확인됨 | 200 `source_state: "UNAVAILABLE", reason_code: "RECEIPT_SOURCE_UNAVAILABLE", items: null, total: null` |
| 저장소 비활성 / DB 연결 실패 | 각각 501 `PERSISTENCE_DISABLED` / 503 `DB_UNAVAILABLE` |
| 스키마 불일치 또는 쿼리 정합성 실패 | 500 `PERSISTENCE_ERROR`. 정상 빈 원장으로 대체하지 않음 |
| 데이터셋 없음 또는 보관 상태 | 기존 404 `DATASET_NOT_FOUND` / 409 `DATASET_INACTIVE` |

화면에서는 `source_state`를 먼저 읽는다. `AVAILABLE`은 표와 페이지를 표시하며 `total=0`은 조회 조건에 맞는 건이 없는 상태다. `UNAVAILABLE`은 공급 원장 미연결로 표시한다. 500·503은 조회 실패 상태로 표시한다. 데이터셋·기준일·필터가 바뀌면 `offset=0`으로 다시 조회한다. 승인 직후에는 현재 조건으로 첫 페이지를 새로 요청한다. [조회 테스트](../backend/tests/test_scheduled_receipts_api.py)

## 이번 검증

보조 PC 전체 비DB pytest 1,384건 통과·69건 건너뜀. 계약과 생성물 집중 검사 12건 통과. 업로드·승인·경합 재조회는 메모리 저장소 및 SQL 드라이버 오류 대역으로, Health는 연결 대역으로 검증했다. 실제 PostgreSQL·Docker·외부 AI API는 미실행이다.
