# XLSX 선택 범위 저장·승인 인계

2026-11-23 KST. 기준 `main`은 [`423c456`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/423c456cf11d090866293c0812c78d6cd7bb81e2)다. 기존 합성 판매 월수요 변환 정책으로 사용자가 고른 XLSX 범위를 명시적으로 저장할 수 있다. 저장 결과는 변환 이력과 승인 전 월수요 배치다. 다른 엔터티의 직접 XLSX 업로드는 기존 `/batches` 경로를 사용한다. [시트·범위 선택 UI](XLSX_TABLE_SELECTION_HANDOFF.md)

## 미리보기와 저장 요청

`POST /ingest/transform-preview?dataset_id=CHUNGPAMO-2027`와 `POST /ingest/transformations?dataset_id=CHUNGPAMO-2027`에 같은 `files` 순서, `policy`, `use_approved_master`와 범위를 보낸다. `policy.columns`는 사용자가 확인한 이름 또는 선택 범위 안의 원본 열 문자다. `policy.dataset_id`는 query와 같아야 한다.

| multipart 필드 | 요청 형식 |
| --- | --- |
| `files` | 원본 File을 키마다 한 개 첨부한다. 같은 원본 바이트를 한 요청에 두 번 넣으면 거부한다. |
| `policy` | `SalesTransformPolicy` JSON 문자열. 저장에는 `user_confirmed=true`가 필요하다. `columns`에는 주문일·제품·수량·단위·상태·주문번호·행번호가 필요하다. |
| `table_selection` | 첨부가 정확히 한 개일 때 `XlsxTableSelection` JSON 문자열. 아래 예시를 참고한다. |
| `table_selections` | 선택 범위가 해당하는 `files`의 0부터 시작하는 인덱스를 키로 한 JSON 문자열. `{"1":{…}}`이면 두 번째 파일에만 적용한다. 예를 들어 첫 CSV는 기존 파싱을 사용하고 다음 XLSX는 범위를 사용한다. |
| `expected_result_digest` | 저장 전용. 방금 검토한 미리보기 `result_digest`를 그대로 보낸다. |
| `created_by`, `source_note` | 저장 전용. 기존 역할 코드와 합성 자료 출처 설명이다. |

두 선택 필드는 한 요청에 함께 보내지 않는다. 단일 선택은 인덱스 `0`의 선택과 같은 입력으로 계산된다. 명시한 필드의 빈 값, 중복 입력, 첨부 범위 밖 인덱스는 `XLSX_RANGE_INVALID`다.

```json
{
  "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "sheet": "1월 판매 내역",
  "header_row": 4,
  "data_start_row": 6,
  "data_end_row": 120,
  "first_col": 3,
  "last_col": 9
}
```

SHA는 구조 미리보기 응답에서 가져온다. 위 선택의 열이 순서대로 일치한다면 `policy.columns`를 `{"order_date":"C","product_id":"D","quantity":"E","unit":"F","status":"G","order_id":"H","line_id":"I"}`로 지정할 수 있다. 여러 파일에 한 정책을 쓰므로 역할별 참조가 각 선택/기본 표에서 같은 의미인지 확인한다. `sources[].resolved_columns`의 값과 `records[].source_locations[]`를 결합해 원본 위치를 표시한다. 예를 들어 `quantity=5`, `sheet="1월 판매 내역"`, `row=6`이면 E6이다. 기존 응답과 같이 그룹당 최대 5개 행 위치를 제공한다.

## 버튼 상태와 성공·오류 처리

- 저장 버튼은 정책 확인, `TRANSFORMED_PREVIEW`, `issues_total=0`, `total>0`, 현재 원본·선택·매핑·데이터셋과 미리보기 일치, 검토자·출처 입력 조건을 만족할 때 활성화한다. `persisted=false`는 미리보기 상태다. 파일(순서 포함), 범위, 컬럼 매핑, 정책 또는 데이터셋/승인 마스터 옵션 변경 시 이전 미리보기·지문을 폐기한다. 파일/시트/헤더/열이 바뀌면 해당 매핑 선택도 초기화한다. 늦게 도착한 응답은 현재 선택과 대조한다.
- `201`은 새 변환 이력과 승인 전 배치, `200`은 같은 입력과 설정으로 이미 저장된 이력이다. `transformation_id`, `batch_id`, `batch_status`를 읽는다. 중복 재시도는 최초 저장의 검토자·출처를 보존한다. `GET /ingest/transformations/{transformation_id}`의 `preview.sources[]`에서 선택 범위와 `resolved_columns`를 확인한다. 목록은 메타데이터만 반환한다. 데이터셋 query는 저장과 조회에서 유지한다.
- `409 XLSX_SOURCE_CHANGED`는 파일이 달라진 경우다. 새 파일의 구조를 확인한다. `409 RESULT_CHANGED`는 원본·선택·정책·승인 마스터 또는 지문이 검토한 결과와 다른 경우다. 새 미리보기와 확인이 필요하다. `422 XLSX_RANGE_INVALID`, `XLSX_SHEET_INVALID`, `XLSX_MERGED_RANGE`, `XLSX_HEADER_INVALID`는 선택 수정, `422 TRANSFORM_MAPPING_HOLD`는 필수 컬럼 매핑 수정이 필요하다.
- `409 TRANSFORM_BLOCKED`는 미확인 정책, 오류 또는 정상 월수요가 빈 경우다. 다른 선택은 별도 입력이지만 정규 월수요 CSV가 기존 활성 배치와 같으면 `409 DUPLICATE_UPLOAD`다. 다른 데이터셋의 이력/배치 UUID는 404다. 근거 검증이나 트랜잭션 실패는 기존 500을 반환한다.

## 저장 이후 배치 검증·승인

1. 반환된 `batch_id`로 `GET /batches/{batch_id}`를 조회한다. `HAS_ERRORS` 또는 `approval_blockers`가 비어 있지 않으면 승인 버튼을 비활성화한다. 승인 제품 등 기준정보를 수정·승인한 뒤 같은 배치를 재검증할 수 있다.
2. `POST /batches/{batch_id}/revalidate`에는 최신 `expected_version`과 `column_overrides={}`, `default_unit=null`, `sheet=null`을 보낸다. 선택을 바꾸려면 새 변환 미리보기와 저장을 사용한다. 재검증은 기존 범위 근거와 정규 CSV를 확인한다.
3. `POST /batches/{batch_id}/approve`에는 승인자 코드와 **배치 응답의 `result_digest`**를 보낸다. 변환 지문은 저장 검토에서 사용한다. 저장 자체로 수요는 공개되지 않는다. 업무 행은 기존 명시적 승인에서 반영된다. 변환 이력 및 원본은 승인·반려 후에도 보존한다.

[OpenAPI](../contracts/openapi.json) · [JSON Schema](../contracts/schemas/ingestion_assistance_v1.json) · [이력·검증 절차](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md)
