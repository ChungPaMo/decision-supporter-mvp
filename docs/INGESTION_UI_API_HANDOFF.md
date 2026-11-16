# 데이터 입력 UI ↔ API 인계

2026-11-16, 기준 main `25d94ae`. 실제 서버 계약은 [OpenAPI](../contracts/openapi.json), [입력 DTO](../contracts/interfaces/ingestion.py), [이력 DTO](../contracts/interfaces/ingestion_history.py), [배치 DTO](../backend/app/batches/schemas.py)다. 아래 API는 구현되어 있으며 화면 연결은 [변경 요청](INGESTION_UI_CHANGE_REQUEST.md)을 따른다. 이번 검증은 실제 FastAPI/분류/매핑/검증/변환/승인 서비스를 호출하고 **저장 경계만 메모리 대역**으로 교체했다. PostgreSQL 영구 저장·트리거 검증은 미실행이다. 현재 PC의 Docker/PostgreSQL 작업은 금지한다.

## 대표 데이터와 등록 순서

대표 자료는 이희원 담당 `modules/planning_engine/synthetic/generate.py`, SEED=20261115의 CHUNGPAMO-2027뿐이다. 기존 생성 파일을 먼저 읽고 없을 때만 Git 제외 .artifacts에 같은 생성기를 실행한다. [14파일 SHA manifest](../contracts/examples/ingestion_e2e_source_manifest.json)를 대조하며 기존 파일/정답/생성기는 변경하지 않는다.

| 원본/정답 | entity 또는 용도 | 실제 기준 |
| --- | --- | --- |
| upload/01_products.csv, 02_materials.csv | product, material | 제품 9, 자재 9 |
| upload/03_bom.csv, 04_inventory.csv | bom, inventory | BOM 9개/구성 27행, 재고 18행 |
| upload/06_capacity_resources.csv | capacity | 자원 6개 |
| upload/07_capacity_quantity_limits.csv, 08_capacity_hours_budgets.csv | capacity | 수량한도 3행, 시간예산 18행 |
| upload/09_routing_steps.csv | routing | 공정 27행, 9제품이 SAW1 공유, 9개 공정은 LB1 인시 동시 요구 |
| raw/transactions/판매현황_2022.csv~판매현황_2026.csv | 변환 원본 5파일 | 86,214행: 정상 83,984 / 취소 887 / 반품 1,343 |
| upload/05_monthly_demand.csv | 독립 정답 | 498 제품·월·수량·단위 행 |

제품·자재 → BOM·재고 → 자원 → 수량한도·시간예산 → Routing → 수요 순으로 승인한다. 수요는 **표준 05 파일 직접 등록 또는 판매 원장 변환 중 하나**를 사용한다. 대표 E2E는 표준 05를 정답으로만 읽고 원장 변환 결과를 등록한다. 양쪽을 모두 승인하면 같은 제품·월 중복으로 거부될 수 있다. CAPA의 수량/설비시간/인시와 Routing 동시 자원 요구량을 합치거나 같은 단위로 환산하지 않는다.

## 공통 요청·상태 원칙

- 모든 입력 보조·배치·이력·승인·조회에 `?dataset_id=CHUNGPAMO-2027`을 명시한다. 생략은 TISSUE-LEGACY이며 전체 조회나 자동 추론이 아니다. `/classifications/file`은 무저장 분류라 데이터셋을 조회하지 않는다. batch multipart의 dataset_id는 선택적 동일값 확인용이며 query를 대체하지 않는다.
- 서버가 저장 비활성이면 저장 API는 `501 PERSISTENCE_DISABLED`다. `use_approved_master=true`도 활성 저장 서버가 필요하다. 현재 PC에서 이를 켜거나 DB에 연결하지 않는다. false이면 참조 검증 미완료를 표시한다. 배포 시 기존 개발 PC의 0009 적용과 실DB 검증이 먼저다.
- 파일·entity·열 선택·정책·마스터 옵션·dataset이 바뀌면 이전 응답/digest를 폐기한다. 비동기 응답은 요청 시 파일/데이터셋/요청 순번을 대조한 뒤 사용한다. 분류·후보·preview 성공은 등록/승인 성공이 아니다.
- HTTP 오류는 `detail.code/message/details`를 표시하고 대역 성공으로 대체하지 않는다. HTTP 200이어도 HOLD/HAS_ERRORS는 다음 단계 제한 상태다.

## UI 동작별 실제 계약

아래 multipart 값은 문자열이고 JSON form은 JSON.stringify로 직렬화한다. JSON body는 application/json이다. DTO 전체를 임의로 바꾸지 않고 아래 표시 필드를 읽는다.

| UI 버튼/동작 | Method·URL | 요청 | 실제 응답 DTO와 표시 | 성공/HOLD·다음 단계 |
| --- | --- | --- | --- | --- |
| 파일 선택 → **파일 유형 추천 요청** | `POST /classifications/file` | multipart file, sample_row_limit=0. 동의한 경우만 5행(서버 최대 20) | ClassificationOutput: recommended_entity, hold, candidates[{entity,score,reasons}], reasons, module_version | 200 추천도 사용자 검토. HOLD이면 직접 유형 선택/판매 변환 안내. 자동 배치 생성 없음 |
| **검토한 추천 유형 선택 / 유형 직접 선택** | 로컬 선택. 선택 후 `POST /ingest/classified-mapping` | multipart file, 선택적 entity, column_overrides JSON, sample_row_limit, use_approved_master | ClassifiedMappingReply: source_sha256, classification, selected_entity, selection_method, mapping, next_action, transform_preview_url | USER_SELECTION 또는 CLASSIFIER_RECOMMENDATION. HOLD에서 entity 미선택 시 mapping=null/SELECT_ENTITY_OR_TRANSFORM. URL은 선택지 안내이며 모든 HOLD가 판매 원장은 아님 |
| **컬럼 구조 분석** | `POST /ingest/profile` | multipart file, include_samples=false, use_approved_master=false(또는 승인 서버에서 true) | ProfileReply: source_sha256, master_scope/master_digest, samples_included, sheets[].columns[] | col은 1부터, column/normalized_column, empty_ratio/type_candidates/format_match_rates/uncertainty_reasons 표시. 기본 예시 값 없음. persisted=false |
| **컬럼 후보 보기 / 매핑 적용 전 확인** | `POST /ingest/mapping-suggestions` | multipart file, entity, column_overrides JSON 기본 {}, use_approved_master | MappingReply: entity/source_sha256, sheets[].status/existing_mapping/suggestions/holds | 5 entity만 지원. suggestions[].col/source_column/suggestions/unresolved_reasons. 후보 target_field/method/evidence/requires_review 표시. MappingCandidate에는 score/confidence 필드가 없다 |
| **선택한 열로 다시 확인** | 위 mapping-suggestions 재호출 또는 `POST /ingest/preview` | file, entity, column_overrides JSON, 선택적 default_unit/sheet | MappingReply 또는 PreviewOut: status, master_data_checked, sheets[].mapping/holds/issues/records | 숫자 col을 overrides 값으로 보내지 않는다. 헤더 이름 또는 A/B/C 등 열 문자 사용. 미확정 필수 열은 HOLD. preview는 저장하지 않고 마스터 조회도 안 함 |
| **판매 변환 정책 확인 / 미리보기** | `POST /ingest/transform-preview` | multipart files 1~8회 반복, policy JSON, use_approved_master. query offset=0/limit=500 | TransformReply: status, policy, sources, policy_digest/input_digest/result_digest, operations/counts/quantity_reconciliation/records/returns/issues/warnings | POLICY_REVIEW_REQUIRED/HAS_ERRORS는 저장 금지. user_confirmed=true로 다시 계산하여 TRANSFORMED_PREVIEW를 검토. persisted=false |
| **표준 파일 등록** | `POST /batches` | multipart file/entity/source_type/source_note/created_by, 선택적 column_overrides/default_unit/sheet | 201 BatchDetail: batch_id/dataset_id/status/file/settings/version/result_digest/validation/approval_blockers | 원본·검증 보관이며 승인 전. product/material/bom/inventory/monthly_demand/capacity/routing 지원 |
| **판매 변환 이력 저장·배치 생성** | `POST /ingest/transformations` | multipart files/policy/use_approved_master + expected_result_digest/created_by/source_note | 201 신규/200 재사용 TransformationDetail: transformation_id, dataset_id, batch_id, batch_status, 지문들, persisted=true, preview | 별도 /batches 재업로드 불필요. 서버가 전체 표준 CSV와 승인 전 배치를 원자 생성. 업무 수요 미반영. preview.persisted=false는 계산 계약 보존 |
| **등록 배치 확인 / 서버 재검증** | `GET /batches/{batch_id}`, `POST /batches/{batch_id}/revalidate` | GET은 query. 재검증 body 아래 예시 | BatchDetail: settings, validation.sheets[].holds/issues, version/result_digest, approval_blockers | MAPPING_HOLD/HAS_ERRORS는 승인 불가. 재검증은 설정 전체 교체. 변환 연결 배치는 {}, default_unit=null, sheet=null 유지 |
| **검증 결과 승인** | `POST /batches/{batch_id}/approve` | approved_by, expected_result_digest=**배치** result_digest | BatchDetail.status=APPROVED, approved_by/approved_at/approved_record_count | READY_FOR_APPROVAL/차단 사유 없음 + 사용자의 명시적 클릭. 변환 result_digest로 승인하면 RESULT_CHANGED |
| **반려** | `POST /batches/{batch_id}/reject` | rejected_by, reason | BatchDetail.status=REJECTED | 최종 상태. 승인으로 해석하지 않는다 |
| **이력 보기 / 새로고침** | `GET /ingest/transformations`, `GET /ingest/transformations/{transformation_id}` | dataset query, list limit=50/offset=0, detail limit=500/offset=0 | TransformationPage/TransformationDetail. 현재 batch_status와 batch_id; 상세 preview.policy/원본 SHA/결과/지문 | 원본 바이트 다운로드 API는 없음. 원본 SHA는 preview.sources[].sha256. 사용자 확인은 preview.policy.user_confirmed. 승인 사실은 batch_status와 BatchDetail에서 확인 |
| **승인 자료 확인** | `GET /products`, `GET /materials`, `GET /boms`, `GET /inventory`, `GET /demand/monthly`, `GET /capacity`, `GET /routings` | dataset query + limit/offset. 월수요는 limit 최대 1000 | 제품/자재/BOM/재고/수요 Page DTO. CAPA/Routing은 dict(items/total/limit/offset), items에 section/payload/batch_id/version/result_digest/source_sha256/approved_at | 승인 전 자료는 승인 조회에 나타나지 않는다. 대표 월수요 total=498, 수량 합 1,812,610 EA |

## 두 종류의 열 매핑

표준 entity 매핑은 `column_overrides={"demand_qty":"C"}`처럼 표준 필드→헤더/열 문자다. RapidFuzz Top-3는 검토 후보이며 자동 적용하지 않는다. method=LEXICAL_SIMILARITY의 evidence에는 RANKING_ONLY_NOT_CONFIDENCE가 포함된다. 분류 score도 확률이 아니다.

**판매 원장의 7개 의미는 policy.columns로 직접 확인한다.** order_date/product_id/quantity/unit/status/order_id/line_id이며 월수요 mapper의 period/demand_qty와 다른 역할이다. 현재 mapping-suggestions가 이 7개 역할 전체를 추천하는 API는 아니다. 새 API를 가정하지 말고 profile의 열 목록에서 사용자가 고른 값을 아래 정책에 넣는다. 주문일과 출고일, 수량과 단가/금액, 정상·취소·반품을 혼동하지 않는다. raw 원장을 monthly_demand로 바로 등록하거나 1순위 후보만으로 집계하지 않는다.

현재 변환은 CHUNGPAMO_SYNTHETIC_SALES v1.0의 SYNTHETIC_ONLY 정책이다. 다른 기업 원장에 보편 정책으로 적용하지 않는다. 정상만 포함, 취소 제외, 반품 절댓값 별도, 팩/EA→EA factor 1, 제품·월 합계, 거래 키 중복 오류다. 86,214→498과 정상 수량 합 1,812,610, 취소 11,240 제외, 반품 8,670 별도를 확인한다.

<!-- contract:SalesTransformPolicy -->
```json
{
  "dataset_id": "CHUNGPAMO-2027",
  "policy_id": "CHUNGPAMO_SYNTHETIC_SALES",
  "version": "1.0",
  "columns": {
    "order_date": "주문일자", "product_id": "제품코드", "quantity": "수량",
    "unit": "단위", "status": "구분", "order_id": "주문번호", "line_id": "행번호"
  },
  "user_confirmed": true
}
```

위 JSON을 **policy form 문자열**로 보낸다. files는 원본 파일 5개로 같은 이름을 반복한다. `/ingest/transformations`에는 직전 확인 preview.result_digest를 expected_result_digest form으로, created_by=INGEST-REVIEWER와 실제 합성 출처 설명을 추가한다. preview/save에서 파일 순서와 use_approved_master를 같게 유지한다. 확인 false→true도 정책 digest가 달라지므로 확인 후 preview를 다시 계산한다. 총 수요/반품 페이지는 total/returns_total과 offset/limit로 표시하며 자른 500행만 재업로드하지 않는다.

표준 배치 등록의 multipart 예: file=01_products.csv, entity=product, source_type=SYNTHETIC, source_note=이희원 CHUNGPAMO-2027 합성 생성기 SEED 20261115, created_by=INGEST-REVIEWER, query dataset_id=CHUNGPAMO-2027. CAPA/Routing도 이 등록 API를 재사용한다. 두 유형은 분류 HOLD이며 profile은 가능하지만 추천/일반 preview의 entity로 지원하지 않는다. 정확 양식·수동 override를 /batches에서 검증한다.

<!-- contract:RevalidateRequest -->
```json
{"expected_version": 1, "column_overrides": {"demand_qty": "C"}, "default_unit": null, "sheet": null}
```

expected_version은 현재 배치 조회값으로 교체한다. 위 예시는 일반 월수요 배치용이다. 변환 연결 배치의 설정을 바꾸려면 새 정책/변환 검토가 필요하다.

<!-- contract:ApproveRequest -->
```json
{"approved_by": "REVIEWER-01", "expected_result_digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

예시 지문은 자리표시자다. 실제 요청은 **GET 배치의 result_digest**를 그대로 사용한다. 변환/입력/정책/manifest 지문과 섞지 않는다. 저장 후 APPROVED가 될 때까지 승인 완료 표시를 하지 않는다. TransformationDetail의 approval_required=true는 절차 표시이며 최종 승인 사실을 뜻하지 않는다.

## 오류 표시와 다음 동작

| 상황 | 실제 상태/코드 | 버튼/복구 |
| --- | --- | --- |
| 빈 CSV·손상 XLSX·지원 밖 확장자 | FILE_EMPTY/XLSX_CORRUPT 422, UNSUPPORTED_TYPE 415 | 파일 다시 선택. 성공으로 대체하지 않음 |
| 불명확한 유형/제품·자재 구분 | ClassificationOutput.hold=true, 추천 없음 | 유형 직접 선택. CAPA/Routing도 수동 선택 |
| 필수 열 누락/복수 후보 | mapping HOLD, batch MAPPING_HOLD, holds[].code/field/message/candidates | 사용자 열 선택→재검증. 저장 전 후보와 배치 검증 상태를 구분 |
| 날짜/수량/단위·미등록 참조 | batch HAS_ERRORS, validation.sheets[].issues[].severity/code/message/location(row/col/cell_ref) | 원본/선택 열 수정 또는 같은 dataset 마스터 승인 후 재검증 |
| 변환 부분 오류 | TransformReply.HAS_ERRORS, issues[].code/location/field, issues_total | 유효 subset을 완성 데이터로 저장하지 않음. TransformIssue에는 message/raw_value가 없으므로 code를 표시 |
| 확인 누락/오류/빈 정상 수요 저장 요청 | TRANSFORM_BLOCKED 409 | 정책 확인·오류 해결 후 preview 재생성 |
| 원본·정책·마스터/지문 변경 | RESULT_CHANGED 409 | 최신 preview/배치 다시 확인, 지문 갱신 |
| 중복 등록/승인 | 동일 이력 재요청 200 재사용; DUPLICATE_UPLOAD/KEYS_ALREADY_APPROVED/ALREADY_APPROVED 409 | 기존 ID·상태 재조회. 다른 CSV 바이트로 같은 월수요를 보내면 업로드 후 승인 시 키 충돌일 수도 있음 |
| 다른 dataset UUID/정책·form 불일치 | TRANSFORM_NOT_FOUND/BATCH_NOT_FOUND 404, DATASET_MISMATCH 409 | 선택 dataset 확인. 다른 dataset에서 대신 찾지 않음 |
| 서버 저장 불가/동시 수정 | PERSISTENCE_DISABLED 501, DB_UNAVAILABLE 503, VERSION_CONFLICT 409 | 등록/승인 성공 표시 금지. 연결·현재 버전 확인 |

한도: 파일당 10MiB, 변환 8개/합계 50MiB/250,000행/10,000 그룹, 요청 본문 51MiB. 분류 메타 최대 20시트/100열/샘플 20행/셀 500자이며 분석은 8시트/64열 등 별도 한도가 있어 큰 파일은 명시적 413/422를 표시한다. 이 제한을 조용히 자르거나 실제 기업 데이터를 외부 API로 보내지 않는다.

재현·실행 결과·실DB 이관은 [이번 검증 기록](INGESTION_API_E2E_VERIFICATION_20261116.md)을 따른다.
