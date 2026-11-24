# 생산계획 엔진 활성화와 인수 검증

2026-11-24 KST · Docker/PostgreSQL이 없는 보조 PC · 시작 `main` [`ec3a0d3`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/ec3a0d3) · 이희원 어댑터 [`2adab58`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/2adab58)

`engine.planning.AVAILABLE=True`로 전환했다. `POST /plans`와 `/plans/what-if`는 승인 입력 또는 저장된 부모의 스냅샷으로 실제 엔진을 실행하며 `persisted=false`를 반환한다. `POST /plan-executions`도 같은 사전검증과 실제 계산을 호출한다. 기존 승인 출처·단위·범위·데이터셋 검증과 정식 `APPROVE` 차단을 유지한다. 계산 코어와 팀 어댑터는 이희원 버전을 사용한다.

## 공식 합성 3개월 Preview

원본은 공식 `CHUNGPAMO-2027` CSV를 조립한 버전 고정 [PlanningInput](../modules/planning_engine/tests/chungpamo/planning_input.json)이다. TestClient에서 승인 입력 제공자만 대체하고 실제 모듈 로더와 엔진을 호출했다. 2027년 1~3월, 제품 9개·예측 27행의 응답은 HTTP 200, 계산 `OK`였다. 제약 **306개**, 생산 **81행**, 자재 **81행**의 총소요·가용·발주 필요량을 [독립 정답](../modules/planning_engine/tests/chungpamo/expected.json)과 대조했다. C05에 따라 안전재고 판정의 음수 사용값은 계약 출력에서 0이다.

| 계획안 | 판정 | 생산 합계 | 근거 |
| --- | --- | ---: | --- |
| 기준형 | `UNVERIFIED` | 93,481 EA | 결품 0. 자재·월 18건에 신규 발주 필요 `PROCUREMENT_REQUIRED` |
| 안정형 | `INFEASIBLE` | 96,583 EA | 결품 3,612 EA. `STOCKOUT` 18개 제품·월 |
| 비용절감형 | `INFEASIBLE` | 88,225 EA | 결품 2,005 EA. `STOCKOUT` 17개 제품·월 |

승인 입고 1행을 포함한 공식 입력의 `missing_inputs`와 결과 공통 `unverified`는 비어 있다. `scheduled_receipts=[]`는 확인된 공급에 적용할 발주가 없다는 뜻이다. `null`은 `RECEIPT_SOURCE_UNAVAILABLE`을 공통 미검증에 한 번 남기고 어느 후보도 `FEASIBLE`을 반환하지 않는다. 두 경우 모두 1월 `MR-N3` 기준형 가용량이 공식 입고 포함 실행보다 10,000 kg 적었다. 부족 자재에 대한 발주 필요 판정은 후보별 평가에서 확인한다. 완전한 별도 소규모 입력은 1·3·6·12개월 모두 `FEASIBLE`을 유지했다. [입고 예정 정책](../modules/planning_engine/PLANNING_RULES.md#51-입고-예정-sr-희원-결정-2026-11-22)

## 계약과 오류 구분

| 조건 | 입력 진단과 후속 실행 |
| --- | --- |
| BOM·라우팅 모두 월 전체 승인 버전 하나 | 진단에서 준비로 표시한다. 월 경계의 버전 변경을 허용하며 `*_VERSION_SELECTED`에 제품·월·버전을 남긴다. |
| 월 중간에 새 버전이 시작하거나 끝남 | 진단 `*_VERSION_MIDMONTH`, 실행 422 `UNSUPPORTED` |
| 월 전체에 유효한 승인 버전 둘 이상 | 진단 `*_VERSION_AMBIGUOUS`, 실행 422 `INPUT_INVALID`. 월 중간 문제가 함께 있어도 오류 모두 유지 |
| 라우팅 버전 내부 단계의 유효기간 혼합 | 해당 버전의 단계 전체를 보존해 진단 `ROUTING_STEP_VALIDITY_MIXED`, 실행 422 `UNSUPPORTED` |
| 해당 월에 유효 후보가 없음 | `BOM_COVERAGE`/`ROUTING_COVERAGE`를 엔진에 전달한다. 엔진은 후보별 영향을 `BOM_MISSING`/`ROUTING_MISSING`으로 설명한다. |
| 재고·시간예산 누락 | 선택된 BOM과 라우팅에 필요한 범위만 계산한다. 누락 코드는 진단·실행에 같은 값이 들어가고 `FEASIBLE`을 막는다. |
| 필수 예측 범위·승인 출처 불일치 | 409 `PLAN_INPUT_UNAVAILABLE`과 `reason`. 잘못된 요청·What-if 키는 422, 다른 데이터셋의 예측·부모 조회는 404 |
| 저장 또는 승인 입력 조회 비활성 | 501 `PERSISTENCE_DISABLED`. 모듈 비활성의 501 `MODULE_NOT_IMPLEMENTED`와 구별 |
| 엔진 출력이 모순되거나 누락 근거를 잃음 | 500 `MODULE_ERROR`. 같은 코드·참조의 중복 근거도 거부한다. |

진단의 입력 지문과 계산 지문은 동일 승인 사실·요청에서 일치한다. 과거의 `*_VERSION_POLICY_REQUIRED` 및 `POLICY_NOT_CONFIRMED` 안내는 새 계산에서 누락으로 간주하지 않는다. 정식 `APPROVE`는 501 `PLAN_APPROVAL_DISABLED`이며 계산·저장과 독립적이다. [생성된 실제 계산 예시](../contracts/examples/responses/41_plan_preview.json) · [입력 진단 예시](../contracts/examples/integration/planning_input_diagnostics.json)

## 보조 PC 실행 결과

- `pytest --no-db -q --tb=short` **1,239 passed / 0 failed / 68 skipped**. OpenAPI·JSON Schema 및 생성 응답 예시 검사를 포함한다. 기존 Starlette/httpx 경고 1건이다.
- `pip check`, `npm run type-check`, Vite 프로덕션 빌드 통과. 저장 비활성 오류와 DEMO 경계 등을 본 비DB Playwright **8개 통과**.
- 변경 파일 휴리스틱 보안 검사 발견 **0건**. 전체 트리의 기존 합성 자료 등 203건은 이번 변경에 포함되지 않는다.
- 초기 테스트 실행에서 기존 엔진 비활성 단언과 현재 분류 화면의 사라진 테이블 선택자를 확인해 새 계약과 표시 기준으로 갱신했다.

## Docker PC 인계

### 개발 DB 읽기 전용 Preview

1. 기존 개발 PC에서 승인된 컨테이너·볼륨·포트와 연결 대상 `chungpamo`, 역할 `chungpamo_app`, revision `0009`를 먼저 확인한다. 기존 `.env`는 로컬에서 사용한다.
2. 루트에서 아래 명령을 실행한다. 첫 연결부터 PostgreSQL 세션을 READ ONLY로 설정한다. 공식 데이터셋의 승인 예측·제품 및 월 범위, 승인 출처, BOM·라우팅, 재고·시간예산·수량한도와 입고 원장 상태를 진단한다. `CHUNGPAMO-2027`은 2027-01~03, `TISSUE-LEGACY`는 2027-01이다. 스크립트는 기존 공식·LEGACY 데이터와 각각의 검증 대상 예측이 하나인 상태를 확인한다. 데이터가 달라졌으면 대상 승인 예측을 읽기 전용으로 식별한 뒤 범위를 재확인한다.

   ```powershell
   .\.venv\Scripts\python.exe scripts\verify_readonly_dataset_api.py
   ```

3. `.artifacts/readonly_dataset_api.json`의 입력 및 후보 상태와 누락·오류 사유를 기록한다. 적합한 참조는 `/plans`의 실제 Preview를 실행한다. 누락 공급의 `UNVERIFIED` 또는 다른 제약 모순에 따른 `INFEASIBLE`, 월 중간 변경의 `UNSUPPORTED`, 승인 예측 범위의 `PLAN_INPUT_UNAVAILABLE`은 관찰값을 그대로 남긴다. `persisted=false`와 동일 입력 지문, 개발 DB 전후 테이블·스키마 객체·예측·승인 배치 지문 일치를 확인한다. 현재 보조 PC에서는 이 절차와 지문 비교를 실행하지 않았다.

### 전용 회귀 DB에서 BASE·WHAT_IF 저장

1. 쓰기 전 `chungpamo_regression` 전용 역할, 별도 자격 증명, sentinel, revision `0009`, 대상 스키마와 기존 행을 읽기 전용으로 검사한다. 사용할 공식 합성 seed와 fixture의 초기화·삭제 범위를 알려 별도 실행 승인을 받는다. 기존 개발 DB는 쓰기 대상에서 제외한다.
2. 승인 후 기존 회귀 DB 가드와 환경 변수를 설정한 다음, 아래 **단일 테스트**를 실행한다. 이 테스트는 전용 DB의 기존 `test_engine` fixture 초기화·정리를 사용한다. 데이터가 있거나 승인 범위가 다르면 중단한다.

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q backend/tests/test_db_dataset_e2e.py::test_actual_plan_preview_and_storage_on_regression_db
   ```

3. Preview 후 이력 건수 불변, BASE와 WHAT_IF 각각 신규 `201`·동일 요청 `200`, 부모 결과와 지문 보존, 실제 저장에서 대역 격리, 타 데이터셋 `404`를 확인한다. 초기화·정리 범위와 결과를 독립 SQL로 대조하고 개발 DB 전후 지문을 다시 비교한다.

비DB에서 BASE·WHAT_IF의 `201`·`200`, 동일 Preview/저장 결과, 부모 지문·공급 원본 불변을 실제 계산과 메모리 저장소로 확인했다. PostgreSQL 저장에는 별도 검증이 남아 있다. 기존 승인 입고 원장과 공급 reader 연동은 백엔드 데이터 출처 작업이다. 현 합성 입력 검증에서 추가로 요청할 이희원 계산 변경은 발견되지 않았다.
