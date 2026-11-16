"""Add immutable transformation sources and batch evidence to every registered dataset."""
from alembic import op
from sqlalchemy import text

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    from app.dataset_schema_v2 import add_history, history_ddl, schema_for
    if op.get_context().as_sql:
        op.execute(history_ddl('TISSUE-LEGACY'))
        op.execute('-- 0009 requires ONLINE registry validation and DDL for every existing dataset, including archived datasets.')
        return
    c = op.get_bind()
    c.execute(text('SELECT pg_advisory_xact_lock(880008)'))
    datasets = c.execute(text('SELECT dataset_id,schema_name FROM public.dataset ORDER BY dataset_id')).mappings().all()
    if not datasets or not any(row['dataset_id'] == 'TISSUE-LEGACY' for row in datasets):
        raise RuntimeError('Dataset registry is missing; ingestion migration refused')
    for row in datasets:
        if row['schema_name'] != schema_for(row['dataset_id']):
            raise RuntimeError('Dataset schema identity mismatch; ingestion migration refused')
        add_history(c, row['dataset_id'])


def downgrade():
    raise RuntimeError('Transformation evidence is permanent; destructive downgrade is unsupported')
