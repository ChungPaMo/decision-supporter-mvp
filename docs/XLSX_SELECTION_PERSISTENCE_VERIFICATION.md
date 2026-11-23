# XLSX 선택 범위 저장 검증

2026-11-23 KST, 보조 PC. 시작 `main`은 [`423c456`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/423c456cf11d090866293c0812c78d6cd7bb81e2)다. [화면 인계](XLSX_SELECTION_PERSISTENCE_HANDOFF.md)

## 구현 및 보존 경계

- 미리보기와 `POST /ingest/transformations`는 선택 JSON을 같은 방식으로 검증한다. 원본 SHA, 정확한 시트 및 범위, 사용자 확정 정책, 데이터셋 및 승인 마스터 조건을 재계산하고 검토한 변환 지문과 대조한다. 선택은 파일별 입력 지문에 들어가며, 단일 선택과 동등한 인덱스 `0` 선택은 한 입력으로 식별된다.
- 원본 바이트와 SHA는 기존 `ingestion_transform_source`에, 선택·역할별 절대 열과 행 위치 예시는 기존 불변 `ingestion_transformation.manifest`에 저장한다. API는 raw 바이트 대신 검증된 원본 식별 정보와 좌표를 반환한다. 상세 재조회·정확한 재시도·배치 재검증·승인은 저장된 정책·자료·선택과 마스터 스냅샷으로 다시 계산해 근거를 대조한다. 정규 배치 CSV의 실제 bytes도 확인한다.
- 정상 정규 CSV, 승인 전 배치 및 원본/manifest는 기존 트랜잭션에 있다. 동일 입력은 기존 advisory lock 및 고유 지문을 사용한다. 다른 시트/범위는 서로 다른 입력이며, 정규 CSV가 같을 때는 기존 활성 배치 중복 방지 제약을 따른다. 이미 승인된 수요 키와 겹치면 기존 승인 게이트가 적용된다.
- 기존 JSONB에 선택을 보관하므로 새 migration과 기존 데이터 재작성은 필요 없다. 선택 생략 시 기존 응답과 지문을 유지한다. PostgreSQL의 0009 불변/지연 트리거, 로컬 FK와 기존 배치 정책을 사용한다. [기존 이력 근거](INGESTION_INTEGRATION_HISTORY.md) · [기존 PC의 0009 검증 기록](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md)

## 보조 PC에서 확인한 동작

TestClient와 기존 트랜잭션 메모리 대역으로 선택형 미리보기 → 201 저장 → 재조회 → canonical 재검증 → 명시적 배치 승인 → 월수요 조회를 확인했다. 저장 직후 승인 수요는 0행이었다. 200 재시도는 동일 이력과 최초 검토자를 반환했다. 같은 원본의 다른 시트·범위는 별도 지문으로 저장했으며 동일 정규 CSV인 경우 중복을 차단했다. CSV와 XLSX가 섞인 요청 및 선택 없는 XLSX도 검증했다.

원본의 비선택 영역이 변경된 경우를 포함한 SHA 불일치, 다른 범위와 오래된 지문, 숨긴 시트, 병합 헤더, 중복 헤더, 잘못된 범위·인덱스, 누락 매핑, 미확인 정책 및 행 오류를 차단했다. `HAS_ERRORS` 배치와 잘못된 배치 지문의 승인을 거부했다. 다른 데이터셋의 이력/배치를 조회할 수 없었다. 선택 좌표·절대 열의 변조는 manifest 지문을 다시 만들어도 재현 검증에서 드러났다. 저장 도중 오류를 주입하면 새 배치와 원본/이력이 롤백되고 이전 승인 수요·이력이 보존됐다.

훤님 합성 XLSX 200개 구조 회귀는 기본 헤더 **18/200**, 지정 헤더 **200/200**이었다. 평면 BOM 9개 지정 매핑 Top-1·Top-3는 각각 **9/27**, 파일 HOLD는 **9/9**로 동일했다. 원본·라벨 SHA를 대조했고 성능 평가용 파일을 저장 대상 대표 자료로 대체하지 않았다. [200개 비교 기준](XLSX_TABLE_SELECTION_VERIFICATION_20261123.md)

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest --no-db -q
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_classifier_xlsx.py --output .artifacts/classifier_xlsx_persistence_regression.json
```

전체 비DB pytest **1,164 passed / 0 failed / 67 skipped / 0 deselected**, 21.61초. RapidFuzz 48건 고정 평가셋 회귀와 OpenAPI·JSON Schema, 오프라인 SQL 생성 검사를 포함한다. Starlette/httpx 경고 1건이 있다. 67개 실DB 검사는 접속 차단으로 건너뛰었다. 실제 PostgreSQL 연결·마이그레이션 적용·DB 쓰기는 미실행이다. 브라우저 화면 연계는 인계 범위다.

변경 파일의 저장소 보안 검사 발견 0건, `pip check` 의존성 오류 0건이다. 전체 트리 검사에는 기존 합성 XLSX 200개와 생성기의 전화 형식 문자열 1건이 남아 있다.

## Docker가 있는 기존 개발 PC 확인 목록

다음 명령은 이 보조 PC에서 실행하지 않았다. 기존 개발 PC에서도 **별도 승인된 폐기 가능한 회귀 DB**에서만 실행한다. `.env.regression.local`의 명시적 대상, 전용 컨테이너/포트, 제한된 역할, sentinel, 예상 스키마·합성 자료를 기존 검증기로 확인한다. 이 실행기는 fixture 시작 시 그 회귀 DB의 제한된 스키마를 재생성한다. 데이터 보존이 필요한 DB에는 사용하지 않는다. [기존 승인·대상 식별 규칙](DEVELOPMENT_WORKFLOW.md)

```powershell
$env:CHUNGPAMO_ALLOW_TEST_DB_RESET = 'chungpamo_regression@127.0.0.1:55433'
try {
    .\.venv\Scripts\python.exe scripts/run_regression.py -q --tb=short backend/tests/test_db_ingestion_history.py
    if ($LASTEXITCODE) { throw 'XLSX history PostgreSQL regression failed' }
} finally {
    Remove-Item Env:CHUNGPAMO_ALLOW_TEST_DB_RESET
}
```

기대 결과는 관련 SQL pytest **3개 통과, 건너뜀 0개**다. 새 `test_postgres_selected_xlsx_history_replay_approval_and_rollback`은 0009 지연 제약을 강제로 확인하고, 기존 PostgreSQL 저장소에서 원본/절대 좌표 재조회, 재시도 ID 일치, 다른 시트의 별도 지문, 이력 UUID 격리, 승인 전 0행과 승인 후 1행, SQL insert 후 의도적 실패의 롤백을 검증한다. 데이터 변경은 fixture의 외부 트랜잭션이 롤백한다.

배포 전에는 기존 개발 DB와 대상 데이터셋이 revision `0009` 상태인지 읽기 전용으로 확인한다. 기존 이력 상세와 승인 배치·월수요의 건수 및 지문이 유지되는지 대조한다. 경쟁 요청의 두 세션 실행은 승인된 회귀 환경에서 동일 요청 201/200과 한 쌍의 이력·배치, 동일 출력 충돌의 무고아 상태를 추가 확인한다. 이번 보조 PC 결과는 PostgreSQL 트리거·잠금·실환경 검증을 포함하지 않는다.
