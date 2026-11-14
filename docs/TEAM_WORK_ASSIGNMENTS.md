# 충파모 MVP — 상세 작업 배분 및 파일 접근 범위

> **2026-11-15 상태 갱신:** CAPA·Routing의 실제 업로드/승인/조회, 신규 0006 및 PlanningSourceProvider 연결은 구현됐다. 아래 작업표의 해당 항목은 후속 유지·확장 업무로 읽는다. [데이터 사전](CAPACITY_ROUTING_DATA_DICTIONARY.md)과 [팀원 변경 요청](CAPACITY_ROUTING_CHANGE_REQUESTS.md)을 우선 확인한다. 계산 알고리즘·프론트 신규 entity 화면은 미구현이며 기존 담당 경계는 유지한다.

> 기준: `ChungPaMo/decision-supporter-mvp` `main` (`2071ce47`, 2026-11-14 확인). 이 문서는 기존 [TEAM_HANDOFF](TEAM_HANDOFF.md), [OWNERSHIP](OWNERSHIP.md), [INTEGRATION_CONTRACT](INTEGRATION_CONTRACT.md)를 보완하는 **팀 실행용 업무 분장표**다. 신규 브랜치·PR 없이 `main`에서 Pull → 담당 경로 수정 → 검증 → Commit → Push한다.

기존 문서의 계약과 실제 코드가 우선한다. 아래 업무는 후속 개발 배분이며 구현 완료 선언이나 미확정 계산 정책의 승인으로 해석하지 않는다. Git 상세 안전 규칙은 [DEVELOPMENT_WORKFLOW](DEVELOPMENT_WORKFLOW.md)를 따른다. 경로는 별도 설명이 없으면 저장소 루트 기준이다.

## 1. 프로젝트 목표와 현재 범위

**시연 E2E:** 휴지 제조기업의 CSV/XLSX → 파일 종류 자동 분류 → 컬럼 매핑·검증·승인 → PostgreSQL → 승인 수요 기반 P50/P80/P90 예측 → MPS 2~3안 → RCCP 월 생산능력 → MRP BOM/자재 → What-if → 최종 MPS 승인·Excel.

- **실제 구현:** 제품·자재·BOM·재고·월별 수요의 업로드/승인/조회, PostgreSQL 저장, 수요예측 실행·이력/차트 복원, 독립 DEMO XLSX.
- **골격만 구현:** 분류 API, 계획 API, 데이터 계약, 읽기 전용 계획 어댑터, 7단계 React 화면.
- **미구현:** 분류 알고리즘, CAPA/라우팅 업로드·승인, MPS/RCCP/MRP/What-if 실제 계산, 계획 실행 영구 저장, 정식 승인/Excel.
- **테스트 수치 구분:** [이전 DB 검증](monorepo_postgresql_verification_20261114.md)은 490 passed·브라우저 12 passed. [골격 검증 기록](E2E_SCAFFOLD_VERIFICATION_20261114.md)은 비DB Python 464 passed·55 skipped, 비DB 브라우저 8 passed. `2071ce47` 통합 시 Python·타입·빌드·계약·보안 검사를 재실행했으며 브라우저 8 passed는 이전 기록이다. DB 테스트 55개는 통합 시 **실행되지 않음**. 이 수치는 이번 문서 추가 작업의 실행 결과가 아니다.

## 2. 폴더 소유권 — 절대 겹치지 않게 개발

| 담당자 | 본인 수정 가능 경로 | 담당 업무 | 수정하지 않을 경로 |
|---|---|---|---|
| **김대영 (전체 통합)** | `backend/`, `contracts/`, `infrastructure/`, `tests/e2e/`, `scripts/`, `.github/`, 루트 설정, 공통 `docs/` | 컬럼 매핑·검증·승인, DB/API, CAPA/라우팅 등록·승인, 엔진 연계, 계획 이력·정식 출력 | 다른 팀원 알고리즘·화면은 사전 협의 없이 수정 금지 |
| **이훤 (파일 분류)** | `modules/file_classifier/` | CSV/XLSX 종류 자동 분류, 추천/HOLD, 성능 검증 | `backend/`, `contracts/`, `frontend/`, DB/승인 로직 |
| **이희원 (계획 엔진)** | `modules/planning_engine/` | 예측 유지, MPS/RCCP/MRP/What-if 계산과 독립 손계산 검증 | `backend/`, `contracts/`, `frontend/`, DB 마이그레이션 |
| **정마나미 (UI/UX)** | `frontend/` | PPT 스타일 7단계 React 화면, 실제/DEMO 구분, API 클라이언트 | `backend/`, `contracts/`, `modules/`, DB·계산 공식 |

**공통 파일:** `contracts/interfaces/`, `backend/app/api/`, Alembic 마이그레이션, OpenAPI/Schema 생성물, CI·루트 설정은 **김대영만 직접 변경**. 다른 팀원이 필요하면 변경 요청을 보낸다. 폴더 소유권은 협업 규칙이지 GitHub에서 강제되는 권한이 아니다.

## 3. 이훤 — 파일 유형 자동 분류

**시작 위치**
- `modules/file_classifier/src/file_classifier/__init__.py` — 현재 `AVAILABLE=False`, `classify()` 미구현.
- `modules/file_classifier/tests/test_classifier_boundary.py`
- `modules/file_classifier/README.md`

**계약**: `classify(ClassificationInput) -> ClassificationOutput`. 분류 모델은 `contracts/interfaces/modules.py`, 공통 기본 타입은 `contracts/interfaces/base.py`를 사용한다.

**입력:** 파일명, SHA-256, format(csv/xlsx/null), 시트명(원본 CSV는 null), 열 이름, 허용된 샘플 행. DTO는 최대 20시트·시트당 100컬럼/20행·셀 500자다. 파일 API의 `sample_row_limit`은 0~20(기본 0), 현재 UI는 사용자 선택 시 최대 5행이다. DB 커넥션·원본 파일 전체를 모듈에 전달하지 않는다. 제한 초과는 422로 처리하며 조용히 잘라내지 않는다.

**출력:** `recommended_entity` (`product`, `material`, `bom`, `inventory`, `monthly_demand` 중 하나 또는 null), `candidates[{entity, score, reasons}]`, `hold`, `reasons`, `module_version`. 점수는 확률 보장이 아니다.

**해야 할 일**
1. 규칙·별칭·열 분포 등으로 데이터 유형 추천; 구분 불가 시 반드시 HOLD.
2. 혼합 시트, 빈 열, 중복 헤더, 비정형 열, 제품/자재 혼동, 알 수 없는 파일을 포함한 반례 시험.
3. 정확도·오분류율·HOLD 비율·응답시간을 공개 가능한 합성 시험셋으로 측정.
4. 완료 시 본인 모듈의 `AVAILABLE=True`와 함수를 연결. 백엔드·공통 DTO 수정 없이 기존 `/classifications` 및 `/classifications/file` 사용.

**하지 않을 일:** 실제 DB 컬럼 매핑·검증·저장·승인, 임의의 CAPA/routing entity 추가, 외부 AI API로 기업 파일 전송.

**테스트:** 루트에서 `./.venv/Scripts/python.exe -m pytest modules/file_classifier -q`.

**완료 기준:** 서로 다른 파일 예시 분류·보류 결과 재현, DTO 검증 통과, 오분류 지표와 버전/근거 제시, 승인 우회 없음.

## 4. 이희원 — 수요예측 및 생산계획 엔진

**시작 위치**
- `modules/planning_engine/engine/planning.py` — `run(PlanningInput) -> PlanningOutput`, 현재 `AVAILABLE=False`.
- `modules/planning_engine/engine/forecast/` — 기존 예측 코드 **단 한 벌**, 복제 금지.
- `modules/planning_engine/mps/`, `modules/planning_engine/rccp/`, `modules/planning_engine/mrp/`, `modules/planning_engine/what_if/`, `modules/planning_engine/tests/`.

**해야 할 일**
1. 순수 Python 함수로 MPS 2~3안 계산. 입력 예측은 P50/P80/P90를 보존하며 안별 분위수·목적함수·KPI는 H-/N- 결정 전 임의 확정하지 않는다. 기초 완제품 재고·안전재고 등 실제 계약과 가정을 명시.
2. RCCP: 수량 한도·인시·설비시간을 각각 검증, 동일 자원 공유 제품의 부하 합계와 제품별 기여 표시. 일별 일정·자동 설비 배정의 지원 범위는 H-02~H-05에서 합의하며 현재 구현된 기능으로 취급하지 않는다.
3. MRP: BOM 전개와 재고 기준일, 필요 자재량·가용량·부족량. 리드타임 부재 시 납기 가능을 확정하지 않음.
4. What-if: 생산량·잔업 등 입력 변경 전후 결과를 동일 함수/계약으로 재계산하고 원본 버전·출처 보존.
5. 미확인/미지원 자료를 0 또는 무제한으로 치환하지 않고 `UNVERIFIED`·오류로 반환.
6. [H-01~H-12 질문](multi_capacity_decision_questions.md)의 답변·결정 기록을 먼저 확보하고, H-12의 독립 손계산 정답표로 테스트 작성. 첨부 초안의 ‘T-01~T-17(총 19케이스)’ 원문과 답변 완료 여부는 이 저장소에서 확인되지 않았으므로 확정 테스트 목록으로 사용하지 않는다. PPT의 예시 수치를 엔진 정답으로 사용 금지.
7. 완료 시 모듈 내부 `AVAILABLE=True`; 백엔드 API 연결 테스트는 김대영과 조율.

**읽을 계약:** `contracts/interfaces/planning.py`, `docs/INTEGRATION_CONTRACT.md`, `docs/multi_capacity_contract_draft.md`, `docs/multi_capacity_decision_questions.md`. 신규 필드·목적함수·제약 결합 규칙이 필요하면 김대영에게 DTO 변경 요청.

**현재 API 경계:** `POST /plans`와 `POST /plans/what-if`는 `PlanCommand`를 받아 `PlanningReply`를 반환하는 읽기 전용 preview다. 실제 forecast UUID와 승인 스냅샷은 서버 provider가 결합한다. 응답은 `persisted=false`, `approval_available=false`이며 실행 저장·승인 기능이 아니다. 기본 provider의 CAPA·라우팅은 null과 missing_inputs로 전달된다. 모듈 미구현은 501이고, What-if의 저장된 기준 계획 provider도 미구현(501 `PLAN_HISTORY_NOT_IMPLEMENTED`)이므로 `AVAILABLE=True`만으로 전체 What-if가 완성되지 않는다.

**테스트:** `./.venv/Scripts/python.exe -m pytest modules/planning_engine -q`.

**완료 기준:** 손계산 정답, 다제품 공유 설비, 자재 부족, 결측, 단위/오류, What-if 전후 재현 시험과 계산 근거·모듈 버전 제출.

## 5. 정마나미 — React 디자인과 실제 업무 화면

**주요 시작 파일**
- `frontend/src/App.tsx`, `frontend/src/layouts/MainLayout.tsx`
- `frontend/src/screens/DataUploadScreen.tsx`, `frontend/src/screens/ForecastScreen.tsx`, `frontend/src/screens/PlanningWorkspace.tsx`
- `frontend/src/components/ClassificationPanel.tsx`, `frontend/src/components/LivePlanningPanel.tsx`, `frontend/src/components/UsageMeter.tsx`, `frontend/src/components/ForecastChart.tsx`
- `frontend/src/styles/app.css`, `frontend/src/styles/operations.css`, `frontend/src/services/api.ts`, `frontend/src/services/planningDemo.ts`, `frontend/src/types/modules.ts`, `frontend/src/store/productionStore.ts`

**디자인 지침:** 이전 화장지 E2E PPT처럼 밝은 작업면, 딥네이비 헤더, 블루 단계 네비게이션, 실제 React 차트/표/BOM 트리/자원 사용량 그래프/What-if 조작으로 구현. 이미지를 UI 배경 전체에 붙이지 않음. 1920×1080과 1366px에서 잘림·겹침 없어야 함.

**7개 화면**
1. 데이터 업로드·분류·매핑·검증·실제 승인(자동분류 미구현 시 수동 선택, 실패 시 Mock 승인 전환 금지).
2. 실제 수요예측 실행 이력·P50/P80/P90 그래프와 제외/경고.
3. MPS 2~3안 생산량·재고·출처 비교.
4. RCCP 수량/설비/인시, 병목/부하율, 검증 범위 표시.
5. MRP BOM, 자재 소요·재고·부족량.
6. What-if 입력·재계산 및 전후 비교(엔진 미구현 시 결과 미산출 표시).
7. 최종 MPS 선택·경고·승인 이력·Excel(정식 승인 API 미구현 시 버튼 차단).

**주의:** 브라우저에 계획 수식/판정 로직을 새로 구현하지 않음. 서버의 409/422/501/503/연결 실패를 처리하되 fixture로 자동 대체하지 않음. 독립 DEMO 패널에는 고정 합성값임을 명확히 표시.

현재 실제 계획 preview는 메모리에만 보관하며 새로고침 후 서버 복원을 지원하지 않는다. 배치·예측의 기존 DB 복원은 유지한다. 모듈 성공 응답의 UI 시험은 TEST-DOUBLE-ONLY이며 실제 계획 계산 완료의 증거가 아니다.

**테스트:** `cd frontend; npm run type-check; npm run build; npm run test:e2e:ui`. 공통 E2E 스크립트를 고쳐야 하면 김대영에게 요청.

**완료 기준:** 단계 이동·상태 보존·모바일·키보드/모달·API 오류, DEMO/실데이터 분리, 실제 React 그래프/테이블/상호작용, 중요 화면 스크린샷 제출.

## 6. 김대영 — DB/API 및 전체 통합

**주요 시작 파일**
- `backend/app/api/integrations.py`, `backend/app/integrations/modules.py`, `backend/app/integrations/planning.py`
- `backend/app/api/batches.py`, `backend/migrations/`, `contracts/interfaces/`, `docs/CAPACITY_REGISTRATION_PLAN.md`
- `tests/e2e/`, `infrastructure/`, `scripts/`

**개발 순서**
1. **계약 확정:** 희원·나미와 CAPA 월 생산수량·인시·설비시간, 자원/라우팅, 셋업·대체 설비·공유 자원, 안전재고·UNVERIFIED 승인 정책을 논의. 확정 전 임의 계산 규칙 금지.
2. **CAPA·라우팅 등록:** 기존 승인 게이트를 확장할 업로드/검증/조회/승인 API와 신규 마이그레이션 작성. `0001~0005` 변경 금지. 승인된 데이터만 계획 입력에 제공.
3. **모듈 연동:** 분류·계획 결과의 DTO/오류/버전 검사. SQL provider로 예측 실행 UUID·입력 지문·승인 BOM/재고/CAPA/라우팅 스냅샷 전달.
4. **실행 이력:** 계획 및 시나리오 결과를 입력 해시·엔진 버전·정책·제약 근거와 함께 원자 저장. What-if 기본 계획 계보 지원.
5. **정식 승인/출력:** 권한·불가 계획 차단·미확인 예외 승인 규칙·감사 기록·승인본 Excel. DEMO XLSX와 별도 제공.
6. **전체 E2E:** 휴지 1종의 실제 입력 → 예측 → MPS/RCCP/MRP/What-if → 저장·확정까지 검증하고 이후 다제품 확장.

**비DB 테스트:** `./scripts/check.ps1`, `./.venv/Scripts/python.exe -m pytest backend/tests/test_planning_adapter.py backend/tests/test_planning_sources.py backend/tests/test_module_integration.py -q --no-db`, `./.venv/Scripts/python.exe scripts/security_check.py`.

**DB 안전:** 전용 Docker 프로젝트 `chungpamo-monorepo`의 `127.0.0.1:55433` 서버·`chungpamo_test` DB를 식별한 뒤, 스키마 초기화 포함 테스트는 별도 사용자 승인 범위에서만 실행한다. 이 문서는 실행 승인이 아니다. 기존 55432·sisicallcall 접근·변경 및 개발 DB 초기화 금지. `docker compose down -v`, `docker system prune`, `docker volume rm` 금지. 이번 문서 추가 작업에서는 DB·Docker를 사용하지 않는다.

## 7. 공통 변경 요청 절차

| 변경 필요 | 요청자 → 반영 담당 |
|---|---|
| 분류 대상 유형/입력 필드 추가 | 훤 → 대영: `contracts/`·백엔드 반영 |
| 계획 출력, CAPA 단위·정책 필드 변경 | 희원 → 대영: DTO/Schema/API/provider 반영 |
| 화면에 새로운 서버 API/오류 필드 필요 | 나미 → 대영: API/계약 검토 후 나미가 화면 연결 |
| API 변경에 따른 화면 변경 | 대영 → 나미 |
| 엔진 계산 공식·정책 해석 변경 | 대영/나미 → 희원 |

**변경 요청 형식:** 목적 / 관련 파일·API / 기존·제안 JSON / 호환 영향 / 테스트 / 우선순위. 기존 문서·계약을 조용히 수정하거나 다른 팀원 폴더를 무단 수정하지 않는다.

## 8. 작업 순서 및 통합 게이트

| 단계 | 병렬 작업 | 통합 완료 조건 |
|---|---|---|
| **A (지금)** | 훤: 분류 알고리즘 · 희원: 순수 계획 계산/손계산 · 나미: React 화면/UX · 대영: CAPA/라우팅 계약 | 각자 담당 폴더 테스트 통과·공통 계약 동결 |
| **B** | 대영: CAPA/라우팅 승인·조회 + 계획 provider | 실제 승인 CAPA/라우팅이 계획 입력에 전달됨 |
| **C** | 훤/희원: 모듈 정식 인터페이스 연결 | API 501→실제 결과 및 오류 경로 검증 |
| **D** | 나미: 계획 비교·진단·What-if 실데이터 화면 · 대영: 실행 이력/승인 | 화면·저장 ID·계보·버전 일치, Mock 분리 |
| **E** | 대영: 정식 승인/Excel · 전원: 합성 E2E | 휴지 1종 전체 흐름과 다제품 회귀 시연 |

## 9. 공통 Git 운영·제출 기준

```powershell
cd C:\chungpamo\decision-supporter-mvp
git status
git fetch origin
git switch main
git pull --ff-only origin main
# 본인 폴더에서만 수정 → 독립 테스트 → 변경 경로 확인
git status
git add <본인이_수정한_경로>
git commit -m "feat: 작업 내용"
# 원격이 바뀌었으면 변경 내역 확인 후 안전하게 반영·재검증
git fetch origin
git push origin main
```

- `git add .`는 다른 팀원의 미커밋 변경이 섞일 수 있으므로 지양.
- Push 충돌 시 강제 Push·reset/clean 금지. 원격 최신 변경을 확인하고 필요한 수정에 대해 담당자와 협의.
- 각 담당 완료 보고: 담당자 / 기준 SHA / 수정 파일 / 실제 구현 및 미구현 / 입출력 예시 / 실행 테스트 passed·failed·skipped / DB 테스트 실행 여부 / 공통 계약 변경 요청 / 민감정보 제외 확인 / 최종 Push SHA.

**완료의 기준:** 단순 폴더·화면·fixture 존재가 아니라 실제 함수/화면/API 경계 시험과 오류·미확인 처리 검증이다. 테스트 대역의 결과를 실계산 또는 공식 승인으로 표현하지 않는다.
