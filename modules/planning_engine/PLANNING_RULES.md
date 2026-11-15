# 계획 엔진 계산 규칙서 v0.3 (초안, 2026-11-15)

계획 엔진(`engine.planning.run`)과 손계산 정답이 **똑같이** 따르는 계산 규칙이다. 손계산 정답은 이 문서만 보고 엔진 코드와 따로 만든다.
기준: [엔진 계약 v0.2 §6](../../docs/engine_forecast_plan_contract.md)과 출력 계약 `contracts/interfaces/planning.py`(PlanningOutput). 바꾼 점은 §9에 모았다.

## 0. 한눈에 보기

```
예측(P50/P80) ─→ ① 목표 생산량 ─→ ② 설비·수량 한도 맞추기 ─→ ③ 재고 따라가기 ─→ ④ 자재 소요 ─→ ⑤ 판정
                  (수요+안전재고   (넘치면 앞 달로 미리 생산,   (결품 확인)       (BOM 전개,      (계획안별
                   −재고)           못 미루면 뒤 달에 보충)                        재고+입고 예정)   가능/불가능)
```

세 계획안은 같은 계산을 쓰고 **두 가지만** 다르다.

| 안 | plan_id | plan_type | 수요 | 쓸 수 있는 시간 |
|---|---|---|---|---|
| 기준형 | `BASELINE` | BASELINE | P50 | 정규 + 잔업 한도 |
| 안정형 | `STABLE` | STABLE | P80 | 정규 + 잔업 한도 |
| 비용절감형 | `COST_SAVING` | COST_SAVING | P50 | 정규만 |

비용절감형은 "잔업비 0, 대신 결품을 감수"하는 안이다(희원 결정 2026-11-16). 충파모 데이터처럼 절단기가 빠듯하면 이 안은 결품 때문에 `INFEASIBLE`이 되는 것이 정상이며, 화면·설명에는 결품 수량과 원인 자원을 함께 보여준다. "안전재고를 쌓지 않는 안"(잔업 허용, 재고 최소)도 검토했지만 기준형과 차이가 작아(잔업 약 14% 감소) 채택하지 않았다.

## 1. 기호와 입력

| 기호 | 뜻 | 입력 위치 |
|---|---|---|
| p, m, r, k | 제품, 월(1·2·3 = 2027-01·02·03), 자원(설비·작업자), 자재 | |
| q(p,m) | 그 안이 쓰는 예측 분위수 (P50 또는 P80) | ForecastFact |
| SS(p) | 제품 안전재고 | ProductFact |
| I₀(p) | 기준일 가용재고 = 현재고 − 할당재고 | InventoryFact |
| h(p,r) | 제품 1개를 만들 때 자원 r을 쓰는 시간 = Σ run_time ÷ reference_qty (공정표의 해당 자원 행 모두 합산, 작업자 인시 포함) | RoutingStep, resource_requirements |
| REG(r,m), OT(r,m) | 정규 가용시간, 잔업 한도 | HoursBudget |
| LIM(p,m) | 월 생산수량 한도 (없으면 무한) | QuantityLimit |
| b(p,k) | 제품 1개당 자재 소요 = 소요량 ÷ 기준수량 × (1 + 스크랩률) | BOM (그 달 1일에 유효한 APPROVED·활성 BOM 1개) |
| M₀(k), SS(k) | 자재 가용재고, 자재 안전재고 | InventoryFact, MaterialFact |
| R(k,m) | 입고예정일이 m월 말 이전인 미입고 발주 수량 합 (누적) | 입고 예정 (§9 계약 추가 요청) |

계산은 모두 **정확한 분수**로 하고, 아래에 적힌 곳에서만 정수로 자른다. 소수 출력은 10진 문자열이다.

## 2. ① 수요와 목표 생산량

1. **계획 수요** d(p,m) = ⌈ q(p,m) × 수요배수 ⌉ (정수 올림). 수요배수는 기본 1, What-if에서만 바뀐다.
2. **목표 생산량** T(p,m): 계획대로 만들어진다고 가정한 재고 J로 차례대로 구한다.
   - J₀ = I₀
   - T(p,m) = max(0, d(p,m) + SS(p) − J(m−1))
   - J(m) = J(m−1) + T(p,m) − d(p,m)

   즉 1월은 "수요 + 안전재고 − 지금 재고", 2·3월은 보통 그달 수요와 같다.

## 3. ② 한도 맞추기 (미리 생산·뒤에 보충)

자원 r의 **쓸 수 있는 시간** CAP(r,m) = REG(r,m) + OT(r,m) (기준형·안정형) 또는 REG(r,m) (비용절감형).

### 3.1 한 달 안에서 줄이기 (같은 비율 규칙)

그 달에 만들려는 양 X(p)가 있을 때:

1. 자원별 부하 L(r) = Σₚ X(p) × h(p,r)
2. 넘치는 자원의 비율 f(r) = CAP(r,m) ÷ L(r) (L(r) ≤ CAP면 f(r) = 1)
3. 제품별 비율 f(p) = min( 1, 그 제품이 쓰는 자원들의 f(r) 중 최솟값, LIM(p,m) ÷ X(p) )
4. **생산량 P(p) = ⌊ X(p) × f(p) ⌋** (정수 내림), **넘친 양 E(p) = X(p) − P(p)**. X(p) = 0이면 P(p) = 0.

내림으로 남는 자투리 시간은 다시 나누지 않는다. 이 방식이면 모든 자원의 부하가 CAP 이하로 보장된다.

### 3.2 앞 달로 미리 생산 (뒤에서부터)

m = 3, 2, 1 순서로:

- X(p) = T(p,m) + (m+1월에서 넘어온 E)
- 3.1을 적용해 P(p,m)과 E(p)를 구한다.
- m ≥ 2면 E(p)를 m−1월로 넘긴다. m = 1에서 남은 E(p)는 **못 만든 양 U(p)**.

넘어온 양과 그달 원래 목표는 구별하지 않고 같은 비율로 줄인다. 잔업이 허용된 안은 **그달 잔업을 먼저 쓰고**, 그래도 넘치는 양만 앞 달로 보낸다(미리 만들면 재고가 쌓이므로).

### 3.3 뒤 달에 보충 (앞에서부터)

U(p) > 0이면 m = 2, 3 순서로 그 달 남은 시간에 늦게라도 만든다.

- 남은 시간 CAP′(r,m) = CAP(r,m) − Σₚ P(p,m) × h(p,r), 남은 수량 한도도 같은 방식
- X(p) = U(p)로 3.1을 적용(CAP 대신 CAP′) → 추가 생산 A(p), U(p) ← U(p) − A(p)
- P(p,m) ← P(p,m) + A(p)

마지막까지 남은 U(p)는 3개월 안에 못 만드는 양이다.

## 4. ③ 재고 따라가기와 결품

- I(p,0) = I₀(p), I(p,m) = I(p,m−1) + P(p,m) − d(p,m)
- **I(p,m) < 0이면 결품.** 결품 수량 = −I(p,m), 다음 달로 그대로 이월된다(음수 재고가 남음).
- 사용시간 USED(r,m) = Σₚ P(p,m) × h(p,r), 잔업시간 = max(0, USED − REG)

## 5. ④ 자재 소요 (MRP)

- 월 소요 N(k,m) = Σₚ P(p,m) × b(p,k)
- 누적 소요 CN(k,m) = N(k,1) + … + N(k,m)
- 누적 가용 AV(k,m) = M₀(k) + R(k,m) − SS(k)
- 누적 부족 SH(k,m) = max(0, CN(k,m) − AV(k,m))
- **그 달 부족(조달 필요량)** = SH(k,m) − SH(k,m−1)

자재 부족은 생산량을 줄이지 않는다(발주하면 된다). 입고예정일은 월 단위로만 본다. 1/20 입고분은 1월 전체에 쓸 수 있다고 본다.

## 6. ⑤ 판정 (ConstraintEvaluation)

| constraint_id | dimension | 강도 | limit / used | status |
|---|---|---|---|---|
| `CAP-{r}-{YYYY-MM}` | 설비 `EQUIPMENT_HOURS`, 작업자 `WORK_HOURS` | HARD | CAP / USED (h, MACHINE_HOUR·PERSON_HOUR) | 항상 USED ≤ CAP → SATISFIED. 3.1에서 넘쳤던 달은 reason `CAPACITY_BINDING` |
| `QTY-{p}-{YYYY-MM}` | `QUANTITY` | HARD | LIM / P (EA) | SATISFIED. 한도에 걸린 달은 `QUANTITY_LIMIT_BINDING` |
| `DEM-{p}-{YYYY-MM}` | `OTHER` | HARD | d + 전월 결품 / 그달까지 공급 (EA) | I(p,m) < 0 → **VIOLATED** (`STOCKOUT`) |
| `SS-{p}-{YYYY-MM}` | `SAFETY_STOCK` | SOFT | SS / I(p,m) | I < SS → VIOLATED (`BELOW_SAFETY_STOCK`) |
| `MAT-{k}-{YYYY-MM}` | `MATERIAL` | HARD | AV / CN | 부족 > 0 → **UNVERIFIED** (`PROCUREMENT_REQUIRED`), 아니면 SATISFIED |

**계획안 판정(feasibility)**: HARD 중 VIOLATED가 하나라도 있으면 `INFEASIBLE` → 아니고 UNVERIFIED가 있으면 `UNVERIFIED` → 나머지 `FEASIBLE`. SOFT 위반은 판정에 영향이 없다.

`material_requirements`에는 자재·월마다 required = N(k,m), available = AV(k,m) − AV(k,m−1) (AV(k,0) = 0, 즉 1월은 재고 − 안전재고 + 1월 입고, 2월부터는 그달 입고), shortage = 그 달 부족을 낸다.

## 7. 입력이 빠지거나 틀렸을 때

| 상황 | 처리 |
|---|---|
| 제품의 공정표(라우팅)가 없음 | 그 제품은 3장을 건너뛰고 P = T. 그 제품이 어느 자원을 쓰는지 모르므로 **모든 CAP**을 `UNVERIFIED` + application_state `MISSING_INPUT`(used = null), unverified에 `ROUTING_MISSING` → 계획안 `UNVERIFIED` |
| 어떤 자원·월의 가용시간이 없음 | 그 자원은 한도 없음으로 보고 CAP-{r}-{m}을 `UNVERIFIED`/`MISSING_INPUT` |
| BOM이 없거나 그 달 유효 BOM이 2개 이상 | 자재 소요 계산 제외, `BOM_MISSING` / `BOM_VERSION_AMBIGUOUS` 경고, MAT `UNVERIFIED` |
| 제품의 예측이 없음 | 계획에서 제외하고 `FORECAST_MISSING` 경고 → status `PARTIAL` |
| 단위가 서로 안 맞음(예: 수요 EA, 재고 kg) | 계산하지 않음, status `INPUT_INVALID`, error `UNIT_MISMATCH` |

## 8. What-if

같은 예측 결과로 계획만 다시 계산한다. 원본 입력은 바꾸지 않는다.

| 변경 | 적용 위치 |
|---|---|
| 수요배수 (예: 1.2) | §2-1의 수요배수 |
| 잔업 한도 변경 | OT(r,m) |
| 재고 수량 변경 | I₀ 또는 M₀ |
| 입고 예정 취소·변경 | R(k,m) |

## 9. 계약 v0.2에서 바꾼 점 (희원 결정 2026-11-15)

| 항목 | v0.2 | v0.3 (이 문서) | 확인 |
|---|---|---|---|
| 계획 기간 | target_month 한 달 | **3개월** (target_month = 시작 월) | 대영 님 확인 필요 |
| 선행생산 | 비용절감형만 | **세 안 모두** (잔업 허용 안은 잔업 먼저) | |
| 공유 자원 배분 | product_id 순 | **같은 비율로 축소** (§3.1) | |
| 입고 예정 | 데이터 없음 → 무시 | **자재 판정에 반영** | PlanningInput에 칸 추가 요청 |
| DEM dimension | `DUE_DATE` | `OTHER` (출력 계약에 DUE_DATE가 없음) | |
| KPI | 안별 kpis[] | 출력 계약에 칸이 없어 이번 범위에서 제외 | 필요하면 추후 요청 |

## 10. 작은 예시

제품 A 하나, 자원 S 하나. 1개에 1시간. I₀ = 0, SS = 0. 잔업 없음.

| | 1월 | 2월 |
|---|---|---|
| 수요 d | 100 | 150 |
| 가용시간 CAP | 130 | 110 |
| ① 목표 T | 100 | 150 |
| ② 2월부터: X | 100 + 40 = 140 | 150 |
| 생산 P | 130 (넘친 10 → U) | 110 (넘친 40 → 1월로) |
| ③ 보충 | – | 2월 남은 시간 0 → 보충 없음 |
| 재고 I | 30 | 30 + 110 − 150 = **−10 (결품 10)** |
| 판정 | DEM-A-01 SATISFIED | DEM-A-02 **VIOLATED** → 계획안 INFEASIBLE |
