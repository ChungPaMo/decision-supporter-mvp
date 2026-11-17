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
