# 제조업 입력 문서의 Upstage Document Intelligence 실측

2026-11-24 KST · 연구 기준 [`61cf597`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/61cf597608839b1f8754f7ccbf9266f43b9a4c44) · [Solar·로컬 모델 비교 및 공용 원장](MAPPING_UPSTAGE_AND_FINAL_COMPARISON_20261124.md)

## 결론

**Excel 셀 값과 위치는 원본에서 읽고, 복잡한 표의 위치 탐지와 PDF·스캔 입력에 Document Parse를 검토할 수 있다.** 원본 XLSX 4개에서 Standard와 Auto는 활성 시트 정답 표 11개 중 10개와 대응되는 표를 찾았다. 기본 XLSX 파서는 시트별 첫 헤더를 읽는 정책이라 이 표본에서 정답 표와 헤더가 일치하지 않았다. 같은 문서를 자동 등록할 근거로는 부족하다. Parse의 같은 위치 문자열 일치는 최대 499/1,075였고, 두 평면 BOM에서 Enhanced가 일부 데이터를 여러 표로 쪼갰다.

Information Extract Enhanced는 별도의 작은 합성 PDF에서 **209/210 필드와 29/30 행**을 그대로 가져왔다. Document Classify는 합성 파생 PDF 12개 중 **10개**, 기존 이훤 분류기는 같은 원본 XLSX **12개**에서 문서 종류가 맞았다. 양쪽이 보고 있는 입력 형태가 다르며, 표 구조·열 매핑·필드 추출은 각기 다른 채점이다.

## 실행 모델과 공식 계약

| 기능 | 실행 ID와 모드 | 제공 API와 평가 입력 | 페이지 정가 USD, 세전 |
| --- | --- | --- | ---: |
| Document Parse | `document-parse-260930` Standard / Enhanced / Auto | `/v1/document-digitization`, multipart. 원본 `.xlsx`, 스모크는 파생 `.pdf` | 0.010 / 0.030 / 페이지별 적용 |
| Document Classify | `document-classify-260904` | `/v1/document-classification`, base64 문서와 JSON Schema `oneOf`. 파생 `.pdf` | 0.004 |
| Information Extract | `information-extract-261113` Standard / Enhanced | `/v1/information-extraction`, base64 문서와 사용자 정의 JSON Schema. 반복 행 파생 `.pdf` | 0.040 / 0.060 |
| Document OCR | API 모델 `ocr` | `/v1/document-digitization`, multipart. `NOT_RUN` | 0.0015 |

- Parse는 XLS/XLSX·CSV/TSV, PDF, 이미지, Office·한컴 문서 등 공식 동기 100 MB/100페이지까지 지원한다. 최신 Snapshot의 Enhanced는 VLM을 사용하고, Auto는 페이지마다 Standard와 Enhanced를 선택한다. `output_formats`에 HTML·Markdown·text를 요청했고 요소 범주, 페이지와 정규화 좌표를 받았다. 정가는 보수적 예약에 사용했다. 공식 가격표의 Standard 기간 할인은 보수 계산에 반영하지 않았다. [모델](https://console.upstage.ai/ko/docs/models/document-parse) · [입력 제한](https://console.upstage.ai/ko/docs/capabilities/parse/input-requirements) · [API](https://console.upstage.ai/api/parse/document-parsing) · [공식 가격](https://www.upstage.ai/pricing/api)
- Information Extract 문서는 XLSX를 명시한다. 스모크·본 평가는 물리 페이지를 아는 PDF로 진행했다. 동기는 50 MB·최대 100페이지다. JSON Schema 루트는 객체이고, 첫 단계의 속성은 string/integer/number/array이며 배열 원소 객체로 반복 행을 표현한다. 배열의 직접 원소를 배열로 만들 수 없고 동기 요청은 객체 속성 100개와 스키마 15,000자 제한이 있다. 더 깊이 중첩한 객체와 `additionalProperties`를 포함한 요청은 두 모드 모두 400이었다. 공식 반복 행 예제 형태로 바꾸고 위치 단위를 `element`로 바꾼 결과 응답을 받았다. 어느 한 변경만이 400의 원인이었다는 근거는 없다. [모델](https://console.upstage.ai/ko/docs/models/information-extract) · [스키마 제약](https://console.upstage.ai/docs/capabilities/extract/writing-a-schema) · [좌표 계약](https://console.upstage.ai/docs/capabilities/extract/location-coordinates) · [API](https://console.upstage.ai/api/information-extraction/universal-extraction)
- Classify의 범주는 `BOM`, `MPS`, `MRP`, `RCCP`, `CRP`, `MES`, `ERP`, `OTHER`다. `split=false`에서 파일 하나에 클래스 하나를 받았다. 다른 업무 종류가 한 파일에 섞인 경우의 `split`은 미실행이다. 원본 XLSX 직접 Classify도 미실행이다. [Classify API](https://console.upstage.ai/api/document-classification) · [문서 모델 비교](https://console.upstage.ai/ko/docs/models/compare/document-intelligence)
- 공급사 설명상 동기 Parse의 입력과 추론 결과는 보관하지 않으며 학습에 쓰지 않는다. 비동기 Parse는 성공 결과를 30일 보관하고 실패 입력은 최대 3일 보관할 수 있다. 이번 연구는 동기 경로만 사용했다. 원본 파일·파생 표·응답 캐시는 로컬 Git 제외 디렉터리에 있고 키는 요청 헤더에만 사용했다. [데이터 처리 정책](https://console.upstage.ai/docs/capabilities/parse/data-handling) · [시작·개인정보 안내](https://console.upstage.ai/docs/getting-started)

## 평가 패널과 정답

`modules/file_classifier/samples/`의 200개 중 기존 `test` 분리에서 12개를 선택했다. `labels.json`, 생성기와 선택 파일 바이트를 시작 Commit의 Git blob과 대조했다. 원본 SHA, 생성기 블록을 실제 시트에서 찾아낸 표 열·행 범위, 그룹 헤더, 병합 범위, 수식 캐시, 파생 PDF 페이지와 SHA를 외부 호출 전에 고정했다. 고정 manifest SHA-256은 `1e4c02590e821aba2e9af2db8358b92c574ea9a9fef82ec002996a0787258f3a`다. 파생 PDF 12개는 14페이지다.

12개에는 단일 헤더 10개, 그룹 헤더 2개, 병합 셀 6개, 공백 행 10개, 공백 열 7개, 제목 6개, 복수 표 1개, 비어 있지 않은 복수 시트 2개, 총계 3개, 숨김 열 2개, 수식 5개가 있었다. 원본에 숨김 행이 있는 표본은 없었다. 4개 원본 Parse 공통 비교는 평면 BOM 2개, MPS 1개, 8개 표가 들어 있는 다중 시트 MRP 1개다. 재현할 때 PDF는 화면 크기에 맞춘 이미지 기반 파생본이고 원본 Excel 렌더러와 재계산 결과를 재현하지 않는다. 수식 캐시가 없으면 빈값이며 수식 결과를 만들어 정답으로 삼지 않았다.

- 파일 유형 정답은 기존 `labels.json`을 사용했다. `미분류`와 `OTHER`를 대응했다.
- 구조 정답은 활성 시트 기준 생성기 표 범위다. 표 검출은 정규화한 헤더 셀 집합의 유사도 0.5 이상, 일대일 대응 기준이다. 표 열·행 개수, 전체 헤더 문자열, 헤더 깊이, 병합 개수 및 비어 있지 않은 셀의 동일 행·열 위치 문자열을 따로 세었다.
- 평면 BOM 두 개에만 `product_id`, `component_id`, `qty_per` 열 역할이 독립 확인돼 있다. 나머지 복합 문서의 분류 결과에 열 매핑 정답률을 붙이지 않았다. 정보 추출은 표준 5개 타입에서 고정 보정용 합성 표 1개씩 6행을 사용한 별도 실험이다.

## 표 탐지 및 값 보존

| 같은 원본 XLSX 4개 | 출력 표 | 대응 표 / 11 | 파일별 표 수 일치 / 4 | 헤더·깊이 일치 | 행 수 일치 | 열 수 일치 | 셀 문자열 / 1,075 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 기존 XLSX 기본 파서 | 5 | 0 | 3 | 0 | 0 | 0 | 0 |
| Parse Standard | 13 | 10 | 3 | 10 | 10 | 10 | 499 |
| Parse Enhanced | 15 | 10 | 1 | 10 | 8 | 10 | 210 |
| Parse Auto | 13 | 10 | 3 | 10 | 10 | 10 | 499 |

정답 표와 대응된 10표의 머리 병합 **개수**는 모두 일치했다. 정확한 병합 셀 주소 복원은 그 수치에 포함되지 않는다. 표 하단·다른 시트의 추가 요소를 별도 표로 잡은 사례가 있고, 대응표 기준 Enhanced는 101개 본문 행이 부족했다. Standard/Auto는 대응표 행 수가 일치했다. 이 원본 4개에서 Auto의 5페이지는 전부 Standard였다.

대응 표의 숫자 문자열 일치는 Standard/Auto 147/536, Enhanced 60/536이다. 같은 위치에서 `Decimal`로 비교하면 각각 165/536, 64/536이다. `20.7 → 20.70`, `23 → 23.00`처럼 값이 같고 표기만 달라진 사례와 행·표 분할 때문에 원래 위치에서 빠진 사례가 있었다. 정답 표에 대응되지 않은 셀은 각 모드 187개로 따로 집계했다. 별도의 원본 ERP 재고 파일 1개에서는 Standard/Enhanced 모두 헤더·행·열 수가 맞았고 셀 문자열 69/126, 숫자 값 51/108이 일치했다. 날짜·단위 열은 이 원본 표들에서 독립 정량 검증할 수 없었다. 조밀한 파생 PDF 스모크 한 장에서 Standard/Auto는 표를 0개 반환했고 Enhanced는 2표로 분할했다. 형식별 성능은 합산하지 않았다.

API가 돌려준 좌표는 변환 페이지 기준이다. 평면 BOM 두 개에서 결과 헤더의 문자열 순서가 원본에 유일하게 존재하는지 확인해 `시트·행·열·셀 주소·원본 SHA`를 연결했다. 이 절차는 두 파일 모두 실제 3행으로 연결했다. 복수 시트나 여러 표에서 헤더가 반복되면 링크를 부여하지 않는다. 페이지 좌표 전체를 Excel A1 주소로 바꾸거나 응답 숫자로 원본 셀 값을 덮어쓰는 흐름은 실험에 없다.

## 분류 및 행 추출

| 실제 문서 종류 | 개수 | 기존 분류기 XLSX | Document Classify 파생 PDF |
| --- | ---: | --- | --- |
| BOM | 2 | BOM 2 | BOM 2 |
| MPS | 1 | MPS 1 | MPS 1 |
| MRP | 1 | MRP 1 | MRP 1 |
| RCCP | 2 | RCCP 2 | CRP 2 |
| CRP | 1 | CRP 1 | CRP 1 |
| MES | 3 | MES 3 | MES 3 |
| ERP | 1 | ERP 1 | ERP 1 |
| 미분류 | 1 | 미분류 1 | OTHER 1 |

RCCP를 CRP로 보내면 이후 잘못된 계획 자료 경로에 진입할 수 있다. 해당 두 문서에 대한 표준 등록 열 정답은 없다. 문서 종류 결과가 값 등록의 증거가 될 수 없으며, 복합·미등록 유형은 기존 확인 게이트에서 HOLD를 유지한다.

| Information Extract 반복 행 | JSON 성공 | 복원 행 / 30 | 값 완전 일치 행 | 동일 값 / 210 | 틀린 값 | 누락 값 | 추가 행 / 근거 없는 빈 필드 채움 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Standard | 5/5 | 30 | 0 | 144 | 59 | 7 | 0 / 0 |
| Enhanced | 5/5 | 30 | 29 | 209 | 1 | 0 | 0 / 0 |

스키마의 필드는 제품, 자재, BOM, 재고, 월별 수요의 허용 등록 필드에서 선택했다. 원본 표시값 보존을 확인하기 위해 leaf를 문자열로 요청하고 결과를 열 순서·스키마·행 위치에 대조했다. 이것은 등록용 DTO 검증이나 컬럼 추천 Top-1의 결과와 별개다. `additional_values` 위치 도구는 모든 성공 응답에 있었으며, 문서 PDF 좌표와 원본 Excel 셀 주소 간 변환은 확인되지 않았다. 필수 항목 실제 누락의 다수 사례와 업무별 형 변환은 추가 검증 대상이다.

## 업로드 이후 후보 비교

6개 열과 평면 BOM 두 문서에 한정했다. 성공은 독립 정답인 세 역할을 한 문서에서 모두 추천한 경우다. 누락된 BOM 등록 필드까지 생성하거나 승인하는 단계는 없다. Parse 결과는 캐시에서 LightGBM·Solar에 공통 사용했다.

| 경로 | 정확 / 6 | 오추천 | 세 역할 충족 / 2 |
| --- | ---: | ---: | ---: |
| 기존 분류 + 기본 파서 + RapidFuzz | 0 | 0 | 0 |
| 기존 분류 + 기본 파서 + LightGBM | 0 | 2 | 0 |
| 기존 분류 + 기본 파서 + Solar Mini | 0 | 0 | 0, 계약 실패 2 |
| 기존 분류 + 확인 범위 + RapidFuzz | 2 | 0 | 0 |
| 기존 분류 + 확인 범위 + LightGBM | 0 | 2 | 0 |
| Document Classify + 기존 XLSX 파서 | — | — | 두 BOM 분류 성공. 기본 파서가 1행을 헤더로 선택 |
| Parse Standard + LightGBM | 0 | 2 | 0 |
| Parse Enhanced + LightGBM | 0 | 1 | 0 |
| Parse Standard + Solar Mini | 2 | 1 | 0, 계약 실패 1 |
| Parse Enhanced + Solar Mini | 6 | 0 | 2 |
| Information Extract 단독 | — | — | 별도 반복행 표의 위 수치 적용 |
| Parse + Information Extract | — | — | `NOT_RUN` |
| Classify + Parse Enhanced + Solar Mini | 6 | 0 | 2, 같은 두 BOM의 개별 성공 캐시를 합성 |

마지막 조합은 캐시에서 두 BOM의 분류가 모두 맞았음을 대조한 값이다. 통합 제품 E2E 실행은 수행하지 않았다. Enhanced에서 컬럼 추천을 전부 맞춘 문서도 행 복원에서 누락이 있었다. 컬럼 추천 성공과 전체 값 적재 가능성을 분리해야 한다.

## 공용 예산과 속도

| 모드 | HTTP 요청 | 성공에서 보고 또는 렌더 페이지 | 공급사 사용량 기반 보수 비용, VAT 포함 USD | P50 / P95 |
| --- | ---: | ---: | ---: | --- |
| Parse Standard | 6 | 7 보고 | 0.0770 | 10.59 / 12.32초 |
| Parse Enhanced | 6 | 7 보고 | 0.2310 | 12.60 / 23.53초 |
| Parse Auto | 5 | 6 보고 | 0.0880 상한 근사 | 10.54 / 13.46초 |
| Document Classify | 12 | 14 렌더 | 0.0616 | 12.30 / 15.22초 |
| Extract Standard | 6 | 5 렌더, 400 1페이지 예약 | 0.2200 + 0.0440 예약 | 13.91 / 21.04초 |
| Extract Enhanced | 6 | 5 렌더, 400 1페이지 예약 | 0.3300 + 0.0660 예약 | 8.12 / 12.16초 |

Parse Auto 최초 PDF의 응답에 페이지 모드 배열이 왔고, 당시 원장은 Enhanced 단가로 예약한 뒤 그대로 반영했다. 이후 요청은 응답 모드별 정가로 정산했다. Classify·Extract의 동기 응답은 토큰을 반환했으며 원장은 모델별 페이지 정가와 미리 고정된 PDF 페이지 수로 계산했다. 원본 XLSX에는 동기 상한 100페이지를 예약했다가 응답의 페이지 수로 정산했다. 400의 예약액을 유지했고, 공급사 실제 결제 영수증은 조회하지 않았다. [공용 원장 합계](MAPPING_UPSTAGE_AND_FINAL_COMPARISON_20261124.md#공용-비용-원장)

## 재현과 사용 경계

```powershell
$base = '.artifacts/mapping-research'
$env:PYTHONPATH = "scripts;$base/deps;$base/metrics-deps"
.\.venv\Scripts\python.exe scripts/mapping_research_document.py prepare --modes standard enhanced auto classify extract-standard extract-enhanced
.\.venv\Scripts\python.exe scripts/mapping_research_document_pipeline.py
.\.venv\Scripts\python.exe scripts/mapping_research_remote.py audit --output "$base/phase2/billing-summary.json"
```

오프라인 `prepare`가 해시를 갱신하므로 새 데이터 검증에서는 기존 manifest를 별도로 보존한다. 승인된 비용 범위에서 원본 Parse를 측정할 때 `mapping_research_document.py run --native --limit 4 --modes standard enhanced auto --approved-paid-api --output .artifacts/mapping-research/document-intelligence/native-panel.json`을 사용한다. 본 실측의 Classify는 `--limit 12 --modes classify`, 정보 추출은 `--limit 5 --modes extract-standard extract-enhanced --flat-extraction`이다. `mapping_research_document_pipeline.py --approved-paid-api`는 이전 Parse 요청을 읽고 같은 두 파일만 Solar에 전달한다. 공용 원장과 기존 캐시를 유지하면 성공한 요청을 반복 청구하지 않는다.

권장 경로는 확인된 Excel 헤더와 범위에서 openpyxl로 값을 추출하고, 필수 필드와 원본 위치를 검증한 뒤 사용자 확인을 받는 흐름이다. 복잡한 문서는 Parse가 표 위치 후보를 주고, 후보가 유일하면 원본에서 다시 읽는다. PDF·스캔은 Enhanced 추출을 별도 검토 대상으로 두며 셀 근거가 재현되지 않는 경우 HOLD한다. 계산식·숨김 행·다중 문서 분할·실제 고객 양식의 추가 근거를 확보해야 한다.
