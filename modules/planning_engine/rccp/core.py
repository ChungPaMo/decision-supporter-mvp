"""RCCP: 한 달 안에서 설비·수량 한도 맞추기 (PLANNING_RULES v0.4 §3.1, §4 사용시간).

모든 계산은 Fraction으로 하고 생산량만 정수로 내림한다. DB·파일에 접근하지 않는 순수 함수다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from math import floor

# h[p][r] = 제품 p 1개를 만들 때 자원 r을 쓰는 시간
Hours = dict[str, dict[str, Fraction]]


@dataclass
class MonthScale:
    production: dict[str, int]
    overflow: dict[str, int]
    resource_factor: dict[str, Fraction]
    capacity_binding: set[str] = field(default_factory=set)
    quantity_binding: set[str] = field(default_factory=set)


def scale_month(want: dict[str, int], cap: dict[str, Fraction | None], limit: dict[str, int | None],
                h: Hours) -> MonthScale:
    """§3.1 같은 비율 규칙. want = 그 달에 만들려는 양 X(p), cap = 쓸 수 있는 시간(None = 한도 모름 → 한도 없음),
    limit = 월 생산수량 한도(None = 한도 없음). h에 없는 제품(라우팅 없음)은 설비 계산 없이 수량 한도만 적용한다."""
    load = {r: sum((Fraction(want[p]) * h.get(p, {}).get(r, 0) for p in want), Fraction(0)) for r in cap}
    over = {r for r in cap if cap[r] is not None and load[r] > cap[r]}
    factor = {r: (cap[r] / load[r] if r in over else Fraction(1)) for r in cap}
    production, overflow, qty_binding = {}, {}, set()
    for p, x in want.items():
        if x <= 0:
            production[p], overflow[p] = 0, 0
            continue
        f = min([Fraction(1)] + [factor[r] for r, hours in h.get(p, {}).items() if r in factor and hours > 0])
        lim = limit.get(p)
        if lim is not None and x > lim and Fraction(lim, x) <= f:
            f = Fraction(lim, x)
            qty_binding.add(p)  # 수량 한도가 실제로 가장 빠듯한 원인일 때만 표시
        production[p] = floor(x * f)
        overflow[p] = x - production[p]
    return MonthScale(production, overflow, factor, over, qty_binding)


def used_hours(production: dict[str, int], h: Hours, resource: str) -> Fraction:
    """§4 USED(r,m) = Σₚ P(p,m) × h(p,r)."""
    return sum((Fraction(production[p]) * h.get(p, {}).get(resource, 0) for p in production), Fraction(0))
