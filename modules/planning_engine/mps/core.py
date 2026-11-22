"""MPS: 계획 수요·목표 생산량·선행생산·보충·재고 (PLANNING_RULES v0.4 §2, §3.2, §3.3, §4)."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import ceil

from rccp.core import Hours, scale_month, used_hours


def planned_demand(forecast: list[Fraction], multiplier: Fraction) -> list[int]:
    """§2-1 d = ⌈ q × 수요배수 ⌉ (곱한 뒤 올림)."""
    return [ceil(q * multiplier) for q in forecast]


def targets(demand: list[int], safety_stock: int, start_inventory: int) -> list[int]:
    """§2-2 T(m) = max(0, d(m) + SS − J(m−1)), J(m) = J(m−1) + T(m) − d(m)."""
    out, j = [], start_inventory
    for d in demand:
        t = max(0, d + safety_stock - j)
        out.append(t)
        j += t - d
    return out


@dataclass
class Balance:
    production: dict[str, list[int]]
    unmade_after_prebuild: dict[str, int]
    unmade_final: dict[str, int]
    resource_factor: list[dict[str, Fraction]]  # 뒤에서부터 계산할 때의 자원별 비율 f(r)
    capacity_binding: list[set[str]]
    quantity_binding: list[set[str]]


def balance(target: dict[str, list[int]], h: Hours, cap: list[dict[str, Fraction | None]],
            limit: list[dict[str, int | None]]) -> Balance:
    """§3.2 뒤에서부터 넘친 양을 앞 달로, §3.3 1월에도 남으면 앞에서부터 남은 시간에 보충.

    h에 없는 제품(라우팅 없음)은 설비 계산 없이 수량 한도만 적용된다(§7). cap 값 None = 한도 모름.
    """
    months = len(cap)
    products = list(target)
    production = {p: [0] * months for p in products}
    factor: list[dict[str, Fraction]] = [{} for _ in range(months)]
    cap_bind: list[set[str]] = [set() for _ in range(months)]
    qty_bind: list[set[str]] = [set() for _ in range(months)]

    carry = {p: 0 for p in products}
    for m in reversed(range(months)):
        want = {p: target[p][m] + carry[p] for p in products}
        res = scale_month(want, cap[m], limit[m], h)
        for p in products:
            production[p][m] = res.production[p]
        carry = res.overflow
        factor[m] = res.resource_factor
        cap_bind[m] |= res.capacity_binding
        qty_bind[m] |= res.quantity_binding
    unmade_after_prebuild = dict(carry)

    unmade = dict(carry)
    for m in range(1, months):
        if not any(unmade.values()):
            break
        current = {p: production[p][m] for p in products}
        cap_left = {r: (None if cap[m][r] is None else cap[m][r] - used_hours(current, h, r)) for r in cap[m]}
        lim_left = {p: (None if limit[m].get(p) is None else limit[m][p] - current[p]) for p in products}
        res = scale_month(unmade, cap_left, lim_left, h)
        for p in products:
            production[p][m] += res.production[p]
        unmade = res.overflow
        cap_bind[m] |= res.capacity_binding
        qty_bind[m] |= res.quantity_binding
    return Balance(production, unmade_after_prebuild, unmade, factor, cap_bind, qty_bind)


def track_inventory(start_inventory: int, production: list[int], demand: list[int]) -> list[int]:
    """§4 I(m) = I(m−1) + P(m) − d(m). 음수면 결품이며 다음 달로 이월된다."""
    out, inv = [], start_inventory
    for p, d in zip(production, demand):
        inv += p - d
        out.append(inv)
    return out
