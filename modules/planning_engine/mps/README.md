# MPS · 이희원

계획 수요·목표 생산량·선행생산(뒤에서부터)·보충(앞에서부터)·재고 추적: [`core.py`](core.py), 규칙 [PLANNING_RULES v0.4](../PLANNING_RULES.md) §2·§3.2·§3.3·§4.
흐름 연결과 판정은 `engine/planning_core.py`. 팀 계약 진입점 `engine.planning.run`은 계약 확정 전까지 `AVAILABLE=False`.
