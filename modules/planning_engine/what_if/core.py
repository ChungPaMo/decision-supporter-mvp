"""What-if: 변경 조건을 넣고 세 계획안을 다시 계산한다 (PLANNING_RULES v0.4 §8).

변경 키는 계약 요청 C03 모양을 그대로 쓴다.
- `demand_multiplier`                         전체 수요 배수
- `demand_multiplier.<product>`               제품별 수요 배수(전체 배수보다 우선)
- `overtime_hours_limit.<resource>.<YYYY-MM>` 그 자원·월 잔업 한도(절대값). 비용절감형은 잔업 0 안이라 영향 없음
- `receipt_qty.<po_id>`                       입고 예정 미입고 수량 변경, 0이면 취소

원본 입력과 기준 결과는 바꾸지 않는다. 변경 입력이 하나라도 잘못되면 계산하지 않고 모든 문제를 돌려준다.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from fractions import Fraction

from engine.planning_core import PLAN_SPECS, Issue, PlanResult, calculate_plans


@dataclass
class PlanDelta:
    plan_id: str
    feasibility: tuple[str | None, str | None]
    stockout_total: tuple[int, int]
    overtime_total: tuple[Fraction, Fraction]


@dataclass
class WhatIfResult:
    status: str  # OK / INPUT_INVALID
    overrides: dict[str, str]
    errors: list[Issue] = field(default_factory=list)
    base: dict[str, PlanResult] = field(default_factory=dict)
    scenario: dict[str, PlanResult] = field(default_factory=dict)

    def deltas(self) -> list[PlanDelta]:
        out = []
        for plan_id, _, _ in PLAN_SPECS:
            b, s = self.base[plan_id], self.scenario[plan_id]
            out.append(PlanDelta(plan_id, (b.feasibility, s.feasibility),
                                 (_stockout_total(b), _stockout_total(s)), (_overtime_total(b), _overtime_total(s))))
        return out


def _stockout_total(r: PlanResult) -> int:
    return sum(sum(v) for v in r.stockout.values())


def _overtime_total(r: PlanResult) -> Fraction:
    return sum((x for v in r.overtime_hours.values() for x in v if x is not None), Fraction(0))


def _nonnegative(value) -> Fraction | None:
    try:
        v = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        return None
    return v if v >= 0 else None


def apply_overrides(data: dict, overrides: dict[str, str]) -> tuple[dict, list[Issue]]:
    """변경을 적용한 새 입력을 만든다(원본은 그대로). 잘못된 변경은 모두 WHATIF_INVALID로 모은다."""
    new = copy.deepcopy(data)
    errors: list[Issue] = []
    products = {p['id'] for p in data['products']}
    resources = {r['id']: i for i, r in enumerate(new['resources'])}
    receipts = {r['po_id']: r for r in new.get('receipts', [])}
    cancelled: set[str] = set()
    for key, raw in overrides.items():
        value = _nonnegative(raw)
        parts = key.split('.')
        if value is None:
            errors.append(Issue('WHATIF_INVALID', (key, 'value')))
            continue
        if parts == ['demand_multiplier']:
            new['demand_multiplier'] = str(value)
        elif parts[0] == 'demand_multiplier' and len(parts) == 2:
            if parts[1] not in products:
                errors.append(Issue('WHATIF_INVALID', (key, 'product')))
                continue
            new.setdefault('demand_multipliers', {})[parts[1]] = str(value)
        elif parts[0] == 'overtime_hours_limit' and len(parts) == 3:
            rid, month = parts[1], parts[2]
            if rid not in resources:
                errors.append(Issue('WHATIF_INVALID', (key, 'resource')))
                continue
            if month not in new['months']:
                errors.append(Issue('WHATIF_INVALID', (key, 'month')))
                continue
            res = new['resources'][resources[rid]]
            ot = list(res.get('overtime') or [])
            ot += [None] * (len(new['months']) - len(ot))
            ot[new['months'].index(month)] = str(value)
            res['overtime'] = ot
        elif parts[0] == 'receipt_qty' and len(parts) == 2:
            po = parts[1]
            if po not in receipts:
                errors.append(Issue('WHATIF_INVALID', (key, 'po_id')))
                continue
            if value == 0:
                cancelled.add(po)
            else:
                receipts[po]['open_qty'] = str(value)
        else:
            errors.append(Issue('WHATIF_INVALID', (key, 'key')))
    if cancelled:
        new['receipts'] = [r for r in new['receipts'] if r['po_id'] not in cancelled]
    return new, errors


def run_what_if(data: dict, overrides: dict[str, str]) -> WhatIfResult:
    """data는 calculate_plans 입력(forecast P50/P80 포함). 기준 세 안과 변경 후 세 안을 함께 돌려준다."""
    new, errors = apply_overrides(data, overrides)
    if errors:
        return WhatIfResult('INPUT_INVALID', dict(overrides), errors=errors)
    return WhatIfResult('OK', dict(overrides), base=calculate_plans(data), scenario=calculate_plans(new))
