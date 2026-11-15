"""Explicitly authorized new regression DB/role only. Never initializes an existing DB."""
from pathlib import Path
import secrets
import os
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]


def main():
    from dotenv import dotenv_values
    from sqlalchemy import create_engine,text
    from sqlalchemy.engine import URL
    from scripts.seed_tissue_capacity import verify_target
    from scripts.verify_test_db import DATABASE,ROLE,SENTINEL,TOKEN
    if os.environ.get("CHUNGPAMO_ALLOW_TEST_DB_RESET")!=TOKEN:raise RuntimeError("Separate provisioning approval required")
    verify_target().dispose()
    destination=ROOT/'.env.regression.local'
    if destination.exists():raise RuntimeError('Local test configuration exists; refusing reprovision')
    env=dotenv_values(ROOT/'.env')
    admin=env.get('POSTGRES_ADMIN_USER','chungpamo_admin');password=env.get('POSTGRES_ADMIN_PASSWORD')
    if not password:raise RuntimeError('Dedicated PostgreSQL admin credential unavailable')
    url=URL.create('postgresql+psycopg',username=admin,password=password,host='127.0.0.1',port=55433,database='postgres')
    engine=create_engine(url,isolation_level='AUTOCOMMIT')
    credential=secrets.token_urlsafe(36)
    # Random URL-safe characters only; never interpolate user-supplied SQL or print credentials.
    with engine.connect() as c:
        if c.execute(text('SELECT 1 FROM pg_database WHERE datname=:n'),{'n':DATABASE}).scalar():raise RuntimeError('Database exists; preserve and investigate')
        if c.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:n'),{'n':ROLE}).scalar():raise RuntimeError('Role exists; preserve and investigate')
        try:
            c.exec_driver_sql(f"CREATE ROLE {ROLE} LOGIN PASSWORD '{credential}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION")
            c.exec_driver_sql(f'CREATE DATABASE {DATABASE} OWNER {ROLE}')
            c.exec_driver_sql(f'REVOKE CONNECT ON DATABASE {DATABASE} FROM PUBLIC')
        except Exception:
            # PostgreSQL/SQLAlchemy exceptions can include the CREATE ROLE SQL/password.
            # Preserve any partially created resources for manual inspection; never retry/reset.
            raise RuntimeError('Regression provisioning failed; preserve resources and inspect privately') from None
    engine.dispose()
    target=URL.create('postgresql+psycopg',username=ROLE,password=credential,host='127.0.0.1',port=55433,database=DATABASE)
    e=create_engine(target)
    with e.begin() as c:
        assert tuple(c.execute(text('SELECT current_database(),current_user')).one())==(DATABASE,ROLE)
        c.execute(text('CREATE TABLE regression_test_sentinel(purpose text NOT NULL)'))
        c.execute(text('INSERT INTO regression_test_sentinel VALUES(:p)'),{'p':SENTINEL})
    destination.write_text('TEST_DATABASE_URL='+target.render_as_string(hide_password=False)+'\n',encoding='utf-8')
    e.dispose()
    print('Created isolated regression DB and unprivileged role; secret saved only to ignored local configuration.')


if __name__=='__main__':main()
