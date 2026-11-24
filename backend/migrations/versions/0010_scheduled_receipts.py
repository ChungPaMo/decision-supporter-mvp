"""Add immutable scheduled receipt revisions to each registered dataset."""
from importlib import import_module
from alembic import op
from sqlalchemy import text

from app.dataset_schema_v3 import add_receipts, receipt_count_definition, receipt_ddl, schema_for


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().as_sql:
        op.execute('-- 0010 offline output shows legacy DDL only; online registry validation and per-dataset DDL are required.')
        op.execute(receipt_ddl('TISSUE-LEGACY'))
        old_count = import_module('migrations.versions.0006_capacity_routing').COUNT
        op.execute(receipt_count_definition(old_count))
        return
    c = op.get_bind()
    c.execute(text('SELECT pg_advisory_xact_lock(880008)'))
    registry = c.execute(text('SELECT dataset_id, schema_name FROM public.dataset ORDER BY dataset_id')).all()
    if ('TISSUE-LEGACY', 'public') not in registry or any(schema_for(d) != s for d, s in registry):
        raise RuntimeError('Unexpected dataset registry; scheduled receipt migration refused')
    for dataset_id, _ in registry:
        add_receipts(c, dataset_id)


def downgrade():
    raise RuntimeError('Approved scheduled receipt revisions are permanent')
