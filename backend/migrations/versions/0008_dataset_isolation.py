"""Additive schema-isolated datasets. No legacy row updates or destructive rollback."""
from alembic import op
from sqlalchemy import text

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

EXPECTED_LEGACY = {'product': ('61aefca9-8077-4ffe-95d0-722e2092fed1', '0153f53446b4b5628bf828620ba55f2930934c723d35749937ac0fd42d077c75', '6c8b3c2d637e29c9282baa86d29240046f58e8604590fd55a8bbd84ae19fb571'), 'material': ('2a09449b-3056-4862-83e1-740ef7f3867f', '778ea1e2ffd54e6f70ef74bd8c02afc8438078602c248cd96b8c23374732a5e3', '6f9285045be3d945a019478ab2da08e8f90b442d9eecc3d4c9e28160908a7f5e'), 'bom': ('c94f3a01-89cb-41e8-82ef-d94e7136b065', '1dd424f8343f85cfab8977c85d6bf99b58ce9169f03d0f2effa512424d482a56', '083ad1ec85b2f816347b2c8ad1594592f9f83cfa510ac33f9c5068d3bf9c5c26'), 'inventory': ('2764fdc3-c216-4e9e-a15e-62abc1ab925a', '66e232b9b15c51741d83ef2d30625d58bde434c6dfbc1e9c4da726ab9f85fd45', 'ee1a5d92b718d41e148cf30514840d9d48818f6327b5334aaace4234c5a489f3'), 'monthly_demand': ('e56c08b0-f078-41f0-9a4b-7f1f9c75a708', '0ec583f804d7be415790be2daacb8cd496415d65bae1426fb2bd83ffbb69367b', 'be4ab542f84b294995ff88d8be4afaf286fad081b3692e823a4aa0d254948db2'), 'capacity': ('9beec28d-b963-415c-a43f-c66eb1175618', 'f370250ad8108425076055b19cb1d1a6b46aa9c0b7b4712fe4100d6f50fbd631', '40d6ed8f997effcf7652f93330b5d9099242fa7746e52bf1ee2f8ce2d04210db'), 'routing': ('1985c611-75a9-41d7-a3d6-ae6f94d6d1f3', '087e01b11a088c171a7a33a9e8c65bccd09c0a66d79225dcf34e9e9cfd2fa2c4', '583b2f78c04915c97e2c010d8346919714616bb82ac789e8a114b3d556e233df')}

DDL="""
CREATE TABLE public.dataset (
 dataset_id varchar(40) PRIMARY KEY CHECK(dataset_id ~ '^[A-Z][A-Z0-9_-]{0,39}$'),
 dataset_name varchar(200) NOT NULL, description text NOT NULL,
 source_type text NOT NULL CHECK(source_type='SYNTHETIC'),
 status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','ARCHIVED')),
 schema_name text NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now(), created_by varchar(60)
);
INSERT INTO public.dataset(dataset_id,dataset_name,description,source_type,schema_name)
 VALUES('TISSUE-LEGACY','Legacy tissue verification','Existing single-product SYNTHETIC verification','SYNTHETIC','public');
ALTER TABLE public.import_batch ADD COLUMN dataset_id varchar(40) NOT NULL DEFAULT 'TISSUE-LEGACY' REFERENCES public.dataset;
ALTER TABLE public.forecast_run ADD COLUMN dataset_id varchar(40) NOT NULL DEFAULT 'TISSUE-LEGACY' REFERENCES public.dataset;
ALTER TABLE public.plan_execution ADD COLUMN dataset_id varchar(40) NOT NULL DEFAULT 'TISSUE-LEGACY' REFERENCES public.dataset;
"""


def upgrade():
    from app.dataset_schema_v1 import CORE_TABLES,provision_schema,schema_for
    offline=op.get_context().as_sql
    if not offline:
        c=op.get_bind()
        actual=set(c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'alembic_version'")).scalars())
        if actual!=set(CORE_TABLES):raise RuntimeError('Unexpected schema; dataset migration refused')
        batches=c.execute(text('SELECT batch_id,entity,status,source_type,source_sha256,result_digest FROM public.import_batch')).mappings().all()
        # Do not classify unknown corporate data or partially processed source batches.
        if batches and (len(batches)!=7 or sorted(r['entity'] for r in batches)!=sorted(['product','material','bom','inventory','monthly_demand','capacity','routing'])
            or any(r['source_type']!='SYNTHETIC' or r['status']!='APPROVED' for r in batches)):
            raise RuntimeError('Unexpected legacy ownership; manual review required')
        if batches:
            if any((str(r['batch_id']),r['source_sha256'],r['result_digest'])!=EXPECTED_LEGACY[r['entity']] for r in batches):
                raise RuntimeError('Unexpected legacy batch identity/hash/digest; migration refused')
            if c.execute(text("SELECT array_agg(product_id ORDER BY product_id) FROM public.product")).scalar()!=['TP-10R']:
                raise RuntimeError('Unexpected legacy products; migration refused')
            if c.execute(text("SELECT array_agg(resource_id ORDER BY resource_id) FROM public.production_resource")).scalar()!=['L1','M1']:
                raise RuntimeError('Unexpected legacy resources; migration refused')
        elif any(c.execute(text('SELECT EXISTS(SELECT 1 FROM public.'+t+')')).scalar() for t in CORE_TABLES if t!='unit'):
            raise RuntimeError('Business rows without expected source batches')
    op.execute(DDL)
    if offline:
        op.execute('-- 0008 requires ONLINE catalog validation/cloning; this offline listing is not a deployment script.')
    else:
        provision_schema(op.get_bind(),'CHUNGPAMO-2027')
        op.execute("INSERT INTO public.dataset(dataset_id,dataset_name,description,source_type,schema_name) VALUES('CHUNGPAMO-2027','Chungpamo Paper 2027','Nine-product synthetic scenario','SYNTHETIC','"+schema_for('CHUNGPAMO-2027')+"')")
    for table in ('import_batch','forecast_run','plan_execution'):
        op.execute(f"ALTER TABLE public.{table} ADD CONSTRAINT ck_{table}_dataset_scope CHECK(dataset_id='TISSUE-LEGACY')")
    op.execute('CREATE TRIGGER trg_dataset_immutable BEFORE UPDATE OR DELETE ON public.dataset FOR EACH ROW EXECUTE FUNCTION public.forbid_change()')


def downgrade():
    raise RuntimeError('Dataset ownership is persistent; destructive downgrade is not supported')
