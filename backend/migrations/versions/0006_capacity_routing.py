"""Approved capacity and concurrent routing resources. Existing revisions unchanged."""
from alembic import op
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

DDL = r"""
CREATE TABLE production_resource (
 resource_id varchar(40) PRIMARY KEY, resource_name text NOT NULL CHECK(length(resource_name)>0),
 kind text NOT NULL CHECK(kind IN ('WORKCENTER','LABOR_POOL','EQUIPMENT','EQUIPMENT_POOL')),
 time_basis text NOT NULL CHECK(time_basis IN ('ELAPSED','PERSON_HOUR','MACHINE_HOUR')),
 parallel_units integer NOT NULL CHECK(parallel_units>=1),
 batch_id uuid NOT NULL REFERENCES import_batch, payload jsonb NOT NULL
);
CREATE TABLE production_quantity_limit (
 capacity_id varchar(40), product_id varchar(40) NOT NULL REFERENCES product,
 period char(7) NOT NULL CHECK(period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
 limit_qty numeric(20,6) NOT NULL CHECK(limit_qty>=0), unit varchar(40) NOT NULL,
 accounting_point text NOT NULL CHECK(accounting_point IN ('FINISHED_OUTPUT','OPERATION_OUTPUT')),
 operation_id varchar(40), batch_id uuid NOT NULL REFERENCES import_batch, payload jsonb NOT NULL,
 PRIMARY KEY(capacity_id,period), CHECK(accounting_point<>'OPERATION_OUTPUT' OR operation_id IS NOT NULL)
);
CREATE UNIQUE INDEX uq_quantity_scope ON production_quantity_limit(product_id,period,accounting_point,coalesce(operation_id,''));
CREATE TABLE production_hours_budget (
 capacity_id varchar(40), resource_id varchar(40) NOT NULL REFERENCES production_resource,
 period char(7) NOT NULL CHECK(period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
 regular_hours numeric(20,6) NOT NULL CHECK(regular_hours>=0),
 overtime_hours_limit numeric(20,6) CHECK(overtime_hours_limit>=0),
 unit text NOT NULL CHECK(unit IN ('h','min')),
 time_basis text NOT NULL CHECK(time_basis IN ('ELAPSED','PERSON_HOUR','MACHINE_HOUR')),
 availability_basis text NOT NULL CHECK(availability_basis IN ('GROSS','NET')), calendar_ref varchar(40),
 batch_id uuid NOT NULL REFERENCES import_batch, payload jsonb NOT NULL,
 PRIMARY KEY(capacity_id,period), UNIQUE(resource_id,period)
);
CREATE TABLE production_routing (
 routing_id varchar(40), routing_version varchar(40), product_id varchar(40) NOT NULL REFERENCES product,
 valid_from date NOT NULL, valid_to date, batch_id uuid NOT NULL REFERENCES import_batch,
 PRIMARY KEY(routing_id,routing_version), CHECK(valid_to IS NULL OR valid_to>=valid_from),
 EXCLUDE USING gist(product_id WITH =, daterange(valid_from,valid_to,'[]') WITH &&)
);
CREATE TABLE production_routing_step (
 routing_id varchar(40), routing_version varchar(40), step_id varchar(40),
 product_id varchar(40) NOT NULL REFERENCES product, operation_id varchar(40) NOT NULL,
 valid_from date NOT NULL, valid_to date, batch_id uuid NOT NULL REFERENCES import_batch, payload jsonb NOT NULL,
 PRIMARY KEY(routing_id,routing_version,step_id),
 FOREIGN KEY(routing_id,routing_version) REFERENCES production_routing,
 CHECK(valid_to IS NULL OR valid_to>=valid_from)
);
CREATE TABLE production_routing_resource_requirement (
 routing_id varchar(40), routing_version varchar(40), step_id varchar(40),
 resource_id varchar(40) REFERENCES production_resource,
 reference_qty numeric(20,6) NOT NULL CHECK(reference_qty>0), quantity_unit varchar(40) NOT NULL,
 run_time numeric(20,6) NOT NULL CHECK(run_time>0), time_unit text NOT NULL CHECK(time_unit IN ('h','min')),
 time_basis text NOT NULL CHECK(time_basis IN ('ELAPSED','PERSON_HOUR','MACHINE_HOUR')),
 concurrent_units integer CHECK(concurrent_units>=1), setup_time numeric(20,6) CHECK(setup_time>=0),
 setup_policy_ref varchar(40), alternative_group_ref varchar(40), is_primary boolean NOT NULL,
 batch_id uuid NOT NULL REFERENCES import_batch,
 PRIMARY KEY(routing_id,routing_version,step_id,resource_id),
 FOREIGN KEY(routing_id,routing_version,step_id) REFERENCES production_routing_step,
 CHECK((time_basis='ELAPSED')=(concurrent_units IS NOT NULL)),
 CHECK(setup_time IS NULL OR setup_policy_ref IS NOT NULL)
);
CREATE UNIQUE INDEX uq_routing_primary ON production_routing_resource_requirement(routing_id,routing_version,step_id) WHERE is_primary;
"""

REQUIRE = "\nCREATE OR REPLACE FUNCTION require_approved_batch() RETURNS trigger LANGUAGE plpgsql AS $$\nDECLARE required_entity text;\nBEGIN\n  required_entity := CASE TG_TABLE_NAME\n    WHEN 'production_resource' THEN 'capacity'\n    WHEN 'production_quantity_limit' THEN 'capacity'\n    WHEN 'production_hours_budget' THEN 'capacity'\n    WHEN 'production_routing' THEN 'routing'\n    WHEN 'production_routing_step' THEN 'routing'\n    WHEN 'production_routing_resource_requirement' THEN 'routing'\n    WHEN 'product' THEN 'product'\n    WHEN 'monthly_demand' THEN 'monthly_demand'\n    WHEN 'material' THEN 'material'\n    WHEN 'bom_header' THEN 'bom'\n    WHEN 'bom_line' THEN 'bom'\n    WHEN 'inventory' THEN 'inventory'\n  END;\n  IF NOT EXISTS (SELECT 1 FROM import_batch\n                 WHERE batch_id = NEW.batch_id AND status = 'APPROVED' AND approved_at = now()\n                   AND (required_entity IS NULL OR entity = required_entity)) THEN\n    RAISE EXCEPTION 'batch % is not APPROVED in this transaction for table %: business rows can only be written by the approving transaction of a matching entity',\n      NEW.batch_id, TG_TABLE_NAME USING ERRCODE = 'check_violation';\n  END IF;\n  RETURN NEW;\nEND $$\n"
COUNT = "\nCREATE OR REPLACE FUNCTION verify_approved_record_count() RETURNS trigger LANGUAGE plpgsql AS $$\nDECLARE n bigint;\nBEGIN\n  IF NEW.entity = 'capacity' THEN\n    SELECT (SELECT count(*) FROM production_resource WHERE batch_id=NEW.batch_id)\n         + (SELECT count(*) FROM production_quantity_limit WHERE batch_id=NEW.batch_id)\n         + (SELECT count(*) FROM production_hours_budget WHERE batch_id=NEW.batch_id) INTO n;\n  ELSIF NEW.entity = 'routing' THEN\n    SELECT count(*) INTO n FROM production_routing_step WHERE batch_id=NEW.batch_id;\n    IF EXISTS(SELECT 1 FROM production_routing_step s WHERE s.batch_id=NEW.batch_id AND\n      (SELECT count(*) FROM production_routing_resource_requirement r WHERE\n       (r.routing_id,r.routing_version,r.step_id)=(s.routing_id,s.routing_version,s.step_id))\n        <> 1+jsonb_array_length(s.payload->'resource_requirements')) THEN\n      RAISE EXCEPTION 'routing resource row count mismatch' USING ERRCODE='check_violation';\n    END IF;\n  ELSIF NEW.entity = 'monthly_demand' THEN\n    SELECT count(*) INTO n FROM monthly_demand WHERE batch_id = NEW.batch_id;\n  ELSIF NEW.entity = 'product' THEN\n    SELECT count(*) INTO n FROM product WHERE batch_id = NEW.batch_id;\n  ELSIF NEW.entity = 'material' THEN\n    SELECT count(*) INTO n FROM material WHERE batch_id = NEW.batch_id;\n  ELSIF NEW.entity = 'bom' THEN\n    SELECT count(*) INTO n FROM bom_line WHERE batch_id = NEW.batch_id;\n  ELSIF NEW.entity = 'inventory' THEN\n    SELECT count(*) INTO n FROM inventory WHERE batch_id = NEW.batch_id;\n  END IF;\n  IF n IS DISTINCT FROM NEW.approved_record_count::bigint THEN\n    RAISE EXCEPTION 'batch %: approved_record_count % but % rows written', NEW.batch_id, NEW.approved_record_count, n\n      USING ERRCODE = 'check_violation';\n  END IF;\n  RETURN NULL;\nEND $$\n"

def upgrade():
    op.execute(DDL)
    op.drop_constraint('ck_batch_entity','import_batch')
    op.create_check_constraint('ck_batch_entity','import_batch',"entity IN ('monthly_demand','product','material','bom','inventory','capacity','routing')")
    op.execute(REQUIRE)
    op.execute(COUNT)
    for table in ('production_resource','production_quantity_limit','production_hours_budget','production_routing','production_routing_step','production_routing_resource_requirement'):
        op.execute(f'CREATE TRIGGER trg_{table}_insert BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION require_approved_batch()')
        op.execute(f'CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION forbid_change()')


def downgrade():
    # Refuse destructive rollback once registrations exist. No automatic data deletion.
    from sqlalchemy import text
    c = op.get_bind()
    if c.execute(text("SELECT EXISTS(SELECT 1 FROM import_batch WHERE entity IN ('capacity','routing'))")).scalar():
        raise RuntimeError('Capacity registrations exist: destructive downgrade refused')
    op.execute("\nCREATE OR REPLACE FUNCTION require_approved_batch() RETURNS trigger LANGUAGE plpgsql AS $$\nDECLARE required_entity text;\nBEGIN\n  required_entity := CASE TG_TABLE_NAME\n    WHEN 'product' THEN 'product'\n    WHEN 'monthly_demand' THEN 'monthly_demand'\n    WHEN 'material' THEN 'material'\n    WHEN 'bom_header' THEN 'bom'\n    WHEN 'bom_line' THEN 'bom'\n    WHEN 'inventory' THEN 'inventory'\n  END;\n  IF NOT EXISTS (SELECT 1 FROM import_batch\n                 WHERE batch_id = NEW.batch_id AND status = 'APPROVED' AND approved_at = now()\n                   AND (required_entity IS NULL OR entity = required_entity)) THEN\n    RAISE EXCEPTION 'batch % is not APPROVED in this transaction for table %: business rows can only be written by the approving transaction of a matching entity',\n      NEW.batch_id, TG_TABLE_NAME USING ERRCODE = 'check_violation';\n  END IF;\n  RETURN NEW;\nEND $$\n")
    op.execute("\nCREATE OR REPLACE FUNCTION verify_approved_record_count() RETURNS trigger LANGUAGE plpgsql AS $$\nDECLARE n bigint;\nBEGIN\n  IF NEW.entity = 'monthly_demand' THEN\n    SELECT count(*) INTO n FROM monthly_demand WHERE batch_id = NEW.batch_id;\n  ELSIF NEW.entity = 'product' THEN\n    SELECT count(*) INTO n FROM product WHERE batch_id = NEW.batch_id;\n  ELSIF NEW.entity = 'material' THEN\n    SELECT count(*) INTO n FROM material WHERE batch_id = NEW.batch_id;\n  ELSIF NEW.entity = 'bom' THEN\n    SELECT count(*) INTO n FROM bom_line WHERE batch_id = NEW.batch_id;\n  ELSIF NEW.entity = 'inventory' THEN\n    SELECT count(*) INTO n FROM inventory WHERE batch_id = NEW.batch_id;\n  END IF;\n  IF n IS DISTINCT FROM NEW.approved_record_count::bigint THEN\n    RAISE EXCEPTION 'batch %: approved_record_count % but % rows written', NEW.batch_id, NEW.approved_record_count, n\n      USING ERRCODE = 'check_violation';\n  END IF;\n  RETURN NULL;\nEND $$\n")
    op.drop_constraint('ck_batch_entity','import_batch')
    op.create_check_constraint('ck_batch_entity','import_batch',"entity IN ('monthly_demand','product','material','bom','inventory')")
    for table in ('production_routing_resource_requirement','production_routing_step','production_routing','production_hours_budget','production_quantity_limit','production_resource'):
        op.drop_table(table)
