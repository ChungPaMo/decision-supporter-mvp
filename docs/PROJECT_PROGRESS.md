# 충파모 프로젝트 진행상황

최종 확인 **2026-11-23 (KST), 기존 개발 PC**. 기준 `main`은 [`c136793`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/c136793c8b974f8b9cd321bbbd9df98b99ba3597)이다. 김대영이 PostgreSQL 두 연결로 XLSX 동일 선택 `201`/`200` 재사용, 범위별 입력 지문, 변조 거부, 고유 제약과 롤백을 확인했다. 서로 다른 범위가 같은 정규 CSV로 경합할 때 PostgreSQL은 중복을 막았으나 API가 `409 DUPLICATE_UPLOAD` 대신 `500 PERSISTENCE_ERROR`를 반환했다. 이번 pytest는 **0 passed / 1 failed / 0 skipped / 0 deselected**였다. 회귀 DB 정리 후 업무 데이터 0행, 개발 DB의 60개 테이블·735개 객체·660개 정의 지문 일치를 확인했다. 백엔드의 중복 오류 매핑 수정과 별도 승인 후 재검증, 브라우저 E2E가 남아 있다. [동시성 검증](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md#2026-11-23-postgresql-동시성무결성-검증)

직전 기존 개발 PC의 기준 `main`은 [`5507c0a`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/5507c0ab98d95db0a6780b56fff7c8a1f327283f)이다. 김대영이 별도 회귀 DB에서 Alembic `0009`와 XLSX 선택 이력 SQL 테스트 **3 passed / 0 failed / 0 skipped / 0 deselected**를 확인했다. 실제 FastAPI·SQL에서 신규 저장 `201`, 재시도 `200`, 재조회 `200`, 선택 좌표·원본 SHA·지문 보존, 명시적 승인 전후 월수요 0→1행과 오류 시 롤백을 검증했다. 개발 DB의 60개 테이블·735개 객체 지문 및 기존 승인·예측 건수는 일치했다. 완료 커밋 제목은 `test: verify selected xlsx history on PostgreSQL`이다. [실DB 검증 결과](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md#2026-11-23-기존-개발-pc의-postgresql-검증-결과) · [나미님 인계](XLSX_SELECTION_PERSISTENCE_HANDOFF.md)

직전 보조 PC의 시작 `main`은 [`423c456`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/423c456cf11d090866293c0812c78d6cd7bb81e2)이다. 사용자 선택 XLSX를 기존 변환 이력과 승인 전 배치에 저장하고 같은 원본·정책·선택을 재현하도록 구현했다. TestClient·메모리에서 201 저장/200 재시도, 상세 조회, 재검증·명시적 승인, 데이터셋 격리와 중간 오류 롤백을 확인했다. 새 마이그레이션은 없다. 당시 전체 비DB **1,164 passed / 0 failed / 67 skipped**. [보조 PC 검증 결과](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md#보조-pc에서-확인한-동작)

직전 11/23 범위 선택 작업에서 원본 SHA에 연결된 시트·헤더·데이터 범위를 구조 미리보기·분류·추천·프로파일·변환 미리보기에 적용했다. 기본 헤더 포착 18/200, 지정 헤더 200/200, 평면 BOM Top-3 0/27→9/27 및 전체 HOLD를 확인했다. 당시 비DB **1,128 passed / 0 failed / 66 skipped / 6 deselected**. 이번 저장 연동에서 200개 구조와 평면 BOM의 기존 결과를 재현했다. [범위 선택 검증](XLSX_TABLE_SELECTION_VERIFICATION_20261123.md)

직전 11/23 분류 계약 작업의 시작 `main`은 [`b2b3ecd`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/b2b3ecd7941b2e6b3cc706d95614d09a584f0115)이며 완료는 [`5002853`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/50028536a4af176306704be574409b142f10eaaf)이다.

현실형 합성 XLSX 200개를 읽어 실제 첫 표 헤더를 포착한 18개, 제목·병합·숨김·수식 동작을 확인했다. 문서 종류 분류 라벨은 200개 모두 일치했다. 평면 BOM 9개의 원본 매핑은 모두 HOLD였다. 표만 복사했을 때 27열 중 9열을 찾았고 숫자 열의 잘못된 단위 하위 후보 9건을 차단했다. 기존 승인 게이트 앞에 구조화 HOLD와 CAPA·Routing 등록 안내를 추가했다. [XLSX 검증과 인계](CLASSIFIER_XLSX_MAPPING_VERIFICATION_20261123.md)

11/23 전체 비DB pytest **1,115 passed / 0 failed / 66 skipped / 6 deselected**. OpenAPI/Schema 동기화와 승인 게이트 시험 통과. 보안 검사에서 이번 변경 파일 발견 0건, 기존 분류기 합성 샘플 관련 발견 201건이다.

11/22 기존 개발 PC의 컬럼 추천 비교 시작 `main`은 [`6e7056a`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/6e7056aeb09166b2bc82d994faaae47f5af15db9)이다. 완료 커밋은 `eval: compare local BGE-M3 and harden mapping suggestions`로 식별한다.

같은 합성 헤더 48건에서 로컬 BGE-M3를 새로 실행했다. RapidFuzz 보완 방식의 Top-3는 26/32→32/32, 오추천은 3/48→7/48이었다. 운영 API는 RapidFuzz를 유지하며 금액·출고·기준/가용 혼용의 수량 오추천을 차단한다. 전체 비DB pytest **1,114 passed / 0 failed / 66 skipped / 0 deselected**. 격리 PostgreSQL 승인 전 저장은 실제 SQL로 확인하고 롤백했다. 개발 DB는 강제 읽기 전용으로 보존했다. [새 비교와 검증](MAPPING_BGE_EVALUATION_20261122.md)

직전 통합 사전검증 시작 `main`은 [`5552b56`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/5552b56dfce38a63f1fff1a45d6e76a0735772b7)이며 완료 커밋은 [`6e7056a`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/6e7056aeb09166b2bc82d994faaae47f5af15db9)이다.

제품 선택 순서에 따른 중복 실행을 방지하고, Preview와 신규 저장에 승인 입력 커버리지와 HARD 적용 상태 검증을 공통 적용했다. 실제 격리 PostgreSQL에서 TEST_DOUBLE 12개월 저장·재조회·계보·고유 제약·잠금·실패 롤백을 확인했다. 개발 DB는 읽기 전용으로 조회해 3개월 진단과 게이트를 확인하고 60개 테이블·735개 객체 지문을 보존했다. 전체 비DB pytest **1,109 passed / 0 failed / 66 skipped / 0 deselected**. `AVAILABLE=False`이며 실제 계획 엔진 영구 실행과 화면 연동은 후속이다. [사전검증·화면 API 인계](PLANNING_CONTRACT_V04_HANDOFF.md#2026-11-22-백엔드-통합-사전검증과-화면-연동)

직전 v0.4 계약 작업의 시작 `main`은 [`5c65cf3`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/5c65cf38986fb1a5804f357bdb52efed33e2d650)이며 완료 커밋은 [`5552b56`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/5552b56dfce38a63f1fff1a45d6e76a0735772b7)이다.

김대영이 C01 기간 1~12개월, C03 What-if 검증, C06 모순 판정 차단을 공통 계약과 기존 백엔드에 반영했다. C02는 승인 입고 DTO와 공급 검증 경계까지 구현했다. 개발 DB 0009에는 승인 입고 원장이 없어 실제 진단은 `RECEIPT_SOURCE_UNAVAILABLE`을 표시한다. 공식 데이터 3개월 스냅샷의 예측 27행·시간예산 18행·수량한도 3행을 실제 SQL로 검증했다. 비DB 전체 **1,102 passed / 0 failed / 66 skipped / 0 deselected**, TypeScript·Vite 빌드 통과. 개발 DB 전후 지문과 원본 SHA 일치. 계획 엔진의 팀 계약 변환부와 정식 승인 게이트 후속은 [v0.4 인계](PLANNING_CONTRACT_V04_HANDOFF.md)에 정리했다.

직전 이희원 작업 기록 **2026-11-22 (KST)**. 작업 시작 `main`은 [`d49818f`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/d49818f2d9038e31e52f6a95027005a91d97eb2a)다. 해당 변경은 `feat: planning what-if recalculation for three plans` Commit과 [누적 이력](DEVELOPMENT_CHANGELOG.md)으로 식별한다.

이번에는 이희원이 **What-if 재계산**(`what_if/core.py`: 수요 배수 전체·제품별, 자원·월 잔업 한도, 입고 예정 수량·취소 → 세 안 모두 재계산, 기준 결과와 비교)을 구현하고 충파모 시연 장면 3개를 [결과 요약](../modules/planning_engine/tests/chungpamo/RESULT.md)에 추가했다(예: 2월 절단기 특근 80h → 안정형 결품 3,612→1,437). 계산 코어·충파모 독립 정답 일치는 같은 날 `fbd6419`·`d49818f`. **팀 계약 `engine.planning.run`은 여전히 `AVAILABLE=False`**(C01~C03 확정 후 변환부 연결). 아래 11/18 이전 기록은 해당 시점 결과다.

2026-11-18 기준 김대영 작업: 시작 `main` [`231bcb2`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/231bcb262c98e764349fc54e5c3c6706e083f46f), `feat: diagnose approved planning inputs without running the engine`.

최종 확인 **2026-11-18 (KST), 보조 개발 PC**. 작업 시작 `main`은 [`231bcb2`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/231bcb262c98e764349fc54e5c3c6706e083f46f)다. 이번 변경은 `feat: diagnose approved planning inputs without running the engine` Commit과 [누적 이력의 마지막 항목](DEVELOPMENT_CHANGELOG.md)으로 식별한다.

이번 B01~B03에서 단일 월 `POST /planning-inputs/preview`, 공통 참조·출처·단위·기간 검증과 계약 협의 명세를 추가했다. **비DB pytest 978 passed / 0 failed / 66 skipped / 6 deselected**. 저장 경계는 대역이며 새 진단 경로의 실제 SQL 검증은 기존 개발 PC의 후속이다. [진단 검증·화면 인계](PLANNING_INPUT_DIAGNOSTICS_VERIFICATION.md)

11/17 기존 개발 PC에서 **집중 비DB pytest 71 passed**, 공식 3개 월 각각의 PlanningInput 실제 SQL 읽기 조립·미구현501을 확인했다. 개발 DB0009·60테이블/스키마 객체735개·승인7+9배치·예측각1건의 전후 보존도 확인했다. 이 기록은 신규 진단 API 구현 전의 결과다. [계획 통합 준비 보고서](PLANNING_ENGINE_INTEGRATION_READINESS.md)

11/17 실제 PostgreSQL 검증(`77067f1`)은 **전체 pytest 1015 passed / 0 failed / 0 skipped / 2 deselected**였다. 공식 원본→변환 이력·승인→예측의 실제 SQL 흐름을 확인했다. 별도 승인 후 개발 DB **0008→0009 적용 완료**. 기존55개 데이터 테이블·승인7+9배치·예측각1·기존객체/볼륨을 보존했고 새 이력4테이블은 빈 상태다. 이후 강제 읽기 전용 GET24건/60테이블 보존을 확인했다. [당시 상세](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md)

이 문서는 **최신 상태**, [DEVELOPMENT_CHANGELOG](DEVELOPMENT_CHANGELOG.md)는 **시간순 변경 이유·결과**, 개별 검증 보고서는 **상세 근거**, [AGENTS](../AGENTS.md)는 **매 작업의 읽기·갱신 규칙**이다. 이전 보고서의 “이번 작업”은 그 보고서 작성 당시를 뜻한다.

## 프로젝트 개요

가상 휴지 제조기업 충파모의 데이터 입력·검증·수요예측·생산계획 의사결정을 지원하는 MVP다. 추천과 사용자 최종 판단을 구분하며 자동 승인하지 않는다.

- 저장소: [ChungPaMo/decision-supporter-mvp](https://github.com/ChungPaMo/decision-supporter-mvp), `main` 직접 개발.
- 기술: Python 3.11+ / FastAPI / Pydantic / SQLAlchemy / Alembic / PostgreSQL 16, CSV·XLSX 파서(openpyxl), RapidFuzz. 예측은 단일 `engine/forecast` 구현(LightGBM), 화면은 React·TypeScript·Vite·Zustand. 검증은 pytest·TestClient·Playwright.
- 구조: `frontend/` → `backend/` API·검증·승인·저장 → `modules/` 분류/예측/계획 어댑터. `contracts/`가 공통 DTO·Schema·OpenAPI, `infrastructure/`가 DB 구성이다.
- 흐름: 파일 선택 → 분류/매핑 추천·사용자 확인 → 정제/변환 미리보기 → 승인 전 배치 → 명시적 검증·승인 → 승인 자료 기반 예측 → 계획 계산/검토(아직 엔진 연결 필요).

| 담당 | 책임·경로 |
| --- | --- |
| 김대영 | `backend/`, `contracts/`, `infrastructure/`, `tests/e2e/`, `scripts/`, `.github/`, 공통 문서·설정, API/DB/통합 |
| 이훤 | `modules/file_classifier/` — 업로드 규칙 분류 및 별도 문서 분류 연구 |
| 이희원 | `modules/planning_engine/` — 단일 예측 구현, 공식 합성 데이터, MPS/RCCP/MRP/What-if |
| 정마나미 | `frontend/` — 화면·상호작용·API 클라이언트·표시 타입 |

상세 경계는 [OWNERSHIP](OWNERSHIP.md), 입출력은 [INTEGRATION_CONTRACT](INTEGRATION_CONTRACT.md)를 따른다. 담당자 배정과 기능 완료는 별개다.

## 최신 개발 현황

| 기능 | 실제 구현·검증 수준 | 담당 | 남은 문제·근거 |
| --- | --- | --- | --- |
| 데이터 입력·파싱 | CSV/XLSX·7종 배치·수동 매핑·재검증·승인/반려 유지. 공식8마스터+원장 변환9번째 배치와 선택 XLSX 변환 이력을 실제 PostgreSQL로 검증 | 김대영 | 동시 저장 및 화면 전체 E2E는 별도. [공식 자료 검증](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) · [선택 XLSX 실DB 검증](XLSX_SELECTION_PERSISTENCE_VERIFICATION.md#2026-11-23-기존-개발-pc의-postgresql-검증-결과) |
| 파일 자동 분류 | 업로드용 `rules-0.4.0`이 구조화 HOLD를 제공하고 백엔드는 CAPA·Routing 등록 힌트를 반환한다. 사용자 선택 범위로 재분류 가능 | 이훤(알고리즘), 김대영(API) | 화면 안내와 범위 선택 연계는 후속. [모듈 갱신](https://github.com/ChungPaMo/decision-supporter-mvp/commit/66880a5) · [표 선택](XLSX_TABLE_SELECTION_HANDOFF.md) |
| 컬럼 매핑·AI 후보 추천 | 정확 일치·별칭·수동 override와 RapidFuzz Top-3 유지. 11/22 48건의 오추천 6→3, Top-3 26/32 및 승인 전 SQL 저장 검증. 11/23 숫자 열의 단위 후보 반증 추가 | 김대영 | 11/22 BGE-M3 보완은 Top-3 32/32이나 오추천 7/48로 운영 적용 보류. 평면 BOM 원본의 헤더 위치와 식별자 부족은 수동 확인 필요. [기존 평가](MAPPING_BGE_EVALUATION_20261122.md) · [현실형 XLSX](CLASSIFIER_XLSX_MAPPING_VERIFICATION_20261123.md) |
| 정제·변환 | 원본5파일86,214→498, SQL 이력·원본bytes/SHA·승인 전 batch 연결·재조회·동시201/200·실제DB 실패 rollback 검증 완료 | 김대영 | 회귀/개발DB0009 적용 확인. 개발DB는 기존공식자료 중복등록 없이 새이력0건 유지. SYNTHETIC_ONLY를 일반 기업에 자동 적용하지 않음. [이력 계약](INGESTION_INTEGRATION_HISTORY.md), [실DB 근거](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |
| PostgreSQL·데이터셋 격리 | 신규v2의 로컬FK·UUID격리·불변/지연트리거 실제 검증. 보관dataset 포함3스키마·기존81테이블 보존 probe 후 rollback. 개발0009도 별도승인·백업확인 후 적용 | 김대영 | 개발/회귀 현재0009. 기존자료와 연결된 볼륨은 보존, downgrade2개 미실행. dataset_id는 인증권한 아님. [최신 근거](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |
| 수요예측 | 단일 엔진/계약 유지. 실제 승인된 변환 수요498행→예측OK/27행 저장·재조회·P50≤P80≤P90, 미승인 probe 제외 확인 | 이희원(엔진), 김대영(API), 정마나미(화면) | 합성 회귀 결과를 실제 기업 적합성으로 일반화하지 않음. [이번 실DB 검증](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |
| 계획 입력 진단 | 승인 input을 한 트랜잭션에서 1~12개월 조립. CP 1·3개월과 LEGACY 1개월 실제 SQL 읽기 확인, 예측 범위 부족 409. 예정 입고 공급 미연결 표시 | 김대영(API), 정마나미(화면 연계) | 6·12개월 실제 조립에는 그 기간을 포함한 저장 예측이 필요. 화면에서 기간·진단·오류 표시 연계. [v0.4 인계](PLANNING_CONTRACT_V04_HANDOFF.md) |
| 생산계획·제약 계산 | 공식 승인자료→단일 월 DTO 실제 조립 확인. **`engine.planning.AVAILABLE=False`/NotImplementedError(팀 계약 연결 전)**. 11/22 계산 코어(MPS/RCCP/MRP·판정·세 안, 내부 형식 입력) 구현·HC-01~18 자동 비교 통과, 충파모 9제품×3개월×3안 독립 정답과 일치(고정 입력 테스트), What-if 재계산 구현(11/22), 팀 계약 변환부 미구현, API501·실제 계획0건. 계산 규칙 v0.4(11/22: 월별 MRP로 자재 음수 제거, 예측 누락 INPUT_INVALID, 재고 누락·미지원 기능 처리, What-if 3종·세 안 재계산, 판정/승인 분리)와 HC-01~18 손계산(독립 검산 18/18). 모듈 시험은 구조/경계 검사 | 이희원(계산), 김대영(계약·저장) | 희원 측 결정은 [계약 답변](../modules/planning_engine/CONTRACT_REQUESTS.md)에 기록. C01 기간·C02 입고 예정·C03 What-if 키·C06 모순 출력 검사는 김대영 검토 필요. 이력7테이블·어댑터·검토/출력 기반은 재구현 불필요. 정식 APPROVE501 유지. [상세·담당 작업](PLANNING_ENGINE_INTEGRATION_READINESS.md), [저장 기반](PLAN_EXECUTION_PERSISTENCE.md) |
| 프론트엔드 | 데이터셋 선택·배치 등록/검토/재검증/승인·분류 패널·예측 조회 및 별도 DEMO 화면 구현. **2026-11-23:** 화면 요청 P0·P1 연결 — 원본 파일 공유와 명시적 "이 파일 등록", 등록 전 컬럼 분석·Top-3 후보·열 선택, 판매 원장 변환 정책/미리보기/이력 저장·배치 연결, 변환 이력 목록·상세, CAPA·Routing 7종 등록. `/ingest/*` dataset scope 적용. type-check/build 통과, 보조 PC 로컬 PostgreSQL(0009)에서 공식 자료로 브라우저 확인 | 정마나미 | **2026-11-23 추가:** XLSX 시트·표 범위 선택 UI(`/ingest/xlsx-layout`, `table_selection`/`table_selections`)와 `hold_kind`·`registration_hint` 안내 연결. 대시보드를 "지금 처리할 일" 목록 중심으로 재구성하고 예측·등록·계획 화면의 표시를 정리(표시만 변경, API 계약 변경 없음). 미연결: 계획 v0.4 화면. **`tests/e2e/browser`는 미실행이며 갱신 필요**(등록이 파일 선택 즉시가 아니라 "이 파일 등록" 클릭으로 바뀜, 데이터 종류 7단계). 기존 npm 취약점 2건 미검토. [API 인계](INGESTION_UI_API_HANDOFF.md), [화면 변경 요청](INGESTION_UI_CHANGE_REQUEST.md) |
| 전체 E2E | 공식14파일 SHA와 입력·저장·승인·예측 **TestClient+실제PostgreSQL** 경로 검증 완료. 메모리/SQL 대역으로 저장 성공을 대체하지 않음 | 김대영(통합), 각 담당 | 신규입력 전체브라우저·실제계획계산을 포함한 제조전체E2E는 미완료. [이번 범위](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |

## 현재까지의 핵심 성과

- 대표 자료는 이희원 담당 **CHUNGPAMO-2027 공식 합성 생성기(SEED=20261115)**의 기존 원본·정답이다. [원본/정답 14파일 SHA manifest](../contracts/examples/ingestion_e2e_source_manifest.json)를 대조하고 검증 전후 보존했다. 임의 성공 fixture로 대체하지 않았다.
- 제품·자재·BOM·재고·자원·CAPA·Routing의 실제 DTO 연결과 공유 설비/동시 인시 요구를 확인했다. 판매 거래 **86,214행 → 월별 수요 498행**이 독립 정답의 제품/월/Decimal 수량/단위와 일치했다. 정상 수요만 집계하고 취소 제외·반품 별도를 유지했다.
- 파일 분류기→컬럼 매핑 API, RapidFuzz Top-3 추천→사용자 확인, 변환 이력→승인 전 배치→명시적 승인 게이트를 연결했다. 추천·미리보기·이력 저장·업무 승인 상태는 서로 구분한다.
- 11/16 공식 자료 FastAPI TestClient E2E와 프론트엔드 연계 문서를 완료했다. 당시 **저장소와 CAPA SQL 경계는 메모리/테스트 대역**이었으며, 이후 11/17의 별도 실제 PostgreSQL 검증으로 입력·승인·예측 저장 경로를 확인했다. 실제 계획 계산 저장은 여전히 미검증이다.
- 가장 최근 실제 PostgreSQL 포함 전체 Python은 **2026-11-17: 1015 passed / 0 failed / 0 skipped / 2 deselected**. 기존 DB63개 중61개와 추가실DB3개를 통과했고 downgrade2개는 사용자 지시로 미실행이다. 당시 별도 비DB는951 passed/66 skipped. TypeScript/build·계약 동기화·보안도 통과했다. [11/17 상세](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md). 이전943/63skipped는 [11/16 기록](INGESTION_API_E2E_VERIFICATION_20261116.md)이다.
- 과거 실제 PostgreSQL 회귀 결과는 2026-11-15 `ff448ac`의 608 passed/0 skipped 등 해당 시점 보고서의 기록이다. 신규 0009나 현재 DB의 검증으로 승격하지 않는다. [DB 근거](DB_REGRESSION_E2E_VERIFICATION.md)

## 남은 작업

1. **김대영:** 개발0009 적용/기존자료 보존과 회귀DB의 원자성·불변성·동시성·격리·공식자료→승인→예측을 검증했다. 기존공식자료를 개발DB에 중복등록하지 않는다. 백업 실제복구리허설과 보존기간 정책은 후속이며 다음 파괴적 fixture도 새 범위승인이 필요하다.
2. **정마나미:** [화면 요청 P0/P1](INGESTION_UI_CHANGE_REQUEST.md)에 따라 기존 화면을 재사용해 신규 API를 연결한다. 기존 승인 UI를 중복 구현하지 않는다. 기존 npm 취약점 2건(Vite/esbuild)도 담당 영역에서 검토한다.
3. **김대영, 기존 개발 PC:** C01/C03/C06과 승인 입고 공급 경계를 구현했고 실DB의 조회·격리를 확인했다. 승인 입고 영구 원장과 변경 이력은 별도 설계 및 DB 적용 승인, 실제 엔진 실행·저장 회귀는 변환부와 격리 DB 사용 승인이 필요하다. [v0.4 인계](PLANNING_CONTRACT_V04_HANDOFF.md)
4. **이희원·김대영 의존 작업:** 계산 코어, HC-01~18, 공식 9제품×3개월×3안 독립 정답 비교 및 What-if 코어는 11/22 구현을 확인했다. 희원님은 새 공통 DTO와 `run` 변환부를 연결하고 월별 BOM·Routing 버전 및 1·3·6·12개월 인수 기준을 확인한다. 김대영은 같은 계약의 실제 저장·재조회와 정책 버전을 검증한다. 정식 승인은 서버 인증과 별도 승인 정책 확정 후 연결한다.
5. **통합/화면 담당:** DB 및 화면 연결 후 공식 자료의 전체 브라우저 E2E를 수행한다. 기존 FE client의 영구 계획 메서드를 재사용하고 LIVE Preview와 이력·저장·승인 상태를 구분한다. 제조 전체 E2E는 실제 계획 엔진도 필요하다.
6. **팀 검토:** 실제 기업 데이터의 이용 범위·단위/거래 상태·매핑 모호성·변환 정책을 검토한다. 합성 데이터 성과를 기업 데이터 성능으로 일반화하지 않는다. 현재 LLM/Upstage 호출은 하지 않으며 후속 입력/출력 계약만 [추천 보고서](MAPPING_RECOMMENDATION_MVP_20261116.md)에 정리돼 있다.

## 개발 환경 제한

**11/23 작업은 Docker·PostgreSQL이 없는 보조 PC에서 수행했다.** DB 접속·마이그레이션·DB 테스트는 미실행이다. 11/22의 기존 개발 PC 검증과 11/17의 별도 승인된 0009 적용은 해당 날짜의 기록이다.

- 기존 DB 데이터를 보존한다. 개발 DB/기존 `chungpamo_test` 초기화 금지, 독립 회귀 DB의 파괴적 작업도 [개발 절차](DEVELOPMENT_WORKFLOW.md)의 식별·보존 확인·별도 실행 승인이 필요하다.
- `frontend/`, `modules/file_classifier/`, `modules/planning_engine/` 담당 폴더 제한과 신규 migration 추가 금지를 유지한다. 추천 점수 기반 자동 등록·승인, 원본 기업 데이터 외부 API 전송을 하지 않는다.
- 분류·컬럼 추천 변경은 TestClient와 비DB 회귀로 검증했다. 66개 DB 테스트와 Alembic 명령 호출 검사 6개는 미실행이다.

## 작업 재개와 팀 공유

작업 시작/완료 절차는 [AGENTS](../AGENTS.md)에 따른다. 시작 시 이 문서와 최근 [CHANGELOG](DEVELOPMENT_CHANGELOG.md), 최신 Git·실제 코드를 함께 확인하고, 종료 시 두 문서를 갱신해 변경 파일만 Commit·Push한다. 검증/기록/Push 실패도 남긴다.

팀 공유용 [Notion 인계 페이지](https://app.notion.com/p/41b441f66d7881f4a060e999510b694b)는 이번에 조회·수정·동기화하지 않았다. GitHub의 두 Markdown 파일이 기준 기록이다. 후속 동기화는 날짜·Commit·상태·근거 링크를 사용한다.
