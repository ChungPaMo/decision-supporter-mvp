# 생산계획 v0.4 백엔드 계약과 팀 인계

2026-11-22 KST, 기존 개발 PC. 시작 `main`은 `5c65cf38986fb1a5804f357bdb52efed33e2d650`이다. 이 문서는 이전 통합 준비 및 진단 보고서의 단일 월 설명에 대한 후속 계약이다. [기준 커밋](https://github.com/ChungPaMo/decision-supporter-mvp/commit/5c65cf38986fb1a5804f357bdb52efed33e2d650) · [희원 요청](../modules/planning_engine/CONTRACT_REQUESTS.md) · [계산 규칙 v0.4](../modules/planning_engine/PLANNING_RULES.md)

| 요청 | 이번 구현 범위 | 남은 작업 |
| --- | --- | --- |
| C01 | 연속 1~12개월 요청, 승인 스냅샷·진단, 공통 출력 범위 검증, 기간 포함 입력 지문·저장 조회·XLSX | 실제 엔진 변환부와 브라우저 연계. 6·12개월의 정상 출력을 확인하려면 해당 기간을 포함하는 저장 예측 필요 |
| C02 | 승인 예정 입고 DTO·공급 경계·잔량과 범위 검증, 미연결 상태 표시 | 승인 원장 스키마·등록/변경/승인 이력·운영 SQL reader는 별도 개발 및 검증 필요 |
| C03 | What-if 키·값·부모 범위 검증, 부모 사실과 결과 재사용 | 엔진 변환부에서 세 후보 재계산·비교 응답 연결 및 실제 저장 검증 |
| C06 | 모순 feasibility 검증과 Preview/저장/상세 공통 출력 검사 | 실제 엔진 출력 검증. 정식 승인 HTTP 501은 서버 인증·역할·승인 정책 확인 후 별도 연계 |

## C01 기간과 이전 호출 호환성

`target_month`는 시작 월, `horizon_months`는 연속 월 수다. `PlanCommand`와 `/planning-inputs/preview`, `/plans/what-if`, `/plan-executions`의 기본값은 3이다. `/plans`는 기존 LIVE 화면의 단일 월 요청을 보존하기 위해 기간 생략 시 1을 쓰며 명시값은 1~12를 받는다. 기존 1개월 호출자와 What-if 클라이언트는 `horizon_months: 1`을 명시하고, 새 화면은 선택값을 모든 엔드포인트에 명시한다. 다음 예시의 UUID는 같은 데이터셋에 저장된 예측 ID로 교체한다. [OpenAPI](../contracts/openapi.json) · [공통 Schema](../contracts/schemas/module_interfaces_draft.json)

```json
{
  "dataset_id": "CHUNGPAMO-2027",
  "forecast_execution_id": "00000000-0000-4000-8000-000000000001",
  "product_ids": ["CP-GIFT-12"],
  "target_month": "2027-01",
  "horizon_months": 3,
  "as_of_date": "2026-12-31",
  "scenario": "BASE"
}
```

SQL provider는 하나의 `REPEATABLE READ`·`READ ONLY` 트랜잭션에서 선택 제품×월 예측, 전 기간 CAPA 예산·한도, 기간 중첩 BOM·Routing 후보 및 기준일 이하 재고를 읽는다. 월별 버전 선택과 재고 이월은 엔진의 책임이다. 월별 후보가 비거나 버전이 모호하면 진단 상태를 표시한다. 예측이 부족하면 HTTP 409 `PLAN_INPUT_UNAVAILABLE`과 `details.reason=FORECAST_PRODUCT_MONTH_COVERAGE`를 반환한다. 테스트는 1·3·6·12개월과 연도 경계 및 제품×월 누락을 다룬다. [SQL 입력](../backend/app/integrations/planning.py) · [범위 검증](../backend/app/integrations/planning_validation.py)

OK 후보의 생산행에는 요청 제품×월마다 정확히 한 행이 필요하다. PARTIAL의 생산행과 자재·제약 평가는 모두 요청 범위 안이어야 한다. 0007은 `target_month` 형식만 검사하며 후보와 자재·제약 행을 같은 월에 묶는 CHECK가 없다. 기간은 기존 JSONB `input_snapshot.command.horizon_months`에 보존하고 목록·상세에서 읽는다. 기존 필드 없는 행은 1개월로 복원하되 읽은 원본 JSON으로 지문을 검증한다. 저장된 입력을 조회 응답에서 정규화하므로 UI는 digest를 재계산하지 않고 서버값을 사용한다. XLSX `Overview`에 기간 길이 및 종료 월을 추가했다. [저장소](../backend/app/plans/repository.py) · [현행 DDL](../backend/migrations/versions/0007_plan_execution.py)

## C02 승인 예정 입고

`PlanningInput.scheduled_receipts`는 `list[ScheduledReceipt] | null`이다. `null`은 승인 공급 미연결, `[]`는 검증된 공급원에 계획 범위에 해당하는 미입고 발주가 없음을 뜻한다. 클라이언트의 `PlanCommand`에는 이 필드가 없다. 각 발주의 `batch_id`는 `approved_inputs.sources`의 `scheduled_receipt` 배치에 대응한다. 공급 경계에서 같은 dataset의 APPROVED·차단 오류 0·result digest 존재 여부를 확인하고, 입력에 배치의 version·원본 SHA·result digest·승인시각을 보존한다. [공급 경계](../backend/app/integrations/planning_receipts.py) · [DTO](../contracts/interfaces/planning.py)

```json
{
  "po_id": "PO-EXAMPLE-1",
  "material_id": "MR-N3",
  "open_qty": "8000",
  "unit": "kg",
  "expected_date": "2026-12-31",
  "supplier_id": "SUP-EXAMPLE",
  "batch_id": "00000000-0000-4000-8000-000000000002"
}
```

예시 배치는 입력 형식 설명용이다. 운영 공급자는 같은 읽기 트랜잭션에서 발주당 승인된 현재 행 하나를 제공해야 한다. 부분 입고 시 주문량에서 누적 입고량을 빼며, 완전 입고·취소는 제외한다. 과입고·발주 중복·타 데이터셋·미등록 자재·단위 불일치를 거절한다. 날짜는 달력 날짜다. 기준일 당일 또는 이전에 남은 수량은 첫 계획 월과 `RECEIPT_OVERDUE`에 해당한다. 기준일 뒤이면서 시작 월보다 앞선 입고도 첫 달에 귀속한다. 이후에는 해당 월에 넣고 종료 월 뒤의 발주는 제외한다. 희원님은 원래 예정일을 사용해 실제 계산의 자재별 첫 월 MAT를 `UNVERIFIED`로 표시해야 한다. 진단에서는 관련 BOM의 지연 발주를 `RECEIPT_OVERDUE`로 보고한다.

0009에는 발주·입고 예정 승인 entity 및 원장 테이블이 없다. 현재 SQL provider의 운영 인스턴스에는 reader가 연결되어 있지 않으므로 진단은 `scheduled_receipts.ready=false`와 `RECEIPT_SOURCE_UNAVAILABLE`을 반환한다. 공식 `derived/scheduled_receipts.csv`는 합성 정답 재료다. 실제 공급을 연결하려면 발주 스냅샷·접수/취소 이벤트의 승인 순서와 이력 식별, 부분입고의 중복 차감 방지 및 해당 기준일 의미, dataset별 FK·배치 승인·원본 SHA/digest·읽기 view를 설계하고 별도 승인으로 migration과 저장 검증을 진행한다. 이번 DTO/공급 경계의 정상 입고 사례는 대역으로 검증했다.

## C03 What-if 계약

`POST /plans/what-if`는 Preview, `POST /plan-executions`는 실행 저장 경로다. 부모 UUID는 저장된 실제 실행이고 동일 dataset, forecast UUID, 제품 집합, 시작 월·기간·기준일과 성공/PARTIAL 상태가 필요하다. 부모의 원본 사실·승인 출처·결과 지문을 저장된 그대로 읽는다. 자식은 override를 새 command에 담는다. 0 수량 취소도 승인 원본에 반영되지 않는다. 제품별 배수는 전체 배수를 대체하며, 월별 잔업은 절대값이다. [What-if 스냅샷](../backend/app/plans/service.py) · [계산 코어](../modules/planning_engine/what_if/core.py)

```json
{
  "forecast_execution_id": "00000000-0000-4000-8000-000000000001",
  "product_ids": ["CP-GIFT-12"],
  "target_month": "2027-01",
  "horizon_months": 3,
  "as_of_date": "2026-12-31",
  "scenario": "WHAT_IF",
  "base_plan_execution_id": "00000000-0000-4000-8000-000000000003",
  "overrides": {
    "demand_multiplier": "1.1",
    "demand_multiplier.CP-GIFT-12": "0.9",
    "overtime_hours_limit.SAW1.2027-02": "80",
    "receipt_qty.PO-EXAMPLE-1": "0"
  }
}
```

허용된 네 키 형태만 받는다. 기존 `production_qty.*` 및 capacity ID 기반 잔업 키는 422다. 키의 제품·자원·발주 ID에는 점 구분자를 사용할 수 없다. 모르는 제품·자원·발주, 기간 밖 월, 잘못된 키는 `PLAN_OVERRIDE_UNSUPPORTED`와 `details.status=INPUT_INVALID`·`details.reason=WHATIF_INVALID`다. 잘못된 Decimal 문자열은 `REQUEST_INVALID`의 필드 메시지에서 `WHATIF_INVALID`로 구분한다. 자원·발주 실제 존재 확인은 부모를 로드할 수 있을 때 이루어진다. 위 예시의 취소는 승인된 입고가 스냅샷에 있는 경우에만 유효하다. 엔진은 세 후보를 한 번에 재계산하며, 부모 비교에는 저장된 부모 결과를 사용한다. 자식에서 조정된 입력과 부모의 저장된 조건을 합성해 누적 변경을 구현하려면 별도 계약 결정이 필요하다.

## C04~C11과 시험 기대값

- 희원님은 `engine.planning.run(PlanningInput) -> PlanningOutput` 변환에서 `command.months`, 제품×월 예측, 같은 월 순서의 시간예산·한도, 월별 유효 BOM·Routing 및 승인된 입고를 사용한다. 현재 core는 `len(months)`로 내부 배열을 다루지만 `bom`·`routing`은 제품별 정적 map이다. 월중·월별 버전이 달라지는 경우에 조용히 첫 버전을 적용하면 안 된다. 월별 표현을 지원하거나 해당 사례를 명시적 미지원으로 회신한다. 내부 `material`은 공개 `material_id`에서 변환하며 시간 값은 원 단위를 보존하거나 h로 일관되게 환산한다. 기존 정답은 3개월이며 팀 계약 변환부의 1·3·6·12개월 인수 시험은 후속이다. [계산 코어](../modules/planning_engine/engine/planning_core.py) · [실행 진입점](../modules/planning_engine/engine/planning.py)
- C04 서버 `policy_snapshot` 및 공식 승인 정책은 아직 비어 있다. 계산 규칙 `PLANNING_RULES-v0.4`의 `policy_ref`는 엔진 산출 근거다. 입력 미확인 상태인 스냅샷에서는 FEASIBLE 결과를 반환할 수 없다. C07 예측 누락은 입력 충돌, C08 재고 후보·월별 BOM/Routing 후보는 그대로 보존한다. C09 KPI 확장 없음. C10 후보는 `execution_id + plan_id`, What-if의 단위는 부모 실행 전체다.
- C05 수량은 비음수로 유지한다. `required_qty`는 그달 총소요, `available_qty`는 월초 재고와 그달 입고 합, `shortage_qty`는 그달 신규 발주 필요량이다. 0과 산출 불가 `null`을 구분한다. `PlanningOutput.material_requirements`와 XLSX MRP를 같은 뜻으로 표시한다.
- C06/C11 `FEASIBLE` 후보에 HARD VIOLATED 또는 HARD UNVERIFIED가 있으면 실패한다. 명시적 SOFT 평가는 계산 feasibility와 공존할 수 있으며 승인 자격 판단은 별도다. 강도 없는 SATISFIED는 역사적 계약으로 허용하고, 강도 없이 VIOLATED/UNVERIFIED이면 FEASIBLE을 거절한다. 정책 참조가 비거나 후보별·전체 `unverified`가 있으면 FEASIBLE을 거절한다. 다른 후보에 귀속된 위반만으로 해당 후보를 차단하지 않는다. Preview·저장·상세는 공통 검사를 사용하고, 공식 승인은 별도 SATISFIED/APPLIED 정책을 유지한다. [출력 DTO](../contracts/interfaces/planning.py) · [승인 검사](../backend/app/plans/approval.py)
- 나미님은 `frontend/src/components/LivePlanningPanel.tsx`, `frontend/src/services/api.ts`, `frontend/src/types/modules.ts`에서 시작 월·1~12개월(기본 3) 선택과 기간 지정 전송을 연결한다. 진단의 `MULTI_MONTH`·건수·입고 공급 미연결과 409 예측 범위 오류를 표시하고, 저장 목록/상세의 기간·부모 실행·지문을 유지한다. What-if는 월·자원 및 발주별 조건과 세 후보 비교를 표시한다. 조건 수정 전 원래 실행과 저장하지 않는 Preview를 구별하고, 501에서는 계산/승인을 사용할 수 없는 상태로 표시한다. [화면 안내](frontend_guide.md)
- 인수 기대값은 `backend/tests/test_planning_sources.py`의 1·3·6·12개월과 연도 경계, `test_planning_input_diagnostics.py`의 3개월 기본/예산 누락/기준일 당일 overdue, `test_plan_executions.py`의 부모 기간·자원·PO 검증/취소 불변/이력 지문, `test_planning_adapter.py`의 422·모순 500에 고정했다. 구현과 테스트는 기존 engine·frontend 담당 폴더 밖에 있다.

## 이번 검증

- 전체 `pytest --no-db -q --tb=short` 1,102 passed / 0 failed / 66 skipped / 0 deselected. 기존 Starlette/httpx 경고 1건. 초기 집중 시험에서 진단 JSON 예시 1건이 불일치했고 실제 응답으로 예시를 갱신해 최종 통과했다. TypeScript와 Vite 프로덕션 빌드, 생성 OpenAPI·Schema·예시 회귀 확인을 완료했다.
- 전용 컨테이너 `chungpamo-monorepo-db` healthy, Docker 29.4.0, PostgreSQL 16.6. `127.0.0.1:55433/chungpamo`, `chungpamo_app`, Alembic 0009에서 설정과 트랜잭션을 모두 읽기 전용으로 검증했다. TestClient 연결 설정만 교체했고 SQL provider를 실제 호출했다.
- `CHUNGPAMO-2027` 1개월/3개월 진단 200. 3개월 단일 스냅샷에 9제품×3개월 예측 27행, BOM 9개, 재고 18행, 시간예산 18행, 수량한도 3행, 라우팅 27행 및 승인 출처 9개가 들어왔다. 공식 예측 밖 6·12개월과 LEGACY의 3개월 요청은 409, LEGACY 1개월은 200, 교차 dataset forecast 404였다. 두 데이터셋 계획 목록은 200/0건, 미존재 상세는 404다.
- 개발 DB 테이블 60개와 스키마 객체 735개의 지문, 승인 배치 7+9건, 예측 각 1건, 전용 Docker 자원이 전후 일치했다. manifest 14개와 별도 예정 입고 CSV SHA도 보존했다. 운영 계획 저장, SQL 승인 입고, DB 쓰기·migration·파괴적 회귀 및 브라우저는 미실행이다. 로컬 증거는 Git 제외 `.artifacts/planning-contract-20261122/`에 있다.
- 변경 후보의 휴리스틱 보안 검사 결과는 0건이다. 전체 트리 검사는 시작 커밋에 이미 있던 분류기 샘플 Excel 200건과 샘플 전화번호 생성 코드 1건을 표시했다. 이번 변경 목록과 교차 대조했다.
