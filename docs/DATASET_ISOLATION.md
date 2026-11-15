# 데이터셋 격리 — 경로 조사·구현·실제 검증

기준 main fd0bc7f3c77d786193acf85259ead54c26a27541, 2026-11-15. API/migration 수정 전에 아래 격리 경로·설계를 먼저 기록했다. 처음에는 Docker가 꺼져 DB 작업을 보류했고, 사용자가 켠 뒤 전용 대상을 재확인해 실제 적용·등록을 완료했다.

## 격리가 필요한 경로

| 경로 | 기존 혼합 위험 | 격리 경계 |
|---|---|---|
| BatchService/SqlBatchRepository | 배치 목록/UUID 상세/원본/재검증/승인/반려와 기준 마스터 전체 조회 | 요청 데이터셋의 저장소/트랜잭션 |
| 제품·자재·BOM·재고·월수요 조회 | 페이지/total 및 참조 조회 전체 | 동일 스키마의 모든 업무 테이블·뷰 |
| capacity.preview/commit/approved_rows | 자원·제품·한도·라우팅 전체 대조 | 같은 데이터셋의 승인 자료만 조회/참조 |
| ForecastRuns create/list/get | 전체 승인 수요, 전역 UUID·중복 키 | 데이터셋별 엔진 입력/실행/결과/출처 FK |
| SqlPlanningSourceProvider | forecast UUID와 마스터/자원 전체 조합 | 같은 데이터셋 forecast·모든 입력·배치 출처 |
| PlanService/Repository | 실행/후보/검토/출력/What-if UUID | 부모/예측/배치/후보의 데이터셋 일치 |
| /dev/forecasts, /ingest/preview, 분류 및 DEMO 출력 | DB 없는 순수 요청 | 데이터셋 DB 조회를 하지 않음. 승인 증명 아님 |

## 방식 비교와 선택

모든 테이블에 dataset_id를 넣고 PK/UNIQUE/FK를 복합키로 바꾸면 행 단위 격리가 가능하지만, 현재 전역 제품/자원 PK와 많은 FK/배제 제약·승인 트리거를 다시 구성해야 한다. 단순 WHERE 필터는 전역 유일성과 교차 참조를 해결하지 못한다.

이번 설계는 **동일 DB의 스키마별 격리 + 공개 dataset 마스터 + root 소유권**이다. TISSUE-LEGACY는 기존 public 업무 테이블을 그대로 사용하고, 다른 데이터셋은 서버가 결정한 별도 스키마에 동일한 최종 구조/독립 PK·FK·뷰·트리거를 둔다. 같은 product_id/resource_id를 허용하되 FK는 같은 스키마만 참조한다. search_path에 다른 데이터셋이나 public fallback을 넣지 않는다. 이는 권한/인증 멀티테넌시 구현이 아니다.

이름 공간과 search_path 동작은 [PostgreSQL 16 Schemas](https://www.postgresql.org/docs/16/ddl-schemas.html), 구조 복제 옵션은 [CREATE TABLE](https://www.postgresql.org/docs/16/sql-createtable.html)을 따른다. LIKE만으로 FK/트리거/뷰가 모두 복제됐다고 간주하지 않고 catalog에서 읽어 로컬 객체로 다시 연결했다. 이 방법은 SQL 권한 자체의 보안 경계가 아니며 앱 역할로 직접 SQL을 실행할 수 있는 사용자의 접근 권한을 분리하지 않는다.

public.dataset이 dataset_id/이름/설명/source_type/status/생성시각/created_by(nullable)/내부 schema_name을 관리한다. import_batch/forecast_run/plan_execution의 dataset_id는 생성 이후 바뀌지 않는 root 소유권이며, 자식 행은 스키마 내부 FK와 root로 상속한다. 데이터셋 ID는 접근 권한을 의미하지 않는다. schema_name은 클라이언트가 정하거나 SQL에 직접 전달하지 않는다.

기존 root에 dataset_id를 default TISSUE-LEGACY로 추가하는 것은 기존 JSON/SHA/result_digest/승인 상태·UUID를 갱신하지 않는다. migration은 비합성/알 수 없는 출처/교차 참조/예상 외 객체를 발견하면 중단해야 한다. 신규 스키마는 구조와 단위 사전만 만들며 기존 업무 행을 복사하지 않는다. 기존 테이블 삭제·재생성·PK 삭제는 하지 않는다.

Alembic **0008**은 `public.dataset`을 추가하고 `public.import_batch`, `public.forecast_run`, `public.plan_execution`에 dataset_id FK/고정 소속 CHECK를 추가한다. 신규 스키마에는 기존 27개 테이블의 구조·독립 키/제약/뷰·트리거와 단위 사전 6건만 생성했다. root 테이블의 DEFAULT/CHECK는 소속 ID로 고정된다. 자식의 FK는 같은 스키마로 향하며 공유 참조는 public.dataset 레지스트리뿐이다. 기존 0001~0007 원문은 변경하지 않았다.

트랜잭션마다 `SET LOCAL search_path`를 사용하고 연결 종료 시 rollback/commit으로 복구한다. 새 스키마의 트리거 함수 12개도 자기 스키마로 search_path를 고정했다. 다른 데이터셋에서 누락 자료를 찾아오지 않는다. migration/런타임 생성은 고정 `dataset_schema_v1.py`를 공유한다. 기존 이력 재현을 위해 v1은 이후 수정하지 않고 새 버전·migration으로 확장한다.

## 호환성 결정

기존 단일 데이터셋 API 호출은 dataset_id 생략 시 **TISSUE-LEGACY만** 선택한다. 생략을 전체 조회로 해석하지 않는다. 신규 클라이언트는 `?dataset_id=CHUNGPAMO-2027`을 모든 영구 DB API에 명시한다. 존재하지 않는/보관 상태/잘못된 ID는 거부한다. dataset_id를 외부에서 바꿔 다른 데이터셋 UUID에 접근하면 해당 스키마에 기록이 없어 404이며 다른 스키마로 찾아가지 않는다.

데이터셋 컨텍스트는 업로드·조회·승인·예측·계획·결정·출력에 동일하게 적용해야 한다. PlanningInput에 명시적 식별자를 포함하고 새 실행의 digest/중복 키에 포함한다. 기존 저장 Snapshot은 원문과 digest를 보존해 읽는다. What-if도 저장 root와 forecast 및 command의 데이터셋을 교차 검사한다.

multipart의 dataset_id는 선택적인 중복 확인값이며 query와 다르면 409다. Form 값만으로 query의 legacy 기본값을 몰래 바꾸지 않는다. PlanCommand.dataset_id도 query와 명시적으로 다르면 409다. Batch 응답과 forecast/plan 실행 응답은 dataset_id를 포함한다. 일반 품목 페이지의 total/offset은 선택한 스키마에서만 계산된다.

예측 모듈의 input_digest 계약은 변경하지 않는다. 백엔드 실행 소유권·중복 키에는 데이터셋을 포함하고 `dataset_input_digest=SHA256(dataset_id, engine_input_digest)`를 별도 제공한다. PlanningInput의 forecast_input_digest는 엔진 input_digest와 대조하며 dataset_input_digest와 혼용하지 않는다. 새 CP 입력에는 forecast 원본 수요 배치까지 포함해 9개 출처를 보존한다. 기존 legacy 입력 사실·출처 구성은 유지한다.

## 데이터셋 API와 운영 절차

- GET /datasets: ID/이름/설명/source_type/status/created_at/created_by. schema_name은 비공개 서버 내부 값.
- POST /datasets: dataset_id/dataset_name/description/source_type=SYNTHETIC. 중복 409, 잘못된 ID 422. 현재 생성 주체는 미인증이므로 created_by=null이다. 인증/권한이 구현됐다는 의미가 아니다.
- GET /datasets/{id}: 없음 404. 보관 상태를 DB API에서 사용하려면 DATASET_INACTIVE 409. 현재 archive/소유권 변경 API는 제공하지 않는다.
- 모든 영구 DB URL에 `?dataset_id=CHUNGPAMO-2027`을 추가한다. DATASET_MISMATCH 409, NOT_FOUND 404, INVALID 422, EXISTS 409이며 원문 DB 오류는 노출하지 않는다.

등록은 `scripts/integrate_dataset.py --approve`로 재현한다. 전용 Docker/DB·0008 확인, 정상 CSV 비DB 계약 검증, rollback-only 격리 시험을 먼저 수행하고, 신규 데이터셋에 예상 SHA가 아닌 자료가 있으면 중단한다. 그 후 기존 API로 9파일을 순서대로 SYNTHETIC 등록·승인한다. 같은 SHA의 기존 배치는 재사용하며 다른 파일을 덮어쓰지 않는다. 생성 데이터는 기존 ignore 규칙을 유지한다.

새 PostgreSQL 테이블/열 migration은 앞으로 **모든 활성 데이터셋 스키마**를 함께 갱신해야 한다. 현재 0008의 catalog clone은 온라인 적용이 필요하다. Alembic --sql 출력은 정적 검사/참고용이며 0008 전체 배포 스크립트가 아니다. dataset 구조 자동 버전 업그레이드·보관/삭제·사용자 권한·기업 데이터셋 source_type 확대는 후속 범위다.

## 검증 상태

Docker Engine 29.4.0, 프로젝트 chungpamo-monorepo, 컨테이너 chungpamo-monorepo-db, 볼륨 chungpamo-monorepo-pgdata, 네트워크 chungpamo-monorepo-net, 127.0.0.1:55433/chungpamo·사용자 chungpamo_app를 확인했다. 기존 revision 0007·7개 APPROVED/SYNTHETIC 배치와 전체 값을 사전 기록했다. 0008 전체 rollback-only dry-run 후 온라인 적용했고 최종 revision은 0008이다.

개발 중 함수 DDL의 `%` 처리와 search_path 복원 누락을 dry-run/원자 migration rollback으로 확인·수정했다. 실패한 적용은 전체 rollback됐으며 임의 stamp나 기존 migration 수정은 없었다. 이후 새 스키마 함수의 search_path 고정을 비파괴적으로 보강했다.

기존 27개 public 테이블을 사전 값과 대조했다. 추가된 dataset_id 소유권 필드를 제외한 모든 값, 원본 바이트·SHA/result_digest·승인 시각·version·forecast UUID·입력/결과는 같았다. 기존 저장 PlanningInput도 추가 dataset 필드를 제외한 사실/출처가 이전 로컬 검증 Snapshot과 동일했다.

| 데이터 | TISSUE-LEGACY | CHUNGPAMO-2027 |
|---|---:|---:|
| APPROVED 배치 | 7 (기존 ID 유지) | 9 |
| 제품 / 자재 | 1 / 3 | 9 / 9 |
| BOM 헤더 / 라인 | 1 / 3 | 9 / 27 |
| 재고 / 월수요 | 4 / 24 | 18 / 498 |
| 자원 / 수량한도 / 시간예산 | 2 / 1 / 2 | 6 / 3 / 18 |
| Routing / 공정 / 자원 요구량 | 1 / 1 / 2 | 9 / 27 / 36 |
| 예측 실행 / 예측 행 | 1 / 1 | 1 / 27 |
| 정식 계획 실행 | 0 | 0 |

신규 예측 UUID: **d125bc5e-02a0-4622-9a1a-7f8e88aeeed3**, 기준일 2026-12-31, 3개월. CP 9제품만 예측하고 2027-01 PlanningInput에는 CP 마스터·6자원·27공정·같은 SAW1·동시 LB1 및 9개 승인 배치의 version/SHA/digest가 포함됐다. 실제 forecast UUID/엔진 지문을 대조했다. legacy UUID를 CP 요청에 쓰면 404이며 그 반대도 조회되지 않는다. 새 파일을 반복 실행해 9배치와 동일 예측을 재사용하고 중복 업로드 409를 확인했다.

| CSV/entity | batch_id | version | rows | status |
|---|---|---:|---:|---|
| 01_products.csv / product | 815fcc3f-cadf-4df4-a9e6-04e4d548d23a | 2 | 9 | APPROVED |
| 02_materials.csv / material | 22b0748c-5c51-4593-96cd-1812bbb61bc5 | 2 | 9 | APPROVED |
| 03_bom.csv / bom | b8c411f0-ab46-4270-8a44-2928d83b3386 | 2 | 27 | APPROVED |
| 04_inventory.csv / inventory | 91f251c5-b985-4813-ad9b-764f0f0f2e68 | 2 | 18 | APPROVED |
| 05_monthly_demand.csv / monthly_demand | fc3f74ae-ab92-43a2-83a0-2118cdd4673a | 2 | 498 | APPROVED |
| 06_capacity_resources.csv / capacity | c8c4001c-7a9a-4c10-a57f-17a914b7aedd | 2 | 6 | APPROVED |
| 07_capacity_quantity_limits.csv / capacity | b091c5da-f4c5-41f5-8e07-5436888ec126 | 2 | 3 | APPROVED |
| 08_capacity_hours_budgets.csv / capacity | bdb9724a-eab5-4b31-8a92-6f12367daa81 | 2 | 18 | APPROVED |
| 09_routing_steps.csv / routing | 40256eef-9dd8-4458-a942-c822da3bfc48 | 2 | 27 | APPROVED |

`scripts/integrate_dataset.py`의 PostgreSQL 검증 **9개 그룹**: 데이터셋 생성/상세/중복/잘못된 ID rollback, 타 데이터셋 제품·자원 거부, 동일 제품/자원 코드 공존, 타 자재 BOM 차단, 배치 UUID 격리, 소속 변경 차단, 모든 FK 소속 대조, 타 forecast UUID 차단·탐침 rollback, 동일 소속 TEST_DOUBLE What-if 계보와 타 소속 계획/자식 거부. 테스트 계획·임시 데이터셋은 모두 rollback했고 실제 계획 계산을 만들지 않았다.

기존 초기화 DB pytest 55개, migration downgrade/왕복, 브라우저 dataset 선택 E2E, 실제 계획 계산·정식 승인/Excel은 실행하지 않았다. 기존 55432·sisicallcall·테스트 DB에 접근하지 않았고 Docker 자원 재생성/삭제도 없었다. 화면·알고리즘 담당 파일은 변경하지 않았다.

### 회귀 및 보안

- 전체 비DB pytest **538 passed / 0 failed / 55 skipped**, 신규 데이터셋 단위 테스트 12개 포함. Starlette/httpx deprecation warning 1건. 기존 테스트 삭제·skip 전환 없이 migration chain/소유권 메타데이터를 새 계약에 맞췄다.
- 정상 생성 CSV 계약 9/9와 기존 오류 기대값 구분은 기존 synthetic 회귀 시험에서 그대로 통과했다. 생성기를 다시 실행했고 파일은 변경하지 않았다.
- TypeScript type-check·Vite build 통과. OpenAPI/JSON Schema/응답 예시 생성 및 동기화 검사 통과.
- pip check 문제 없음, 보안 검사 findings=0, 수정 문서의 로컬 링크 47개 확인. 생성 자료 추적 0건, 알고리즘/frontend 파일 diff 0건, 기존 migration 0001~0007 diff 0건.
- 원격/로컬 HEAD 및 Push 결과는 최종 응답의 SHA를 기준으로 확인한다. 검증 Snapshot·보존 비교 자료는 ignored `.artifacts/`에만 보관하며 기업 데이터·비밀값을 Commit하지 않는다.

새 파일은 backend/app/datasets.py, dataset_schema_v1.py, api/datasets.py, contracts/interfaces/dataset.py, 신규 0008, backend/tests/test_datasets.py, scripts/integrate_dataset.py다. 기존 배치·예측·계획의 API dependency/provider/출처·DTO·생성 문서를 함께 확장했다. UI·엔진 담당 요청은 [별도 문서](DATASET_FRONTEND_CHANGE_REQUEST.md)에 기록했다.
