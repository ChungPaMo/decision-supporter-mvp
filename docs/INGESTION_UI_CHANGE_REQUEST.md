# 데이터 입력 화면 변경 요청 — 정마나미님

2026-11-16, 기준 main `25d94ae`. frontend/src/screens/DataUploadScreen.tsx, components/ClassificationPanel.tsx, services/api.ts, store/productionStore.ts, types/api.ts를 읽고 작성했다. **이번 작업에서는 frontend를 수정하지 않았다.** 실제 요청/응답·버튼 순서는 [API 인계](INGESTION_UI_API_HANDOFF.md)를 따른다. 새 API/가상 응답 필드는 요청하지 않는다.

## 이미 구현된 기능 — 재개발 요청 아님

- 실제 데이터셋 목록/선택, 데이터셋별 배치 선택 기억, 전환 시 업무 상태 초기화와 scoped 요청의 오래된 응답 폐기가 있다.
- 5종 entity 선택, CSV/XLSX 등록·출처 입력, 배치 목록·상세·검증 행/오류 표시가 있다. 서버 미확인·저장 비활성이면 등록/승인을 막는다.
- 분류 파일 선택/요청, 최대 5행 샘플 동의, 후보/근거/HOLD, 사용자 추천 유형 선택이 있다. 유형 선택은 배치를 만들지 않는다.
- 배치 HOLD의 원본 열/열 문자 수동 입력, expected_version 기반 재검증, 역할 코드/지문 기반 명시적 승인·반려, 승인 자료 조회가 있다.

## 부족한 부분과 구체적 요청

| 우선순위·화면 | 현재 구현 | 변경/추가 기능 | 실제 API·필드 | HOLD/오류·사용자 확인 |
| --- | --- | --- | --- | --- |
| P0 · 데이터 업로드/파일 선택 | 등록 input의 onChange가 즉시 uploadBatch를 호출한다. 분류 패널의 선택 파일은 별개이며 onChoose는 entity만 바꾼다 | 선택한 원본을 분류·분석·매핑 확인과 공유하고 **명시적 등록 버튼**에서 기존 uploadBatch를 호출하도록 연결. 기존 분류/업로드 UI를 재사용 | /classifications/file, /ingest/classified-mapping, /batches. source_sha256, selected_entity/selection_method, classification.hold | 파일/유형이 바뀌면 이전 결과 폐기. HOLD에서 유형 직접 확인. 분류 성공만으로 등록/승인하지 않음 |
| P0 · API 클라이언트/데이터셋 | /batches 등은 dataset query를 붙이고 오래된 응답을 폐기한다. UNSCOPED에 /ingest/ 전체가 포함되어 있다 | 새 profile/mapping/transform/history 메서드와 DTO 타입 추가. 선택 dataset_id를 명시하고 동일한 stale-response 보호 적용. 기존 scoped 배치 동작 재사용 | /ingest/profile, /ingest/mapping-suggestions, /ingest/classified-mapping, /ingest/transform-preview, /ingest/transformations 및 상세 | 다른 dataset의 결과·UUID 재사용 금지. 변경 전 요청의 이력/지문/선택 정책도 폐기. /ingest/transformations는 영구 API이므로 unscoped 취급 금지 |
| P0 · 컬럼 분석/후보 검토 | 프로파일/Top-3 추천 UI·API 메서드는 없다. 배치 생성 뒤 HOLD 수동 입력은 있다 | 등록 전에 열 목록/형식/빈값/반증/기존 매핑과 Top-3를 표시하고 선택한 값을 기존 column_overrides·재검증 입력으로 연결 | ProfileReply.sheets[].columns, MappingReply.sheets[].suggestions/holds/existing_mapping. 후보 target_field/method/evidence/requires_review | 후보 score/confidence 필드를 만들지 않음. 점수는 확률 아님. 필수 미확정은 HOLD, 사용자가 헤더명 또는 열 문자로 확인 |
| P0 · 판매 원장 변환 정책 | 정책·변환 미리보기 화면과 메서드가 없다 | 합성 판매 전용 모드에서 파일 5개, 주문일·제품·수량·단위·상태·주문/행번호의 7개 열을 **policy.columns**로 선택. 고정 정상/취소/반품/팩 정책을 확인 | SalesTransformPolicy, /ingest/transform-preview. policy.user_confirmed, columns/date_formats/unit_mapping | 월수요 column_overrides와 섞지 않음. SYNTHETIC_ONLY임을 표시하고 일반 기업 원장에 자동 적용하지 않음. 확인 후 preview를 재계산 |
| P0 · 변환 결과 검토 | 현재 검증 화면은 기존 BatchDetail.validation만 표시 | 정상/취소/반품/오류 행 수, 수량 대조, 월수요/별도 반품, 연산·원본 SHA·지문·경고를 표시 | TransformReply.status/counts/quantity_reconciliation/operations/sources/records/returns/issues/issues_total/warnings/total/returns_total | HAS_ERRORS의 유효 subset을 성공으로 표시하지 않음. TransformIssue에는 code/location/field만 있다. POLICY_REVIEW_REQUIRED 저장 버튼 비활성. 페이지 일부를 완성 CSV처럼 재등록하지 않음 |
| P0 · 명시적 이력 저장/등록 | 변환 저장과 이력 화면이 없다 | 확인된 preview의 원본/정책/지문을 명시적으로 /ingest/transformations에 보내고 반환 batch_id를 기존 배치 검토 화면의 선택 배치로 연결 | expected_result_digest=변환 지문, created_by/source_note. TransformationDetail.transformation_id/batch_id/batch_status/persisted/preview | 저장 완료와 승인 완료를 분리. 201 신규/200 재사용. 반환 배치를 다시 조회하고 사용자가 기존 승인 버튼 클릭. 별도 /batches 이중 등록 금지 |
| P0 · 기존 검증·승인 화면 | 상세 재조회·재검증·승인·반려가 이미 있다 | 생성 배치 연결과 표시만 확장. 배치 지문/변환 지문을 분리하고 변환 연결 배치의 열 설정 변경을 제한 | GET /batches/{batch_id}, revalidate, approve. BatchDetail.result_digest/status/approval_blockers/settings/version | 변환 지문을 approve에 보내지 않음. canonical {}, null, null 설정 유지. RESULT_CHANGED/VERSION_CONFLICT는 새 조회·검토. 기존 승인·반려 구현을 다시 만들지 않음 |
| P1 · 변환 이력 탭 | 기존 배치 이력만 있다 | 선택 dataset의 변환 목록과 상세 원본 SHA/정책/근거/결과·현재 배치 상태 표시 | GET /ingest/transformations, GET /ingest/transformations/{transformation_id}. TransformationPage, TransformationDetail | batch_status와 BatchDetail로 승인 확인. preview.persisted=false는 당시 계산 계약이다. 원본 바이트 다운로드 API는 없으므로 버튼을 가정하지 않음 |
| P1 · CAPA/Routing 등록 | Entity 타입/ENTITY_ORDER는 5종만 지원. 분류 패널 설명은 아직 CAPA/Routing 저장 미제공이라고 쓴다 | 기존 배치 등록/검증 UI를 7종으로 확장하고 설명 정정. 신규 별도 승인 UI 대신 공통 배치 흐름 재사용 | POST /batches entity=capacity/routing, GET /capacity, GET /routings. 정확 표준 헤더/column_overrides | 분류 HOLD가 정상. 일반 mapping-suggestions/ingest preview의 지원 entity가 아님. 자원→예산/한도→Routing 순서를 안내하고 시간기준/수량 단위를 분리 |

모든 저장 동작은 연결된 기존 개발 PC의 검증된 서버에서만 사용한다. 현재 PC에서 저장 API의 501을 우회하거나 Mock 성공·자동 승인을 추가하지 않는다. 원본 파일/셀 값을 외부 AI API로 전송하는 작업도 요청하지 않는다.

## 화면 수용 기준

공식 CHUNGPAMO-2027 자료로 제품·자재·BOM·재고·자원·한도/예산·Routing을 검토한 뒤 판매 원장 86,214행을 498행 정답과 대조한다. 정상/취소/반품 분리와 미승인 상태를 표시하고 사용자의 정책 확인·등록·승인 클릭을 각각 유지한다. 형식 오류/애매함/누락/잘못된 선택/다른 dataset/부분 오류/미확인/지문 변경/중복은 다음 단계나 승인 성공으로 바꾸지 않는다. 이 API 경로의 메모리 E2E 결과와 실제 PostgreSQL 검증을 구분한다.
