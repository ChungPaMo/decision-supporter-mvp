"""Reference checks and coverage of a single-month planning snapshot."""
from calendar import monthrange
from collections import Counter
from datetime import date

from app.errors import ApiError, ErrorCode
from contracts.interfaces.planning import PlanCommand, PlanningInput


def input_conflict(reason: str) -> ApiError:
    return ApiError(409, ErrorCode.PLAN_INPUT_UNAVAILABLE,
                    '계획 입력 범위 또는 승인 자료의 일관성을 확인하세요.', {'reason': reason})


def month_bounds(target_month: str) -> tuple[date, date]:
    year, month = map(int, target_month.split('-'))
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


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
    forecast_products = {row.product_id for row in snapshot.forecast_rows}
    if (forecast_products != requested or len(snapshot.forecast_rows) != len(requested)
            or any(row.target_month != command.target_month for row in snapshot.forecast_rows)):
        raise input_conflict('FORECAST_PRODUCT_MONTH_COVERAGE')
    if any(row.unit != products[row.product_id] for row in snapshot.forecast_rows):
        raise input_conflict('FORECAST_UNIT_MISMATCH')

    sources = {row.batch_id: row.entity for row in facts.sources}
    groups = {'product': facts.products, 'material': facts.materials, 'bom': facts.boms, 'inventory': facts.inventory}
    if len(sources) != len(facts.sources) or any(
            sources.get(row.batch_id) != entity for entity, rows in groups.items() for row in rows):
        raise input_conflict('APPROVED_SOURCE_MISMATCH')

    units = {'PRODUCT': products, 'MATERIAL': materials}
    first, last = month_bounds(command.target_month)
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

    # CapacityRegistrationDraft checks resource/time basis, concurrent requirements and the route graph.
    for draft in (snapshot.capacity_snapshot, snapshot.routing_snapshot):
        if draft is None:
            continue
        if not any(entity in ('capacity', 'routing') for entity in sources.values()):
            raise input_conflict('APPROVED_SOURCE_MISMATCH')
        if any(row.period != command.target_month for row in [*draft.hours_budgets, *draft.quantity_limits]):
            raise input_conflict('CAPACITY_PERIOD_MISMATCH')
        if any(row.product_id not in requested or products.get(row.product_id) != row.unit
               for row in draft.quantity_limits):
            raise input_conflict('CAPACITY_PRODUCT_OR_UNIT_MISMATCH')
        if any(row.product_id not in requested or products.get(row.product_id) != row.quantity_unit
               or row.valid_from > last or (row.valid_to and row.valid_to < first) for row in draft.routing_steps):
            raise input_conflict('ROUTING_PRODUCT_UNIT_OR_PERIOD_MISMATCH')


def input_coverage(snapshot: PlanningInput):
    """Summarize facts without selecting BOM versions, inventory dates or capacity policies."""
    facts = snapshot.approved_inputs
    requested = set(snapshot.command.product_ids)
    selected_boms = [bom for bom in facts.boms if bom.header.product_id in requested]
    bom_counts = Counter(bom.header.product_id for bom in selected_boms)
    stock_counts = Counter((row.item_type, row.item_id) for row in facts.inventory)
    direct_components = {(line.component_type, line.component_id) for bom in selected_boms for line in bom.lines}
    stock_needed = {('PRODUCT', product) for product in requested} | direct_components
    capacity, routing = snapshot.capacity_snapshot, snapshot.routing_snapshot
    drafts = [d for d in (capacity, routing) if d is not None]
    resources = {row.resource_id for draft in drafts for row in draft.resources}
    routes = routing.routing_steps if routing else []
    budgets = capacity.hours_budgets if capacity else []
    missing = set(snapshot.missing_inputs)
    warnings = {'POLICY_NOT_CONFIRMED'}
    warnings.update(code for code in missing if code.endswith('POLICY_REQUIRED') or code == 'POLICY_NOT_CONFIRMED')
    missing -= warnings
    if requested - bom_counts.keys():
        missing.add('BOM_COVERAGE')
    if stock_needed - stock_counts.keys():
        missing.add('INVENTORY_COVERAGE')
    if not budgets or resources - {row.resource_id for row in budgets}:
        missing.add('HOURS_COVERAGE')
    if not resources:
        missing.add('CAPACITY_NOT_REGISTERED')
    if requested - {row.product_id for row in routes}:
        missing.add('ROUTING_COVERAGE')
    first, last = month_bounds(snapshot.command.target_month)
    if (any(count > 1 for count in bom_counts.values())
            or any(row.header.valid_from > first or (row.header.valid_to and row.header.valid_to < last)
                   for row in selected_boms)):
        warnings.add('BOM_VERSION_POLICY_REQUIRED')
    if any(stock_counts[key] > 1 for key in stock_needed):
        warnings.add('INVENTORY_SNAPSHOT_POLICY_REQUIRED')
    route_versions = {(row.product_id, row.routing_id, row.routing_version) for row in routes}
    if (len(route_versions) > len({row.product_id for row in routes})
            or any(row.valid_from > first or (row.valid_to and row.valid_to < last) for row in routes)):
        warnings.add('ROUTING_VERSION_POLICY_REQUIRED')

    # Counts describe facts handed to the engine, including unselected approved master rows.
    inputs = {
        'forecast': (len(snapshot.forecast_rows), True),
        'products': (len(facts.products), True),
        'materials': (len(facts.materials), 'BOM_COVERAGE' not in missing),
        'bom': (len(facts.boms), 'BOM_COVERAGE' not in missing and 'BOM_VERSION_POLICY_REQUIRED' not in warnings),
        'inventory': (len(facts.inventory), 'INVENTORY_COVERAGE' not in missing and 'INVENTORY_SNAPSHOT_POLICY_REQUIRED' not in warnings),
        'resources': (len(resources), bool(resources)),
        'quantity_limits': (len(capacity.quantity_limits) if capacity else 0, True),
        'hours_budgets': (len(budgets), 'HOURS_COVERAGE' not in missing),
        'routing': (len(routes), 'ROUTING_COVERAGE' not in missing and 'ROUTING_VERSION_POLICY_REQUIRED' not in warnings),
    }
    return inputs, sorted(missing), sorted(warnings)
