# 계획 엔진 계약 답변·요청 (이희원 → 김대영, 2026-11-22)

[계획 엔진 통합 준비 보고서](../../docs/PLANNING_ENGINE_INTEGRATION_READINESS.md)의 §4(C01~C11)와 §6(희원에게 확인할 9가지)에 대한 답이다. 계산 규칙은 [PLANNING_RULES v0.4](PLANNING_RULES.md)에 반영했다.
여기 적은 것은 **희원의 계산 측 결정과 계약 변경 요청**이며, 공통 DTO·Schema·DB 변경 여부는 대영 님이 판단한다. 공통 계약이 확정되기 전에는 `AVAILABLE=False`를 유지한다.

## 1. §6 질문에 대한 답

| # | 질문 요지 | 답 |
|---|---|---|
| 1 | v0.3/HC가 구현 기준인가, 각 항목 확정 여부 | 희원 측에서는 **v0.4로 확정**(3개월·같은 비율 배분·잔업 먼저·세 안 모두 선행생산·비용절감형 = 잔업 0 + 결품 감수). 팀 계약 확정은 C01~C06 검토 후. HC 정답은 v0.4 기준으로 갱신한다 |
| 2 | `run(PlanningInput)->PlanningOutput`·AVAILABLE 유지, DB/파일 접근 없이 계산 | **예.** 엔진은 주어진 Snapshot만 쓰고 CSV·DB를 읽지 않는다. 필요한 값은 아래 C01~C03 요청으로 전달받는다 |
| 3 | 예정 입고: 미입고·부분입고·취소, 월중 입고, lead time 없는 PROCUREMENT_REQUIRED 해석 | 미입고 수량만 센다. 입고예정일이 속한 달 전체에 사용. 납기가 기준일 이전이면 1월 입고 + `RECEIPT_OVERDUE` 경고. 취소 발주는 백엔드가 넘기지 않는다고 본다. `PROCUREMENT_REQUIRED`는 "그달 이만큼 발주가 필요하나 리드타임이 없어 제때 받을 수 있는지는 확인 못 함"이라는 뜻(규칙서 §5) |
| 4 | C05 음수 가용·부족 표현 | **교과서식 월별 MRP로 변경**: required = 그달 총소요, available = 월초 재고 + 그달 입고, shortage = 그달 발주 필요량. 정의상 모두 0 이상이므로 DTO·DB 비음수 제약을 그대로 쓴다. 손계산 예시는 규칙서 §10과 HC-09·HC-13 |
| 5 | 누락·다중 BOM·라우팅 누락·공유 인력, 상태 경계 | 규칙서 §7 표. 예측 누락 = `INPUT_INVALID`(provider 409와 같은 기준). 재고 누락 = 0 + `INVENTORY_MISSING`·UNVERIFIED. 라우팅 누락 = 모든 CAP UNVERIFIED. 다단계 BOM·ELAPSED·GROSS = `UNSUPPORTED`. 셋업·대체 설비 = 반영 안 하고 UNVERIFIED. 공유 인력 LB1은 PERSON_HOUR 자원으로 같은 비율 규칙에 포함, 인원 수로 다시 곱하지 않음 |
| 6 | SOFT/HARD/UNVERIFIED 합성과 승인 조건 | 엔진 feasibility: HARD VIOLATED → INFEASIBLE, HARD UNVERIFIED 또는 안별 unverified 있음 → UNVERIFIED, 나머지 FEASIBLE. SOFT(안전재고) 위반은 표시만. **승인 가능 여부는 백엔드 승인 정책이 정한다**(엔진은 승인 권한을 만들지 않음) |
| 7 | What-if: 후보 하나 조정인지 전체 재생성인지, 월별 범위 | **세 안 모두 재계산.** 조정 항목은 수요 배수(전체/제품별), 잔업 한도(자원·월별 절대값), 입고 예정 취소·수량 변경(발주번호별) 3가지. 재고 변경·생산량 직접 지정은 이번 범위 제외 |
| 8 | 결정적 ID·정책 버전·근거 코드, HC→run 자동 비교, 9제품×3월 테스트 | plan_id는 `BASELINE`/`STABLE`/`COST_SAVING` 고정, 출력 순서 고정, policy_ref `PLANNING_RULES-v0.4`, constraint_id 규칙은 규칙서 §6. HC 자동 비교 테스트와 공식 9제품×3월 테스트는 owner 폴더(`modules/planning_engine/tests/`)에서 제공한다. 테스트 없이 AVAILABLE을 켜지 않는다 |
| 9 | 다단계 BOM·ELAPSED/min·셋업·대체·GROSS·P90 지원 범위 | 단일 단계 MATERIAL BOM만 지원. `min`은 h로 환산(지원). ELAPSED·GROSS·다단계 BOM은 UNSUPPORTED. 셋업·대체 설비는 무시 + UNVERIFIED. 안정형은 P80만(P90 선택 정책은 이번 범위 제외) |

## 2. C01~C11 입장과 요청

| ID | 희원 입장 | 대영 님께 요청 |
|---|---|---|
| C01 기간 | 3개월 계획이 필요(2월 설 연휴 병목을 1월 선행생산으로 푸는 장면) | PlanCommand에 기간(예: `horizon_months: 3` 또는 기간 배열) 추가, provider가 3개월 예측·CAPA·한도를 한 Snapshot에 담기. 출력 검증·저장 CHECK의 기간 범위 확장 |
| C02 예정 입고 | 자재 판정에 반영(1/20 MR-N3 10,000kg) | PlanningInput에 입고 예정 목록 추가: `po_id, material_id, open_qty, unit, expected_date, supplier_id` + 출처 배치. 승인된 미입고 발주만 전달 |
| C03 What-if | 수요 배수·잔업 한도(월별)·입고 변경 3종, 세 안 재계산 | override 키를 월별 구조로: 예 `demand_multiplier`, `demand_multiplier.<product>`, `overtime_hours_limit.<resource>.<YYYY-MM>`, `receipt_qty.<po_id>`(0 = 취소). 기존 `production_qty.<product>`는 이번 범위에서 엔진이 쓰지 않음 |
| C04 정책 | v0.4 규칙을 policy_ref `PLANNING_RULES-v0.4`로 반환 | policy_version 전달 방식 결정. 서버가 정책을 정하면 엔진은 그 버전을 그대로 기록 |
| C05 자재 수량 | 월별 MRP로 바꿔 음수 없음 | DTO 변경 불필요(필드 의미만 문서화: required = 그달 총소요, available = 월초 재고 + 그달 입고, shortage = 그달 발주 필요량) |
| C06 판정 | 엔진 = 계산 판정, 승인 = 백엔드 | PlanningOutput 검사에 "FEASIBLE인데 HARD VIOLATED 평가가 있으면 거부" 추가 요청 |
| C07 예측 누락 | INPUT_INVALID로 provider와 통일 | 변경 없음 |
| C08 BOM·재고·라우팅 | 재고는 품목별 기준일 이전 최신 1개, BOM은 그 달 1일 유효 1개, 라우팅 다중 버전은 같은 규칙 | provider가 후보를 모두 넘겨도 엔진이 위 규칙으로 고름. 규칙에 안 맞으면 경고·UNVERIFIED |
| C09 KPI·비용 | 이번 범위 제외. 비용절감형을 "비용 최적화"라 부르지 않음 | 비교 지표가 필요하면 별도 버전에서 함께 정의 |
| C10 식별 | plan_id는 실행 안에서만 유일(execution_id + plan_id) | What-if는 부모 execution 전체를 기준으로 세 안 재생성 |
| C11 검증 일관성 | – | Preview와 저장 검증을 같은 범위로 맞춰 주시면 엔진은 그 범위 안의 출력만 낸다 |

## 3. 희원 다음 작업 (owner 폴더)

1. 작은 손계산 케이스를 v0.4로 갱신(HC-09 가용량 의미 변경, 입고·재고 누락·미지원 케이스 추가)
2. 계산 코어 구현(기간 수와 무관) + HC 자동 비교 테스트. 입력 변환부는 현행 단일 월 PlanningInput으로 먼저 동작, C01 확정 시 3개월로 확장
3. 충파모 9제품 × 3개월 × 3안 정답과 엔진 비교
4. What-if
