# 개발·협업 절차

모든 충파모 개발은 이 모노레포의 `main`에서 진행한다. 새 브랜치와 PR을 생성하지 않는다. 각 담당은 OWNERSHIP.md의 경로에서 작업하며, 공유 계약·DB 스키마·루트 설정 변경은 김대영과 검토한다.

## Git 작업 순서

1. 작업 시작 전 `git status`와 `git fetch origin`으로 미커밋 변경·원격 변경을 확인한다. 기존 미커밋 변경을 보존한다.
2. `main`에서 `git pull --ff-only origin main`을 실행한다. 다른 팀원의 작업과 충돌하거나 fast-forward가 불가능하면 변경 내역과 원인을 확인하고, 임의로 덮어쓰지 않는다.
3. 담당 경로에서 개발하고 Python·TypeScript·빌드·계약 동기화·보안 검사를 실행한다. DB 초기화가 필요한 테스트는 별도 승인을 받는다.
4. 검증된 변경만 Commit하고 원격 최신 상태를 다시 확인한 뒤 `git push origin main`을 실행한다. Push가 거부되면 강제 Push하지 않고 원격 변경을 확인한다.
5. 로컬 `main`과 원격 `main` HEAD가 일치하는지 확인한다. 충돌은 파일과 원인을 보고하고 무리하게 병합하지 않는다.

`git push --force`, `git reset --hard`, `git clean -fd`를 사용하지 않는다. 출처 저장소와 다른 프로젝트 자원을 변경하지 않으며 비밀정보·실제 기업 데이터는 Commit하지 않는다.

## 기본 검증

루트에서 `./scripts/bootstrap.ps1`, `./scripts/check.ps1`. 기본 검증은 `--no-db`로 DB 연결을 차단한다. 건너뛴 DB 테스트는 통과가 아니다. CI도 DB 비파괴 검사와 UI 경계 검증을 기본으로 한다. Python 3.11+, Node 20+를 사용한다.

새 엔드포인트/오류 코드를 추가하면 frontend_guide와 OpenAPI를, 계약 변경이면 생성 Schema·예시를 갱신한다. 계획 공식·KPI를 Fixture 숫자에 맞춰 구현하지 않는다.

## 개발 DB 시작

1. `./scripts/init-env.ps1`: 기존 .env가 있으면 중단. 신규 임의 비밀번호로 새 파일만 생성한다.
2. `./scripts/start-db.ps1`: 새 자원 이름·포트가 모두 비어 있을 때만 시작한다. 기존 자원이 발견되면 자동 재사용/재시작하지 않고 점검을 요구한다.
3. `cd backend; ../.venv/Scripts/python.exe -m alembic upgrade head`. 새 전용 DB 대상임을 먼저 확인한다.
4. `./scripts/backend.ps1`와 `./scripts/frontend.ps1`을 각각 실행한다. CORS 출처는 http://127.0.0.1:5173만 사용한다. 비밀번호를 frontend/VITE_에 넣지 않는다.

과거 충파모 서버 55432, sisicallcall, 기존 Windows 서비스는 사용·변경하지 않는다. down -v, system prune, volume rm 명령을 쓰지 않는다.

## 파괴적 테스트는 별도 승인

DB 테스트는 public DROP/재생성, TRUNCATE, 0001~0005 왕복을 포함한다. **전용 대상 식별 + 기존 데이터 보존 불필요 확인 + 사용자의 해당 실행 승인**이 먼저다. 과거 별도 작업의 일회성 승인은 재사용하지 않는다.

신규 모노레포 컨테이너/볼륨/프로젝트/포트, 테스트 DB명, 테이블·스키마, SYNTHETIC 출처를 확인한다. 예상 밖 데이터가 있으면 중단한다. 승인 후에만 아래 토큰을 해당 프로세스 환경에 설정한다. 토큰은 승인을 대신하지 않는다.

```powershell
$env:CHUNGPAMO_ALLOW_TEST_DB_RESET='chungpamo_test@127.0.0.1:55433'
./.venv/Scripts/python.exe -m scripts.verify_test_db
./.venv/Scripts/python.exe -m pytest -q --tb=short
./.venv/Scripts/python.exe tests/e2e/run_postgres_e2e.py
Remove-Item Env:CHUNGPAMO_ALLOW_TEST_DB_RESET
```

guard는 데이터 삭제를 하지 않는다. guard 통과 이후 pytest/E2E만 테스트 DB를 재생성한다. 테스트 전 개발 DB 내용·DDL·기존 Docker 자원 식별자를 보존하고 종료 후 비교한다. pytest와 E2E를 같은 테스트 DB에서 동시에 실행하지 않는다.

## 비DB 브라우저 검증

`cd frontend; node node_modules/@playwright/test/cli.js install chromium` 후 루트에서 `./.venv/Scripts/python.exe tests/e2e/run_ui_e2e.py`. 실제 persistence-disabled API와 PPT 화면 상호작용만 확인한다. DB 기반 등록·예측 E2E 검증의 대체가 아니다.
