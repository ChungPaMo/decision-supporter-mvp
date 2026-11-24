# Upstage 백엔드 연동 기반과 검증

2026-11-24 KST · Windows 보조 PC · 김대영

기준 `main` [`84de5b0`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/84de5b06293e468b109a4f6f241d3142f86175a5)

기존 파서·Exact/RapidFuzz를 기본 경로로 두고 Solar 후보와 문서 구조를 별도 API에서 검토할 수 있게 했다. 외부 기능은 기본 비활성화다. 비DB 테스트와 기존 합성 응답 캐시로 검증했다. Phase 4 유료 요청과 추가 비용은 0이며 누적 연구비 계산·예약액은 USD 9.90682308/10이다.

## 구성

| 구성 | 책임 |
| --- | --- |
| [`UpstageClient`](../backend/app/integrations/upstage.py) | HTTPS, 기능·모델 선택, 요청·응답 제한, 오류 변환, 요청 ID, 사용량, 비용 예약·결과 통지 |
| [`ai_mapping.py`](../backend/app/ingest/ai_mapping.py) | 원본 파싱 결과와 기존 추천을 받은 뒤 전략, 입력 프로파일, 프롬프트 버전, 로컬 업무·자료형 검증 적용 |
| [`mapping_review.py`](../contracts/mapping_review.py) · [`mapping_knowledge.py`](../contracts/mapping_knowledge.py) | 연구와 API에서 공유하는 문구·업무 개념·표준 필드 설명, Solar 요청 작성, enum JSON Schema, 종료·ID 검사, 부분 채택·충돌 검증 |
| [`ai_documents.py`](../backend/app/ingest/ai_documents.py) | Parse 표 구조 및 XLSX 위치 후보, Extract 반복 행의 출처·값·근거 검증 |
| [`ingest_ai.py`](../backend/app/api/ingest_ai.py) · [AI JSON Schema](../contracts/schemas/ingestion_ai_review_v1.json) | 독립 읽기 전용 FastAPI 계약. 기존 추천·변환·배치 API와 별도 |

| Provider 기능 | 동기 요청 경로 | Phase 4 연결 범위 |
| --- | --- | --- |
| Solar Chat | `/v1/chat/completions`, Mini 4.5 Preview는 `/v1/responses` | 매핑 검토. Mini 4/Pro 4의 지원 별칭이나 스냅샷으로 교체 가능 |
| Solar Embedding | `/v1/embeddings` | 내부 Provider. Embedding 2 query/passage, 요청 순서·인덱스·1024차원 검증 |
| Document Parse | `/v1/document-digitization` | 문서 분석. `standard`, `enhanced`, `auto` 및 페이지 구성이 모드에 맞는지 확인 |
| Information Extract | `/v1/information-extraction` | 내부 검토. `standard`/`enhanced`, 사용자 정의 반복 행 스키마 |
| Document Classify | `/v1/document-classification` | 내부 Provider. 허용 클래스만 반환하며 기존 파일 분류기 흐름과 독립 |
| Document OCR | `/v1/document-digitization` | 내부 Provider. `ocr` 및 페이지·단어 구조 검증 |

연동 형식과 동기 페이지 상한은 공식 자료를 기준으로 확인했다. Classify의 기본 스냅샷은 문서에 명시된 `document-classify-261113`을 사용하며 과거 연구 결과의 모델은 그대로 보존했다. [Document Parse API](https://console.upstage.ai/api/parse/document-parsing) · [Information Extract API](https://console.upstage.ai/api/information-extraction/universal-extraction) · [Document Classify](https://console.upstage.ai/ko/docs/capabilities/classify/document-classification) · [Document OCR API](https://console.upstage.ai/api/parse/document-ocr)

## 환경 설정과 비용

- [`.env.example`](../.env.example)의 `UPSTAGE_API_ENABLED`, 기능별 플래그, `AI_EXTERNAL_DATA_ALLOWED`는 모두 `false`다. 실제 배포 자격증명은 기존 설정 방식의 환경 변수 또는 배포 시크릿으로 주입한다. 연구용 `.env.upstage.local`은 애플리케이션 설정 대상에서 제외한다.
- 외부 요청마다 시스템 및 기능 플래그, 요청의 `external_review=true`, 운영자가 합성 원본임을 확인해 등록한 `AI_EXTERNAL_SYNTHETIC_SOURCES`의 데이터셋별 SHA-256, 서버 키, 비용 예약이 필요하다. 예를 들어 허용 목록의 자료형은 `{"SYNTHETIC-REVIEW":["<원본 파일의 SHA-256>"]}`다. `dataset_id`는 요청의 데이터 범위다. 공유 환경의 인증과 접근 제어는 배포 시 적용한다.
- 매핑은 표준 필드·업무 정의, 헤더, 물리 열 ID, 값 종류·형식·결측 비율만 보낸다. 값 표본을 보내지 않는다. 문서 기능은 허용된 합성 파일 한 개를 일반화한 파일명 또는 base64로 보낸다. `ApprovedSource`는 내부 호출자가 검증한 파일을 가리킨다. Embedding 텍스트도 그 원본에서 안전하게 생성한 입력만 내부에서 전달해야 한다.
- `CostTracker.reserve`는 요청당 상한을 원자적으로 예약한다. 최대 입력 바이트, 출력 토큰, 동기 문서 최대 100페이지, 문서 모드를 입력으로 받는다. XLSX 한 파일을 한 페이지로 계산하지 않으며 Auto는 Enhanced 상한을 적용할 수 있어야 한다. `complete`는 동일 요청 ID의 사용량과 전송 결과를 기록한다. 확인할 수 없는 과금과 오류는 미확정 예약으로 유지한다. 계량 저장소는 배포에서 `app.state.upstage_cost_tracker`로 주입한다. 저장소가 없거나 예약에 실패하면 전송하지 않는다. 기존 연구 원장·캐시와 런타임 비용 계량은 독립이다. [동기 페이지 상한](https://console.upstage.ai/ko/docs/models/compare/document-intelligence) · [요금](https://www.upstage.ai/pricing/api) · [Parse 데이터 처리](https://console.upstage.ai/docs/capabilities/parse/data-handling)
- HTTP 클라이언트는 고정 HTTPS 호스트를 사용한다. 리디렉션, 환경 프록시와 자동 재시도는 비활성화했다. 기본 제한은 30초, 매핑 32열·128 KiB 공급사 요청, 문서 파일 및 전송 본문 2 MiB, 공급사 응답 1 MiB다. 바이트·열·시간 상한은 설정으로 조정한다. 필요한 로그는 내부 요청 ID·기능·오류 코드만 남긴다.

## 추천 전략과 검증

| `AI_MAPPING_STRATEGY` | 범위 |
| --- | --- |
| `hold_review` | 기본. 확정 매핑도 로컬 후보도 없는 열만 검토한다. 이미 점유된 표준 필드는 제외한다. |
| `direct` | 전체 표의 열과 표준 필드를 직접 비교한다. |
| `concept` | 전체 표를 업무 개념 ID로 판별한다. 서버가 개념 ID를 표준 필드로 해석한다. |
| `business` | 표준 필드와 제조업 지식·반례를 함께 보여 주고 검토한다. |
| `verify_candidates` | 기존 후보를 입력으로 제공하고 독립 검토한다. 확정 매핑은 동결하고 기존 후보는 `baseline`에 남긴다. |

`AI_MAPPING_MODEL`, `AI_MAPPING_PROMPT_VERSION`, `AI_MAPPING_KNOWLEDGE_VERSION`은 독립 설정이다. 지원되는 버전은 `mapping-v1`·`mapping-v2`와 `manufacturing-v1`이다. 실행 결과의 `run`에 버전·SHA-256, 모델·스냅샷, 처리시간, 사용량을 기록한다. 미등록 버전과 지원 범위 밖 모델은 공급사 전송 전에 거부한다. 프롬프트와 업로드 헤더는 각각 시스템 메시지와 JSON 데이터에 두며 후보의 허용 범위는 서버가 만든다.

출력 잘림·거절·JSON 구조 손상·객체 키 중복은 AI 결과 전체를 HOLD한다. 구조가 정상이고 일부 ID·필드만 잘못됐으면 해당 열을 제외한다. 중복 대상, 기존 매핑 충돌, 단위·날짜·수량·코드·업무 뜻 불일치, 집계·변환이 필요한 후보는 별도 HOLD 사유가 된다. 기존 확정 매핑을 유지하고, 로컬 RapidFuzz 점수는 기존 `baseline`의 후보 정렬에 사용한다. `REVIEWABLE`은 사용자 검토가 가능한 상태다.

## API 예시와 프론트엔드 연동

두 요청 모두 `dataset_id` 쿼리와 `multipart/form-data`를 사용한다. 업로드한 원본 파일 `file`과 선택 동의 `external_review`를 보낸다. XLSX는 기존 [범위 선택 계약](XLSX_TABLE_SELECTION_HANDOFF.md)의 JSON `table_selection` 문자열을 함께 전달할 수 있다.

| 요청 | 폼 필드 | 응답 |
| --- | --- | --- |
| `POST /ingest/ai-mapping-review?dataset_id=SYNTHETIC-REVIEW` | `file`, 필수 `entity`, 선택 `external_review`, `table_selection`, `column_overrides` (기본 `{}`) | 파일 내부 분석의 `baseline`, `status`, `columns`, `run`, 오류 시 `issue`·`error_request_id` |
| `POST /ingest/ai-document-analysis?dataset_id=SYNTHETIC-REVIEW` | XLSX/PDF/PNG/JPEG `file`, 선택 `external_review`, XLSX용 `table_selection` | `source_sha256`, `mode`, `tables` (헤더·개수·페이지 좌표), `status`, `run` |

예를 들어 이전 단계에서 받은 파일과 범위를 유지한 채 `entity=monthly_demand`, `external_review=false`, `column_overrides={"product_id":"A"}`로 검토를 요청하면 `status=DISABLED`, `issue=AI_DISABLED`, `columns=[]`, `run=null`, `persisted=false`, `auto_approve=false`와 일반 `baseline`이 반환된다. 기능과 합성 입력을 승인한 환경에서 `external_review=true`로 검토한 열은 다음처럼 표시할 수 있다.

```json
{
  "source_id": "3",
  "col": 3,
  "source_column": "Forecast total",
  "target_field": "demand_qty",
  "source": "AI_SOLAR",
  "business_concept": null,
  "reason": "MODEL_AND_LOCAL_CHECKS_PASSED",
  "validation": "REVIEWABLE",
  "hold_reason": null,
  "conflict": false,
  "requires_user_confirmation": true
}
```

1. 기존 추천과 AI 검토 후보를 화면에서 각각 확인할 수 있도록 표시한다. `PRESERVED`는 기존 후보, `HOLD`는 확인이 필요한 열이다. 파일·데이터셋·표 범위·확정 매핑이 바뀌면 이전 검토를 폐기하고 다시 요청한다.
2. Parse 결과가 `USER_RANGE_MATCH`이면 선택한 헤더 위치와 행 개수가 일치했다는 보조 증거로 표시한다. 페이지 좌표와 Excel 원본 셀 주소를 구분한다. 복수 시트, 반복·병합 헤더, 위치 근거 부족은 HOLD로 표시한다. XLSX 값은 기존 원본 파서에서 읽고, HTML·Markdown과 추출 셀 값은 API 응답에서 제외한다.
3. 사용자가 확정한 매핑을 기존 변환 미리보기·변환 이력/배치 저장·검증·명시적 승인 경로로 전달한다. 기존 `/ingest/mapping-suggestions`의 승인 마스터 옵션은 그 API에서 계속 사용할 수 있다. 새 검토 API의 `baseline`은 DB 없이 파일을 기준으로 계산한다.

### Extract 내부 검토 계약

`extract_document`는 표준 엔터티의 키를 포함한 `{"rows":[{...}]}` 구조를 사용한다. 행 속성은 기본형 `string`, `integer`, `number`, `boolean`이고 중첩 객체와 추가 배열은 미지원이다. 서버 내부의 `ExtractionEvidence`로 데이터셋·원본 SHA·문서 유형·행 키·원본 값을 먼저 확정한다. 출력 행 키·값·타입을 대조하고 `additional_values`의 해당 값·페이지·정규화된 사각형 좌표를 확인한다. 추가·중복·누락 행/필드, 값 차이, 위치 누락은 HOLD다. 성공 응답도 확인된 행 키와 검증 결과만 제공한다.

### 오류 처리

`DISABLED`·`BLOCKED`·`UNAVAILABLE`·`HOLD`·`PARTIAL`은 검토 응답이므로 API의 기존 분석과 함께 제공된다. 파일·폼·SHA 오류는 기존 방식대로 4xx를 사용한다. 공급사 400/422는 `UPSTAGE_BAD_REQUEST`, 401/403은 `UPSTAGE_AUTHENTICATION`, 429는 `UPSTAGE_RATE_LIMIT`, 서버 오류는 `UPSTAGE_HTTP_ERROR`다. 연결·시간·크기·응답 형식 오류도 코드로 구분한다. 429의 초 단위 `Retry-After`가 있으면 반환한다. 원격 요청 및 응답 원문과 인증정보는 API 오류 메시지에 포함하지 않는다.

## 검증 결과

| 검증 | 이번 실행 결과 |
| --- | --- |
| 전체 비DB pytest | **1,313 passed, 68 skipped**. DB 의존 검증은 건너뛰었다. Starlette TestClient deprecation 경고 1건 |
| RapidFuzz 48건 | Top-1 25/32 · Top-3 26/32 · 오추천 3/48 · HOLD 20/48 |
| RapidFuzz 70건 | Top-1 5/37 · Top-3 6/37 · 오추천 7/70 · HOLD 58/70 |
| OpenAPI·JSON Schema | 기존 경로 및 구성 비교, 신규 스냅샷/Schema 생성 검사 통과 |
| 보안 검사 | 변경 파일 24개에서 탐지 0건. 저장소 전체 검사에서 기존 분류기 샘플 200개와 전화번호 패턴 3건을 탐지 |
| Upstage·DB | 실제 Upstage 요청 0건. DB·Docker 검증 미실행 |

[오프라인 재생 도구](../scripts/verify_upstage_backend_replay.py)는 Phase 3 요청 키, 캐시 본문 SHA, 합성 원본 CSV SHA를 검증한 후 두 패널 총 230개 응답을 재생했다. 공통 검증을 사용한 연구 집계의 정답·오추천·HOLD와 계약 오류 집계가 이전 보고서와 일치했다. `concept` 백엔드 경로에서는 기존 응답 ID를 1부터 시작하는 원본 열 번호로 바꾸고 MockTransport에 전달했다. 연구용 판별과 달리 실제 원본 프로파일을 적용하고 기존 로컬 매핑을 보전하므로 집계가 달라진다. [Phase 3 보고서](MAPPING_FINAL_ARCHITECTURE_EVALUATION_20261124.md)

| 평가셋 | Phase 3 공통 검증 재생, 정답 / 오추천 / HOLD | 백엔드 보호 규칙을 적용한 캐시 재생, 정답 / 오추천 / HOLD |
| --- | ---: | ---: |
| Final 130문서 · 1,132열 | 585 / 26 / 521 | 500 / 24 / 608 |
| Confirmatory 100문서 · 980열 | 278 / 24 / 678 | 391 / 23 / 566 |

Final에서는 형식 불일치 207열 등을 보류했고 Confirmatory에서는 기존 매핑 280열을 보전했다. 재생에는 Phase 3에서 이미 생성한 응답을 사용했다. 신규 프롬프트나 기본 `hold_review` 모델의 실측 품질은 별도 평가가 필요하다. 비용 기록은 재생 전후 SHA가 일치했다.

```powershell
$env:PYTHONPATH='backend;.;scripts;.artifacts/mapping-research/deps;.artifacts/mapping-research/metrics-deps'
.\.venv\Scripts\python.exe -m pytest --no-db -q --tb=short
.\.venv\Scripts\python.exe scripts/verify_upstage_backend_replay.py
.\.venv\Scripts\python.exe scripts/evaluate_mapping_recommendations.py
.\.venv\Scripts\python.exe scripts/evaluate_mapping_embeddings.py --method rapidfuzz
```

## 외부 활성화 전 확인

- 배포 인증과 합성 SHA 승인 절차, 요청 수 제한, 다중 프로세스 비용 예약·정산 계량을 연결한다. 공급사 429/타임아웃·예약 복구와 실제 과금 대조를 승인된 소규모 합성 자료로 확인한다.
- 프롬프트·업무 지식 변경은 버전과 해시를 남기고 동일 입력의 정답·오추천·HOLD·응답 실패·비용을 비교한다. 두 기존 패널의 캐시로 회귀를 확인하고 새 품질 평가는 독립 합성 입력과 별도 전송·예산 승인을 사용한다.
- 원본 XLSX 범위·값·근거가 충돌하는 표를 우선 확인한다. 반복 행의 원본 검증과 공식 문서에 명시된 지원 범위를 확인한 뒤 사용할 내부 Extract 호출 경로를 정한다. 프론트엔드 연동 전에는 사용자 확인과 오류 시 기존 추천 표시를 검증한다.
