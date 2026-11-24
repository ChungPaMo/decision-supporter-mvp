"""Reference checks and coverage of an approved planning snapshot."""
from calendar import monthrange
from collections import defaultdict
from datetime import date

from app.errors import ApiError, ErrorCode
from contracts.interfaces.planning import PlanCommand, PlanningInput, PlanningOutput


def input_conflict(reason: str) -> ApiError:
    return ApiError(409, ErrorCode.PLAN_INPUT_UNAVAILABLE,
                    '계획 입력 범위 또는 승인 자료의 일관성을 확인하세요.', {'reason': reason})


def month_bounds(target_month: str) -> tuple[date, date]:
    year, month = map(int, target_month.split('-'))
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def horizon_bounds(command: PlanCommand) -> tuple[date, date]:
    return month_bounds(command.target_month)[0], month_bounds(command.months[-1])[1]


def forecast_scope(command: PlanCommand) -> set[tuple[str, str]]:
    return {(product, month) for product in command.product_ids for month in command.months}


def overlaps(start, end, first, last):
    return start <= last and (end is None or end >= first)


def routing_versions(steps):
    versions = defaultdict(list)
    for step in steps:
        versions[step.product_id, step.routing_id, step.routing_version].append(step)
    return versions


def validate_input(command: PlanCommand, snapshot: PlanningInput) -> None:
    if snapshot.dataset_id != command.dataset_id:
        raise ApiError(409, ErrorCode.DATASET_MISMATCH, '계획 입력 스냅샷의 데이터셋이 일치하지 않습니다.')
    if snapshot.command != command:
        raise ApiError(500, ErrorCode.MODULE_ERROR, '계획 입력 명령이 스냅샷과 일치하지 않습니다.')

    facts = snapshot.approved_inputs
    products = {row.product_id: row.base_unit for row in facts.products}
    materials = {row.material_id: row.base_unit for row in facts.materials}
    requested = set(command.product_ids)
    if not requested <= products.keys():
        raise input_conflict('PRODUCT_COVERAGE')
    forecast_keys = {(row.product_id, row.target_month) for row in snapshot.forecast_rows}
    if forecast_keys != forecast_scope(command) or len(forecast_keys) != len(snapshot.forecast_rows):
        raise input_conflict('FORECAST_PRODUCT_MONTH_COVERAGE')
    if any(row.unit != products[row.product_id] for row in snapshot.forecast_rows):
        raise input_conflict('FORECAST_UNIT_MISMATCH')

    approved = {row.batch_id: row for row in facts.sources}
    sources = {key: row.entity for key, row in approved.items()}
    groups = {'product': facts.products, 'material': facts.materials, 'bom': facts.boms, 'inventory': facts.inventory}
    if len(sources) != len(facts.sources) or any(
            sources.get(row.batch_id) != entity for entity, rows in groups.items() for row in rows):
        raise input_conflict('APPROVED_SOURCE_MISMATCH')

    units = {'PRODUCT': products, 'MATERIAL': materials}
    first, last = horizon_bounds(command)
    for bom in facts.boms:
        header = bom.header
        if (header.product_id not in products or not header.is_active or header.valid_from > last
                or (header.valid_to and header.valid_to < max(first, header.valid_from))):
            raise input_conflict('BOM_PRODUCT_OR_PERIOD_MISMATCH')
        if (not bom.lines or len({line.line_no for line in bom.lines}) != len(bom.lines)
                or any(line.bom_id != header.bom_id
                       or units[line.component_type].get(line.component_id) != line.unit for line in bom.lines)):
            raise input_conflict('BOM_COMPONENT_OR_UNIT_MISMATCH')
    if any(row.as_of_date > command.as_of_date or units[row.item_type].get(row.item_id) != row.unit
           for row in facts.inventory):
        raise input_conflict('INVENTORY_REFERENCE_UNIT_OR_DATE_MISMATCH')

    problem = receipt_snapshot_problem(snapshot, approved, materials)
    if problem:
        raise input_conflict(problem)

    # CapacityRegistrationDraft checks resource/time basis, concurrent requirements and the route graph.
    for draft in (snapshot.capacity_snapshot, snapshot.routing_snapshot):
        if draft is None:
            continue
        if not any(entity in ('capacity', 'routing') for entity in sources.values()):
            raise input_conflict('APPROVED_SOURCE_MISMATCH')
        if any(row.period not in command.months for row in [*draft.hours_budgets, *draft.quantity_limits]):
            raise input_conflict('CAPACITY_PERIOD_MISMATCH')
        if any(row.product_id not in requested or products.get(row.product_id) != row.unit
               for row in draft.quantity_limits):
            raise input_conflict('CAPACITY_PRODUCT_OR_UNIT_MISMATCH')
        if (any(row.product_id not in requested or products.get(row.product_id) != row.quantity_unit
                for row in draft.routing_steps)
                or any(not any(overlaps(row.valid_from, row.valid_to, first, last) for row in steps)
                       for steps in routing_versions(draft.routing_steps).values())):
            raise input_conflict('ROUTING_PRODUCT_UNIT_OR_PERIOD_MISMATCH')


def receipt_snapshot_problem(snapshot, approved, materials) -> str | None:
    receipts = snapshot.scheduled_receipts or []
    if len({row.po_id for row in receipts}) != len(receipts):
        return 'RECEIPT_DUPLICATE_PO'
    for row in receipts:
        source = approved.get(row.batch_id)
        if source is None or source.entity != 'scheduled_receipt' or not source.result_digest:
            return 'RECEIPT_SOURCE_MISMATCH'
        if materials.get(row.material_id) != row.unit or row.period(snapshot.command) is None:
            return 'RECEIPT_REFERENCE_UNIT_OR_PERIOD_MISMATCH'
    return None


_LEGACY_ADVISORIES = {
    'POLICY_NOT_CONFIRMED', 'BOM_VERSION_POLICY_REQUIRED', 'ROUTING_VERSION_POLICY_REQUIRED',
    'INVENTORY_SNAPSHOT_POLICY_REQUIRED',
}


def month_version(versions, first, last, kind, warnings):
    """Mirror the engine's whole-month rule for diagnostics and coverage only."""
    active = [(start, end, value) for start, end, value in versions if overlaps(start, end, first, last)]
    full = [value for start, end, value in active if start <= first and (end is None or end >= last)]
    if len(full) < len(active):
        warnings.add(f'{kind}_VERSION_MIDMONTH')
    if len(full) > 1:
        warnings.add(f'{kind}_VERSION_AMBIGUOUS')
    return (full[0] if len(full) == len(active) == 1 else None), bool(active)


def input_coverage(snapshot: PlanningInput):
    """Summarize the same approved scope that the engine calculates."""
    facts = snapshot.approved_inputs
    requested = set(snapshot.command.product_ids)
    months = snapshot.command.months
    capacity, routing = snapshot.capacity_snapshot, snapshot.routing_snapshot
    resources = {row.resource_id for draft in (capacity, routing) if draft for row in draft.resources}
    routes = routing.routing_steps if routing else []
    budgets = capacity.hours_budgets if capacity else []
    missing = set(snapshot.missing_inputs) - _LEGACY_ADVISORIES
    warnings = set()
    boms_by_product = defaultdict(list)
    routes_by_product = defaultdict(list)
    mixed_products = set()
    for bom in facts.boms:
        header = bom.header
        if header.status == 'APPROVED' and header.is_active:
            boms_by_product[header.product_id].append((header.valid_from, header.valid_to, bom.lines))
    for (product, _, _), steps in routing_versions(routes).items():
        windows = {(step.valid_from, step.valid_to) for step in steps}
        if len(windows) != 1:
            mixed_products.add(product)
            warnings.add('ROUTING_STEP_VALIDITY_MIXED')
        else:
            (start, end), = windows
            routes_by_product[product].append((start, end, steps))

    direct_components = set()
    used_resources = set()
    for month in months:
        first, last = month_bounds(month)
        for product in requested:
            lines, has_bom = month_version(boms_by_product[product], first, last, 'BOM', warnings)
            steps, has_route = month_version(routes_by_product[product], first, last, 'ROUTING', warnings)
            if not has_bom:
                missing.add('BOM_COVERAGE')
            if not has_route and product not in mixed_products:
                missing.add('ROUTING_COVERAGE')
            direct_components.update((line.component_type, line.component_id) for line in lines or [])
            used_resources.update(req.resource_id for step in steps or [] for req in (step, *step.resource_requirements))

    stock_needed = {('PRODUCT', product) for product in requested} | direct_components
    stock_dates = defaultdict(list)
    for row in facts.inventory:
        stock_dates[row.item_type, row.item_id].append(row.as_of_date)
    if stock_needed - stock_dates.keys():
        missing.add('INVENTORY_COVERAGE')
    if any(dates.count(max(dates)) > 1 for key, dates in stock_dates.items() if key in stock_needed):
        warnings.add('INVENTORY_AMBIGUOUS')

    budget_keys = {(row.resource_id, row.period) for row in budgets}
    if ({(resource, month) for resource in used_resources for month in months} - budget_keys
            or not (budgets or routes)):
        missing.add('HOURS_COVERAGE')
    if not resources:
        missing.add('CAPACITY_NOT_REGISTERED')
    if routing is None:
        missing.add('ROUTING_NOT_REGISTERED')
    if snapshot.scheduled_receipts is None:
        missing.add('RECEIPT_SOURCE_UNAVAILABLE')
    elif any(row.expected_date <= snapshot.command.as_of_date
             and ('MATERIAL', row.material_id) in direct_components for row in snapshot.scheduled_receipts):
        warnings.add('RECEIPT_OVERDUE')

    # Counts describe facts handed to the engine, including unselected approved master rows.
    inputs = {
        'forecast': (len(snapshot.forecast_rows), True),
        'products': (len(facts.products), True),
        'materials': (len(facts.materials), 'BOM_COVERAGE' not in missing),
        'bom': (len(facts.boms), 'BOM_COVERAGE' not in missing and not any(code.startswith('BOM_') for code in warnings)),
        'inventory': (len(facts.inventory), 'INVENTORY_COVERAGE' not in missing and 'INVENTORY_AMBIGUOUS' not in warnings),
        'resources': (len(resources), bool(resources)),
        'quantity_limits': (len(capacity.quantity_limits) if capacity else 0, True),
        'hours_budgets': (len(budgets), 'HOURS_COVERAGE' not in missing),
        'routing': (len(routes), 'ROUTING_COVERAGE' not in missing and not any(code.startswith('ROUTING_') for code in warnings)),
        'scheduled_receipts': (len(snapshot.scheduled_receipts or []), snapshot.scheduled_receipts is not None),
    }
    return inputs, sorted(missing), sorted(warnings - missing)


def with_input_coverage(snapshot: PlanningInput) -> PlanningInput:
    _, missing, _ = input_coverage(snapshot)
    return snapshot.model_copy(update={'missing_inputs': missing})


def validate_overrides(command: PlanCommand, parent: PlanningInput | None = None) -> None:
    resources = set()
    receipts = set()
    if parent is not None:
        resources = {row.resource_id for draft in (parent.capacity_snapshot, parent.routing_snapshot)
                     if draft for row in draft.resources}
        receipts = {row.po_id for row in parent.scheduled_receipts or []}

    for key in command.overrides:
        parts = key.split('.')
        kind, *args = parts
        if key == 'demand_multiplier':
            continue
        if kind == 'demand_multiplier' and len(args) == 1 and args[0] in command.product_ids:
            continue
        if (kind == 'overtime_hours_limit' and len(args) == 2 and args[0] and args[1] in command.months
                and (parent is None or args[0] in resources)):
            continue
        if kind == 'receipt_qty' and len(args) == 1 and args[0] and (parent is None or args[0] in receipts):
            continue
        raise ApiError(422, ErrorCode.PLAN_OVERRIDE_UNSUPPORTED, 'Invalid or unsupported What-if override.',
                       {'status': 'INPUT_INVALID', 'reason': 'WHATIF_INVALID'})


def validate_pair(snapshot: PlanningInput, result: PlanningOutput, *, check_current_coverage: bool = True) -> None:
    """Apply the same output scope and invariants to preview, storage and replay."""
    result.references_and_cardinality()
    command = snapshot.command
    if snapshot.dataset_id != command.dataset_id:
        raise ValueError('Input and command dataset mismatch')
    units = {(row.product_id, row.target_month): row.unit for row in snapshot.forecast_rows}
    if units.keys() != forecast_scope(command) or len(units) != len(snapshot.forecast_rows):
        raise ValueError('Missing or duplicate forecast input scope')
    approved = {row.batch_id: row for row in snapshot.approved_inputs.sources}
    if len(approved) != len(snapshot.approved_inputs.sources):
        raise ValueError('Duplicate input source')

    for plan in result.plans:
        keys = {(row.product_id, row.period) for row in plan.production}
        if len(keys) != len(plan.production) or any(
                units.get((row.product_id, row.period)) != row.unit for row in plan.production):
            raise ValueError('Output scope or unit mismatch')
        if result.status == 'OK' and keys != units.keys():
            raise ValueError('Incomplete OK candidate')

    missing = snapshot.missing_inputs
    if check_current_coverage and result.plans:
        _, missing, warnings = input_coverage(snapshot)
        if any('_VERSION_' in code or code in {'ROUTING_STEP_VALIDITY_MIXED', 'INVENTORY_AMBIGUOUS'} for code in warnings):
            raise ValueError('Conflicting approved versions or inventory cannot produce candidates')
    if missing and any(plan.feasibility == 'FEASIBLE' for plan in result.plans):
        raise ValueError('Missing approved input cannot be reported as verified')

    resources = {row.resource_id for draft in (snapshot.capacity_snapshot, snapshot.routing_snapshot)
                 if draft for row in draft.resources}
    if any(row.period not in command.months or (row.product_id and row.product_id not in command.product_ids)
           or (row.resource_id and row.resource_id not in resources) for row in result.constraint_evaluations):
        raise ValueError('Constraint reference outside input')
    materials = {row.material_id: row.base_unit for row in snapshot.approved_inputs.materials}
    problem = receipt_snapshot_problem(snapshot, approved, materials)
    if problem:
        raise ValueError(problem)
    material_keys = {(row.plan_id, row.material_id, row.period) for row in result.material_requirements}
    if len(material_keys) != len(result.material_requirements) or any(
            materials.get(row.material_id) != row.unit or row.period not in command.months
            for row in result.material_requirements):
        raise ValueError('Material reference or unit mismatch')
