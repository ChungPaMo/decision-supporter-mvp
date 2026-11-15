# 이희원 합성데이터 통합 검증 — 실제 DB 등록 보류

검증일: 2026-11-15. 기준 main: **e87b75d6b111be4f939b65ec4f3403a188d84954**. 작업 시작 시 팀원 커밋 2개를 fast-forward로 반영했다. 이 문서는 **1차 비DB 계약 검증 결과**이며 PostgreSQL 등록·승인·PlanningInput 실제 연결 완료 보고서가 아니다.

## 결론과 안전 중단 사유

- 생성기 실행 성공, 업로드 CSV 9개 모두 정상 계약 검증 성공. FastAPI TestClient와 실제 BatchService/파서/매핑/검증/digest/승인 로직을 사용하되 저장소는 명시적 인메모리 대역이다. CAPA 저장만 대역으로 대체하고 실제 validate_rows를 호출했다. DB 트리거·FK·잠금·영구 저장을 검증한 결과가 아니다.
- **실제 DB 승인 0건, PostgreSQL 신규 등록 0건.** 실제 예측 UUID를 새로 만들거나 실제 PlanningInput을 조회하지 않았다. 순수 CapacityRegistrationDraft 검증을 실제 PlanningInput 연결로 표현하지 않는다.
- Docker Desktop Linux Engine 파이프가 없어 전용 컨테이너 inspect가 실패했다. 따라서 프로젝트 chungpamo-monorepo·127.0.0.1:55433/chungpamo·현재 revision/기존 키/승인 배치를 현시점에 재식별할 수 없었다. 대상 확인 전에 DB에 직접 접속하지 않았다. 기존 7개 배치/0007은 이전 보고 기준이며 이번 SELECT 확인값이 아니다.
- **Docker가 켜져도 바로 승인하면 안 된다.** [ForecastRuns.create](../backend/app/forecast/runs.py)는 승인 월수요 전체를 조회한다. [SqlPlanningSourceProvider](../backend/app/integrations/planning.py)는 제품·자재·BOM·재고 전체, [planning_snapshot](../backend/app/batches/capacity.py)은 자원·월 가용시간 전체를 읽는다. 따라서 코드가 TP-10R과 달라도 새 9제품 자료가 기존 스냅샷·digest·coverage/예측 대상에 영향을 줄 수 있다. 현재 scenario_id 격리 계약은 없다. 사용자 안전 조건에 따라 실제 등록을 보류했다.
- 이번 작업은 DB 접속/업로드/승인/마이그레이션/초기화/기존 데이터 변경을 수행하지 않았다. 기존 자료를 보존하기 위해 알려진 55432·sisicallcall·테스트 DB에도 접근하지 않았다.

## 생성 및 원본 변환 검증

`.venv/Scripts/python.exe -X utf8 modules/planning_engine/synthetic/generate.py`를 저장소 루트에서 실행했다. 생성기는 raw 판매/생산/구매/재고 대조와 expected→raw→upload 일치 검사를 통과해 exit 0으로 종료했다. 이어 convert.py를 별도로 실행해 raw만 읽어 `.artifacts/synthetic_reconvert/`에 다시 변환했고, 9개 업로드 파일이 원본 생성 결과와 **모두 바이트 동일**했다.

실제 위치는 `modules/planning_engine/synthetic/data/upload/`다. 요청의 `data/01_*.csv` 루트 경로가 아니라 README의 upload 하위 경로를 사용한다. 생성기·변환기 파일은 수정하지 않았다. 출력은 기존 data/·CSV ignore 규칙대로 추적하지 않는다.

모두 UTF-8 BOM, 헤더 제외 총 615행이다. 파일별 SHA-256과 entity는 다음과 같다.

| CSV | entity | Rows | SHA-256 |
|---|---|---:|---|
| 01_products.csv | product | 9 | `41214dbc5b0a4656a702cf9cc19fc5c1f56c04163437b26465022f57b8fb736f` |
| 02_materials.csv | material | 9 | `bc1da829b0d69526294dd4683b2784e95a6215f4f090dc42abaadaa0a1bafff1` |
| 03_bom.csv | bom | 27 | `5ac622fc6b61130acbb54e9a2e16da410a398b8ab358b906910eb5c154a5f05a` |
| 04_inventory.csv | inventory | 18 | `025eceecbb7a2c901e9f4e11429ed39db873b9bbd9dfa3a61223fa932e995845` |
| 05_monthly_demand.csv | monthly_demand | 498 | `8e43184b4ee8cea60b50b8358dd21c414fa99afdbf52c6bfaecd9c2c1b251b29` |
| 06_capacity_resources.csv | capacity | 6 | `d6903ba6a1d82386392953dffd39b01e301bcf8f01d49c2eb99cd65052532b5a` |
| 07_capacity_quantity_limits.csv | capacity | 3 | `0b006a728cb16c98cfe25cdf2b869ceba031918fbfc0684900db674927dd3c7f` |
| 08_capacity_hours_budgets.csv | capacity | 18 | `e7b78f9546bdb64e92c6295599ed3ec5d39b042314e101254a64e62873c12648` |
| 09_routing_steps.csv | routing | 27 | `da84aec2d914250807cf89a6a58e5b6360feba77644726bd2bef362f868eac03` |

### CSV headers (actual generated files)

- `01_products.csv`: `제품코드, 제품명, 단위, 제품유형, 안전재고`
- `02_materials.csv`: `자재코드, 자재명, 단위, 안전재고`
- `03_bom.csv`: `BOM코드, 제품코드, 버전, 상태, 활성, 유효시작일, 유효종료일, 기준수량, 순번, 구성유형, 구성품코드, 소요량, 단위, 스크랩률`
- `04_inventory.csv`: `품목구분, 품목코드, 기준일, 현재고, 할당재고, 가용재고, 단위`
- `05_monthly_demand.csv`: `product_id, period, demand_qty, unit`
- `06_capacity_resources.csv`: `resource_id, resource_name, kind, time_basis, parallel_units`
- `07_capacity_quantity_limits.csv`: `capacity_id, product_id, period, limit_qty, unit, accounting_point, operation_id`
- `08_capacity_hours_budgets.csv`: `capacity_id, resource_id, period, regular_hours, overtime_hours_limit, unit, time_basis, availability_basis, calendar_ref`
- `09_routing_steps.csv`: `resource_id, reference_qty, quantity_unit, run_time, time_unit, time_basis, concurrent_units, setup_time, setup_policy_ref, alternative_group_ref, routing_id, routing_version, step_id, product_id, operation_id, predecessor_step_ids, valid_from, valid_to, resource_requirements`

## 타입·참조·정상 파일 결과

정상 9개 모두 자동 매핑으로 READY_FOR_APPROVAL, blocking error 0, HOLD 0이었다. 인메모리 승인 응답은 200/APPROVED, 같은 파일 재업로드는 409 DUPLICATE_UPLOAD였다. 이는 **인메모리 승인 9건**이며 실제 DB 승인 건수가 아니다. 승인 digest는 서버 응답을 그대로 사용했고 직접 승인 상태 SQL은 쓰지 않았다.

| 범위 | 검증 결과 |
|---|---|
| 01/02 | 제품 9개·자재 9개. 코드/이름/기본 단위/제품 유형·안전재고 타입과 승인 마스터 참조 통과 |
| 03 | BOM 구성품 27행·헤더 9개. MATERIAL 참조와 단위·Decimal·스크랩률·유효기간/버전 통과 |
| 04 | 제품/자재 재고 18행. 기준일 전부 2026-12-31, 현재고·할당·가용 및 단위 검증 통과 |
| 05 | 제품·월 수요 498행, 2022-01~2026-12 범위. 신제품은 짧은 이력 유지. 타입·키 검증 통과 |
| 06/07/08 | 별도 capacity 배치 3개 순차 처리 성공. 자원 6개·한도 3행·시간예산 18행, 2027-01/02/03 유지 |
| 09 | 9제품별 REWIND→CUT→PACK 3공정, 총 27행. 선행 공정 JSON 파싱·DAG·자원/제품 참조 통과 |
| 공유/동시 자원 | SAW1을 9제품 모두 같은 코드로 참조. PACK 9개에 LB1 PERSON_HOUR가 추가 동시 소요로 유지되며 기계시간에 합산하지 않음 |
| 시간·수량 | 참조수량·run_time은 양수 Decimal 문자열, h/min과 PERSON_HOUR/MACHINE_HOUR 구별. 인력 인원 수를 인시에 다시 곱하지 않음 |

원본 팩/개→EA 및 손실률 %→소수는 convert.py 단계에서 처리된다. kg는 kg로 유지하며 API가 임의 물리 단위를 환산하지 않는다. CAPA 신규 DTO의 14자리 정수부/6자리 소수 및 기존 품목 수량 계약을 각 검증기에 통과시켰다. 빈 선택값은 null, predecessor_step_ids/resource_requirements는 JSON 배열로 파싱했다. 비용·입고 예정·원시 거래는 현재 승인 entity에 추가하지 않았다.

기존 기준 시드 파일과 정적 비교하면 CP-* 제품/MR-* 자재/RW1·RW2·SAW1·PK1·PK2·LB1 자원은 TP-10R/TP-* 자재/M1·L1과 코드가 구별된다. 단, **이는 기존 DB 실조회 대조가 아니며 시나리오 격리를 보증하지 않는다.** 기존 DB의 BOM/재고/수요/CAPA/Routing 키·기간 대조는 전용 환경 확인 후 별도 수행해야 한다.

## 오류 파일·false accept/false reject와 희원님 수정 요청

기준 마스터만 있는 별도 인메모리 저장소로 각 오류 파일을 검증했다. 정상 파일 승인 후 이미 등록된 수요 키 때문에 우연히 거부되는 결과를 배제했다.

| 파일 | 실제 결과 | 위치·현재 값·요청 |
|---|---|---|
| demand_missing_qty.csv | HAS_ERRORS / QTY_MISSING | 4행 C열, 빈 수요량. 기대대로 차단 |
| demand_duplicate_period.csv | READY, DUPLICATE_ROW_IDENTICAL 경고 | 8행이 7행과 같은 CP-N3-3030 / 2026-12 / 9930 EA. 기존 계약은 첫 행만 사용하며 허용. 충돌 오류 시험이 목적이면 동일 키의 C8을 예를 들어 **9931**로 바꾸고 DUPLICATE_KEY_CONFLICT 기대값으로 수정 요청 |
| demand_bad_period_format.csv | READY, 오류 0 | 2행 B열 `2026/07`. API ingest는 YYYY/MM을 YYYY-MM으로 정규화하는 기존 계약. 실제 오류 시험은 `2026-13`처럼 유효하지 않은 월로 수정 요청 |
| products_unknown_unit.csv | HAS_ERRORS / UNIT_UNKNOWN | 2행 C열 BOXX. 기대대로 차단 |
| bom_unknown_material.csv | HAS_ERRORS / MATERIAL_NOT_REGISTERED | 2행 K열 MR-XXX. 기대대로 차단 |
| inventory_negative_qty.csv | HAS_ERRORS / QTY_NEGATIVE | 2행 D/F열 -100. 현재고·가용재고 두 오류 차단 |
| sales_orders_dirty_sample.csv | /ingest/preview에서 MAPPING_HOLD | 주문/거래 원본은 월별 수요 입력 계약이 아님. 별도 정제·월별 집계 기능으로 구분 |

생성기가 의도한 negative 기대값으로는 2건이 수용됐지만 기존 백엔드 계약 기준으로는 **false accept가 아니라 fixture 기대값 불일치**다. 기존 API를 강화해 호환성을 깨뜨리지 않았다. 정상 파일의 false reject는 0건이다. `2026-13`과 동일 키·상이 수량은 별도 단위 시험에서 실제 차단됨을 확인했다.

생성기 담당 폴더를 수정하지 않았고 팀원에게 외부 메시지를 보내지 않았다. 위 두 행과 README의 errors 설명을 함께 수정 요청한다. 합성 수치·원가·안전재고·병목 설명은 계산 정책/엔진 정답으로 승격하지 않았다.

## 시나리오 격리 제안과 재개 조건

1. 최소 변경안: 기존 개발 DB를 그대로 두고 **새 전용 시나리오 DB**를 별도 사용자 승인·대상 점검 후 준비한다. 기존 PostgreSQL 서버/역할/DB 자원 재사용 범위와 권한도 먼저 합의한다. 이번에는 새 DB/컨테이너를 생성하지 않았다.
2. 장기안: import_batch·마스터/업무 키·승인 조회·forecast 요청/저장·PlanningInput·시나리오 계보에 scenario_id를 일관되게 도입한다. 단순 제품 필터나 코드 접두사는 마스터/공유 자원 격리를 대신하지 못한다. 기존 데이터를 자동 이전하거나 global 조회 의미를 조용히 변경하지 않는다.
3. Docker와 전용 대상 식별을 복구하고, 기존 승인 배치와 전체 키/기간을 SELECT로 대조한다. 선택한 격리 계약이 기존 TP-10R의 입력 내용·digest를 보존하는지 회귀 시험 후 실제 API 등록을 재개한다.
4. 이후 9개 파일을 제품→자재→BOM→재고→수요→자원→수량→시간→Routing 순서로 실제 승인하고 SELECT 건수·출처를 확인한다. 실제 저장 예측 UUID와 PlanningInput에서 9제품/공유 SAW1/동시 LB1/모델 버전·배치 SHA/digest를 대조한다. 현재 이 단계는 **미실행**이다.

## 변경 파일·검증 범위

추가한 `scripts/verify_synthetic_contracts.py`는 DB 접속 기능이 없는 오프라인 API 검증 도구다. 상세 진단은 ignored `.artifacts/synthetic_validation.json`에 저장한다. `backend/tests/test_synthetic_contracts.py`는 담당자 생성기를 수정하지 않고 임시 디렉터리로 출력을 돌려 9개 정상·6개 오류·원시 거래·공유/동시 자원 계약을 재현한다. 생성 데이터가 없는 새 checkout에서도 실행된다.

백엔드 운영 파서/승인/DB 계약의 결함은 이번 검증에서 발견되지 않아 변경하지 않았다. 알고리즘·frontend·기존 migration도 변경하지 않았다. 실제 DB 환경 미확인 및 시나리오 격리 부재를 성공으로 간주하지 않는다.

검증 명령과 결과:

| 검증 | 실제 결과 |
|---|---|
| generate.py | exit 0, 생성기 자체 raw/거래/재고/변환 일치 검사 통과 |
| 독립 convert.py 재실행 | 9/9 업로드 CSV 바이트 동일 |
| verify_synthetic_contracts.py | 정상 9/9 오프라인 API 계약 통과, 인메모리 승인 9건, 재업로드 9/9 차단 |
| 신규 단위 테스트 | 16 passed / 0 failed / 0 skipped |
| 전체 `pytest --no-db` | **526 passed / 0 failed / 55 skipped**, deprecation warning 1건 |
| TypeScript / Vite build | 모두 통과, frontend 파일 수정 없음 |
| OpenAPI·Schema·응답 예시 동기화 | 전체 pytest에 포함해 통과, 운영 API 계약 변경 없음 |
| pip check / security_check.py | 의존성 문제 없음 / findings 0 |
| 문서 링크·생성 자료 미추적 | 링크 및 `.gitignore` 확인 |

실제 DB 대상 재식별/기존 키·기간 SELECT/실제 업로드 승인/PostgreSQL 건수/실제 예측 UUID·PlanningInput/DB 브라우저 E2E는 **미실행**이다. 기존 초기화 pytest 55개는 통과 수에 포함하지 않았다. 합성 시나리오의 실제 DB 통합 목표는 보류 상태이며 Docker 복구만으로 자동 승인하지 않는다.
