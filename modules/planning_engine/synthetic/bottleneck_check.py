"""병목 어림 점검: 예측 P50/P80/P90 각각에서 설비 시간과 자재가 버티는지 본다 (SYNTHETIC).

설계 확인용 어림 계산이다. 계획 엔진의 정답이 아니다(정답은 손계산으로 따로 만든다).
계획 엔진이 받을 자료(upload 파일 + 입고 예정 + 예측 결과)만 읽는다.

규칙 (가장 단순한 "그달 필요한 만큼 그달 생산"):
  생산 필요량  1월 = max(0, 예측 + 안전재고 − 기초재고), 2·3월 = 예측 (안전재고는 1월에 맞춘 뒤 유지)
  설비 부하    생산 필요량 × 공정표 시간 → 정규시간, 정규+잔업 한도와 비교
  자재 여유    (기초재고 + 그달까지 들어올 입고 예정) − 그달까지 누적 소요 − 안전재고
               새 발주는 넣지 않는다. 음수면 "그때까지 추가 입고가 필요하다"는 뜻
  수량 한도    선물세트 월 생산 한도와 비교

실행 (저장소 루트):
    python -X utf8 modules/planning_engine/synthetic/bottleneck_check.py
"""
from __future__ import annotations

import csv
import json
import math
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SCENARIOS = ["p50", "p80", "p90"]


def read(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load():
    up = DATA / "upload"
    forecast = json.loads((DATA / "forecast" / "forecast.json").read_text(encoding="utf-8"))
    products = {r["제품코드"]: r for r in read(up / "01_products.csv")}
    materials = {r["자재코드"]: r for r in read(up / "02_materials.csv")}
    stock = {r["품목코드"]: Decimal(r["가용재고"]) for r in read(up / "04_inventory.csv")}
    bom = {}
    for b in read(up / "03_bom.csv"):
        bom.setdefault(b["제품코드"], []).append((b["구성품코드"], Decimal(b["소요량"]) * (1 + Decimal(b["스크랩률"]))))
    unit_hours = {}                                   # 제품 → {자원: 1개당 시간}
    for s in read(up / "09_routing_steps.csv"):
        h = unit_hours.setdefault(s["product_id"], {})
        reqs = [{"resource_id": s["resource_id"], "reference_qty": s["reference_qty"], "run_time": s["run_time"]}]
        reqs += json.loads(s["resource_requirements"])
        for r in reqs:
            h[r["resource_id"]] = h.get(r["resource_id"], Decimal(0)) + Decimal(r["run_time"]) / Decimal(r["reference_qty"])
    hours = {(r["resource_id"], r["period"]): (Decimal(r["regular_hours"]), Decimal(r["overtime_hours_limit"]))
             for r in read(up / "08_capacity_hours_budgets.csv")}
    limits = {(r["product_id"], r["period"]): Decimal(r["limit_qty"]) for r in read(up / "07_capacity_quantity_limits.csv")}
    receipts = [(r["material_id"], r["expected_date"][:7], Decimal(r["qty"]))
                for r in read(DATA / "derived" / "scheduled_receipts.csv")]
    resources = [r["resource_id"] for r in read(up / "06_capacity_resources.csv")]
    return forecast, products, materials, stock, bom, unit_hours, hours, limits, receipts, resources


def check():
    forecast, products, materials, stock, bom, unit_hours, hours, limits, receipts, resources = load()
    months = sorted({f["target_month"] for f in forecast["forecasts"]})
    fc = {(f["product_id"], f["target_month"], s): Decimal(f[s]) for f in forecast["forecasts"] for s in SCENARIOS}
    result = {}
    for s in SCENARIOS:
        need = {}
        for p, info in products.items():
            for i, m in enumerate(months):
                f = fc[(p, m, s)]
                q = max(Decimal(0), f + Decimal(info["안전재고"]) - stock[p]) if i == 0 else f
                need[(p, m)] = Decimal(math.ceil(q))
        load_ = {(r, m): sum(need[(p, m)] * unit_hours[p].get(r, 0) for p in products) for r in resources for m in months}
        mat_use = {(mat, m): sum(need[(p, m)] * per for p in products for mm, per in bom[p] if mm == mat)
                   for mat in materials for m in months}
        slack = {}
        for mat, info in materials.items():
            cum_use = Decimal(0)
            for m in months:
                cum_use += mat_use[(mat, m)]
                arrived = sum(q for mm, rm, q in receipts if mm == mat and rm <= m)
                slack[(mat, m)] = stock[mat] + arrived - cum_use - Decimal(info["안전재고"])
        result[s] = {"need": need, "load": load_, "mat_use": mat_use, "slack": slack}
    return result, months, products, materials, hours, limits, resources, receipts, stock


def report():
    result, months, products, materials, hours, limits, resources, receipts, stock = check()
    L = ["# 병목 어림 점검 (SYNTHETIC)", "",
         "설계 확인용 어림이며 계획 엔진 정답이 아니다. 규칙: 1월 = 예측 + 안전재고 − 기초재고, 2·3월 = 예측.", "",
         "## 설비·인력 부하 (정규시간 대비 %)", "",
         "괄호는 부하(h). 100% 초과 = 잔업 필요, `!!` = 정규+잔업 한도도 초과.", "",
         "| 자원 | 월 | 정규 / 잔업한도 | " + " | ".join(s.upper() for s in SCENARIOS) + " |", "|---|---|---|---|---|---|"]
    for r in resources:
        for m in months:
            reg, ot = hours[(r, m)]
            cells = []
            for s in SCENARIOS:
                h = result[s]["load"][(r, m)]
                mark = " !!" if h > reg + ot else (" 잔업" if h > reg else "")
                cells.append(f"{float(h / reg):.0%} ({float(h):,.0f}){mark}")
            L.append(f"| {r} | {m} | {reg} / {ot} | " + " | ".join(cells) + " |")
    L += ["", "## 자재 여유 (기초재고 + 입고예정 − 누적 소요 − 안전재고)", "",
          "음수 = 그달 말까지 새 발주 입고가 그만큼 더 필요. 입고 예정: " +
          ", ".join(f"{mat} {q:,} ({m})" for mat, m, q in receipts), "",
          "| 자재 | 월 | " + " | ".join(s.upper() for s in SCENARIOS) + " |", "|---|---|---|---|---|"]
    for mat in materials:
        for m in months:
            cells = []
            for s in SCENARIOS:
                v = result[s]["slack"][(mat, m)]
                cells.append(f"{float(v):,.0f}" + (" 부족" if v < 0 else ""))
            L.append(f"| {mat} | {m} | " + " | ".join(cells) + " |")
    L += ["", "## 수량 한도", "", "| 제품 | 월 | 한도 | " + " | ".join(s.upper() for s in SCENARIOS) + " |", "|---|---|---|---|---|---|"]
    for (p, m), lim in sorted(limits.items()):
        cells = [f"{float(result[s]['need'][(p, m)]):,.0f}" + (" 초과" if result[s]["need"][(p, m)] > lim else "")
                 for s in SCENARIOS]
        L.append(f"| {p} | {m} | {lim:,} | " + " | ".join(cells) + " |")
    L += ["", "## 생산 필요량 (팩)", "", "| 제품 | 기초재고 | " + " | ".join(f"{m} {s.upper()}" for m in months for s in SCENARIOS) + " |",
          "|---|---|" + "---|" * (len(months) * 3)]
    for p in products:
        L.append(f"| {p} | {stock[p]:,} | " + " | ".join(f"{float(result[s]['need'][(p, m)]):,.0f}" for m in months for s in SCENARIOS) + " |")
    text = "\n".join(L) + "\n"
    out = DATA / "forecast" / "bottleneck_check.md"
    out.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(report())
