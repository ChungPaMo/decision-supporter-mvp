"""Fail closed before destructive tests; explicit human authorization is mandatory."""
import json
import os
from pathlib import Path
import subprocess

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'chungpamo_test@127.0.0.1:55433'
EXPECTED_TABLES = {'alembic_version', 'batch_source_file', 'bom_header', 'bom_line',
                   'demand_forecast', 'forecast_run', 'forecast_run_input', 'import_batch',
                   'inventory', 'material', 'monthly_demand', 'product', 'production_capacity',
                   'sales_order', 'unit'}


def authorize_reset(url=None):
    if os.environ.get('CHUNGPAMO_ALLOW_TEST_DB_RESET') != TOKEN:
        raise RuntimeError('Separate user approval required before test DB reset; see docs/DEVELOPMENT_WORKFLOW.md')
    url = make_url(url or os.environ.get('DATABASE_URL') or dotenv_values(ROOT / '.env').get('DATABASE_URL', ''))
    if (url.drivername, url.host, url.port, url.username, url.database) not in [
        ('postgresql+psycopg', '127.0.0.1', 55433, 'chungpamo_app', db) for db in ('chungpamo', 'chungpamo_test')
    ]:
        raise RuntimeError('Refusing database target outside dedicated monorepo server')
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'chungpamo-monorepo-db'], encoding='utf-8'))[0]
    if (info['Config']['Labels'].get('com.docker.compose.project') != 'chungpamo-monorepo'
            or info['State']['Health']['Status'] != 'healthy'
            or info['NetworkSettings']['Ports']['5432/tcp'] != [{'HostIp': '127.0.0.1', 'HostPort': '55433'}]
            or set(info['NetworkSettings']['Networks']) != {'chungpamo-monorepo-net'}
            or not any(m.get('Name') == 'chungpamo-monorepo-pgdata' for m in info['Mounts'])):
        raise RuntimeError('Container project, port, mount, network or health mismatch')
    target = url.set(database='chungpamo_test')
    engine = create_engine(target, connect_args={'connect_timeout': 3})
    try:
        with engine.connect() as c:
            if c.execute(text('SELECT current_database()')).scalar_one() != 'chungpamo_test':
                raise RuntimeError('Not the test database')
            schemas = set(c.execute(text("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'")).scalars())
            tables = set(c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).scalars())
            if schemas - {'public'} or tables - EXPECTED_TABLES:
                raise RuntimeError('Unexpected schema/table; preserve and investigate')
            if 'import_batch' in tables:
                invalid = c.execute(text("SELECT count(*) FROM import_batch WHERE source_type <> 'SYNTHETIC' OR coalesce(source_note,'') = ''")).scalar_one()
                if invalid:
                    raise RuntimeError('Non-synthetic/unidentified test data; refusing reset')
            for table in ('sales_order', 'production_capacity'):
                if table in tables and c.execute(text(f'SELECT count(*) FROM {table}')).scalar_one():
                    raise RuntimeError('Unexpected planning data; refusing reset')
    finally:
        engine.dispose()
    return target


if __name__ == '__main__':
    authorize_reset()
    print('Dedicated test target verified; no data was modified by this check.')
