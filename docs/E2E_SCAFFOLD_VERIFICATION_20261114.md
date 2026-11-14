# 최종 E2E 개발 뼈대 검증 — 2026-11-14

기준 feature/backend-integration / af5e4fdbc0412db5039479d666b51e64fdcd63e4. 시작 작업 트리는 clean, fetch 후 원격과 차이는 0/0이었다. 기존 미커밋 작업을 지우거나 source repo를 수정하지 않았다.

## 완성한 연결 경계

- 분류 JSON API 유지 + 파일 DTO 변환 경로, 샘플 동의·HOLD·근거·명시적 유형 선택 UI. 추천은 batch 생성·승인과 분리한다.
- 모듈 구현 후 사용할 승인 데이터 read-only provider·계획 어댑터. 입력/출력 타입·범위/단위/오류 검증·지문·미저장/승인불가 envelope를 제공한다.
- CAPA·라우팅의 독립 수량/인시/설비시간 DTO·구조 검증·미래 승인 API 명세·테스트 계획. 현재 batch entity나 DB는 늘리지 않았다.
- 실제 모듈 응답과 합성 설명의 명시적 UI 모드, 단계별 결과, DEMO 선택 지속·RCCP 사용량·MRP 부족 표시·What-if 입력·최종 검토·모달 키보드 동작.
- 팀원별 자기 폴더·함수·계약·fixture·독립 시험·공통 파일 금지 경계를 TEAM_HANDOFF에 기록했다. mps/rccp/mrp/what_if가 editable 설치 후 import되는지도 검사한다.

## 이번 실행 결과

기존 PostgreSQL 490/브라우저 12 결과를 재사용하지 않는다. 이번 범위는 비DB 검증이다.

| 검증 | 결과 |
|---|---|
| 전체 Python 비DB | 464 passed / 0 failed / 55 skipped (8.22s) |
| 독립 modules 시험 | 36 passed (전체 Python에도 포함) |
| TypeScript / Vite production | 통과 |
| OpenAPI / JSON Schema / 소유 경계 | 전체 Python 동기화·경계 시험 통과 |
| 비DB 브라우저 UI | 8 passed |
| pip check / 공개 후보 보안 스캔 | 통과 |
| PostgreSQL 초기화·통합 시험 | 미실행·별도 승인 필요 |

브라우저 성공 렌더러는 TEST-DOUBLE-ONLY 응답 주입 시험이다. 알고리즘 개발·운영 성능·실제 계획 생성 완료를 의미하지 않는다. 실제 미구현 501과 HOLD/승인 비우회는 별도 경로로 검사한다. SQL provider는 fake 연결/저장소의 read-only·출처·기간·페이지·누락 처리로 시험했고 실제 PostgreSQL 실행은 이번에 하지 않았다.

## 수정한 주요 공백

기존 계획 어댑터는 AVAILABLE을 켜도 항상 501이었다. 이제 준비된 모듈을 승인 입력 provider로 연결하되 저장·승인 기능은 별도로 남겼다. 출력의 2~3안·중복·단위·범위와 불완전한 FEASIBLE을 검사한다. What-if는 실제 기준 계획 저장이 없으면 명시적 501이다.

기존 분류 메타데이터는 하드코딩이었고 업로드 연결이 없었다. 가용 플래그·파일 API·추천/HOLD UI를 추가했다. CSV에는 시트명이 없어 기존 non-empty 가정이 422를 유발했으며 null 시트명/format 계약으로 수정했다. Pydantic regex 엔진에서 지원하지 않는 lookahead는 동등한 연도 패턴으로 수정해 0000 거부를 유지했다.

계획안 선택이 단계 이동 때 초기화되는 문제를 UI 상태로 분리해 고쳤고, 실제 연결 모드에도 표시되던 합성 전용 전역 안내를 제거해 모드별 표시로 통합했다. 배치 작업 중 추천 유형을 바꾸는 동작도 비활성화했다. 모달 Escape·Tab 포커스 경계·복귀를 보완했다.

## 안전성과 남은 결정

이번 작업은 DB 접속/초기화·migration 적용·Docker 자원/OS 서비스 변경을 하지 않았다. API UI 시험은 PERSISTENCE=disabled와 도달하지 않는 DB URL을 사용하며 Python 시험은 --no-db로 연결을 차단한다. .env·실기업 자료·토큰·PPT·로그/trace/스크린샷·개인 로컬 경로는 Git에 포함하지 않는다. 바이너리 자료는 기존 이관 이미지 6개이며 새 자료가 아니다.

소스 저장소 3개의 비무시 파일 SHA256은 시작 기준과 동일하다(PoC 403, 기존 backend 147, 기존 frontend 58개). 0001~0005 및 예측 계산 소스도 바이트가 같다. 공개 후보의 기존 비밀값·토큰·전화번호·개인 사용자 경로 패턴 검사는 검출 0건이다. 이는 휴리스틱 검사이며 운영 보안 감사를 뜻하지 않는다. Starlette/httpx 사용 중단 예정 경고 1건과 Node 색상 환경 경고는 남아 있다.

CAPA 강도·동시 적용·셋업·대체/공유 설비·달력/시간 의미·결측·목적함수·KPI·UNVERIFIED 승인·비교 기준은 기존 H-/N- 질문의 결정 사항이다. 분류·계획 알고리즘, CAPA 등록/승인, 실제 계획 저장·What-if 기준 이력·정식 승인/출력은 아직 미구현이다. 새 SQL provider와 이 후속 저장 경로는 별도 승인 후 전용 테스트 DB에서 검증해야 한다.

## 변경 파일

아래는 이번 작업 시작 대비 코드/문서/생성물 목록이다. Git commit SHA·Push·PR 상태는 완료 보고와 Git 이력으로 확인한다.

- `README.md`
- `backend/app/api/integrations.py`
- `backend/app/errors.py`
- `backend/app/integrations/modules.py`
- `backend/app/integrations/planning.py`
- `backend/export_contract_schema.py`
- `backend/tests/test_module_integration.py`
- `backend/tests/test_planning_adapter.py`
- `backend/tests/test_planning_sources.py`
- `contracts/examples/integration/capacity_registration.json`
- `contracts/examples/integration/classification_hold.json`
- `contracts/examples/integration/classification_input.json`
- `contracts/examples/integration/classification_ready.json`
- `contracts/examples/integration/planning_input.json`
- `contracts/examples/integration/planning_output.json`
- `contracts/interfaces/base.py`
- `contracts/interfaces/capacity.py`
- `contracts/interfaces/modules.py`
- `contracts/interfaces/planning.py`
- `contracts/openapi.json`
- `contracts/schemas/module_interfaces_draft.json`
- `docs/ARCHITECTURE.md`
- `docs/CAPACITY_REGISTRATION_PLAN.md`
- `docs/E2E_SCAFFOLD_VERIFICATION_20261114.md`
- `docs/INTEGRATION_CONTRACT.md`
- `docs/OWNERSHIP.md`
- `docs/TEAM_HANDOFF.md`
- `docs/frontend_guide.md`
- `frontend/README.md`
- `frontend/src/components/ClassificationPanel.tsx`
- `frontend/src/components/LivePlanningPanel.tsx`
- `frontend/src/components/UsageMeter.tsx`
- `frontend/src/layouts/MainLayout.tsx`
- `frontend/src/screens/DataUploadScreen.tsx`
- `frontend/src/screens/PlanningWorkspace.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/services/planningDemo.ts`
- `frontend/src/store/productionStore.ts`
- `frontend/src/styles/operations.css`
- `frontend/src/types/modules.ts`
- `modules/file_classifier/README.md`
- `modules/planning_engine/README.md`
- `modules/planning_engine/mps/__init__.py`
- `modules/planning_engine/mrp/__init__.py`
- `modules/planning_engine/rccp/__init__.py`
- `modules/planning_engine/tests/test_capacity_contract.py`
- `modules/planning_engine/tests/test_planning_boundary.py`
- `modules/planning_engine/what_if/__init__.py`
- `pyproject.toml`
- `tests/e2e/browser/handoff.spec.ts`
- `tests/e2e/run_ui_e2e.py`
- `tests/e2e/test_ownership_boundaries.py`
