# Architecture · 2026-11-14

공식 통합 대상은 이 저장소 하나다. 기존 세 저장소는 읽기 전용 출처다.

## 실행 경계

React `frontend/` → FastAPI `backend/app/api/` → 등록·검증·승인 서비스 → SQL 저장소/트리거 → PostgreSQL.
승인 월별 수요 → backend 예측 스냅샷 → `engine.forecast.run` → 실행/출처/결과 원자 저장 → React 이력·차트.
`PERSISTENCE=disabled`이면 저장 API는 501이며 Fixture 승인으로 전환하지 않는다.

| 영역 | 배치와 이유 |
|---|---|
| backend/app | FastAPI·모델·기존 sql_repository 위치 유지. 불필요한 persistence 이동은 하지 않음 |
| modules/planning_engine/engine/forecast | 기존 엔진 **한 벌만** 이동. 공개 import `engine.forecast` 유지. editable 패키지와 pytest pythonpath로 연결 |
| modules/planning_engine/{mps,rccp,mrp,what_if} | 담당자 구현 경계·README. 계산 알고리즘은 없음. 통합 진입점 engine.planning |
| modules/file_classifier/src/file_classifier | bounded descriptor 계약과 순수 함수 확장점. 현재 NotImplementedError |
| contracts/interfaces | Pydantic·Protocol 초안. 공유 변경은 김대영 검토 |
| contracts/schemas | 신규 모듈 계약 생성물. 기존 Schema는 경로 호환을 위해 contracts/ 루트 유지 |
| tests/e2e | 통합 담당의 Python 서버 실행기·브라우저 테스트. Playwright 의존성은 frontend 설치를 사용 |
| infrastructure | 기존 0001~0005를 그대로 사용하는 새 전용 Compose. DB 마이그레이션 원본은 backend/migrations 유지 |

## 구현과 미구현

- 실제: CSV/XLSX 파싱·수동 entity 선택·매핑·검증·명시적 승인/반려·DB 조회, 승인 수요 예측·중복/동시성·저장·복원, JSON→DEMO Excel formatter.
- 미구현: 파일 자동 분류 알고리즘, CAPA·라우팅 업로드/승인, MPS/RCCP/MRP/What-if 계산, 계획 실행 영구 저장·정식 승인·정식 출력.
- `/classifications`, `/plans`, `/plans/what-if`는 명시적 501 MODULE_NOT_IMPLEMENTED. `/integrations/modules`는 구현 경계를 알려 준다. API 성공을 흉내 내지 않는다.
- PPT 수치는 DEMO 화면의 고정 설명값. 화면 선택·슬라이더는 계산·승인·서버 저장이 아니다. 실제 예측과 자동 연결하지 않는다.

## 데이터 안전성

기존 서버 55432와 별도인 **127.0.0.1:55433**, Compose `chungpamo-monorepo`, 컨테이너 `chungpamo-monorepo-db`, 볼륨 `chungpamo-monorepo-pgdata`, 네트워크 `chungpamo-monorepo-net`을 사용한다. DB 이름은 기존 계약 호환을 위해 chungpamo/chungpamo_test지만 PostgreSQL 서버와 저장 볼륨이 다르다. 기존 .env·비밀번호·볼륨은 재사용하지 않는다.

애플리케이션은 인증·권한·실기업 운영 검증 전의 로컬 MVP다. CODEOWNERS는 경로 접근 권한을 제한하는 장치가 아니다.
