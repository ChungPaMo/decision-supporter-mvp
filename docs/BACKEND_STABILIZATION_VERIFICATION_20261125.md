# 백엔드 안정화 및 서비스 통합 검증

2026-11-25 KST, 메인 Windows PC. 시작 `main`의 복구 검증 변경 6개는 `a22ea37eda8e26ee84f65404abc1d68d2760635a`로 원격에 반영했다. 아래 안정화 검증과 변경을 담은 커밋 제목은 `fix: complete backend stabilization and end-to-end verification`이다.

## OpenAPI 업무 API 전수 목록

현재 [OpenAPI 스냅샷](../contracts/openapi.json)의 업무 경로 **48개 operation**을 포함한다. 입력은 DTO, multipart 및 질의 필드로 표시했다. 오류 열은 OpenAPI에 선언된 상태이며 공통 응답으로 선언만 된 경로가 포함될 수 있다. 실측 여부는 SQL·Edge 열의 증거를 따른다. 테스트명은 [backend/tests](../backend/tests)의 파일명에서 `test_`를 생략했다.

| Operation | 구현·DB·범위 | 입력 | 성공 / 선언된 오류 | 거래·중복 | 현재 UI | 단위·계약 테스트 | 실DB 증거 | 실제 브라우저 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /batches` | 배치 · 데이터셋별 SQL | status, limit, offset, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 자료 넣기·기록 | batches_api / batch_service / db_rules | 개발·회귀 실제 GET | 목록·상세로 상태 복원 |
| `POST /batches` | 배치 · 데이터셋별 SQL | multipart, dataset_id | 201 / 404,409,413,415,422,500,501,503 | 원본과 배치 원자 저장·파일 중복 409 | 자료 넣기·기록 | batches_api / batch_service / db_rules / db_scheduled_receipts | 회귀 실제; 반려는 기존 실DB 이력 | 201/200 |
| `GET /batches/{batch_id}` | 배치 · 데이터셋별 SQL | batch_id, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 자료 넣기·기록 | batches_api / batch_service / db_rules | 개발·회귀 실제 GET | 목록·상세로 상태 복원 |
| `POST /batches/{batch_id}/approve` | 배치 · 데이터셋별 SQL | ApproveRequest, batch_id, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 락·digest·SHA·동시 승인; 상태와 업무행 원자 저장 | 자료 넣기·기록 | batches_api / batch_service / db_rules / db_scheduled_receipts | 회귀 실제; 반려는 기존 실DB 이력 | 201/200 |
| `POST /batches/{batch_id}/reject` | 배치 · 데이터셋별 SQL | RejectRequest, batch_id, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 상태 전이·재반려 거절 | 자료 넣기·기록 | batches_api / batch_service / db_rules / db_scheduled_receipts | 회귀 실제; 반려는 기존 실DB 이력 | 미실행 |
| `POST /batches/{batch_id}/revalidate` | 배치 · 데이터셋별 SQL | RevalidateRequest, batch_id, dataset_id | 200 / 404,409,413,415,422,500,501,503 | version 비교·검증 상태 원자 갱신 | 자료 넣기·기록 | batches_api / batch_service / db_rules / db_scheduled_receipts | 회귀 실제; 반려는 기존 실DB 이력 | 201/200 |
| `GET /boms` | 승인 자료 · 데이터셋별 SQL | product_id, bom_id, active_only, limit, offset, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 자료/예측/계획에서 사용 | product_master / bom_inventory / capacity_registration / db_dataset_e2e | 개발 읽기·회귀 실제 자료 | 예측선택·승인된 자료 참조 |
| `GET /capacity` | 승인 자료 · 데이터셋별 SQL | limit, offset, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 자료/예측/계획에서 사용 | product_master / bom_inventory / capacity_registration / db_dataset_e2e | 개발 읽기·회귀 실제 자료 | 예측선택·승인된 자료 참조 |
| `POST /classifications` | 분류 엔진 · 파일/요청 한도, DB 없음 | ClassificationInput | 200 / 404,409,413,415,422,500,501,503 | 없음 | 현재 새 화면 직접 연결 없음 | document_sort / classification_registration / module_integration | DB 없음 | 미실행 |
| `POST /classifications/documents` | 분류 엔진 · 파일/요청 한도, DB 없음 | multipart | 200 / 404,409,413,415,422,500,501,503 | 없음 | 문서 모아 분류 | document_sort / classification_registration / module_integration | DB 없음 | 미실행 |
| `POST /classifications/file` | 분류 엔진 · 파일/요청 한도, DB 없음 | multipart | 200 / 404,409,413,415,422,500,501,503 | 없음 | 파일 분류 | document_sort / classification_registration / module_integration | DB 없음 | 200 |
| `GET /datasets` | 데이터셋 레지스트리 · SQL · 데이터셋/관리 입력 | 없음 | 200 / 404,409,413,415,422,500,501,503 | 조회 | 데이터셋 선택 | datasets / db_ingestion_history | 개발·회귀 실제 GET | GET 선택 200 |
| `POST /datasets` | 데이터셋 레지스트리 · SQL · 데이터셋/관리 입력 | DatasetCreate | 201 / 404,409,413,415,422,500,501,503 | 생성 트랜잭션·ID 충돌 409 | 등록 화면 없음 | datasets / db_ingestion_history | 생성은 기존 실DB 이력 | 미실행 |
| `GET /datasets/{dataset_id}` | 데이터셋 레지스트리 · SQL · 데이터셋/관리 입력 | dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 데이터셋 선택 | datasets / db_ingestion_history | 개발·회귀 실제 GET | 미실행 |
| `GET /demand/monthly` | 승인 자료 · 데이터셋별 SQL | product_id, period_from, period_to, limit, offset, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 자료/예측/계획에서 사용 | product_master / bom_inventory / capacity_registration / db_dataset_e2e | 개발 읽기·회귀 실제 자료 | 예측선택·승인된 자료 참조 |
| `POST /dev/forecasts` | 개발 합성 예측 · DB 없음 | DevForecastRequest | 200 / 422,500,503 | 없음 | 현재 새 화면 직접 연결 없음 | forecast_api | DB 없음 | 미실행 |
| `POST /exports/plans/xlsx` | DEMO Excel · 메모리 | PlanExportRequest | 200 / 413,422 | 없음 | 현재 화면 대신 구 UI DEMO | exports | DB 없음 | 새 화면 미실행 |
| `GET /forecasts` | 승인 월수요 예측 · 데이터셋별 SQL | limit, offset, dataset_id | 200 / 404,409,422,500,501,503 | 조회 | 수요 예측·기록 | forecast_runs / db_dataset_e2e | 개발·회귀 실제 | 실제 조회 |
| `POST /forecasts` | 승인 월수요 예측 · 데이터셋별 SQL | ForecastRunRequest, dataset_id | 200,201 / 404,409,422,500,501,503 | 실행 및 입력 저장·동일 실행 200 | 수요 예측·기록 | forecast_runs / db_dataset_e2e | 개발·회귀 실제 | 201 및 결과 표시 |
| `GET /forecasts/{execution_id}` | 승인 월수요 예측 · 데이터셋별 SQL | execution_id, dataset_id | 200 / 404,409,422,500,501,503 | 조회 | 수요 예측·기록 | forecast_runs / db_dataset_e2e | 개발·회귀 실제 | 실제 조회 |
| `GET /health` | 서버 상태 · SQL 연결 점검 | 없음 | 200 / 503 | 없음 | Shell | health | 개발 및 회귀 HTTP | 연결 끊김 배너 |
| `POST /ingest/ai-document-analysis` | 선택형 분석 · 외부 기능 기본 비활성, 합성 출처 가드 | multipart, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 운영 배치 자동 승인 없음 | 매핑 AI 직접 UI 미연결 | upstage_integration | 외부 호출 미실행 | 미실행 |
| `POST /ingest/ai-mapping-review` | 선택형 분석 · 외부 기능 기본 비활성, 합성 출처 가드 | multipart, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 운영 배치 자동 승인 없음 | 매핑 AI 직접 UI 미연결 | upstage_integration | 외부 호출 미실행 | 미실행 |
| `POST /ingest/classified-mapping` | 가공·분석; 선택적으로 승인 참조 SQL | multipart, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 저장 없음 | 분류·매핑 후보 | ingest_api / ingestion_assistance / classified_mapping / xlsx_table_selection | 옵션 경계의 기존 실DB db_ingestion_assistance; 이번 READ ONLY Edge | 200 |
| `POST /ingest/mapping-suggestions` | 가공·분석; 선택적으로 승인 참조 SQL | multipart, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 저장 없음 | 매핑 후보 | ingest_api / ingestion_assistance / classified_mapping / xlsx_table_selection | 옵션 경계의 기존 실DB db_ingestion_assistance; 이번 READ ONLY Edge | 200 |
| `POST /ingest/preview` | 메모리 분석 | multipart | 200 / 422 | 저장 없음 | 단독 미리보기 | ingest_api / ingestion_assistance / classified_mapping / xlsx_table_selection | 별도 테스트 | 미실행 |
| `POST /ingest/profile` | 가공·분석; 선택적으로 승인 참조 SQL | multipart, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 저장 없음 | 컬럼 프로파일 | ingest_api / ingestion_assistance / classified_mapping / xlsx_table_selection | 옵션 경계의 기존 실DB db_ingestion_assistance; 이번 READ ONLY Edge | 200 |
| `POST /ingest/transform-preview` | 가공·분석; 선택적으로 승인 참조 SQL | multipart, offset, limit, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 저장 없음 | 판매 원장 Preview | ingest_api / ingestion_assistance / classified_mapping / xlsx_table_selection | 별도 테스트 | 미실행 |
| `GET /ingest/transformations` | 판매 원장 변환 이력 · 데이터셋별 SQL | limit, offset, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | SalesTransformPanel | ingestion_history / xlsx_transformation_history / db_ingestion_history | 기존 실DB 이력·XLSX·롤백 증거; 이번 지정 C02에는 미포함 | 이번 미실행 |
| `POST /ingest/transformations` | 판매 원장 변환 이력 · 데이터셋별 SQL | multipart, dataset_id | 200,201 / 404,409,413,415,422,500,501,503 | 원본·정규 CSV 배치·이력 원자 저장; 같은 입력 200 | SalesTransformPanel | ingestion_history / xlsx_transformation_history / db_ingestion_history | 기존 실DB 이력·XLSX·롤백 증거; 이번 지정 C02에는 미포함 | 이번 미실행 |
| `GET /ingest/transformations/{transformation_id}` | 판매 원장 변환 이력 · 데이터셋별 SQL | transformation_id, offset, limit, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | SalesTransformPanel | ingestion_history / xlsx_transformation_history / db_ingestion_history | 기존 실DB 이력·XLSX·롤백 증거; 이번 지정 C02에는 미포함 | 이번 미실행 |
| `POST /ingest/xlsx-layout` | 메모리 분석 | multipart, sheet, row_start, row_limit, col_start, col_limit | 200 / 404,409,413,415,422,500,501,503 | 저장 없음 | 시트·범위 | ingest_api / ingestion_assistance / classified_mapping / xlsx_table_selection | 옵션 경계의 기존 실DB db_ingestion_assistance; 이번 READ ONLY Edge | 200 |
| `GET /integrations/modules` | 모듈 상태 · 메모리 | 없음 | 200 / 404,409,413,415,422,500,501,503 | 없음 | 현재 새 화면 직접 연결 없음 | module_integration | DB 없음 | 미실행 |
| `GET /inventory` | 승인 자료 · 데이터셋별 SQL | item_type, item_id, as_of_date, limit, offset, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 자료/예측/계획에서 사용 | product_master / bom_inventory / capacity_registration / db_dataset_e2e | 개발 읽기·회귀 실제 자료 | 예측선택·승인된 자료 참조 |
| `GET /materials` | 승인 자료 · 데이터셋별 SQL | material_id, q, limit, offset, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 자료/예측/계획에서 사용 | product_master / bom_inventory / capacity_registration / db_dataset_e2e | 개발 읽기·회귀 실제 자료 | 예측선택·승인된 자료 참조 |
| `GET /plan-executions` | 계획 이력 · 데이터셋별 SQL | limit, offset, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 계획·기록 상세 | plan_executions / db_dataset_e2e / db_scheduled_receipts | 회귀 실제 | 목록·상세 200 |
| `POST /plan-executions` | 계획 이력 · 데이터셋별 SQL | PlanExecutionCreate, dataset_id | 200,201 / 404,409,413,415,422,500,501,503 | 입력 지문 중복 200·동시 저장 단일 행 | 계획·기록 상세 | plan_executions / db_dataset_e2e / db_scheduled_receipts | 회귀 실제 | 201/200 |
| `GET /plan-executions/{execution_id}` | 계획 이력 · 데이터셋별 SQL | execution_id, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 계획·기록 상세 | plan_executions / db_dataset_e2e / db_scheduled_receipts | 회귀 실제 | 목록·상세 200 |
| `GET /plan-executions/{execution_id}/candidates` | 계획 이력 · 데이터셋별 SQL | execution_id, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 계획·기록 상세 | plan_executions / db_dataset_e2e / db_scheduled_receipts | 회귀 실제 | 상세 투영과 별개 엔드포인트는 미실행 |
| `GET /plan-executions/{execution_id}/decisions` | 계획 이력 · 데이터셋별 SQL | execution_id, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 계획·기록 상세 | plan_executions / db_dataset_e2e / db_scheduled_receipts | 회귀 실제 | 상세 투영과 별개 엔드포인트는 미실행 |
| `POST /plan-executions/{execution_id}/decisions` | 검토·반려 구현 · SQL; APPROVE 501 | PlanDecisionRequest, execution_id, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 검토 원자 감사 기록·version·digest | 계획 이력 상세 | plan_executions / db_dataset_e2e | 기존 실DB 이력; 이번에는 승인 501 경계만 | 조회 화면; 상태 변경 미실행 |
| `GET /plan-executions/{execution_id}/export.xlsx` | 공식 Excel · 승인 실행 SQL 가드 | execution_id, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 읽기; 미승인 409 | 공식 출력 활성 버튼 없음 | exports / plan_executions | 가드 테스트; 정상 발행 미검증 | 미실행 |
| `POST /planning-inputs/preview` | 계획 입력/계산 · 데이터셋별 SQL | PlanCommand, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 입력 READ ONLY; 저장 없음 | /planning-inputs는 현재 새 화면 직접 연결 없음 | planning_input_diagnostics / real_planning_integration / db_scheduled_receipts | 개발·회귀 실제 | 미실행 |
| `POST /plans` | 계획 입력/계산 · 데이터셋별 SQL | LegacyPlanPreviewCommand, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 입력 READ ONLY; 저장 없음 | 생산계획 | planning_input_diagnostics / real_planning_integration / db_scheduled_receipts | 개발·회귀 실제 | 200 및 계획 비교 |
| `POST /plans/what-if` | 계획 입력/계산 · 데이터셋별 SQL | PlanCommand, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 입력 READ ONLY; 저장 없음 | 생산계획 | planning_input_diagnostics / real_planning_integration / db_scheduled_receipts | 개발·회귀 실제 | 200 및 계획 비교 |
| `GET /products` | 승인 자료 · 데이터셋별 SQL | product_id, q, limit, offset, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 자료/예측/계획에서 사용 | product_master / bom_inventory / capacity_registration / db_dataset_e2e | 개발 읽기·회귀 실제 자료 | 예측선택·승인된 자료 참조 |
| `GET /routings` | 승인 자료 · 데이터셋별 SQL | limit, offset, dataset_id | 200 / 404,409,413,415,422,500,501,503 | 조회 | 자료/예측/계획에서 사용 | product_master / bom_inventory / capacity_registration / db_dataset_e2e | 개발 읽기·회귀 실제 자료 | 예측선택·승인된 자료 참조 |
| `GET /scheduled-receipts` | 입고 원장 · 데이터셋별 SQL | as_of_date, limit, offset, po_id, material_id, state, dataset_id | 200 / 404,409,422,500,501,503 | 동일 READ ONLY 스냅샷에서 개수·목록 | 자료 넣기·계획 | scheduled_receipts_api / db_scheduled_receipts | 개발·회귀 실제 GET 200 | CSV 승인 후 실제 조회 |

## API 결함과 설계 경계

- `POST /ingest/transformations`는 이미 같은 입력에서 기존 이력을 200으로 반환했으나 OpenAPI에는 201만 있었다. 응답 본문 형식을 바꾸지 않고 `TransformationDetail`의 200 응답을 선언하고 생성 스냅샷과 계약 테스트를 갱신했다. 기존 HTTP 201/200 회귀도 통과했다. [라우터](../backend/app/api/ingest_history.py) · [계약 회귀](../backend/tests/test_frontend_fixtures.py)
- 현재 경로에서 `TODO`·`FIXME`·`return NotImplemented` 업무 핸들러는 발견되지 않았다. 데모 Excel과 합성 개발 예측은 명시된 동작이다. 분류·계산 모듈의 501은 모듈 가용성 경계, 배치·이력·계획 API의 501은 영구 저장 설정 경계다. 문서 분석·AI 매핑 보조는 기본 비활성 경계 및 단위 대역만 검증했고 외부 호출을 하지 않았다.
- 생산계획 정식 APPROVE 501은 유지한다. 정책 결정 범위는 인증 주체와 검토·결재 역할, 후보 선택 근거, HARD 위반 및 UNVERIFIED 처리, 예외 승인 이력, 실행 version·입력 지문 확인, 동일 승인 경합, 승인 후 공식 Excel의 접근·추적이다. 현재 REVIEW/REJECT와 이력 조회는 지원한다. [결재 정책 경계](../backend/app/plans/approval.py) · [실행 서비스](../backend/app/plans/service.py)

## 실제 Edge·FastAPI·PostgreSQL

`chungpamo_regression` 0010, `CHUNGPAMO-2027`의 공식 합성만 기준이다. LEGACY는 교차 읽기에 사용했다. 공식 E2E Uvicorn은 8001, Vite는 5174, Edge는 headless다. 단계별 HTTP 응답, 배치·실행 ID, 해시, 스크린샷은 Git 제외 `.artifacts/planning-postgresql-20261124/long-e2e-ui-20261125/`에 있다.

| 실제 브라우저 플로우 | 결과 |
| --- | --- |
| 공식 CSV 10개 선택 → 파일 개수가 붙은 분류 버튼 → 분류 결과 | 통과. `/classifications/file` 실제 응답. 문구 전체 일치 대신 개수가 붙는 버튼 이름 패턴으로 찾았다. |
| 공식 10개 파일 순서 등록·검증·승인 | 전부 **화면 조작**. 전체 승인 버튼에서 참조 순서대로 10회 등록 201 및 승인 200, API 보조 쓰기 0건. 등록된 원본 SHA와 승인 요청의 `expected_source_sha256`을 기록했다. |
| XLSX 시트·표 범위 및 컬럼 매핑 | 같은 회귀 DB READ ONLY의 별도 Edge에서 합성 XLSX `Catalog`, A1:C3, 실제 프로파일·매핑 후보·수동 선택 200. 공식 10개는 CSV이므로 표 선택은 별도 합성 XLSX 경로로 재현했다. |
| 수동 재검증, 입고 행 표시·새로고침 | 동일 실행 데이터에서 합성 HOLD를 UI로 등록 201, 수동 매핑과 재검증 200, 버전 1→2와 `READY_FOR_APPROVAL`. 공식 입고 조회의 MR-N3·10,000 kg을 표시하고 새로고침 후 승인 상태를 복원했다. |
| 승인 수요 예측 → BASE·재사용 | 예측 201·27행. BASE Preview 200 전후 저장 0건. BASE 저장 201, 동일 화면 재실행 200·동일 ID. MR-N3 92,100 kg. |
| What-if와 저장, 이력 복원 | 5,000 kg 및 0 변경 각각 Preview 200·저장 201, MR-N3 각각 87,100/82,100 kg. 부모와 자식 상세 및 새로고침 통과. |
| 오류 화면 | 브라우저 네트워크 차단 시 앱 경고 표시. 실제 DB를 중지하는 503 시나리오는 미실행이다. |

첫 세부 검사에서 개별 등록 버튼 이름이 11개 요소와 일치했고, 입고 원장 행 대신 파일명 행을 잡았다. 두 건은 테스트 선택자의 실패다. 동일 상태에서 상세 패널과 MR-N3 셀로 범위를 좁힌 보완으로 각각 실제 수동 등록·재검증과 원장 조회가 통과했다. 기존 권한 경계와 데이터는 유지했다.

### 실DB 무결성

- 중복 업로드 409·재승인 409, 오래된 재검증 버전 409·승인 digest 409 `RESULT_CHANGED`, 파일 SHA 불일치 409 `BATCH_SOURCE_MISMATCH`.
- 필수 컬럼 누락 `MAPPING_HOLD`, 승인 차단 409, 잘못된 숫자·날짜·단위와 누락 참조는 `HAS_ERRORS`. 존재하지 않는 배치·계획 및 타 데이터셋 배치·계획 접근 404. 기간 13개월 및 음수 What-if 422, 부모에 없는 PO 422 `PLAN_OVERRIDE_UNSUPPORTED`.
- 두 승인 요청은 200·409, 같은 신규 계획을 동시에 저장하면 201·200과 동일 ID 1개였다. SQL 오류 주입은 500 `PERSISTENCE_ERROR`로 배치 version과 상태를 보존했고 실패한 입고 업무 행은 0건이었다. 승인 원장 UPDATE·DELETE는 PostgreSQL SQLSTATE `23514`였다.
- 지정 C02 실DB pytest 1통과·0실패·0건너뜀. 종료 시 CP 29개만 `TRUNCATE … RESTRICT`로 정리하고 양쪽 업무 행 0건·기준정보 및 0010을 확인했다. PowerShell 출력 인코딩 때문에 최초 정리 사전검사가 멈췄으며, 읽기 전용으로 전체 출처와 세션을 재검증한 뒤 한 번 정리했다.

## 성능 기초값

Windows 메인 PC, 로컬 FastAPI 및 PostgreSQL 16.6, CHUNGPAMO-2027의 공식 10배치, 9제품·3개월·3후보. P50/P95는 순위법으로 계산했다. 15개 표본의 P95는 이 표에서 최댓값이다. 단위는 ms다.

| 읽기·계산 | 표본 | 평균 | P50 | P95 | 최대 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 배치 목록 | 15 | 15.4 | 15.1 | 20.3 | 20.3 |
| 입고 원장 | 15 | 16.3 | 16.8 | 17.7 | 17.7 |
| 예측 상세 | 15 | 13.7 | 13.2 | 19.7 | 19.7 |
| 계획 상세 | 15 | 46.7 | 44.3 | 93.2 | 93.2 |
| BASE Preview | 15 | 70.2 | 67.0 | 105.0 | 105.0 |
| What-if Preview | 15 | 95.7 | 86.1 | 132.6 | 132.6 |
| 수동 재검증 API | 15 | 11.9 | 11.1 | 15.3 | 15.3 |

읽기·계산은 실제 HTTP 응답 본문 수신까지 측정했다. 수동 재검증은 FastAPI TestClient 및 실제 회귀 PostgreSQL로 매 요청의 SAVEPOINT를 완료한 뒤 외부 트랜잭션을 롤백한 별도 측정이다. 이 수치는 HTTP 및 durable commit 비용을 포함하지 않는다.

| 브라우저 쓰기 | 표본 | 평균 | P50 | P95 | 최대 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 파일 등록·검증 | 10 | 29.8 | 27.8 | 47.6 | 47.6 |
| 배치 승인 | 10 | 52.2 | 36.6 | 141.5 | 141.5 |
| 예측 생성 | 1 | 619.1 | 619.1 | 619.1 | 619.1 |
| 계획 저장·재사용 | 4 | 466.8 | 556.0 | 605.2 | 605.2 |

읽기 SQL 단일 표본에서 배치 목록 SELECT 3개·15,170 B, 원장 SELECT 3개·884 B, 예측 상세 SELECT 3개·9,817 B, 계획 상세 SELECT 7개·172,594 B였다. 계획 상세는 보관 스냅샷 전체를 반환해 상대적으로 크다. 성능 개선 판단 전에는 더 큰 제품·기간 표본과 쿼리/직렬화 시간을 따로 측정한다. 이 단일 표본에서 N+1을 확정하거나 인덱스를 변경하지 않았다.

## Migration 실패 검증과 백업

신규 `chungpamo-c02-0010-failure-rehearsal`과 전용 볼륨, network none 및 포트 미공개 조건에서 과거 0009 백업을 복구했다. 각 실패 후 revision 0009, 60개 테이블, 데이터·스키마·승인·예측 지문이 일치했다.

| 시나리오 | 실제 결과 |
| --- | --- |
| 잘못된 DB 대상 | 별도 격리 가드가 실제 연결의 DB명을 비교해 Alembic 시작 전 차단 |
| 예상 밖 레지스트리 | 격리 트랜잭션에 불일치하는 합성 레코드를 추가하자 기존 0010이 적용을 거절. 실패 후 그 행도 롤백 |
| 잠금 제한 | `public.import_batch` 배타 잠금과 350 ms 제한으로 SQLSTATE `55P03`. 먼저 변경을 시작한 스키마도 복구 |
| 한 스키마 DDL 직후 오류 | 실제 첫 스키마 원장 생성 직후 SQLSTATE `22012`로 중단. 두 원장 및 revision의 부분 적용 0건 |

리허설 컨테이너·볼륨만 삭제했다. 증거는 Git 제외 `.artifacts/planning-postgresql-20261124/stability-migration-20261125/`에 남겼다. 개발 `0010`의 공식 PO 승인 후 백업은 `.artifacts/planning-postgresql-20261124/development-approved-0010-backup-20261125/chungpamo-0010-approved-po.dump`, **342,605 bytes**, SHA-256 `37034ac6007c78a5d0909a3bd41582e2f419b7f799c22710d96968da448c773c`다. TOC 테이블 62개와 전체 디코딩 통과, 개발 DB 전후와 이전 0008/0009 백업 지문 일치. 이 새 아카이브의 복구 실행은 미실행이다.

## 팀 인계와 중간평가 시연

- 정마나미 — 부모의 `input_snapshot.scheduled_receipts`를 사용하고 `null`·`[]`를 구분한다. 현재 원장과 다른 발주는 서버에서 422가 검증됐다. 브라우저에서는 현재 원장과 부모가 동일한 5,000 kg·0 흐름이 통과했다. [프론트 인계](FRONTEND_BACKEND_CONTRACT_FOLLOWUP_20261125.md)
- 이훤 — 표준 파일 및 XLSX 분류는 실브라우저 확인을 마쳤다. 예정 입고는 현재 파일명 힌트·수동 확인 경로다. 별도 자동 분류 계약과 HOLD 반례 수용 여부가 남아 있다.
- 이희원 — 공식 입력에서 입고로 MR-N3 부족은 해소되지만 `UNVERIFIED`/두 `INFEASIBLE` 판정이 유지된다. 이번 범위에서 계산 알고리즘 결함을 확인하지 못했다. 정식 결재 시 제약·예외 및 계획 가능성의 업무 기준을 협의한다.
- 김대영 — API 계약의 변환 재사용 응답을 보완했다. 계획 결재 인증과 정책이 합의되면 거래·감사·공식 Excel 검증을 추가한다. AI 매핑 연구와 Solar 사용은 보류했다.

개발 DB 0010의 기존 합성 PO를 보여주는 읽기 시연은 백엔드 프로세스에 `PGOPTIONS=-c default_transaction_read_only=on`과 `PERSISTENCE=postgres`를 지정하고 루트에서 `powershell.exe -NoProfile -File scripts/backend.ps1`로 시작한다. 프론트 폴더에서 `VITE_API_URL=http://127.0.0.1:8000`과 허용 개발 출처를 맞추고 `npm.cmd run dev -- --host 127.0.0.1`을 실행한다. 자료·기존 예측·입고 조회와 3개월 계획 Preview를 보여준다. 이 시연에서는 새 저장을 수행하지 않는다.

쓰기까지 보여줄 때는 새로 식별·승인한 전용 0010 회귀 환경에서 공식 생성기의 9개 파일과 합성 `PO-2701-001` CSV를 사용한다. 사용자 순서는 CHUNGPAMO-2027 선택 → 분류 → 참조 순서 승인 → 입고 확인 → 2026-12-31 기준 3개월 예측 → 2027년 1~3월 Preview → BASE 저장·동일 입력 재사용 → 5,000 및 0 kg What-if 저장 → 부모·자식 이력·새로고침이다. DB URL은 Git 제외 전용 설정으로만 주입하고 사용한 포트를 검증한다. 현 회귀 DB는 종료 정리로 업무 행 0건이다. 개발 DB를 데모 저장 대상으로 사용하지 않으며 정식 APPROVE와 공식 Excel 발행은 시연 완료 기능에서 제외한다. 실제 기업 데이터로 검증하지 않았다.

## 회귀 결과

전체 비DB **1,423 passed / 0 failed / 69 skipped**, 변환·XLSX·OpenAPI 집중 **43 passed**, 지정 회귀 PostgreSQL **1 passed / 0 failed / 0 skipped**. 브라우저 본 실행에서 두 선택자 오류는 같은 데이터의 보완에서 통과했고, 별도 READ ONLY XLSX·매핑·네트워크 오류도 통과했다. TypeScript, Vite, `backend.ps1` 구동, 실제 OpenAPI 200 및 스냅샷 일치를 확인했다. 이 수치는 메인 PC 안정화 검증 결과다.

비DB 재실행은 루트에서 `.\.venv\Scripts\python.exe -m pytest --no-db -q`, 프론트 폴더에서 `npm.cmd run type-check` 및 `npm.cmd run build`를 사용한다. 기존 SQL 회귀는 별도 실행 권한과 회귀 URL·sentinel·업무 행 0건을 확인하고 `CHUNGPAMO_ALLOW_RECEIPT_SQL_TEST`로 `backend/tests/test_db_scheduled_receipts.py::test_actual_approved_receipts_and_parent_what_if`만 지정한다. 실제 브라우저 검증은 전용 두 서버를 띄우고 로컬 증거의 Playwright `browser.cjs` 및 `manual-validation.cjs`를 순서대로 실행했다. 이 자료는 개발 DB를 쓰기 대상으로 삼는 자동 실행기가 아니다.
