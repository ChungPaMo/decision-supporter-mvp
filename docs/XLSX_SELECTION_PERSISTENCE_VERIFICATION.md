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

## 기존 개발 PC의 PostgreSQL 검증 절차

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

## 2026-11-23 기존 개발 PC의 PostgreSQL 검증 결과

기준 `main`은 [`5507c0a`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/5507c0ab98d95db0a6780b56fff7c8a1f327283f)이다. 승인 범위인 회귀 DB `127.0.0.1:55433/chungpamo_regression`에서 `backend/tests/test_db_ingestion_history.py`만 한 번 실행했다. Docker `chungpamo-monorepo-db`의 PostgreSQL 16.6을 사용했다. 직전에 `chungpamo_regression_runner` 접속과 DB 소유권, 제한된 역할, 회귀 sentinel, 허용 스키마, 다른 접속 0개 및 보존 대상 업무 데이터 0건을 확인했다. fixture는 `public`과 `CHUNGPAMO-2027` 물리 스키마를 재생성하고 Alembic `0009`를 적용했다. 종료 후에도 두 스키마와 sentinel, `0009`를 확인했다. 회귀 DB에 업무 데이터나 임시 데이터셋은 남지 않았다.

| SQL 테스트 | 결과 | 확인한 동작 |
| --- | --- | --- |
| `test_postgres_history_sources_replay_approval_and_cross_dataset_isolation` | 통과 | 이력 재사용, 다른 데이터셋 접근 차단, 승인 전 월수요 0행 → 승인 후 2행, 이력·원본 불변 트리거와 지연 제약 |
| `test_postgres_new_dataset_provisions_history_tables_and_local_foreign_keys` | 통과 | 새 데이터셋에 이력 테이블 2개 생성, 외래 키가 로컬 테이블 또는 `public.dataset`을 참조, 검증용 데이터셋 롤백 |
| `test_postgres_selected_xlsx_history_replay_approval_and_rollback` | 통과 | 실제 FastAPI 응답, 선택 좌표·SHA·지문 보존, 승인 전 월수요 0행 → 승인 후 1행, 저장 실패 롤백 |

**3 passed / 0 failed / 0 skipped / 0 deselected**, 약 6.18초. 기존 Starlette/httpx 경고 1건. 선택형 XLSX 테스트에서 FastAPI `TestClient`의 의존성을 트랜잭션이 격리된 실제 SQL 저장소에 연결했다. `POST /ingest/transformations` 신규 저장은 `201`, 동일 요청 재시도는 `200`, `GET /ingest/transformations/{id}`는 `200`이었다. 세 응답의 이력·배치 ID와 본문이 같았고, 미리보기와 저장 응답의 `input_digest`·`result_digest`도 일치했다.

재조회에서 `January` 시트, 헤더 4행, 데이터 행 6~8·열 C~I, 수량 열 E, 원본 행 근거 6·8과 원본 SHA-256을 확인했다. 같은 원본의 `February` 시트는 원본 SHA-256을 공유하면서 다른 `input_digest`를 받았다. 명시적 배치 재검증·승인 뒤에만 선택 범위의 월수요 1행이 반영됐다. 실제 이력·원본 INSERT 뒤 오류를 주입했을 때 배치·원본·이력·이력 원본·월수요 5개 테이블의 건수와 기존 manifest 지문이 유지됐다.

개발 DB `chungpamo`는 읽기 전용으로 비교했다. 사전검사와 테스트 후의 **60개 테이블 데이터 지문, 735개 스키마 객체 지문, 660개 열·인덱스 정의 지문**이 모두 일치했다. Alembic은 전후 `0009`였다.

| 개발 데이터셋 | 승인 배치 | 월수요 | 예측 이력 | 변환 이력 / 변환 원본 |
| --- | ---: | ---: | ---: | ---: |
| `CHUNGPAMO-2027` | 9 | 498 | 1 | 0 / 0 |
| `TISSUE-LEGACY` | 7 | 24 | 1 | 0 / 0 |

사전·사후 비교와 JUnit 증거는 Git에서 제외된 로컬 `.artifacts/`에 보관한다. 다음 실DB 검증 범위는 동일 입력을 두 연결에서 동시에 저장하는 경우, 같은 시트의 범위 변경과 정규 CSV 충돌, 원본·선택 변조 반례다. 브라우저 E2E와 전체 SQL 회귀는 이번 실행 범위 밖이다. [화면 인계](XLSX_SELECTION_PERSISTENCE_HANDOFF.md)

## 2026-11-23 PostgreSQL 동시성·무결성 검증

기준 `main`은 [`c136793`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/c136793c8b974f8b9cd321bbbd9df98b99ba3597)이다. 별도 1회 승인 후 `127.0.0.1:55433/chungpamo_regression`을 새로 검사했다. `chungpamo_regression_runner` 역할·DB 소유권, sentinel, 승인된 두 스키마, 기준 데이터 외 0행과 다른 세션 0개가 모두 일치했다. `public`과 `CHUNGPAMO-2027`만 재생성하고 Alembic `0009`를 적용했다. 실제 FastAPI `TestClient`와 PostgreSQL 16.6에서 실행한 pytest는 **0 passed / 1 failed / 0 skipped / 0 deselected**, 5.18초다. 단일 테스트가 여섯 항목을 검사했으며 마지막 응답 코드 단언에서 실패했다.

| 검증 항목 | 결과 | 실측 |
| --- | --- | --- |
| 동일 파일·동일 선택 동시 저장 | 성공 | 독립 PostgreSQL 세션 두 개에서 `201` 한 건, `200` 한 건. 이력·배치 ID와 응답 본문이 같았다. |
| 같은 시트의 선택 범위별 입력 지문 | 성공 | `January`의 `C6:I6`, `C6:I8`, `C6:I9`가 각각 다른 `input_digest`를 받았다. 최초 두 범위의 이력과 좌표를 재조회했다. |
| 서로 다른 입력의 동일 정규 CSV 등록 | DB 차단 성공, 동시 HTTP 계약 실패 | `C6:I8`과 `C6:I9`의 정규 CSV 바이트가 같았다. 앞 요청 `201` 후 재시도는 `409 DUPLICATE_UPLOAD`. 두 요청이 경합했을 때 앞 요청은 `201`, 뒤 요청은 기대 `409` 대신 `500 PERSISTENCE_ERROR`. |
| 원본 SHA·선택·매핑·변환 지문 변조 | 성공 | SHA 변경은 `409 XLSX_SOURCE_CHANGED`. 선택 범위 또는 유효한 매핑을 바꾸거나 제출 지문을 바꾸면 각각 `409 RESULT_CHANGED`. 존재하지 않는 매핑은 `422 TRANSFORM_MAPPING_HOLD`. 각 요청 뒤 5개 테이블의 행 수와 내용 지문이 같았다. |
| PostgreSQL 잠금·고유 제약 | 성공 | 실제 `pg_locks`와 `pg_blocking_pids()`에서 동일 입력은 `advisory`, 동일 CSV는 `transactionid` 대기를 관측했다. CSV 충돌은 `23505`와 `import_batch_entity_source_sha256_idx`로 확인했다. |
| 중간 SQL 오류·고아 데이터 방지 | 성공 | 배치·배치 파일·이력·XLSX 원본 INSERT를 확인한 뒤 원본 행을 중복 삽입했다. `23505` 기본 키 위반이 `500 PERSISTENCE_ERROR`로 반환됐고, 5개 테이블의 행 수와 내용 지문이 유지됐다. |

| 시점 | 배치 | 배치 원본 | 변환 이력 | 변환 원본 | 월수요 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 동일 입력 동시 저장 후 | 2 | 2 | 1 | 1 | 0 |
| 다른 범위 저장·CSV 충돌 후 및 변조·실패 후 | 3 | 3 | 2 | 2 | 0 |
| 승인된 정리 후 | 0 | 0 | 0 | 0 | 0 |

배치와 배치 원본에는 합성 제품 마스터 검증용 1건이 포함된다. 각 성공 이력에서 API와 SQL의 입력·결과·manifest·정규 CSV 지문이 모두 일치했다. `January` 헤더 4행, 수량 열 E 및 XLSX 원본 바이트와 SHA-256 `24c4001aba464e91e31a0a15770ac38418023f3b7303a763d0c2d56a3ff4e8da`도 확인했다. 실측 `input_digest`는 `C6:I6`이 `7e5948fe1a3644b9ca2d9d70ac3110320a0c053c8645f141cc334f597a5bfcbc`, `C6:I8`이 `b40d6163ead245f535cd003efec0db78699eb42951e08de10bd9effc957b244d`, 중복 차단된 `C6:I9`가 `43c1a279d69902bbd08418fa9019bb3053b5b9856163b0e1cc8f16be66e9ff58`이다. `C6:I8`과 `C6:I9`의 정규 CSV SHA-256은 `5b91a773e461c87a625bbcd82c2baf2e889ecaf16ad742342f92e7afa3b648a5`였다.

오류의 원인은 `SqlBatchRepository.transaction()`이 `uq_batch_live_entity_sha`만 중복으로 분류하는 데 있다. 데이터셋의 `LIKE … INCLUDING ALL` 경로에서는 같은 인덱스가 `import_batch_entity_source_sha256_idx`로 생성된다. 이 이름의 `23505`는 일반 저장 오류가 된다. 후속 변경은 두 인덱스의 중복만 `409 DUPLICATE_UPLOAD`로 매핑하고, 다른 고유 제약과 저장 오류의 처리를 보존해야 한다. [SQL 저장소](../backend/app/batches/sql_repository.py) · [데이터셋 스키마 생성](../backend/app/dataset_schema_v1.py)

정리는 `CHUNGPAMO-2027`의 승인된 21개 테이블을 명시한 `TRUNCATE … RESTRICT`로 완료했다. 회귀 DB의 두 스키마, sentinel, revision `0009`, 초기 기준 행과 업무 데이터 0행을 다시 확인했다. 개발 DB `chungpamo`는 사전·사후 **60개 테이블, 735개 스키마 객체, 660개 열·인덱스 정의 지문** 및 승인 배치·월수요·예측·변환 건수가 일치했다.

실행 근거와 재현 코드는 Git에서 제외된 로컬 `.artifacts/xlsx-concurrency-20261123/`에 보관한다. JUnit의 SHA-256은 `5cf03b092fc58944c741d0833b1a25b92f18a55783b2fa6f8e38a6eb8f9480c0`이다. API 오류 수정·승인된 새 SQL 검증과 브라우저 E2E는 후속이다.

## 2026-11-23 중복 오류 매핑 수정과 재검증 범위

기준 `main`은 [`b9bf235`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/b9bf2357fd9f6c273ca0088b2307a4fa5709925c)이다. SQL 저장소는 드라이버의 SQLSTATE `23505`, 현재 데이터셋의 물리 스키마, 테이블 `import_batch`, 그 스키마의 활성 배치 고유 인덱스 이름이 모두 일치할 때 기존 `409 DUPLICATE_UPLOAD`를 반환한다. `public`의 `uq_batch_live_entity_sha`와 데이터셋 스키마의 `import_batch_entity_source_sha256_idx`는 `(entity, source_sha256)`에 걸린 같은 조건부 고유 인덱스다. 다른 고유 제약·FK·CHECK·트리거 오류 및 연결 장애의 기존 처리를 유지한다. 마이그레이션과 OpenAPI 변경은 없다. [SQL 저장소](../backend/app/batches/sql_repository.py) · [비DB 회귀 테스트](../backend/tests/test_sql_batch_error_mapping.py)

기존 개발 PC의 읽기 전용 사전검사에서 두 인덱스의 정의, `127.0.0.1:55433/chungpamo_regression`, `chungpamo_regression_runner`, sentinel, Alembic `0009`, 대상 스키마, 업무 데이터 0행과 다른 세션 0개를 확인했다. 개발 DB의 테이블 60개·객체 735개·열 및 인덱스 정의 660개 지문은 직전 기록과 같았다. 코드 수정 후 실제 PostgreSQL 쓰기·동시성 테스트는 미실행이다.

새 1회 승인 범위는 회귀 DB의 `public`·`CHUNGPAMO-2027` 재생성, Alembic `0009`, 기존 동시성 테스트에 필요한 합성 INSERT·COMMIT, 같은 데이터셋의 사전 확인된 21개 테이블 정리다. 동일 입력은 `201`/`200`으로 이력·배치를 한 쌍만 남기고, 서로 다른 범위의 동일 정규 CSV 경합은 `201`/`409 DUPLICATE_UPLOAD`로 끝나야 한다. 변조 거부, 중간 오류 롤백, 고아 데이터 0행, 정리 후 업무 데이터 0행, 개발 DB의 사전·사후 지문 일치도 확인한다.

## 2026-11-23 수정 후 PostgreSQL 동시성 재검증

별도 승인으로 [`872492b`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/872492bdd6fdb4f1005e4f1533716f58444be68a)의 PostgreSQL 회귀를 한 번 실행했다. 직전에 `127.0.0.1:55433/chungpamo_regression`, `chungpamo_regression_runner`, sentinel, `public`·`CHUNGPAMO-2027` 스키마, 다른 세션 0개와 업무 데이터 0행을 확인했다. 두 스키마를 한 번 재생성하고 Alembic `0009`를 적용했다. FastAPI `TestClient`와 PostgreSQL 16.6의 `test_xlsx_selection_concurrency_and_integrity`는 **1 passed / 0 failed / 0 skipped / 0 deselected**, 5.67초였다.

| 검증 항목 | 실측 결과 |
| --- | --- |
| 동일 XLSX·동일 범위 경쟁 | `201`과 `200` 각 1건. 두 연결 사이 advisory lock 대기를 관측했고, 배치·이력 ID와 두 응답 본문이 같았다. |
| 서로 다른 선택이 생성한 동일 정규 CSV 경쟁 | `201`과 `409 DUPLICATE_UPLOAD` 각 1건. `transactionid` 대기 후 PostgreSQL이 `import_batch_entity_source_sha256_idx`에서 `23505`를 반환했다. |
| 먼저 커밋된 동일 CSV 재등록 | `409 DUPLICATE_UPLOAD`. 후발 배치와 이력은 생성되지 않았다. |
| 관련 없는 고유 제약과 일반 SQL 오류 | 원본 이력 기본 키의 `23505`와 나눗셈 오류 `22012` 모두 `500 PERSISTENCE_ERROR`. 두 오류는 실제 INSERT가 발생한 뒤 주입했다. |
| 롤백과 고아 데이터 | 두 오류 전후 배치 3행, 배치 원본 3행, 변환 이력 2행, XLSX 원본 2행, 월수요 0행이었다. 5개 테이블의 내용 지문이 일치했고 연결이 끊긴 배치·배치 원본·이력·XLSX 원본은 각각 0행이었다. 배치 수에는 합성 제품 마스터 1행이 포함된다. |
| 지문과 선택 보존 | `January` 헤더 4행, 데이터 범위 `C6:I6`·`C6:I8`, 수량 열 `E` 및 원본 바이트와 SHA-256이 일치했다. 세 범위(`C6:I9` 포함)의 입력 지문은 서로 달랐다. 두 저장 이력의 입력·결과·manifest·정규 CSV 지문이 API와 SQL에서 일치했다. |

원본·좌표·매핑·결과 지문 변조도 기존 `409` 또는 `422`로 거부됐다. 종료 시 승인된 21개 테이블만 `TRUNCATE … RESTRICT`로 정리한 뒤 회귀 DB 업무 데이터 0행, sentinel과 Alembic `0009`를 읽기 전용으로 재확인했다. 개발 DB `chungpamo`의 **60개 테이블·735개 스키마 객체·660개 열 및 인덱스 정의 지문**과 주요 데이터 건수가 사전 기록과 모두 일치했다. SQL 범위에서 추가 결함은 발견되지 않았다. 브라우저 E2E는 미실행이다.

재현 코드와 실행 근거는 Git에서 제외한 로컬 `.artifacts/xlsx-concurrency-recheck-20261123/`에 보관한다. JUnit SHA-256은 `5e089963dbb2b078cbf5c8b116b208f2acf4c8dc7d66b456251ff27fd9c8ecc7`이다.

## 2026-11-23 실제 브라우저 읽기 전용 검증

시작 `main`은 [`741b6dc`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/741b6dc4a7f80acd633b70ca01e2a0c0f3b3adff)이며, 계획 엔진 팀원 변경을 fast-forward한 [`2adab58`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/2adab58debdce885f34cc0e93010f0f82b0359a2)에서 같은 결과를 확인했다. Edge `158.0.4370.33`·Playwright, Vite·React, 실제 FastAPI·PostgreSQL 16.6/Alembic `0009`로 읽기 전용 시나리오 **5개 통과, 실패 0개**였다. TypeScript 타입 검사도 통과했다. API를 `127.0.0.1:8091`, UI를 `127.0.0.1:5191`에서 임시 실행했다. 개발 DB 연결에는 `default_transaction_read_only=on`을 강제했고 검사 서버의 HTTP 가드가 저장·재검증·승인 경로를 차단했다. 실API 응답은 Playwright에서 대체하지 않았다. `#scenario/2`는 별도 합성 화면으로 표시됐고 API 호출은 0건이었다.

| 단계 | 상태 | 확인 근거 |
| --- | --- | --- |
| 1. XLSX 파일 업로드 | 정상 연동 | 실제 브라우저에서 합성 XLSX를 선택하고 분류·구조·미리보기 API에 multipart로 전송했다. 영구 등록은 6단계에서 판정한다. |
| 2. 유형 추천·HOLD | 정상 연동 | `/classifications/file` `200`. 표준 제품 파일은 `product` 추천. 제목이 있는 판매 원장은 범위 선택 전 `UNKNOWN`, 선택 후 `NEEDS_TRANSFORM`을 화면에 보였다. |
| 3. 시트·헤더·범위 | 부분 연동 | `/ingest/xlsx-layout` `200`, 숨김 시트 선택 차단, `January` 헤더 4행·`C6:I8` 적용 및 분류 요청 반영을 확인했다. HOLD에서 판매 원장 변환으로 이동하면 대상 화면의 파일 입력은 비어 있어 파일과 범위를 다시 선택해야 했다. |
| 4. 컬럼 후보와 수동 수정 | 부분 연동 | 표준 등록의 `/ingest/profile`·`/ingest/classified-mapping`·`/ingest/mapping-suggestions`는 모두 `200`. 수동 선택 `product_id ← product_id`가 재확인 요청에 들어갔다. 판매 원장은 `/ingest/profile` 헤더 목록과 수동 입력을 제공한다. **판매 원장의 정책 열 후보 또는 기존 후보 이관은 미연동**이다. |
| 5. 변환 미리보기와 오류 | 정상 연동 | 기본 수량 열 이름 불일치는 `422 TRANSFORM_MAPPING_HOLD`; 수량을 원본 `E` 열에 수동 지정하고 10행까지 포함하면 `200 HAS_ERRORS`로 `E10`을 표시하고 저장을 비활성화했다. 8행까지로 다시 선택하면 `200 TRANSFORMED_PREVIEW`, 정상 월수요 1행·수량 14, `persisted=false`였다. |
| 6. 선택형 변환 이력 저장 | 부분 연동 | 클릭 시 실제 `POST /ingest/transformations` 요청에서 데이터셋·선택 좌표와 SHA·수동 매핑·미리보기 지문을 확인했다. 검증 가드 `403 UI_CHECK_READ_ONLY`를 화면에 표시했다. `201`/`200` 저장 성공과 재조회는 미실행이다. |
| 7. 저장 배치 재조회·재검증 | 부분 연동 | 기존 배치의 목록·상세와 변환 이력 목록을 실제 API `200`으로 확인했다. 개발 DB에 변환 이력은 0건이었다. 신규 이력 상세·연결 배치의 `revalidate` 실행은 미검증이다. |
| 8. 별도 승인 | 부분 연동 | `BatchPanel`의 명시적 승인과 배치 지문 전달을 코드에서 확인했다. 실제 승인 전 배치에 대한 버튼 동작·서버 응답은 미실행이다. |
| 9. DB 월수요 반영 | 부분 연동 | 기존 승인 수요 `/demand/monthly` `200`, 총 498행과 화면의 상위 100행 조회를 확인했다. 새 XLSX의 승인 전후 행 수는 미검증이다. |

### 담당별 후속 작업

- **정마나미** — HOLD에서 판매 원장 변환으로 이동할 때 같은 `File`과 선택 범위를 전달한다. 판매 원장의 정책 열과 표준 월수요의 컬럼 후보를 구분하고, 헤더 목록과 수동 입력밖에 없는 현재 경로의 안내를 명확히 한다. 필요하다면 계약을 합의해 판매 원장 정책 열 후보를 연결한다.
- **김대영** — 이번 읽기 범위에서 백엔드 결함은 발견되지 않았다. 기존 `run_postgres_e2e.py`에는 두 차례 스키마 재생성과 별도 등록·예측 시나리오가 있으므로, 이번 XLSX 흐름에는 단일 전용 실행기로 범위를 좁힌다. 합성 제품·자재 승인 후 XLSX 변환 `201`/재시도 `200`, 이력·배치 상세, `revalidate` 버전 증가, 별도 승인, 수요 `0→1`과 화면 재조회·새로고침을 검증한다. `revalidate`는 버전을, 승인 요청은 배치 상세의 `result_digest`를 사용한다.

회귀 DB는 읽기 전용 사전검사에서 `127.0.0.1:55433/chungpamo_regression`, `chungpamo_regression_runner`, sentinel, `0009`, 예상 두 스키마, 다른 연결 0개, 초기 기준 데이터 외 0행이었다. 정식 E2E는 이 상태를 다시 확인하고 **스키마 재생성 없이**, `CHUNGPAMO-2027`의 합성 제품·자재 및 XLSX 저장·재검증·승인, 종료 시 사전 확인한 의존 테이블 21개 정리만 별도 승인받아 실행할 수 있다. 이번 실행에서는 개발 DB 60개 테이블·735개 객체·660개 정의 지문과 회귀 DB 상태가 전후 일치했다. 테스트 코드·API 관찰·비교 자료는 Git에서 제외한 `.artifacts/xlsx-browser-readonly-20261123/`에 보관한다. [화면 인계](XLSX_SELECTION_PERSISTENCE_HANDOFF.md)

## 2026-11-23 실제 브라우저 쓰기 E2E

별도 승인으로 [`1fee108`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/1fee1084385ebcbaccc2ce13f416649dd8279004)에서 Edge `158.0.4370.33`·Playwright → Vite·React → 실제 FastAPI → PostgreSQL 16.6 쓰기 시나리오를 **1회 실행해 통과**했다. 시작 직전에 `127.0.0.1:55433/chungpamo_regression`의 역할 `chungpamo_regression_runner`, sentinel, Alembic `0009`, `public`과 `CHUNGPAMO-2027` 스키마, 업무 데이터와 다른 세션 각각 0건을 확인했다. 이번 전용 실행기는 스키마 재생성이나 마이그레이션을 실행하지 않았다. 합성 API 응답 없이 브라우저 원본 조작으로 아래 단계를 확인했다.

| 브라우저 조작 | 실측 결과 |
| --- | --- |
| 제품·자재 등록과 명시적 승인 | 제품·자재 각각 등록 `201`, 승인 `200`, 각 1행 반영. |
| XLSX 업로드와 유형 추천 | 분류 `200`. 선택 전 `UNKNOWN` HOLD, 범위 설정 후 `NEEDS_TRANSFORM` HOLD. |
| 시트·헤더·범위 선택 및 수동 매핑 | 구조 조회 `200`. `January` 헤더 4행, `C6:I8`, 수량 열 `E`. 6·8행이 포함되고 범위 밖 오류 행은 제외됐다. |
| 정책 확인 및 변환 미리보기 | `200 TRANSFORMED_PREVIEW`. 월수요 미리보기 1행·14 EA, `persisted=false`. |
| 변환 신규 저장 | `201`, 연결 배치는 `READY_FOR_APPROVAL`. 저장 요청에 선택 좌표·원본 SHA·수동 매핑·미리보기 지문이 일치했다. |
| 같은 입력 재시도 | 화면에서 같은 선택으로 다시 미리보기와 저장을 눌러 `200`을 받았다. 이력·배치 ID와 지문이 같고, 이력 1행·총 배치 3행이었다. |
| 이력·연결 배치 재조회 | 화면의 이력 새로고침·상세·배치 검토가 모두 `200`. 배치 버전 `1`, 선택 범위와 원본 SHA 유지. |
| 재검증 | 서버 재검증 `200`, 버전 `1→2`. 요청은 `expected_version=1`, 빈 열 매핑, `default_unit=null`, `sheet=null`이었다. |
| 별도 승인과 월수요 조회 | 승인 버튼으로 `200`, `APPROVED`, 버전 `2→3`. 승인 지문은 배치 상세에서 가져왔다. 화면 승인 목록에 `UI-E2E-P1`, `2090-01`, `14 EA` 1행이 표시됐다. |
| 화면 새로고침 | `/demand/monthly` 및 변환 이력 상세 `200`. 같은 배치의 1행과 이력의 `APPROVED` 상태를 다시 표시했다. |

별도 API 조회에서 월수요는 최초·변환 저장 직후·재검증 후 각각 0행, 승인 후 1행이었다. 브라우저 종료 뒤 독립 SQL 조회에서 제품·자재·월수요 각 1행, 배치·배치 원본 각 3행, 변환 이력·XLSX 원본 각 1행을 확인했다. SQL의 승인 수요 뷰에서도 `UI-E2E-P1 / 2090-01 / 14.0000 EA` 1행이었다. 행 수와 아래 ID·지문 및 선택 범위를 대조했다.

| 저장 근거 | 값 |
| --- | --- |
| 변환 이력 ID | `2b45336b-a4bf-4c88-99da-d5859c6316ae` |
| 월수요 배치 ID | `d0e2f903-2acc-4e9b-a8a6-170cb8e7bf8d` |
| XLSX 원본 SHA-256 | `96839c665311d8b76bc4012cb74e7ff1372ca92fe15af9b2bb254b353e58552a` |
| 입력 지문 | `66cbde62fc625ca6584f757a0f11e368fb7be06fe70fea1fd7122afdf76725d5` |
| 변환 결과 지문 | `96a76ddf81b54edf02503e57d7bd6f288dd25917808ad81169e5a8845c79eaa3` |
| 변환 manifest 지문 | `284ffae7227c1a265788b351eb2aeddd5f8e4a2251a5881b768df1b893ad5cc0` |
| 정규 CSV SHA-256 | `7060dbe9fa8029fab0adb12be636e789979d1beaad2e639215e181d5c6258a33` |
| 승인에 사용한 배치 결과 지문 | `2c9cc969adebace8b9346de723c8eb773d134c6c5d65d562c4d4cd8aa05d64e9` |

정리는 승인된 `CHUNGPAMO-2027`의 21개 테이블만 `TRUNCATE … RESTRICT`로 수행했다. 회귀 DB는 업무 데이터 0행, 다른 세션 0개, sentinel 정상, Alembic `0009`로 사전 상태와 일치했다. 개발 DB는 읽기 전용으로 **60개 테이블·735개 스키마 객체·660개 열 및 인덱스 정의 지문**과 주요 건수의 전후 일치를 확인했다. 재현 도구, 브라우저 응답과 SQL 근거는 Git에서 제외한 로컬 `.artifacts/xlsx-browser-write-20261123/`에 보관한다.

- **정마나미** — HOLD 화면에서 판매 원장 변환으로 이동하면 파일과 범위를 다시 선택해야 하는 문제가 재현됐다. 파일·선택 이관은 후속 화면 작업이다.
- **김대영** — 승인 범위의 백엔드 결함은 발견되지 않았다. 같은 입력 저장은 두 번째 클릭 전 미리보기를 다시 실행했으며, 실제 `200` 재사용과 DB 중복 0건을 확인했다.
