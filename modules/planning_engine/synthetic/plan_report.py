"""㈜충파모제지 세 계획안 결과 요약 문서 (SYNTHETIC). 계산 코어 결과를 사람이 읽는 표로 정리한다.

입력: modules/planning_engine/tests/chungpamo/plan_input.json
출력: modules/planning_engine/tests/chungpamo/RESULT.md
실행: PYTHONUTF8=1 .venv/Scripts/python.exe -X utf8 modules/planning_engine/synthetic/plan_report.py
(pytest.ini의 pythonpath처럼 modules/planning_engine를 import 경로에 넣는다)
"""
from __future__ import annotations

import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.planning_core import PLAN_SPECS, calculate_plans, decimal_str  # noqa: E402
from what_if.core import run_what_if  # noqa: E402

DIR = ROOT / 'tests' / 'chungpamo'
SCENARIOS = [
    ('2월 절단기 특근', {'overtime_hours_limit.SAW1.2027-02': '80'}),
    ('수요 10% 증가', {'demand_multiplier': '1.1'}),
    ('1/20 원단 입고 취소', {'receipt_qty.PO-2701-001': '0'}),
]
LABEL = {'BASELINE': '기준형 (P50 + 잔업)', 'STABLE': '안정형 (P80 + 잔업)', 'COST_SAVING': '비용절감형 (P50, 잔업 0)'}


def fmt(x) -> str:
    return '–' if x is None else decimal_str(x)


def jan_orders(r) -> str:
    """1월 발주 필요량이 있는 자재 (장면 비교용)."""
    items = [f'{k} {fmt(m.shortage[0])}' for k, m in r.materials.items() if m.shortage[0] > 0]
    return ', '.join(items) or '없음'


def main() -> None:
    data = json.loads((DIR / 'plan_input.json').read_text(encoding='utf-8'))
    results = calculate_plans(data)
    months = data['months']
    out = ['# ㈜충파모제지 2027-01~03 세 계획안 결과 (SYNTHETIC)', '',
           f'계산 코어 `engine/planning_core.py`, 규칙 [PLANNING_RULES v0.4](../../PLANNING_RULES.md). '
           f'입력 [plan_input.json](plan_input.json)(`{data["source_digest"][:19]}…`, 예측 `{data["forecast_input_digest"][:19]}…`). '
           '독립 계산 정답 [expected.json](expected.json)과 일치하는지는 `tests/test_chungpamo_plan.py`가 확인한다. '
           '`synthetic/plan_report.py`로 생성하며 손으로 고치지 않는다.', '',
           '## 한눈에', '', '| 안 | 판정 | 결품 합계(EA) | 잔업 합계(h) | 한도에 걸린 설비·월 | 발주 필요 자재·월 |', '|---|---|---|---|---|---|']
    for plan_id, _, _ in PLAN_SPECS:
        r = results[plan_id]
        stock = sum(sum(v) for v in r.stockout.values())
        ot = sum((x for v in r.overtime_hours.values() for x in v if x is not None), Fraction(0))
        bind = [e.constraint_id[4:] for e in r.evaluations if 'CAPACITY_BINDING' in e.reason_codes]
        mats = sum(1 for e in r.evaluations if e.constraint_id.startswith('MAT-') and e.status != 'SATISFIED')
        out.append(f'| {LABEL[plan_id]} | **{r.feasibility}** | {stock:,} | {fmt(ot)} | {", ".join(bind) or "없음"} | {mats}건 |')
    for plan_id, _, _ in PLAN_SPECS:
        r = results[plan_id]
        out += ['', f'## {LABEL[plan_id]} — {r.feasibility}', '',
                '| 제품 | 계획 수요 | 생산 | 월말 재고 | 결품 |', '|---|---|---|---|---|']
        for p in r.production:
            out.append(f'| {p} | {" / ".join(map(str, r.planned_demand[p]))} | {" / ".join(map(str, r.production[p]))} '
                       f'| {" / ".join(map(str, r.end_inventory[p]))} | {" / ".join(map(str, r.stockout[p]))} |')
        out += ['', '| 자원 | 한도(h) | 사용(h) | 잔업(h) |', '|---|---|---|---|']
        for rid in r.used_hours:
            caps = [e.limit_value for m in months for e in r.evaluations if e.constraint_id == f'CAP-{rid}-{m}']
            out.append(f'| {rid} | {" / ".join(fmt(c) for c in caps)} | {" / ".join(fmt(u) for u in r.used_hours[rid])} '
                       f'| {" / ".join(fmt(o) for o in r.overtime_hours[rid])} |')
        out += ['', '| 자재 | 총소요 | 가용 | 발주 필요량 | 월말 재고 |', '|---|---|---|---|---|']
        for k, mr in r.materials.items():
            out.append(f'| {k} ({mr.unit}) | {" / ".join(fmt(x) for x in mr.required)} | {" / ".join(fmt(x) for x in mr.available)} '
                       f'| {" / ".join(fmt(x) for x in mr.shortage)} | {" / ".join(fmt(x) for x in mr.end_on_hand)} |')
        if r.warnings or r.unverified:
            out += ['', '경고·확인 불가: ' + ', '.join(sorted({i.code for i in r.warnings + r.unverified}))]
    out += ['', '## What-if 시연 장면', '', '각 장면은 세 안을 모두 다시 계산한 결과다(규칙서 §8). 화살표 왼쪽이 기준, 오른쪽이 변경 후.', '',
            '| 장면 | 변경 | 안 | 판정 | 결품 합계 | 잔업 합계(h) | 1월 발주 필요(자재 단위) |', '|---|---|---|---|---|---|---|']
    for title, overrides in SCENARIOS:
        r = run_what_if(data, overrides)
        for d in r.deltas():
            out.append(f'| {title} | `{", ".join(f"{k}={v}" for k, v in overrides.items())}` | {LABEL[d.plan_id]} '
                       f'| {d.feasibility[0]} → {d.feasibility[1]} | {d.stockout_total[0]:,} → {d.stockout_total[1]:,} '
                       f'| {fmt(d.overtime_total[0])} → {fmt(d.overtime_total[1])} '
                       f'| {jan_orders(r.base[d.plan_id])} → {jan_orders(r.scenario[d.plan_id])} |')
    out.append('')
    (DIR / 'RESULT.md').write_text('\n'.join(out), encoding='utf-8')
    print(DIR / 'RESULT.md')


if __name__ == '__main__':
    main()
