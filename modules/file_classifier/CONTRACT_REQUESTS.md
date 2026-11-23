# 파일 분류 모듈 연동 현황과 요청 사항

작성: 이훤, 2026-11-22. 2026-11-23 갱신. 기준 코드: `rules-0.4.0`.
다른 담당 폴더는 직접 고치지 않고, 필요한 변경을 이 문서로 요청한다.

## 0. 2026-11-23 반영: 보류 종류를 모듈이 직접 준다 (`rules-0.4.0`)

김대영 님이 `docs/CLASSIFIER_XLSX_MAPPING_VERIFICATION_20261123.md`에서 인계한 "`ClassificationOutput.hold_kind`를 분류 결과에서 직접 제공" 요청을 반영했다.

- 보류일 때 `hold_kind`를 항상 채운다. 추천했을 때는 `null`이다. 문구(`reasons`)와 후보, 추천 유형은 바꾸지 않았다.
- 값의 뜻
  - `NEEDS_TRANSFORM`: 판매 내역이나 월이 가로로 펼쳐진 표. 집계·변환하면 월 수요가 된다.
  - `OTHER_ROUTE`: 설비 능력·라우팅 자료. 다른 등록 경로를 쓴다.
  - `AMBIGUOUS`: 시트마다 유형이 다르거나, 한 표가 두 유형에 걸쳐 있거나, 품목 코드·이름만 있어 제품인지 자재인지 알 수 없다.
  - `UNKNOWN`: 근거가 부족하다. 보류 이유가 시트마다 달라 한 가지 안내로 묶을 수 없을 때도 이 값이다.
- 버전을 `rules-0.4.0`으로 올렸다. 백엔드의 임시 변환(`legacy_hold_kind`)은 `hold_kind`가 비어 있을 때만 동작해 쓰이지 않게 됐으므로, 2026-11-23에 이훤이 `backend/app/integrations/modules.py`에서 직접 지웠다(21줄, 다른 동작은 그대로).
- **임시 변환과 다른 결과가 한 가지 있다.** 자체 사례 263건 중 보류 114건을 비교했더니 113건이 같고 1건이 달랐다. 제품 코드·이름과 월 열이 함께 있는 가로 월 수요 표인데, 임시 변환은 후보가 2개(월 수요, 제품)라는 이유로 `AMBIGUOUS`를 줬고 모듈은 `NEEDS_TRANSFORM`을 준다. 제품 마스터 쪽 일치도가 14%뿐이라 변환 안내가 맞다고 판단했다. 후보가 2개 이상이면 항상 `AMBIGUOUS`여야 한다면 알려 달라.
- `registration_hint`는 모듈이 채우지 않는다. 등록 양식의 필수·허용 헤더를 아는 쪽이 백엔드이므로 지금처럼 백엔드가 붙이는 것이 맞다.
- 시험: `tests/test_hold_kind.py`.

## 0-1. 2026-11-23 제안: 표 범위를 자동으로 찾아 준다 (`tables-0.1.0`)

김대영 님의 [표 범위 선택 API](../../docs/XLSX_TABLE_SELECTION_HANDOFF.md)는 사용자가 머리글 행과 데이터 범위를 직접 지정한다. 그 범위를 미리 채워 줄 수 있는 함수를 모듈에 만들었다. 백엔드와 화면은 고치지 않았다.

```python
from file_classifier.tables import find_tables_in_xlsx

for t in find_tables_in_xlsx(xlsx_bytes):      # 보이는 시트의 표를 위에서부터 모두
    t.sheet, t.header_row, t.data_start_row, t.data_end_row, t.first_col, t.last_col, t.total_row
```

- 좌표는 원본 시트 기준 1부터 시작하고 끝을 포함한다. `XlsxTableSelection`과 같은 뜻이라 `source_sha256`만 더하면 그대로 넣을 수 있다.
- 합계 행은 데이터 범위에서 빼고 `total_row`로 따로 알려 준다. 가로로 병합된 칸이 있는 행은 머리글로 고르지 않는다.
- 확인한 것: 더미 200개에서 찾은 첫 표의 범위를 `POST /classifications/file`의 `table_selection`에 넣었더니 200개 모두 받아들여졌다(병합·머리글 오류 0건). 재현: `tools/eval_tables_api.py`.
- 정확도: 더미 200개의 표 422개를 모두 맞게 찾았다. 다만 규칙을 이 200개를 보면서 만들었고, 실제 기업 파일로는 재지 않았다. 자세한 내용은 README의 "표 위치 찾기".
- **제안.** `/ingest/xlsx-layout` 응답에 "추천 범위" 목록을 선택 필드로 넣으면, 화면이 범위를 미리 채워 두고 사용자는 확인만 하면 된다. 추천은 제안일 뿐이고 사용자가 고칠 수 있어야 한다. 넣을지와 필드 이름은 김대영 님이 정해 달라.
- 참고: 범위를 넣어도 더미 200개 중 192개는 여전히 보류(`UNKNOWN`)다. 대부분 보고서라서 등록 대상 5종이 아니기 때문이며, 표를 못 읽어서가 아니다.

## 1. 지금 연결된 것

| 연결 | 상태 | 근거 |
| --- | --- | --- |
| 분류기 → 백엔드 API (`/classifications`, `/classifications/file`) | 연결됨 | `backend/app/integrations/modules.py` |
| 분류기 → 컬럼 매핑 추천 (`/ingest/classified-mapping`) | 연결됨 | `backend/app/api/ingest_assistance.py` |
| 분류기 → 화면 "파일 유형 추천" 패널 | 연결됨 | `frontend/src/components/ClassificationPanel.tsx` |
| 문서 종류 분류(BOM/MPS/MRP/RCCP/CRP/MES/ERP) → API·화면 | 연결 안 됨 | `tools/sort_folder.py`로만 실행 가능 |

## 2. 공식 합성 자료(CHUNGPAMO-2027)로 확인한 결과

이희원 담당 생성기가 만든 CSV 48개를 분류기에 넣었다(2026-11-22, 열 이름 기준).

- 업로드용 5종(제품, 자재, BOM, 재고, 월 수요)과 그 오류 예시 파일: 모두 올바른 유형으로 추천.
- 설비 능력 3종과 라우팅: 보류. `rules-0.3.0`부터 "설비 능력(CAPA) 등록 / 라우팅 등록에서 유형을 직접 선택" 안내를 붙인다.
- 판매현황 5개: 보류, 월 수요로 집계 안내.
- 재고수불부, 생산실적, 자재투입, 구매발주, 입고 등 거래·현황 자료: 보류. 다섯 유형으로 잘못 추천한 파일 없음.

고정 시험: `tests/test_official_dataset.py`. 생성기의 열 이름이 바뀌면 이 시험이 실패하므로, 열 이름을 바꿀 때 알려 주면 함께 고친다.

## 3. 요청 사항

### 김대영 (계약·백엔드)

1. **분류 유형 확장 여부 결정.** 현재 계약의 `Entity`는 5종이라 설비 능력·라우팅 파일은 추천하지 못하고 안내만 한다. 백엔드에는 설비 능력 등록이 구현돼 있으므로, 계약에 유형을 추가해 주면 분류기가 추천까지 하도록 맞추겠다. 필요한 것은 추가할 유형 이름 목록이다(예: `capacity_resources`, `capacity_quantity_limits`, `capacity_hours_budgets`, `routing_steps`).
2. **(반영됨, 위 0번) 보류 사유를 구분할 필드.** 지금은 보류 이유가 문장(`reasons`)으로만 전달돼, 화면이 "변환하면 등록 가능", "다른 등록 경로", "판단 불가"를 구분하려면 문장을 해석해야 한다. `hold_kind` 같은 선택 필드(예: `NEEDS_TRANSFORM`, `OTHER_ROUTE`, `AMBIGUOUS`, `UNKNOWN`)를 계약에 추가하면 분류기가 값을 채우겠다.
3. **문서 종류 분류 API.** 필요하다고 판단되면 경로와 응답 형식을 정해 달라. 분류기 쪽 호출 함수는 `file_classifier.doctype.classify_workbook`이며 openpyxl만 필요하다. 의미 매칭(`doctype_embed`)은 torch와 BGE-M3가 필요하므로 서버 기본 경로에는 넣지 않는 것을 권한다.

### 정마나미 (화면)

1. **보류 표시 구분.** 보류일 때 제목이 항상 "분류가 모호합니다"로 나온다. 판매 내역(집계하면 등록 가능)과 설비 능력·라우팅(다른 등록 경로)은 모호한 것이 아니므로, 위 2번 필드가 생기면 문구를 나눠 달라. 그 전에는 `reasons` 첫 문장을 제목 아래에 그대로 보여 주는 것으로 충분하다.
2. **후보가 없을 때 빈 표.** 보류이고 후보가 0개면 표 머리글만 보인다. 이 경우 표를 숨겨 달라.
3. **CAPA·라우팅 안내 문구.** 패널의 "저장·승인은 아직 제공하지 않습니다" 문구가 현재 백엔드 상태(설비 능력 등록 구현됨)와 맞는지 확인해 달라.

### 이희원 (합성 자료)

요청 없음. 업로드용 파일의 열 이름을 바꿀 계획이 있으면 미리 알려 달라.

## 4. 분류기가 지키는 것

- 함수와 계약(`classify(ClassificationInput) -> ClassificationOutput`)은 그대로 둔다. 문구와 버전(`module_version`)만 바뀐다.
- 추천이 없으면 항상 `hold=True`와 이유를 돌려준다. 점수는 확률이 아니다.
- 파일 내용을 외부로 보내지 않는다.
