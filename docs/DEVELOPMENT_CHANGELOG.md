# 개발 변경 이력

이 문서는 주요 작업을 시간순으로 누적한다. 최신 상태는 [PROJECT_PROGRESS](PROJECT_PROGRESS.md), 상세 방법·수치는 각 검증 보고서를 따른다. 작성 규칙과 새 항목 양식은 [AGENTS](../AGENTS.md)에 있다. 기존 항목을 삭제하거나 새 검증 결과로 덮어쓰지 않는다.

## 과거 이력 복원 기준

2026-11-17에 `main`의 Git 로그·각 Commit 변경 경로·관련 보고서와 실제 코드를 대조해 아래 주요 이력을 복원했다. 날짜는 이 저장소 Git의 작성일(KST), 시작/완료 Commit은 해당 변경 구간이다. 같은 날짜의 순서는 Git 계보를 따른다. 커밋에 포함된 보고서의 실행 결과는 **당시 기록이며 이번에 재실행한 결과가 아니다**. 확인되지 않은 독립 실행 수치·출처 저장소 개발 날짜는 추정하지 않는다.

브랜치는 현재 `main` 계보를 표시하고, 과거 작업 브랜치는 보고서에서 확인된 경우만 별도로 적는다. 초기 이관 이전 소스의 전체 개발 이력이 이 저장소에 합쳐진 것은 아니다. 아래는 주요 변경 요약이며, 모든 소규모 수정은 Git 로그에서 확인한다.

### 2026-11-14 — 초기 모노레포·데이터 입력·수요예측 API 이관

**Git**
- 시작 Commit: `baf829d` (최초 README).
- 완료 Commit: `e488282`.
- 브랜치: 현재 `main` 계보. 이관 보고서의 당시 작업 브랜치는 `feature/backend-integration`이며 이후 직접 main 절차로 전환했다.

**작업 목적**
- 기존 backend/frontend/예측 구현을 단일 저장소로 이관하고 파일→검증·승인→예측 흐름을 연결한다.

**구현 내용**
- `backend/app/` 입력·배치·승인·SQL·예측 API와 기존 0001~0005, `frontend/` 화면, 공통 계약/실행 경로를 이관했다.
- 예측 코드를 `modules/planning_engine/engine/forecast/` 한 벌로 이동하고 승인 수요/실행 이력·P50/P80/P90 연결을 유지했다. 새로 모든 알고리즘을 작성한 것으로 해석하지 않는다.

**검증 결과**
- 당시 이관 목록·제외 파일·출처 보존과 검증 절차는 이관 보고서에 기록돼 있다. 후속 실제 PostgreSQL/브라우저 실행은 아래 `af5e4fd` 항목과 구분한다. 이 항목에서 별도 테스트 수치를 추정하지 않는다.

**기술적 결정**
- allowlist 이관과 단일 예측 구현으로 중복/비밀 파일 복사를 방지했다. 원본 저장소 Git 이력을 강제로 합치지 않았고 계획 DEMO를 실제 계산으로 취급하지 않았다.

**남은 문제**
- 전용 PostgreSQL 실제 검증, 분류·계획 모듈의 계약/담당 확정이 필요했다.

**관련 자료**
- [Commit e488282](https://github.com/ChungPaMo/decision-supporter-mvp/commit/e488282), [이관 보고서](MIGRATION_REPORT.md), [예측 실행 API](api_contract_forecast_runs.md).

### 2026-11-14 — PostgreSQL 승인·예측 E2E 및 협업 경계 정립

**Git**
- 시작 Commit: `e488282`.
- 완료 Commit: DB 검증 `af5e4fd`, 계약/화면/인계·직접 main 절차를 거쳐 `2b09648`.
- 브랜치: `main` 계보; `2071ce4`부터 직접 main 개발 절차 명문화.

**작업 목적**
- 이관된 등록·검증·승인·예측이 독립 PostgreSQL 환경에서 동작하는지 확인하고 팀원별 확장 지점을 정한다.

**구현 내용**
- `af5e4fd`: 전용 DB·승인 guard·단일 제품 예측 API/브라우저 검증을 보강했다.
- `08f0592`, `7014c3e`, `4bf4ed3`: typed 모듈 어댑터, CAPA 초안, 검토 화면·DEMO 경계, 팀원 인계/독립 시험을 추가했다. `docs/OWNERSHIP.md`, `DEVELOPMENT_WORKFLOW.md`, `TEAM_WORK_ASSIGNMENTS.md`에 경로·Git 규칙을 명시했다.

**검증 결과**
- 당시 `af5e4fd` 보고: 실제 PostgreSQL 포함 pytest **490 passed / 0 failed / 0 skipped**, DB 브라우저 9 passed, 비DB UI 브라우저 3 passed.
- 후속 뼈대 보고의 **464 passed / 55 skipped**, 비DB 브라우저 8 passed는 별도 실행이다. 현재 신규 입력 API/전체 제조 E2E 검증으로 승격하지 않는다.

**기술적 결정**
- 새 전용 자원과 명시적 파괴적 테스트 승인 guard를 사용했다. 미구현 모듈은 501, DEMO는 별도 표시하며 실제 성공으로 대체하지 않았다.

**남은 문제**
- 분류·계획 계산 담당 구현, CAPA/Routing 영구 입력, 계획 정식 승인 정책이 남았다.

**관련 자료**
- [DB Commit af5e4fd](https://github.com/ChungPaMo/decision-supporter-mvp/commit/af5e4fd), [협업 Commit 2b09648](https://github.com/ChungPaMo/decision-supporter-mvp/commit/2b09648), [DB 검증](monorepo_postgresql_verification_20261114.md), [뼈대 검증](E2E_SCAFFOLD_VERIFICATION_20261114.md), [팀 인계](TEAM_HANDOFF.md).

### 2026-11-15 — CAPA·동시 자원 Routing 등록·승인

**Git**
- 시작 Commit: `2b09648`.
- 완료 Commit: `ef52bcc` (구현), `91bdaea` (합성 양식 추적 보정).
- 브랜치: `main` 계보.

**작업 목적**
- 수량 한도·설비시간·인시·동시 자원 Routing을 기존 배치 검증/승인과 계획 입력에 연결한다.

**구현 내용**
- `backend/app/batches/capacity.py`, 배치 등록/SQL 저장, `contracts/interfaces/`, Alembic 0006과 합성 업로드 양식을 추가했다. 승인 자료를 PlanningInput 스냅샷으로 연결했다.

**검증 결과**
- 당시 기존 개발 PC에서 0006 적용, 합성 7배치 명시적 승인·실제 행 조회·동일 파일 재사용을 확인했다. 별도 비DB pytest **479 passed / 55 skipped**; 이는 DB 테스트 전체 통과 수치가 아니다.

**기술적 결정**
- 수량/설비시간/총인시를 구분하고 API 승인 경로를 재사용했다. 기존 0001~0005와 다른 담당 폴더는 보존했다.

**남은 문제**
- CAPA/Routing 화면 확장과 실제 계획 알고리즘이 남았다.

**관련 자료**
- [Commit ef52bcc](https://github.com/ChungPaMo/decision-supporter-mvp/commit/ef52bcc), [Commit 91bdaea](https://github.com/ChungPaMo/decision-supporter-mvp/commit/91bdaea), [검증](CAPACITY_ROUTING_VERIFICATION.md), [데이터 사전](CAPACITY_ROUTING_DATA_DICTIONARY.md).

### 2026-11-15 — 불변 계획 이력·What-if 계보·검토/출력 게이트

**Git**
- 시작 Commit: `91bdaea`.
- 완료 Commit: `043b341`.
- 브랜치: `main` 계보.

**작업 목적**
- 실제 엔진 연결에 앞서 입력·결과·출처·검토 결정을 불변 이력으로 보존하는 기반을 만든다.

**구현 내용**
- `backend/app/plans/`, `/plan-executions`, 계약/예시, Alembic 0007에 스냅샷·후보·제약·자재·계보·검토·출력 게이트를 추가했다.

**검증 결과**
- 당시 비DB 서비스/계약 시험과 개발 DB의 0007 적용·롤백 전용 probe가 보고돼 있다. 실제 계획 계산 성공 검증은 아니다. 테스트 대역의 저장 성공과 REAL_ENGINE 결과를 구분한다.

**기술적 결정**
- 기존 무저장 Preview를 유지하고 정식 출력은 신뢰할 수 있는 승인 저장본으로 제한했다. 공개 APPROVE는 인증/정책 미연결로 차단했다.

**남은 문제**
- `engine.planning.AVAILABLE=False`/501 상태와 실제 엔진·인증·정식 승인 연결이 남았다.

**관련 자료**
- [Commit 043b341](https://github.com/ChungPaMo/decision-supporter-mvp/commit/043b341), [계획 저장 계약·검증](PLAN_EXECUTION_PERSISTENCE.md).

### 2026-11-15 — 이희원 공식 합성 자료와 입력 계약 확인

**Git**
- 시작 Commit: `043b341`.
- 완료 Commit: 생성기 `16c2aa1`·원장 확장 `e87b75d`, 1차 계약 검증 `fd0bc7f`.
- 브랜치: `main` 계보.

**작업 목적**
- 연결된 제품·자재·BOM·재고·CAPA·Routing·판매 기준을 갖춘 재현 가능한 합성 데이터로 입력 계약을 검증한다.

**구현 내용**
- 이희원 담당 `modules/planning_engine/synthetic/generate.py`와 원장/업로드/정답 생성 흐름을 추가했다. 통합 담당은 `scripts/verify_synthetic_contracts.py`, `backend/tests/test_synthetic_contracts.py`로 기존 생성기를 재사용했다.

**검증 결과**
- 당시 표준 9파일의 계약·오류 자료·참조/공유 자원 구조를 비DB로 검증했다. `fd0bc7f` 시점은 **실제 DB 등록/승인 0건**이며 메모리 저장소 시험이었다. 이후 실제 DB 등록은 다음 항목이다.

**기술적 결정**
- 담당자 생성기/독립 정답을 기준으로 삼고 임의 성공 시드로 대체하지 않았다. 비용·원시 거래 등 지원 외 데이터를 새 승인 entity에 섞지 않았다.

**남은 문제**
- 기존 개발 자료와 새 9제품 자료의 DB 격리, 실제 등록/예측 연결이 필요했다.

**관련 자료**
- [생성기 Commit 16c2aa1](https://github.com/ChungPaMo/decision-supporter-mvp/commit/16c2aa1), [검증 Commit fd0bc7f](https://github.com/ChungPaMo/decision-supporter-mvp/commit/fd0bc7f), [1차 합성 계약 검증](SYNTHETIC_DATA_INTEGRATION_VERIFICATION.md).

### 2026-11-15 — 데이터셋 격리 및 독립 PostgreSQL 회귀

**Git**
- 시작 Commit: `fd0bc7f`.
- 완료 Commit: 격리 `bbf70b5`, 회귀 `ff448ac`.
- 브랜치: `main` 계보.

**작업 목적**
- TISSUE-LEGACY와 CHUNGPAMO-2027의 승인 자료·예측·UUID가 섞이지 않게 하고 개발 데이터를 보존하는 회귀 경계를 만든다.

**구현 내용**
- `backend/app/datasets.py`, `dataset_schema_v1.py`, 저장소·API scope, Alembic 0008로 같은 DB의 스키마별 격리를 구현했다.
- 별도 회귀 DB/역할·대상/sentinel guard와 데이터셋 API E2E·개발 DB 읽기 전용 fingerprint 검사를 보강했다.

**검증 결과**
- 당시 `bbf70b5`에서 격리 적용·공식 자료 승인/예측 및 기존 자료 보존을 확인했다. `ff448ac`의 실제 PostgreSQL 전체 pytest는 **608 passed / 0 failed / 0 skipped**; 별도 비DB 실행은 **549 passed / 59 skipped**였다.
- 56개 개발 DB 테이블의 전후 행 수/SHA 보존을 보고했다. 데이터셋 선택 브라우저는 당시 미구현으로 미실행이었다. 현재 DB 상태는 이번에 재조회하지 않았다.

**기술적 결정**
- 단순 WHERE 필터/전 테이블 복합키 개편 대신 스키마와 root 소유권으로 격리했다. dataset_id를 인증 권한으로 취급하지 않고 파괴적 회귀를 개발 DB에서 분리했다.

**남은 문제**
- 당시 데이터셋 UI 연결이 필요했다. 이후 신규 0009 SQL 경로는 이 검증에 포함되지 않는다.

**관련 자료**
- [Commit bbf70b5](https://github.com/ChungPaMo/decision-supporter-mvp/commit/bbf70b5), [Commit ff448ac](https://github.com/ChungPaMo/decision-supporter-mvp/commit/ff448ac), [격리 보고서](DATASET_ISOLATION.md), [DB 회귀](DB_REGRESSION_E2E_VERIFICATION.md), [개별 감사](DB_REGRESSION_TEST_AUDIT.md).

### 2026-11-15 — 결정적 컬럼 분석·후보·판매 변환 Preview

**Git**
- 시작 Commit: `ff448ac`.
- 완료 Commit: `d21423e`.
- 브랜치: `main` 계보.

**작업 목적**
- 기존 정확 매핑/승인 경로를 보호하면서 파일 구조 분석·검토 후보·대량 원장 변환을 보조한다.

**구현 내용**
- `backend/app/ingest/profiling.py`, `recommendation.py`, `transformation.py`, `api/ingest_assistance.py`, 입력 DTO/Schema와 소규모 벤치마크를 추가했다.

**검증 결과**
- 당시 벤치마크·API·대량 합성 자료에서 **86,214→498 정답 일치**를 확인했다. 당시 전체 PostgreSQL 포함 638 passed/0 skipped, 별도 비DB 577 passed/61 skipped 기록은 보고서에 있다. 신규 변환 이력 저장(후속 0009)의 검증은 아니다.

**기술적 결정**
- 결정적 후보/형식 반증/사용자 확인, SYNTHETIC_ONLY 정책의 정상/취소/반품 분리를 선택했다. 외부 AI 호출·자동 승인·임의 정책 확장은 적용하지 않았다.

**남은 문제**
- 분류 entity 연계, 변환 결과와 배치/영구 이력 연결, 후보 속도/모호성 개선이 필요했다.

**관련 자료**
- [Commit d21423e](https://github.com/ChungPaMo/decision-supporter-mvp/commit/d21423e), [설계](AI_MAPPING_INTEGRATION_DESIGN.md), [벤치마크](DATA_INGESTION_BENCHMARK.md).

### 2026-11-16 — 이훤 규칙 분류기와 별도 문서 분류 연구

**Git**
- 시작 Commit: `03a9470`.
- 완료 Commit: 업로드 규칙 `ebf5f47`, 별도 문서 분류/의미어 연구·문서 `115ed4d`→`d8954c7`→`fefe103`.
- 브랜치: `main` 계보.

**작업 목적**
- 파일 유형 추천/HOLD를 구현하고, 다른 양식의 문서 분류 가능성을 별도 조사한다.

**구현 내용**
- 이훤 담당 `modules/file_classifier/src/file_classifier/` 규칙·경계·합성 시험과 폴더 분류 도구/연구를 추가했다. API용 `AVAILABLE=True`/규칙 분류와 별도 문서·임베딩 실험은 다른 경로다.

**검증 결과**
- 규칙·경계·fixture 시험 및 합성 문서 평가 결과가 모듈에 있다. 독립 당일 pytest 합계는 여기서 추정하지 않는다. 실제 API 연계의 초기 실패/최종 회귀는 아래 `0a60e92` 보고서를 따른다. 연구 결과는 실제 기업 데이터 성능 증거가 아니다.

**기술적 결정**
- CAPA/Routing/판매 원장 등 모호한 파일은 HOLD로 두고 별도 도구의 embedding을 업로드 API에 연결하지 않았다.

**남은 문제**
- 기존 API 테스트의 미구현(501) 가정 수정과 분류→매핑 연결이 필요했다.

**관련 자료**
- [Commit ebf5f47](https://github.com/ChungPaMo/decision-supporter-mvp/commit/ebf5f47), [연구 Commit d8954c7](https://github.com/ChungPaMo/decision-supporter-mvp/commit/d8954c7), [분류기 설명·연구 구분](../modules/file_classifier/README.md), [후속 API 검증](INGESTION_INTEGRATION_VERIFICATION_20261116.md).

### 2026-11-16 — 프론트엔드 데이터셋·업무 화면 보강

**Git**
- 시작 Commit: `fefe103`.
- 완료 Commit: `f6818fc`→`d6bf46c`→`0762ebf`.
- 브랜치: `main` 계보.

**작업 목적**
- 공통 셸·예시 시나리오·데이터셋 연계와 실제 업무 화면의 상호작용을 정리한다.

**구현 내용**
- `frontend/`의 데이터셋 선택/상태 초기화, 화면·공통 셸·업무 UX를 보강했다. 현재 배치 등록·재검증·승인, 분류 패널과 예측 조회가 있으며 DEMO와 실제 API 흐름을 구분한다.

**검증 결과**
- Commit 변경 파일과 현재 소스, 후속 `0a60e92`의 비DB 브라우저 8 passed 및 `86a1fdb`의 type-check/build 보고가 근거다. 이 프론트 변경 당시의 별도 테스트 합계와 신규 입력 UI E2E 완료는 추정하지 않는다.

**기술적 결정**
- 기존 화면·배치/승인 흐름을 유지하며 DEMO 성공을 실서비스 성공으로 대체하지 않는다.

**남은 문제**
- 이후 추가된 profile/Top-3/판매 정책·변환 이력 UI는 아직 연결되지 않았다. 담당자에게 API 인계/화면 변경 요청을 전달한다.

**관련 자료**
- [Commit f6818fc](https://github.com/ChungPaMo/decision-supporter-mvp/commit/f6818fc), [Commit 0762ebf](https://github.com/ChungPaMo/decision-supporter-mvp/commit/0762ebf), [확인된 기존 화면·변경 요청](INGESTION_UI_CHANGE_REQUEST.md).

### 2026-11-16 — 분류·매핑·변환 이력 연결

**Git**
- 시작 Commit: 최신 통합 기준 `0762ebf` (작업 시작 시 로컬 `115ed4d`에서 갱신).
- 완료 Commit: `0a60e92`.
- 브랜치: `main`.

**작업 목적**
- 기존 분류·매핑·판매 변환을 연결하고 원본/정책/결과를 승인 전 배치와 함께 보존한다.

**구현 내용**
- 분류 API 경계와 classified-mapping을 통합하고 `backend/app/ingest/history.py`, `history_repository.py`, `api/ingest_assistance.py`에 명시적 이력 생성·조회/재사용·배치 연결을 추가했다.
- Alembic 0009와 `dataset_schema_v2.py`에 불변 근거/원자 저장/스키마 갱신 코드를 작성했다. 기존 정확 매핑·수동 override·승인 digest/버전 게이트를 보존했다.

**검증 결과**
- 초기 비DB 회귀 **874 passed / 1 failed / 61 skipped**: 실제 분류기를 501로 가정한 실패를 현재 계약에 맞게 수정했다.
- 최종 **906 passed / 0 failed / 63 skipped**, 비DB Playwright 8 passed, type-check/build·계약·오프라인 migration 검사 통과. 이력/롤백/재사용은 **메모리 저장소 시험**이다. **0009 온라인 적용·실DB 잠금/트리거/원자성은 미실행**.

**기술적 결정**
- 기존 서비스/승인 전 배치를 재사용하고 전체 결과·원본 SHA·확인 정책을 불변 근거로 연결했다. 현재 PC에서는 DB 작업을 하지 않았다. 실패를 skip/가짜 성공으로 바꾸지 않았다.

**남은 문제**
- 기존 개발 PC에서 0009 적용·독립 DB 시험·이력의 실제 영구 보존을 확인해야 한다.

**관련 자료**
- [Commit 0a60e92](https://github.com/ChungPaMo/decision-supporter-mvp/commit/0a60e92), [연계/이력 계약](INGESTION_INTEGRATION_HISTORY.md), [검증 보고서](INGESTION_INTEGRATION_VERIFICATION_20261116.md).

### 2026-11-16 — RapidFuzz Top-3 컬럼 후보 개선

**Git**
- 시작 Commit: `0a60e92`.
- 완료 Commit: `25d94ae`.
- 브랜치: `main`.

**작업 목적**
- 기존 규칙을 유지하면서 기업 파일 매핑 검토에 사용할 후보의 속도·오류·HOLD를 소규모로 비교한다.

**구현 내용**
- `backend/app/ingest/recommendation.py`에서 RapidFuzz Top-3·형식/의미 반증을 재사용 가능한 추천 경로로 적용했다. 별칭을 정답으로 복사하지 않은 48건 평가 자료·저장 결과와 회귀 시험을 추가했다.

**검증 결과**
- 당시 비교에서 RapidFuzz와 기존 SequenceMatcher 후보 Top-3는 26/32(81.25%)로 같고, 오답 1순위 6/48·무후보 17/48이 남았다. RapidFuzz는 측정 환경에서 약 5.9배 빨랐다. 정확 규칙 자동 매핑의 성능 개선으로 해석하지 않는다.
- 당시 전체 비DB pytest **914 passed / 0 failed / 63 skipped**. BGE-M3는 기존 연구 결과만 검토했으며 새 48건 평가의 동등 실측 결과가 아니다. 모델/LLM/Upstage 호출 없음.

**기술적 결정**
- 정확 매핑·사용자 확인·승인을 유지하는 검토 전용 추천을 선택했다. 복잡한 모델 조합/대규모 탐색 대신 오류·문맥 한계를 기록하고 Upstage는 후속 계약 대안만 정리했다.

**남은 문제**
- 새 표현/유사 후보의 잘못된 추천과 의미 구별이 남는다. 점수만으로 자동 등록/승인하지 않고 UI 연결·실제 기업 적용 검토가 필요하다.

**관련 자료**
- [Commit 25d94ae](https://github.com/ChungPaMo/decision-supporter-mvp/commit/25d94ae), [방법·오류·MVP/후속 LLM 계약](MAPPING_RECOMMENDATION_MVP_20261116.md), [기존 벤치마크](DATA_INGESTION_BENCHMARK.md).

### 2026-11-16 — 공식 데이터 API E2E 및 프론트엔드 인계

**Git**
- 시작 Commit: `25d94ae`.
- 완료 Commit: `86a1fdb`.
- 브랜치: `main`.

**작업 목적**
- 공식 자료의 실제 데이터 계약과 입력 API 사용자 흐름을 확인하고 화면 담당자가 기존 기능을 재사용하도록 인계한다.

**구현 내용**
- `backend/tests/ingestion_e2e_support.py`, `test_ingestion_api_e2e.py`, `test_ingestion_sales_generated.py`, 인계 계약 검사와 `contracts/examples/ingestion_e2e_source_manifest.json`을 추가/보강했다.
- `docs/INGESTION_UI_API_HANDOFF.md`, `INGESTION_UI_CHANGE_REQUEST.md`에 실제 DTO·상태·버튼/정책·dataset 범위와 기존 UI 재사용 요청을 작성했다. 운영 코드/담당 모듈·frontend는 변경하지 않았다.

**검증 결과**
- 원본/정답 **14파일 SHA 보존**, 공식 8마스터 배치와 판매 변환 9번째 수요 배치, **86,214→498 독립 정답 일치**를 TestClient로 검증했다. 저장소와 CAPA SQL만 메모리 대역이며 PostgreSQL 검증이 아니다.
- 대표 흐름 1 passed, 오류/확인+기존 추천 집중 33 passed, 인계 계약 4 passed; 최종 비DB **943 passed / 0 failed / 63 skipped**, type-check/build·계약 동기화·보안 검사 통과. 신규 입력 브라우저·실DB E2E는 미실행이다.

**기술적 결정**
- 표준 05 월수요 파일은 독립 정답으로만 읽고 원장 변환과 이중 등록하지 않았다. 오류 fixture만 별도로 파생했다. 기존 추천 평가/모델을 불필요하게 다시 측정하지 않았다.

**남은 문제**
- 0009 실DB 적용/검증, 나미 담당 새 입력 UI 연결, 실제 계획 엔진 확인과 전체 브라우저 E2E가 남았다. 기존 npm 취약점 2건과 Starlette/httpx 경고는 보고서의 인계 상태를 유지한다.

**관련 자료**
- [Commit 86a1fdb](https://github.com/ChungPaMo/decision-supporter-mvp/commit/86a1fdb), [E2E 상세](INGESTION_API_E2E_VERIFICATION_20261116.md), [API 인계](INGESTION_UI_API_HANDOFF.md), [화면 요청](INGESTION_UI_CHANGE_REQUEST.md).

### 2026-11-17 — 영구 진행상황 기록 체계 구축

**Git**
- 시작 Commit: `86a1fdb7399741c80bc376dfa794d518bf327cac` (로컬/원격 main 일치, 작업 트리 clean).
- 완료 Commit: 이 항목을 포함하는 고유 제목 **`docs: establish project progress records and agent rules`**의 Commit. 자기 SHA를 사전에 적는 대신 `git log main -1 --format=%H --fixed-strings --grep='docs: establish project progress records and agent rules'`로 조회한다. 실제 SHA와 Push 결과는 완료 후 최종 응답에 보고한다.
- 브랜치: `main`. 새 브랜치/PR 없음.

**작업 목적**
- PC·세션·대화가 바뀌어도 실제 구현/검증/후속 작업을 이어갈 수 있는 저장소 기준 기록과 Codex 상시 절차를 만든다.

**구현 내용**
- 기존 루트 AGENTS가 없음을 확인하고 `AGENTS.md`에 시작/완료 기록 의무·검증 정직성·Git/소유권/데이터 보호·현재 PC DB 금지를 통합했다.
- `docs/PROJECT_PROGRESS.md`에 최신 상태/담당/검증 경계/남은 작업을, 이 파일에 Git/보고서 기반 누적 이력을 작성했다. `README.md`, `docs/DEVELOPMENT_WORKFLOW.md`에 진입 링크와 현재 환경 제한을 추가했다.
- 기능 코드·원본/정답·migration·담당 폴더를 변경하지 않았다. Notion은 조회/수정/동기화하지 않았다.

**검증 결과**
- `git fetch origin`, `git pull --ff-only origin main`: 시작 시 최신 `86a1fdb`, 로컬/원격 일치 확인.
- 문서 정적 검사 통과: 변경 Markdown 5개, 로컬 링크 70개, main 계보의 Git 참조 19개, 변경 이력 13항목/항목별 7개 필수 구획, 변경 범위·공백·문자 인코딩 확인. 실제 구현 상태는 분류/계획 capability·매핑/예측 소스와 기존 보고서를 대조했다.
- 기능 테스트/모델/브라우저/DB/API는 미실행. 문서 작업에 불필요한 재실행을 피했으며 **943 passed / 63 skipped는 11/16 과거 결과**다.

**기술적 결정**
- Git Markdown 두 문서를 기준으로 최신 현황/누적 이력을 구분하고 상세 시험은 기존 보고서로 연결한다. 계획 이력 저장 기반과 미구현 계산 엔진, 메모리 E2E와 실제 PostgreSQL 검증을 분리했다.
- Commit 자체의 SHA를 미리 만들 수 없으므로 이번 항목은 고유 제목으로 완료 Commit을 식별한다. 반복 amend/빈 Commit을 만들지 않고 최종 응답에서 확인된 SHA를 보고한다.

**남은 문제**
- 기존 개발 PC의 0009/독립 DB 검증, 나미의 신규 입력 API 화면 연결, 희원의 계획 엔진 통합 확인, 전체 브라우저 E2E·기업 데이터 검토는 [현재 현황](PROJECT_PROGRESS.md)의 담당/범위를 따른다.
- 향후 매 작업에서 이 규칙을 적용한다. Notion 팀 공유 페이지로의 동기화는 이번 범위에 포함하지 않았다.

**관련 자료**
- [AGENTS](../AGENTS.md), [현재 현황](PROJECT_PROGRESS.md), [개발 절차](DEVELOPMENT_WORKFLOW.md), [기준 코드 Commit 86a1fdb](https://github.com/ChungPaMo/decision-supporter-mvp/commit/86a1fdb), [공식 E2E 근거](INGESTION_API_E2E_VERIFICATION_20261116.md).

### 2026-11-17 — 기존 개발 PC PostgreSQL 입력 이력·공식 E2E 검증

**Git**
- 시작 Commit: `acd40a511a57b9c0d92d2391a2d028ed09914af7`, main clean, fetch/switch/pull --ff-only 후 원격 일치.
- 완료 Commit: 고유 제목 `test: verify PostgreSQL ingestion history and preserve development data`로 이 항목을 포함하는 Commit. `git log main -1 --format=%H --fixed-strings --grep='test: verify PostgreSQL ingestion history and preserve development data'`로 조회하며 실제 SHA/Push는 완료 응답에서 확인한다.
- 브랜치: `main`, 새 브랜치/PR/강제 Push 없음.

**작업 목적**
- 기존 승인 자료를 보존하면서 다른 PC에서 준비한 0009·SQL 변환 이력·공식 자료 입력→명시적 승인→예측을 실제 PostgreSQL로 검증한다.

**구현 내용**
- `backend/tests/test_db_ingestion_history.py`: IMMEDIATE로 staging을 확인한 뒤 DEFERRED 기본값을 복원하고 승인 후에도 제약을 검증했다. 운영 승인/트리거·migration은 변경하지 않았다.
- `backend/tests/test_db_ingestion_official.py`: 공식 14파일 SQL E2E, 201/200 동시 재전송, 실제 unique 위반에 의한 원자 rollback, commit 후 불변성/추가원본 거부, 승인된498행→예측OK27행을 추가했다.
- `scripts/verify_ingestion_migration_postgres.py`: 승인된 회귀 DB에서 새0008→실제0009 upgrade 본문을 실행해 보관dataset 포함81테이블 보존을 확인하고 probe를 rollback했다. downgrade는 없다.
- `scripts/postgresql_preservation.py`, `scripts/apply_ingestion_0009.py`, 안전성 테스트: 개발 DB 강제 읽기 전용 지문/백업 및 별도 승인 적용 guard를 마련했다. 상세 보고서와 PROJECT_PROGRESS를 갱신했다.

**검증 결과**
- Docker Desktop4.70.0/Engine29.4.0, 기존 chungpamo-monorepo-db·전용 볼륨/네트워크·55433을 확인했다. 개발 chungpamo/chungpamo_app은0008, 승인7+9배치·예측각1이었다. 다른 DB에는 접속하지 않았다.
- 초기 환경의 RapidFuzz 누락을 고정3.14.6 설치로 보완했다. 초기 실DB1003 passed/1 failed/2 deselected는 위 fixture 타이밍 문제였고 수정 후 집중5개가 통과했다.
- 최종 전체 **1015 passed / 0 failed / 0 skipped / 2 deselected**. 기존 DB63개 중61개+신규SQL3개가 통과했다. 사용자 지시에 따라 과거 downgrade2개는 미실행이다. 별도 보존/승인 가드8개도 통과했으며 최종 전체에 포함된다.
- 공식원장86,214→498/원본14SHA/정답/저장 bytea/승인 지문/미승인 제외/예측이력은 **실제 PostgreSQL** 증거다. 타입/빌드·OpenAPI/Schema·pip check·컴파일·보안도 통과했다. 기존 Starlette/httpx warning1건은 남는다. 전체 브라우저는 미실행이다.
- 개발56테이블/기존 DB객체/승인배치·예측·Docker identity는 회귀 전후 동일. 비공개 pg_dump custom 백업292,343 bytes와 전체SHA/pg_restore목차를 검증했으며 실제복구리허설은 하지 않았다.
- 이후 별도 사용자 승인으로 개발DB의 현재0008·동일사전지문·백업을 재검사하고 **0008→0009만 적용**했다. 기존55개 데이터 테이블과 승인7+9배치·예측2건·기존객체가 동일했고 버전만 변경됐다. 새이력4테이블은0행/총60테이블이며, 적용후 GET24건을 PostgreSQL 강제 READ ONLY로 확인했다.
- 최종 별도 비DB는 **951 passed / 0 failed / 66 skipped**. 새보존가드8개는 최종전체/비DB 모두 포함한다. 실제저장 E2E는 회귀DB에만 한정하고 개발DB에 공식자료를 중복등록하지 않았다.

**기술적 결정**
- 사용자가 기존 개발 PC의 Docker/DB 사용·회귀초기화와 개발0009를 각각 새로 승인했다. 개발DB에는 additive upgrade만 적용하고 초기화·downgrade·자동복구를 하지 않았다. 과거 보조 PC 금지·DB 초기화 승인을 포괄 재사용하지 않는다.
- 현재0009와 v2의 실제 SQL 동작을 검증했으며 새 migration을 만들거나 기존0001~0008/담당폴더/원본/정답을 수정하지 않았다. 파괴적 fixture는 회귀 DB에만 한정하고 회귀 DB 자체는 보존한다.

**남은 문제**
- 김대영: 적용된 개발/회귀0009의 환경 정합성을 유지하고 백업 실제복구리허설/보존기간 정책을 후속 검토한다. 이번에 복구는 필요하지 않았고 미승인 변경·자동복구·downgrade는 하지 않았다.
- 정마나미: 신규 입력 UI/클라이언트 dataset scope와 전체 브라우저 E2E. 이희원: 실제 계획 계산/정식승인 정책은 별도. 이훤: 분류기는 기존 구현을 호출했으며 별도 알고리즘 변경은 없다.
- Notion 동기화·기업 데이터 적합성·기존 npm 취약점 인계는 이번에 완료/해결했다고 주장하지 않는다.

**관련 자료**
- [기준 Commit acd40a5](https://github.com/ChungPaMo/decision-supporter-mvp/commit/acd40a511a57b9c0d92d2391a2d028ed09914af7), [이번 상세 검증](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md), [현재 현황](PROJECT_PROGRESS.md), [기존 이력 계약](INGESTION_INTEGRATION_HISTORY.md), [공식14파일 manifest](../contracts/examples/ingestion_e2e_source_manifest.json).

### 2026-11-17 — 생산계획 엔진 현황 및 백엔드 통합 준비 분석

**Git**
- 시작 Commit: `77067f128ea0531f24855584f9ccfa41f2b84d3b`. 작업 트리 clean, fetch→main switch→pull --ff-only 후 로컬/원격 일치.
- 완료 Commit: 이 항목을 포함하는 고유 제목 **`docs: assess planning engine integration readiness`**. `git log main -1 --format=%H --fixed-strings --grep='docs: assess planning engine integration readiness'`로 실제 SHA 조회, Push/원격 일치는 완료 후 최종 응답에 보고한다.
- 브랜치: `main`. 새 브랜치/PR/강제 Push 없음.

**작업 목적**
- 희원 담당 실제 계산 구현과 김대영의 기존 API/SQL 기반을 구분하고, 엔진 완성을 기다리지 않고 수행할 독립 통합 작업과 계약 의존 작업을 특정한다.

**구현 내용**
- [PLANNING_ENGINE_INTEGRATION_READINESS](PLANNING_ENGINE_INTEGRATION_READINESS.md) 추가: 구성요소별5단계 상태, 실제 코드/테스트 근거, 공식 자료 대조, 기존 API/저장7테이블/What-if·승인 gate, 계약 차이 C01~C11, 담당·파일·선행 조건·완료 기준 B01~B09, 희원/나미 인계와 단계별 순서 정리.
- [PROJECT_PROGRESS](PROJECT_PROGRESS.md)를 최신 분석 범위로 갱신했다. 기존 완료 기능·직전 전체1015/2제외 기록은 보존하고 이번 집중71개와 분리했다.
- 서비스/계획·분류 엔진/frontend/공식 생성기·정답/migration/테스트 코드는 수정하지 않았다. 기존 INTEGRATION_CONTRACT 등의 과거 설명과 현재 코드 차이는 새 보고서에 정정 관계로 기록했다.

**검증 결과**
- 2026-11-17 집중 비DB pytest **71 passed / 0 failed / 0 skipped**: 모듈 경계10개와 계획 어댑터/source/저장·capability/Schema 검사. Starlette/httpx deprecation warning1건. 기존 테스트 대역은 계산 완료 근거가 아니다.
- 실제 개발 DB `127.0.0.1:55433/chungpamo`, 역할 `chungpamo_app`, 전용 Docker identity와 revision0009/강제 READ ONLY 확인. 공식3개 월의 단일 월 PlanningInput을 기존 SQL provider로 조립했다. 월마다9제품·9자재·BOM27줄·재고18·자원6·시간6·수량한도1·라우팅27/추가인력9·승인출처9 확인. 정책 미확인 상태는 유지했다.
- 공식 수요498행의 제품/기간/Decimal 수량/단위 정답 일치, 원본manifest14파일 SHA 전후 일치. 타dataset forecast404·provider 소속409·모르는 제품409 확인. 실제 planning.run은 NotImplementedError, 계획3API501·GET목록200/0건·APPROVE501 확인.
- DB60테이블 전체 행 지문·스키마객체735개 정의·registry·승인7+9배치·예측각1건·revision·Docker identity 전후 불변. 테스트/회귀DB에 접속하거나 개발DB를 변경/초기화하지 않았고 migration도 실행하지 않았다. 접속 설정 외에 실제 SQL provider/엔진을 성공 대역으로 바꾸지 않았다.
- 일회성 검증 스크립트의 datetime/JSON 비교와 잘못된 조회 컬럼명 오류를 바로잡아 최종 조회/보존 대조를 통과했다. 서비스 결함으로 오인하거나 최초 검사 실패를 통과로 기록하지 않는다. 상세 증거는 ignored `.artifacts/planning-readiness-20261117/`에만 둔다.
- 전체 pytest·파괴적 PostgreSQL 회귀·migration 왕복·브라우저·TypeScript/build는 분석 범위에 필요하지 않아 미실행. 변경 문서 로컬 Markdown 링크107개·diff --check·보안 검사(텍스트435파일/findings0)를 통과했다. 휴리스틱 보안 검사이며 백업·비밀값·공식 원본은 Git에 포함하지 않는다.

**기술적 결정**
- MPS/RCCP/MRP/What-if는 여전히 미구현이다. v0.3·12개 HC 손계산을 구현 완료로 바꾸지 않는다. 실제 SQL로 검증한 것은 승인 입력 조립이며 계산/REAL_ENGINE 저장 성공이 아니다.
- 새 provider/계획 저장 테이블을 중복 생성하지 않는다. 기존 연결점을 재사용하는 입력 진단·참조 검증·계약/fixture 인계는 독립 작업으로 분리했다.
- 단일 월↔3개월, 예정 입고/What-if 범위, 음수 부족량 증감, 정책 판정/승인 차이는 변경 요청으로 유지한다. PlanningOutput의 HARD VIOLATED+FEASIBLE 검증 공백도 기록했으며 이번에 코드나 업무 규칙을 임의 수정하지 않았다. APPROVE501 유지.

**남은 문제**
- 김대영: B01/B02/B03/B09부터 독립 진행 가능. 입력 진단 API 경로는 제안이며 아직 구현하지 않았다. C01~C06 합의 후 기간/입고/정책/What-if 확장·실엔진 SQL 검증 준비.
- 이희원: v0.3 변경 확인, 자재 수량 의미·부족 입력/공유 자원 정책·What-if 범위 확정 요청에 답하고 owner 폴더에서 실제 run 및 HC 정답 자동 비교 구현.
- 정마나미: 기존 API client의 영구 계획 메서드 재사용, Preview/저장/승인·DEMO 분리, 기간/기준일/계보·오류·복원 화면 연계. 이번에 frontend는 변경하지 않았다.
- 정식 승인·비용/KPI·서버 인증·최종 브라우저 제조E2E는 의존 작업이다. 미구현501을 임의로 해제하지 않는다.

**관련 자료**
- [기준 Commit 77067f1](https://github.com/ChungPaMo/decision-supporter-mvp/commit/77067f128ea0531f24855584f9ccfa41f2b84d3b), [이번 통합 준비 보고서](PLANNING_ENGINE_INTEGRATION_READINESS.md), [최신 상태](PROJECT_PROGRESS.md), [희원 규칙 초안](../modules/planning_engine/PLANNING_RULES.md), [기존 계획 저장 계약](PLAN_EXECUTION_PERSISTENCE.md), [직전 실제 SQL 검증](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md).

### 2026-11-18 — 계획 입력 진단 API·공통 검증·계약 협의 명세

**Git**
- 시작 Commit `231bcb262c98e764349fc54e5c3c6706e083f46f`, fetch 및 fast-forward 후 확인.
- 완료 Commit은 고유 제목 `feat: diagnose approved planning inputs without running the engine`으로 조회한다. `git log main -1 --format=%H --fixed-strings --grep='feat: diagnose approved planning inputs without running the engine'`
- 브랜치 `main`.

**작업 목적**
- 계획 계산 구현 전에도 저장 예측과 승인 자료의 단일 월 입력을 확인하고 B01~B03을 보조 PC에서 검증한다.

**구현 내용**
- `backend/app/api/integrations.py`에 `POST /planning-inputs/preview`를 추가했다. `backend/app/integrations/planning.py`와 `planning_validation.py`에서 기존 provider·참조·출처·단위·기간 검증, 요약·지문을 연결했다.
- `contracts/interfaces/planning.py`와 OpenAPI/Schema/합성 예시를 갱신했다. 신규 TestClient·provider 대역 회귀, C01~C11 차이·8개 인수 사례·화면 인계를 추가했다.

**검증 결과**
- 최종 루트 비DB pytest **978 passed / 0 failed / 66 skipped / 6 deselected**. 실DB 테스트 66개는 접속 차단, 오프라인 Alembic 호출 검사 6개는 선택 제외했다. 초기 회귀의 OpenAPI enum 순서와 가이드 누락 2건을 수정해 재검증했다.
- `persisted=false`, 실행 생성 금지, 기존 계산 API의 501, OpenAPI/JSON Schema/예시 동기화 통과. Docker·실DB·Alembic·브라우저는 미실행이다.

**기술적 결정**
- 기존 BASE 명령과 단일 월 범위로 진단한다. 200 응답에서 누락과 모호성을 표시하고 필수 예측 범위·변조·참조 충돌은 기존 오류 계약으로 처리한다. LEGACY에서도 수요 출처를 검증하며 기존 계획 스냅샷 형식을 보존한다.
- 입력 존재와 엔진 가용성을 별도 필드로 제공한다. 업무 정책 합의 항목은 테스트 명세에서 보류하고 `POLICY_NOT_CONFIRMED`를 유지한다.

**남은 문제**
- 기존 개발 PC에서 공식 저장 예측으로 새 경로의 실제 PostgreSQL 읽기·격리·출처·지문 및 이력 보존을 확인한다.
- 이희원과 기간·입고·What-if·정책·부호·판정을 확정한다. 정마나미에게 단일 월 진단 응답·오류·상태별 화면 계약을 인계한다.

**관련 자료**
- [시작 Commit 231bcb2](https://github.com/ChungPaMo/decision-supporter-mvp/commit/231bcb262c98e764349fc54e5c3c6706e083f46f), [진단 검증·인수 명세](PLANNING_INPUT_DIAGNOSTICS_VERIFICATION.md), [현황](PROJECT_PROGRESS.md), [통합 계약](INTEGRATION_CONTRACT.md).

### 2026-11-22 — 계획 엔진 계산 규칙 v0.4·통합 준비 보고서 답변 (이희원)

**Git**
- 시작 Commit `91f9cc9953f5bb6a2ceb9472cfa275ccd484fe18` (fetch 후 fast-forward).
- 완료 Commit은 고유 제목 `docs: planning rules v0.4 and contract answers for planning engine`으로 조회한다. `git log main -1 --format=%H --fixed-strings --grep='docs: planning rules v0.4 and contract answers for planning engine'`
- 브랜치 `main`.

**작업 목적**
- [통합 준비 보고서](PLANNING_ENGINE_INTEGRATION_READINESS.md) §4 C01~C11과 §6 희원 확인 9가지에 답하고, 계산 규칙의 구멍(C05 자재 음수 등)을 계산 구현 전에 막는다.

**구현 내용**
- `modules/planning_engine/PLANNING_RULES.md` v0.4: 자재 결과를 교과서식 월별 MRP(required = 그달 총소요, available = 월초 재고 + 그달 입고, shortage = 그달 발주 필요량, 음수 없음)로 변경. 입고 예정은 미입고 수량·입고 달 전체 사용·납기 지남은 1월 + `RECEIPT_OVERDUE`. 예측 누락 `INPUT_INVALID`, 재고 누락 0 + `INVENTORY_MISSING`·UNVERIFIED, 다단계 BOM·ELAPSED·GROSS `UNSUPPORTED`, 셋업·대체 설비는 무시 + UNVERIFIED. What-if는 수요 배수·잔업 한도(자원·월)·입고 변경 3종이며 세 안 모두 재계산. feasibility는 계산 판정이고 승인 여부는 백엔드 정책.
- `modules/planning_engine/CONTRACT_REQUESTS.md`: §6 답변과 C01~C11 입장·요청(기간 필드, 입고 예정 필드, 월별 What-if 키, FEASIBLE+HARD VIOLATED 거부 검사).
- `tests/hand_calc/small_cases.json`·`SMALL_CASES.md`: HC-09를 v0.4 MRP 의미로 갱신(가용량 150/120, 발주 필요량 80/110 유지).

**검증 결과**
- 2026-11-22 이희원 PC, 루트 `.venv`: `pytest modules/planning_engine` **34 passed / 0 failed**. 규칙서만 보고 별도 작성한 임시 계산 스크립트로 HC-01~12 재계산 **12/12 일치**. JSON 파싱·`git diff --check` 통과.
- 계획 엔진 계산 코드는 없으므로 엔진 결과와 정답 비교는 미실행. Docker·DB·브라우저 미실행.

**기술적 결정**
- 각 결정은 희원이 추천안 중 선택(자재 MRP, 입고 단순+경고, 예측 누락 거절, 재고 누락 0+경고, 미지원은 틀리면 거절·조금이면 경고, What-if 3종·세 안 재계산, 엔진 판정/승인 분리). 누적 부족 방식, 엄격한 입고 처리, 예측 누락 PARTIAL, 생산량 직접 지정은 채택하지 않음.

**남은 문제**
- 김대영: C01 기간·C02 입고 예정·C03 What-if 키·C04 정책 버전·C06 모순 출력 검사 검토.
- 이희원: HC 보강(입고·재고 누락·미지원 케이스), 계산 코어 구현과 HC 자동 비교 테스트, 충파모 9제품×3개월×3안 정답 비교, What-if. 계약 확정 전 `AVAILABLE=False` 유지.

**관련 자료**
- [계산 규칙 v0.4](../modules/planning_engine/PLANNING_RULES.md), [계약 답변](../modules/planning_engine/CONTRACT_REQUESTS.md), [작은 손계산](../modules/planning_engine/tests/hand_calc/SMALL_CASES.md), [통합 준비 보고서](PLANNING_ENGINE_INTEGRATION_READINESS.md).

### 2026-11-22 — 계획 엔진 손계산 케이스 보강 HC-13~17 (이희원)

**Git**
- 시작 Commit `766d48ce4cb004e271408cfb67dc2d378dad2036`.
- 완료 Commit은 고유 제목 `test: add planning hand-calc cases for receipts, missing inventory and unsupported inputs`으로 조회한다. `git log main -1 --format=%H --fixed-strings --grep='test: add planning hand-calc cases for receipts, missing inventory and unsupported inputs'`
- 브랜치 `main`.

**작업 목적**
- 계산 코어 구현 전에, v0.4에서 정했지만 정답이 없던 입고 예정·재고 누락·미지원 기능 처리를 손계산 정답으로 고정하고, 그 과정에서 드러난 규칙 빈틈을 막는다.

**구현 내용**
- `modules/planning_engine/tests/hand_calc/small_cases.json`·`SMALL_CASES.md`: HC-13 입고 예정(미입고 수량만, 납기 지남 1월·경고·UNVERIFIED, 기간 뒤·BOM 밖 무시), HC-14 재고 누락(0으로 계산·UNVERIFIED), HC-15 다단계 BOM(UNSUPPORTED), HC-16 입고 단위 오류+다단계 BOM(INPUT_INVALID, 오류 모두 나열), HC-17 셋업 시간 무시(UNVERIFIED). 입고 예정 입력을 C02 요청 필드 모양(`po_id, material, open_qty, unit, expected_date`)으로 바꾸고 HC-09도 같은 모양으로 갱신(정답 변화 없음).
- `modules/planning_engine/PLANNING_RULES.md` v0.4 보강: 납기 지난 입고가 있는 자재의 1월 MAT는 `UNVERIFIED`(`RECEIPT_OVERDUE`), BOM에 없는 자재 입고는 무시, 입고 단위 오류는 `INPUT_INVALID`/`UNIT_MISMATCH`, 문제가 겹치면 `INPUT_INVALID` > `UNSUPPORTED` 순서이고 error_codes에 모두 나열.
- `CONTRACT_REQUESTS.md`: HC-13 참조 문구 정리.

**검증 결과**
- 2026-11-22 이희원 PC, 루트 `.venv`: `pytest modules/planning_engine` **34 passed / 0 failed**(계산 코드 없음, 기존 구조 검사).
- 규칙서만 보고 별도 작성한 임시 검산 스크립트(판정·feasibility·경고·오류 코드까지 비교)로 HC-01~17 **17/17 일치**. 정답을 일부러 틀리게 바꾼 5건은 모두 불일치로 검출. JSON 파싱 통과.
- 엔진 결과와 정답 비교는 계산 코드가 없어 미실행. Docker·DB·브라우저 미실행.

**기술적 결정**
- 희원이 추천안 중 선택: 납기 지난 입고는 계산에 넣되 판정은 UNVERIFIED(경고만 / 계산 제외 안은 채택 안 함), 입고 단위 오류는 INPUT_INVALID·BOM 밖 입고는 무시(행만 빼고 경고 / 모두 거절 안은 채택 안 함), 상태 우선순위 INPUT_INVALID > UNSUPPORTED이고 오류 모두 나열(첫 오류에서 멈춤 안은 채택 안 함).
- 입고 예정 필드 모양은 C02 요청안을 따랐다. 대영 검토로 필드가 바뀌면 케이스 입력 모양만 고친다.

**남은 문제**
- 김대영: C01 기간·C02 입고 예정·C03 What-if 키·C06 모순 출력 검사 검토(변경 없음).
- 이희원: 계산 코어 구현과 HC-01~17 자동 비교 pytest, 충파모 9제품×3개월×3안 정답 비교, What-if. 계약 확정 전 `AVAILABLE=False` 유지.

**관련 자료**
- [계산 규칙 v0.4](../modules/planning_engine/PLANNING_RULES.md), [작은 손계산](../modules/planning_engine/tests/hand_calc/SMALL_CASES.md), [계약 답변](../modules/planning_engine/CONTRACT_REQUESTS.md), [시작 Commit](https://github.com/ChungPaMo/decision-supporter-mvp/commit/766d48ce4cb004e271408cfb67dc2d378dad2036).

### 2026-11-22 — 계획 엔진 계산 코어와 손계산 자동 비교 (이희원)

**Git**
- 시작 Commit `c306d7d7daad7a76326faad988a0b3848701fc8f`.
- 완료 Commit은 고유 제목 `feat: planning calculation core with hand-calc comparison tests`으로 조회한다. `git log main -1 --format=%H --fixed-strings --grep='feat: planning calculation core with hand-calc comparison tests'`
- 브랜치 `main`.

**작업 목적**
- 비어 있던 계획 계산(MPS/RCCP/MRP·판정)을 PLANNING_RULES v0.4대로 구현하고, 손계산 정답과 자동 비교해 규칙대로 계산함을 보인다.

**구현 내용**
- `modules/planning_engine/rccp/core.py`: 한 달 안 같은 비율 축소(정수 내림), 사용시간. `mps/core.py`: 계획 수요·목표량, 뒤에서부터 선행생산, 앞에서부터 보충, 재고 추적. `mrp/core.py`: BOM 단위 소요, 입고 예정 배치, 월별 MRP 표.
- `engine/planning_core.py`: 내부 형식(손계산 JSON과 같은 모양) 입력 검사(§7, 오류 모두 수집, INPUT_INVALID > UNSUPPORTED), 판정 CAP/QTY/DEM/SS/MAT, 계획안 feasibility, 세 안(BASELINE P50+잔업 / STABLE P80+잔업 / COST_SAVING P50 정규만) 계산. 필드 이름은 계약 ConstraintEvaluation과 같게 맞춤.
- `tests/test_hand_calc.py`: HC-01~18 자동 비교(적힌 항목만 비교, 모르는 항목·중복 판정 ID는 실패). `tests/test_planning_core_edges.py`: 입력 경계 16개. 손계산 HC-18(정수 내림 7.5→7) 추가.
- `PLANNING_RULES.md` v0.4 보강: 라우팅 없는 제품도 수량 한도 적용, BOM 없는 제품 → 모든 MAT UNVERIFIED, BOM 자재가 목록에 없으면 `MATERIAL_MISSING`, 안 쓰는 자재 제외, 기준일 당일 미입고는 납기 지남, 가용시간·잔업 한도·수량 한도 누락 처리, `INVALID_QUANTITY`, QTY 표시는 수량 한도가 가장 빠듯한 원인일 때만.
- `mps/`·`rccp/`·`mrp/` README를 구현 상태로 갱신. `engine/planning.py`의 `run()`·`AVAILABLE=False`는 바꾸지 않음.

**검증 결과**
- 2026-11-22 이희원 PC, 루트 `.venv`: `pytest modules/planning_engine` **76 passed / 0 failed**(HC 18 + 세 안 1 + 소수 형식 6 + 경계 16 + 기존 포함).
- 엔진 규칙을 일부러 틀리게 바꾼 10가지(내림→반올림, 배수 순서, 보충 생략, 기준일 당일, QTY 과다표시, 0시간 자원, BOM 누락, 안 쓰는 자재, unverified 무시, 자재 안전재고)는 모두 테스트 실패로 검출. 첫 시도에서 반올림 변형이 통과해 HC-18을 추가했다.
- 규칙서만 보고 별도 작성한 임시 검산 스크립트로 HC-01~18 **18/18 일치**.
- 독립 코드 리뷰(별도 에이전트) 지적 중 HIGH 5건·MEDIUM 7건·LOW 일부를 수정하고 경계 테스트로 고정.
- 루트 전체 pytest: **515 passed / 80 errors**. 오류 80건은 모두 이 PC `.venv`에 백엔드 의존성 `rapidfuzz`가 없어 생긴 수집 오류(이번 변경과 무관, 미해결). Docker·DB·브라우저 미실행.

**기술적 결정**
- 희원 선택: 기존 폴더에 단계별 구조, 코어 입출력은 내부 형식(팀 계약과는 변환부로 연결), 이번 범위는 코어 + HC 자동 비교(변환부는 C01·C02 확정 후). 리뷰 후속 4건도 추천안 선택(BOM 없음 → 모든 MAT UNVERIFIED, 라우팅 없어도 수량 한도 적용, 없는 자재 INPUT_INVALID·안 쓰는 자재 제외, 기준일 당일 미입고 = 납기 지남).
- 잔업 한도 값이 없으면 잔업 0 + 경고(보수적이라 판정은 믿을 수 있어 unverified로 두지 않음).

**남은 문제**
- 이희원: 충파모 9제품×3개월×3안 독립 정답과 엔진 비교, What-if 구현, C01·C02 확정 후 PlanningInput→내부 형식 변환부(BOM 버전 선택 `BOM_VERSION_AMBIGUOUS` 포함)와 PlanningOutput 변환, 그 뒤 `AVAILABLE` 전환.
- 김대영: C01 기간·C02 입고 예정·C03 What-if 키·C06 모순 출력 검사 검토(변경 없음). 이 PC `.venv`의 `rapidfuzz` 누락은 환경 정리 필요(대영 확인).

**관련 자료**
- [계산 규칙 v0.4](../modules/planning_engine/PLANNING_RULES.md), [작은 손계산](../modules/planning_engine/tests/hand_calc/SMALL_CASES.md), [계약 답변](../modules/planning_engine/CONTRACT_REQUESTS.md), [시작 Commit](https://github.com/ChungPaMo/decision-supporter-mvp/commit/c306d7d7daad7a76326faad988a0b3848701fc8f).

### 2026-11-22 — 충파모 9제품×3개월×3안 계산 결과와 독립 정답 비교 (이희원)

**Git**
- 시작 Commit `fbd641967500762c42b1d9193cca13bfafecffc8`.
- 완료 Commit은 고유 제목 `test: compare planning core with independent CHUNGPAMO-2027 answers`으로 조회한다. `git log main -1 --format=%H --fixed-strings --grep='test: compare planning core with independent CHUNGPAMO-2027 answers'`
- 브랜치 `main`.

**작업 목적**
- 손계산 18개를 넘어, 시연에 쓸 공식 합성 데이터 전체에서 계산 코어가 규칙대로 계산하는지 엔진과 독립된 정답으로 확인하고 결과를 고정한다.

**구현 내용**
- `synthetic/plan_input.py`: upload 01~09·입고 예정·예측 결과 → 계산 코어 내부 형식 입력 `tests/chungpamo/plan_input.json`(원본 SHA digest·예측 input digest 기록). 2027-01-01 유효 BOM 1개, 라우팅 resource_requirements(LB1)를 자원 행으로 펼침.
- `tests/chungpamo/expected.json`: 엔진·테스트 코드를 보지 않은 별도 에이전트가 PLANNING_RULES v0.4만 보고 만든 계산기의 정답(그 계산기도 HC-01~18 18/18 일치 후 산출). 세 안 × 판정 102개 전체 포함.
- `tests/test_chungpamo_plan.py`: 엔진 결과와 정답 전 항목 비교(판정 ID 집합도 일치 요구). `synthetic/plan_report.py` → `tests/chungpamo/RESULT.md` 시연용 요약. `synthetic/README.md` 실행 순서 추가.
- `small_cases.json` conventions의 납기 지남 문구를 규칙서(기준일 당일 포함)와 일치시킴(독립 계산기가 불일치 지적).

**검증 결과**
- 2026-11-22 이희원 PC, 루트 `.venv`: `pytest modules/planning_engine` **80 passed / 0 failed**. 정답을 일부러 바꾼 2건(생산량 1개, 판정 1개 누락)은 실패로 검출.
- generate.py 재생성 후 upload 9개·입고 예정 파일 SHA가 이전과 같고, 예측을 다시 돌린 결과도 11/15와 input digest·27행 값 모두 동일함을 확인한 뒤 고정.
- 결과: 기준형 결품 0·**UNVERIFIED**(9개 자재 모두 2·3월 발주 필요), 안정형 결품 3,612·INFEASIBLE, 비용절감형 결품 2,005·INFEASIBLE. 1월 MAT은 1/20 입고 예정 포함 모두 충분.
- backend 테스트(대영 합성 데이터 계약 포함)는 이 PC `.venv`에 `rapidfuzz`가 없어 수집 오류로 미실행. 생성기 코드는 바꾸지 않았다. Docker·DB·브라우저 미실행.

**기술적 결정**
- 희원 선택: 정답은 별도 에이전트가 규칙서만 보고 계산, 입력·정답을 고정 파일로 커밋하고 pytest로 비교(LightGBM·생성 없이 결정적), 예측은 다시 돌려 확인 후 고정.

**남은 문제**
- 시연 관점: 미래 발주가 1/20 한 건뿐이라 기준형도 UNVERIFIED(발주 필요)로 나온다. **희원 결정: 데이터는 그대로 두고 "결품은 없지만 2·3월 발주 권고" 장면으로 쓴다**(공식 데이터·SHA manifest 유지). 화면은 UNVERIFIED 사유(PROCUREMENT_REQUIRED)와 발주 필요량을 보여 주도록 정마나미·김대영과 조율 필요.
- 이희원: What-if, C01·C02 확정 후 PlanningInput 변환부·PlanningOutput 변환, AVAILABLE 전환. 김대영: C01~C06 검토, 이 PC `.venv` rapidfuzz 확인.

**관련 자료**
- [결과 요약](../modules/planning_engine/tests/chungpamo/RESULT.md), [계산 규칙 v0.4](../modules/planning_engine/PLANNING_RULES.md), [합성 데이터 README](../modules/planning_engine/synthetic/README.md), [시작 Commit](https://github.com/ChungPaMo/decision-supporter-mvp/commit/fbd641967500762c42b1d9193cca13bfafecffc8).

### 2026-11-22 — 계획 What-if 재계산 (이희원)

**Git**
- 시작 Commit `d49818f2d9038e31e52f6a95027005a91d97eb2a`.
- 완료 Commit은 고유 제목 `feat: planning what-if recalculation for three plans`으로 조회한다. `git log main -1 --format=%H --fixed-strings --grep='feat: planning what-if recalculation for three plans'`
- 브랜치 `main`.

**작업 목적**
- 과제 7의 What-if(조건을 바꾸면 계획안이 어떻게 달라지는가)를 계산 코어 위에 구현하고 시연 장면을 준비한다.

**구현 내용**
- `modules/planning_engine/what_if/core.py`: C03 요청 키(`demand_multiplier`, `demand_multiplier.<제품>`, `overtime_hours_limit.<자원>.<YYYY-MM>`, `receipt_qty.<발주번호>`)를 적용한 새 입력으로 세 안 재계산, 기준 결과와 함께 반환, 안별 판정·결품·잔업 변화(`deltas`). 원본 입력은 바꾸지 않음.
- `engine/planning_core.py`: 제품별 수요 배수(`demand_multipliers`) 지원.
- `tests/test_what_if.py`: 손계산 기대값 6개 + 충파모 2월 절단기 특근 장면. `synthetic/plan_report.py`·`RESULT.md`: What-if 시연 장면 3개(2월 SAW1 특근, 수요 10% 증가, 1/20 원단 입고 취소)와 1월 발주 필요 자재 열.
- `PLANNING_RULES.md` §8 세부 규칙, `what_if/README.md` 갱신.

**검증 결과**
- 2026-11-22 이희원 PC, 루트 `.venv`: `pytest modules/planning_engine` **86 passed / 0 failed**. What-if 규칙을 일부러 바꾼 4가지(배수 곱하기, 취소 시 행 유지, 원본 수정, 월 검사 생략)는 모두 실패로 검출.
- 시연 결과: 2월 SAW1 특근 80h → 안정형 결품 3,612→1,437(비용절감형 변화 없음), 수요 10% 증가 → 기준형 UNVERIFIED→INFEASIBLE(결품 0→6,063), 1/20 원단 취소 → 결품 변화 없고 1월 MR-N3 발주 필요(기준형 약 4,028kg).
- What-if 결과는 계산 코어(독립 정답으로 검증됨)에 입력 변경만 더한 것이며 What-if 자체의 충파모 독립 정답은 만들지 않았다. backend 테스트는 이 PC `rapidfuzz` 누락으로 미실행. Docker·DB·브라우저 미실행.

**기술적 결정**
- 희원 선택: C03 키 그대로 입력, 제품 배수가 전체 배수보다 우선(곱하지 않음), 잔업 변경은 비용절감형에 적용 안 함(잔업 0 정의 유지), 잘못된 변경은 계산 없이 `INPUT_INVALID`/`WHATIF_INVALID`로 모두 나열.

**남은 문제**
- 김대영: C01 기간·C02 입고 예정·C03 What-if 키 확정 → 이희원이 PlanningInput/PlanCommand overrides → 내부 형식 변환부와 PlanningOutput 변환, `AVAILABLE` 전환. C06 모순 출력 검사.
- 화면: What-if 비교(기준→변경 후 판정·결품·잔업·발주 필요량) 표시 방식 정마나미와 조율.

**관련 자료**
- [결과 요약](../modules/planning_engine/tests/chungpamo/RESULT.md), [계산 규칙 v0.4 §8](../modules/planning_engine/PLANNING_RULES.md), [계약 답변 C03](../modules/planning_engine/CONTRACT_REQUESTS.md), [시작 Commit](https://github.com/ChungPaMo/decision-supporter-mvp/commit/d49818f2d9038e31e52f6a95027005a91d97eb2a).

### 2026-11-22 — 생산계획 v0.4 백엔드 계약 준비 (김대영)

**Git**
- 시작 Commit `5c65cf38986fb1a5804f357bdb52efed33e2d650`. Clean `main`과 최신 `origin/main`을 확인했다.
- 완료 Commit 조회는 `git log main -1 --format=%H --fixed-strings --grep='feat: prepare backend for planning v0.4 integration'`을 사용한다.
- 브랜치 `main`.

**작업 목적**
- 현재 엔진 코어와 기존 승인 조회·진단·저장 경계를 대조하고 C01·C02·C03·C06을 후속 엔진 연동에 필요한 수준으로 반영한다.

**구현 내용**
- `PlanCommand`에 연속 1~12개월을 추가했다. 기존 provider와 CAPA 조회를 확장하고, 진단·Preview·저장의 기간과 출력 범위를 검증한다. 실행 목록·상세·XLSX에 기간을 전달한다.
- 예정 입고 DTO와 승인 공급 검증 경계를 추가했다. 같은 데이터셋의 승인 출처, 부분 입고 잔량, 취소·중복·날짜·단위를 검사한다. 운영 스키마에 승인 원장이 없어 `RECEIPT_SOURCE_UNAVAILABLE`을 표시한다.
- What-if 허용 키와 부모 scope를 갱신했다. 새 계산 응답에는 기준형·안정형·비용절감형 세 후보가 필요하다. C06은 HARD 위반·미확인과 FEASIBLE의 모순을 거절한다. C05 MRP 값의 월별 의미와 비음수 제약을 기록했다.
- OpenAPI·생성 Schema·진단 예시·화면 안내와 함께 상세 인계 및 현재 현황을 갱신했다.

**검증 결과**
- 기존 개발 PC의 전체 비DB pytest 1,102 passed / 0 failed / 66 skipped / 0 deselected. 최초 집중 검사의 진단 예시 불일치 1건은 응답 갱신 후 통과했다. TypeScript·Vite 빌드 통과. 브라우저·실DB 쓰기·파괴적 회귀·migration 미실행.
- 전용 Docker와 `chungpamo` 0009의 강제 읽기 전용 트랜잭션 확인. CP 3개월에 예측 27행·시간예산 18행·수량 한도 3행·승인 출처 9개 조립. CP 6·12개월 및 LEGACY 3개월은 예측 범위 409, 교차 dataset 예측은 404. 데이터/객체 지문 60테이블·735객체와 원본 SHA 전후 일치.
- 변경 후보 보안 발견 0건. 전체 트리에 표시된 기존 분류기 Excel 200건과 합성 전화번호 생성 코드 1건은 시작 커밋의 파일과 대조했다.

**기술적 결정**
- 일반 요청 기본 기간은 3개월이며 기존 `/plans`의 생략 호출은 1개월로 유지한다. 이전 행은 1개월을 복원하고 원본 JSON의 지문을 비교한다. 기간은 기존 JSONB를 사용한다.
- 승인 입고 공급 미연결 `null`과 검증된 빈 목록을 구분한다. 공식 합성 입고 CSV는 실제 승인 공급으로 사용하지 않는다. 정책 참조와 서버 승인 권한은 별도이며 공개 승인 501을 유지한다.

**남은 문제**
- 이희원은 팀 `run` 변환과 월별 버전/기간 검증, 정마나미는 기간·오류·What-if·저장 이력 화면 연계를 맡는다.
- 승인 입고 원장과 실제 저장·재조회 시험에는 별도 데이터 계약과 DB 적용 또는 격리 DB 검증 승인이 필요하다.

**관련 자료**
- [v0.4 인계·실DB 검증](PLANNING_CONTRACT_V04_HANDOFF.md), [공통 계약](INTEGRATION_CONTRACT.md), [계획 저장 계약](PLAN_EXECUTION_PERSISTENCE.md), [현재 현황](PROJECT_PROGRESS.md), [희원 요청](../modules/planning_engine/CONTRACT_REQUESTS.md).

### 2026-11-22 — 생산계획 저장·조회 통합 사전검증 (김대영)

**Git**
- 시작 Commit `5552b56dfce38a63f1fff1a45d6e76a0735772b7`. 시작 `main`과 원격이 일치했고 작업 트리가 깨끗했다.
- 완료 Commit은 `git log main -1 --format=%H --fixed-strings --grep='fix: harden planning execution preflight and validation'`으로 확인한다.
- 브랜치 `main`.

**작업 목적**
- 실계산 모듈 연결에 앞서 계획 저장·조회·What-if의 입력 지문, 중복 실행, 실패·롤백 경계를 보강한다.

**구현 내용**
- 공통 계획 HTTP 입구에서 제품 ID 순서를 정규화해 제품 선택 순서가 달라도 동일한 입력 지문을 사용한다.
- Preview와 신규 저장은 누락된 승인 입력을 FEASIBLE로 표시하는 결과를 거절한다. 적용하지 못한 HARD 검사와 모순되는 결과 및 수정된 typed 결과도 거절한다. 손상된 부모·재사용 이력은 `PERSISTENCE_ERROR`로 반환한다.
- 같은 트랜잭션의 advisory lock과 재사용 조회를 저장소 메서드로 묶었다. `verify_plan_storage.py`는 전용 회귀 DB 식별·sentinel·빈 테스트 데이터 검사를 통과할 때만 외부 롤백 트랜잭션을 실행한다.
- 화면 담당자용 API 경로, 요청·응답 JSON, 422/500 결과 봉투와 상태 코드 처리 사례를 인계 문서에 추가했다.

**검증 결과**
- 2026-11-22 기존 개발 PC에서 전체 비DB pytest 1,109 passed / 0 failed / 66 skipped / 0 deselected. Schema/OpenAPI·예시 회귀, TypeScript·Vite 빌드 통과. 변경 파일의 보안 발견 0건이며 전체 트리의 분류기 샘플 관련 기존 발견 201건은 유지된다.
- 개발 DB 0009 강제 READ ONLY에서 3개월 27행 진단, 동일 입력 지문, 501 계산 게이트·422 잘못된 override·404 격리를 확인했다. 테이블 60개와 객체 735개가 사전 지문과 일치했다.
- `chungpamo_regression` 0009에서 TEST_DOUBLE 12개월 저장·재조회, 계보/FK, 중복 재사용·고유 제약, 두 연결 잠금 경합·해제, 저장 실패 롤백을 확인했다. 비교 테이블 30개가 전후 동일했다. 초기 조회/대역 오류의 수정과 최종 결과는 인계 문서에 기록했다.

**기술적 결정**
- 기존 이력의 원본 지문과 계산 상태를 보존한다. 적용하지 못한 HARD 검사나 모순된 계산 상태는 거절하되 새 승인 입력 커버리지 검사는 새 계산과 새 저장에 적용한다.
- 격리 시험에서는 계획 결과를 TEST_DOUBLE로 구분했고 개발 DB는 읽기 전용으로 연결했다. 기존 스키마·DB 초기화 없이 외부 트랜잭션을 롤백했다.

**남은 문제**
- 희원 `run` 변환 및 실계산 결과 검증, 나미 UI 연결, 실제 성공 요청 두 건의 PostgreSQL 201/200 경쟁 시험, 정식 승인과 승인 입고 공급은 후속이다. 초기화가 필요한 전체 PostgreSQL pytest는 미실행이다.

**관련 자료**
- [사전검증과 화면 API 인계](PLANNING_CONTRACT_V04_HANDOFF.md#2026-11-22-백엔드-통합-사전검증과-화면-연동), [격리 SQL 검사](../scripts/verify_plan_storage.py), [현재 현황](PROJECT_PROGRESS.md).

### 2026-11-22 — 로컬 BGE-M3 후보 비교와 컬럼 추천 보강 (김대영)

**Git**
- 시작 Commit `6e7056aeb09166b2bc82d994faaae47f5af15db9`. `main`과 원격이 일치했고 작업 트리가 깨끗했다.
- 완료 Commit은 `git log main -1 --format=%H --fixed-strings --grep='eval: compare local BGE-M3 and harden mapping suggestions'`으로 확인한다.
- 브랜치 `main`.

**작업 목적**
- 동일 합성 평가셋에서 의미 후보의 정확도·오추천·응답 비용을 측정하고 운영 추천에 적용할지 결정한다.

**구현 내용**
- `scripts/evaluate_mapping_bge.py`로 고정 합성 48건에서 RapidFuzz/BGE-M3 dense/순서를 보존한 BGE 보완을 비교했다. 공식 로컬 모델과 동일 별칭·검증 경계를 사용했다.
- 업무 의미 반증을 보강했다. 한자 금액, 재고 평가액, 출고 수량과 기준/가용 혼용 열에 부적절한 수량 후보를 억제한다. API 필드와 운영 의존성은 기존 계약을 유지한다.
- 이름을 바꾼 합성 수량 열을 사용자가 직접 확인한 뒤 변환 미리보기와 승인 전 저장을 거치는 회귀 테스트를 추가했다.

**검증 결과**
- 새 48건에서 RapidFuzz Top-1 25/32, Top-3 26/32, 오추천 3/48, 후보 HOLD 20/48. BGE 보완 31/32, 32/32, 7/48, 10/48. 지연 중앙값은 0.15ms와 45.63ms, RSS는 55.6MiB와 1,512.1MiB였다. 시작 커밋 RapidFuzz의 오추천도 같은 실행 환경에서 다시 측정해 6/48을 확인했다.
- 전체 비DB pytest 1,114 passed / 0 failed / 66 skipped / 0 deselected. TypeScript·Vite 빌드 및 계약 동기화 통과. 변경 파일 보안 발견 0건. 전체 트리의 기존 분류기 샘플 관련 발견 201건은 별도로 기록했다.
- 개발 DB는 읽기 전용 추천과 자료 보존을 검증했다. 격리 DB에서 실제 SQL `READY_FOR_APPROVAL` 및 공개 수요 0행을 확인하고 전체 롤백했다. 개발 60테이블·735객체와 격리 비교 34테이블은 전후 일치했다. 파괴적 DB pytest는 미실행이다.

**기술적 결정**
- BGE는 후보 정답 6건을 더 찾았지만 정답이 없는 열의 후보와 잘못된 첫 후보가 증가했다. 모델을 운영 API에 연결하지 않고 RapidFuzz와 사용자 확인을 유지한다.
- 평가 모델 파일·라이브러리·상세 산출물은 로컬 Git 제외 경로에만 두었다. 기존 승인과 변환 계약을 재사용했다.

**남은 문제**
- 외부 검토로 고정한 별도 평가셋에서 업무 의미 반증·정답 없는 열 처리와 지연을 다시 확인해야 의미 후보를 운영에 연결할 수 있다. 모호한 이름은 현재 사용자 확인을 요구한다.

**관련 자료**
- [2026-11-22 새 평가와 검증](MAPPING_BGE_EVALUATION_20261122.md), [이전 RapidFuzz 평가](MAPPING_RECOMMENDATION_MVP_20261116.md), [통합 설계](AI_MAPPING_INTEGRATION_DESIGN.md).

### 2026-11-23 — 현실형 XLSX 검증과 분류 등록 경로 계약

**Git**
- 시작 Commit `b2b3ecd7941b2e6b3cc706d95614d09a584f0115`.
- 완료 Commit은 `git log main -1 --format=%H --fixed-strings --grep='feat: expose structured file classification routes and audit xlsx mapping'`으로 확인한다.
- 브랜치 `main`.

**작업 목적**
- 실제 합성 XLSX 레이아웃의 업로드 제약과 추천 오류를 확인하고, CAPA·Routing 등록 경로와 HOLD 사유를 API 계약에 반영한다.

**구현 내용**
- `backend/app/integrations/modules.py`와 `contracts/interfaces/modules.py`에 `hold_kind`와 `registration_hint`를 연결했다. 정확한 양식 확인에 기존 CAPA/Routing 등록 DTO를 재사용했다.
- `backend/app/ingest/recommendation.py`에서 숫자만 있는 열에 단위 후보를 차단했다. API 회귀, Schema·OpenAPI 및 화면 가이드를 갱신했다.
- `scripts/evaluate_classifier_xlsx.py`와 검증 보고서로 200개 시트 구조 및 원본과 표 추출본의 매핑 차이를 재현할 수 있게 했다.

**검증 결과**
- 문서 분류 200/200과 업로드 분류 HOLD/UNKNOWN 200개를 별도로 기록했다. 실제 첫 표 헤더 포착 18/200. 평면 BOM 9개의 원본 Top-1/Top-3 0/27, 표만 복사한 입력 9/27. 모두 파일 HOLD. 잘못된 단위 하위 후보 9건 제거.
- 최종 비DB **1,115 passed / 0 failed / 66 skipped / 6 deselected**. OpenAPI·Schema 동기화 통과. 보안 검사 변경 파일 0건, 기존 합성 샘플 관련 201건. 실DB·Alembic·외부 모델 실행은 없었다.

**기술적 결정**
- 다섯 `recommended_entity`는 유지한다. CAPA·Routing은 사용자가 별도 검증 경로로 이동하도록 안내한다. 추천·등록·승인 단계는 각각 유지한다.
- 파서 레이아웃 문제와 랭킹 문제를 각각 측정한다. 기존 BGE-M3 결과를 참고하고 RapidFuzz 운영 경로를 유지한다.

**남은 문제**
- 이훤의 모듈에서 구조화 HOLD를 직접 제공하고 나미님 화면에서 상태·등록 경로를 연결한다. 사용자 확인 기반 헤더 영역·반복 블록 처리와 누락 필수 필드의 데이터 계약은 후속이다.

**관련 자료**
- [시작 Commit b2b3ecd](https://github.com/ChungPaMo/decision-supporter-mvp/commit/b2b3ecd7941b2e6b3cc706d95614d09a584f0115), [XLSX 검증·계약 인계](CLASSIFIER_XLSX_MAPPING_VERIFICATION_20261123.md), [11/22 BGE-M3 비교](MAPPING_BGE_EVALUATION_20261122.md).

### 2026-11-23 — 사용자 지정 엑셀 헤더·표 범위

**Git**
- 시작 Commit `50028536a4af176306704be574409b142f10eaaf`.
- 완료 Commit은 `git log main -1 --format=%H --fixed-strings --grep='feat: analyze user-selected xlsx table ranges'`로 확인한다.
- 브랜치 `main`.

**작업 목적**
- 원본 Excel의 제목·결재란·주석 대신 사용자가 확인한 표를 분석하고 시트·셀 좌표와 SHA를 유지한다.

**구현 내용**
- `backend/app/ingest/xlsx_layout.py`, `contracts/interfaces/xlsx.py`에 시트·구조 창과 범위 검증을 구현했다. `POST /ingest/xlsx-layout`과 분류·프로파일·추천·변환 미리보기의 선택 필드를 추가했다.
- 변환 입력 지문과 원본 열 번호에 선택을 반영했다. OpenAPI·Schema, API 회귀, 200개 원본 재현 스크립트와 화면 인계를 갱신했다.

**검증 결과**
- 실제 첫 헤더 확인은 기본 18/200, 정답 좌표를 공급한 선택형 API 200/200이다. 평면 BOM Top-1/Top-3는 각각 0/27에서 9/27이며 9개 파일이 계속 HOLD다. 원본 SHA와 절대 좌표를 확인했다.
- 비DB **1,128 passed / 0 failed / 66 skipped / 6 deselected**. 기존 48건 회귀·OpenAPI·Schema 통과. 변경 파일 보안 발견 0건, 기존 합성 샘플 관련 201건. Docker·실DB·Alembic·모델 재실행은 미실행이다.

**기술적 결정**
- 사용자 좌표를 원본 SHA에 묶고 파일당 한 개 표를 분석한다. 병합이 걸친 범위, 중복 헤더, 숨긴 시트는 오류로 돌려주고 수식은 캐시 값만 읽는다. 기존 기본 파싱과 배치 승인 경로를 유지한다.

**남은 문제**
- 나미님의 시트·좌표 선택 UI 연동이 필요하다. 선택 범위의 영구 저장, 반복 블록 결합 및 누락된 BOM 필드 보완은 후속이다.

**관련 자료**
- [기준 Commit 5002853](https://github.com/ChungPaMo/decision-supporter-mvp/commit/50028536a4af176306704be574409b142f10eaaf), [선택 검증](XLSX_TABLE_SELECTION_VERIFICATION_20261123.md), [화면 계약](XLSX_TABLE_SELECTION_HANDOFF.md).

### 2026-11-23 — XLSX 선택 범위의 변환 이력 저장과 승인 연동

**Git**
- 시작 Commit `423c456cf11d090866293c0812c78d6cd7bb81e2`.
- 완료 Commit은 `git log main -1 --format=%H --fixed-strings --grep='feat: persist selected xlsx transformation evidence'`로 확인한다.
- 브랜치 `main`.

**작업 목적**
- 검토한 범위를 기존 변환 이력과 승인 배치에 연결하고 원본·정책·좌표를 재현한다.

**구현 내용**
- `ingest_assistance.py`/`ingest_history.py`에 단일 `table_selection`과 인덱스별 `table_selections` 공통 검증을 연결했다. `transformation.py`/`history.py`에서 역할별 절대 열과 선택, 원본 바이트·정규 CSV를 기존 manifest와 재생 경로에 연결했다.
- XLSX TestClient·메모리 회귀, 미래 SQL 회귀 1개, OpenAPI/Schema와 화면·Docker PC 체크리스트를 추가했다.

**검증 결과**
- 전체 비DB **1,164 passed / 0 failed / 67 skipped**. 저장→재조회→재검증→승인, 200 재시도, 다른 시트/범위, 불량 입력, 격리, 변조 감지, 롤백과 기존 이력 보존을 대역에서 검증했다. 200개 헤더/평면 BOM 비교, RapidFuzz 48건 회귀, OpenAPI/Schema 통과.
- 보조 PC의 실제 PostgreSQL과 마이그레이션 적용은 미실행이다. 기존 0009를 위한 새 SQL 시험은 `--no-db`에서 제외됐다.

**기술적 결정**
- 선택 정보는 기존 불변 JSONB manifest에 저장한다. 별도 시스템이나 migration을 추가하지 않는다. 같은 정규 CSV의 중복과 업무 수요 키의 승인 충돌은 기존 정책을 적용한다.

**남은 문제**
- 기존 개발 PC의 실제 SQL 제약·동시성 검증 및 나미님 화면 연계가 남았다. 이 연동은 기존 합성 판매 정책의 월수요 변환에 적용된다.

**관련 자료**
- [검증 및 PostgreSQL 체크리스트](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md), [프론트엔드 인계](XLSX_SELECTION_PERSISTENCE_HANDOFF.md), [기존 이력 계약](INGESTION_INTEGRATION_HISTORY.md).
