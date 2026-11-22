# MRP · 이희원

단일 단계 BOM 전개, 입고 예정 배치, 교과서식 월별 MRP 표(발주 필요량, 음수 없음): [`core.py`](core.py), 규칙 [PLANNING_RULES v0.4](../PLANNING_RULES.md) §5·§5.1.
DB 직접 접근·승인 상태 변경은 하지 않는다. 자재 부족은 생산량을 줄이지 않고 판정을 UNVERIFIED로 둔다.
