"""upload/05_monthly_demand.csv → 예측 엔진 입력 JSON (forecast-input-0.1-draft) (SYNTHETIC).

백엔드가 승인된 월 수요로 만드는 요청과 같은 모양이다. DB 없이 합성 데이터로 엔진을 바로 돌려 보려고 쓴다.
batch_id에는 원본 CSV의 SHA-256 앞 16자리를 넣어 어떤 파일에서 만든 요청인지 추적할 수 있게 한다.

실행 (저장소 루트):
    python -X utf8 modules/planning_engine/synthetic/forecast_request.py [--demand CSV] [--output JSON]
기본값: data/upload/05_monthly_demand.csv → data/forecast/request.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRAINED_UNTIL = "2026-12-31"
HORIZON = 3


def build(demand_csv: Path) -> dict:
    data = demand_csv.read_bytes()
    batch_id = f"SYN-05-{hashlib.sha256(data).hexdigest()[:16].upper()}"
    with demand_csv.open(encoding="utf-8-sig", newline="") as f:
        rows = [{"product_id": r["product_id"], "period": r["period"], "demand_qty": r["demand_qty"],
                 "unit": r["unit"], "source_type": "SYNTHETIC", "batch_id": batch_id} for r in csv.DictReader(f)]
    return {"contract_version": "forecast-input-0.1-draft", "request_id": f"FREQ-CHUNGPAMO-{TRAINED_UNTIL.replace('-', '')}",
            "trained_until": TRAINED_UNTIL, "horizon_months": HORIZON, "p50_method": "MA12",
            "quantiles": ["P50", "P80", "P90"], "min_history_months": 12, "missing_month_policy": "ZERO_FILL",
            "random_seed": 42, "rows": rows}


def main():
    ap = argparse.ArgumentParser(description="월 수요 CSV → 예측 요청 JSON")
    ap.add_argument("--demand", type=Path, default=HERE / "data" / "upload" / "05_monthly_demand.csv")
    ap.add_argument("--output", type=Path, default=HERE / "data" / "forecast" / "request.json")
    args = ap.parse_args()
    request = build(args.demand)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    products = sorted({r["product_id"] for r in request["rows"]})
    print(f"{args.output}: 제품 {len(products)}개, 행 {len(request['rows'])}개, batch_id {request['rows'][0]['batch_id']}")


if __name__ == "__main__":
    main()
