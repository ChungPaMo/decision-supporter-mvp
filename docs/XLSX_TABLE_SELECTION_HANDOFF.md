# 엑셀 표 범위 선택 API 인계

2026-11-23 KST. 기준 `main`은 [`5002853`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/50028536a4af176306704be574409b142f10eaaf)다. 제목, 결재란, 표지와 반복 표가 있는 XLSX에서 사용자가 확인한 한 개의 표를 분류·컬럼 추천·프로파일·변환 미리보기에 전달한다. `table_selection`을 생략한 기존 경로는 기존 파싱을 사용한다.

## 화면 흐름과 요청 형식

1. `POST /ingest/xlsx-layout`에 원본 XLSX를 multipart `file`로 보낸다. `source_sha256`, 시트의 정확한 `name`, `visibility`, `max_row`와 `max_col`을 받는다. 시트 이름을 고르기 전 `window`는 `null`이다. `hidden`/`veryHidden`은 목록에 표시되며 미리보기와 분석에서는 선택할 수 없다.
2. 같은 원본을 다시 보내며 `sheet`, `row_start`, `row_limit`, `col_start`, `col_limit` query로 구조 창을 요청한다. 기본 창은 20행 × 16열, 최대 50행 × 32열이다. 워크시트 경계에서 창을 자른다. `window.cells`의 `row`/`col`, `kind`/`value`, `hidden_columns`, `merged_ranges`(최대 200개)를 사용한다. 표시 문자열은 최대 80자이며 이메일·전화 형태는 마스킹한다. 수식 셀은 `kind=formula`와 `value=null`로 표시한다. 일반 셀 문자열은 텍스트로 렌더링한다.
3. 사용자가 원본 좌표로 시트, 단일 헤더 행, 첫/끝 데이터 행, 첫/끝 열을 직접 지정한다. `table_selection` multipart 문자열에 아래 JSON을 넣고 같은 `file`을 첨부한다. 모든 좌표는 **원본 기준 1부터 시작하며 끝을 포함**한다. 예시는 3행 C~E 헤더와 4~22행 C~E 데이터를 선택한다. `source_sha256`은 목록 응답에서 받은 값을 사용한다.

```json
{
  "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "sheet": "자료",
  "header_row": 3,
  "data_start_row": 4,
  "data_end_row": 22,
  "first_col": 3,
  "last_col": 5
}
```

| API | 선택 필드와 결과 |
| --- | --- |
| `POST /classifications/file` | `table_selection`을 넣으면 선택한 표로만 추천하고 선택을 돌려준다. 기존 `sample_row_limit`의 기본은 0이다. |
| `POST /ingest/profile` | 선택 좌표·원본 SHA와 해당 표의 프로파일을 반환한다. `col`은 원본 열 번호다. |
| `POST /ingest/mapping-suggestions` | 기존 `entity`·`column_overrides`와 선택 좌표를 사용한다. `suggestions[].col`과 `existing_mapping` 값은 원본 열 번호다. `E`는 원본 5열을 가리킨다. |
| `POST /ingest/classified-mapping` | 같은 선택을 분류와 매핑에 적용한다. `classification.table_selection`과 매핑이 있을 때 `mapping.table_selection`을 확인한다. |
| `POST /ingest/transform-preview` | `files`의 0부터 시작하는 순서 번호를 키로 한 JSON 문자열 `table_selections`를 보낸다. 예를 들어 `{"0":{…},"2":{…}}`는 첫 번째와 세 번째 XLSX에만 적용한다. 선택 없는 파일은 기본 동작을 유지한다. 각 `sources[].table_selection`과 원본 SHA, 결과/오류의 원본 시트·행·열을 읽는다. |

파일, 시트, 헤더 위치 또는 범위를 바꾸면 이전 응답과 매핑 선택, 변환 지문을 폐기한다. 새 결과의 `table_selection`을 현재 상태와 대조한 뒤 표시한다. 같은 파일의 다른 범위를 선택해도 원본 SHA는 같고, 변환의 `input_digest`/`result_digest`에는 선택이 반영된다. 컬럼 참조는 선택된 헤더명 또는 선택 안에 있는 원본 열 문자다. 선택 안의 열 문자를 헤더명보다 먼저 해석한다.

## 범위 처리와 오류

- 한 요청에는 한 파일당 한 개의 연속 표 범위를 지정한다. 표가 여러 개면 하나씩 확인한다. 이어 붙이기와 BOM 반복 블록 결합은 후속 기능이다.
- 숨긴 열은 선택에 포함되면 원본 열 위치 그대로 처리한다. 병합 영역이 선택된 헤더 또는 데이터와 겹치면 오류다. 병합 그룹이 있는 표는 병합되지 않은 하위 헤더 행을 고른다.
- 빈 데이터 행은 건너뛰며 나머지 행 번호는 유지한다. 수식은 Excel이 저장한 캐시 값만 사용한다. 캐시가 없으면 빈 값으로 처리한다. 수식·오류 헤더는 거부한다. 필수 컬럼이 없으면 기존 매핑 HOLD 또는 변환 매핑 오류를 표시한다.
- 8개 시트, 64열, 시트당 100,000행, 전체 200만 셀, 업로드 10MiB, 펼친 ZIP 50MiB 한도를 적용한다.

| HTTP·코드 | 화면 처리 |
| --- | --- |
| 409 `XLSX_SOURCE_CHANGED` | 파일이 바뀌었다. 시트 목록과 범위를 다시 선택한다. |
| 422 `XLSX_SHEET_INVALID` | 정확한 이름의 보이는 시트를 선택한다. |
| 422 `XLSX_RANGE_INVALID` | 필수 범위, 행/열 순서, 빈 범위, 워크시트 경계 또는 변환 파일 인덱스를 확인한다. |
| 422 `XLSX_MERGED_RANGE` | 병합이 닿지 않는 하위 헤더 또는 표 범위를 지정한다. |
| 422 `XLSX_HEADER_INVALID` | 정규화 시 중복되는 열 이름, 수식·오류 또는 헤더가 없는 행을 확인한다. |
| 415 `UNSUPPORTED_TYPE`, 413 `ANALYSIS_LIMIT`/`FILE_TOO_LARGE` | XLSX 여부와 용량·행열 한도를 확인한다. |

선택형 변환은 기존 `/ingest/transformations`로 명시적 저장을 요청할 수 있다. 저장과 승인의 버튼 상태 및 지문 사용은 [나미님 저장·승인 인계](XLSX_SELECTION_PERSISTENCE_HANDOFF.md)를 따른다. 일반 `/batches` 원본 업로드에는 선택 범위를 보내지 않는다. [OpenAPI](../contracts/openapi.json) · [응답·요청 스키마](../contracts/schemas/ingestion_assistance_v1.json)
