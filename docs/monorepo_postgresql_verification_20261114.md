# 모노레포 전용 PostgreSQL 통합 검증 — 2026-11-14

## 승인 범위와 격리

사용자가 **기존 DB와 분리한 새 프로젝트 생성** 및 **새 chungpamo_test DB public 스키마만 초기화**하도록 명시적으로 승인했다. 개발 DB 초기화, 기존 55432 충파모 및 sisicallcall DB 접속/변경, 기존 볼륨 삭제는 허용되지 않았으며 수행하지 않았다.

최초 Docker 엔진 연결 불가에서는 작업을 중단했다. 사용자 엔진 실행 후 다음을 다시 검사했다.

| 항목 | 실제 확인값 |
|---|---|
| Engine / PostgreSQL | Docker 29.4.0 / postgres:16.6 |
| Compose 프로젝트 | chungpamo-monorepo |
| 컨테이너 | chungpamo-monorepo-db · healthy |
| 호스트 포트 | 127.0.0.1:55433 → 컨테이너 5432 |
| 볼륨 | chungpamo-monorepo-pgdata |
| 네트워크 | chungpamo-monorepo-net |
| 개발 DB | 새 서버의 chungpamo · 빈 public 스키마 유지 |
| 테스트 DB | 새 서버의 chungpamo_test · 최종 revision 0005 |
| 앱 역할 | chungpamo_app · superuser/createdb/createrole 모두 false |

시작 전 위 신규 이름의 자원과 55433 리스너가 없었다. 임의 개발 비밀번호로 새 루트 .env를 생성했고 Git ignore를 확인했다. 기존 .env·DB·볼륨은 재사용하지 않았다. Compose config를 비밀값을 출력하지 않는 --quiet로 검증한 뒤 새 db 서비스만 생성했다.

각 초기화 전에 승인 토큰, URL의 driver/host/port/user/DB, 실제 current_database, 컨테이너 프로젝트/health/포트/볼륨/네트워크, 예상 스키마·테이블, 기존 배치의 SYNTHETIC 출처를 검사한다. 초기화 직전 연결에서도 current_database가 chungpamo_test임을 확인한다. 같은 DB 이름을 쓰더라도 기존 55432와 새 55433은 다른 서버·저장 볼륨이다.

## 실제 실행 결과

```powershell
$env:CHUNGPAMO_ALLOW_TEST_DB_RESET='chungpamo_test@127.0.0.1:55433'
./.venv/Scripts/python.exe -m scripts.verify_test_db
./.venv/Scripts/python.exe -m pytest -q --tb=short
# 490 passed / 0 failed / 0 skipped (26.75s)
./.venv/Scripts/python.exe tests/e2e/run_postgres_e2e.py
# 최종 실행: 기존 회귀 7 + API 재시작 복원 1 + 독립 휴지 1 = 9 passed
```

- 테스트 DB에서 0001→0002→0003→0004→0005 적용. 빈 테스트 DB의 0005→0001→0002→0003→0004→0005 왕복과 0005의 legacy 결과 보존·이력 존재 시 downgrade 차단 시험 통과.
- 기존에 건너뛴 PostgreSQL 필수 55개 실제 실행. 승인 트리거·상태 전이·원본 append-only·행 수 확인·잘못된 참조 차단·트랜잭션 롤백·BOM 유효기간 겹침·동시 승인 충돌을 검증했다.
- 승인 수요만 조회, 실행 UUID·입력 digest·모델 버전·출처 저장, 중복 실행·실패 재시도·동시 충돌·DB 저장 실패 롤백을 검증했다.
- 브라우저에서 CSV/XLSX→매핑 HOLD→재검증→승인/반려→실제 조회, 409/422/501/503/네트워크 오류, 부분 성공·이력 부족·INPUT_INVALID/run=null, 새로고침·API 프로세스 재시작 후 복원 통과.
- 비DB UI 경계/모바일 브라우저 시험 3개 별도 통과. 브라우저 총 12개다. TypeScript·프로덕션 빌드도 재실행해 통과했다.
- Starlette/httpx 사용 중단 예정 경고 1건과 Node 색상 환경 경고는 남았다. 테스트 실패·skip은 최종 실행에 없다. 원격 CI 통과를 주장하는 수치는 아니다.

## 발견한 시험 준비 오류와 수정

첫 브라우저 시도에서 기존 7개 통과, 신규 휴지 시나리오 1개 실패가 발생했다. 이력 조회가 이전 음성 시험의 최소 이력 120개월을 폼에 복원했는데, 휴지 시나리오가 24개월 데이터에 맞는 최소 12개월을 지정하지 않았다. 엔진은 TP-10R을 정상적으로 제외했다. 입력 조건을 생략한 테스트 결함이며 예측 계산 결함이 아니다.

휴지 시험에서 기준일·기간·P50 방식·최소 이력·시드를 모두 명시했다. 결과 존재·제품·월·저장/차트/복원 assertion을 유지하고 입력 24행/예측 1행도 확인한다. 추가로 기존 회귀 시험과 데이터·학습 이력이 섞이지 않도록 기존 7개→재시작 복원 1개 후 테스트 API를 종료하고, **같은 승인된 테스트 DB만** 다시 검증·재생성한 뒤 휴지 1종을 실행한다. 시험을 삭제·skip하거나 예상 결과를 완화하지 않았다.

## 휴지 1종 실제 결과

최종 테스트 DB의 제품은 TP-10R 하나이며 승인된 월별 수요는 2025~2026년 24행이다. 제품→자재→BOM→재고→수요의 다섯 배치는 모두 SYNTHETIC/APPROVED다. MA12, 기준일 2026-12-31, 기간 1개월, 최소 이력 12, seed 42로 실행했다.

| 대상 월 | P50 | P80 | P90 | 실행 |
|---|---:|---:|---:|---|
| 2027-01 | 9933.3333 | 10629.8146 | 11645.9477 | OK · 입력 24행 · 예측 1행 |

수량 단위 EA는 이 합성 제품에서 화장지 10롤 1팩을 의미한다. 소수 예측값은 실제 엔진의 수요 추정이며 정수 생산계획이 아니다. 이 값이 PPT의 고정 설명값과 같다고 가정하지 않는다. 원본 승인→예측 저장→React 차트/표→새로고침 복원까지 실제로 확인했다. MPS 이후의 생산계획 계산은 여전히 미구현이다.

## 종료 확인과 남은 범위

- 신규 개발 DB의 public 테이블 목록은 시작과 종료 모두 빈 배열이다. 개발 DB 초기화·마이그레이션·업무 데이터 변경 없음. 새 개발 DB로 앱의 저장 기능을 쓰려면 별도로 README의 정상 migration 절차가 필요하다.
- 최종 테스트 DB revision은 0005이며 합성 승인/예측 자료를 남겼다. 전용 DB 컨테이너는 healthy로 유지했다. E2E가 시작한 API·Vite 프로세스는 종료했다.
- 기존 컨테이너 ID, 기존 볼륨 이름·네트워크 ID는 유지됐다. 기존 DB 접속, 서비스 변경, down -v/prune/volume rm은 수행하지 않았다.
- .env·비밀값·브라우저 로그/trace/스크린샷은 Git에 포함하지 않는다. 보안 검사와 소스 저장소 보존 검사를 다시 수행한다.
- 자동 분류, CAPA·라우팅 등록/승인, MPS/RCCP/MRP/What-if 계산, 정식 계획 저장·승인·출력은 담당자 구현 대상이다. 전체 제조 E2E가 완료됐다고 표현하지 않는다.
