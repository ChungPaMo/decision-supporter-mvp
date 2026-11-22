# 데이터 입력 보조 계약과 향후 AI 연결 설계

2026-11-22, 고정 합성 48건의 로컬 BGE-M3 평가에서 후보 포함률과 동시에 오추천도 늘었다. 운영은 RapidFuzz를 유지하고 금액·출고·기준/가용 혼용에 대한 후보 반증을 보강했다. 요청·응답·수동 확인과 승인 게이트는 기존 계약을 따른다. [새 측정과 적용 결정](MAPPING_BGE_EVALUATION_20261122.md)

2026-11-16 컬럼 추천 후속: [48건 비교·MVP 결정](MAPPING_RECOMMENDATION_MVP_20261116.md)에 따라 scorer를 RapidFuzz로 교체했다. 정확/별칭/수동 매핑·cutoff·Top-3·DTO·승인 게이트는 유지하고 괄호 속 의미 반증을 보강했다. 아래 SequenceMatcher 설명은 최초 구현 기록이다. 현재 PC의 Docker/PostgreSQL 구성·실DB 검사·0009 실제 적용은 금지·보류하며 기존 개발 PC로 이관한다. BGE-M3는 기존 연구를 재사용했고 Upstage/LLM은 호출하지 않는다.

2026-11-16 후속: [분류·변환 이력 연결](INGESTION_INTEGRATION_HISTORY.md)에서 classified-mapping과 명시적 영구 저장 API, 신규 0009를 추가했다. 아래 무저장·원본 SHA 연결 한계는 기존 preview API의 당시 계약으로 보존한다. 새 저장 경로와 혼동하지 않는다. AI 호출·저장 매핑 규칙 자동 적용은 여전히 없다.

2026-11-15, `ingestion-assistance-0.1`. [연구 근거](AI_ASSISTED_DATA_INGESTION_RESEARCH.md)를 먼저 작성한 뒤 구현했다. **현재 AI/embedding/API key/외부 추론 호출은 없다.** 모델·서비스·비용 계약은 미선정이다. 이 문서는 현 구현과 후속 제안을 구분한다.

## 현재 흐름과 개발 경계

파일 분류는 기존 `/classifications` 및 `/classifications/file`과 `modules/file_classifier/`의 이훤 담당이다. 이번 구현은 사용자가 선택한 entity 내부의 프로파일/매핑 후보/합성 판매 변환만 담당한다. 분류기 알고리즘·계획 엔진·frontend는 수정하지 않는다.

```text
원본(bytes, SHA 유지) → 기존 parser / 제한된 분석 preflight
                    → 컬럼 profile → 기존 exact alias map + 검토 후보
                    → 정책 DTO + 사용자 확인 → 허용 연산 recipe preview
                    → 원본 대비 합계/제외/오류/추적 검토
                    → 사용자가 표준 CSV를 별도 /batches에 업로드
                    → 기존 검증·재검증·명시적 승인·SQL 트랜잭션
```

새 분석 API는 DB 승인 자료/배치/정책 테이블을 생성하지 않는다. 기능을 위한 신규 DB migration은 추가/수정하지 않고 개발 DB에 migration을 적용하지 않았다. 승인된 회귀 DB에서 기존 0001~0008을 재적용하는 시험은 별도다. 추천 경로에서 기존 `map_sheet`/`run_preview` 동작을 바꾸지 않는다. Decimal 수량·기존 날짜/중복 정책·원본 SHA·수동 override·셀 위치·같은 데이터셋 참조 검증을 재사용한다.

## 실제 API (multipart/form-data)

공통 query `dataset_id`: 생략 시 TISSUE-LEGACY, 데이터 권한을 부여하는 값이 아니다. `use_approved_master=false`가 기본이며 이때 DB 접속은 없다. true이면 기존 SQL repository로 해당 ACTIVE dataset의 승인 제품/자재만 읽는다. persistence 비활성 501, DB 장애 503, 없는/비활성 dataset 404/409, 잘못된 dataset 422. 다른 dataset으로 fallback하지 않는다.

오프라인 기본 모드는 dataset ID 문법만 확인하며 DB 내 존재/상태를 보증하지 않는다. master_scope=null을 ‘참조 검증 완료’로 표시하지 않는다.

| 경로 | 입력 | 응답과 경계 |
| --- | --- | --- |
| `POST /ingest/profile` | file(CSV/XLSX), include_samples=false, use_approved_master=false | source_sha256, master_scope/digest, sheet/column 통계. 등록·승인 결과와 별개 |
| `POST /ingest/mapping-suggestions` | file, entity(product/material/monthly_demand/bom/inventory), column_overrides JSON, use_approved_master | 기존 선택 컬럼, top-3 후보·방법·근거·HOLD. fuzzy 추천 자동 적용 없음 |
| `POST /ingest/transform-preview` | files(1~8개), policy(JSON), use_approved_master; query offset=0/limit=500 | 정책/입력/결과 digest, 원본 SHA 목록, partition counts, 월 수요·반품·합계·오류·행 위치. persisted=false |
| `POST /ingest/preview` | 기존 계약 유지 | 기존 파싱·매핑·검증이며 새 변환 실행을 암묵적으로 수행하지 않음 |

프로파일링 수치는 실제 비어 있지 않은 셀을 분모로 계산한 형식/마스터 일치 비율이다. 확률이나 의미 신뢰도가 아니다. count=0일 때 비율은 0, 마스터 미제공 시 master ratio는 null이다. 코드/숫자, mixed formats, 의미 미해결 이유를 별도로 제공한다. 마스터 digest는 해당 dataset 제품/자재 코드·기준단위 snapshot의 SHA로서 DB 전체 revision이나 승인자 인증을 대신하지 않는다.

요청 예:

```json
{
  "dataset_id": "CHUNGPAMO-2027",
  "policy_id": "CHUNGPAMO_SYNTHETIC_SALES",
  "version": "1.0",
  "columns": {
    "order_date": "주문일자", "product_id": "제품코드", "quantity": "수량",
    "unit": "단위", "status": "구분", "order_id": "주문번호", "line_id": "행번호"
  },
  "user_confirmed": false
}
```

이 JSON은 `policy` form 문자열에 넣는다. 파일 5개는 같은 이름 `files`로 반복한다. 나머지 고정 정책 필드는 Pydantic 기본값을 쓰며 응답 policy에는 모두 기록된다. `user_confirmed`는 진짜 JSON boolean만 허용한다. 이는 호출자가 선택한 검토 상태이며 로그인/전자서명이나 승인 자체를 증명하지 않는다.

응답 핵심 형식 (수치는 작은 합성 입력의 예시):

```json
{
  "status": "POLICY_REVIEW_REQUIRED", "dataset_id": "CHUNGPAMO-2027",
  "counts": {"source_rows": 4, "normal_included": 2, "cancelled_excluded": 1,
    "returns_separate": 1, "error_rows": 0, "aggregation_errors": 0, "monthly_demand_rows": 1},
  "records": [{"product_id": "P1", "period": "2026-01", "demand_qty": "0.3", "unit": "EA",
    "source_row_count": 2, "source_locations": [{"source_index": 0, "sheet": "", "row": 2, "col": null}]}],
  "auto_approve": false, "approval_required": true, "persisted": false
}
```

위는 일부 필드만 보여준다. 전체 기계 계약: [DTO](../contracts/interfaces/ingestion.py), [생성 Schema](../contracts/schemas/ingestion_assistance_v1.json), [OpenAPI](../contracts/openapi.json). row의 source_locations는 최대 5개 예시다. 전체 추적이라고 해석하지 않는다. 각 source_index는 응답 sources의 filename/sha256에 대응한다. col은 오류에서만 구체적으로 채워질 수 있다.

## 매핑 우선순위와 HOLD

1. 저장된 사용자 규칙은 [SavedMappingRuleDraft](../contracts/interfaces/ingestion.py)만 정의했다. 저장/자동 적용은 NOT_IMPLEMENTED이며 DB migration을 만들지 않았다. 향후 dataset/entity/header_signature/version 일치와 재확인이 선행돼야 한다.
2. 현재 요청의 명시적 `column_overrides`가 우선이며 기존 mapper로 해석한다.
3. 표준 필드명 → 강한 별칭 → 약한 별칭을 구분해 보여준다. 기존 mapper는 그대로다.
4. 표준 라이브러리 [SequenceMatcher](https://docs.python.org/3/library/difflib.html)로 후보 검색한다. autojunk=false, 후보용 lexical cutoff 0.60, 최대 3개. 숫자/날짜/코드·마스터 반증으로 걸러낸다. 이 cutoff는 정확도·보정 confidence·자동 선택 임계값이 아니다.
5. 승인 마스터 코드 일치율 0.8 이상이면 제품/자재 후보를 추가할 수 있으나 의미를 확정하지 않고 검토를 요구한다. 작은 표본에 대한 정확도 보장은 없다.
6. 필수 열 없음/복수/중복 헤더, 약한 필수 별칭, 자료형 반증은 보조 응답에서 HOLD. fuzzy top-1도 자동 선택하지 않는다. existing_mapping은 기존 선택을 설명할 뿐 그 전체가 승인됐다는 뜻이 아니다.

금액↔수량, 제품↔자재, 출고↔주문, 현재고↔가용재고, 반품/취소↔정상 수요, 생산한도/설비시간/인시↔판매 수요는 단순 문자열 유사도로 합치지 않는다. 마스터 코드가 두 namespace에 같이 존재할 수도 있어 값만으로 제품/자재를 결정하지 않는다. 파일 헤더가 거짓 의미를 표기하는 경우까지 자동 검증할 수 있다고 주장하지 않는다.

## 1차 합성 판매 정책

`CHUNGPAMO_SYNTHETIC_SALES` v1.0 / source_scope=SYNTHETIC_ONLY: ㈜충파모제지 **합성** 자료용이다. 다른 회사의 보편 정책이 아니다. 원본의 연도별 `판매현황_2022.csv`~`판매현황_2026.csv`를 함께 읽는다. 요청서의 단일 `판매현황_2022~2026.csv`는 현재 생성기에 없으므로 파일 구조를 실제 코드에 맞춰 처리했다.

| 순서/연산 | 구현 의미 | 금지·오류 처리 |
| --- | --- | --- |
| SELECT_COLUMNS | 선택한 7개 semantic columns만 사용 | 필수 누락·중복/동일 열 다중 역할은 HOLD 오류 |
| RENAME_COLUMNS | 응답 policy에 원본→정규 역할 매핑 기록 | 원본 파일 변경 없음 |
| NORMALIZE_DATE | 주문일자, 명시한 YYYY-MM-DD/YYYY/MM/DD/YYYYMMDD, 실제 달력 검증 후 YYYY-MM | 지역식 M/D/Y·모호한 소수 월·잘못된 날짜 추정 안 함 |
| NORMALIZE_UNIT | 팩/EA→EA, factor=1 | 다른 단위/박스 환산/다른 제품 pack 규격 추정 금지 |
| FILTER_ROWS | 정상 포함, 취소 제외, 반품 절댓값 별도 집계 | 알 수 없는 상태는 오류. 반품 수요 차감 없음 |
| VALIDATE_REFERENCE | 마스터 제공 시 같은 dataset의 제품·EA 기준단위 확인 | 미제공은 UNVERIFIED 경고, unknown/cross code 오류 |
| GROUP_BY | 제품·월. 거래 키(주문번호, 행번호) 중복은 오류 | 반복 주문을 월 수요와 같은 ‘동일값 dedupe’로 지우지 않음 |
| SUM_DECIMAL | 기존 숫자 형식/범위 검증 후 Decimal context 40, 월 합계 NUMERIC(18,4) 재검증 | float·반올림으로 정답 맞추기·0수요 월 생성 안 함 |

연산은 이 **고정 recipe**로 컴파일하여 한 번의 streaming reduction으로 실행한다. API는 operation list/SQL/Python/정규식 코드를 입력으로 받지 않는다. `compile_recipe`의 parameters는 서버가 만든 설명이다. 다른 연산 순서·환산 계수·상태 정의는 v1에서 422이며 후속 정책 버전 합의가 필요하다.

정상·취소·반품·오류의 source row counts는 전체 원본 행 수를 분할한다. 월 합계 overflow는 source row 오류와 별도의 aggregation_errors로 센다. 정상 수량 합과 결과 수량 합을 Decimal로 대조하며 취소/반품 수량은 별도다. 오류가 있으면 HAS_ERRORS로 표시하고 응답에 남은 유효 subset을 완성 데이터로 취급하지 않는다.

## 상태·재현성·저장 한계

- HAS_ERRORS: 원본/집계 오류가 있어 등록 준비로 취급하면 안 됨.
- POLICY_REVIEW_REQUIRED: 계산된 preview는 있지만 명시적 확인 없음.
- TRANSFORMED_PREVIEW: 고정 정책 확인 후 preview 생성. DB 저장/승인/참조 검증 완료 상태가 아니다. 특히 master_scope=null이면 미검증 참조 경고를 유지한다.
- 모든 상태에서 persisted=false, auto_approve=false, approval_required=true. preview ID/정책 digest를 `/batches/{id}/approve`에 넘겨 승인을 대체할 수 없다.
- policy_digest는 선택한 전체 정책(확인 여부 포함), input_digest는 순서 있는 원본 SHA·정책·dataset·마스터 digest, result_digest는 집계 결과/근거/오류를 포함한다. 같은 입력/정책/마스터에서 페이지와 무관하게 같은 digest다. 실행시간은 응답 digest에 넣지 않는다.
- 현재 policy/원본 SHA 연결은 **응답/로컬 manifest**이며 영구 감사 로그가 아니다. 표준 CSV를 기존 `/batches`에 올리면 그 배치 SHA는 표준 CSV의 SHA다. 원본 판매 파일들의 SHA까지 DB에 보존되는 것처럼 말하지 않는다. 후속은 raw-file relation + immutable transformation manifest + 사용자 선택/버전 기록을 신규 설계/승인 후 구현한다.

## 자원·샘플·개인정보 한도

파일당 10 MiB, 분석 64 columns/2백만 cells, XLSX 최대 8 sheets 및 압축해제 크기 50 MiB. 변환은 최대 8 files/합계 50 MiB/250,000 rows/10,000 product-month groups. 새 3개 경로는 ASGI에서 chunked 요청도 51 MiB로 제한한다. CSV 변환은 한 행씩 읽고 파일 바이트·거래 키·집계만 유지한다. 기존 파서는 고치지 않았고 CSV/XLSX profile은 한도 내 materialization을 사용한다. XLSX 전체를 무제한 stream 처리한다고 주장하지 않는다.

컬럼당 distinct는 최대 2,048개까지 정확히 세고 포화 시 lower-bound 표시. 예시는 기본 미노출, 요청 시 최대 3개/48자, 이메일·번호 패턴은 REDACTED. 포화 후 표시는 보관 후보 안의 빈도이며 전체 top values 보장이 아니다. 휴리스틱 masking은 개인정보 식별 보증이 아니다. 대량 고유값/원본 행/거래처명/주소/금액을 응답에 싣지 않는다. 마스터/날짜 형식 cache는 요청 내부에 한정한다.

issues 최대 100개, aggregate당 trace 최대 5개, 수요·반품은 offset/limit 재요청(최대 500)으로 조회한다. stateless 재요청은 원본과 정책을 다시 전송한다. 영구 원본 저장 기반 상세 trace paging은 후속이다. 메모리 수치는 [벤치마크](DATA_INGESTION_BENCHMARK.md)의 측정 범위를 읽어야 한다.

## 향후 AI 추천 경계 (설계만, 미구현)

입력 envelope: contract_version, dataset_id, file/sheet의 경로 제거 이름, 표준 entity 설명, 필수 필드/단위/업무 역할, 제한된 profiles, 기존 후보·반증·HOLD와 사용자 질문. 전체 원본/전체 마스터/개인정보는 보내지 않는다. 외부 전송은 사용자/조직 정책 및 필드 allowlist 승인 후 별도 구현한다.

AI 출력 제안 예 (아직 실행 가능한 API 계약이 아님):

```json
{
  "contract_version": "ai-mapping-proposal-draft",
  "suggested_entity": "monthly_demand",
  "column_mappings": [{"source": "상품번호", "target": "product_id", "reason": "코드 후보", "requires_user_confirmation": true}],
  "proposed_operations": [{"operation": "NORMALIZE_DATE", "source": "주문일자", "target": "period", "granularity": "MONTH"}],
  "unresolved_questions": ["취소·반품·단위 정책 확인 필요"]
}
```

후속 JSON Schema는 additionalProperties=false, mapping 최대 64/작업 최대 8/질문 최대 10, entity/target/operation enum, 각 operation별 허용 parameter oneOf로 제한한다. 서버는 schema → 선택 entity의 target field → 파일 내 유일 source → dataset 일치 → 수량/단위/참조 → 고정 연산 순서/업무 정책 → 사용자 확인을 다시 검사한다. AI의 suggested_entity는 분류기에 대한 별도 제안일 뿐 승인된 entity를 바꾸지 못한다.

AI에는 DB/파일 쓰기·임의 코드 실행·승인·오류 무시 도구를 주지 않는다. 헤더/예시 안의 프롬프트 인젝션은 untrusted data로 구분하고 system instruction으로 승격하지 않는다. 과신/잘못된 의미 추론·외부 정보 전송·토큰 비용·지연·모델 변경 위험을 남기고, provider/model/prompt/schema version과 입력·출력 digest로 재현 범위를 기록한다. 먼저 lexical+profile 기준을 개선하고 임베딩 후보 검색의 top-k/비용을 측정한 뒤 미해결 사례에만 LLM을 비교한다.

## 팀원별 다음 연결

- 김대영: 본 백엔드/DTO/벤치마크, 향후 저장 정책·manifest·인증 검토. 공통 계약 변경 검토자.
- 이훤: `modules/file_classifier/`의 entity 분류 구현. 현재 분류 API/DTO를 유지하고 백엔드 `MappingReply`를 분류 결과로 오용하지 않는다.
- 정마나미: `frontend/`에 분석→후보/반증→정책 확인→preview/제외/오류→기존 업로드·승인 UI를 연결한다. reference 미검증/HOLD/부분 유효 subset을 성공 승인으로 표시하지 않는다. 코드 변경 요청은 이 문서/실제 OpenAPI에 기반한다.
- 이희원: 합성 판매 정책의 날짜·취소·반품·팩=EA 의미를 검토하고 다른 기업/원장에는 보편화하지 않는다. `modules/planning_engine/` 생성기·계산식은 이번에 수정하지 않는다.
