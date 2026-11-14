# Monorepo migration · 2026-11-14

## 출처와 시작 상태

| 저장소 | 기준 SHA | 시작 Git 상태 |
|---|---|---|
| chungpamo-ai-poc | d5def2701722c7d72deb58c31a0acd377ee151de | clean, 이관 대상 아님 |
| decision-supporter | fc877158f91c17e9f8452225c4fa217d498866ba | clean |
| decision-supporter-frontend | 388a9802df09481a730f3d9148ef04832b100ed7 | clean |
| decision-supporter-mvp | 원격 baf829d55514277380f8cf4475d41f6d279701f7 | 로컬 unborn/clean, 원격 README 확인 후 main 체크아웃 |

원격 초기 README 커밋을 보존하고 feature/backend-integration에서 통합했다. 기존 Git 이력을 강제 합치지 않았다. 소스 저장소는 fetch/수정/commit/push/reset/clean하지 않았다. 추적·비무시 미추적 파일 SHA256을 작업 전 기록하고 종료 시 대조한다.

## 이관과 조정

203개 추적 파일을 allowlist로 이관했다. 전체 원본→대상은 migration_inventory.json에 기록했다. 이 목록은 이관 직후의 목록이며 후속 통합 이동은 아래가 우선한다.

- backend/app·tests·migrations, contracts, docs 재사용. 기존 SQLAlchemy 패키지 위치 유지.
- engine 전체 → modules/planning_engine/engine 한 벌. 예측 계산 파일·기존 마이그레이션 0001~0005는 바이트 그대로 유지. 테스트/예시 생성기의 repo-root 기준만 조정.
- db/init과 compose → infrastructure. 기존 자원과 충돌하지 않도록 새 프로젝트/컨테이너/볼륨/네트워크·55433 지정.
- React src·설정·합성 Mock·기존 디자인 문서/이미지 → frontend. 과거 스크린샷은 현재 화면 증거가 아니다.
- frontend 브라우저 spec/실행기 → tests/e2e. 내부 경로·tsconfig alias·전용 변환 캐시·새 DB 대상·승인 guard 추가.
- .git, .env(예시 제외), .venv, node_modules, dist, 테스트 캐시, DB 파일, .claude/.impeccable 로컬 도구 설정은 복사하지 않았다. 새 환경은 독립 설치했다.

## PPT와 화면

사용자가 확인한 `충파모_화장지_E2E_레이아웃개선_최종.pptx`를 기준으로 사용했다. 요청 이름의 (1) 접미사 차이는 사용자 확인을 받았다. 로컬 경로·PPT 원본·슬라이드 이미지는 Git에 포함하지 않는다.

네이비 헤더·단계 탐색·업로드/검증/승인 카드·실제 예측 SVG 차트·MPS 비교표·RCCP 자원 카드·MRP BOM 펼침·What-if 슬라이더·최종 승인 안내를 HTML/CSS/React로 구성했다. PPT의 숫자 충돌/잠정 정책은 계산식으로 확정하지 않았다. 알고리즘 미구현 단계는 명시적 DEMO/미검증이며 정식 승인 불가다.

## 검증 기록

현재 비DB pytest: 435 passed / 55 skipped / 0 failed. DB 테스트 55개는 미실행이며 성공으로 간주하지 않는다. TypeScript·프로덕션 빌드·pip check 통과. persistence-disabled 실제 API/PPT 화면/모바일 브라우저 E2E 3 passed.

이관 과정에서 의존성 파일의 이전 engine 경로, root browser spec의 Node 모듈 해석, Windows 기본 Playwright 변환 캐시 문제를 확인하고 수정했다. 전용 가상환경·tsconfig alias·전용 캐시를 사용한다. 기존 저장소 실행 환경은 변경하지 않았다.

과거 478/8 통과 기록은 **이관 후 검증 결과와 별개**다.

## 현재 완료 범위와 보류

2026-11-14 신규 서버 생성·테스트 DB 초기화의 별도 승인을 요청했으나 아직 답변이 없어 Docker/DB 실행·초기화는 하지 않았다. 기존 개발·테스트 DB에도 접속·변경하지 않았다. DB pytest 55개와 PostgreSQL 등록/예측 브라우저 E2E 9개(기존 8 + 휴지 1)는 이관 후 미실행이다. 새로운 전체 제조 E2E 완료로 표현하지 않는다.

독립 모듈 테스트는 27 passed(전체 pytest에 포함), 전체 비DB pytest는 435 passed / 55 skipped / 0 failed, 비DB 실제 API·화면 경계 브라우저 E2E는 3 passed다. 모듈 import·OpenAPI/Schema 동기화·소유 경계 검사·TypeScript·프로덕션 빌드·pip check를 통과했다. Starlette/httpx 사용 중단 예정 경고 1건은 남았다. CI 정의는 추가했으며 원격 CI 실행 결과는 로컬 검사와 별도다.

오프라인 보안 스캔에서 비밀·토큰·개인 연락처·실사용자 로컬 경로 패턴이 검출되지 않았다. 가상 사용자 someone 경로 차단 회귀 테스트와 검사기 자체 정규식은 알려진 예외다. 6개 이관 이미지가 바이너리이며 기존 GitHub 자료를 그대로 보존했다. 새 PPT·추출 이미지·브라우저 로그·환경·의존성 캐시는 Git에서 제외했다. 이 검사는 휴리스틱이며 기업 운영 보안 감사를 의미하지 않는다.

세 출처 저장소의 시작 대비 파일 SHA256은 모두 동일하다(PoC 403, backend 147, frontend 58개). 0001~0005 마이그레이션과 예측 계산 파일 contract/features/model/service도 원본과 바이트가 같다.

검증된 초기 통합을 feature/backend-integration으로 반영한다. DB 재검증·담당자 알고리즘·정식 계획 저장/승인/출력은 남은 작업으로 유지한다.
