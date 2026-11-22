"""Capacity registration: exact-header templates, approved references, no calculations."""
import json
from decimal import Decimal
from pydantic import ValidationError
from sqlalchemy import text
from contracts.interfaces.capacity import Resource, QuantityLimit, HoursBudget, RoutingStep, CapacityRegistrationDraft

MODELS = {'resources': Resource, 'quantity_limits': QuantityLimit, 'hours_budgets': HoursBudget, 'routing_steps': RoutingStep}
TABLES = {'resources': 'production_resource', 'quantity_limits': 'production_quantity_limit',
          'hours_budgets': 'production_hours_budget', 'routing_steps': 'production_routing_step'}


def approved_rows(c, section):
    table = TABLES[section]
    return c.execute(text(f"SELECT t.payload,t.batch_id FROM {table} t JOIN import_batch b USING(batch_id) "
                          "WHERE b.status='APPROVED' AND b.blocking_error_count=0 ORDER BY t.batch_id,t.payload::text")).mappings().all()


def validate_rows(tx, entity, rows):
    """Full-batch checks, repeated under the approval transaction lock."""
    resources = [r['payload'] for r in approved_rows(tx.c, 'resources')]
    products = {p.product_id: p for p in tx.list_known_products()}
    incoming = {s: [p for section, p in rows if section == s] for s in MODELS}
    draft = CapacityRegistrationDraft(**{**incoming, 'resources': resources + incoming['resources']})
    draft.check_approved_products(set(products))
    for row in [*draft.quantity_limits, *draft.routing_steps]:
        unit = row.unit if isinstance(row, QuantityLimit) else row.quantity_unit
        if unit != products[row.product_id].base_unit: raise ValueError('Product base unit mismatch')
    if entity == 'capacity' and incoming['routing_steps']: raise ValueError('Routing requires routing batch')
    if entity == 'routing' and any(incoming[s] for s in ('resources','quantity_limits','hours_budgets')):
        raise ValueError('Routing batch must contain only routing steps')
    for section in ('quantity_limits', 'hours_budgets'):
        previous = [r['payload'] for r in approved_rows(tx.c, section)]
        keys = set()
        for r in previous + incoming[section]:
            key = ((r['product_id'],r['period'],r['accounting_point'],r.get('operation_id')) if section == 'quantity_limits'
                   else (r['resource_id'],r['period']))
            if key in keys: raise ValueError('Duplicate monthly capacity scope')
            keys.add(key)
    # Conservative registration policy: no overlapping versions per product/routing.
    groups = {}
    for r in incoming['routing_steps']:
        key = (r['routing_id'],r['routing_version'])
        interval = (r['product_id'],r['valid_from'],r.get('valid_to'))
        if key in groups and groups[key] != interval: raise ValueError('Inconsistent routing version validity')
        groups[key] = interval
    old = [r['payload'] for r in approved_rows(tx.c,'routing_steps')]
    intervals = [(r['routing_id'],r['routing_version'],r['product_id'],r['valid_from'],r.get('valid_to')) for r in old]
    intervals = list(dict.fromkeys(intervals)) + [(k[0],k[1],*v) for k,v in groups.items()]
    for i,a in enumerate(intervals):
        for b in intervals[i+1:]:
            if a[:2] == b[:2] or (a[2] == b[2] and a[3] <= (b[4] or '9999-12-31') and b[3] <= (a[4] or '9999-12-31')):
                raise ValueError('Overlapping routing validity or duplicate version')
    for q in draft.quantity_limits:
        if q.accounting_point == 'OPERATION_OUTPUT':
            raise ValueError('Operation-output capacity requires an approved operation scope policy; unsupported')
    for h in draft.hours_budgets:
        if h.calendar_ref: raise ValueError('Calendar master registration is not implemented')
    for step in draft.routing_steps:
        for r in [step,*step.resource_requirements]:
            if r.setup_policy_ref or r.alternative_group_ref:
                raise ValueError('Setup/alternative policy is not confirmed')
    return draft


def preview(tx, filename, data, entity, overrides, sheet_filter):
    from app.ingest.parsing import parse_file
    from app.ingest.pipeline import PreviewOut, FileOut, SheetOut, CapacityRecordOut, LocationOut, IssueOut, MappingHoldOut, FieldMappingOut
    parsed = parse_file(filename,data)
    sheets, all_rows = [], []
    for sheet in parsed.sheets:
        headers = [h.name for h in sheet.header]
        candidates = [s for s,m in MODELS.items() if set(k for k,f in m.model_fields.items() if f.is_required()) <= set(headers)]
        section = sheet.name if sheet.name in MODELS else (candidates[0] if len(candidates)==1 else None)
        fields = MODELS[section].model_fields if section else {}
        mapped = dict(overrides or {})
        translated = [next((k for k,v in mapped.items() if v==h),h) for h in headers]
        if not section:
            candidates = [s for s,m in MODELS.items() if set(k for k,f in m.model_fields.items() if f.is_required()) <= set(translated)]
            section = candidates[0] if len(candidates)==1 else None
            fields = MODELS[section].model_fields if section else {}
        hold = not section or len(set(translated)) != len(translated) or not set(k for k,f in fields.items() if f.is_required()) <= set(translated)
        issues, records = [], []
        if sheet_filter and sheet_filter != sheet.name:
            raise ValueError('Partial-sheet registration is not supported; upload an explicit atomic workbook')
        if not hold:
            for row in sheet.rows:
                try:
                    if len(row.cells)>len(headers): raise ValueError('Row exceeds header width')
                    values = {k:cell.value for k,cell in zip(translated,row.cells) if cell.value not in (None,'')}
                    if set(values)-set(fields): raise ValueError('Unknown columns')
                    for k in ('predecessor_step_ids','resource_requirements'):
                        if k in values: values[k] = json.loads(values[k])
                    obj = MODELS[section].model_validate(values)
                    payload = obj.model_dump(mode='json')
                    all_rows.append((section,payload))
                    records.append(CapacityRecordOut(section=section,payload=payload,location=LocationOut(sheet=sheet.name,row=row.row)))
                except (ValueError,ValidationError):
                    issues.append(IssueOut(severity='ERROR',code='CAPACITY_ROW_INVALID',message='Invalid required field, unit, time basis or policy reference.',location=LocationOut(sheet=sheet.name,row=row.row)))
        sheets.append(SheetOut(name=sheet.name,status='HOLD' if hold else 'MAPPED',header_rows=sheet.header_rows,data_rows=len(sheet.rows),
                     mapping=[FieldMappingOut(field=k,col=i+1,header=str(headers[i]),method='USER_OVERRIDE' if k in mapped else 'ALIAS_STRONG',review_required=False) for i,k in enumerate(translated) if k in fields],
                     unmapped_headers=[str(h) for h in translated if h not in fields],holds=[MappingHoldOut(code='CAPACITY_MAPPING_HOLD',message='Use exact template headers or explicit column overrides.')] if hold else [],
                     validated=not hold,error_rows=len(issues),valid_records=len(records),issues=issues,records=records))
    if all_rows and not any(s.issues or s.holds for s in sheets):
        try: validate_rows(tx,entity,all_rows)
        except ValueError:
            sheets[0].issues.append(IssueOut(severity='ERROR',code='CAPACITY_REFERENCE_INVALID',message='Duplicate, unapproved reference, invalid unit, cycle, validity overlap or unsupported policy.'))
    errors = sum(len(s.issues) for s in sheets)
    status = 'MAPPING_HOLD' if any(s.holds for s in sheets) else 'HAS_ERRORS' if errors else 'READY_FOR_APPROVAL' if all_rows else 'MAPPING_HOLD'
    if errors and status != 'MAPPING_HOLD': status='HAS_ERRORS'
    return PreviewOut(entity=entity,file=FileOut(name=parsed.filename,format=parsed.format,size_bytes=parsed.size_bytes,sha256=parsed.sha256,meta=parsed.meta),status=status,
                      master_data_checked=True,blocking_error_count=errors,warning_count=0,sheets=sheets)


def commit(tx,batch_id,actor,records):
    # Serialize resource/scope validation across competing capacity and routing approvals.
    tx.c.execute(text("SELECT pg_advisory_xact_lock(762501)"))
    rows = [(r.section,r.payload) for r in records]
    entity = tx.get_batch(batch_id).entity
    try:
        validate_rows(tx,entity,rows)
    except ValueError:
        from app.errors import ApiError, ErrorCode
        raise ApiError(409,ErrorCode.RESULT_CHANGED,'Capacity references changed; revalidate the batch.') from None
    tx.mark_approved(batch_id,actor,len(records))
    for section,p in rows:
        keys = {
            'resources': ['resource_id','resource_name','kind','time_basis','parallel_units'],
            'quantity_limits': ['capacity_id','product_id','period','limit_qty','unit','accounting_point','operation_id'],
            'hours_budgets': ['capacity_id','resource_id','period','regular_hours','overtime_hours_limit','unit','time_basis','availability_basis','calendar_ref'],
            'routing_steps': ['routing_id','routing_version','step_id','product_id','operation_id','valid_from','valid_to'],
        }[section]
        if section=='routing_steps':
            tx.c.execute(text("INSERT INTO production_routing(routing_id,routing_version,product_id,valid_from,valid_to,batch_id) VALUES(:routing_id,:routing_version,:product_id,:valid_from,:valid_to,:batch_id) ON CONFLICT(routing_id,routing_version) DO NOTHING"),{**p,'batch_id':batch_id})
        columns = ','.join(keys)+',batch_id,payload'
        vals = ','.join(':'+k for k in keys)+',:batch_id,CAST(:payload AS jsonb)'
        tx.c.execute(text(f'INSERT INTO {TABLES[section]}({columns}) VALUES({vals})'),{**p,'batch_id':batch_id,'payload':json.dumps(p)})
        if section=='routing_steps':
            primary = {k:p.get(k) for k in ('resource_id','reference_qty','quantity_unit','run_time','time_unit','time_basis','concurrent_units','setup_time','setup_policy_ref','alternative_group_ref')}
            for i,r in enumerate([primary,*p.get('resource_requirements',[])]):
                tx.c.execute(text("""INSERT INTO production_routing_resource_requirement
                    (routing_id,routing_version,step_id,resource_id,reference_qty,quantity_unit,run_time,time_unit,time_basis,concurrent_units,setup_time,setup_policy_ref,alternative_group_ref,is_primary,batch_id)
                    VALUES(:routing_id,:routing_version,:step_id,:resource_id,:reference_qty,:quantity_unit,:run_time,:time_unit,:time_basis,:concurrent_units,:setup_time,:setup_policy_ref,:alternative_group_ref,:is_primary,:batch_id)"""),
                    {**p,**r,'batch_id':batch_id,'is_primary':i==0})
    return len(records)


def planning_snapshot(c, command):
    from app.integrations.planning_validation import horizon_bounds, month_bounds

    first_date, last_date = horizon_bounds(command)
    first, last = first_date.isoformat(), last_date.isoformat()
    periods = set(command.months)
    resources = approved_rows(c,'resources')
    quantities = [r for r in approved_rows(c,'quantity_limits') if r['payload']['period'] in periods and r['payload']['product_id'] in command.product_ids]
    budgets = [r for r in approved_rows(c,'hours_budgets') if r['payload']['period'] in periods]
    routing = [r for r in approved_rows(c,'routing_steps') if r['payload']['product_id'] in command.product_ids and r['payload']['valid_from']<=last and (r['payload'].get('valid_to') or '9999-12-31')>=first]
    ids = {r['batch_id'] for r in [*resources,*quantities,*budgets,*routing]}
    common = {'resources':[r['payload'] for r in resources], 'quantity_limits':[], 'hours_budgets':[], 'routing_steps':[], 'unresolved_policy_refs':['POLICY_NOT_CONFIRMED']}
    capacity = {**common,'quantity_limits':[r['payload'] for r in quantities],'hours_budgets':[r['payload'] for r in budgets]} if quantities or budgets else None
    routes = {**common,'routing_steps':[r['payload'] for r in routing]} if routing else None
    missing = ['POLICY_NOT_CONFIRMED']
    if capacity is None: missing.append('CAPACITY_NOT_REGISTERED')
    if routes is None: missing.append('ROUTING_NOT_REGISTERED')
    budget_keys = {(r['payload']['resource_id'], r['payload']['period']) for r in budgets}
    if any((r['payload']['resource_id'], month) not in budget_keys for r in resources for month in periods):
        missing.append('HOURS_COVERAGE')
    for month in periods:
        start, end = (day.isoformat() for day in month_bounds(month))
        for product in command.product_ids:
            steps = [r['payload'] for r in routing if r['payload']['product_id'] == product
                     and r['payload']['valid_from'] <= end and (r['payload'].get('valid_to') or '9999-12-31') >= start]
            versions = {(row['routing_id'], row['routing_version']) for row in steps}
            if not steps:
                missing.append('ROUTING_COVERAGE')
            if len(versions) > 1 or any(row['valid_from'] > start or (row.get('valid_to') or '9999-12-31') < end for row in steps):
                missing.append('ROUTING_VERSION_POLICY_REQUIRED')
    return capacity,routes,ids,sorted(set(missing))
