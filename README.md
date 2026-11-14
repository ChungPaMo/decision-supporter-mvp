# decision-supporter-mvp

충파모 공식 단일 모노레포 · 가상 휴지 제조기업 생산계획 지원 MVP.
기존 backend/frontend의 실제 등록·승인·예측을 통합했으며 분류·계획 계산은 담당자가 구현할 연결점입니다.

이관 후 검증: 비DB pytest **435 passed / 55 skipped**, TypeScript·빌드·모듈 import·계약 동기화 통과, 비DB 브라우저 E2E **3 passed**. 신규 DB 생성·초기화 승인은 대기 중이므로 DB 테스트와 PostgreSQL 브라우저 E2E는 아직 재실행하지 않았습니다. 전체 제조 E2E 완료 상태가 아닙니다.

## 현재 동작 범위

| 단계 | 상태 |
|---|---|
| CSV/XLSX 수동 유형 선택·매핑·검증·승인/반려·PostgreSQL 저장 | 실제 구현 이관 |
| 파일 자동 분류 | 미구현, API 501. 수동 선택 유지 |
| 승인 수요 → P50/P80/P90 → DB 실행/출처/결과 → React 이력·차트 | 실제 구현 이관 |
| MPS 3안 / RCCP / MRP / What-if | 인터페이스·명시적 501·독립 DEMO 화면. 계산 엔진 미구현 |
| 최종 MPS 저장·승인·정식 Excel | 미구현. 기존 독립 Fixture DEMO Excel formatter만 유지 |

## 구조와 담당

```text
frontend/                       정마나미 · React/디자인/표시/API 클라이언트
backend/                        김대영 · FastAPI/검증/승인/SQL/마이그레이션
modules/file_classifier/        이훤 · 분류 확장점, 알고리즘 미구현
modules/planning_engine/        이희원 · engine/forecast 단일 구현 + 계획 확장점
contracts/{interfaces,schemas}/ 김대영 · 신규 공통 계약
infrastructure/                 김대영 · 새 전용 PostgreSQL Compose
tests/e2e/                      김대영 · 실제 연결/비파괴 UI 브라우저 검증
scripts/ .github/ docs/          공통 실행·협업·검증
```

## Windows PowerShell 실행

Python 3.11+, Node 20+, DB 실행 시 Docker Desktop이 필요합니다.

```powershell
cd C:\chungpamo\decision-supporter-mvp
./scripts/bootstrap.ps1
./scripts/init-env.ps1           # 새 임의 개발 비밀번호, 기존 .env는 덮어쓰지 않음
./scripts/start-db.ps1           # 기존 자원 발견 시 중단, 신규 전용 55433만
cd backend
../.venv/Scripts/python.exe -m alembic upgrade head
cd ..
./scripts/backend.ps1           # 별도 터미널: http://127.0.0.1:8000/docs
./scripts/frontend.ps1          # 별도 터미널: http://127.0.0.1:5173
```

DB 없이 시작하려면 init-env/start-db/migration을 생략합니다. 기본 PERSISTENCE=disabled이므로 DB API는 501, health는 DB 부재 시 503입니다. API 연결 실패 시 Fixture로 자동 전환하지 않습니다.

DB 프로젝트 `chungpamo-monorepo`, 컨테이너 `chungpamo-monorepo-db`, 볼륨 `chungpamo-monorepo-pgdata`, 네트워크 `chungpamo-monorepo-net`입니다. 기존 55432 충파모 서버 및 sisicallcall과 별도입니다. 다른 저장소의 .env/환경/DB를 복사하거나 재사용하지 않습니다.

## 검증

```powershell
./scripts/check.ps1             # DB 연결 차단 pytest + pip check + TypeScript + build
./.venv/Scripts/python.exe scripts/security_check.py
cd frontend
node node_modules/@playwright/test/cli.js install chromium
cd ..
./.venv/Scripts/python.exe tests/e2e/run_ui_e2e.py
```

DB 테스트는 스키마 초기화를 포함하며 별도 사용자 승인과 전용 대상 확인 후에만 실행합니다. [절차](docs/DEVELOPMENT_WORKFLOW.md)를 따르세요. `--no-db` skip은 통과가 아닙니다.

휴지 1종 합성 데이터는 `contracts/examples/tissue_*.csv`입니다. source_type=SYNTHETIC와 출처 설명을 지정해 제품 → 자재 → BOM → 재고 → 월별 수요 순서로 승인합니다. TP-10R의 EA는 10롤 1팩입니다. 기준일 2026-12-31, 1개월 예측으로 2027년 1월을 확인합니다. 예측값이 PPT 고정 예시와 같다고 보장하지 않습니다.

## 협업과 계약

- [구조](docs/ARCHITECTURE.md), [소유권](docs/OWNERSHIP.md), [인터페이스](docs/INTEGRATION_CONTRACT.md)
- [개발 절차](docs/DEVELOPMENT_WORKFLOW.md), [이관·검증 기록](docs/MIGRATION_REPORT.md)
- [다중 CAPA 미확정 초안](docs/multi_capacity_contract_draft.md), [팀 결정 질문](docs/multi_capacity_decision_questions.md)

모듈 개발은 각 담당 폴더에서 진행하고 공통 계약·DB·설정은 김대영 검토 PR로 통합합니다. 실제 GitHub 계정 매핑이 미확인이라 CODEOWNERS 활성 규칙은 없습니다. 초기 원격 README 이력은 보존했습니다.
