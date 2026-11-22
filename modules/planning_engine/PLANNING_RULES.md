# 계획 엔진 계산 규칙서 v0.4 (초안, 2026-11-22)

계획 엔진(`engine.planning.run`)과 손계산 정답이 **똑같이** 따르는 계산 규칙이다. 손계산 정답은 이 문서만 보고 엔진 코드와 따로 만든다.
기준: [엔진 계약 v0.2 §6](../../docs/engine_forecast_plan_contract.md)과 출력 계약 `contracts/interfaces/planning.py`(PlanningOutput). 바꾼 점은 §9에 모았다.
이 문서는 **희원의 계산 제안**이다. 공통 계약(기간·입고 예정·What-if 키·정책 버전)은 김대영 검토 후 확정된다([계약 요청](CONTRACT_REQUESTS.md)).

## 0. 한눈에 보기

```
예측(P50/P80) ─→ ① 목표 생산량 ─→ ② 설비·수량 한도 맞추기 ─→ ③ 재고 따라가기 ─→ ④ 자재 소요 ─→ ⑤ 판정
                  (수요+안전재고   (넘치면 앞 달로 미리 생산,   (결품 확인)       (월별 MRP 표,   (계획안별
                   −재고)           못 미루면 뒤 달에 보충)                        발주 필요량)     가능/불가능)
```

세 계획안은 같은 계산을 쓰고 **두 가지만** 다르다.

| 안 | plan_id | plan_type | 수요 | 쓸 수 있는 시간 |
|---|---|---|---|---|
| 기준형 | `BASELINE` | BASELINE | P50 | 정규 + 잔업 한도 |
| 안정형 | `STABLE` | STABLE | P80 | 정규 + 잔업 한도 |
| 비용절감형 | `COST_SAVING` | COST_SAVING | P50 | 정규만 |

- 비용절감형은 "잔업비 0, 대신 결품을 감수"하는 안이다(희원 결정 2026-11-16). 충파모 데이터처럼 절단기가 빠듯하면 이 안은 결품 때문에 `INFEASIBLE`이 되는 것이 정상이며, 화면·설명에는 결품 수량과 원인 자원을 함께 보여준다. "안전재고를 쌓지 않는 안"(잔업 허용, 재고 최소)도 검토했지만 기준형과 차이가 작아(잔업 약 14% 감소) 채택하지 않았다.
- 안정형은 P80만 쓴다. P90은 입력에 보존되지만 이번 범위에서 쓰지 않는다.
- plan_id는 위 세 문자열로 고정하고, 출력 순서도 BASELINE → STABLE → COST_SAVING으로 고정한다. policy_ref는 `PLANNING_RULES-v0.4`.

## 1. 기호와 입력

| 기호 | 뜻 | 입력 위치 |
|---|---|---|
| p, m, r, k | 제품, 월(1·2·3 = 시작 월부터 3개월), 자원(설비·작업자), 자재 | |
| q(p,m) | 그 안이 쓰는 예측 분위수 (P50 또는 P80) | ForecastFact |
| SS(p) | 제품 안전재고 | ProductFact |
| I₀(p) | 기준일 가용재고 = 현재고 − 할당재고 | InventoryFact (품목별로 기준일 이전 가장 최신 시점 1개) |
| h(p,r) | 제품 1개를 만들 때 자원 r을 쓰는 시간 = Σ run_time ÷ reference_qty (공정표의 해당 자원 행 모두 합산, 작업자 인시 포함, `min`은 ÷60으로 h 환산) | RoutingStep, resource_requirements |
| REG(r,m), OT(r,m) | 정규 가용시간, 잔업 한도 | HoursBudget |
| LIM(p,m) | 월 생산수량 한도 (없으면 무한) | QuantityLimit |
| b(p,k) | 제품 1개당 자재 소요 = 소요량 ÷ 기준수량 × (1 + 스크랩률) | BOM (그 달 1일에 유효한 APPROVED·활성 BOM 1개) |
| M₀(k), SS(k) | 자재 가용재고(현재고 − 할당재고), 자재 안전재고 | InventoryFact, MaterialFact |
| SR(k,m) | m월에 들어오기로 한 입고 예정 수량 (§5.1) | 입고 예정 (계약 추가 요청 C02) |

계산은 모두 **정확한 분수**로 하고, 아래에 적힌 곳에서만 정수로 자른다. 소수 출력은 10진 문자열(소수 4자리 이하, 끝의 0 제거)이다.

## 2. ① 수요와 목표 생산량

1. **계획 수요** d(p,m) = ⌈ q(p,m) × 수요배수(p) ⌉ (곱한 뒤 정수 올림). 수요배수는 기본 1, What-if에서만 바뀐다.
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

## 5. ④ 자재 소요 (월별 MRP 표)

교과서식 MRP다. "부족하면 그달 발주해서 채운다"고 보고 다음 달로 넘어간다(희원 결정 2026-11-22). 모든 값이 0 이상이다.

| 줄 | 식 |
|---|---|
| 총소요 N(k,m) | Σₚ P(p,m) × b(p,k) |
| 가용 AVL(k,m) | POH(k,m−1) + SR(k,m). POH(k,0) = M₀(k) |
| **발주 필요량** NET(k,m) | max(0, N(k,m) + SS(k) − AVL(k,m)) |
| 월말 재고 POH(k,m) | AVL(k,m) + NET(k,m) − N(k,m) (발주분이 그달 들어온다고 가정) |

자재 부족은 생산량을 줄이지 않는다(발주하면 된다). 리드타임은 입력에 없으므로 "그달 발주해서 그달 받을 수 있는지"는 확인하지 않는다(`UNVERIFIED`).

### 5.1 입고 예정 SR (희원 결정 2026-11-22)

- **미입고 수량만** 센다. 일부 입고된 발주의 이미 들어온 양은 재고(M₀)에 들어 있다.
- 입고예정일이 속한 **달 전체**에 쓸 수 있다고 본다. 1/20 입고분은 1월 초 며칠은 실제로 모자랄 수 있지만 월 단위 계획에서는 1월에 넣는다.
- 입고예정일이 기준일 **당일 또는 이전**(납기 지남: 재고는 기준일이 끝난 시점이므로 당일 예정분이 미입고면 이미 늦음)이면 **1월 입고로 보고** warning `RECEIPT_OVERDUE`(input_refs에 발주번호). 정말 들어올지 모르므로 **그 자재의 1월 MAT 판정은 발주 필요량과 관계없이 `UNVERIFIED`**(reason `RECEIPT_OVERDUE`)로 둔다. 그래서 늦은 입고에 기대는 계획안이 FEASIBLE로 보이지 않는다(희원 결정 2026-11-22 보강).
- 기준일 뒤이지만 계획 시작 월보다 앞인 입고는 1월에 넣는다(경고 없음).
- 계획 기간 뒤에 들어오는 입고는 계산에 넣지 않는다.
- 어느 BOM에도 쓰이지 않는 자재의 입고는 계획과 관계없으므로 조용히 무시한다.
- 입고 단위가 자재 단위와 다르면 재고와 같은 기준으로 계산하지 않는다(status `INPUT_INVALID`, error `UNIT_MISMATCH`, §7).
- 취소된 발주는 백엔드가 넘기지 않는다고 본다(승인 자료 기준).

## 6. ⑤ 판정 (ConstraintEvaluation)

| constraint_id | dimension | 강도 | limit / used | status |
|---|---|---|---|---|
| `CAP-{r}-{YYYY-MM}` | 설비 `EQUIPMENT_HOURS`, 작업자 `WORK_HOURS` | HARD | CAP / USED (h, MACHINE_HOUR·PERSON_HOUR) | 항상 USED ≤ CAP → SATISFIED. 3.1에서 넘쳤던 달은 reason `CAPACITY_BINDING` |
| `QTY-{p}-{YYYY-MM}` | `QUANTITY` | HARD | LIM / P (EA) | SATISFIED. 수량 한도가 그 제품을 줄인 **가장 빠듯한 원인**이었던 달만 `QUANTITY_LIMIT_BINDING`(설비 비율이 더 작으면 표시 안 함) |
| `DEM-{p}-{YYYY-MM}` | `OTHER` | HARD | – | I(p,m) < 0 → **VIOLATED** (`STOCKOUT`), 아니면 SATISFIED |
| `SS-{p}-{YYYY-MM}` | `SAFETY_STOCK` | SOFT | SS / I(p,m) | I < SS → VIOLATED (`BELOW_SAFETY_STOCK`) |
| `MAT-{k}-{YYYY-MM}` | `MATERIAL` | HARD | AVL / N + SS(k) | NET > 0 → **UNVERIFIED** (`PROCUREMENT_REQUIRED`). 1월에 납기 지난 입고가 있으면 **UNVERIFIED** (`RECEIPT_OVERDUE`, 둘 다면 두 코드 모두). 아니면 SATISFIED |

**계획안 판정(feasibility)**
1. HARD 중 VIOLATED가 하나라도 있으면 `INFEASIBLE`
2. 아니고 HARD 중 UNVERIFIED가 있거나, 그 안의 unverified 목록이 비어 있지 않으면 `UNVERIFIED`
3. 나머지 `FEASIBLE`

SOFT 위반(안전재고 미달)은 판정을 바꾸지 않고 표시만 한다. **엔진의 feasibility는 계산 결과일 뿐이고, 승인해도 되는지는 백엔드 승인 정책이 따로 정한다**(희원 결정 2026-11-22). 결품이 있는데 FEASIBLE인 모순 출력은 계약 검사에서 막아 달라고 요청한다(C06).

`material_requirements`에는 자재·월마다 required = N(k,m), available = AVL(k,m), shortage = NET(k,m)을 낸다.

## 7. 입력이 빠지거나 틀렸을 때 (희원 결정 2026-11-22)

| 상황 | 처리 |
|---|---|
| 계획할 제품의 예측이 없음 | 계산하지 않음. status `INPUT_INVALID`, error `FORECAST_MISSING` (백엔드 provider의 409와 같은 기준) |
| 품목의 재고 행이 없음 | 0으로 계산. warning `INVENTORY_MISSING` + 모든 안의 unverified에 같은 코드 → `UNVERIFIED` |
| 제품의 공정표(라우팅)가 없음 | 그 제품은 설비 계산을 건너뛴다. **월 생산수량 한도가 있으면 그것만 적용**(선행생산·보충 포함, QTY 판정도 냄), 없으면 P = T. 어느 자원을 쓰는지 모르므로 **모든 CAP**을 `UNVERIFIED` + application_state `MISSING_INPUT`(used = null), unverified에 `ROUTING_MISSING` (희원 결정 2026-11-22 보강) |
| 어떤 자원·월의 가용시간이 없음(값 없음·배열 짧음, 공정표에만 있고 자원 목록에 없는 자원 포함) | 그 자원·월은 한도 없음으로 보고 CAP-{r}-{m}을 `UNVERIFIED`/`MISSING_INPUT`(used는 계산값), unverified에 `CAPACITY_MISSING` |
| 잔업 허용 안인데 잔업 한도 값이 없음 | 잔업 0으로 보수적으로 계산하고 warning `OVERTIME_LIMIT_MISSING`(판정은 그대로 믿을 수 있으므로 unverified 아님) |
| 월 생산수량 한도의 어떤 달이 비어 있음 | 그달은 한도 없음 |
| BOM이 없는 제품 | 그 제품이 쓰는 자재를 모르므로 warning·unverified `BOM_MISSING`, **모든 MAT**을 `UNVERIFIED`/`MISSING_INPUT`(계산된 숫자는 그대로 표시). 라우팅 누락과 같은 방식 (희원 결정 2026-11-22 보강) |
| 그 달 유효 BOM이 2개 이상 | `BOM_VERSION_AMBIGUOUS` — 버전 고르기는 입력 변환부에서 처리(계산 코어 입력에는 제품당 BOM 1개) |
| BOM이 가리키는 자재가 자재 목록에 없음 | 단위·안전재고를 모르므로 계산하지 않음. `INPUT_INVALID`, error `MATERIAL_MISSING` (희원 결정 2026-11-22 보강) |
| 자재 목록에 있지만 어느 BOM에도 쓰이지 않는 자재 | MRP 표·MAT 판정·재고 누락 검사에서 제외(입고 규칙과 같은 생각) (희원 결정 2026-11-22 보강) |
| 기준수량·BOM 기준수량이 0 이하, 제품 수량(재고·안전재고·한도)이 정수가 아님 | 계산하지 않음. `INPUT_INVALID`, error `INVALID_QUANTITY` |
| 공정 시간 단위가 h·min이 아님 | `INPUT_INVALID`, error `UNIT_MISMATCH` |
| 단위가 서로 안 맞음(예: 수요 EA, 재고 kg / 자재 kg, 자재 재고 g / 자재 kg, 입고 예정 m) | 계산하지 않음. status `INPUT_INVALID`, error `UNIT_MISMATCH` |
| **다단계 BOM**(구성품이 제품), **ELAPSED 시간 기준**, **GROSS 가용시간** | 계산이 틀려지므로 계산하지 않음. status `UNSUPPORTED`, error `BOM_MULTILEVEL_UNSUPPORTED` / `TIME_BASIS_UNSUPPORTED` / `AVAILABILITY_BASIS_UNSUPPORTED` |
| **셋업 시간**, **대체 설비 그룹** 값이 있음 | 반영하지 않고 계산. 모든 안의 unverified에 `SETUP_TIME_IGNORED` / `ALTERNATIVE_RESOURCE_IGNORED` → `UNVERIFIED` |

없는 값을 0이나 무한으로 채운 경우에는 항상 경고·unverified 코드와 input_refs로 근거를 남긴다.

**문제가 여러 개 겹칠 때**(희원 결정 2026-11-22 보강): 상태는 `INPUT_INVALID` > `UNSUPPORTED` > 계산(OK) 순서로 정한다. 입력 검사는 첫 문제에서 멈추지 않고 끝까지 하며, error_codes에는 발견한 문제를 모두 담는다(한 번에 고칠 수 있게). 계산하지 않는 상태에서는 계획안을 내지 않는다.

## 8. What-if (희원 결정 2026-11-22)

같은 예측 결과로 **세 안을 모두** 다시 계산한다. 원본 승인 입력과 기준 결과는 바꾸지 않는다.

| 변경 | 범위 | 적용 위치 | 시연 장면 |
|---|---|---|---|
| 수요 배수 | 전체 또는 제품별 | §2-1 수요배수(p) | "수요가 20% 늘면?" |
| 잔업 한도 | 자원·월별 (절대값) | OT(r,m) | "2월에 특근하면?" |
| 입고 예정 취소·수량 변경 | 발주번호별 | SR(k,m) | "1/20 원단이 안 들어오면?" |

세부 규칙(희원 결정 2026-11-22 보강):
- 변경 키는 계약 요청 C03 모양: `demand_multiplier`, `demand_multiplier.<제품>`, `overtime_hours_limit.<자원>.<YYYY-MM>`, `receipt_qty.<발주번호>`(0 = 취소, 행을 지우므로 납기 지남 경고도 사라짐).
- 전체 배수와 제품 배수를 함께 주면 **제품 배수가 우선**(곱하지 않음).
- 잔업 한도 변경은 기준형·안정형에만 들어간다. 비용절감형은 잔업 0 안이므로 결과가 바뀌지 않는다.
- 없는 제품·자원·발주번호, 음수·숫자 아닌 값, 계획 기간 밖의 월, 모르는 키(`production_qty.*` 포함)는 계산하지 않고 `INPUT_INVALID`, error `WHATIF_INVALID`(input_refs = 키, 문제 종류)를 **모두** 돌려준다.
- 결과는 기준 세 안과 변경 후 세 안을 함께 내고, 안별로 판정·결품 합계·잔업 합계 변화를 비교할 수 있게 한다.

재고 수량 변경, 생산량 직접 지정은 이번 범위에서 뺐다(생산량 직접 지정은 결과가 "사람이 만든 안 1개"가 되어 출력 규칙이 더 필요함).

## 9. 바뀐 점

| 항목 | 계약 v0.2 | v0.3 (2026-11-15) | v0.4 (2026-11-22) | 확인 |
|---|---|---|---|---|
| 계획 기간 | target_month 한 달 | **3개월** (target_month = 시작 월) | 같음 | C01 대영 확인 필요 |
| 선행생산 | 비용절감형만 | **세 안 모두** (잔업 허용 안은 잔업 먼저) | 같음 | C04 |
| 공유 자원 배분 | product_id 순 | **같은 비율로 축소** | 같음 | C04 |
| 입고 예정 | 무시 | 자재 판정에 반영 | **미입고 수량·달 전체·납기 지남은 1월+경고+1월 MAT UNVERIFIED, BOM 밖 자재 무시, 단위 오류 INPUT_INVALID** | C02 칸 추가 요청 |
| 자재 결과 | 누적 부족 증가분 | 누적 부족 증가분(음수 가능) | **월별 MRP 표: 발주 필요량, 음수 없음** | C05 |
| 판정 | SOFT 무시 | SOFT 무시 | **unverified 목록도 UNVERIFIED로, 승인은 백엔드** | C06 |
| 예측 누락 | – | 빼고 PARTIAL | **INPUT_INVALID** | C07 |
| 재고 누락·미지원 기능 | – | – | **0+경고 / UNSUPPORTED·경고 구분, 겹치면 INPUT_INVALID > UNSUPPORTED, 오류 모두 나열** | C08 |
| What-if | 배수·재고·입고 | 배수·잔업·재고·입고 | **배수·잔업(월별)·입고, 세 안 모두 재계산** | C03 |
| DEM dimension | `DUE_DATE` | `OTHER` | 같음 | |
| KPI | 안별 kpis[] | 범위 제외 | 같음 | C09 |

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

자재 MRP 표 예시(원단 재고 150, 안전재고 20, 매달 210 사용, 3월 입고 400):

| | 1월 | 2월 | 3월 |
|---|---|---|---|
| 총소요 N | 210 | 210 | 210 |
| 가용 AVL | 150 | 20 | 20 + 400 = 420 |
| 발주 필요량 NET | 80 | 210 | 0 |
| 월말 재고 POH | 20 | 20 | 210 |
