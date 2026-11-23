# 파일 분류·매핑·변환 이력 연결

> 2026-11-23: XLSX의 `table_selection`/`table_selections`는 미리보기와 저장에 공통으로 적용한다. 선택 범위와 역할별 원본 열 위치는 기존 불변 manifest의 `result.sources[]`에 보존한다. 새 마이그레이션은 필요하지 않으며 저장 후 기존 배치 승인으로 이어진다. [요청·오류·화면 인계](XLSX_SELECTION_PERSISTENCE_HANDOFF.md) · [비DB 검증·PostgreSQL 체크리스트](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md)

2026-11-16, 기준 main `0762ebff937a3e4cebbd63f608d9fd0963bf024c`. 김대영 담당 backend/contracts/tests/scripts/docs만 수정한다. 분류기·계획 엔진·frontend 구현은 변경하지 않았다.

## 분류와 매핑

업로드용 `file_classifier.classify()`는 AVAILABLE=True인 규칙 기반 rules-0.2.0이다. `/classifications`와 `/classifications/file`은 실제 추천 또는 HOLD를 반환한다. 모듈 비활성/미구현은 501, 실행·출력 계약 실패는 원문을 숨긴 500이다. 최신 분류기 README의 문서 종류·임베딩 연구는 별도 도구이며 HTTP 경로에 연결하지 않았다. AI·외부 추론 호출은 없다.

`POST /ingest/classified-mapping?dataset_id=CHUNGPAMO-2027`은 multipart file, 선택적 entity, column_overrides JSON, sample_row_limit=0, use_approved_master=false를 받는다. 기본 헤더만 전달하며 샘플은 명시한 최대 20행만 전달한다. 추천 entity를 기존 recommend()에 전달하지만 미확정 열/fuzzy 후보를 자동 적용하지 않는다. selection_method는 CLASSIFIER_RECOMMENDATION 또는 명시적 entity의 USER_SELECTION이다.

HOLD이면 selected_entity=null, mapping=null, selection_method=REQUIRED, next_action=SELECT_ENTITY_OR_TRANSFORM이다. 사용자는 entity를 선택해 다시 요청하거나 응답의 transform_preview_url(`/ingest/transform-preview`)에서 판매 정책을 검토한다. URL 안내는 모든 HOLD 파일이 판매 원장이라는 판정이 아니다. 제품·자재·BOM·재고·월수요만 지원하며 CAPA/Routing은 기존처럼 보류한다. 기존 mapping-suggestions/profile/preview/transform-preview API도 유지한다.

## 명시적 이력 저장

`POST /ingest/transformations?dataset_id=CHUNGPAMO-2027`은 기존 preview와 같은 files, policy, use_approved_master에 다음 form을 추가한다.

| form | 의미 |
| --- | --- |
| expected_result_digest | 직전에 검토한 preview의 64자리 소문자 SHA256 |
| created_by | 필수 역할 코드, 예: INGEST-REVIEWER. 로그인/전자서명 증명 아님 |
| source_note | 필수 합성 자료 출처 설명, 최대 1,000자 |

policy.dataset_id와 query가 같고 user_confirmed=true여야 한다. 원본을 재계산해 digest가 다르면 RESULT_CHANGED 409다. 원본/집계 오류·정상 수요 없음·정책 미확인은 TRANSFORM_BLOCKED 409다. preview와 저장에서 approved master 옵션을 같게 유지하고 마스터가 바뀌면 새로운 preview를 검토한다. 파일명은 경로/제어문자 없이 200자 이내여야 한다.

신규 저장은 201, 동일 input_digest 재요청은 기존 transformation/batch ID를 200으로 반환한다. 최초 검토자·출처를 보존한다. 입력 순서·정책·데이터셋·마스터가 digest에 포함된다. 동일 표준 CSV가 다른 활성 배치로 이미 등록되어 있으면 기존 DUPLICATE_UPLOAD 409로 전체 롤백한다. 기존 배치에 근거를 사후 추가하지 않는다. 반려된 이력도 동일 입력 재요청으로 덮어쓰지 않는다.

한 트랜잭션에서 전체 변환 계산 → 검토 digest 대조 → 서버가 전체 월수요 CSV 생성 → 기존 BatchService.create_batch로 SYNTHETIC 승인 전 배치 생성 → 불변 manifest/원본 저장을 수행한다. 화면의 첫 500행만 저장하지 않는다. 오류가 발생하면 배치·표준 CSV·이력·원본이 모두 롤백된다. 배치는 기존 마스터 검증에 따라 READY_FOR_APPROVAL 또는 HAS_ERRORS일 수 있다.

저장 요청은 업무 수요 행을 쓰거나 승인하지 않는다. 반환된 batch_id로 기존 `GET /batches/{batch_id}`를 조회하고 **배치의 result_digest**를 사용해 기존 `/batches/{batch_id}/approve`를 명시적으로 호출한다. 변환 result_digest와 배치 검증 result_digest는 서로 다른 지문이다. 연결 배치 재검증은 canonical 설정({}, default_unit=null, sheet=null)을 유지한다. 다른 열 해석은 차단하며 정책 변경은 새 변환 검토를 거친다. 승인·재검증 시 원본/전체 결과/출력 바이트 연결도 확인한다.

## 조회와 보존 범위

`GET /ingest/transformations?dataset_id=...&limit=50&offset=0`은 메타데이터 목록이다. `GET /ingest/transformations/{transformation_id}?dataset_id=...&limit=500&offset=0`은 검증한 이력과 결과 페이지다. 다른 데이터셋 UUID는 404이며 fallback하지 않는다. 생략은 TISSUE-LEGACY다.

상위 persisted=true는 저장된 이력이다. 내부 preview.persisted=false는 당시 순수 계산 계약을 그대로 보존한 것이며 업무 행 승인 여부가 아니다. batch_status는 현재 배치 상태다. auto_approve=false/approval_required=true는 검토 절차를 설명하며 실제 승인 사실은 배치에서 확인한다.

manifest는 engine_version, transformation/batch/dataset ID, 검토 역할·출처, 전체 policy(선택 열 매핑 포함), 연산 목록, counts·합계·분리 반품, 원본 SHA 목록, 모든 월수요 결과, 행 위치 예시, 마스터 코드·단위 snapshot, 출력 CSV SHA를 보존한다. manifest_digest로 전체 근거를 검증한다. 원본 바이트는 source 테이블에 보존하지만 조회 API로 노출하지 않는다. 행 위치는 그룹당 최대 5개 예시이며 전체 계보가 아니다.

상세 조회·승인 검증은 저장된 마스터 snapshot으로 원본을 재실행한다. 현재 마스터를 과거 근거로 대체하지 않는다. 재현 불일치는 실패하며 덮어쓰지 않는다. 현재 reducer-1.0만 지원한다. 향후 버전 변경 시 과거 실행기·검증 경로를 보존해야 한다. 최대 250,000행 재실행 비용이 있으며 원본 다운로드/삭제/보존기간/검증 캐시는 후속이다.

## PostgreSQL 배포 조건

신규 Alembic **0009**는 기존 0001~0008과 dataset_schema_v1.py를 변경하지 않는다. 온라인으로 public.dataset의 모든 스키마(보관 상태 포함)에 ingestion_transformation/ingestion_transform_source를 추가한다. schema_name은 서버 계산값과 대조한다. 업무 행 UPDATE, DROP/TRUNCATE, downgrade는 하지 않는다. offline SQL은 public 예시이며 전체 데이터셋 배포 스크립트가 아니다.

불변 UPDATE/DELETE 트리거, 로컬 batch FK, 고정 dataset CHECK, 원본 SHA·크기 CHECK, 지연 제약 트리거로 보호한다. 지연 트리거는 원본 수·인덱스·SHA/파일명·총 크기와 배치 출력 SHA를 대조한다. Python은 전체 manifest·replay를 대조한다. input_digest advisory lock과 유일 제약으로 동시 저장을 직렬화한다. 트리거·동시성의 실제 PostgreSQL 동작은 별도 실DB 시험 대상이다.

새 데이터셋은 dataset_schema_v2.py로 모든 표를 먼저 만든 뒤 history row type을 사용하는 트리거 함수를 컴파일한다. FK/함수 search_path는 해당 데이터셋에 고정한다. 앱 배포 전에 모든 스키마에 0009가 필요하며 현재 PC에서는 **마이그레이션 미적용**이다. 인증정보를 생성·추측하거나 기존 DB에 임의 접속하지 않았다.

## 프론트엔드 담당 연결 요청

유형 추천·수동 확인 → 매핑 후보 검토 → 판매 정책/합계/제외·반품 검토 → 명시적 이력 저장 → 반환 batch 재조회 → 기존 승인 순서다. 미리보기 변경 시 이전 digest/페이지를 폐기한다. 저장 성공을 승인 성공으로 표시하지 않는다.

현재 frontend 클라이언트는 `/ingest/`를 unscoped로 분류한다. 새 매핑/이력 요청은 **선택 dataset_id를 query에 명시**하고 데이터셋 전환 후 이전 응답을 폐기해야 한다. `/ingest/transformations*`는 영구 API다. 화면/API 클라이언트 수정은 나미 담당이며 이번 작업에서는 변경하지 않았다.

## AI 후속 경계

현재 AI 호출은 없다. [연구](AI_ASSISTED_DATA_INGESTION_RESEARCH.md)와 [후속 envelope](AI_MAPPING_INTEGRATION_DESIGN.md)를 유지한다. retriever-eval README/results의 후보 순위와 오매핑 위험은 자동 적용 근거가 아니다. 향후 규칙이 보류한 열만 dataset/entity/schema/alias/model 버전과 함께 후보 검색에 전달하고 의미 반증·사용자 선택을 거친다. SQL/실행 코드·자동 승인·불확실한 top-1 적용은 허용하지 않는다. 저장된 사용자 매핑 규칙은 아직 NOT_IMPLEMENTED이며 이력의 policy.columns를 전역 규칙으로 자동 재사용하지 않는다.

이번 실행 결과·환경 제한은 [검증 기록](INGESTION_INTEGRATION_VERIFICATION_20261116.md)을 참고한다.
