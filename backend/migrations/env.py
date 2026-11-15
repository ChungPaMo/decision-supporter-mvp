from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.models import Base
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 테스트가 전용 DB 를 지정할 수 있도록 -x url=... 를 허용한다. 지정하지 않으면 .env / 기본값(프로젝트 전용 컨테이너).
    url = context.get_x_argument(as_dictionary=True).get("url") or get_settings().database_url
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        schema=context.get_x_argument(as_dictionary=True).get('schema') or os.environ.get('REGRESSION_MIGRATION_SCHEMA')
        if schema:
            from scripts.verify_test_db import validate_test_url,DATABASE,ROLE
            validate_test_url(url)
            if schema not in ('regression_history_0001','regression_history_0005'):
                raise RuntimeError('Historical migration schema not allowlisted')
            with connection.begin():
                from sqlalchemy import text
                if tuple(connection.execute(text('SELECT current_database(),current_user')).one())!=(DATABASE,ROLE):
                    raise RuntimeError('Historical migration target mismatch')
                connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}",public,pg_catalog')
                context.configure(connection=connection,target_metadata=target_metadata,version_table_schema=schema)
                with context.begin_transaction():context.run_migrations()
            return
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
