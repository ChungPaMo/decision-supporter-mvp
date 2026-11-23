"""팀 계약 PlanningInput → 계산 코어 내부 형식 → PlanningOutput 변환 (PLANNING_RULES v0.4 §11).

계산은 하지 않는다. 계산은 `engine.planning_core`(세 안)와 `what_if.core`(변경 조건 적용)가 한다.
여기서 정하는 것은 계약 값을 계산 입력으로 옮기는 규칙뿐이다.

- 기간: `command.months`(시작 월부터 연속 1~12개월)
- 월별 BOM·라우팅 버전: 그달 1일~말일 전체에 유효한 APPROVED·활성 버전 1개를 그달에 쓴다.
  달 중간에 시작·종료되는 버전 → UNSUPPORTED(*_VERSION_MIDMONTH), 전체 유효 버전 2개 이상 → INPUT_INVALID(*_VERSION_AMBIGUOUS),
  0개 → 그달 BOM·라우팅 없음(코어가 UNVERIFIED 처리)
- 재고: 기준일 이하 가장 최근 기준일 1행. 같은 날 2행 이상 → INPUT_INVALID(INVENTORY_AMBIGUOUS), 할당 > 현재고 → INVALID_QUANTITY
- 자원: 선택 제품의 선택 라우팅이 쓰는 자원만 계산·판정한다. ID가 28자를 넘으면 ID_TOO_LONG(판정 ID 40자 제한)
- 시간 예산: 자원·월당 1행(2행 이상 INPUT_INVALID CAPACITY_AMBIGUOUS), min은 h로 환산
- 수량 한도: 제품·월 여러 행이면 가장 작은 값. OPERATION_OUTPUT 기준은 UNSUPPORTED
- 입고 예정: null(공급 미연결)이면 입고 0으로 계산하고 unverified RECEIPT_SOURCE_UNAVAILABLE
- missing_inputs: 코드마다 출력 unverified로 그대로 전달 → 어떤 안도 FEASIBLE이 되지 않는다
- WHAT_IF: command.overrides를 `what_if.core.apply_overrides`로 적용해 세 안을 다시 계산한다(부모 비교는 백엔드)
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from fractions import Fraction

from contracts.interfaces.modules import PlanningInput, PlanningOutput
from engine.planning_core import PLAN_SPECS, POLICY_REF, Evaluation, Issue, PlanResult, calculate_plans, decimal_str
from what_if.core import apply_overrides

MODULE_VERSION = f'chungpamo-planning/{POLICY_REF}'
LABELS = {'BASELINE': '기준형 (P50 + 잔업)', 'STABLE': '안정형 (P80 + 잔업)', 'COST_SAVING': '비용절감형 (P50, 잔업 0)'}
_TIME_UNITS = {'h': Fraction(1), 'min': Fraction(1, 60)}
_HOUR_DIMENSIONS = {'EQUIPMENT_HOURS', 'WORK_HOURS'}
_MAX_ID = 40 - len('CAP-') - len('-2027-01')

MESSAGES = {
    'FORECAST_MISSING': '계획 기간의 수요예측이 없습니다.',
    'UNIT_MISMATCH': '단위가 기준 단위와 다릅니다.',
    'INVALID_QUANTITY': '수량 값이 올바르지 않습니다(정수·양수 조건).',
    'MATERIAL_MISSING': 'BOM 자재가 자재 목록에 없습니다.',
    'PRODUCT_MISSING': '요청 제품이 승인 제품 목록에 없습니다.',
    'INVENTORY_AMBIGUOUS': '같은 기준일의 재고 행이 둘 이상입니다.',
    'CAPACITY_AMBIGUOUS': '같은 자원·월의 시간 예산 행이 둘 이상입니다.',
    'BOM_VERSION_AMBIGUOUS': '그달 전체에 유효한 BOM 버전이 둘 이상입니다.',
    'ROUTING_VERSION_AMBIGUOUS': '그달 전체에 유효한 라우팅 버전이 둘 이상입니다.',
    'BOM_VERSION_MIDMONTH': '달 중간에 BOM 버전이 바뀌는 경우는 지원하지 않습니다.',
    'ROUTING_VERSION_MIDMONTH': '달 중간에 라우팅 버전이 바뀌는 경우는 지원하지 않습니다.',
    'BOM_MULTILEVEL_UNSUPPORTED': '다단계 BOM(반제품 구성)은 지원하지 않습니다.',
    'TIME_BASIS_UNSUPPORTED': 'ELAPSED 시간 기준은 지원하지 않습니다.',
    'AVAILABILITY_BASIS_UNSUPPORTED': 'GROSS 가용시간 기준은 지원하지 않습니다.',
    'QUANTITY_LIMIT_POINT_UNSUPPORTED': '공정 산출(OPERATION_OUTPUT) 기준 수량 한도는 지원하지 않습니다.',
    'ID_TOO_LONG': f'ID가 너무 깁니다(판정 ID에 쓰려면 {40 - 12}자 이하).',
    'ROUTING_STEP_VALIDITY_MIXED': '한 라우팅 버전 안에서 단계마다 유효기간이 다른 경우는 지원하지 않습니다.',
    'WHATIF_INVALID': '변경 조건(What-if)이 올바르지 않습니다.',
    'INVENTORY_MISSING': '재고가 없어 0으로 계산했습니다.',
    'ROUTING_MISSING': '라우팅이 없어 설비 사용시간을 계산하지 못했습니다.',
    'BOM_MISSING': 'BOM이 없어 자재 소요를 계산하지 못했습니다.',
    'CAPACITY_MISSING': '시간 예산이 없어 설비 한도를 확인하지 못했습니다.',
    'OVERTIME_LIMIT_MISSING': '잔업 한도가 없어 잔업 0으로 계산했습니다.',
    'RECEIPT_OVERDUE': '납기가 지난 미입고 발주를 첫 달 입고로 계산했습니다.',
    'RECEIPT_SOURCE_UNAVAILABLE': '승인된 입고 예정 자료가 연결되지 않아 입고 0으로 계산했습니다.',
    'SETUP_TIME_IGNORED': '셋업 시간은 반영하지 않았습니다.',
    'ALTERNATIVE_RESOURCE_IGNORED': '대체 설비는 반영하지 않았습니다.',
    'POLICY_APPLIED': '계산 규칙',
    'BOM_VERSION_SELECTED': '월별로 적용한 BOM 버전',
    'ROUTING_VERSION_SELECTED': '월별로 적용한 라우팅 버전',
}


def _issue(i: Issue) -> dict:
    return {'code': i.code, 'message': MESSAGES.get(i.code, i.code), 'input_refs': [str(x) for x in i.input_refs]}


def _num(value) -> str:
    return decimal_str(value)


def _month_days(month: str) -> tuple[date, date]:
    y, m = map(int, month.split('-'))
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def _select_versions(rows: list, months: list[str], kind: str, product: str,
                     invalid: list[Issue], unsupported: list[Issue]) -> list:
    """rows = [(버전 키, valid_from, valid_to, payload)]. 달마다 그달 전체에 유효한 payload 하나(없으면 None)."""
    out = []
    for month in months:
        first, last = _month_days(month)
        full, partial = [], []
        for key, start, end, payload in rows:
            if start > last or (end is not None and end < first):
                continue
            (full if start <= first and (end is None or end >= last) else partial).append((key, payload))
        if partial:
            unsupported.append(Issue(f'{kind}_VERSION_MIDMONTH', (product, month)))
        if len(full) > 1:
            invalid.append(Issue(f'{kind}_VERSION_AMBIGUOUS', (product, month)))
        out.append(full[0] if len(full) == 1 and not partial else None)
    return out


def _same_each_month(per_month: list[dict]) -> bool:
    return all(x == per_month[0] for x in per_month)


class Converted:
    def __init__(self):
        self.data: dict = {}
        self.invalid: list[Issue] = []
        self.unsupported: list[Issue] = []
        self.unverified: list[Issue] = []  # 입력 수준(모든 안 공통) 확인 불가
        self.evidence: list[Issue] = [Issue('POLICY_APPLIED', (POLICY_REF,))]


def to_internal(request: PlanningInput) -> Converted:
    """PlanningInput → calculate_plans 입력. 변환 단계에서 찾은 문제는 invalid/unsupported로 모은다."""
    cv = Converted()
    cmd = request.command
    months = list(cmd.months)
    facts = request.approved_inputs
    invalid, unsupported = cv.invalid, cv.unsupported

    # 재고: 기준일 이하 가장 최근 1행
    stock: dict[tuple[str, str], list] = defaultdict(list)
    for row in facts.inventory:
        if row.as_of_date <= cmd.as_of_date:
            stock[(row.item_type, row.item_id)].append(row)

    def apply_stock(item: dict, kind: str, unit: str) -> None:
        rows = stock.get((kind, item['id']))
        if not rows:
            return
        latest = max(r.as_of_date for r in rows)
        same = [r for r in rows if r.as_of_date == latest]
        if len(same) > 1:
            invalid.append(Issue('INVENTORY_AMBIGUOUS', (item['id'], latest.isoformat())))
        row = same[0]
        if row.unit != unit:
            item['inventory_unit'] = row.unit
        item['on_hand'], item['allocated'] = row.on_hand_qty, row.allocated_qty
        if Fraction(row.allocated_qty) > Fraction(row.on_hand_qty):  # 가용재고 음수 → 계약 수량(비음수)으로 낼 수 없음
            invalid.append(Issue('INVALID_QUANTITY', (item['id'], 'allocated')))

    master = {p.product_id: p for p in facts.products}
    products = []
    for pid in cmd.product_ids:
        fact = master.get(pid)
        if fact is None:
            invalid.append(Issue('PRODUCT_MISSING', (pid,)))
            continue
        item = {'id': pid, 'unit': fact.base_unit, 'safety_stock': fact.safety_stock_qty}
        apply_stock(item, 'PRODUCT', fact.base_unit)
        products.append(item)
    materials = []
    for fact in facts.materials:
        item = {'id': fact.material_id, 'unit': fact.base_unit, 'safety_stock': fact.safety_stock_qty}
        apply_stock(item, 'MATERIAL', fact.base_unit)
        materials.append(item)

    # 예측: 제품×월. 빠진 달은 None → 코어가 FORECAST_MISSING
    by_key = {(r.product_id, r.target_month): r for r in request.forecast_rows}
    forecast: dict[str, dict[str, list]] = {'P50': {}, 'P80': {}}
    for p in products:
        rows = [by_key.get((p['id'], m)) for m in months]
        for r in rows:
            if r is not None and r.unit != p['unit']:
                invalid.append(Issue('UNIT_MISMATCH', (p['id'], r.target_month)))
        forecast['P50'][p['id']] = [None if r is None else r.p50 for r in rows]
        forecast['P80'][p['id']] = [None if r is None else r.p80 for r in rows]

    # 수량 한도
    limits: dict[str, list] = {}
    unit_of = {p['id']: p['unit'] for p in products}
    if request.capacity_snapshot is not None:
        for q in request.capacity_snapshot.quantity_limits:
            if q.product_id not in unit_of or q.period not in months:
                continue
            if q.accounting_point != 'FINISHED_OUTPUT':
                unsupported.append(Issue('QUANTITY_LIMIT_POINT_UNSUPPORTED', (q.product_id, q.capacity_id, q.period)))
                continue
            if q.unit != unit_of[q.product_id]:
                invalid.append(Issue('UNIT_MISMATCH', (q.product_id, q.capacity_id, q.period)))
                continue
            row = limits.setdefault(q.product_id, [None] * len(months))
            i = months.index(q.period)
            row[i] = q.limit_qty if row[i] is None else min(row[i], q.limit_qty, key=Fraction)

    # 라우팅: 제품별 버전 → 달마다 선택 → 자원별 1개당 시간
    versions: dict[str, dict[tuple[str, str], list]] = defaultdict(lambda: defaultdict(list))
    if request.routing_snapshot is not None:
        for s in request.routing_snapshot.routing_steps:
            if s.product_id in unit_of:
                versions[s.product_id][(s.routing_id, s.routing_version)].append(s)
    routing_by_month: list[dict] = [{} for _ in months]
    for pid, by_version in versions.items():
        rows = []
        for key, steps in by_version.items():
            windows = {(s.valid_from, s.valid_to) for s in steps}
            if len(windows) > 1:  # 한 버전 안에서 단계마다 유효기간이 다르면 어느 달에 무엇을 쓸지 정할 수 없다
                unsupported.append(Issue('ROUTING_STEP_VALIDITY_MIXED', (pid, key[0], key[1])))
                continue
            (start, end), = windows
            rows.append((key, start, end, steps))
        chosen = _select_versions(rows, months, 'ROUTING', pid, invalid, unsupported)
        for m, pick in enumerate(chosen):
            if pick is None:
                continue
            key, steps = pick
            hours: dict[str, Fraction] = {}
            flags: dict[str, dict] = {}
            for s in steps:
                for line in [s, *s.resource_requirements]:
                    if line.time_basis == 'ELAPSED':
                        unsupported.append(Issue('TIME_BASIS_UNSUPPORTED', (pid, s.step_id, line.resource_id)))
                        continue
                    h = Fraction(line.run_time) / Fraction(line.reference_qty) * _TIME_UNITS[line.time_unit]
                    hours[line.resource_id] = hours.get(line.resource_id, Fraction(0)) + h
                    f = flags.setdefault(line.resource_id, {})
                    if line.setup_time is not None and Fraction(line.setup_time) != 0:
                        f['setup_time'] = line.setup_time
                    if line.alternative_group_ref:
                        f['alternative_group'] = line.alternative_group_ref
            routing_by_month[m][pid] = {rid: {'run_time': str(h), 'reference_qty': '1', 'time_unit': 'h', **flags[rid]}
                                        for rid, h in hours.items()}
            if len({None if c is None else c[0] for c in chosen}) > 1:  # 기간 안에 버전이 바뀌면 근거로 남김
                cv.evidence.append(Issue('ROUTING_VERSION_SELECTED', (pid, months[m], key[0], key[1])))

    # 자원·시간 예산
    drafts = [d for d in (request.capacity_snapshot, request.routing_snapshot) if d is not None]
    resource_rows = {}
    for d in drafts:
        for r in d.resources:
            resource_rows.setdefault(r.resource_id, r)
    budgets: dict[tuple[str, str], list] = defaultdict(list)
    if request.capacity_snapshot is not None:
        for b in request.capacity_snapshot.hours_budgets:
            budgets[(b.resource_id, b.period)].append(b)
    resources = []
    used_resources = {rid for month in routing_by_month for steps in month.values() for rid in steps}
    for rid, r in resource_rows.items():
        if rid not in used_resources:  # 선택 제품 라우팅이 안 쓰는 자원은 계산·판정에서 뺀다
            continue
        item = {'id': rid, 'time_basis': r.time_basis, 'regular': [], 'overtime': []}
        for m in months:
            rows = budgets.get((rid, m), [])
            if len(rows) > 1:
                invalid.append(Issue('CAPACITY_AMBIGUOUS', (rid, m)))
            b = rows[0] if rows else None
            scale = _TIME_UNITS[b.unit] if b is not None else Fraction(1)
            item['regular'].append(None if b is None else str(Fraction(b.regular_hours) * scale))
            item['overtime'].append(None if b is None or b.overtime_hours_limit is None
                                    else str(Fraction(b.overtime_hours_limit) * scale))
            if b is not None and b.availability_basis == 'GROSS':
                item['availability_basis'] = 'GROSS'
        resources.append(item)

    # BOM: 제품별 버전 → 달마다 선택
    bom_versions: dict[str, list] = defaultdict(list)
    material_unit = {m['id']: m['unit'] for m in materials}
    for b in facts.boms:
        h = b.header
        if h.product_id in unit_of and h.status == 'APPROVED' and h.is_active:
            bom_versions[h.product_id].append(((h.bom_id, h.bom_version), h.valid_from, h.valid_to, b))
    bom_by_month: list[dict] = [{} for _ in months]
    for pid, rows in bom_versions.items():
        chosen = _select_versions(rows, months, 'BOM', pid, invalid, unsupported)
        for m, pick in enumerate(chosen):
            if pick is None:
                continue
            key, b = pick
            lines = []
            for line in b.lines:
                if line.component_type == 'MATERIAL' and line.component_id in material_unit \
                        and line.unit != material_unit[line.component_id]:
                    invalid.append(Issue('UNIT_MISMATCH', (b.header.bom_id, str(line.line_no))))
                lines.append({'material': line.component_id, 'qty': line.qty_per, 'base_qty': b.header.base_qty,
                              'scrap_rate': line.scrap_rate,
                              **({'component_type': 'PRODUCT'} if line.component_type == 'PRODUCT' else {})})
            bom_by_month[m][pid] = lines
            if len({None if c is None else c[0] for c in chosen}) > 1:  # 기간 안에 버전이 바뀌면 근거로 남김
                cv.evidence.append(Issue('BOM_VERSION_SELECTED', (pid, months[m], key[0], key[1])))

    # ID 길이: constraint_id = 접두어(4) + ID + -YYYY-MM(8)이 계약 Code 최대 40자를 넘으면 낼 수 없다
    bom_materials = {line['material'] for month in bom_by_month for lines in month.values() for line in lines}
    for ident in [*unit_of, *(r['id'] for r in resources), *sorted(bom_materials)]:
        if len(ident) > _MAX_ID:
            invalid.append(Issue('ID_TOO_LONG', (ident,)))

    # 입고 예정
    if request.scheduled_receipts is None:
        receipts = []
        cv.unverified.append(Issue('RECEIPT_SOURCE_UNAVAILABLE', ()))
    else:
        receipts = [{'po_id': r.po_id, 'material': r.material_id, 'open_qty': r.open_qty, 'unit': r.unit,
                     'expected_date': r.expected_date.isoformat()} for r in request.scheduled_receipts]
    for code in request.missing_inputs:
        issue = Issue(code, ())
        if issue not in cv.unverified:
            cv.unverified.append(issue)

    cv.data = {
        'months': months, 'as_of': cmd.as_of_date.isoformat(), 'demand_multiplier': '1',
        'products': products, 'forecast': forecast, 'resources': resources, 'quantity_limits': limits,
        'materials': materials, 'receipts': receipts,
    }
    if _same_each_month(routing_by_month):
        cv.data['routing'] = routing_by_month[0]
    else:
        cv.data['routing_by_month'] = routing_by_month
    if _same_each_month(bom_by_month):
        cv.data['bom'] = bom_by_month[0]
    else:
        cv.data['bom_by_month'] = bom_by_month
    return cv


def _evaluation(plan_id: str, e: Evaluation) -> dict:
    used = e.used_value
    if e.dimension == 'SAFETY_STOCK' and used is not None and used < 0:
        used = Fraction(0)  # 계약 수량은 비음수(C05). 결품은 DEM 판정과 STOCKOUT 사유로 드러난다
    return {
        'constraint_id': e.constraint_id, 'plan_id': plan_id, 'dimension': e.dimension, 'period': e.period,
        'resource_id': e.resource_id, 'product_id': e.product_id, 'status': e.status,
        'limit_value': None if e.limit_value is None else _num(e.limit_value),
        'used_value': None if used is None else _num(used),
        'unit': 'h' if e.dimension in _HOUR_DIMENSIONS else e.unit,
        'time_basis': e.time_basis, 'strength': e.strength, 'application_state': e.application_state,
        'input_refs': [str(x) for x in e.input_refs], 'reason_codes': list(e.reason_codes),
    }


def _failure(status: str, errors: list[Issue], warnings: list[Issue] = ()) -> PlanningOutput:
    return PlanningOutput(status=status, plans=[], constraint_evaluations=[], material_requirements=[],
                          evidence=[], warnings=[_issue(i) for i in warnings], unverified=[],
                          errors=[_issue(i) for i in dict.fromkeys(errors)], module_version=MODULE_VERSION)


def to_output(request: PlanningInput, cv: Converted, results: dict[str, PlanResult]) -> PlanningOutput:
    cmd = request.command
    statuses = {r.status for r in results.values()}
    if statuses != {'OK'}:
        errors = [i for r in results.values() for i in r.errors]
        return _failure('INPUT_INVALID' if 'INPUT_INVALID' in statuses else 'UNSUPPORTED', errors)
    unit_of = {p['id']: p['unit'] for p in cv.data['products']}
    plans, evaluations, materials, warnings = [], [], [], []
    for plan_id, _, _ in PLAN_SPECS:
        r = results[plan_id]
        feasibility = r.feasibility
        if feasibility == 'FEASIBLE' and cv.unverified:
            feasibility = 'UNVERIFIED'
        plans.append({
            'plan_id': plan_id, 'plan_type': plan_id, 'label': LABELS[plan_id], 'feasibility': feasibility,
            'production': [{'product_id': p, 'period': month, 'production_qty': str(r.production[p][m]),
                            'unit': unit_of[p]} for p in cmd.product_ids for m, month in enumerate(r.months)],
            'policy_ref': r.policy_ref, 'unverified': [_issue(i) for i in r.unverified],
        })
        evaluations += [_evaluation(plan_id, e) for e in r.evaluations]
        for kid, mr in r.materials.items():
            for m, month in enumerate(r.months):
                materials.append({'plan_id': plan_id, 'material_id': kid, 'period': month,
                                  'required_qty': _num(mr.required[m]), 'available_qty': _num(mr.available[m]),
                                  'shortage_qty': _num(mr.shortage[m]), 'unit': mr.unit, 'input_refs': []})
        warnings += [i for i in r.warnings if i not in warnings]
    return PlanningOutput(status='OK', plans=plans, constraint_evaluations=evaluations,
                          material_requirements=materials, evidence=[_issue(i) for i in cv.evidence],
                          warnings=[_issue(i) for i in warnings], unverified=[_issue(i) for i in cv.unverified],
                          errors=[], module_version=MODULE_VERSION)


def run(request: PlanningInput) -> PlanningOutput:
    """계약 입력 하나로 세 계획안을 계산한다. WHAT_IF면 변경 조건을 적용한 세 안이다."""
    cv = to_internal(request)
    if cv.invalid:
        return _failure('INPUT_INVALID', cv.invalid + cv.unsupported)
    if cv.unsupported:
        return _failure('UNSUPPORTED', cv.unsupported)
    data = cv.data
    if request.command.scenario == 'WHAT_IF':
        data, errors = apply_overrides(data, dict(request.command.overrides))
        if errors:
            return _failure('INPUT_INVALID', errors)
    return to_output(request, cv, calculate_plans(data))
