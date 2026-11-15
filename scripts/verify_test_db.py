"""Fail closed: a separate disposable DB, role, credentials and approval are required.
This check never creates, resets or silently retargets a database.
"""
import json
import os
import subprocess
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url

DATABASE = 'chungpamo_regression'
ROLE = 'chungpamo_regression_runner'
TOKEN = DATABASE+'@127.0.0.1:55433'
SENTINEL = 'DISPOSABLE-SYNTHETIC-REGRESSION-V1'


def validate_test_url(url=None):
    raw=url or os.environ.get('TEST_DATABASE_URL')
    if not raw:raise RuntimeError('Explicit TEST_DATABASE_URL is required; development DATABASE_URL is never reused')
    try:u=make_url(raw)
    except Exception:raise RuntimeError('Invalid test database URL') from None
    if (u.drivername,u.host,u.port,u.username,u.database)!=('postgresql+psycopg','127.0.0.1',55433,ROLE,DATABASE):
        raise RuntimeError('Refusing database target outside dedicated regression DB/role')
    if not u.password or u.query:
        raise RuntimeError('Separate test password required; URL options are not allowed')
    from dotenv import dotenv_values
    from pathlib import Path
    raw_dev=dotenv_values(Path(__file__).resolve().parents[1]/'.env').get('DATABASE_URL')
    dev=make_url(raw_dev) if raw_dev else None
    if dev and u.password==dev.password:raise RuntimeError('Development credentials cannot be reused')
    return u


def assert_destructive_engine(engine):
    if os.environ.get('CHUNGPAMO_ALLOW_TEST_DB_RESET')!=TOKEN:
        raise RuntimeError('Separate user approval required before destructive regression tests')
    validate_test_url(engine.url)


def authorize_reset(url=None):
    if os.environ.get('CHUNGPAMO_ALLOW_TEST_DB_RESET')!=TOKEN:
        raise RuntimeError('Separate user approval required before test DB reset; current request does not authorize initialization')
    target=validate_test_url(url)
    info=json.loads(subprocess.check_output(['docker','inspect','chungpamo-monorepo-db'],encoding='utf-8'))[0]
    if (info['Config']['Labels'].get('com.docker.compose.project')!='chungpamo-monorepo'
        or info['State'].get('Health',{}).get('Status')!='healthy'
        or info['HostConfig']['PortBindings'].get('5432/tcp')!=[{'HostIp':'127.0.0.1','HostPort':'55433'}]
        or set(info['NetworkSettings']['Networks'])!={'chungpamo-monorepo-net'}
        or {m['Name'] for m in info['Mounts'] if m['Type']=='volume'}!={'chungpamo-monorepo-pgdata'}):
        raise RuntimeError('Dedicated container identity mismatch')
    engine=create_engine(target,connect_args={'connect_timeout':3})
    try:
        with engine.connect() as c:
            if tuple(c.execute(text('SELECT current_database(),current_user')).one())!=(DATABASE,ROLE):
                raise RuntimeError('Connected database/role mismatch')
            flags=c.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user')).one()
            if any(flags):raise RuntimeError('Privileged regression role refused')
            if c.execute(text("SELECT to_regclass('public.regression_test_sentinel')")).scalar() is None:
                raise RuntimeError('Disposable database sentinel missing; preserve existing data')
            if c.execute(text('SELECT purpose FROM public.regression_test_sentinel')).scalars().all()!=[SENTINEL]:
                raise RuntimeError('Invalid disposable database sentinel')
            from app.dataset_schema_v1 import CORE_TABLES,schema_for
            allowed_schemas={'public',schema_for('CHUNGPAMO-2027'),'regression_history_0001','regression_history_0005'}
            schemas=set(c.execute(text("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema'")).scalars())
            if schemas-allowed_schemas:raise RuntimeError('Unexpected test schema; preserve and investigate')
            for schema in schemas:
                tables=set(c.execute(text('SELECT tablename FROM pg_tables WHERE schemaname=:s'),{'s':schema}).scalars())
                if tables-set(CORE_TABLES)-{'dataset','alembic_version','regression_test_sentinel'}:
                    raise RuntimeError('Unexpected test table; preserve and investigate')
                if 'import_batch' in tables:
                    invalid=c.execute(text(f"SELECT count(*) FROM {schema}.import_batch WHERE source_type<>'SYNTHETIC' OR coalesce(source_note,'')='' ")).scalar()
                    if invalid:raise RuntimeError('Non-synthetic/unidentified rows; refusing reset')
    finally:engine.dispose()
    return target


if __name__=='__main__':
    authorize_reset()
    print('Explicit regression target verified; no data modified.')
