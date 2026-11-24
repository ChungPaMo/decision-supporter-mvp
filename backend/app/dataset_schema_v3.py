"""Add an approved append-only receipt ledger to a v2 dataset schema."""
from sqlalchemy import text

from app.dataset_schema_v2 import CORE_TABLES as V2_TABLES, provision_schema as provision_v2, schema_for


CORE_TABLES = (*V2_TABLES, 'scheduled_receipt_revision')
ENTITIES = "'monthly_demand','product','material','bom','inventory','capacity','routing','scheduled_receipt'"


def receipt_ddl(dataset_id):
    schema = f'"{schema_for(dataset_id)}"'
    return f"""
    ALTER TABLE {schema}.import_batch DROP CONSTRAINT ck_batch_entity;
    ALTER TABLE {schema}.import_batch ADD CONSTRAINT ck_batch_entity CHECK (entity IN ({ENTITIES}));

    CREATE TABLE {schema}.scheduled_receipt_revision (
      dataset_id varchar(40) NOT NULL CHECK(dataset_id='{dataset_id}') REFERENCES public.dataset(dataset_id),
      po_id varchar(40) NOT NULL CHECK(po_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{{0,39}}$' AND position('--' in po_id)=0),
      po_line_id varchar(40) CHECK(po_line_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{{0,39}}$' AND position('--' in po_line_id)=0),
      receipt_key varchar(40) GENERATED ALWAYS AS (po_id || COALESCE('--' || po_line_id, '')) STORED,
      revision integer NOT NULL CHECK(revision > 0),
      material_id varchar(40) NOT NULL REFERENCES {schema}.material(material_id),
      expected_date date NOT NULL CHECK(isfinite(expected_date)),
      effective_date date NOT NULL CHECK(isfinite(effective_date)),
      ordered_qty numeric(20,6) NOT NULL CHECK(ordered_qty > 0 AND ordered_qty <> 'NaN'::numeric),
      received_qty numeric(20,6) NOT NULL CHECK(received_qty >= 0 AND received_qty <= ordered_qty),
      unit varchar(40) NOT NULL REFERENCES {schema}.unit(unit_code),
      supplier_id varchar(40) CHECK(supplier_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{{0,39}}$'),
      status text NOT NULL CHECK(status IN ('OPEN','CANCELLED')),
      batch_id uuid NOT NULL REFERENCES {schema}.import_batch(batch_id),
      source_sheet text NOT NULL CHECK(length(source_sheet) > 0),
      source_row_no integer NOT NULL CHECK(source_row_no > 0),
      source_row_sha256 char(64) NOT NULL CHECK(source_row_sha256 ~ '^[0-9a-f]{{64}}$'),
      PRIMARY KEY(receipt_key, revision),
      UNIQUE(batch_id, source_sheet, source_row_no)
    );
    CREATE INDEX ix_receipt_order ON {schema}.scheduled_receipt_revision(po_id);
    CREATE INDEX ix_receipt_effective ON {schema}.scheduled_receipt_revision(receipt_key, effective_date, revision DESC);

    CREATE OR REPLACE FUNCTION {schema}.guard_receipt_revision() RETURNS trigger
    LANGUAGE plpgsql SET search_path TO {schema}, pg_catalog AS $$
    DECLARE previous record;
    BEGIN
      PERFORM pg_advisory_xact_lock(hashtextextended(NEW.dataset_id || ':' || NEW.po_id, 763002));
      IF NOT EXISTS (
        SELECT 1 FROM import_batch WHERE batch_id=NEW.batch_id AND dataset_id=NEW.dataset_id
          AND entity='scheduled_receipt' AND status='APPROVED'
          AND blocking_error_count=0 AND approved_at=now() AND result_digest IS NOT NULL
      ) THEN
        RAISE EXCEPTION 'receipt requires its matching approved batch in this transaction' USING ERRCODE='check_violation';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM material WHERE material_id=NEW.material_id AND base_unit=NEW.unit) THEN
        RAISE EXCEPTION 'receipt material or base unit mismatch' USING ERRCODE='check_violation';
      END IF;
      IF EXISTS (SELECT 1 FROM scheduled_receipt_revision WHERE po_id=NEW.po_id
                 AND (po_line_id IS NULL) <> (NEW.po_line_id IS NULL)) THEN
        RAISE EXCEPTION 'order-wide and line-specific receipts cannot be mixed' USING ERRCODE='check_violation';
      END IF;
      SELECT * INTO previous FROM scheduled_receipt_revision
        WHERE receipt_key=NEW.po_id || COALESCE('--' || NEW.po_line_id, '') ORDER BY revision DESC LIMIT 1;
      IF NOT FOUND THEN
        IF NEW.revision <> 1 OR NEW.status <> 'OPEN' THEN
          RAISE EXCEPTION 'first receipt revision must be open revision one' USING ERRCODE='check_violation';
        END IF;
      ELSIF NEW.revision::bigint <> previous.revision::bigint + 1
         OR NEW.effective_date < previous.effective_date OR NEW.material_id <> previous.material_id
         OR NEW.unit <> previous.unit OR NEW.received_qty < previous.received_qty
         OR previous.status='CANCELLED' OR previous.received_qty=previous.ordered_qty THEN
        RAISE EXCEPTION 'receipt revision conflicts with approved history' USING ERRCODE='check_violation';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER trg_receipt_guard BEFORE INSERT ON {schema}.scheduled_receipt_revision
      FOR EACH ROW EXECUTE FUNCTION {schema}.guard_receipt_revision();
    CREATE TRIGGER trg_receipt_immutable BEFORE UPDATE OR DELETE ON {schema}.scheduled_receipt_revision
      FOR EACH ROW EXECUTE FUNCTION {schema}.forbid_change();
    """


def receipt_count_definition(definition):
    marker = "\n  END IF;\n  IF n IS DISTINCT FROM NEW.approved_record_count::bigint THEN"
    branch = "\n  ELSIF NEW.entity = 'scheduled_receipt' THEN\n"
    if branch in definition:
        return definition
    if definition.count(marker) != 1:
        raise RuntimeError('Unexpected batch row count trigger definition; receipt migration refused')
    return definition.replace(marker, branch +
        '    SELECT count(*) INTO n FROM scheduled_receipt_revision WHERE batch_id = NEW.batch_id;' + marker)


def add_receipts(c, dataset_id):
    schema = f'"{schema_for(dataset_id)}"'
    name = f'{schema}.verify_approved_record_count()'
    definition = c.execute(text('SELECT pg_get_functiondef(to_regprocedure(:name))'), {'name': name}).scalar_one()
    updated = receipt_count_definition(definition)
    c.exec_driver_sql(receipt_ddl(dataset_id))
    if updated != definition:
        c.execute(text(updated))
    c.exec_driver_sql(f'ALTER FUNCTION {name} SET search_path TO {schema}, pg_catalog')


def provision_schema(c, dataset_id):
    provision_v2(c, dataset_id)
    if schema_for(dataset_id) != 'public' and c.exec_driver_sql(
        "SELECT to_regclass('public.scheduled_receipt_revision') IS NOT NULL"
    ).scalar_one():
        add_receipts(c, dataset_id)
