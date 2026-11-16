# 파일 입력 통합 검증 — 2026-11-16

김대영 담당의 연속 작업. 시작 로컬 main은 `115ed4daf8cf1aaf9743df3c1ca415afd70e185a`, 미커밋 변경 없음. 원격 origin은 ChungPaMo/decision-supporter-mvp이며 최신 main `0762ebff937a3e4cebbd63f608d9fd0963bf024c`를 fetch/fast-forward한 뒤 작업했다. 새 브랜치·PR은 만들지 않았다. 최종 Push SHA는 최종 응답과 Git 이력에서 확인한다.

## 확인한 환경

실제 경로는 `C:\chungpamo\decision-supporter-mvp`다. Python 3.11.9, Node v24.18.0, npm 11.16.0. 프로젝트 .venv를 새로 만들고 infrastructure/python-constraints.txt와 backend/requirements-forecast.txt의 고정 의존성을 설치했다. frontend는 기존 package-lock.json으로 npm ci했다. PowerShell 실행 정책으로 npm.ps1이 차단되어 npm.cmd를 사용했고, pip의 CP949 읽기 오류는 Python -X utf8로 해결했다. 저장소 의존성 버전/lockfile은 바꾸지 않았다.

프로젝트 .env/.env.regression.local과 DB 관련 환경변수는 없었다. Docker/psql 명령은 PATH에서 확인되지 않았다. 기존 55433 주소를 같은 DB라고 가정하지 않았고 실제 DB 접속을 시도하지 않았다. DB·역할·비밀번호를 생성/추측하지 않았으며 migration/초기화/DROP/TRUNCATE/downgrade/volume 작업을 하지 않았다. 따라서 개발 DB의 과거 7/9개 승인 배치·예측 보존 상태를 이번에 조회·대조한 것으로 주장하지 않는다.

## 기준 코드 복원과 단계별 결과

README/INTEGRATION_CONTRACT/TEAM_WORK_ASSIGNMENTS/DATASET_ISOLATION, AI 연구·매핑 설계·벤치마크, DB 회귀·개별 감사, 분류기 README/계약/규칙/테스트, ingest/batches/모듈 어댑터/0001~0008을 확인했다. 별도 retriever-eval README와 results/trichef_results.json, trichef_tradeoff.json을 확인했으며 외부 모델을 실행하지 않았다. API용 규칙 분류와 별도 문서·임베딩 연구를 구분했다. 새 기능 전 기존 API/mapper/transformer/BatchService/스키마 격리를 검색·재사용했다.

처음 실행한 전체 비DB 회귀는 **874 passed / 1 failed / 61 skipped**였다. 실패는 실제 분류기 200/HOLD를 501로 가정한 테스트였다. 테스트를 삭제하거나 실패를 skip으로 바꾸지 않고 현재 계약에 맞췄다.

1단계 최초 API/분류 모듈 검사는 309 passed. JSON·파일 실제 추천, HOLD, AVAILABLE=False의 501, 실행 예외·잘못된 출력의 500/민감값 비노출을 확인했다. 최종 보강으로 실행 내부 ImportError도 가짜 미구현으로 바꾸지 않고 500으로 처리한다.

2단계 최초 매핑/변환/대량 합성 검사는 34 passed. 분류 entity→기존 후보 생성, HOLD에서 명시적 사용자 선택, 수동 override 보존, 판매 원장→확인한 정책의 월수요 preview를 검증했다. CAPA/Routing은 보류하며 AI 호출이나 자동 매핑·승인을 추가하지 않았다.

3단계 서비스/HTTP/정적 스키마 검사는 최초 17+3 passed에서 다중 원본·대량 연결까지 확장했다. 원본 바이트와 SHA/선택 매핑/정책/전체 결과/지문을 불변 이력으로 저장하도록 PostgreSQL 코드를 작성했다. 620행 결과가 첫 500행으로 잘리지 않는지, 동일 입력 재사용, 다중 원본 취소/반품 분리, 실패 시 배치까지 롤백, 참조 snapshot 재현, 변조 차단, 데이터셋 UUID 격리, canonical 설정 고정, 기존 승인 digest 게이트를 **테스트 전용 메모리 저장소**로 확인했다. 이는 PostgreSQL 저장·잠금·트리거 동작 증명이 아니다.

## 최종 실행 결과

| 검사 | 이번 PC 실제 결과 |
| --- | --- |
| 전체 pytest --no-db | **906 passed / 0 failed / 63 skipped**, 19.43초 |
| 비DB Playwright shell/handoff | **8 passed**, 6.6초 |
| TypeScript type-check / Vite build | 통과 / 통과 |
| OpenAPI·JSON Schema·기존 응답 예시 동기화 | 전체 pytest에서 통과 |
| Alembic SQL 오프라인 생성·체인/모델 비교 | 전체 pytest에서 통과. 온라인 적용 아님 |
| pip check | No broken requirements found |
| 저장소 민감정보·원본 파일 검사 | findings=0 |
| Git diff --check | 통과 |

기존 DB 61개와 신규 실DB 이력 시험 2개를 합쳐 63개는 **접속 없이 제외**했다. 이들은 통과가 아니다. 기존 별도 DB fixture의 강제 초기화 조건과 URL/역할/sentinel 검사도 보존했다. 이번에 새로 skip 장식을 붙여 실패를 숨긴 테스트는 없다. pytest에서 Starlette/httpx deprecation warning 1건이 남으며 기존 고정 의존성은 바꾸지 않았다.

최신 UI에 맞춰 통합 담당 E2E의 메뉴 접근성 이름과 dataset query를 포함한 대역 URL을 수정했다. 실제 분류기 HOLD는 실제 서버로 검증하고, 계획 테스트의 대역은 계속 TEST-DOUBLE-ONLY로 표시한다. frontend/src나 알고리즘 파일을 수정해 테스트 결과를 맞추지 않았다.

보안 검사에서 기존 분류기 합성 연락처 생성기의 전부 0인 전화번호가 탐지됐다. 원본을 확인한 뒤 해당 파일/분류 사례의 all-zero 예시만 좁게 허용했다. 같은 줄의 다른 번호·다른 파일·실제 로컬 비밀값 검사는 유지한다. 분류기 담당 파일은 변경하지 않았다.

## 대량 합성 자료 재실행

이번 PC에서 생성기를 임시 경로로 실행해 새 합성 파일 5개(13,299,665 bytes)를 읽었다. 원본 86,214행 = 정상 83,984 + 취소 887 + 반품 1,343, 오류/집계 오류 0. 변환 결과는 498개 제품·월 행이며 생성기의 독립 기준 CSV와 제품/월/수량/단위가 모두 일치했다. 정상 수량 1,812,610과 결과 합계가 같았고 취소 11,240은 제외, 반품 8,670은 별도 보존했다. 반품을 정상 수요에서 차감하지 않았다.

확장 회귀는 이 전체 원본→변환 이력→기존 승인 전 배치→명시적 승인 서비스→498개 기준 결과 비교까지 **메모리 테스트 대역**에서 실행했다. 실제 승인 DB 데이터가 생성된 것은 아니다. 원본 파일 5개의 저장 바이트도 입력과 같음을 확인했다.

기존 benchmark_ingestion.py도 새 합성 자료로 실행했다. tracemalloc 포함 변환 17.38초, 최대 Python 추적 할당 20,220,350 bytes. 파일 읽기/실DB 저장/프로세스 RSS를 포함하지 않으며 회귀 검사와 동시 실행한 단일 측정이라 성능 개선 비교나 운영 성능 보장은 아니다. 정상 CSV 계약 9/9 및 오류 사례 6건도 기존 기대값과 같았다. 원본·성능 산출물·JUnit은 ignored .artifacts에만 남긴다.

## 남은 환경 검증과 담당자 인계

Alembic 0009의 온라인 적용, 실제 PostgreSQL 원자 롤백·지연 트리거·동시 제출·마스터 조회·새 데이터셋 생성은 **미검증**이다. test_db_ingestion_history.py에 실DB 회귀를 준비했지만 이번에 실행하지 않았다. 배포 전에 실제 대상·역할·격리/보존 조건을 확인해야 하며 전체 기존 회귀 fixture는 초기화를 포함하므로 별도 실행 승인이 필요하다. 기존 개발 DB나 chungpamo_test로 대체하지 않는다.

이번 npm audit는 기존 esbuild moderate와 Vite high, 총 2개 취약 패키지를 보고했다. 검사 종료 코드 1이며 **보안 무결점으로 주장하지 않는다**. frontend 담당 경로/고정 lockfile 제한에 따라 npm audit fix나 major upgrade를 실행하지 않았다. 나미에게 Vite/esbuild 업데이트·호환성·브라우저 회귀가 필요함을 인계한다. 이는 이번 코드가 새로 추가한 의존성이 아니다.

새 화면 연결은 [연계 계약](INGESTION_INTEGRATION_HISTORY.md)과 frontend_guide.md를 따른다. 특히 기존 클라이언트의 `/ingest/` unscoped 규칙을 새 영구 API에 사용하지 말고 선택 dataset_id를 명시해야 한다. 이력 저장 완료와 승인 완료, 변환 digest와 배치 digest를 구분한다. AI 후보 추천은 설계만 유지하며 이번 범위에서 도입하지 않았다.

기존 frontend/, modules/, migration 0001~0008 및 dataset_schema_v1.py의 diff는 0건이다. 새 스키마는 v2와 0009로 분리했고 변경 파일만 명시해 Commit한다. Git 운영은 main 직접 Commit·Push, 강제 Push/reset/clean 없음이다.
