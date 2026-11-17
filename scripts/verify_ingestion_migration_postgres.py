"""Approved REGRESSION DB only: fresh upgrade to 0008, rollback-only 0009 preservation probe.

Never downgrades. Development DB is not opened. Existing sentinel/target guard is mandatory.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]


def main():
    from dotenv import dotenv_values
    from sqlalchemy import create_engine, text
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from app.dataset_schema_v1 import CORE_TABLES, provision_schema, schema_for
    from scripts.verify_test_db import authorize_reset, DATABASE, ROLE, SENTINEL
    from tests.test_db_rules import _approved_batch, _product, _demand
    url = authorize_reset(dotenv_values(ROOT / '.env.regression.local')['TEST_DATABASE_URL'])
    engine = create_engine(url)
    with engine.begin() as c:
        assert tuple(c.execute(text('SELECT current_database(),current_user')).one()) == (DATABASE, ROLE)
        for schema in ('regression_history_0001', 'regression_history_0005', schema_for('CHUNGPAMO-2027'), 'public'):
            c.exec_driver_sql('DROP SCHEMA IF EXISTS "' + schema + '" CASCADE')
        c.exec_driver_sql('CREATE SCHEMA public')
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', '0008'], cwd=ROOT / 'backend',
        env={**os.environ, 'DATABASE_URL': url.render_as_string(hide_password=False)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with engine.begin() as c:
        c.execute(text('CREATE TABLE regression_test_sentinel(purpose text NOT NULL)'))
        c.execute(text('INSERT INTO regression_test_sentinel VALUES(:p)'), {'p': SENTINEL})
    archive_id = 'ARCHIVED-MIGRATION-PROBE'
    schemas = ['public', schema_for('CHUNGPAMO-2027'), schema_for(archive_id)]
    with engine.connect() as c:
        transaction = c.begin()
        try:
            provision_schema(c, archive_id)
            c.execute(text("INSERT INTO public.dataset(dataset_id,dataset_name,description,source_type,status,schema_name) VALUES(:d,'Synthetic migration probe','Rollback only','SYNTHETIC','ARCHIVED',:s)"), {'d': archive_id, 's': schemas[-1]})
            for schema in schemas:
                c.exec_driver_sql(f'SET LOCAL search_path TO "{schema}",pg_catalog')
                product = _approved_batch(c, entity='product'); _product(c, product, 'MIGRATION-PROBE')
                demand = _approved_batch(c); _demand(c, demand, 'MIGRATION-PROBE')
                c.execute(text("INSERT INTO demand_forecast(product_id,target_month,horizon,p50,p80,p90,p50_method,quantile_model_version,trained_until) VALUES('MIGRATION-PROBE','2027-01',1,1,2,3,'MA12','SYNTHETIC-MIGRATION','2026-12-31')"))
            c.exec_driver_sql('SET LOCAL search_path TO public,pg_catalog')
            c.exec_driver_sql('SET CONSTRAINTS ALL IMMEDIATE')
            def fingerprints():
                output = {}
                for schema in schemas:
                    for table in CORE_TABLES:
                        rows = c.execute(text(f'SELECT row_to_json(t)::text FROM "{schema}"."{table}" t')).scalars().all()
                        output[schema + '.' + table] = hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()
                return output
            before = fingerprints()
            path = ROOT / 'backend/migrations/versions/0009_ingestion_history.py'
            spec = importlib.util.spec_from_file_location('approved_regression_migration_probe', path)
            migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(c)):
                migration.upgrade()
            assert before == fingerprints(), '0009 altered existing rows'
            for schema in schemas:
                assert c.execute(text('SELECT count(*) FROM pg_tables WHERE schemaname=:s AND tablename IN (\'ingestion_transformation\',\'ingestion_transform_source\')'), {'s': schema}).scalar_one() == 2
                assert c.execute(text(f'SELECT count(*) FROM "{schema}".ingestion_transformation')).scalar_one() == 0
            report = {'scope': 'ROLLBACK-ONLY REAL POSTGRESQL 0009 UPGRADE BODY', 'schemas_including_archived': 3,
                      'existing_table_fingerprints_equal': len(before), 'approved_batch_and_demand_and_forecast_preserved': True,
                      'downgrade_executed': False, 'probe_rolled_back': True}
        finally:
            transaction.rollback()
        assert c.execute(text('SELECT to_regnamespace(:s)'), {'s': schemas[-1]}).scalar() is None
        assert c.execute(text("SELECT to_regclass('public.ingestion_transformation')")).scalar() is None
        assert c.execute(text('SELECT version_num FROM public.alembic_version')).scalar_one() == '0008'
    engine.dispose()
    out = ROOT / '.artifacts/postgresql-ingestion-20261117/migration-probe.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
