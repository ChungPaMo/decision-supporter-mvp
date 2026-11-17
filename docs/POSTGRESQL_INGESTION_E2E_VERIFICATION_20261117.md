# 기존 개발 PC PostgreSQL 입력 통합 검증 — 2026-11-17

시작 SHA `acd40a511a57b9c0d92d2391a2d028ed09914af7`, main clean, fetch/switch/pull --ff-only 후 원격과 일치했다. 완료 Commit은 이 보고서를 포함하는 고유 제목 `test: verify PostgreSQL ingestion history and preserve development data`로 식별한다. 자기 SHA를 미리 적거나 반복 amend하지 않으며 최종 SHA/Push는 완료 응답에서 확인한다.

이번 요청은 **기존 개발 PC의 Docker/DB 사용을 명시적으로 허용**했다. AGENTS의 보조 PC 금지를 다른 환경의 일반 허용으로 바꾸지 않는다. 개발 DB의 0009 적용과 회귀 초기화 승인은 별개다. 진행 기록은 [PROJECT_PROGRESS](PROJECT_PROGRESS.md), 누적 기록은 [DEVELOPMENT_CHANGELOG](DEVELOPMENT_CHANGELOG.md)를 함께 갱신한다.

## 실제 환경과 사전 상태

| 항목 | 이번 확인 |
| --- | --- |
| Docker Desktop / Engine | 4.70.0 / 29.4.0, desktop-linux |
| 기존 프로젝트 / 컨테이너 | chungpamo-monorepo / chungpamo-monorepo-db, healthy |
| image / 바인딩 | postgres:16.6 / 127.0.0.1:55433→5432 |
| 기존 영구 볼륨 / 네트워크 | chungpamo-monorepo-pgdata / chungpamo-monorepo-net |
| 개발 DB / 실제 사용자 | chungpamo / chungpamo_app |
| 회귀 DB / 실제 사용자 | chungpamo_regression / chungpamo_regression_runner |
| 개발·회귀 초기 revision | 각각 0008 |
| 개발 데이터셋 | TISSUE-LEGACY(public), CHUNGPAMO-2027(ds_d3ef2e29ee90f6c7258d259aa99525b9), 모두 ACTIVE |
| 개발 승인 배치 / 예측 이력 | Legacy 7 / CP 9, forecast_run 각 1건 |

최초 sandbox에서 Docker pipe 접근이 거부됐고, 읽기 전용 명령의 실행 권한으로 재시도해 실제 엔진 연결을 확인했다. 컨테이너를 시작/재시작/재생성하지 않았다. 다른 컨테이너·볼륨은 사용자 요청의 목록 확인만 했으며 55432/다른 DB에 접속하지 않았다. Windows 서비스도 변경하지 않았다.

기존 `.env`, `.env.regression.local`의 host/port/DB/user를 검사하고 비밀번호는 출력하지 않았다. 실제 `current_database/current_user`, 컨테이너/볼륨/네트워크, sentinel, 허용 스키마·테이블·SYNTHETIC 출처를 재검사했다. 회귀 DB의 업무 배치는 비어 있었고 과거 history 스키마·ARCHIVED-TEST 레지스트리는 이전 테스트 자원이었다. ARCHIVED-TEST의 스키마는 없어 기존 상태에 곧바로 0009를 덮어 적용하지 않고, 별도 승인 후 fixture의 전용 초기화 절차를 사용했다.

## 0009 검토·마이그레이션 보존 시험

0009→0008 연결을 확인했다. 기존 0001~0008과 dataset_schema_v1.py는 변경하지 않았다. 신규 migration도 추가하지 않았다. 기존 0009는 public.dataset의 **보관 데이터셋 포함 전체 등록 스키마**를 검증하고 advisory lock(880008) 아래 다음을 추가한다.

- 스키마당 ingestion_transformation/ingestion_transform_source 2테이블.
- dataset CHECK/FK, 로컬 batch FK, input_digest 및 batch_id 유일성.
- 원본 bytea 크기/SHA CHECK, 불변 UPDATE/DELETE 트리거.
- 원본 수/인덱스/파일명/SHA/크기·출력 CSV SHA 대조용 지연 제약 트리거.
- canonical 매핑 설정을 지키는 batch UPDATE 트리거.

업무 행을 UPDATE/DELETE하거나 기존 테이블을 재작성하지 않는다. 기존 승인/예측의 DML 계약은 유지한다. offline SQL은 public 예시이므로 전체 스키마 온라인 적용의 대체 증거로 취급하지 않았다.

`scripts/verify_ingestion_migration_postgres.py`는 승인된 **회귀 DB만** 새로 0008까지 upgrade한 후 트랜잭션 안에서 3개 스키마(보관 dataset 포함)에 합성 승인 제품/수요 및 기존 방식 forecast 행을 만들었다. 실제 Alembic Operations로 기존 0009의 upgrade 본문을 실행하고 **81개 기존 테이블의 행 지문 동일**, 신규 이력 6테이블 생성·빈 상태를 확인했다. 전체 probe/추가 보관 스키마는 transaction rollback했다. downgrade는 없었다. 이 시험 자체는 revision stamp를 바꾸는 CLI 시험이 아니며, 이후 실제 pytest fixture의 빈 public에서 **Alembic 0001→0009 정상 upgrade**도 별도로 통과했다.

## 승인과 제외 범위

사용자는 이번 작업의 회귀 초기화를 허용하면서 **downgrade 테스트 2개는 제외**하도록 명시했다. 설정 token이 사용자 승인을 대신하지 않는다. public, CP 테스트 스키마와 과거 history 스키마의 DROP/재생성·TRUNCATE는 chungpamo_regression 내부에서만 실행했다. 개발 chungpamo·기존 chungpamo_test·볼륨은 초기화하지 않았다. 회귀 DB 자체는 삭제하지 않고 남겼다.

이번 실제 미실행 2개 (pytest `-k` 선택 제외, skip 장식/본문 변경 없음):

1. test_postgres_integration.py::test_empty_test_db_migrates_down_to_0001_and_up_sequentially
2. test_forecast_runs.py::test_0005_preserves_legacy_results_and_allows_new_run

따라서 이전 미실행 DB **63개 중 61개 실행·통과 / 2개 미실행**이다. 추가한 실DB 3개를 합치면 **64개 실DB case 통과**다. 새 데이터셋 v2/local FK 시험은 원래 두 ingestion-history DB case에 포함돼 실제 실행됐다.

## 실행 결과와 발견 문제

| 실행 | 이번 실제 결과 |
| --- | --- |
| 최초 비DB 수집 | RapidFuzz 미설치로 24 collection errors. 테스트 통과로 세지 않음 |
| 환경 보완 | 저장소에 이미 고정된 RapidFuzz 3.14.6만 로컬 venv에 설치. 버전/lockfile 변경 없음 |
| 최초 실DB 전체 | 1003 passed / 1 failed / 2 deselected |
| 원인 수정 후 집중 DB | 5 passed (원래 이력 2 + 새 실제 SQL 3) |
| 최종 전체 pytest | **1015 passed / 0 failed / 0 skipped / 2 deselected**, 59.06초 |
| 별도 비DB 전체 | **951 passed / 0 failed / 66 skipped**, 23.17초. DB 63+추가3은 접속 차단으로 제외 |
| 승인·보존 가드 | 비DB 8 passed, 최종 전체에 포함. 승인 전 SQL 접근 차단·기존 자료/객체 변경 탐지·0009 비교 허용범위 확인 |
| TypeScript / Vite production build | 통과 / 통과, frontend 수정 없음 |
| OpenAPI·JSON Schema·기존 예시·격리 | 전체 pytest의 동기화/격리 검사 통과 |
| Python 컴파일 / pip check | 통과 / No broken requirements found |
| 비밀/원본 파일 검사 | findings=0, dump/env/원본/로그/JUnit은 stage 제외 |

실패는 운영 승인 결함이 아니라 **새 DB 시험 fixture의 제약 타이밍 오류**였다. `SET CONSTRAINTS ALL IMMEDIATE`로 staging evidence를 확인한 뒤 그 상태를 유지해, 승인 상태 UPDATE 직후 수요 행 INSERT보다 먼저 approved_record_count가 검사됐다. staging 검사 뒤 DEFERRED를 복원하고 승인 뒤에도 IMMEDIATE 검증을 추가했다. 운영 트리거/승인 게이트/기존 migration을 완화하지 않았다.

기존 Starlette/httpx deprecation warning 1건은 남는다. 이전 943 passed는 이번 수집 실패/수정 후 재실행과 구분하며, 2 deselected를 passed/skipped로 섞지 않는다. 새 입력 브라우저 E2E는 UI 담당 영역 때문에 실행하지 않았다. 과거 npm 취약점 인계는 이번에 재검사/수정한 것이 아니다.

## 공식 자료 실제 SQL E2E

`backend/tests/test_db_ingestion_official.py`는 기존 [14파일 manifest](../contracts/examples/ingestion_e2e_source_manifest.json)와 owner 폴더의 공식 자료를 읽어 SHA를 대조했다. 자료가 다르면 덮어쓰지 않는다. 등록은 **회귀 DB의 CHUNGPAMO-2027 테스트 데이터셋**에서만 수행했고 개발 DB의 같은 공식 자료를 중복 등록하지 않았다.

서비스/저장소/SQL을 메모리 대역으로 교체하지 않고 실제 FastAPI→SQLAlchemy→PostgreSQL 경로를 실행했다. 테스트 연결/설정만 전용 DB에 주입했다. 작은 실패/미승인 probe는 공식 행에서 파생한 negative fixture이며 성공 경로의 원본/정답을 대체하지 않는다.

1. 공식 8개 master 배치 업로드·명시적 승인: 제품9/자재9/BOM9/재고18/CAPA27/Routing27. 표준 05 월수요는 정답으로만 사용했다.
2. 판매 원장의 실제 분류 HOLD·일반 월수요 mapping HOLD, 명시적 정책/승인 마스터를 사용한 preview.
3. 원본5개 **86,214행 = 정상83,984 + 취소887 + 반품1,343**, 오류0 → **498행**. 제품·월·Decimal 수량·단위가 독립 정답과 모두 동일했다.
4. 동시 transformation POST 2개가 **201/200** 및 같은 transformation/batch ID를 반환했다. advisory lock/유일성/재사용을 실제 두 연결로 확인했다.
5. 원본5개의 저장 bytea와 입력 bytes/크기/SHA가 일치했고 정책·전체 결과·지문·batch 연결을 재조회했다. 이력 저장은 persisted=true지만 업무 승인 전이며 수요 조회는0이었다.
6. 변환 digest로 승인 시409, **배치 result_digest**로 명시적 승인 후498행 조회. 별도 TestClient/DB 연결에서도 저장 이력과 APPROVED를 복원했다. 다른 dataset의 UUID 조회는404였다.
7. 별도 미승인 수요 probe를 둔 상태에서 forecast snapshot은 승인된 변환 배치만 포함했고498행 모두 정답과 같았다. **예측 상태 OK, 9제품×3개월=27행**, P50≤P80≤P90 및 예측 이력 저장·재조회 통과.
8. 모든 source/manifest14개 SHA를 사후 재대조했다. 사용자 대신 자동 승인하는 경로는 없다.

원본/정책/출력 지문·ID의 상세 결과는 ignored `.artifacts/postgresql-ingestion-20261117/official-e2e.json`에 둔다. 계획 MPS/RCCP/MRP·What-if 계산·정식 계획 승인은 검증 대상이 아니며 완료로 주장하지 않는다.

## 원자성·불변성과 테스트 후 상태

실제 source INSERT를 전부 수행한 다음 같은 PK를 다시 INSERT해 PostgreSQL unique violation을 발생시켰다. HTTP500 PERSISTENCE_ERROR 후 import_batch/batch_source_file/ingestion_transformation/ingestion_transform_source 건수가 모두 직전과 같았다. 이 실패 경계에만 테스트 fault injection을 사용했고 원래 저장 SQL을 먼저 실행했다.

이미 commit된 manifest/source UPDATE는 실제 CHECK 위반으로 거부됐다. 선언되지 않은 6번째 source를 추가하면 **commit 때** 지연 트리거가 거부했고 원본5개만 남았다. API 명령 승인 전후 상태와 다른 UUID 격리도 실제 저장소로 확인했다. 기존 배치/예측 동시성·승인 rollback 회귀도 별도 기존 DB 테스트에서 통과했다.

테스트 fixture는 승인된 회귀 DB에서 생성한 업무 자료를 TRUNCATE 정리한다. 따라서 E2E ID는 실행 증거이고 장기 데모 자료 보존을 약속하지 않는다. 회귀 DB/0009/sentinel은 보존하며 개발·기존 테스트 DB를 복사/초기화하지 않았다.

## 개발 데이터 보존·백업·0009 승인 상태

`scripts/postgresql_preservation.py`는 정확한 Docker/DB/역할을 검사한 후 REPEATABLE READ + PostgreSQL 강제 READ ONLY로 56개 기존 테이블의 **서버 JSON text** 행 수/SHA를 계산했다. Decimal을 float로 변환하지 않는다. 기존 함수/트리거/제약/view 정의도 별도로 지문화했다. 회귀 종료 후 기존 registry·행/지문·승인7+9배치·예측각1·DB 객체와 Docker identity가 동일했다.

기존 컨테이너의 pg_dump custom 백업을 ignored `.artifacts/postgresql-ingestion-20261117/chungpamo-before-0009.dump`에 생성했다. **292,343 bytes**, 전체 SHA 및 pg_restore --list를 검증했다. DB restore·다운그레이드·볼륨 복구는 하지 않았고 실제 복구 리허설 완료로 주장하지 않는다. 백업/목차/해시/지문은 Git에 올리지 않는다.

**사용자의 별도 명시 승인 후 개발 DB에 0008→0009만 적용했다.** `scripts/apply_ingestion_0009.py`는 실행 직전 실제 host/port/DB/user, 현재0008, unchanged 사전 지문, 백업 byte/SHA/목차를 재검사했다. 기존 upgrade 명령을 정확한 개발 URL 환경변수로 실행했고 초기화·downgrade·복구·자동재시도는 없었다.

직후 비교에서 기존 **55개 데이터 테이블**(업무54+dataset)의 행/체크섬과 승인7+9배치·예측각1, 기존 함수/트리거/제약/view 및 Docker identity가 동일했다. 기존56개 중 달라진 것은 public.alembic_version의0008→0009뿐이다. 새 history4테이블은 모두0행이고 총60테이블이다. 예정한 함수4/트리거10 및 새 테이블 제약만 추가됐다. 차이가 없어 추가 복구는 필요하지 않았다.

| 개발 DB 주요 건수 (전=후) | TISSUE-LEGACY | CHUNGPAMO-2027 |
| --- | --- | --- |
| 승인배치 / 예측실행 | 7 / 1 | 9 / 1 |
| 제품 / 자재 | 1 / 3 | 9 / 9 |
| BOM header / line | 1 / 3 | 9 / 27 |
| 재고 / 월수요 | 4 / 24 | 18 / 498 |
| 자원 / 수량한도 / 시간예산 | 2 / 1 / 2 | 6 / 3 / 18 |
| Routing step | 1 | 27 |
| 기존 예측결과 행 | 1 | 27 |
| 신규 변환이력 / 원본 | 0 / 0 | 0 / 0 |

적용 이후 개발 DB에서는 **GET 조회만** 추가 실행했다. PostgreSQL 강제 READ ONLY로 제품/자재/BOM/재고/수요/배치/CAPA/Routing/예측/새 이력 목록·없는 UUID 및 기존 예측 상세 **24건**을 확인했고 조회 전후60테이블 지문도 동일했다. 개발 DB에 공식 자료를 다시 저장하거나 새 승인/예측을 만들지 않았다. 실제 저장 E2E는 전술한 별도 회귀 DB에서만 수행했다. 이제 개발 DB의 신규 이력 SQL 배포 조건은 갖췄지만 화면 통합·새 업무 자료 등록을 이미 완료한 것은 아니다.

## 변경 파일과 인계

- backend/tests/test_db_ingestion_history.py: 지연 제약 검사 시점 복원·승인 후 검증 추가.
- backend/tests/test_db_ingestion_official.py: 공식 SQL E2E, 실제 동시 재전송·rollback·불변성·예측 입력.
- backend/tests/test_postgresql_preservation_safety.py: 승인 전 실행 차단·사전/사후 보존 비교 8개 검사.
- scripts/verify_ingestion_migration_postgres.py: 승인된 회귀 DB의 rollback-only 기존 자료/보관 schema 0009 검증.
- scripts/postgresql_preservation.py: 개발 read-only 사전/사후 지문·비공개 백업.
- scripts/apply_ingestion_0009.py: 별도 승인된 경우에만 실행하는 보존 guard.
- 본 보고서와 PROJECT_PROGRESS/DEVELOPMENT_CHANGELOG: 최신 환경·통과·미실행·담당 인계 기록.

김대영: 적용된 개발0009와 신규 SQL/기존 자료의 정합성을 유지하고 다음 회귀의 파괴적 작업은 새 범위 승인을 받는다. 정마나미: 기존 [UI 인계](INGESTION_UI_API_HANDOFF.md)에 따라 신규 입력 화면을 연결하고 실제 브라우저 E2E를 준비한다. 이희원: 계획 엔진/업무 제약 계산 통합은 별도이며 이번 입력·예측 성공으로 완료 처리하지 않는다. 이훤: 이번 검증에서 기존 rules 분류기를 그대로 사용했고 모듈을 변경하지 않았다. 원본·정답·모든 담당 폴더·0001~0008은 변경하지 않았다.
