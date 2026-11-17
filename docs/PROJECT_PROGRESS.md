# 충파모 프로젝트 진행상황

최종 확인: **2026-11-17 (KST)**. 구현 기준: [`86a1fdb`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/86a1fdb7399741c80bc376dfa794d518bf327cac), 로컬/원격 `main` 일치 확인. 이번 작업은 기록 체계 문서화이며 기능 코드를 변경하거나 기능 테스트를 새로 실행하지 않았다. 기록 변경 Commit은 [누적 이력의 마지막 항목](DEVELOPMENT_CHANGELOG.md)으로 식별한다.

이번 문서 검증: 변경 범위·로컬 링크·Git 참조·기록 양식·공백/인코딩 정적 검사 통과. 상세 결과는 누적 이력에 기록했다.

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
| 데이터 입력·파싱 | CSV/XLSX, 7종 배치(product/material/bom/inventory/monthly_demand/capacity/routing), 수동 매핑·재검증·승인/반려 구현. 기존 저장 경로는 과거 실DB 검증, 최신 입력 흐름은 TestClient·메모리 경계 검증 | 김대영 | 신규 변환 이력의 SQL 경로 재검증 필요. [공식 API E2E](INGESTION_API_E2E_VERIFICATION_20261116.md) |
| 파일 자동 분류 | 업로드용 규칙 분류 `AVAILABLE=True`, `rules-0.2.0`; JSON/파일 API 통합. 표준 5종 추천, CAPA/Routing·판매 원장 HOLD. 실제 API 회귀 검증 | 이훤(알고리즘), 김대영(API) | HOLD는 직접 유형 확인/변환 안내. 별도 문서·임베딩 연구는 업로드 API와 별개. [통합 검증](INGESTION_INTEGRATION_VERIFICATION_20261116.md) |
| 컬럼 매핑·AI 후보 추천 | 정확 일치·별칭·수동 override 유지, RapidFuzz Top-3/근거/사용자 검토 추천 구현. 소규모 48건 비교와 API 회귀 기록 존재 | 김대영 | 신규 표현·문맥 의존 오류 남음. BGE-M3는 과거 연구 재사용, 운영 연결/새 모델 실행 없음. LLM 호출 없음. [추천 평가·결정](MAPPING_RECOMMENDATION_MVP_20261116.md) |
| 정제·변환 | 형식/필수/중복/단위/참조 검증, 확인 정책 기반 합성 판매→월수요 구현. 원본·정책·전체 결과 이력/승인 전 배치 연결 SQL 코드와 0009 존재 | 김대영 | **0009 실DB 미적용·신규 이력 실DB 미검증**. 현재 증거는 메모리 저장소. SYNTHETIC_ONLY 정책을 일반 기업에 자동 적용하지 않음. [이력 계약](INGESTION_INTEGRATION_HISTORY.md) |
| PostgreSQL·데이터셋 격리 | 기존 승인 트랜잭션·출처/지문 게이트, 동일 DB 내 데이터셋별 스키마·UUID/참조 격리 구현. 0008까지 과거 실DB 검증 기록. 신규 스키마 v2·0009는 코드만 준비 | 김대영 | 현재 DB 상태는 조회하지 않음. dataset_id는 인증 권한이 아님. [격리](DATASET_ISOLATION.md), [과거 DB 회귀](DB_REGRESSION_E2E_VERIFICATION.md) |
| 수요예측 | `modules/planning_engine/engine/forecast/` 단일 구현과 API, 승인 수요 스냅샷·출처·중복 방지·P50/P80/P90 이력/화면 연계 구현. 과거 실제 PostgreSQL 예측 검증 기록 | 이희원(엔진), 김대영(API), 정마나미(화면) | 신규 변환 수요의 실DB→예측 연결 및 실제 기업 적합성 확인 필요. [예측 API](api_contract_forecast_runs.md), [과거 DB E2E](monorepo_postgresql_verification_20261114.md) |
| 생산계획·제약 계산 | DTO·어댑터·승인 CAPA/Routing 스냅샷·계획 이력/계보/검토/출력 게이트 기반 구현. **실제 `engine.planning.AVAILABLE=False`, MPS/RCCP/MRP/What-if 계산 미구현**, API 501 | 이희원(계산), 김대영(계약·저장) | 계산 엔진 통합 상태를 희원과 확인. 저장 기반/수기 계산 사례/DEMO를 실제 계획 완료로 해석하지 않음. 정식 APPROVE도 인증·정책 미연결로 차단. [소스](../modules/planning_engine/engine/planning.py), [계획 저장 기반](PLAN_EXECUTION_PERSISTENCE.md) |
| 프론트엔드 | 데이터셋 선택·배치 등록/검토/재검증/승인·분류 패널·예측 조회 및 별도 DEMO 화면 구현. 기존 비DB 브라우저 검사 기록과 11/16 type-check/build 통과 기록 | 정마나미 | 새 profile/Top-3/변환 정책·이력 API 화면 연결, CAPA/Routing 입력 확장 필요. `/ingest/` dataset scope·오래된 응답 보호 포함. [API 인계](INGESTION_UI_API_HANDOFF.md), [화면 변경 요청](INGESTION_UI_CHANGE_REQUEST.md) |
| 전체 E2E | 공식 자료의 **입력 API 사용자 흐름은 TestClient+메모리 저장 경계로 완료**. 기존 등록·예측의 과거 실DB/브라우저 검증은 별도 존재 | 김대영(통합), 각 담당 | 신규 입력 전체 브라우저·0009 실DB·실제 계획 계산을 포함한 제조 전체 E2E는 미완료. API 대역 결과로 대체하지 않음. [최신 범위](INGESTION_API_E2E_VERIFICATION_20261116.md) |

## 현재까지의 핵심 성과

- 대표 자료는 이희원 담당 **CHUNGPAMO-2027 공식 합성 생성기(SEED=20261115)**의 기존 원본·정답이다. [원본/정답 14파일 SHA manifest](../contracts/examples/ingestion_e2e_source_manifest.json)를 대조하고 검증 전후 보존했다. 임의 성공 fixture로 대체하지 않았다.
- 제품·자재·BOM·재고·자원·CAPA·Routing의 실제 DTO 연결과 공유 설비/동시 인시 요구를 확인했다. 판매 거래 **86,214행 → 월별 수요 498행**이 독립 정답의 제품/월/Decimal 수량/단위와 일치했다. 정상 수요만 집계하고 취소 제외·반품 별도를 유지했다.
- 파일 분류기→컬럼 매핑 API, RapidFuzz Top-3 추천→사용자 확인, 변환 이력→승인 전 배치→명시적 승인 게이트를 연결했다. 추천·미리보기·이력 저장·업무 승인 상태는 서로 구분한다.
- 공식 자료 FastAPI TestClient E2E와 프론트엔드 연계 문서를 완료했다. **저장소와 CAPA SQL 경계는 메모리/테스트 대역**이므로 실제 PostgreSQL 영구 저장 완료를 뜻하지 않는다.
- 가장 최근 전체 Python 실행 기록은 **2026-11-16, `86a1fdb`: 943 passed / 0 failed / 63 skipped (`--no-db`)**다. 63개 DB 테스트는 접속 차단으로 제외했으며 통과가 아니다. 같은 작업에서 TypeScript/build·계약 동기화도 통과했다. **이번 11/17 문서 작업에서 재실행한 수치가 아니다.** [상세 보고서](INGESTION_API_E2E_VERIFICATION_20261116.md)
- 과거 실제 PostgreSQL 회귀 결과는 2026-11-15 `ff448ac`의 608 passed/0 skipped 등 해당 시점 보고서의 기록이다. 신규 0009나 현재 DB의 검증으로 승격하지 않는다. [DB 근거](DB_REGRESSION_E2E_VERIFICATION.md)

## 남은 작업

1. **기존 개발 PC / 김대영:** 실제 대상·현재 revision·기존 배치/예측 보존 상태를 먼저 확인하고 기존 0009를 등록된 모든 데이터셋 스키마(보관 상태 포함)에 적용한다. 독립 회귀 DB에서 원자 저장/실패 롤백/불변 트리거/동시 요청 재사용/격리/스키마 v2와 승인 전→재검증→명시적 승인→수요/예측 연결을 검증한다. 파괴적 fixture는 별도 대상과 해당 실행 승인 후 사용한다.
2. **정마나미:** [화면 요청 P0/P1](INGESTION_UI_CHANGE_REQUEST.md)에 따라 기존 화면을 재사용해 신규 API를 연결한다. 기존 승인 UI를 중복 구현하지 않는다. 기존 npm 취약점 2건(Vite/esbuild)도 담당 영역에서 검토한다.
3. **이희원·김대영:** 별도 연구/계산 규칙과 실제 `planning.run` 구현·통합 여부를 확인하고, 엔진 계약/제약 결과·정식 승인 정책을 연결한다. 현재 확인된 엔진은 미구현이다.
4. **통합/화면 담당:** DB 및 화면 연결 후 공식 자료의 전체 브라우저 E2E를 수행한다. 제조 전체 E2E는 실제 계획 엔진도 필요하다.
5. **팀 검토:** 실제 기업 데이터의 이용 범위·단위/거래 상태·매핑 모호성·변환 정책을 검토한다. 합성 데이터 성과를 기업 데이터 성능으로 일반화하지 않는다. 현재 LLM/Upstage 호출은 하지 않으며 후속 입력/출력 계약만 [추천 보고서](MAPPING_RECOMMENDATION_MVP_20261116.md)에 정리돼 있다.

## 개발 환경 제한

**현재 보조 PC에서는 Docker와 PostgreSQL 관련 작업을 일절 수행하지 않는다.** Docker 설치·실행·컨테이너/볼륨 명령, PostgreSQL 설치·구성·실행·접속, migration 온라인 적용, DB 쓰기 테스트·실DB E2E는 **기존 개발 PC에서만** 수행한다. 현재 PC에서는 비DB 검사와 독립 Python 실험만 허용한다. 과거 DB 실행법/주소/승인은 현재 실행 허가가 아니다.

- 기존 DB 데이터를 보존한다. 개발 DB/기존 `chungpamo_test` 초기화 금지, 독립 회귀 DB의 파괴적 작업도 [개발 절차](DEVELOPMENT_WORKFLOW.md)의 식별·보존 확인·별도 실행 승인이 필요하다.
- `frontend/`, `modules/file_classifier/`, `modules/planning_engine/` 담당 폴더 제한과 신규 migration 추가 금지를 유지한다. 추천 점수 기반 자동 등록·승인, 원본 기업 데이터 외부 API 전송을 하지 않는다.
- 이번 기록 체계 작업은 Markdown만 수정한다. 기존 기능 테스트·DB·모델·외부 API는 실행하지 않는다.

## 작업 재개와 팀 공유

작업 시작/완료 절차는 [AGENTS](../AGENTS.md)에 따른다. 시작 시 이 문서와 최근 [CHANGELOG](DEVELOPMENT_CHANGELOG.md), 최신 Git·실제 코드를 함께 확인하고, 종료 시 두 문서를 갱신해 변경 파일만 Commit·Push한다. 검증/기록/Push 실패도 남긴다.

팀 공유용 [Notion 인계 페이지](https://app.notion.com/p/41b441f66d7881f4a060e999510b694b)는 이번에 조회·수정·동기화하지 않았다. GitHub의 두 Markdown 파일이 기준 기록이다. 후속 동기화는 날짜·Commit·상태·근거 링크를 사용한다.
