"""MRP: 단일 단계 BOM 전개, 입고 예정, 월별 MRP 표 (PLANNING_RULES v0.4 §5, §5.1)."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


def per_unit(qty: Fraction, base_qty: Fraction, scrap_rate: Fraction) -> Fraction:
    """b(p,k) = 소요량 ÷ 기준수량 × (1 + 스크랩률)."""
    return qty / base_qty * (1 + scrap_rate)


@dataclass(frozen=True)
class Receipt:
    po_id: str
    material: str
    open_qty: Fraction
    unit: str
    expected_date: str  # YYYY-MM-DD


@dataclass
class ReceiptPlan:
    by_month: dict[str, list[Fraction]]  # 자재 → 월별 SR
    overdue: dict[str, list[str]]  # 자재 → 납기 지난 발주번호


def schedule_receipts(receipts: list[Receipt], months: list[str], as_of: str, materials: set[str]) -> ReceiptPlan:
    """§5.1 미입고 수량을 입고예정일이 속한 달 전체에 쓴다.

    - 기준일 이전(납기 지남) → 1월, overdue에 기록
    - 기준일 이후지만 계획 시작 전 → 1월
    - 계획 기간 뒤 → 넣지 않음
    - materials(BOM에 쓰이는 자재)에 없는 자재 → 무시
    """
    by_month = {k: [Fraction(0)] * len(months) for k in materials}
    overdue: dict[str, list[str]] = {}
    for r in receipts:
        if r.material not in materials:
            continue
        if r.expected_date <= as_of:
            idx = 0
            overdue.setdefault(r.material, []).append(r.po_id)
        else:
            ym = r.expected_date[:7]
            if ym > months[-1]:
                continue
            idx = months.index(ym) if ym in months else 0
        by_month[r.material][idx] += r.open_qty
    return ReceiptPlan(by_month, overdue)


@dataclass
class MrpRow:
    required: Fraction  # 총소요 N
    available: Fraction  # 가용 AVL = 전월 POH + SR
    shortage: Fraction  # 발주 필요량 NET
    end_on_hand: Fraction  # 월말 재고 POH


def mrp_table(gross: list[Fraction], start_on_hand: Fraction, safety_stock: Fraction,
              receipts: list[Fraction]) -> list[MrpRow]:
    """§5 교과서식 월별 MRP. 부족분은 그달 발주해 그달 받는다고 보고 다음 달로 넘어간다."""
    rows, poh = [], start_on_hand
    for n, sr in zip(gross, receipts):
        avl = poh + sr
        net = max(Fraction(0), n + safety_stock - avl)
        poh = avl + net - n
        rows.append(MrpRow(n, avl, net, poh))
    return rows
