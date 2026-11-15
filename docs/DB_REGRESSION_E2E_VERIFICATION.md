# PostgreSQL 회귀 및 데이터셋별 API E2E 검증

검증일: 2026-11-15. 작업 시작 및 원격 기준 SHA: `bbf70b5e66f7c61b3b43ac87a034b61b684198e0` (`main`). 이 문서의 변경은 이후 검증 커밋에 포함된다. 최종 SHA는 Git 이력/완료 보고에서 확인한다.

## 결과와 검증 경계

| 실제 실행 | 결과 |
| --- | --- |
| PostgreSQL 포함 전체 pytest | **608 passed / 0 failed / 0 skipped** |
| 그중 기존 DB 테스트 | **55 passed / 0 failed / 0 skipped**; [개별 55행 감사](DB_REGRESSION_TEST_AUDIT.md) |
| 추가 데이터셋 DB E2E | **4 passed** (전체 608개에 포함) |
| DB 접속을 차단한 별도 전체 pytest `--no-db` | **549 passed / 0 failed / 59 skipped**; skip은 기존 DB 55개 + 추가 DB 4개 |
| 개발 DB PostgreSQL 강제 읽기 전용 API 검증 | **9개 그룹 passed**, 56개 테이블의 행 수·정렬 JSON SHA-256 동일 |
| 프론트엔드 TypeScript / Vite production build | 통과 / 통과; frontend 파일 변경 없음 |
| E2E TypeScript | 통과; `tests/e2e` 전용 Node 타입 의존성으로 보완 |
| Python `pip check` / 컴파일 검사 | 통과 / 통과 |
| OpenAPI·JSON Schema 계약 동기화 | 전체 pytest 내 기존 동기화 테스트 통과; API·생성 계약 변경 없음 |
| 보안·문서 경로 검사 | 보안 탐지 0건; 공개 후보 텍스트 346개 검사. 변경 Markdown의 상대 링크·코드 참조 경로 검사 통과 |
| 데이터셋 선택 브라우저 실행 | **미실행·보류**; 해당 UI 미구현. 실패/skip/통과로 집계하지 않음 |

pytest에는 기존 Starlette TestClient/httpx deprecation warning 1건이 남는다. 이번에 의존성을 임의 교체하지 않았다. 기존 538 passed / 55 skipped 보고는 비DB 모드의 과거 기록이며, 위 실제 DB 실행 결과와 구분한다.

## 전용 회귀 DB와 승인

사용자는 새 `chungpamo_regression` DB와 `chungpamo_regression_runner` 계정 생성을 승인하고 다음 범위를 명시했다.

> “DROP SCHEMA, TRUNCATE 등 초기화 작업은 새로 생성한 chungpamo_regression DB 내부에서만 허용해.”

기존 `chungpamo`, `chungpamo_test`는 초기화·수정하지 않았다. 기존 55432 및 다른 Docker 프로젝트 DB에는 접속하지 않았다. 기존 컨테이너·네트워크·볼륨을 생성/삭제/재시작하지 않았다. 기존 모노레포 PostgreSQL 서버 안에 **새 DB/새 제한 계정**만 생성했다. 이 회귀 DB와 계정은 테스트 종료 후에도 삭제하지 않고 보존했다.

| 식별 항목 | 확인한 값 |
| --- | --- |
| PostgreSQL | 16.6, `127.0.0.1:55433` |
| Docker Engine / Compose 프로젝트 | 29.4.0 / `chungpamo-monorepo` |
| 컨테이너 / health | `chungpamo-monorepo-db` / healthy |
| 포트 바인딩 | `127.0.0.1:55433 → 5432/tcp` |
| 볼륨 / 네트워크 | `chungpamo-monorepo-pgdata` / `chungpamo-monorepo-net` |
| DB / 실제 `current_database()` | `chungpamo_regression` |
| 사용자 / 실제 `current_user` | `chungpamo_regression_runner` |
| 계정 권한 | NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION; 새 DB 소유 |
| 인증정보 | 개발 계정과 다른 임의 비밀번호. Git 제외 `.env.regression.local`에만 저장 |
| 최종 public revision | **0008**; 이번 실행에서 빈 public에 0001→0008 적용 |
| 과거 검증 전용 스키마 | `regression_history_0001`, `regression_history_0005`; 모두 회귀 DB 내부, 최종 각 0005 |

`scripts/verify_test_db.py`는 승인 토큰 → 정확한 URL/role → Docker 식별 → 실제 DB/role 및 권한 → sentinel → 허용 스키마/테이블 → 기존 배치 SYNTHETIC 출처 순으로 검사한다. 승인 토큰은 동의 자체를 대신하지 않는다. 개발 URL을 테스트 URL로 자동 치환하지 않는다. URL query 옵션, localhost 별칭, 55432, 개발/기존 테스트 DB, 잘못된 사용자, 개발 비밀번호 재사용을 거부한다. 잘못된 대상은 Docker/SQL 접근 전에 중단하도록 11개 비DB 안전성 테스트를 추가했다.

회귀 계정은 DB 생성/관리 권한이 없지만 PostgreSQL 공통 기본 설정에 따라 다른 DB의 접속 권한이 자동 차단된다고 가정하지 않는다. 실행 안전성은 명시적인 대상·사용자 검사와 고정 URL, 별도 자격증명으로 보강했다. 기존 DB ACL을 수정하지 않았다.

초기 생성 당시 새 DB의 빈 public을 확인하고 `regression_test_sentinel`을 만들었다. 이후 reset에는 정확한 sentinel이 필요하다. 예상하지 못한 스키마/테이블 또는 비합성·출처 불명 배치가 있으면 보존하고 중단한다. 각 cleanup에도 대상 guard를 둔다. 세션 초기화는 회귀 DB 안의 public/CP 테스트 데이터셋/과거 검증 스키마에만 한정한다. 테스트는 순차 실행하며 개발 DB에서 실행하지 않는다.

## 기존 55개 skip 원인과 수정

`--no-db`는 `test_engine`을 skip하고 SQLAlchemy/psycopg 접속을 차단한다. 과거 55 skipped는 이 실행 모드의 결과로, DB 기능 통과를 뜻하지 않았다. 원래 파일/함수/매개변수 이름을 JUnit 간 대조해 55개 모두 실제 실행됨을 확인했다.

| 파일 | 원래 DB case 수 | 주요 검증 |
| --- | --- | --- |
| `backend/tests/test_db_rules.py` | 30 | 승인 상태·불변성·지연 constraint·참조·BOM 기간 겹침·quantile·승인 입력 view |
| `backend/tests/test_forecast_runs.py` | 14 | 승인 입력만 사용, 저장·재조회·digest·모델 버전·오류·rollback·동시 실행·과거 0005 보존 |
| `backend/tests/test_health.py` | 1 | 실제 DB health |
| `backend/tests/test_postgres_integration.py` | 2 | 과거 migration 순차 왕복·실제 등록/매핑/승인 API |
| `backend/tests/test_sql_repository.py` | 8 | SQL 조회·승인·참조·중복·rollback·동시 승인 row lock |

첫 실제 DB 실행은 **591 passed / 2 failed / 0 skipped**였다. 두 실패는 과거 0001~0005 왕복 시험이 최신 0008 public에서 downgrade를 시도한 것이 원인이다. 0008의 안전한 downgrade 거부를 우회하거나 기존 마이그레이션을 고치지 않았다.

- `backend/migrations/env.py`에 회귀 DB·허용 스키마에서만 동작하는 historical migration 경로를 추가했다. 실제 DB/사용자를 확인하고 transaction-local search_path와 별도 version table을 사용한다. 일반 migration 경로는 유지했다.
- 과거 0001→0005 순차 검증은 별도 history 스키마에서 그대로 실행했다. current public은 0008을 유지한다.
- 과거 0005의 legacy row 보존/0004 왕복/이력이 있을 때 downgrade 거부도 별도 history 스키마에서 확인했다. current API의 신규 9행과 역사 검증의 legacy 1행을 각각 검증해 원래 총 10행 검증 의미를 유지했다. legacy fixture와 이력은 **회귀 DB 안에서 만든 합성 데이터**이며 개발 DB에서 복사하지 않았다.
- 테스트 삭제·skip 전환·constraint 완화는 하지 않았다. Alembic version 파일 **0001~0008은 변경하지 않았다**. 운영 API나 생산계획 알고리즘의 결함을 발견한 것으로 확대 해석하지 않는다.

## 데이터셋 API E2E와 트랜잭션

추가 파일 `backend/tests/test_db_dataset_e2e.py`의 모듈 fixture가 committed 합성 템플릿과 임시 디렉터리에 새로 생성한 합성 CSV를 실제 `/batches` 업로드·검증·승인 경로로 등록한다. 개발 DB의 기존 승인 자료를 테스트 DB에 복사하지 않는다. 파일 생성기의 OUT은 해당 임시 디렉터리에만 지정하며 모듈 소스/소유 파일은 수정하지 않는다.

| case | 실제 확인 |
| --- | --- |
| 데이터셋 E2E (매개변수 2개) | Legacy 1제품/24수요/2자원 및 CP 9제품/498수요/6자원, offset 경계, 실제 예측 생성 201→동일 입력 재사용 200, input/dataset digest 구분, 실제 SQL PlanningInput, cross forecast UUID 404, 미구현 계획 501 |
| 잘못된 참조·dataset | CP 자원을 Legacy CAPA에 넣은 배치 HAS_ERRORS, 승인 409, cross batch 404, unknown 404, inactive 409 |
| 계획 저장·동시성 | 명시적 TEST_DOUBLE 저장/공개 상세·Excel 404, 중복 key 경쟁 1성공/1 unique violation, What-if parent 보존·교차 dataset 거부, 동시 REVIEW 1성공/1 trigger 거부, version 2·event 1개, audit UPDATE 거부·입력 snapshot 불변 |

계획 계산 모듈과 정식 승인은 **미구현 501을 유지**한다. 계획 DB 저장 테스트는 `origin=TEST_DOUBLE`로 표시하고 공개 API에서 숨겨지는 것까지 확인했다. dedup/동시 REVIEW는 PostgreSQL 직접 연결 두 개를 사용하는 저장소/트리거 검증이며, 실제 알고리즘·정식 승인 E2E 통과를 의미하지 않는다. What-if도 테스트 snapshot 계보 검증이고 실제 재계산이 아니다.

기존 55개는 동시 배치 승인에서 한 번만 쓰는 것, version/digest 충돌, 삽입 실패 시 전체 승인 rollback, 동시 예측 실행 충돌 후 재사용을 실제 PostgreSQL로 검증했다. 제약·승인 게이트는 우회하지 않았다.

## 기존 개발 데이터 보존: 읽기 전용 9개 그룹

`scripts/verify_readonly_dataset_api.py`는 `default_transaction_read_only=on`으로 강제한 PostgreSQL 연결을 실제 SQL 저장소에 주입한다. API 서비스를 fixture 결과로 대체하지 않는다. 개발 DB에서 upload/approve/예측 생성/DDL/reset을 호출하지 않는다. 계획 POST는 write 전 501로 끝나는 미구현 게이트만 확인했다.

1. Legacy 8개 조회 API·total/offset 확인.
2. CP 8개 조회 API·total/offset 확인.
3. dataset 생략 시 Legacy만 조회; unknown/잘못된 이름 거부.
4. Legacy의 기존 예측 UUID·digest·승인 provenance 및 SQL PlanningInput 확인.
5. Legacy 계획 preview/실행/승인 501, 빈 이력, malformed/없는 UUID 및 출력 차단.
6. CP의 기존 예측 UUID·digest·승인 provenance 및 SQL PlanningInput 확인.
7. CP 계획 preview/실행/승인 501, 빈 이력, 잘못된 UUID·출력 차단.
8. 양방향 교차 forecast UUID를 API와 실제 SQL 입력 구성에서 거부.
9. 실제 scoped master로 CP BOM의 Legacy 제품 및 Legacy Routing의 CP 자원을 검증기가 거부. staging write 없이 수행.

public 업무 27개 + CP 업무 27개 + public dataset/alembic_version = **56개 테이블**의 전체 행을 정렬 JSON으로 fingerprint했다. 검증 전후, 전체 회귀 테스트 후 재검증에서 행 수와 SHA-256이 동일했다. 승인 배치 Legacy 7/CP 9, 기존 예측 UUID와 원본 digest를 포함해 보존됐다. 원시 행/원본 파일/호스트명이 있는 XML·로그는 Git 제외 `.artifacts`에만 둔다. fingerprint는 행 보존 근거이며 전체 서버 DDL/ACL의 완전한 감사를 대신하지 않는다.

## 브라우저 준비와 담당자 후속

[준비 시나리오](../tests/e2e/scenarios/README.md)는 `.scenario.ts` 함수로 작성했고 자동 실행 테스트로 등록하거나 skip 처리하지 않았다. 데이터셋 조회 → CP 선택 → 9제품 → 예측 → CAPA/Routing → 501 → Legacy 전환 → UUID/상태 비재사용의 8단계다. 현재 UI에는 데이터셋 선택 기능이 없어 **이번 브라우저 실행은 보류**했다.

- 정마나미 (`frontend/`): dataset selector와 공통 API dataset_id 전달, dataset 변경 시 예측/계획 UUID·loading·선택 상태 초기화, stale 응답 배제. 제안 접근성 이름/테스트 ID는 시나리오 README에서 협의한다. 재현: CP 데이터가 API에는 있지만 UI에서 dataset 전환 불가. 기대: dataset 단위 화면·실행·이력 격리. 관련 API: `/datasets`, master queries, `/forecasts`, `/plan-executions`.
- 이희원 (`modules/planning_engine/`): 현재 planning entrypoint는 미구현이며 실제 API 501. 승인된 SQL PlanningInput을 받는 알고리즘을 기존 계약대로 구현하고 독립 테스트 후 통합한다. 이 작업에서 계산식을 대신 구현하지 않았다.
- 김대영 (`backend/`, `contracts/`, `tests/e2e/`, `scripts/`): UI 완료 후 회귀 DB에만 브라우저 acceptance 등록·실행, 인증/권한·정식 승인 정책은 기존 미확정 게이트 유지. 회귀 초기화는 후속 작업마다 범위 승인 후 실행한다.
- 이훤 (`modules/file_classifier/`): 기존 분류 계약/501 연결점을 유지한다. 이번 검증으로 분류 알고리즘 완료를 주장하지 않는다.

## 재현 및 보안

**현재 DB는 이미 생성되어 있다. provision 명령을 다시 실행하지 않는다.** 다른 환경에 신규 생성할 때만 사용자가 DB명/role/초기화 범위를 승인한 후 `scripts/provision_regression_db.py`를 사용한다. 기존 DB/role/config가 발견되면 중단하며 재사용·초기화·삭제하지 않는다. [비밀값 없는 설정 예시](../infrastructure/regression.env.example)를 참고한다.

승인된 현재 환경에서 루트 실행:

```powershell
$env:PYTHONPATH='backend;modules/planning_engine;modules/file_classifier/src;.'
$env:CHUNGPAMO_ALLOW_TEST_DB_RESET='chungpamo_regression@127.0.0.1:55433'
./.venv/Scripts/python.exe scripts/run_regression.py
Remove-Item Env:CHUNGPAMO_ALLOW_TEST_DB_RESET
./.venv/Scripts/python.exe -m pytest --no-db -q --tb=short
./.venv/Scripts/python.exe scripts/verify_readonly_dataset_api.py
./.venv/Scripts/python.exe scripts/audit_db_tests.py
./.venv/Scripts/python.exe scripts/security_check.py
cd tests/e2e
npm ci --ignore-scripts --no-audit --no-fund
cd ../../frontend
node node_modules/typescript/bin/tsc -p ../tests/e2e/tsconfig.json --noEmit
npm run type-check
npm run build
```

`TEST_DATABASE_URL`은 runner가 무시된 로컬 설정에서 읽으며 URL/비밀번호를 출력하지 않는다. 테스트용 Node 타입은 `tests/e2e/package.json`과 lockfile에 고정해 frontend 의존성·소유 파일을 변경하지 않았다. 초기 E2E 타입 검사의 Node 내장 모듈/Disposable 타입 누락을 해결한 뒤 재검사했다.

보안 검사는 tracked/untracked 공개 후보 전체에 대해 로컬 비밀번호 일치, 토큰/개인키, 사용자 경로/전화번호 패턴, env/DB dump/실행 로그/허용하지 않은 binary를 확인한다. 새 회귀 비밀번호도 known-secret 검사 대상이다. `.env.regression.local`은 Git ignore 확인 및 stage 제외한다. 합성 fixture 원본·임시 생성 데이터·JUnit은 추가 커밋하지 않는다. 자동 패턴 검사는 비밀정보 부재의 절대 보증이 아니므로 staged diff도 검토한다.

미해결: dataset 선택 브라우저 실행, 실제 계획 계산·정식 승인·정식 Excel은 미구현 범위이며 이번 통과 수치에 넣지 않는다. Docker/DB 초기화 권한을 팀 문서만으로 일반화하지 않는다.
