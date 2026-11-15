"""회사 원본(raw/) → 업로드 파일(upload/) · 분석용 집계(derived/) 변환.

raw는 회사가 가진 원본(회사 말투·회사 양식)이고, upload와 derived는 우리가 raw에서 만든 것이다.
이 스크립트는 raw 파일만 읽는다. 생성기 내부 값은 쓰지 않는다.

실행 (저장소 루트):
    python -X utf8 modules/planning_engine/synthetic/convert.py <raw 폴더> <upload 폴더> <derived 폴더>
"""
from __future__ import annotations

import csv
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate_sales  # noqa: E402

UNIT_TO_BASE = {"팩": "EA", "개": "EA", "kg": "kg"}
KIND = {"설비": ("EQUIPMENT", "MACHINE_HOUR"), "작업자": ("LABOR_POOL", "PERSON_HOUR")}
COST_UNIT = {"원/설비시간": "MACHINE_HOUR", "원/인시": "PERSON_HOUR"}
APPROVAL = {"승인": "APPROVED"}


def read(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def dec(x, places=4):
    q = Decimal(1).scaleb(-places)
    return format(Decimal(x).quantize(q, rounding=ROUND_HALF_UP).normalize(), "f")


def base_unit(u):
    if u not in UNIT_TO_BASE:
        raise ValueError(f"알 수 없는 단위 {u!r}")
    return UNIT_TO_BASE[u]


def convert_all(raw: Path, up: Path, derived: Path):
    m, plans, snaps = raw / "master", raw / "plans", raw / "snapshots"
    products = read(m / "제품마스터.csv")
    materials = read(m / "자재마스터.csv")
    resources = read(m / "설비목록.csv")
    product_order = [p["제품코드"] for p in products]

    write(up / "01_products.csv", ["제품코드", "제품명", "단위", "제품유형", "안전재고"],
          [(p["제품코드"], p["제품명"], p["기준단위"], p["제품유형"], p["안전재고"]) for p in products])
    write(up / "02_materials.csv", ["자재코드", "자재명", "단위", "안전재고"],
          [(r["자재코드"], r["자재명"], r["단위"], r["안전재고"]) for r in materials])

    bom = read(m / "BOM.csv")
    write(up / "03_bom.csv", ["BOM코드", "제품코드", "버전", "상태", "활성", "유효시작일", "유효종료일", "기준수량", "순번",
                              "구성유형", "구성품코드", "소요량", "단위", "스크랩률"],
          [(b["BOM번호"], b["제품코드"], b["버전"], APPROVAL[b["승인상태"]], b["사용여부"], b["적용시작일"],
            b["적용종료일"], b["기준수량"], b["순번"], "MATERIAL", b["자재코드"], b["소요량"], base_unit(b["단위"]),
            format((Decimal(b["손실률(%)"]) / 100).normalize(), "f")) for b in bom])

    stock = read(snaps / "재고현황_20261231.csv")
    write(up / "04_inventory.csv", ["품목구분", "품목코드", "기준일", "현재고", "할당재고", "가용재고", "단위"],
          [("PRODUCT" if s["품목구분"] == "제품" else "MATERIAL", s["품목코드"], s["기준일"], s["현재고"], s["할당재고"],
            s["가용재고"], base_unit(s["단위"])) for s in stock])

    monthly, returns = aggregate_sales.aggregate(aggregate_sales.read_orders(raw / "transactions"))
    aggregate_sales.write_outputs(monthly, returns, product_order, up / "05_monthly_demand.csv",
                                  derived / "returns_monthly.csv")

    write(up / "06_capacity_resources.csv", ["resource_id", "resource_name", "kind", "time_basis", "parallel_units"],
          [(r["설비코드"], r["설비명"], *KIND[r["구분"]], r["대수·인원"]) for r in resources])

    limits = read(plans / "월별생산한도.csv")
    write(up / "07_capacity_quantity_limits.csv",
          ["capacity_id", "product_id", "period", "limit_qty", "unit", "accounting_point", "operation_id"],
          [(q["관리번호"], q["제품코드"], q["적용월"], q["최대생산수량"], base_unit(q["단위"]), "FINISHED_OUTPUT", "")
           for q in limits])

    basis = {r["설비코드"]: KIND[r["구분"]][1] for r in resources}
    rank = {r["설비코드"]: i for i, r in enumerate(resources)}
    hours = sorted(read(plans / "월별가용시간계획.csv"), key=lambda h: (rank[h["설비코드"]], h["적용월"]))
    write(up / "08_capacity_hours_budgets.csv",
          ["capacity_id", "resource_id", "period", "regular_hours", "overtime_hours_limit", "unit", "time_basis",
           "availability_basis", "calendar_ref"],
          [(f"H-{h['설비코드']}", h["설비코드"], h["적용월"], h["정규가용시간(h)"], h["잔업한도(h)"], "h",
            basis[h["설비코드"]], "NET", "") for h in hours])

    routing_rows, prev = [], {}
    for s in read(m / "공정표.csv"):
        extra = []
        if s["1000팩당작업인시"]:
            extra = [{"resource_id": s["작업자코드"], "reference_qty": "1000", "quantity_unit": "EA",
                      "run_time": s["1000팩당작업인시"], "time_unit": "h", "time_basis": "PERSON_HOUR",
                      "concurrent_units": None, "setup_time": None, "setup_policy_ref": None, "alternative_group_ref": None}]
        product = s["제품코드"]
        routing_rows.append((s["설비코드"], s["시간당처리량(팩)"], "EA", 1, "h", "MACHINE_HOUR", "", "", "", "",
                             f"RT-{product}", "V1", s["공정코드"], product, s["공정코드"],
                             json.dumps([prev[product]] if product in prev else []), s["적용시작일"], "",
                             json.dumps(extra, ensure_ascii=False)))
        prev[product] = s["공정코드"]
    write(up / "09_routing_steps.csv",
          ["resource_id", "reference_qty", "quantity_unit", "run_time", "time_unit", "time_basis", "concurrent_units",
           "setup_time", "setup_policy_ref", "alternative_group_ref", "routing_id", "routing_version", "step_id",
           "product_id", "operation_id", "predecessor_step_ids", "valid_from", "valid_to", "resource_requirements"],
          routing_rows)

    # ---- derived: 원가 표(설비·인력 시간당 비용 + 제품 월 재고유지비) ----
    cost_basis = read(m / "원가기준.csv")
    cost_rows, holding_rate = [], None
    for c in cost_basis:
        if c["항목구분"] == "재고유지비율":
            holding_rate = Decimal(c["정규단가"]) / 100
            continue
        unit = COST_UNIT[c["단위"]]
        cost_rows += [("RESOURCE", c["대상코드"], "REGULAR", c["정규단가"], 1, unit, "KRW"),
                      ("RESOURCE", c["대상코드"], "OVERTIME", c["잔업단가"], 1, unit, "KRW")]
    current_price = {p["자재코드"]: Decimal(p["단가"]) for p in read(m / "구매단가표.csv") if not p["적용종료일"]}
    for code in product_order:
        cost = sum(Decimal(b["소요량"]) * (1 + Decimal(b["손실률(%)"]) / 100) * current_price[b["자재코드"]]
                   for b in bom if b["제품코드"] == code)
        cost_rows.append(("PRODUCT", code, "HOLDING_PER_MONTH", dec(cost * holding_rate, 0), 1, "EA", "KRW"))
    write(derived / "costs.csv", ["target_kind", "target_id", "cost_component", "amount", "per_quantity", "quantity_unit",
                                  "currency"], cost_rows)

    write(derived / "scheduled_receipts.csv", ["po_id", "material_id", "qty", "unit", "expected_date", "supplier_id"],
          [(p["발주번호"], p["자재코드"], p["미입고수량"], base_unit(p["단위"]), p["납기예정일"], p["공급사코드"])
           for p in read(snaps / "미입고발주현황_20261231.csv")])
    return monthly, returns


if __name__ == "__main__":
    convert_all(*map(Path, sys.argv[1:4]))
    print("변환 완료")
