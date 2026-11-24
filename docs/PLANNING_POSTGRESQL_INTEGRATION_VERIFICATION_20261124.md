# 생산계획 실제 PostgreSQL 검증과 C02 승인 입고 설계

2026-11-24 KST · 메인 Windows PC · 김대영 · 기준 [91927a0](https://github.com/ChungPaMo/decision-supporter-mvp/commit/91927a0d568962526c896de518e4d3a01cd7b0ec)

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

[기존 단일 테스트](../backend/tests/test_db_dataset_e2e.py)에서 Preview 이력 불변·BASE와 WHAT_IF의 201/200·상세 결과 및 입력/계산 digest·부모 원본 보존·타 데이터셋 부모 404·APPROVE 501을 검증하도록 보강했다. 실제 저장 SQL과 투영이 완료된 직후 SQL 오류를 주입해 일곱 계획 테이블의 행 수가 원복되는지도 검증한다. 쓰기·초기화는 이번 P1 범위를 승인받은 뒤 한 번만 수행한다. 승인 전 실DB BASE/WHAT_IF 저장과 롤백은 **미실행** 상태다.

## P2 · C02 승인 입고 원장과 SQL reader 제안

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

### 별도 승인 요청 범위와 수용 기준

신규 migration은 `0009` 다음 순번으로 제안한다. **migration 파일 작성 및 연결 코드 구현**에는 별도 승인이 필요하다. 예상 변경은 기존 활성·보관 데이터셋의 배치 entity 체크와 승인/행 수 트리거 확장, 승인 입고 원장·인덱스·불변 제약, 신규 dataset provisioning, 기존 배치 검증기와 SQL reader다. 이전 revision 파일과 승인 데이터의 재작성은 필요 없다. 그다음 **실행 승인**은 전용 회귀 DB에만 upgrade 및 합성 쓰기를 적용하는 별도 건으로 요청한다. 개발 DB 적용·운영 입고 등록은 추가 검토 범위다.

1. 연결 없음 `null`, 연결·승인 없음 `[]`, 같은 PO의 미승인 개정·타 데이터셋·취소·완전 입고 또는 기간 밖의 입고를 검증한다. 잘못된 자재·단위·날짜·과입고·중복·동시 승인 실패를 확인한다.
2. 공식 합성 `PO-2701-001`을 실제 업로드·검증·명시적 승인한다. 기준일 2026-12-31부터 2027-01~03을 검증하고, 승인 전후 1월 MR-N3 가용량 82,100→92,100 kg과 후보별 신규 발주량을 대조한다. 앞의 공식 입고 포함 계산은 기대값이다. C02 연결 후 모든 후보가 `FEASIBLE`일 것으로 가정하지 않는다.
3. 승인 입고가 포함된 실제 BASE를 저장한 뒤 `receipt_qty.PO-2701-001`의 양수 변경 및 0 취소를 각각 WHAT_IF로 계산·저장한다. 승인 원장·부모 입력·기존 결과 지문, 기존 `null` 부모에서 해당 발주 조정을 사용할 수 없는 상태를 확인한다.

### 팀 인계

- 희원님은 `PLANNING_RULES-v0.4` 계산과 기존 3,612→1,437 결품 기준을 유지한다. 실DB에서는 입고 공급이 연결되기 전후의 자재 판정이 달랐다. 공개 DTO의 제품 결품 사유와 수량 표시가 별개임을 공유한다.
- 김대영은 별도 승인 후 회귀 단일 테스트와 C02 DDL·reader·승인 통합을 담당한다. 독립 회귀 쓰기 후 개발 DB 지문을 다시 대조한다.
- 나미님은 `scheduled_receipts.ready=false`와 확인된 빈 공급을 구별해 표시하고, Preview와 실제 저장·승인 가능 여부를 각각 표시한다. 정식 `APPROVE`는 현재 501이다.

메인 PC에서 전체 비DB pytest는 **1,359 passed, 68 skipped**였다. 실제 PostgreSQL 쓰기 테스트는 건너뜀에 포함된다. 검증 증거는 Git 제외 `.artifacts/planning-postgresql-20261124/`에 보존했다. 이번 작업에서 Upstage 호출과 AI 매핑 연구비 사용은 없었다.

```powershell
.\.venv\Scripts\python.exe scripts/verify_readonly_dataset_api.py --output .artifacts/planning-postgresql-20261124/readonly-dataset-api.json
```
