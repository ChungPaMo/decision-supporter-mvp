"""Extension point owned by 이희원. Forecast remains in engine.forecast.

PlanningInput → 계산 코어(MPS/RCCP/MRP, What-if) → PlanningOutput. 변환 규칙은 engine/adapter.py,
계산 규칙은 PLANNING_RULES v0.4.
"""
from contracts.interfaces.modules import PlanningInput, PlanningOutput

from engine.adapter import run as _run

AVAILABLE = True


def run(request: PlanningInput) -> PlanningOutput:
    return _run(request)
