"""충파모 합성 판매 실적으로 수요예측 백테스트 (Kaggle 실험기록 26-10-26 §7~9 와 같은 절차).

- 입력: synthetic/data/forecast/request.json 의 승인 월 수요(9제품, 2022-01~2026-12).
- rolling-origin: 기준 월 T 마다 T 까지의 실적만으로 실제 엔진 `engine.forecast.run` 을 돌려 T+1~T+3 을 예측한다.
  p50_method=MA12 와 LGBM_L1 을 각각 실행한다(P80·P90 은 배포 설정인 MA12 실행 값).
- 분할: 목표 월 2025 = 검증, 2026 = 테스트. 주 지표는 h=2 WAPE.
- 기준선: naive, ma3, ma6, ma12, snaive. 평가는 엔진이 예측을 낸 (제품, 목표 월, h) 행만 사용한다.

실행: PYTHONUTF8=1 python -m synthetic.forecast_backtest   (modules/planning_engine 에서)
출력: synthetic/data/forecast/backtest_20261126.json (git 제외). 결과 기록은 FORECAST_BACKTEST_20261126.md.
"""

from __future__ import annotations

import calendar
import json
from collections import defaultdict
from pathlib import Path

from engine.forecast.service import run

HERE = Path(__file__).resolve().parent
REQUEST = HERE / "data" / "forecast" / "request.json"
OUT = HERE / "data" / "forecast" / "backtest_20261126.json"
H = (1, 2, 3)
SPLITS = {"validation": 2025, "test": 2026}


def idx(p: str) -> int:
    return int(p[:4]) * 12 + int(p[5:7]) - 1


def label(m: int) -> str:
    return f"{m // 12:04d}-{m % 12 + 1:02d}"


def month_end(m: int) -> str:
    y, mo = m // 12, m % 12 + 1
    return f"{y:04d}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}"


def collect():
    base = json.loads(REQUEST.read_text(encoding="utf-8"))
    rows = base["rows"]
    series: dict[str, dict[int, float]] = defaultdict(dict)
    for r in rows:
        series[r["product_id"]][idx(r["period"])] = float(r["demand_qty"])
    first_target, last_target = idx("2025-01"), idx("2026-12")
    preds = []
    for T in range(first_target - max(H), last_target):
        sub = [r for r in rows if idx(r["period"]) <= T]
        out = {}
        for method in ("MA12", "LGBM_L1"):
            req = dict(base, request_id=f"BT-{label(T)}-{method}", trained_until=month_end(T),
                       p50_method=method, rows=sub)
            res = run(req)
            assert res["status"] in ("OK", "PARTIAL"), (label(T), method, res["status"], res["errors"])
            out[method] = {(f["product_id"], f["horizon"]): f for f in res["forecasts"]}
        for (pid, h), f in out["MA12"].items():
            tm = T + h
            if not first_target <= tm <= last_target:
                continue
            s = series[pid]
            hist = [s.get(m, 0.0) for m in range(min(s), T + 1)]
            actual = s.get(tm, 0.0)
            preds.append({
                "product_id": pid, "origin": label(T), "target": label(tm), "h": h, "actual": actual,
                "ma12": float(f["p50"]), "lgbm": float(out["LGBM_L1"][(pid, h)]["p50"]),
                "p80": float(f["p80"]), "p90": float(f["p90"]),
                "naive": hist[-1], "ma3": sum(hist[-3:]) / 3, "ma6": sum(hist[-6:]) / 6,
                "snaive": s.get(tm - 12, 0.0),
            })
        print(label(T), len(out["MA12"]))
    return preds


def wape(rows, key):
    a = sum(r["actual"] for r in rows)
    return sum(abs(r[key] - r["actual"]) for r in rows) / a, sum(r[key] - r["actual"] for r in rows) / a


def pinball(rows, key, alpha):
    a = sum(r["actual"] for r in rows)
    loss = sum(alpha * (r["actual"] - r[key]) if r["actual"] > r[key] else (1 - alpha) * (r[key] - r["actual"])
               for r in rows)
    return loss / a, sum(r["actual"] <= r[key] for r in rows) / len(rows)


def summarize(preds):
    points = ["ma12", "lgbm", "ma6", "ma3", "snaive", "naive"]
    out = {"points": {}, "quantiles": {}, "per_product_h2": {}, "rows": len(preds)}
    for split, year in SPLITS.items():
        for h in H:
            sel = [r for r in preds if r["h"] == h and r["target"].startswith(str(year))]
            out["points"][f"{split}_h{h}"] = {"n": len(sel), **{k: dict(zip(("wape", "bias"), wape(sel, k))) for k in points}}
            out["quantiles"][f"{split}_h{h}"] = {
                "p80": dict(zip(("pinball", "coverage"), pinball(sel, "p80", 0.8))),
                "p90": dict(zip(("pinball", "coverage"), pinball(sel, "p90", 0.9))),
            }
        sel = [r for r in preds if r["h"] == 2 and r["target"].startswith(str(year))]
        for pid in sorted({r["product_id"] for r in sel}):
            ps = [r for r in sel if r["product_id"] == pid]
            out["per_product_h2"].setdefault(pid, {})[split] = {
                "n": len(ps), "ma12": wape(ps, "ma12")[0], "lgbm": wape(ps, "lgbm")[0],
                "ma12_bias": wape(ps, "ma12")[1], "lgbm_bias": wape(ps, "lgbm")[1],
                "p80_cov": pinball(ps, "p80", 0.8)[1]}
    v = out["points"]["validation_h2"]
    gain = (v["ma12"]["wape"] - v["lgbm"]["wape"]) / v["ma12"]["wape"]
    out["adoption_rule"] = {"lgbm_validation_gain_vs_ma12": gain, "lgbm_validation_bias": v["lgbm"]["bias"],
                            "passes": gain >= 0.05 and abs(v["lgbm"]["bias"]) <= 0.05}
    return out


if __name__ == "__main__":
    preds = collect()
    summary = summarize(preds)
    OUT.write_text(json.dumps({"summary": summary, "predictions": preds}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(json.dumps(summary["points"]["validation_h2"], indent=1))
    print(json.dumps(summary["points"]["test_h2"], indent=1))
    print(json.dumps(summary["adoption_rule"], indent=1))
