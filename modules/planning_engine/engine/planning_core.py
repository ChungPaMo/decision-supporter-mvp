"""계획 엔진 계산 코어 (PLANNING_RULES v0.4). 기간 수와 무관한 순수 계산.

입력은 계산용 내부 형식(손계산 케이스 `tests/hand_calc/small_cases.json`의 input과 같은 모양)이고,
출력도 내부 결과(PlanResult)다. 팀 계약 PlanningInput/PlanningOutput과의 변환은 별도 변환부가 맡는다.

흐름: 입력 검사 → ① 목표량(mps) → ② 한도 맞추기(mps+rccp) → ③ 재고(mps) → ④ 자재(mrp) → ⑤ 판정(여기).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from math import floor
from typing import Any

from mps.core import balance, planned_demand, targets, track_inventory
from mrp.core import Receipt, mrp_table, per_unit, schedule_receipts
from rccp.core import Hours, used_hours

POLICY_REF = 'PLANNING_RULES-v0.4'

# §0 세 계획안: (plan_id, 예측 분위수, 잔업 허용)
PLAN_SPECS = (
    ('BASELINE', 'P50', True),
    ('STABLE', 'P80', True),
    ('COST_SAVING', 'P50', False),
)

_CAP_DIMENSION = {'MACHINE_HOUR': 'EQUIPMENT_HOURS', 'PERSON_HOUR': 'WORK_HOURS'}
_TIME_UNITS = {'h': Fraction(1), 'min': Fraction(1, 60)}


def decimal_str(value: Fraction | int) -> str:
    """10진 문자열(소수 4자리 이하, 0.5는 올림, 끝의 0 제거). Fraction에서 한 번만 반올림한다."""
    v = Fraction(value)
    q = floor(abs(v) * 10000 + Fraction(1, 2))
    if q == 0:
        return '0'
    whole, frac = divmod(q, 10000)
    text = f'{whole}.{frac:04d}'.rstrip('0').rstrip('.')
    return ('-' if v < 0 else '') + text


@dataclass(frozen=True)
class Issue:
    code: str
    input_refs: tuple[str, ...] = ()


@dataclass
class Evaluation:
    constraint_id: str
    dimension: str
    period: str
    status: str
    strength: str
    limit_value: Fraction | None = None
    used_value: Fraction | None = None
    unit: str | None = None
    resource_id: str | None = None
    product_id: str | None = None
    time_basis: str | None = None
    application_state: str = 'APPLIED'
    reason_codes: list[str] = field(default_factory=list)
    input_refs: list[str] = field(default_factory=list)


@dataclass
class MaterialResult:
    material_id: str
    unit: str
    required: list[Fraction]
    available: list[Fraction]
    shortage: list[Fraction]
    end_on_hand: list[Fraction]


@dataclass
class PlanResult:
    status: str  # OK / INPUT_INVALID / UNSUPPORTED
    months: list[str]
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    unverified: list[Issue] = field(default_factory=list)
    planned_demand: dict[str, list[int]] = field(default_factory=dict)
    target: dict[str, list[int]] = field(default_factory=dict)
    unmade_after_prebuild: dict[str, int] = field(default_factory=dict)
    unmade_final: dict[str, int] = field(default_factory=dict)
    production: dict[str, list[int]] = field(default_factory=dict)
    end_inventory: dict[str, list[int]] = field(default_factory=dict)
    scale_factor: dict[str, list[Fraction]] = field(default_factory=dict)
    used_hours: dict[str, list[Fraction]] = field(default_factory=dict)
    overtime_hours: dict[str, list[Fraction | None]] = field(default_factory=dict)
    per_unit: dict[tuple[str, str], Fraction] = field(default_factory=dict)
    materials: dict[str, MaterialResult] = field(default_factory=dict)
    evaluations: list[Evaluation] = field(default_factory=list)
    feasibility: str | None = None
    policy_ref: str = POLICY_REF

    @property
    def stockout(self) -> dict[str, list[int]]:
        return {p: [max(0, -i) for i in inv] for p, inv in self.end_inventory.items()}

    @property
    def error_codes(self) -> set[str]:
        return {i.code for i in self.errors}

    @property
    def unverified_codes(self) -> set[str]:
        return {i.code for i in self.unverified}


def _frac(value: Any) -> Fraction:
    return Fraction(str(value))


def _at(values: list | None, m: int) -> Any:
    """월별 배열의 m번째 값. 배열이 짧거나 값이 비어 있으면 None."""
    if values is None or m >= len(values):
        return None
    return values[m]


def _is_count(value: Any) -> bool:
    try:
        return _frac(value).denominator == 1
    except (ValueError, ZeroDivisionError):
        return False


def _positive(value: Any) -> bool:
    try:
        return _frac(value) > 0
    except (ValueError, ZeroDivisionError):
        return False


def _check_input(data: dict, n: int) -> tuple[list[Issue], list[Issue]]:
    """§7 입력 검사. 첫 문제에서 멈추지 않고 (INPUT_INVALID 대상, UNSUPPORTED 대상)을 모두 모은다."""
    invalid, unsupported = [], []
    product_ids = {p['id'] for p in data['products']}
    materials = {k['id']: k for k in data.get('materials', [])}
    for p in data['products']:
        q = data['demand'].get(p['id'])
        if q is None or len(q) < n or any(v is None for v in q[:n]):
            invalid.append(Issue('FORECAST_MISSING', (p['id'],)))
        if p.get('inventory_unit', p['unit']) != p['unit']:
            invalid.append(Issue('UNIT_MISMATCH', (p['id'],)))
        for key in ('safety_stock', 'on_hand', 'allocated'):
            if key in p and not _is_count(p[key]):
                invalid.append(Issue('INVALID_QUANTITY', (p['id'], key)))
    for p, lims in data.get('quantity_limits', {}).items():
        if any(v is not None and not _is_count(v) for v in lims):
            invalid.append(Issue('INVALID_QUANTITY', (p, 'quantity_limit')))
    for k in materials.values():
        if k.get('inventory_unit', k['unit']) != k['unit']:
            invalid.append(Issue('UNIT_MISMATCH', (k['id'],)))
    for p, steps in data['routing'].items():
        for r, step in steps.items():
            if not _positive(step['reference_qty']):
                invalid.append(Issue('INVALID_QUANTITY', (p, r, 'reference_qty')))
            if step.get('time_unit', 'h') not in _TIME_UNITS:
                invalid.append(Issue('UNIT_MISMATCH', (p, r)))
    bom_materials = set()
    for p, lines in data.get('bom', {}).items():
        for line in lines:
            k = line['material']
            if k in product_ids or line.get('component_type') == 'PRODUCT':
                unsupported.append(Issue('BOM_MULTILEVEL_UNSUPPORTED', (p, k)))
                continue
            bom_materials.add(k)
            if not _positive(line['base_qty']):
                invalid.append(Issue('INVALID_QUANTITY', (p, k, 'base_qty')))
            if k not in materials:
                invalid.append(Issue('MATERIAL_MISSING', (p, k)))
    for r in data.get('receipts', []):
        mat = materials.get(r['material'])
        if r['material'] in bom_materials and mat is not None and r['unit'] != mat['unit']:
            invalid.append(Issue('UNIT_MISMATCH', (r['po_id'],)))
    for r in data['resources']:
        if r.get('time_basis') == 'ELAPSED':
            unsupported.append(Issue('TIME_BASIS_UNSUPPORTED', (r['id'],)))
        if r.get('availability_basis') == 'GROSS':
            unsupported.append(Issue('AVAILABILITY_BASIS_UNSUPPORTED', (r['id'],)))
    return invalid, unsupported


def _routing_hours(data: dict) -> tuple[Hours, list[Issue]]:
    """§1 h(p,r) = run_time ÷ reference_qty (min은 ÷60). 셋업·대체 설비는 반영하지 않고 unverified."""
    h: Hours = {}
    ignored: list[Issue] = []
    for p, steps in data['routing'].items():
        h[p] = {}
        for r, step in steps.items():
            hours = _frac(step['run_time']) / _frac(step['reference_qty']) * _TIME_UNITS[step.get('time_unit', 'h')]
            h[p][r] = h[p].get(r, Fraction(0)) + hours
            if step.get('setup_time') not in (None, '0', 0):
                ignored.append(Issue('SETUP_TIME_IGNORED', (p, r)))
            if step.get('alternative_group'):
                ignored.append(Issue('ALTERNATIVE_RESOURCE_IGNORED', (p, r)))
    return h, ignored


def calculate(data: dict) -> PlanResult:
    """계획안 하나를 계산한다. data['demand']는 그 안이 쓰는 분위수, data['ot_allowed']는 잔업 허용 여부."""
    months: list[str] = list(data['months'])
    n = len(months)
    invalid, unsupported = _check_input(data, n)
    if invalid:
        return PlanResult('INPUT_INVALID', months, errors=invalid + unsupported)
    if unsupported:
        return PlanResult('UNSUPPORTED', months, errors=unsupported)

    result = PlanResult('OK', months)
    products = [p['id'] for p in data['products']]
    multiplier = _frac(data.get('demand_multiplier', '1'))

    # 재고 (§7 재고 누락 → 0 + 경고 + unverified)
    start_inv: dict[str, int] = {}
    for p in data['products']:
        if 'on_hand' not in p:
            start_inv[p['id']] = 0
            result.warnings.append(Issue('INVENTORY_MISSING', (p['id'],)))
            result.unverified.append(Issue('INVENTORY_MISSING', (p['id'],)))
        else:
            start_inv[p['id']] = int(_frac(p['on_hand'])) - int(_frac(p.get('allocated', 0)))

    # ① 계획 수요·목표 생산량
    for p in data['products']:
        pid = p['id']
        result.planned_demand[pid] = planned_demand([_frac(q) for q in data['demand'][pid][:n]], multiplier)
        result.target[pid] = targets(result.planned_demand[pid], int(_frac(p['safety_stock'])), start_inv[pid])

    # ② 쓸 수 있는 시간 (§3, §7 가용시간·잔업 한도 없음)
    h, ignored = _routing_hours(data)
    result.unverified.extend(ignored)
    routed = [p for p in products if p in h]
    unrouted = [p for p in products if p not in h]
    for p in unrouted:
        result.unverified.append(Issue('ROUTING_MISSING', (p,)))
    ot_allowed = bool(data['ot_allowed'])
    resources = {r['id']: r for r in data['resources']}
    for p in routed:  # 공정표에는 있는데 자원 목록에 없는 자원 → 한도 모름
        for rid in h[p]:
            if rid not in resources:
                resources[rid] = {'id': rid, 'time_basis': None, 'regular': [], 'overtime': []}
    cap: list[dict[str, Fraction | None]] = [{} for _ in range(n)]
    regular: dict[str, list[Fraction | None]] = {}
    for rid, r in resources.items():
        regular[rid] = []
        for m in range(n):
            reg = _at(r.get('regular'), m)
            regular[rid].append(None if reg is None else _frac(reg))
            if reg is None:
                cap[m][rid] = None
                result.unverified.append(Issue('CAPACITY_MISSING', (rid, months[m])))
                continue
            ot = Fraction(0)
            if ot_allowed:
                raw = _at(r.get('overtime'), m)
                if raw is None:
                    result.warnings.append(Issue('OVERTIME_LIMIT_MISSING', (rid, months[m])))
                else:
                    ot = _frac(raw)
            cap[m][rid] = _frac(reg) + ot
    limits = data.get('quantity_limits', {})
    limit = [{p: (None if _at(limits.get(p), m) is None else int(_frac(limits[p][m]))) for p in products}
             for m in range(n)]

    # ② 한도 맞추기 (라우팅 없는 제품은 설비 없이 수량 한도만)
    bal = balance(result.target, h, cap, limit)
    result.production = bal.production
    result.unmade_after_prebuild = bal.unmade_after_prebuild
    result.unmade_final = bal.unmade_final
    result.scale_factor = {rid: [bal.resource_factor[m][rid] for m in range(n)] for rid in resources}

    # ③ 재고·사용시간
    for p in products:
        result.end_inventory[p] = track_inventory(start_inv[p], result.production[p], result.planned_demand[p])
    for rid in resources:
        result.used_hours[rid] = [used_hours({p: result.production[p][m] for p in routed}, h, rid) for m in range(n)]
        result.overtime_hours[rid] = [None if regular[rid][m] is None
                                      else max(Fraction(0), result.used_hours[rid][m] - regular[rid][m])
                                      for m in range(n)]

    # ⑤-1 설비·수량·수요·안전재고 판정
    for rid, r in resources.items():
        basis = r.get('time_basis')
        for m in range(n):
            ev = Evaluation(f'CAP-{rid}-{months[m]}', _CAP_DIMENSION.get(basis, 'OTHER'), months[m], 'SATISFIED',
                            'HARD', limit_value=cap[m][rid], unit=basis, resource_id=rid, time_basis=basis)
            if unrouted:
                ev.status, ev.application_state, ev.input_refs = 'UNVERIFIED', 'MISSING_INPUT', list(unrouted)
            elif cap[m][rid] is None:
                ev.status, ev.application_state, ev.used_value = 'UNVERIFIED', 'MISSING_INPUT', result.used_hours[rid][m]
            else:
                ev.used_value = result.used_hours[rid][m]
                if rid in bal.capacity_binding[m]:
                    ev.reason_codes.append('CAPACITY_BINDING')
            result.evaluations.append(ev)
    unit_of = {p['id']: p['unit'] for p in data['products']}
    for p in products:
        for m in range(n):
            if limit[m][p] is None:
                continue
            result.evaluations.append(Evaluation(
                f'QTY-{p}-{months[m]}', 'QUANTITY', months[m], 'SATISFIED', 'HARD', limit_value=Fraction(limit[m][p]),
                used_value=Fraction(result.production[p][m]), unit=unit_of[p], product_id=p,
                reason_codes=['QUANTITY_LIMIT_BINDING'] if p in bal.quantity_binding[m] else []))
    for p in data['products']:
        pid, ss = p['id'], int(_frac(p['safety_stock']))
        for m in range(n):
            inv = result.end_inventory[pid][m]
            result.evaluations.append(Evaluation(
                f'DEM-{pid}-{months[m]}', 'OTHER', months[m], 'VIOLATED' if inv < 0 else 'SATISFIED', 'HARD',
                unit=p['unit'], product_id=pid, reason_codes=['STOCKOUT'] if inv < 0 else []))
            result.evaluations.append(Evaluation(
                f'SS-{pid}-{months[m]}', 'SAFETY_STOCK', months[m], 'VIOLATED' if inv < ss else 'SATISFIED', 'SOFT',
                limit_value=Fraction(ss), used_value=Fraction(inv), unit=p['unit'], product_id=pid,
                reason_codes=['BELOW_SAFETY_STOCK'] if inv < ss else []))

    # ④ 자재 MRP와 ⑤-2 자재 판정
    _materials(data, result, products, months)

    # ⑤-3 계획안 판정
    hard = [e.status for e in result.evaluations if e.strength == 'HARD']
    if 'VIOLATED' in hard:
        result.feasibility = 'INFEASIBLE'
    elif 'UNVERIFIED' in hard or result.unverified:
        result.feasibility = 'UNVERIFIED'
    else:
        result.feasibility = 'FEASIBLE'
    return result


def _materials(data: dict, result: PlanResult, products: list[str], months: list[str]) -> None:
    """§5 자재 MRP. BOM에 쓰이는 자재만 계산한다(안 쓰는 자재는 표·판정·재고 누락 검사에서 제외)."""
    if 'bom' not in data and not data.get('materials'):
        return
    n = len(months)
    bom = data.get('bom', {})
    for p, lines in bom.items():
        for line in lines:
            key = (p, line['material'])
            result.per_unit[key] = result.per_unit.get(key, Fraction(0)) + per_unit(
                _frac(line['qty']), _frac(line['base_qty']), _frac(line.get('scrap_rate', '0')))
    no_bom = [p for p in products if p not in bom]
    for p in no_bom:  # 그 제품이 쓰는 자재를 모름 → 모든 MAT UNVERIFIED (라우팅 누락과 같은 방식)
        result.warnings.append(Issue('BOM_MISSING', (p,)))
        result.unverified.append(Issue('BOM_MISSING', (p,)))
    used = {k for (_, k) in result.per_unit}
    receipts = [Receipt(r['po_id'], r['material'], _frac(r['open_qty']), r['unit'], r['expected_date'])
                for r in data.get('receipts', [])]
    if receipts and 'as_of' not in data:
        raise ValueError('as_of is required when receipts are given')
    plan = schedule_receipts(receipts, months, data.get('as_of', ''), used)
    for k, pos in plan.overdue.items():
        for po in pos:
            result.warnings.append(Issue('RECEIPT_OVERDUE', (po,)))
    for mat in data.get('materials', []):
        kid = mat['id']
        if kid not in used:
            continue
        if 'on_hand' not in mat:
            start = Fraction(0)
            result.warnings.append(Issue('INVENTORY_MISSING', (kid,)))
            result.unverified.append(Issue('INVENTORY_MISSING', (kid,)))
        else:
            start = _frac(mat['on_hand']) - _frac(mat.get('allocated', '0'))
        ss = _frac(mat.get('safety_stock', '0'))
        gross = [sum((Fraction(result.production[p][m]) * result.per_unit.get((p, kid), 0) for p in products),
                     Fraction(0)) for m in range(n)]
        rows = mrp_table(gross, start, ss, plan.by_month[kid])
        result.materials[kid] = MaterialResult(kid, mat['unit'], [r.required for r in rows],
                                               [r.available for r in rows], [r.shortage for r in rows],
                                               [r.end_on_hand for r in rows])
        for m, row in enumerate(rows):
            reasons = (['PROCUREMENT_REQUIRED'] if row.shortage > 0 else []) + \
                      (['RECEIPT_OVERDUE'] if m == 0 and kid in plan.overdue else [])
            ev = Evaluation(f'MAT-{kid}-{months[m]}', 'MATERIAL', months[m], 'UNVERIFIED' if reasons else 'SATISFIED',
                            'HARD', limit_value=row.available, used_value=row.required + ss, unit=mat['unit'],
                            reason_codes=reasons, input_refs=list(plan.overdue.get(kid, [])) if m == 0 else [])
            if no_bom:
                ev.status, ev.application_state = 'UNVERIFIED', 'MISSING_INPUT'
                ev.input_refs = ev.input_refs + no_bom
            result.evaluations.append(ev)


def calculate_plans(data: dict) -> dict[str, PlanResult]:
    """세 계획안(§0)을 계산한다. data['forecast'] = {'P50': {제품: [...]}, 'P80': {...}}.

    분위수가 통째로 없으면 그 안의 모든 제품을 예측 누락으로 본다(INPUT_INVALID).
    """
    out = {}
    for plan_id, quantile, ot_allowed in PLAN_SPECS:
        out[plan_id] = calculate({**data, 'demand': data['forecast'].get(quantile, {}), 'ot_allowed': ot_allowed})
    return out
