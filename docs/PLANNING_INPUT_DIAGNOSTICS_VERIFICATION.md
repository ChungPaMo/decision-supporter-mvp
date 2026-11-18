# 계획 입력 진단 API와 통합 검증

2026-11-18 (KST), 보조 개발 PC. 시작 `main`은 [`231bcb2`](https://github.com/ChungPaMo/decision-supporter-mvp/commit/231bcb262c98e764349fc54e5c3c6706e083f46f)다. B01~B03의 출발점은 [통합 준비 보고서](PLANNING_ENGINE_INTEGRATION_READINESS.md)다.

## B01 — 요청과 응답

`POST /planning-inputs/preview?dataset_id=CHUNGPAMO-2027`에 아래 JSON을 보낸다. 예시 UUID는 해당 데이터셋의 실제 저장 예측 UUID로 교체하고 선택 제품과 예측 월을 맞춘다. `dataset_id`는 query를 따르며 생략 시 `TISSUE-LEGACY`다. body에 명시한 값은 query와 같아야 한다.

```json
{
  "forecast_execution_id": "00000000-0000-4000-8000-000000000001",
  "product_ids": ["CP-GIFT-12"],
  "target_month": "2027-01",
  "as_of_date": "2026-12-31",
  "scenario": "BASE"
}
```

응답 `PlanningInputDiagnostics`는 dataset/예측 UUID/대상 월/기준일, `scope=SINGLE_MONTH`, 유형별 `ready`/`row_count`, `missing_inputs`, `warning_codes`, 승인 배치 식별 정보, `forecast_input_digest`, `input_digest`, `engine_available`, `persisted=false`를 반환한다. [OpenAPI](../contracts/openapi.json) · [JSON Schema](../contracts/schemas/module_interfaces_draft.json) · [합성 응답 예시](../contracts/examples/integration/planning_input_diagnostics.json)

- `INPUTS_PRESENT`는 현재 단일 월 조회 범위의 자료가 있고 추가 확인이 필요한 입력 모호성이 없다는 뜻이다. `POLICY_NOT_CONFIRMED`는 항상 유지한다. `NEEDS_REVIEW`는 누락이나 BOM/Routing 버전·월중 유효성, 여러 재고 시점 등의 확인 항목이 있다는 뜻이다.
- `engine_available`은 `engine.planning.AVAILABLE` 표시다. `INPUTS_PRESENT`와 엔진 플래그로 생산 가능성, 실행 성공 또는 승인 자격을 판단할 수 없다. 진단은 예측 재생성, 계산, 이력 저장, 승인 호출 없이 기존 provider로 읽는다.
- 유형별 `row_count`는 스냅샷에 포함된 행 수다. 제품·자재 등의 승인 마스터와 승인 출처에는 선택하지 않은 품목 자료도 포함될 수 있다. `bom`은 헤더 수이며 `inventory`는 기준일 이하의 후보 행 수다. CAPA는 중복을 제거한 자원 수, 월별 시간예산 수, 선택 제품 수량한도 수를 구분한다. 수량한도는 선택 입력이므로 `0`행이어도 `ready=true`이며, 무제한 생산을 뜻하지 않는다. 필요한 시간예산 누락은 별도 표시한다.
- `input_digest`는 기존 계획 Preview와 동일한 방식으로 입력 전체를 해시한 값이다. 진단 응답의 요약과 지문은 검토에 쓰며 후속 실행을 고정하는 토큰이 아니다. 다음 요청 시 승인 자료가 바뀔 수 있다. 원본 파일·예측 수량·마스터 원문은 이 응답에 포함하지 않는다.

## B02 — 공통 입력 검증과 오류 계약

SQL provider는 기존 데이터셋 스키마와 `REPEATABLE READ` / `READ ONLY` 트랜잭션을 사용한다. 예측이 성공 또는 PARTIAL이고, 선택 제품마다 요청 월의 행이 하나씩 있어야 한다. 스냅샷의 배치는 같은 dataset의 `APPROVED` 및 검증 차단 오류 0건이어야 한다. 저장 예측이 가리키는 수요 배치의 version, SHA-256, result digest, approved_at을 일치시킨다. LEGACY도 대조하되 기존 집계·지문 호환성을 위해 계획 스냅샷의 승인 출처에 수요 배치를 추가하지 않는다. 다른 데이터셋은 기존대로 예측 수요 출처를 포함한다. 신규 원본 파일 바이트 재해시나 새 이력 저장은 이 검증에 포함되지 않는다.

순수 검증은 SQL provider와 계산 어댑터, 진단에서 재사용한다. 승인 출처 유형, 제품·예측 범위 및 단위, BOM 제품·구성품과 단위/유효 기간, 재고 품목·단위·기준일, CAPA 월·제품 단위, Routing 제품·단위·월 중첩을 확인한다. 자원·시간 기준·동시 요구·선행 공정은 기존 `CapacityRegistrationDraft`가 확인한다. `as_of_date`는 재고 조회 상한이며 과거 승인 상태 복원이 아니다. 여러 재고 시점 중 하나를 임의로 고르거나 BOM·라우팅 정책을 새로 정하지 않는다. 진단에서 보고하는 커버리지·모호성은 입력 계약을 확장하거나 저장된 이력의 지문을 변경하지 않는다.

| HTTP | `detail.code` | 의미 |
| --- | --- | --- |
| 200 | 해당 없음 | 현재 범위의 입력 요약. 누락·경고 확인 필요 |
| 404 | `FORECAST_NOT_FOUND`, `DATASET_NOT_FOUND` | 없는 예측 또는 다른 dataset의 예측은 같은 404. 없는 dataset도 기존 404 |
| 409 | `DATASET_MISMATCH`, `DATASET_INACTIVE`, `PLAN_INPUT_UNAVAILABLE` | 명시 scope 불일치/보관 dataset, 필요한 제품·월 예측 누락, 출처 충돌, 손상/참조/단위/기간 오류. `details.reason`이 있는 경우 원인 분류에 사용 |
| 422 | `REQUEST_INVALID`, `DATASET_INVALID` | 잘못된 DTO/날짜/월/UUID/scope 형식 또는 What-if 진단 요청 |
| 500 | `PERSISTENCE_ERROR`, `MODULE_ERROR` | 저장소 읽기 또는 입력 조립 장애. 내부 예외 및 자격정보 비노출 |
| 501 | `PERSISTENCE_DISABLED` | 저장 예측을 읽을 수 없는 서버 설정. 엔진 미구현만으로 진단은 501을 반환하지 않음 |
| 503 | `DB_UNAVAILABLE` | 필요한 저장소 연결 장애 |

기존 `/plans`, `/plans/what-if`, `/plan-executions`의 계산 게이트는 그대로 적용된다. 정상 스냅샷 진단으로 계획 실행 저장 또는 계획 승인 경로가 열리지 않는다.

## B03 — 희원님과 확정할 계약과 인수 테스트

| 항목 | 현재 계약에서 확인한 범위 | 합의·후속 변경 요청 |
| --- | --- | --- |
| C01 기간 | `target_month` 하나, 예측·예산·출력도 같은 월. 공식 3개월 조회는 각각의 단일 월 조립 | horizon의 명시 방식과 월별 재고 이월 확정. DTO·provider·저장/출력·What-if·화면을 함께 변경 |
| C02 예정 입고 | 승인 entity·PlanningInput 필드 없음. extra 필드는 거부 | 입고 ID, 품목, 수량과 기준 단위, 예상일, 잔량/부분 입고/취소, 중복 키, 월 경계·기준일을 정의하는 초안. 기존 배치 검증·명시적 승인 후 같은 dataset에서 출처/버전/지문과 함께 조회하도록 설계 |
| C03 What-if | 기존 저장 부모의 dataset, forecast, 제품, 월, 기준일 고정. 현재 허용된 키는 `production_qty.<product>`와 `overtime_hours_limit.<capacity>` | 재고·입고·수요 변경 여부, 월별 키, 후보 범위와 절대값/증감 입력 표현 합의 |
| C04 정책 | policy snapshot은 비어 있고 `POLICY_NOT_CONFIRMED` 유지 | v0.2/v0.3의 배분·선행 생산·결품·잔업·셋업 등 적용 기준과 버전/선택·예외의 기록 방식 확정 |
| C05 자재 부호 | `available_qty`, `shortage_qty`는 비음수 DTO/DB 제약 | 가용·누적 부족·부족 해소·순증감을 어느 필드에 담을지 합의. DTO/DB/Excel/화면 표시와 정답을 함께 설계 |
| C06 HARD/SOFT | 순수 출력 DTO에 `FEASIBLE + HARD VIOLATED` 검증 공백. 저장에는 입력 미확인 시 FEASIBLE 금지. 형식상 FEASIBLE이어도 정식 승인 정책은 별도 | HARD 위반/미검증과 SOFT 위반이 계산 판정과 승인 자격에 미치는 영향을 각각 확정 |
| C07 누락 제품 | 선택 제품/월 예측 누락 시 409 | 제외/PARTIAL을 허용할 경우 제품 및 월 범위와 표시 합의. 0 수요 대체 금지 유지 |
| C08 BOM·재고·Routing | 유효기간 후보와 다중 재고 시점 보존. 진단은 모호성 표시 | 선택 기준일, 재고 대표 시점, 다단계 BOM·월중 변경/동시 자원 계산 정책 확정 |
| C09 추천·KPI·비용 | typed 계획 출력에 추천 후보/KPI 항목이 없고 비용 입력 미연결 | 지표·산식·통화·미산출/추천/선택 표현 합의 후 버전 확장 |
| C10 후보 선택 | 후보 ID는 실행 내에서만 유일. What-if는 부모 실행 ID를 지정 | 단일 후보/전체 후보 조정 여부, 부모 후보 ID와 검토·승인 화면의 식별 범위 합의 |
| C11 일관성 | 신규 입력 공통 검증 적용. 결과는 저장 경로가 추가 자재/자원/범위 검증 수행 | 출력 정합성 공통화는 기간·결과 정책 합의 후 적용. 기존 저장 계약 예시의 호환성 검증 포함 |

| 인수 테스트 사례 | 현재 동작·근거 | 합의 후 검증할 조건 |
| --- | --- | --- |
| FEASIBLE + HARD VIOLATED | `PlanningOutput`이 조합 자체를 일률 거부하지 않음 | 동일 후보의 강제 제약 위반과 feasibility가 모순될 때의 계약 및 오류를 확정한 뒤 응답·저장에 같은 기준 적용 |
| HARD UNVERIFIED | DTO는 미확인 상태를 표현. 승인 조건은 충족되지 않음 | 미확인 원인과 범위를 보존하고 실행 결과·승인 자격에서 어떻게 처리할지 확인 |
| SOFT VIOLATED | DTO는 조합 표현 가능. 현재 정식 승인은 SATISFIED/APPLIED 요구 및 501 비활성 | 계산 판정과 승인 경고/차단의 합의된 조건을 각각 시험 |
| 음수 자재 가용 증감 | 예를 들어 가용 5→2의 차이 `-3`은 현재 `available_qty` DTO 거부 | 잔액/순증감 의미와 승인된 출력 필드를 확정하고 부호를 임의 변경하지 않음을 검증 |
| 누적 부족량 감소 | 누적 부족 10→4의 차이 `-6`은 현재 `shortage_qty` DTO 거부 | 누적 부족 감소/해소량 표현과 화면·Excel 일치 검증 |
| 3개월 입력의 월별 공유 자원 | horizon 추가 필드 거부. 현행은 단일 월 | 여러 제품의 동일 자원을 월별로 합계하고 타 월과 혼합하지 않으며 재고 이월을 반영하는 합의된 공식·정답 비교 |
| 예정 입고 미승인 | 예정 입고 DTO/승인 입력 경로 없음 | 미승인·반려/취소·다른 dataset 입고를 계산에서 제외하고 승인된 입고만 출처와 함께 사용 |
| What-if 대상 월 불일치 | 기존 부모 스냅샷과 월이 다르면 409 | 현재 단일 월 회귀 유지. horizon 합의 후 선택 월/후보 범위 오류와 불변 부모 재현 검증 |

합의가 필요한 기대값은 명세에 남겼다. 현재 API와 DTO의 확정된 동작만 이번 코드 회귀 시험에 포함한다.

## 비DB 검증 결과

Windows Python 3.11.9에서 실행했다. SQL provider의 연결·조회 경계와 별도의 typed `PlanningInput` provider를 대역으로 검증했다. 공식 합성 자료의 기존 입력·예측 증거는 11/17 보고서에 보존돼 있다. 이번 신규 API 시험은 작은 계약 fixture를 사용했다.

저장소 루트에서 아래 명령을 실행했다.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest --no-db -q -k 'not (test_columns_match_models or test_status_check_matches_enum or test_gate_objects_are_generated or test_entity_check_matches_supported_entities)'
```

**978 passed / 0 failed / 66 skipped / 6 deselected**, 18.12초. 66개는 DB 접속 차단으로 건너뛰었고 6개는 `alembic upgrade ... --sql`을 호출하는 오프라인 SQL 생성 검사여서 선택에서 제외했다. 기존 Starlette/httpx deprecation 경고 1건이 있다. 진단 성공·누락·모호성, 데이터셋 범위/타 UUID, 출처 변조/미승인, 단위·기간·자원 검증, `persisted=false`·실행 생성 금지, 기존 계산 501, OpenAPI·JSON Schema·예시 동기화가 통과했다.

초기 집중 실행은 78개 통과했다. 이후 첫 백엔드 중심 실행은 OpenAPI 생성 시 기존 enum 순서와 새 경로의 가이드 누락으로 2건 실패했다. 기존 생성기 순서로 다시 생성하고 화면 인계를 추가해 최종 루트 회귀에서 두 검사를 통과했다. Docker·PostgreSQL과 Alembic 실행, 브라우저와 실제 계획 계산은 미실행이다.

저장소 보안 검사에서 탐지 0건, `pip check`에서 의존성 오류 0건을 확인했다.

## 기존 개발 PC 검증과 화면 인계

**김대영, 기존 개발 PC:** 11/17에 개발 0009와 공식 자료의 기존 읽기 조립이 확인됐다. 새 진단 경로는 별도 검증 대상이다. 전용 환경·현재 revision과 기존 공식 자료/예측 UUID를 확인한 뒤 1~3월 각각의 GET 예측과 POST 진단을 읽기 전용으로 비교한다. 공식 자료를 중복 등록하지 않는다. 기존 `TISSUE-LEGACY`와 `CHUNGPAMO-2027`의 범위, 타 dataset UUID의 404, 승인 출처 일치, 월별 CAPA/Routing과 Digest 안정성을 확인하고 실행·배치·예측 수 및 보존 지문을 전후 대조한다. 승인/지문 변조·누락을 실제로 주입하는 검증은 보존 DB와 격리된 승인된 시험 환경에서만 수행한다. [11/17 실DB 기록](POSTGRESQL_INGESTION_E2E_VERIFICATION_20261117.md)

**정마나미:** 선택 dataset·저장 예측·제품·대상 월·기준일 변경 시 이전 진단 응답을 폐기한다. `INPUTS_PRESENT`는 현재 입력 범위의 자료가 있다는 문구로 표시하고, `NEEDS_REVIEW` 및 `POLICY_NOT_CONFIRMED`는 항목별 경고로 표시한다. `engine_available`, `persisted=false`, 실행·저장·승인 상태는 각각 표시한다. 404/409/422/501/503은 `detail.code`로 처리하고 테스트/DEMO 결과로 대체하지 않는다. 화면 구현은 담당자 인계다.
