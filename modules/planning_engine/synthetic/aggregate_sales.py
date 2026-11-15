"""판매(출고) 내역 → 월별 수요 변환.

규칙
- 월 수요 = 주문일자 기준, 구분이 '정상'인 행의 수량 합.
- '취소' 행은 제외한다.
- '반품' 행은 수요에서 빼지 않고 반품 월(접수일 기준)별로 따로 집계한다.
- 단위 '팩'은 제품 기준 단위 'EA'로 본다. 그 밖의 단위가 나오면 멈춘다.

실행 (저장소 루트):
    python -X utf8 modules/planning_engine/synthetic/aggregate_sales.py <판매내역 폴더> <월수요 CSV> <반품 CSV> [제품 CSV]

제품 CSV(첫 열이 제품코드)를 주면 그 순서로 행을 정렬하고, 없으면 제품코드 순으로 정렬한다.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

UNIT_MAP = {"팩": "EA", "EA": "EA"}


def read_orders(folder: Path, pattern: str = "판매현황_*.csv"):
    for path in sorted(folder.glob(pattern)):
        with path.open(encoding="utf-8-sig", newline="") as f:
            yield from csv.DictReader(f)


def aggregate(rows):
    demand, returns = {}, {}
    for r in rows:
        unit = UNIT_MAP.get(r["단위"])
        if unit is None:
            raise ValueError(f"알 수 없는 단위 {r['단위']!r}: 주문번호 {r['주문번호']}")
        key = (r["제품코드"], r["주문일자"][:7])
        qty = int(r["수량"])
        if r["구분"] == "정상":
            demand[key] = demand.get(key, 0) + qty
        elif r["구분"] == "반품":
            returns[key] = returns.get(key, 0) + (-qty)
        elif r["구분"] != "취소":
            raise ValueError(f"알 수 없는 구분 {r['구분']!r}: 주문번호 {r['주문번호']}")
    return demand, returns


def write(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def write_outputs(demand, returns, product_order, demand_csv: Path, returns_csv: Path):
    rank = {p: i for i, p in enumerate(product_order)}
    keys = sorted(demand, key=lambda k: (rank.get(k[0], len(rank)), k[0], k[1]))
    write(demand_csv, ["product_id", "period", "demand_qty", "unit"], [(p, m, demand[(p, m)], "EA") for p, m in keys])
    rkeys = sorted(returns, key=lambda k: (rank.get(k[0], len(rank)), k[0], k[1]))
    write(returns_csv, ["product_id", "period", "return_qty", "unit"], [(p, m, returns[(p, m)], "EA") for p, m in rkeys])


def main(argv):
    folder, demand_csv, returns_csv = map(Path, argv[1:4])
    demand, returns = aggregate(read_orders(folder))
    products = sorted({p for p, _ in demand})
    if len(argv) > 4:
        with Path(argv[4]).open(encoding="utf-8-sig", newline="") as f:
            products = [row[0] for row in list(csv.reader(f))[1:]]
    write_outputs(demand, returns, products, demand_csv, returns_csv)
    print(f"월 수요 {len(demand)}행, 반품 {len(returns)}행")


if __name__ == "__main__":
    main(sys.argv)
