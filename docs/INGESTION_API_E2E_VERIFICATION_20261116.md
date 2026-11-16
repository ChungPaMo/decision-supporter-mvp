# 데이터 입력 API E2E 검증 — 2026-11-16

시작·확인한 최신 main: `25d94aec1d3eba63f2896100c3c37df01acf5d2b`, 미커밋 변경 없음. origin fetch 후 로컬/원격 일치를 확인했다. 기존 main에서만 작업하고 브랜치/PR은 만들지 않았다. 최종 Commit·Push SHA는 완료 응답과 Git 이력에서 확인한다. 이전 914 passed/63 skipped는 이전 실행 기록이며 아래가 이번 결과다.

## 대표 자료와 보존

이희원 담당의 **CHUNGPAMO-2027 공식 합성 생성기(SEED=20261115)**와 원본/정답을 재사용했다. 현재 PC에는 modules/planning_engine/synthetic/data가 없어 같은 생성기를 Git 제외 .artifacts/ingestion-e2e-dataset에 실행했다. 이후 해당 파일을 읽기 전용으로 재사용했으며 생성기·소유 폴더·기존 정답을 수정하지 않았다. 기존 파일의 SHA가 다르면 덮어쓰거나 자동 재생성하지 않고 실패한다.

[원본 manifest](../contracts/examples/ingestion_e2e_source_manifest.json)는 표준 9파일과 판매 원장 5파일의 SHA 14개를 고정한다. API 흐름 전후에도 모두 동일함을 확인했다. 성공 흐름을 임의의 P1/가상 마스터로 대체하지 않고 공식 제품·자재를 실제 배치 API로 등록·명시적 승인했다. 오류/애매함/중복·확인 처리용 소규모 자료만 공식 파일의 헤더/첫 행에서 별도로 파생했고 negative 이름과 테스트 주석으로 구분했다. 기존 생성기의 dirty 오류 자료도 그대로 사용했다.

## 실제 API 연결 결과

모든 API는 FastAPI TestClient의 실제 라우터/DTO/파서/분류기/RapidFuzz 추천/검증/변환/승인 서비스를 호출했다. 테스트 저장소·CAPA SQL 읽기/쓰기에만 명시적 메모리 대역을 사용했다. 운영 서버의 저장 비활성 상태를 성공 응답으로 바꾸는 기능은 추가하지 않았다. 기본 설정에서 /batches·/ingest/transformations의 501도 그대로 검사했다.

| 경로·사용자 단계 | 이번 결과 |
| --- | --- |
| /classifications/file | 공식 표준 5종 product/material/bom/inventory/monthly_demand 추천. CAPA 3파일·Routing HOLD. 원장 HOLD와 월수요 변환 안내·모듈 버전 확인 |
| /ingest/classified-mapping | 제품·자재 불명확성은 HOLD/mapping=null, 사용자가 entity를 고르면 USER_SELECTION. 저장 없음 |
| /ingest/profile | 원본 SHA·형식 통계·같은 CP 승인 마스터 scope/digest 확인, 기본 샘플 값 없음 |
| /ingest/mapping-suggestions | Top-3·근거·requires_review, 원장의 일반 월수요 매핑 HOLD. 수동 열 선택과 배치 재검증 연결 |
| /batches 및 /products, /materials, /boms, /inventory, /capacity, /routings | 공식 마스터·CAPA·Routing 8배치 승인 대역. 제품 9/자재 9/BOM 9(27구성)/재고 18, 자원 6/한도 3/예산 18/Routing 27. 같은 9제품의 SAW1 공유와 9공정의 LB1 동시 인시 요구를 실제 DTO로 대조 |
| /ingest/transform-preview | 원본 5개 86,214행→498행을 독립 표준 05 정답과 제품·월·Decimal 수량·단위까지 일치 확인. 정책/입력/결과 지문과 원본 SHA 5개 확인 |
| /ingest/transformations | 실제 서비스가 표준 CSV+승인 전 배치+이력 생성. persisted=true와 preview.persisted=false를 구분. policy.columns/확인 상태·원본/지문·dataset/batch 연결 대조 |
| /batches/{batch_id}/approve | 저장 직후 승인자/시각/승인 건수는 null, 승인 수요 0. 변환 지문을 승인에 쓰면 409. 조회한 **배치 지문**으로 명시적 승인 후 498행 조회 |
| /ingest/transformations 목록/상세, /demand/monthly | 승인 전/후 batch_status, batch_id·지문 유지. 승인 후 498행·같은 배치 출처·독립 정답 일치. 다른 dataset UUID는 404 |

공식 05_monthly_demand.csv는 raw 경로에서 정답으로만 사용했다. 원장 변환으로 생성한 수요를 9번째 배치로 승인했고 동일 수요를 표준 파일로 이중 승인하지 않았다. 같은 결과라도 CSV 바이트가 다르면 업로드 SHA 중복과 제품·월 승인 키 중복은 서로 다른 시점의 검사이므로 인계 문서에 구분했다.

원장 행 수는 정상 **83,984**, 취소 **887**, 반품 **1,343**, 원본/집계 오류 **0**이다. 정상 수량 **1,812,610 EA**와 월수요 합계가 같고 취소 **11,240** 제외, 반품 **8,670** 별도다. 반품을 정상 수요에서 빼지 않는다. 정책은 기존 CHUNGPAMO_SYNTHETIC_SALES v1.0이며 새 정책·모델 실험은 없다.

## 오류·사용자 확인 검사

신규 독립 오류/경계 25개와 대표 원장 경로 1개, 인계 계약 검사 4개를 추가/확장했다. 빈 CSV·손상 XLSX, 분류 애매함, 한 열의 복수 후보, 필수 열 누락, 날짜/수량/단위 오류, 잘못된 열 선택→오류→수동 수정 복구를 확인했다. 다른 dataset에만 있는 제품 사용과 배치 UUID 접근은 차단됐다. 변환 부분 오류·미확인 정책·원본/정책/지문 변경은 저장되지 않았다. 중복 변환 요청은 같은 ID를 재사용하고 자동 승인하지 않았으며 중복 파일/승인 요청도 차단됐다.

기존 대량 원장 회귀의 이름과 498행 비교는 유지하면서 서비스만 별도로 호출하던 흐름을 전체 공식 자료의 API 흐름으로 확장했다. 별도 ingestion benchmark 호출과 임의 제품 시드는 제거했다. 이전 48건 추천 연구 테스트는 이미 저장된 결과와 fixture SHA/별칭 독립성을 확인하도록 변경해 이번 작업에서 scoring/timing 비교를 반복하지 않았다. 추천 운영 코드는 그대로다.

## 이번 실행 결과

| 검사 | 실제 결과 |
| --- | --- |
| 대표 86,214→498 TestClient E2E 초기 실행 | 1 passed, 9.17초. SQL/실DB 승인 아님 |
| 오류/HOLD·사용자 확인 + 기존 추천 회귀 집중 검사 | 33 passed (신규 25 + 기존 8) |
| UI 인계 URL·요청 JSON의 OpenAPI/DTO 검증 | 4 passed |
| 최종 전체 Python --no-db | **943 passed / 0 failed / 63 skipped**, 20.06초 |
| OpenAPI·Schema·기존 응답 예시 동기화 | 전체 pytest에서 통과. API 변경 없어 생성물 변경 없음 |
| frontend type-check / Vite build | 통과 / 통과. 소스 수정 없음 |
| pip check / 저장소 보안 검사 | 문제 없음 / findings=0 |

63개 DB 테스트는 연결 차단 상태에서 제외했으며 통과가 아니다. Starlette/httpx 기존 deprecation warning 1건을 별도 기록한다. 브라우저 UI의 신규 입력 화면 E2E는 화면 미구현/담당 폴더 제한으로 실행하지 않았으며 TestClient 결과로 화면 완료를 주장하지 않는다. 기존 npm 취약점 2건의 담당자 인계 상태도 그대로이며 이번에 프론트 의존성을 변경하지 않았다.

이번 작업에서는 Docker 설치/실행/컨테이너·볼륨 명령, PostgreSQL 설치/실행/접속, 온라인 migration, DB 쓰기/E2E를 수행하지 않았다. 새 migration·API도 추가하지 않았고 backend/app/ 운영 코드, frontend/, modules/의 diff는 0이다. 메모리 상태 APPROVED와 실제 PostgreSQL 승인/영구 보존은 다르다.

## 변경 파일·나미님 인계

- backend/tests/ingestion_e2e_support.py: 공식 원본 재사용·SHA 대조·메모리 저장 경계.
- backend/tests/test_ingestion_api_e2e.py: 사용자 흐름과 오류/확인 경계. test_ingestion_sales_generated.py: 기존 대량 회귀를 공식 자료의 API 여정으로 확장.
- backend/tests/test_ingestion_ui_contract.py: 문서 URL과 3종 요청 JSON을 현재 OpenAPI/DTO로 검증. test_mapping_recommendations.py: 이전 평가 결과만 재사용.
- contracts/examples/ingestion_e2e_source_manifest.json: 기존 자료 SHA/정답 건수. 생성 CSV·원본은 Commit하지 않음.
- scripts/verify_ingestion_api_e2e.py: --no-db 집중 실행기. `.venv/Scripts/python.exe -X utf8 scripts/verify_ingestion_api_e2e.py`로 재현. 상세 결과와 JUnit은 ignored .artifacts에만 보관.
- [UI API 인계](INGESTION_UI_API_HANDOFF.md), [부족한 UI 변경 요청](INGESTION_UI_CHANGE_REQUEST.md), frontend_guide 링크를 추가했다. 이미 있는 분류·수동 재검증·승인/반려·배치 이력은 재개발 요청하지 않는다.

나미님 우선 사항은 선택 파일 공유와 명시적 등록, /ingest/*의 dataset query/stale 보호, 등록 전 profile/Top-3 검토, raw 정책의 **policy.columns** 선택, preview/이력/배치 지문 분리, 이력 저장 후 기존 승인 화면 연결이다. CAPA/Routing은 서버에 등록 API가 있지만 화면 Entity는 5종이고 분류 패널 설명이 오래되어 확장이 필요하다.

## 기존 개발 PC에 남긴 실DB 검사

1. 실제 서버/컨테이너·볼륨/DB/역할·개발/독립 회귀 DB 격리를 확인하고 승인 배치·예측 이력을 읽기 전용으로 기록한다.
2. 기존 0009를 모든 등록 스키마(보관 상태 포함)에 안전하게 적용하고 기존 데이터/0001~0008 보존을 확인한다.
3. 실제 SQL의 원자 저장/실패 롤백·원본 SHA·불변 manifest·지연 트리거·동시 재요청·로컬 FK/데이터셋 격리·새 스키마 v2를 검증한다.
4. 공식 자료 8마스터+원장→498수요 경로를 실제 승인/예측 입력까지 확인하고 사전/사후 개발 데이터를 대조한다. UI 구현 후 같은 dataset의 브라우저 E2E를 실행한다.
5. 기존 회귀 fixture의 초기화/DROP/TRUNCATE는 대상 식별과 해당 실행의 별도 승인 후에만 수행한다. 현재 PC나 개발 DB/chungpamo_test로 대신 실행하지 않는다.
