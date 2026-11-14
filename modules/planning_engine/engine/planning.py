"""Extension point owned by 이희원. Forecast remains in engine.forecast."""
from contracts.interfaces.modules import PlanningInput, PlanningOutput

AVAILABLE = False


def run(request: PlanningInput) -> PlanningOutput:
    raise NotImplementedError('MPS/RCCP/MRP/what-if calculations are not implemented')
