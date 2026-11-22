"""Rollback-only PostgreSQL checks in the dedicated synthetic regression DB."""
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ('backend', 'modules/planning_engine', '.')]

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.batches.service import BatchService
from app.batches.sql_repository import SqlBatchRepository, SqlBatchTx
from app.datasets import schema_for
from app.errors import ApiError
from app.forecast.runs import ForecastRuns
from app.forecast.runs_schemas import ForecastRunRequest
from app.integrations.planning import _json, snapshot_digest
from app.plans.repository import PlanRepository
from app.plans.service import what_if_snapshot
from contracts.interfaces.planning import PlanCommand, PlanningInput, PlanningOutput, MaterialRequirement
from scripts.postgresql_preservation import docker_identity
from scripts.verify_test_db import DATABASE, ROLE, SENTINEL, validate_test_url

EXAMPLES = ROOT / 'contracts/examples'
PROTECTED_TABLES = ('import_batch', 'batch_source_file', 'product', 'material', 'monthly_demand',
                    'forecast_run', 'forecast_run_input', 'demand_forecast',
                    'plan_execution', 'plan_candidate', 'plan_constraint_evaluation',
                    'plan_material_requirement', 'plan_execution_input', 'plan_review', 'plan_decision')
OFFICIAL = 'CHUNGPAMO-2027'


def verify_target(connection):
    if tuple(connection.execute(text('SELECT current_database(), current_user')).one()) != (DATABASE, ROLE):
        raise RuntimeError('Refusing to run outside the isolated regression DB and role')
    flags = connection.execute(text(
        'SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user')).one()
    if any(flags):
        raise RuntimeError('Privileged regression role refused')
    if connection.execute(text('SELECT purpose FROM public.regression_test_sentinel')).scalars().all() != [SENTINEL]:
        raise RuntimeError('Dedicated regression sentinel missing')
    if connection.execute(text('SELECT version_num FROM public.alembic_version')).scalar_one() != '0009':
        raise RuntimeError('Expected existing revision 0009')
    scope = connection.execute(text('SELECT schema_name,status FROM public.dataset WHERE dataset_id=:dataset'),
                               {'dataset': OFFICIAL}).one()
    if tuple(scope) != (schema_for(OFFICIAL), 'ACTIVE'):
        raise RuntimeError('Dedicated regression dataset scope mismatch')


def fingerprint(connection):
    return {
        f'{schema}.{table}': tuple(connection.execute(text(
            f"""SELECT count(*), md5(coalesce(string_agg(row_to_json(t)::text, E'\\n' ORDER BY row_to_json(t)::text), ''))
            FROM "{schema}"."{table}" AS t""")).one())
        for schema in ('public', schema_for(OFFICIAL))
        for table in PROTECTED_TABLES
    }


class SavepointDatabase:
    """Keep the application transaction boundaries inside the caller's outer rollback."""
    dataset_id = 'TISSUE-LEGACY'

    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def begin(self):
        with self.connection.begin_nested():
            yield self.connection


def seed_snapshot(connection):
    database = SavepointDatabase(connection)
    service = BatchService(SqlBatchRepository(database))
    for entity, name in [('product', 'tissue_products.csv'), ('material', 'tissue_materials.csv'),
                         ('monthly_demand', 'tissue_demand.csv')]:
        batch = service.create_batch(name, (EXAMPLES / name).read_bytes(), entity=entity, source_type='SYNTHETIC',
                                     source_note='Rollback-only planning SQL fixture')
        service.approve(batch.batch_id, approved_by='TEST-REVIEWER', expected_result_digest=batch.result_digest)
    forecast = ForecastRuns(database).create(
        ForecastRunRequest(trained_until='2026-12-31', horizon_months=12)).execution
    assert forecast.status in ('OK', 'PARTIAL') and len(forecast.result.forecasts) == 12

    # Approved facts and forecast are generated through real storage. The planning result is a test double.
    source_rows = connection.execute(text("""SELECT batch_id,version AS batch_version,entity,
                source_sha256,result_digest,approved_at FROM import_batch WHERE status='APPROVED' ORDER BY batch_id""")).mappings()
    sources = list(source_rows)
    example = json.loads((EXAMPLES / 'integration/planning_input.json').read_text(encoding='utf-8'))['payload']
    approved = SqlBatchTx(connection)
    products, _ = approved.list_products(None, None, 100, 0)
    materials, _ = approved.list_materials(None, None, 100, 0)
    product = products[0]
    material = materials[0]
    command = PlanCommand(forecast_execution_id=forecast.execution_id, product_ids=['TP-10R'],
                          target_month='2027-01', horizon_months=12, as_of_date='2026-12-31')
    snapshot = PlanningInput.model_validate_json(_json({
        **example, 'command': command.model_dump(mode='json'), 'forecast_input_digest': forecast.input_digest,
        'forecast_rows': [{**row.model_dump(mode='json', include={'product_id','target_month','p50','p80','p90'}),
                           'unit': product.base_unit} for row in forecast.result.forecasts],
        'approved_inputs': {
            'products': [asdict(row) for row in products], 'materials': [asdict(row) for row in materials],
            'boms': [], 'inventory': [], 'sources': [dict(row) for row in sources],
        },
    }))
    result = PlanningOutput.model_validate(json.loads(
        (EXAMPLES / 'integration/planning_output.json').read_text(encoding='utf-8'))['payload'])
    result.status = 'OK'
    for plan in result.plans:
        plan.production = [plan.production[0].model_copy(update={'period': period}) for period in command.months]
    result.material_requirements = [
        MaterialRequirement(plan_id=result.plans[0].plan_id, material_id=material.material_id, period=period,
                            required_qty='1.000001', available_qty=None, shortage_qty=None,
                            unit=material.base_unit, input_refs=['TEST-DOUBLE-ONLY'])
        for period in command.months
    ]
    return snapshot, result


def expect_code(call, code):
    try:
        call()
    except ApiError as exc:
        assert exc.code.value == code, exc.code
    else:
        raise AssertionError(f'Expected {code}')


def probe(connection, engine, snapshot, result):
    key = uuid4().hex * 2
    origin = 'TEST_DOUBLE'
    assert PlanRepository.lock_and_find_reusable(connection, key, origin=origin) is None
    parent = PlanRepository.save(connection, snapshot, result, {'test_double': True}, key, origin=origin)
    assert PlanRepository.lock_and_find_reusable(connection, key, origin=origin) == parent.execution_id
    assert PlanRepository.lock_and_find_reusable(connection, key) is None
    with engine.connect() as other:
        verify_target(other)
        assert not other.execute(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key': int(key[:15], 16)}).scalar_one()

    replay = PlanRepository.detail(connection, parent.execution_id, include_test=True)
    assert replay.input_digest == snapshot_digest(snapshot) and replay.result_snapshot == result
    assert replay.horizon_months == 12
    expect_code(lambda: PlanRepository.detail(connection, parent.execution_id), 'PLAN_NOT_FOUND')
    command = PlanCommand.model_validate({
        **snapshot.command.model_dump(), 'scenario': 'WHAT_IF', 'base_plan_execution_id': parent.execution_id,
        'overrides': {'demand_multiplier': '1.1'},
    })
    expect_code(lambda: what_if_snapshot(parent, command), 'PLAN_NOT_FOUND')
    child_input = what_if_snapshot(parent, command, allow_test=True)
    child = PlanRepository.save(connection, child_input, result, {'test_double': True}, uuid4().hex * 2, origin=origin)
    assert child.base_plan_execution_id == parent.execution_id and child.input_digest != parent.input_digest
    assert child.input_snapshot.base_plan_snapshot['result_digest'] == parent.result_digest
    assert PlanRepository.detail(connection, parent.execution_id, include_test=True) == replay
    unknown_parent = child_input.model_copy(deep=True)
    unknown_parent.command.base_plan_execution_id = uuid4()
    try:
        with connection.begin_nested():
            PlanRepository.save(connection, unknown_parent, result, {}, uuid4().hex * 2, origin=origin)
    except IntegrityError as exc:
        assert exc.orig.sqlstate == '23503'
    else:
        raise AssertionError('Unknown parent FK was accepted')
    connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema_for(OFFICIAL)}", pg_catalog')
    expect_code(lambda: PlanRepository.detail(connection, parent.execution_id, include_test=True), 'PLAN_NOT_FOUND')
    connection.exec_driver_sql('SET LOCAL search_path TO public, pg_catalog')
    connection.exec_driver_sql('SET CONSTRAINTS ALL IMMEDIATE')
    connection.exec_driver_sql('SET CONSTRAINTS ALL DEFERRED')

    try:
        with connection.begin_nested():
            PlanRepository.save(connection, snapshot, result, {}, key, origin=origin)
    except IntegrityError as exc:
        assert exc.orig.sqlstate == '23505'
    else:
        raise AssertionError('Duplicate TEST_DOUBLE was accepted')

    class FailAfterInsert:
        def execute(self, query, params):
            if str(query).startswith('INSERT INTO plan_material_requirement'):
                raise RuntimeError('Synthetic mid-save fault')
            return connection.execute(query, params)

    before = fingerprint(connection)
    try:
        with connection.begin_nested():
            PlanRepository.save(FailAfterInsert(), snapshot, result, {}, uuid4().hex * 2, origin=origin)
    except RuntimeError as exc:
        assert str(exc) == 'Synthetic mid-save fault'
    else:
        raise AssertionError('Expected mid-save fault')
    assert fingerprint(connection) == before
    return key


def main():
    identity = docker_identity()
    target = validate_test_url(dotenv_values(ROOT / '.env.regression.local').get('TEST_DATABASE_URL'))
    read_only = create_engine(target, connect_args={'options': '-c default_transaction_read_only=on', 'connect_timeout': 3})
    engine = create_engine(target, connect_args={'options': '-c lock_timeout=2000 -c statement_timeout=15000', 'connect_timeout': 3})
    try:
        with read_only.connect() as c:
            verify_target(c)
            assert c.execute(text('SHOW transaction_read_only')).scalar_one() == 'on'
            before = fingerprint(c)
            if any(count for count, _ in before.values()):
                raise RuntimeError('Regression fixture tables are not empty; preserve existing rows')
        with engine.connect() as c:
            outer = c.begin()
            try:
                verify_target(c)
                assert fingerprint(c) == before
                c.exec_driver_sql('SET LOCAL search_path TO public, pg_catalog')
                key = probe(c, engine, *seed_snapshot(c))
            finally:
                outer.rollback()
        with engine.connect() as c:
            verify_target(c)
            c.exec_driver_sql('SET LOCAL search_path TO public, pg_catalog')
            assert PlanRepository.lock_and_find_reusable(c, key, origin='TEST_DOUBLE') is None
        with read_only.connect() as c:
            verify_target(c)
            assert fingerprint(c) == before
        assert docker_identity() == identity
        print(json.dumps({'database': DATABASE, 'revision': '0009', 'origin': 'TEST_DOUBLE',
                          'horizon_months': 12, 'dedup': 'reuse and 23505 verified',
                          'lock': 'contended on second connection and released on rollback',
                          'lineage': 'verified', 'dataset_isolation': 'verified',
                          'injected_fault': 'rolled back', 'tables_verified_unchanged': len(before)}))
    finally:
        engine.dispose()
        read_only.dispose()


if __name__ == '__main__':
    main()
