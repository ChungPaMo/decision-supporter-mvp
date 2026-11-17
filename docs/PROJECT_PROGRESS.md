# 충파모 프로젝트 진행상황

최종 확인: **2026-11-17 (KST), 기존 개발 PC**. 시작 기준: [`acd40a5`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/acd40a511a57b9c0d92d2391a2d028ed09914af7), fetch/pull 후 로컬/원격 main 일치. 이번 실제 PostgreSQL 검증 Commit은 고유 제목 `test: verify PostgreSQL ingestion history and preserve development data`와 [누적 이력의 마지막 항목](DEVELOPMENT_CHANGELOG.md)으로 식별한다.

이번 검증: **전체 pytest 1015 passed / 0 failed / 0 skipped / downgrade 2개 선택 제외**. 공식 원본→변환 이력·승인→예측을 실제 SQL로 확인했다. 별도 승인 후 개발 DB **0008→0009 적용 완료**: 기존55개 데이터 테이블·승인7+9배치·예측각1·기존객체/볼륨 보존, revision만 변경하고 새 이력4테이블은 빈 상태다. 이후 강제 읽기 전용 GET24건/60테이블 보존 확인. [이번 상세](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md).

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
| 데이터 입력·파싱 | CSV/XLSX·7종 배치·수동 매핑·재검증·승인/반려 유지. 공식8마스터+원장 변환9번째 배치를 실제 PostgreSQL로 검증 | 김대영 | 화면 전체 E2E는 별도. [실DB 검증](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |
| 파일 자동 분류 | 업로드용 규칙 분류 `AVAILABLE=True`, `rules-0.2.0`; JSON/파일 API 통합. 표준 5종 추천, CAPA/Routing·판매 원장 HOLD. 실제 API 회귀 검증 | 이훤(알고리즘), 김대영(API) | HOLD는 직접 유형 확인/변환 안내. 별도 문서·임베딩 연구는 업로드 API와 별개. [통합 검증](INGESTION_INTEGRATION_VERIFICATION_20261116.md) |
| 컬럼 매핑·AI 후보 추천 | 정확 일치·별칭·수동 override 유지, RapidFuzz Top-3/근거/사용자 검토 추천 구현. 소규모 48건 비교와 API 회귀 기록 존재 | 김대영 | 신규 표현·문맥 의존 오류 남음. BGE-M3는 과거 연구 재사용, 운영 연결/새 모델 실행 없음. LLM 호출 없음. [추천 평가·결정](MAPPING_RECOMMENDATION_MVP_20261116.md) |
| 정제·변환 | 원본5파일86,214→498, SQL 이력·원본bytes/SHA·승인 전 batch 연결·재조회·동시201/200·실제DB 실패 rollback 검증 완료 | 김대영 | 회귀/개발DB0009 적용 확인. 개발DB는 기존공식자료 중복등록 없이 새이력0건 유지. SYNTHETIC_ONLY를 일반 기업에 자동 적용하지 않음. [이력 계약](INGESTION_INTEGRATION_HISTORY.md), [실DB 근거](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |
| PostgreSQL·데이터셋 격리 | 신규v2의 로컬FK·UUID격리·불변/지연트리거 실제 검증. 보관dataset 포함3스키마·기존81테이블 보존 probe 후 rollback. 개발0009도 별도승인·백업확인 후 적용 | 김대영 | 개발/회귀 현재0009. 기존자료와 연결된 볼륨은 보존, downgrade2개 미실행. dataset_id는 인증권한 아님. [최신 근거](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |
| 수요예측 | 단일 엔진/계약 유지. 실제 승인된 변환 수요498행→예측OK/27행 저장·재조회·P50≤P80≤P90, 미승인 probe 제외 확인 | 이희원(엔진), 김대영(API), 정마나미(화면) | 합성 회귀 결과를 실제 기업 적합성으로 일반화하지 않음. [이번 실DB 검증](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |
| 생산계획·제약 계산 | DTO·어댑터·승인 CAPA/Routing 스냅샷·계획 이력/계보/검토/출력 게이트 기반 구현. **실제 `engine.planning.AVAILABLE=False`, MPS/RCCP/MRP/What-if 계산 미구현**, API 501 | 이희원(계산), 김대영(계약·저장) | 계산 엔진 통합 상태를 희원과 확인. 저장 기반/수기 계산 사례/DEMO를 실제 계획 완료로 해석하지 않음. 정식 APPROVE도 인증·정책 미연결로 차단. [소스](../modules/planning_engine/engine/planning.py), [계획 저장 기반](PLAN_EXECUTION_PERSISTENCE.md) |
| 프론트엔드 | 데이터셋 선택·배치 등록/검토/재검증/승인·분류 패널·예측 조회 및 별도 DEMO 화면 구현. 기존 비DB 브라우저 검사 기록과 11/16 type-check/build 통과 기록 | 정마나미 | 새 profile/Top-3/변환 정책·이력 API 화면 연결, CAPA/Routing 입력 확장 필요. `/ingest/` dataset scope·오래된 응답 보호 포함. [API 인계](INGESTION_UI_API_HANDOFF.md), [화면 변경 요청](INGESTION_UI_CHANGE_REQUEST.md) |
| 전체 E2E | 공식14파일 SHA와 입력·저장·승인·예측 **TestClient+실제PostgreSQL** 경로 검증 완료. 메모리/SQL 대역으로 저장 성공을 대체하지 않음 | 김대영(통합), 각 담당 | 신규입력 전체브라우저·실제계획계산을 포함한 제조전체E2E는 미완료. [이번 범위](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md) |

## 현재까지의 핵심 성과

- 대표 자료는 이희원 담당 **CHUNGPAMO-2027 공식 합성 생성기(SEED=20261115)**의 기존 원본·정답이다. [원본/정답 14파일 SHA manifest](../contracts/examples/ingestion_e2e_source_manifest.json)를 대조하고 검증 전후 보존했다. 임의 성공 fixture로 대체하지 않았다.
- 제품·자재·BOM·재고·자원·CAPA·Routing의 실제 DTO 연결과 공유 설비/동시 인시 요구를 확인했다. 판매 거래 **86,214행 → 월별 수요 498행**이 독립 정답의 제품/월/Decimal 수량/단위와 일치했다. 정상 수요만 집계하고 취소 제외·반품 별도를 유지했다.
- 파일 분류기→컬럼 매핑 API, RapidFuzz Top-3 추천→사용자 확인, 변환 이력→승인 전 배치→명시적 승인 게이트를 연결했다. 추천·미리보기·이력 저장·업무 승인 상태는 서로 구분한다.
- 공식 자료 FastAPI TestClient E2E와 프론트엔드 연계 문서를 완료했다. **저장소와 CAPA SQL 경계는 메모리/테스트 대역**이므로 실제 PostgreSQL 영구 저장 완료를 뜻하지 않는다.
- 가장 최근 실제 전체 Python은 **2026-11-17: 1015 passed / 0 failed / 0 skipped / 2 deselected**. 기존 DB63개 중61개와 추가실DB3개를 통과했고 downgrade2개는 사용자 지시로 미실행이다. 별도 비DB는951 passed/66 skipped. TypeScript/build·계약 동기화·보안도 통과했다. [이번 상세](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md). 이전943/63skipped는 [11/16 기록](INGESTION_API_E2E_VERIFICATION_20261116.md)이다.
- 과거 실제 PostgreSQL 회귀 결과는 2026-11-15 `ff448ac`의 608 passed/0 skipped 등 해당 시점 보고서의 기록이다. 신규 0009나 현재 DB의 검증으로 승격하지 않는다. [DB 근거](DB_REGRESSION_E2E_VERIFICATION.md)

## 남은 작업

1. **김대영:** 개발0009 적용/기존자료 보존과 회귀DB의 원자성·불변성·동시성·격리·공식자료→승인→예측을 검증했다. 기존공식자료를 개발DB에 중복등록하지 않는다. 백업 실제복구리허설과 보존기간 정책은 후속이며 다음 파괴적 fixture도 새 범위승인이 필요하다.
2. **정마나미:** [화면 요청 P0/P1](INGESTION_UI_CHANGE_REQUEST.md)에 따라 기존 화면을 재사용해 신규 API를 연결한다. 기존 승인 UI를 중복 구현하지 않는다. 기존 npm 취약점 2건(Vite/esbuild)도 담당 영역에서 검토한다.
3. **이희원·김대영:** 별도 연구/계산 규칙과 실제 `planning.run` 구현·통합 여부를 확인하고, 엔진 계약/제약 결과·정식 승인 정책을 연결한다. 현재 확인된 엔진은 미구현이다.
4. **통합/화면 담당:** DB 및 화면 연결 후 공식 자료의 전체 브라우저 E2E를 수행한다. 제조 전체 E2E는 실제 계획 엔진도 필요하다.
5. **팀 검토:** 실제 기업 데이터의 이용 범위·단위/거래 상태·매핑 모호성·변환 정책을 검토한다. 합성 데이터 성과를 기업 데이터 성능으로 일반화하지 않는다. 현재 LLM/Upstage 호출은 하지 않으며 후속 입력/출력 계약만 [추천 보고서](MAPPING_RECOMMENDATION_MVP_20261116.md)에 정리돼 있다.

## 개발 환경 제한

**이번 2026-11-17 요청은 기존 개발 PC의 Docker/DB 사용을 명시적으로 허용했다.** 실제컨테이너/볼륨/host/port/DB/user를 재확인하고 회귀초기화와 개발0009를 각각 별도로 승인받아 수행했다. 개발0009 적용 이후는 강제읽기전용 조회만 수행했다. 다른 보조 PC의 Docker/PostgreSQL 금지 및 과거승인 재사용금지는 유지한다.

- 기존 DB 데이터를 보존한다. 개발 DB/기존 `chungpamo_test` 초기화 금지, 독립 회귀 DB의 파괴적 작업도 [개발 절차](DEVELOPMENT_WORKFLOW.md)의 식별·보존 확인·별도 실행 승인이 필요하다.
- `frontend/`, `modules/file_classifier/`, `modules/planning_engine/` 담당 폴더 제한과 신규 migration 추가 금지를 유지한다. 추천 점수 기반 자동 등록·승인, 원본 기업 데이터 외부 API 전송을 하지 않는다.
- 이번 작업은 테스트·보존검사/승인guard·문서를 수정했다. 계획/분류 알고리즘·frontend·기존migration 파일을 수정하지 않았다. 기존 분류/예측 엔진은 실제 호출해 검증했고 새 모델 실험·외부AI 호출은 하지 않았다. 컨테이너/볼륨을 생성·재시작·삭제하지 않았다.

## 작업 재개와 팀 공유

작업 시작/완료 절차는 [AGENTS](../AGENTS.md)에 따른다. 시작 시 이 문서와 최근 [CHANGELOG](DEVELOPMENT_CHANGELOG.md), 최신 Git·실제 코드를 함께 확인하고, 종료 시 두 문서를 갱신해 변경 파일만 Commit·Push한다. 검증/기록/Push 실패도 남긴다.

팀 공유용 [Notion 인계 페이지](https://app.notion.com/p/41b441f66d7881f4a060e999510b694b)는 이번에 조회·수정·동기화하지 않았다. GitHub의 두 Markdown 파일이 기준 기록이다. 후속 동기화는 날짜·Commit·상태·근거 링크를 사용한다.
