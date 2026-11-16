"""Add ingestion evidence to v1 without changing the frozen 0008 provisioning code."""
from app.dataset_schema_v1 import CORE_TABLES as V1_TABLES, ROOT_TABLES as V1_ROOTS, schema_for

HISTORY_TABLES = ('ingestion_transformation', 'ingestion_transform_source')
CORE_TABLES = (*V1_TABLES, *HISTORY_TABLES)
ROOT_TABLES = (*V1_ROOTS, 'ingestion_transformation')

DDL = r'''
CREATE TABLE __SCHEMA__.ingestion_transformation (
 transformation_id uuid PRIMARY KEY,
 dataset_id varchar(40) NOT NULL DEFAULT '__DATASET__' REFERENCES public.dataset(dataset_id),
 batch_id uuid NOT NULL UNIQUE REFERENCES __SCHEMA__.import_batch(batch_id),
 created_at timestamptz NOT NULL,
 input_digest varchar(64) NOT NULL UNIQUE CHECK (input_digest ~ '^[a-f0-9]{64}$'),
 result_digest varchar(64) NOT NULL CHECK (result_digest ~ '^[a-f0-9]{64}$'),
 policy_digest varchar(64) NOT NULL CHECK (policy_digest ~ '^[a-f0-9]{64}$'),
 output_sha256 varchar(64) NOT NULL CHECK (output_sha256 ~ '^[a-f0-9]{64}$'),
 manifest_digest varchar(64) NOT NULL CHECK (manifest_digest ~ '^[a-f0-9]{64}$'),
 manifest jsonb NOT NULL,
 CONSTRAINT ck_ingestion_transformation_dataset_scope CHECK (dataset_id = '__DATASET__'),
 CHECK ((manifest->>'dataset_id' = dataset_id AND manifest->>'batch_id' = batch_id::text
     AND manifest->>'transformation_id' = transformation_id::text
     AND manifest->>'output_sha256' = output_sha256
     AND manifest->'result'->>'dataset_id' = dataset_id
     AND manifest->'result'->>'input_digest' = input_digest
     AND manifest->'result'->>'result_digest' = result_digest
     AND manifest->'result'->>'policy_digest' = policy_digest
     AND manifest->'result'->>'status' = 'TRANSFORMED_PREVIEW'
     AND manifest->'result'->'policy'->>'user_confirmed' = 'true'
     AND jsonb_array_length(manifest->'result'->'records') > 0
     AND (manifest->'result'->>'total')::int = jsonb_array_length(manifest->'result'->'records')
     AND jsonb_array_length(manifest->'result'->'sources') BETWEEN 1 AND 8) IS TRUE)
);
CREATE TABLE __SCHEMA__.ingestion_transform_source (
 transformation_id uuid NOT NULL REFERENCES __SCHEMA__.ingestion_transformation(transformation_id),
 source_index int NOT NULL CHECK (source_index BETWEEN 0 AND 7),
 filename varchar(200) NOT NULL,
 sha256 varchar(64) NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
 content bytea NOT NULL,
 size_bytes int NOT NULL CHECK (size_bytes = octet_length(content) AND size_bytes BETWEEN 1 AND 10485760),
 PRIMARY KEY (transformation_id, source_index),
 UNIQUE (transformation_id, sha256),
 CHECK (sha256 = encode(sha256(content), 'hex'))
);
CREATE TRIGGER trg_ingestion_transformation_immutable BEFORE UPDATE OR DELETE ON __SCHEMA__.ingestion_transformation
 FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.forbid_change();
CREATE TRIGGER trg_ingestion_source_immutable BEFORE UPDATE OR DELETE ON __SCHEMA__.ingestion_transform_source
 FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.forbid_change();
CREATE FUNCTION __SCHEMA__.ingestion_evidence_guard() RETURNS trigger LANGUAGE plpgsql
 SET search_path TO __SCHEMA__,pg_catalog AS $$
DECLARE evidence ingestion_transformation; batch import_batch; source_count int; source_size bigint;
BEGIN
 SELECT * INTO STRICT evidence FROM ingestion_transformation WHERE transformation_id=NEW.transformation_id;
 SELECT * INTO STRICT batch FROM import_batch WHERE batch_id=evidence.batch_id;
 IF batch.dataset_id<>evidence.dataset_id OR batch.entity<>'monthly_demand' OR batch.source_type<>'SYNTHETIC'
    OR batch.source_sha256<>evidence.output_sha256
    OR batch.default_unit IS NOT NULL OR batch.sheet_filter IS NOT NULL OR batch.column_overrides<>'{}'::jsonb THEN
   RAISE EXCEPTION 'Transformation batch evidence mismatch';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM batch_source_file WHERE batch_id=evidence.batch_id
       AND encode(sha256(content),'hex')=evidence.output_sha256) THEN
   RAISE EXCEPTION 'Transformation output bytes mismatch';
 END IF;
 SELECT count(*),coalesce(sum(size_bytes),0) INTO source_count,source_size
   FROM ingestion_transform_source WHERE transformation_id=evidence.transformation_id;
 IF source_count<>jsonb_array_length(evidence.manifest->'result'->'sources') OR source_size>52428800 THEN
   RAISE EXCEPTION 'Transformation sources incomplete or oversized';
 END IF;
 IF EXISTS (SELECT 1 FROM ingestion_transform_source s WHERE s.transformation_id=evidence.transformation_id
    AND ((evidence.manifest->'result'->'sources'->s.source_index->>'sha256' = s.sha256
      AND evidence.manifest->'result'->'sources'->s.source_index->>'filename' = s.filename
      AND (evidence.manifest->'result'->'sources'->s.source_index->>'source_index')::int = s.source_index) IS NOT TRUE)) THEN
   RAISE EXCEPTION 'Transformation source manifest mismatch';
 END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER trg_ingestion_evidence_complete AFTER INSERT ON __SCHEMA__.ingestion_transformation
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.ingestion_evidence_guard();
CREATE CONSTRAINT TRIGGER trg_ingestion_source_complete AFTER INSERT ON __SCHEMA__.ingestion_transform_source
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.ingestion_evidence_guard();
CREATE FUNCTION __SCHEMA__.ingestion_batch_settings_guard() RETURNS trigger LANGUAGE plpgsql
 SET search_path TO __SCHEMA__,pg_catalog AS $$
BEGIN
 IF EXISTS (SELECT 1 FROM ingestion_transformation WHERE batch_id=NEW.batch_id)
    AND (NEW.default_unit IS NOT NULL OR NEW.sheet_filter IS NOT NULL OR NEW.column_overrides<>'{}'::jsonb) THEN
   RAISE EXCEPTION 'Transformation output mapping is immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_ingestion_batch_settings BEFORE UPDATE ON __SCHEMA__.import_batch
 FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.ingestion_batch_settings_guard();
'''


def history_ddl(dataset_id):
    schema = schema_for(dataset_id)
    return DDL.replace('__SCHEMA__', '"' + schema + '"').replace('__DATASET__', dataset_id)


def add_history(c, dataset_id):
    from sqlalchemy import text
    c.execute(text(history_ddl(dataset_id)))


def provision_schema(c, dataset_id):
    """Clone all v2 tables before compiling trigger functions that reference history row types."""
    from sqlalchemy import text
    schema = schema_for(dataset_id)
    if schema == 'public':
        return
    previous_path = c.exec_driver_sql('SHOW search_path').scalar_one()
    c.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    c.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", pg_catalog')
    for table in CORE_TABLES:
        c.exec_driver_sql(f'CREATE TABLE "{schema}"."{table}" (LIKE public."{table}" INCLUDING ALL EXCLUDING CONSTRAINTS)')
    constraints = c.execute(text('''SELECT t.relname,k.conname,pg_get_constraintdef(k.oid) AS definition
        FROM pg_constraint k JOIN pg_class t ON t.oid=k.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname='public' AND t.relname=ANY(:tables) AND k.contype IN ('c','f') ORDER BY t.relname,k.conname'''),
        {'tables': list(CORE_TABLES)}).mappings().all()
    for row in constraints:
        if row['conname'] in {f'ck_{table}_dataset_scope' for table in ROOT_TABLES}:
            continue
        definition = row['definition'].replace('public.', f'"{schema}".').replace(f'"{schema}".dataset', 'public.dataset')
        name = row['conname'].replace('"', '""')
        c.exec_driver_sql(f'ALTER TABLE "{schema}"."{row["relname"]}" ADD CONSTRAINT "{name}" {definition}')
    for table in ROOT_TABLES:
        c.exec_driver_sql(f'ALTER TABLE "{schema}"."{table}" ALTER COLUMN dataset_id SET DEFAULT \'{dataset_id}\'')
        c.exec_driver_sql(f'ALTER TABLE "{schema}"."{table}" ADD CONSTRAINT ck_{table}_dataset_scope CHECK(dataset_id=\'{dataset_id}\')')
    functions = c.execute(text('''SELECT p.proname,pg_get_functiondef(p.oid) AS definition FROM pg_proc p
        JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prorettype='trigger'::regtype
        ORDER BY p.proname''')).mappings().all()
    for row in functions:
        c.execute(text(row['definition'].replace('public.', f'"{schema}".')))
        name = row['proname'].replace('"', '""')
        c.exec_driver_sql(f'ALTER FUNCTION "{schema}"."{name}"() SET search_path TO "{schema}",pg_catalog')
    triggers = c.execute(text('''SELECT pg_get_triggerdef(g.oid) AS definition FROM pg_trigger g
        JOIN pg_class t ON t.oid=g.tgrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname='public' AND t.relname=ANY(:tables) AND NOT g.tgisinternal ORDER BY g.tgname'''),
        {'tables': list(CORE_TABLES)}).mappings().all()
    for row in triggers:
        c.exec_driver_sql(row['definition'].replace('public.', f'"{schema}".'))
    view = c.execute(text("SELECT pg_get_viewdef('public.v_forecast_input_monthly_demand'::regclass,true)")).scalar_one()
    c.exec_driver_sql(f'CREATE VIEW "{schema}".v_forecast_input_monthly_demand AS ' + view.replace('public.', f'"{schema}".'))
    c.exec_driver_sql(f'INSERT INTO "{schema}".unit SELECT * FROM public.unit')
    c.execute(text("SELECT set_config('search_path',:path,true)"), {'path': previous_path})
