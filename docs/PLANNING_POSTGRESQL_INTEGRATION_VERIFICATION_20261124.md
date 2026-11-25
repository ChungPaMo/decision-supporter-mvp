# 생산계획 실제 PostgreSQL 검증과 C02 승인 입고 설계

2026-11-24 KST · 메인 Windows PC · 김대영 · 기준 [91927a0](https://github.com/ChungPaMo/decision-supporter-mvp/commit/91927a0d568962526c896de518e4d3a01cd7b0ec)

2026-11-24 후속 작업은 [c4cb3c5](https://github.com/ChungPaMo/decision-supporter-mvp/commit/c4cb3c519e4dc205f2e74f1f2196b0fbd91a75f4)에서 시작했다. P0 증거를 보존했고 P1 승인 단일 실DB 테스트를 완료했다. P2 원장·승인 흐름·SQL reader·`0010` 파일을 작성했다. `0010` 실제 적용과 합성 입고 DB 등록은 미실행이다.

## P0 · 개발 DB 읽기 전용 실측

Docker Engine 29.4.0의 `chungpamo-monorepo-db`는 `healthy`였다. Compose 프로젝트는 `chungpamo-monorepo`, 호스트 바인딩은 `127.0.0.1:55433`, 전용 볼륨은 `chungpamo-monorepo-pgdata`였다. PostgreSQL 16.6의 `chungpamo`에 `chungpamo_app`으로 연결했다. 첫 연결부터 `default_transaction_read_only=on`을 적용했고 실제 `transaction_read_only=on` 및 Alembic `0009`를 확인했다.

`scripts/verify_readonly_dataset_api.py`가 실제 FastAPI TestClient와 SQL provider, `AVAILABLE=True`의 실제 계획 엔진을 호출했다. 서버 대역은 연결 설정에만 사용했으며 입력 데이터와 엔진은 실제 경로를 탔다. 첫 실행에서 검증 스크립트의 로컬 변수 `preview`가 교차 Routing 검증 함수 이름을 가리는 오류를 확인했다. 변수 이름을 고쳤고, 동일 읽기 전용 검증으로 교차 참조를 포함한 **7개 검사**를 모두 통과했다. 출력 위치를 새 비공개 경로로 지정해 이전 증거를 보존했다. [검증 실행기](../scripts/verify_readonly_dataset_api.py)

| 대상 | 입력 진단 | 실행 미리보기 | 저장 상태 |
| --- | --- | --- | --- |
| CHUNGPAMO-2027, 2027-01~03 | `POST /planning-inputs/preview` → 200, `MULTI_MONTH`, `NEEDS_REVIEW` | `POST /plans` → 200, 계산 `OK` | `persisted=false`, 이력 0→0 |
| TISSUE-LEGACY, 2027-01 | 200, 단일 월 | 200, 계산 `OK` | `persisted=false`, 이력 0→0 |

공식 데이터셋의 기존 승인 예측에서 제품 9개와 제품·월별 예측 27행을 제공했다. 제품·자재 각 9행, BOM 헤더 9건, 재고 18행(2026-12-31), CAPA 자원 6개·수량 한도 3행·시간 예산 18행, Routing 27단계를 읽었다. BOM 9건과 Routing 27단계의 버전은 모두 `V1`이고 측정 기간에 유효했다. 버전이 기간 중 바뀌지 않아 이번 출력에는 `*_VERSION_SELECTED` 전환 근거가 생성되지 않았다. 승인 출처 9건은 제품·자재·BOM·재고·월수요·Routing 각 1건과 CAPA 3건이며, 각 배치의 승인 버전·원본 SHA·결과 digest·승인시각을 스냅샷에서 확인했다.

- 계획 입력 digest는 진단·실행·별도 SQL 스냅샷에서 동일한 `sha256:8bcf1369096d4a02644d822e5929c30d45c8e8dd159936392c44a50f895970e7`이었다.
- Preview 응답의 `result`를 영구 저장과 동일한 정규화 함수로 해시한 계산 digest는 `sha256:757dd64ea5f3804e6d894ec0b97e6f5f6d2632d059068bf35b67564c93eb1b5f`였다. 이는 로컬로 산출한 값이다. 현재 Preview API는 계산 digest를 별도 필드로 반환하지 않는다.
- 개발 DB의 테이블 60개·객체 735개·컬럼 및 인덱스 정의 660개 지문은 실행 전후와 직전 보존 실측 모두 일치했다. CHUNGPAMO-2027/TISSUE-LEGACY 승인 9/7건, 월수요 498/24행, 예측 실행 각 1건과 계획 실행 0/0건이 동일했다.

## 공식 기준과 비교한 생산·자재 결과

응답 생산 행 81개, 자재 행 81개, 제약 평가 306개를 확인했다. 결품 수량은 공개 DTO의 `STOCKOUT` 근거와 별도로, 동일 SQL 스냅샷을 계산 코어에 넘겨 제품별 음수 월말재고에서 구했다. API가 반환한 안전재고 제약의 수량 필드는 비음수 계약을 따른다.

| 계획안 | 판정 | 생산 합계 EA | 결품 EA (1/2/3월) | 결품 제품·월 | 신규 발주 필요 자재·월 |
| --- | --- | ---: | --- | ---: | ---: |
| 기준형 | UNVERIFIED | 93,481 | 0 / 0 / 0 | 0 | 19 |
| 안정형 | INFEASIBLE | 96,583 | 0 / 994 / 2,618 | 18 | 19 |
| 비용절감형 | INFEASIBLE | 88,225 | 0 / 29 / 1,976 | 17 | 19 |

현재 SQL 공급에서 `scheduled_receipts=null`, 진단의 `scheduled_receipts.ready=false`, 공통 미검증 `RECEIPT_SOURCE_UNAVAILABLE`이 함께 확인됐다. 1월 MR-N3는 다음과 같다. 부족량은 C05의 신규 발주 필요량이며 안전재고 반영 때문에 단순 총소요와 가용량의 차이와 다를 수 있다.

| 계획안 | 1월 총소요 kg | SQL 가용량 kg | SQL 신규 발주 kg | 공식 입고 포함 가용량·신규 발주 kg |
| --- | ---: | ---: | ---: | --- |
| 기준형 | 83,128.4006 | 82,100 | 4,028.4006 | 92,100 · 0 |
| 안정형 | 86,235.1947 | 82,100 | 7,135.1947 | 92,100 · 0 |
| 비용절감형 | 80,927.2391 | 82,100 | 1,827.2391 | 92,100 · 0 |

공식 DTO와 실DB 스냅샷의 승인 대상 원본 9개 SHA 및 P50/P80/P90 27행 값이 일치했다. 합성 예측 요청은 원본 CSV 해시로 만든 `SYN-05-…` 배치 식별자를 사용하고 DB 예측 요청은 실제 승인 배치 UUID를 포함하므로 입력 digest가 다르다. 계산 코어에 전달되는 제품·예측·BOM·Routing·재고·CAPA 값을 숫자 표현과 목록 순서를 정규화해 비교하자 입고 목록만 달랐다. 공식 DTO에는 2027-01-20 `PO-2701-001`의 MR-N3 10,000 kg이 있다. 생산량·결품·판정은 세 후보 모두 공식 값과 같았고, 입고 포함 시 각 안의 신규 발주 필요 자재·월이 19건에서 18건으로 줄었다. [공식 결과](../modules/planning_engine/tests/chungpamo/RESULT.md) · [공식 DTO](../modules/planning_engine/tests/chungpamo/planning_input.json) · [합성 예측 요청 생성기](../modules/planning_engine/synthetic/forecast_request.py)

기존 승인 스냅샷을 메모리에 복사해 SAW1의 2027-02 잔업 한도를 40에서 80시간으로 적용하면, 실DB에서 읽은 입력과 공식 입고 포함 입력 모두 안정형의 결품이 **3,612→1,437 EA**, 생산량이 **96,583→97,791 EA**로 바뀌었다. 변경 후 안정형 결품은 0/27/1,410 EA이며 판정은 `INFEASIBLE`이다. 이는 읽기 전용 SQL 입력에 대한 **분리 계산**이다. 저장 부모를 사용하는 실제 API 검증은 P1이다.

## P1 · 전용 회귀 DB 쓰기 사전검사와 실행 범위

읽기 전용으로 `127.0.0.1:55433/chungpamo_regression`, `chungpamo_regression_runner`, revision `0009`, sentinel `DISPOSABLE-SYNTHETIC-REGRESSION-V1`을 확인했다. 전용 역할은 `chungpamo`의 `CONNECT` 권한이 없고 수퍼유저·DB/역할 생성·복제를 할 수 없다. 다른 세션 0건, 업무 행 0건이었다. `public`의 32개 테이블과 CHUNGPAMO-2027의 29개 테이블에는 데이터셋 등록·단위·revision·sentinel 시드만 있었다. history 스키마 2개는 존재하지 않았다.

단일 테스트의 기존 fixture는 회귀 DB 안의 `public`과 `ds_d3ef2e29ee90f6c7258d259aa99525b9`를 1회 재생성하고 `0009`까지 upgrade한 후 sentinel을 복원한다. 기존 fixture의 history 두 스키마 `DROP IF EXISTS`는 사전 부재 확인을 전제로 한다. 공식 생성기의 CHUNGPAMO-2027 합성 9배치와 저장소의 TISSUE-LEGACY 합성 7배치를 등록·승인한다. 필요한 예측·BASE·WHAT_IF와 트랜잭션 실패 검증은 동일 회귀 DB 안에서 수행한다.

두 스키마의 종료 정리는 각각 `forecast_run, import_batch CASCADE`의 FK 폐쇄 집합 **28개씩**이다. 실제 조회한 목록은 아래와 같다.

```text
batch_source_file, bom_header, bom_line, demand_forecast, forecast_run,
forecast_run_input, import_batch, ingestion_transform_source, ingestion_transformation,
inventory, material, monthly_demand, plan_candidate, plan_constraint_evaluation,
plan_decision, plan_execution, plan_execution_input, plan_material_requirement,
plan_review, product, production_capacity, production_hours_budget,
production_quantity_limit, production_resource, production_routing,
production_routing_resource_requirement, production_routing_step, sales_order
```

[지정 단일 테스트](../backend/tests/test_db_dataset_e2e.py)를 검증 당시의 `0009`에서 1회 실행했다. 대상·역할·sentinel·revision·업무 행 0·다른 세션 0·스키마별 28개 FK 폐쇄 집합이 승인 범위와 정확히 일치했다. 승인된 fixture 재생성 후 **1 passed / 0 failed / 0 skipped**였다. 기존 Starlette/httpx 경고 1건이 있었다.

| P1 실DB 항목 | 실제 결과 |
| --- | --- |
| 공식 3개월 입력 진단·Preview | 각각 200, Preview 전후 실행 이력 0→0, `persisted=false` |
| BASE | 신규 201, 동일 요청 200, 저장 상세 200. Preview와 결과 및 입력·계산 digest 일치 |
| 저장 부모를 참조한 WHAT_IF | Preview 200, 신규 저장 201, 동일 요청 200, 저장 상세 200. 3후보 재계산, 부모 입력·결과 digest와 승인 원본 스냅샷 보존 |
| 2027-02 SAW1 잔업 80h | 안정형 결품 **3,612→1,437 EA**, 생산 **96,583→97,791 EA**. 실제 저장된 입력을 계산 코어로 대조했고, 저장 API의 월별 생산 행도 일치 |
| 범위 밖 부모·정식 승인 | LEGACY에서 CP 부모 조회·What-if 실행/저장 404, 정식 APPROVE 501 |
| SQL 오류와 정리 | 실제 저장·투영 직후 SQL 오류로 500 `PERSISTENCE_ERROR`. 일곱 계획 테이블 행 수 불변. 28개씩 정리 후 양쪽 스키마 시드만 남고 업무 행 0 |

P1은 입고 reader 미연결 스냅샷으로 실행했다. 개발 DB의 테이블 60개·객체 735개·정의 660개 지문은 P0와 실행 전후 모두 일치했다. 비공개 JUnit XML과 사전·종료 증거는 `.artifacts/planning-postgresql-20261124/p1/`에 남겼다.

## P2 · C02 승인 입고 원장과 SQL reader 구현

`0009`의 `import_batch.ck_batch_entity`와 승인 기록 수 검증 트리거에 `scheduled_receipt`가 없다. `ReceiptLedgerRow`, `ReceiptLedgerReader`, `open_receipts`, 출처 검사와 `ScheduledReceipt` DTO는 이미 있다. 이 경계를 재사용하며 승인 매핑·등록 파이프라인을 중복하지 않는다. [C02 계약](PLANNING_CONTRACT_V04_HANDOFF.md#c02-승인-예정-입고) · [공급 인터페이스](../backend/app/integrations/planning_receipts.py) · [SQL provider](../backend/app/integrations/planning.py)

| 항목 | 설계 제안 |
| --- | --- |
| 저장 위치와 식별자 | 데이터셋별 스키마에 append-only `scheduled_receipt_revision`. `dataset_id` 스코프 제약, `(po_id, revision)` 유일성. 발주에 여러 행이 있으면 발주·행의 안정적인 조합 키를 쓰며 What-if 경로에서 구분자인 점은 금지한다. |
| 값과 참조 | 승인 자재 `material_id`, 달력형 `expected_date`, 사업 효력일 `effective_date`, `ordered_qty > 0`, `0 <= received_qty <= ordered_qty`, 표준 단위, 선택 `supplier_id`를 저장한다. 자재 참조와 단위는 동일 스키마의 재료 기준 단위로 검증한다. |
| 변경·취소·부분 입고 | 버전별 누적 입고를 기록하며 계획에는 주문−누적 입고만 내보낸다. 완전 입고는 계산에서 제외한다. 취소는 새 `CANCELLED` 버전으로 기록하고 이전 버전을 보존한다. 같은 발주·개정의 동시 승인 및 역순/누적 수량 충돌은 잠금·유일성·상태 검증에서 거절한다. 취소 후 재개는 업무 결정 대상이다. |
| 승인 출처 | 기존 `import_batch`의 `scheduled_receipt` entity로 동일 승인 트랜잭션에서 기록한다. `batch_id` 참조와 `(batch_id, source_row_no)` 유일성, 원본 행 지문을 보존한다. 승인자·버전·원본 SHA·결과 digest는 기존 배치/파일 경로를 사용한다. 승인 검증 실패나 DB 실패는 원장과 상태 전이를 함께 롤백한다. |
| SQL reader | 현재 `REPEATABLE READ`의 같은 데이터셋 연결에서 승인·차단 오류 0·출처 digest를 갖고 기준일에 유효한 최신 개정 1건을 조회한다. 미승인 개정은 이전 승인 개정을 가리지 않는다. 원본 발주 날짜와 승인 시각은 따로 보존하며, 기준일/승인 시점의 선택 정책은 팀 검토 후 고정한다. |
| 계획 스냅샷 | 계획 결과 재조회·What-if는 저장된 부모 입력을 그대로 사용한다. 적용된 행의 `ScheduledReceipt`와 승인 출처를 보존하고, 취소로 제외된 상태가 공급 판단에 영향을 주면 해당 승인 배치도 출처에 반영하도록 검토한다. 같은 계획 입력의 digest는 공급이 `null`인지 `[]`인지에 따라서도 구분된다. |

조회 제안에서 최신 개정을 고른 다음 취소·완료 및 계획 종료 뒤 입고를 제외한다. 기준일 당일 또는 이전의 미입고는 제외하지 않고 첫 달 및 `RECEIPT_OVERDUE`로 전달한다. 기준일 뒤·계획 시작 전에도 첫 달 귀속 규칙을 보존한다. SQL reader 미연결은 `null`, 연결·조회 성공 후 적용 입고 없음은 `[]`다. 연결된 reader에 DB 오류가 나면 기존 오류 계약으로 실패시켜 확인 가능한 빈 공급과 구별한다.

### 작성한 코드와 입력 방식

`0010`은 기존 활성·보관 데이터셋의 배치 entity 조건과 기존 지연 승인 행 수 함수를 확장하고 데이터셋별 입고 원장·인덱스·불변 트리거를 추가한다. 동일한 구조를 신규 데이터셋 초기화에 연결했다. 이전 migration 파일은 수정하지 않았다. 개발 0009 카탈로그에서 양쪽 스키마의 기존 승인 행 수 함수 정의를 읽어 함수 본문 접합을 메모리로 검증했다. 작성한 DDL은 실DB에서 실행하지 않았다. [0010 migration](../backend/migrations/versions/0010_scheduled_receipts.py) · [원장 DDL](../backend/app/dataset_schema_v3.py) · [배치 서비스](../backend/app/batches/receipts.py)

`POST /batches?dataset_id=CHUNGPAMO-2027`에 multipart `entity=scheduled_receipt`와 CSV 또는 명시적으로 선택한 단일 XLSX 시트를 전송한다. 열은 정확한 필드명 또는 `column_overrides`로 지정한다. 기존 재검증과 승인 API를 통해 `expected_result_digest`를 확인한다. 승인 직전 발주 단위로 잠근 뒤 승인 개정을 다시 확인하며, DB 트리거가 동일 트랜잭션의 승인 배치·수량·자재 기준단위·개정 순서를 추가로 검사한다.

```csv
po_id,po_line_id,revision,material_id,expected_date,effective_date,ordered_qty,received_qty,unit,supplier_id,status
PO-2701-001,,1,MR-N3,2027-01-20,2026-12-31,10000,0,kg,SUP-PULP-A,OPEN
```

예시의 `effective_date`는 계획 기준일에 이 합성 발주가 유효하다는 테스트 조건이다. 계획 키는 행 없는 발주의 `po_id`, 행이 있는 발주의 `po_id--po_line_id`다. 구분자 `--`와 점은 개별 입력 키에서 쓰지 않는다. 같은 발주에서 행 있는 방식과 행 없는 방식을 혼합하지 않는다. `revision`은 1에서 시작해 연속으로 증가하며 효력일 및 누적 입고량은 역행하지 않는다. 완료·취소 개정은 종결로 처리한다. 재개나 사후 정정의 예외 정책은 업무 협의 대상이다.

SQL reader는 계획 기준일 이하의 `effective_date`와 읽기 트랜잭션에서 확인된 승인 상태를 사용한다. `approved_at`은 행이 효력을 갖는 업무일과 별개인 감사 시각이다. 오늘 조회를 과거 시점의 승인 가능 상태로 재구성하지 않으며, 저장 결과와 What-if는 이미 저장한 부모의 승인 증거를 사용한다. 최신 유효 승인 개정의 취소·완료·기간 밖 행을 적용 입고에서 제외하고, 해당 승인 배치는 조회 당시의 출처로 유지한다. 0009에서 미연결은 `null`, 0010에서 정상 조회한 빈 공급은 `[]`이며 스키마 불일치·조회 실패는 오류로 전달한다.

비DB의 실제 계획 엔진·SQL 조회 대역에서 공식 입고 전후의 1월 가용량 **82,100→92,100 kg**과 앞 표의 후보별 발주량 **4,028.4006 / 7,135.1947 / 1,827.2391→0 kg**, 미연결 사유 제거, 같은 후보 판정을 검증했다. 수량 변경과 0 취소 가정으로 자재 가용량이 변해도 부모와 승인 입력이 유지됐다.

### 별도 실행 승인 요청 범위와 수용 기준

- 대상은 `chungpamo-monorepo-db`의 `127.0.0.1:55433/chungpamo_regression`, 역할 `chungpamo_regression_runner`, 동일 sentinel이다. 최초 연결은 읽기 전용으로 세션·스키마·FK·시드 전용 여부와 개발 DB 접속 권한 부재를 확인한다.
- 회귀 DB 한정 `0009→0010` upgrade **1회**. 이 migration은 등록된 `public`과 CHUNGPAMO-2027 두 스키마에 DDL을 적용한다. 기존 개발 DB는 `0009` 상태로 유지한다.
- [전용 실DB 테스트](../backend/tests/test_db_scheduled_receipts.py) `test_actual_approved_receipts_and_parent_what_if` **1회**. 별도 토큰 `CHUNGPAMO_ALLOW_RECEIPT_SQL_TEST=chungpamo_regression@127.0.0.1:55433`과 전용 `TEST_DATABASE_URL`이 필요하다. 이 테스트는 migration·스키마 재생성을 수행하지 않는다.
- CHUNGPAMO-2027에만 공식 합성 9배치, 새 예측, 합성 PO 개정·거절 사례, BASE 및 WHAT_IF를 작성한다. LEGACY는 교차 데이터셋 조회만 수행한다. 종료 시 기존 P1 목록의 28개와 `scheduled_receipt_revision`을 합친 CHUNGPAMO-2027의 **29개 테이블만 명시적 `TRUNCATE … RESTRICT`**로 정리한다. 새 FK 폐쇄 집합을 실측해 다르면 중단한다. 개발 DB와 레지스트리·단위 시드, 볼륨은 정리 범위에서 제외한다.

1. 연결 없음 `null`, 연결·승인 없음 `[]`, 같은 PO의 미승인 개정·타 데이터셋·취소·완전 입고 또는 기간 밖의 입고를 검증한다. 잘못된 자재·단위·날짜·과입고·중복·동시 승인 실패를 확인한다.
2. 공식 합성 `PO-2701-001`을 실제 업로드·검증·명시적 승인한다. 기준일 2026-12-31부터 2027-01~03을 검증하고, 승인 전후 1월 MR-N3 가용량 82,100→92,100 kg과 후보별 신규 발주량을 대조한다. 앞의 공식 입고 포함 계산은 기대값이다. C02 연결 후 모든 후보가 `FEASIBLE`일 것으로 가정하지 않는다.
3. 승인 입고가 포함된 실제 BASE를 저장한 뒤 `receipt_qty.PO-2701-001`의 양수 변경 및 0 취소를 각각 WHAT_IF로 계산·저장한다. 승인 원장·부모 입력·기존 결과 지문, 기존 `null` 부모에서 해당 발주 조정을 사용할 수 없는 상태를 확인한다.

### 팀 인계

- 희원님은 `PLANNING_RULES-v0.4` 계산과 기존 3,612→1,437 결품 기준을 유지한다. 실DB에서는 입고 공급이 연결되기 전후의 자재 판정이 달랐다. 공개 DTO의 제품 결품 사유와 수량 표시가 별개임을 공유한다.
- 김대영은 별도 승인 후 회귀 0010 적용과 C02 단일 SQL 테스트를 담당한다. 독립 회귀 쓰기 후 개발 DB 지문을 다시 대조한다.
- 나미님은 `scheduled_receipts.ready=false`와 확인된 빈 공급을 구별해 표시하고, Preview와 실제 저장·승인 가능 여부를 각각 표시한다. 정식 `APPROVE`는 현재 501이다.

P2 코드와 동기화 후 전체 비DB pytest는 **1,371 passed, 69 skipped**였다. 0010 전용 실DB 테스트는 건너뜀에 포함된다. OpenAPI와 JSON Schema 생성물, 오프라인 Alembic 계보와 기존 승인 게이트 계약이 일치했다. 새 코드를 기존 개발 0009에 연결한 읽기 전용 검사 7개도 통과했으며 P0의 계획 입력·결과 digest 및 이력 건수와 일치했다. 검증 증거는 Git 제외 `.artifacts/planning-postgresql-20261124/`에 보존했다. 이번 작업에서 Upstage 호출과 AI 매핑 연구비 사용은 없었다.

```powershell
.\.venv\Scripts\python.exe scripts/verify_readonly_dataset_api.py --output .artifacts/planning-postgresql-20261124/readonly-dataset-api.json
```

## P3 · 회귀 PostgreSQL 0010 적용과 C02 승인 결함 확인

2026-11-24 KST, 메인 Windows PC. 시작 `main`은 [`8ccff79`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/8ccff7928e4b03466c254c6bf4ba548c62dc6b05)이다. PostgreSQL 16.6의 `chungpamo-monorepo-db` 안에서 `127.0.0.1:55433/chungpamo_regression` 및 `chungpamo_regression_runner`를 확인했다. 읽기 전용으로 `0009`, sentinel `DISPOSABLE-SYNTHETIC-REGRESSION-V1`, 다른 세션 0개, 업무 행 0개, 두 등록 데이터셋과 단위 시드, 개발 DB `CONNECT` 권한 부재를 확인했다. 적용 전 각 스키마의 정리 FK 폐쇄 집합은 28개였다.

### migration 및 HTTP 결과

- 회귀 DB에서 `0009→0010` upgrade **1회 성공**. `public`과 CHUNGPAMO-2027 스키마 각각에 `scheduled_receipt_revision` 1개, FK 4개, 인덱스 4개(PK 및 UNIQUE 포함), 등록 검증·불변 트리거 2개를 실제 카탈로그에서 확인했다. 데이터셋 값 제약, `import_batch`의 entity 허용 목록, 기존 승인 행 수 검증 함수에 추가된 입고 분기와 스키마별 검색 경로를 확인했다. 변경 대상으로 지정되지 않은 기존 카탈로그 정의와 기존 행 지문은 동일했다. 두 스키마의 구조를 정규화해 일치 여부를 확인했고, 신규 데이터셋 provision이 동일 DDL 설치 함수를 호출하는 것은 코드로 확인했다. 신규 스키마 provisioning의 실제 DDL 실행은 미검증이다.
- `test_actual_approved_receipts_and_parent_what_if` **1회 실행, 0 passed / 1 failed / 0 skipped**. Starlette/httpx 사용 중단 예정 경고 1건. 공식 합성 배치 9개의 업로드 201·승인 200, 3개월 예측 저장 201, 공식 입고 `PO-2701-001` 업로드 201·재검증 200(버전 1→2, 결과 digest 동일)을 확인했다.
- 승인 전 입고 행 0개와 `scheduled_receipts={ready:true,row_count:0}`, Preview 200을 확인했다. 1월 MR-N3 가용량은 세 후보 모두 **82,100 kg**, 신규 발주 필요량은 기준형 **4,028.4006 kg**, 안정형 **7,135.1947 kg**, 비용절감형 **1,827.2391 kg**이었다. 같은 테스트에서 reader 가용성만 대역으로 끈 별도 부모를 실제 SQL·엔진으로 201 저장했고, `scheduled_receipts=null`·`RECEIPT_SOURCE_UNAVAILABLE` 및 해당 부모 입고 조정 422 `PLAN_OVERRIDE_UNSUPPORTED`까지 확인했다. 실제 0009의 읽기 전용 미연결 증거는 P0에 있다.
- 최초 공식 입고 승인에서 HTTP **500**. 같은 시간대의 PostgreSQL 로그에서 `scheduled_receipt_revision_source_sheet_check` 위반을 확인했다. CSV 공통 파서의 시트 이름은 빈 문자열인데 승인 INSERT가 그대로 전달했다. 기존 제약을 유지하고 원장의 CSV 출처 표기만 `CSV`로 저장하도록 수정했다. 파싱 위치, 원본 행 SHA, XLSX 시트명, 승인 digest의 산출 경로는 보존된다. 비DB 회귀가 CSV/XLSX의 실제 파싱부터 승인 SQL 바인딩 및 승인 행 수 호출까지 확인한다.
- 입고 승인 성공 및 92,100 kg·발주량 0, 후보별 생산량·판정, 승인 입고 포함 부모 기반 양수·0·복합 What-if, 타 데이터셋·효력일·연체·부분/완전/취소·잘못된 입력·동시 승인·실패 롤백의 테스트 후반부는 **실DB에서 도달하지 못했다**. 위 기대값은 P2 비DB 및 공식 자료 기준이다. 실제 승인 결과처럼 사용하지 않는다.

### 종료 확인과 P3 재검증 범위

fixture가 CHUNGPAMO-2027의 기존 P1 28개 테이블과 `scheduled_receipt_revision`만 명시적인 `TRUNCATE … RESTRICT`로 정리했다. 종료 읽기 전용 스냅샷에서 두 스키마의 업무 행 0개, migration 직후 DDL, 단위·데이터셋·sentinel 시드가 일치했다. 회귀 DB는 `0010`을 유지하고 개발 DB는 `0009`이며, 개발 DB 60개 테이블의 행 수·지문, 735개 스키마 객체·660개 추가 정의, 승인 배치 7+9건·예측 2건·계획 이력이 전후 일치했다. AI 매핑 Phase 9-A는 보류 상태였고 비용 원장 SHA도 일치했다. 실행 및 정리 증거는 Git 제외 `.artifacts/planning-postgresql-20261124/p3/`에 보존했다.

수정 후 전체 비DB pytest는 **1,373 passed / 0 failed / 69 skipped**, 입고·OpenAPI·생성 Schema 집중 검사는 **33 passed / 0 failed / 1 skipped**였다. 지정 실DB 테스트의 실행 결과는 위 실패 1건이고, 비DB 실행의 건너뜀에는 DB 테스트가 포함된다.

P3 재검증에는 현재 `0010`인 같은 회귀 DB·역할·sentinel·스키마의 읽기 전용 재확인과 동일 지정 노드 **1회**에 대한 신규 승인이 필요하다. 범위는 CHUNGPAMO-2027 합성 9배치와 검증용 입고 개정의 업로드·재검증·명시적 승인, 예측/BASE/WHAT_IF 저장, 제약 및 롤백 시험, 동일 29개 테이블의 명시적 종료 정리다. LEGACY는 교차 조회 전용으로 사용한다. 현재 revision이 0010이므로 새 upgrade나 스키마 재생성은 재현에 필요하지 않다.

## P4 · 개발 DB 적용 체크리스트 (P3 수정 재검증 통과 후)

1. `chungpamo` 역할·포트와 `0009`, 등록 대상 스키마 `public` 및 CHUNGPAMO-2027, 승인·예측·계획 이력, 공식 원본 SHA와 기준 지문을 읽기 전용으로 재확인한다. 이전 `0008` 시점 백업과 별도로 현재 `0009`의 비공개 `pg_dump -Fc`를 확보한다. 크기·SHA·`pg_restore --list`를 확인하고 실제 복구 가능성은 승인받은 별도 격리 대상의 복구 리허설로 검증한다.
2. 별도 승인 후 개발 DB의 `0009→0010`만 1회 적용한다. P3에서 확인한 스키마별 신규 원장·FK 4개·인덱스 4개·트리거 2개, 승인 guard 함수 1개, 기존 entity CHECK와 승인 행 수 함수의 변경만 허용한다. 기존 행은 전수 지문으로, 기존 정의는 허용 목록을 제외하고 적용 직전과 대조한다. 불일치하면 추가 쓰기를 멈추고 백업·복구안을 보고한다.
3. 별도로 합성 입고 쓰기를 승인받은 뒤 `CHUNGPAMO-2027`에서 `PO-2701-001`의 개정 및 동일 파일 SHA를 먼저 조회한다. 이미 승인된 같은 자료는 기존 승인 이력을 사용하고 값이 다르면 조사를 시작한다. 신규 자료는 `/batches` 등록 → `/revalidate` → 서버 digest를 전달한 명시적 `/approve`로 처리한다. 한 번의 승인만 원장에 남았는지 읽기 전용으로 확인한다.
4. revision 0010을 명시적으로 확인하는 읽기 전용 실행 경로로 기존 승인 예측의 2027-01~03 진단과 Preview를 다시 실행한다. P0 스크립트는 현재 `0009`를 고정하므로 P4에서는 별도 지원이 필요하다. 1월 MR-N3 가용량·후보별 신규 발주 필요량·생산량·판정·승인 출처의 전후 차이를 비교한다. 저장된 부모를 활용하는 경우 입고 수량 변경·0·SAW1 조합의 Preview 및 부모 지문 보존을 확인한다. 개발 DB의 실제 BASE/WHAT_IF 영구 저장이 필요하면 승인 범위에 명시하고 별도로 기록한다.

이전 `0008` private 백업의 크기와 SHA가 기존 기록과 일치했고 목차 검사 기록도 확인했다. `0009`의 신규 백업과 실제 복구 리허설은 P4 준비 단계에 남아 있다.

**P4 상태** — 변경 후 P3 실DB 승인과 후반 검증을 다시 통과하기 전에는 개발 DB 적용 승인을 요청하거나 실행하지 않는다.

## C02 읽기 API · 메인 PC 실DB 검증

2026-11-25에 추가한 `GET /scheduled-receipts`의 실DB 검증 절차다. 보조 PC에서는 TestClient와 SQL 연결 대역으로 검증했다. 아래 작업은 기존 메인 PC에서 환경과 대상을 다시 확인한 뒤 수행한다. 이 API에는 새 migration이 필요하지 않다. [조회 계약](FRONTEND_BACKEND_CONTRACT_FOLLOWUP_20261125.md#c02-승인-입고-원장-읽기-api-설계)

### 개발 DB 0009 읽기 전용

저장소 루트에서 기존 개발 DB의 포트·이름·역할·스키마 및 revision을 확인한다. 아래 절차는 기존 보존 도구의 확인을 재사용해 이름·역할·리소스를 검증하고, 시작부터 연결을 읽기 전용으로 연다. 두 데이터셋에서 200 `UNAVAILABLE`과 `items=null`, `total=null`, `reason_code=RECEIPT_SOURCE_UNAVAILABLE`를 확인한다. GET 전후 테이블 행 수·데이터 지문과 카탈로그를 대조한다.

```powershell
@'
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from scripts.postgresql_preservation import compare, development_url, snapshot
from app import db
from app.api import scheduled_receipts
from app.config import Settings
from app.main import app

before = snapshot()
assert before['revision'] == '0009'
engine = create_engine(development_url(), connect_args={
    'options': '-c default_transaction_read_only=on', 'connect_timeout': 3,
})
settings = Settings(_env_file=None, persistence='postgres')
try:
    with patch.object(db, 'get_engine', return_value=engine), patch.object(
        scheduled_receipts, 'get_settings', return_value=settings
    ), TestClient(app) as client:
        for dataset in ('CHUNGPAMO-2027', 'TISSUE-LEGACY'):
            response = client.get('/scheduled-receipts', params={
                'dataset_id': dataset, 'as_of_date': '2027-01-05',
            })
            assert response.status_code == 200, response.status_code
            result = response.json()
            assert result['dataset_id'] == dataset and result['source_state'] == 'UNAVAILABLE'
            assert result['reason_code'] == 'RECEIPT_SOURCE_UNAVAILABLE'
            assert result['items'] is None and result['total'] is None
finally:
    engine.dispose()
    after = snapshot()
    compare(before, after)
    assert before['objects'] == after['objects']
print('C02 GET on 0009: 2 unavailable, development DB unchanged')
'@ | .\.venv\Scripts\python.exe -
```

### 전용 회귀 DB 0010 통합 검증

P3의 대상·역할·sentinel·합성 출처·업무 행 0개·정리 범위를 읽기 전용으로 사전 확인한다. 아래 지정 테스트는 **별도 실행 승인 후 1회** 실행한다. 이 테스트의 기존 fixture는 합성 승인 개정과 계획 이력을 쓰고 종료 시 지정된 회귀 테이블을 정리한다. `TEST_DATABASE_URL`은 기존 로컬 설정에서 사용한다.

```powershell
$env:CHUNGPAMO_ALLOW_RECEIPT_SQL_TEST = 'chungpamo_regression@127.0.0.1:55433'
try {
@'
import os

import pytest
from dotenv import dotenv_values

if not os.environ.get('TEST_DATABASE_URL'):
    os.environ['TEST_DATABASE_URL'] = dotenv_values('.env.regression.local')['TEST_DATABASE_URL']
raise SystemExit(pytest.main([
    '-q', 'backend/tests/test_db_scheduled_receipts.py::test_actual_approved_receipts_and_parent_what_if',
]))
'@ | .\.venv\Scripts\python.exe -
    if ($LASTEXITCODE -ne 0) { throw 'C02 PostgreSQL regression failed' }
} finally {
    Remove-Item Env:CHUNGPAMO_ALLOW_RECEIPT_SQL_TEST
}
```

기대 결과는 지정 테스트 1건 통과와 건너뜀 0건이다. 최초 200 `AVAILABLE`과 빈 목록, 승인 후 조회 출처와 원장 행의 일치, 다른 데이터셋의 빈 결과, 기준일별 개정 선택, 부분 입고 잔량, 완료·취소 잔량 0, 기존 OPEN 개정 제외, 정렬·페이지·전체 건수 유지를 확인한다. 공식 입고 반영 및 부모 What-if의 기존 P3 검증도 통과해야 한다. GET 전후 원장 행 동일과 승인 이력 무결성, 종료 후 회귀 시드와 개발 DB 지문을 확인한다.
