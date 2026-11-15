"""Frozen schema provisioning v1 for Alembic 0008 and dataset creation.
Do not change v1 after release; use a new version/migration for schema evolution.
"""
import hashlib
import re
from sqlalchemy import text

CORE_TABLES=('unit','import_batch','batch_source_file','product','material','monthly_demand','sales_order','bom_header','bom_line',
    'inventory','production_capacity','demand_forecast','forecast_run','forecast_run_input','production_resource','production_quantity_limit',
    'production_hours_budget','production_routing','production_routing_step','production_routing_resource_requirement',
    'plan_execution','plan_candidate','plan_constraint_evaluation','plan_material_requirement','plan_execution_input','plan_review','plan_decision')
ROOT_TABLES=('import_batch','forecast_run','plan_execution')


def schema_for(value):
    if not re.fullmatch(r'[A-Z][A-Z0-9_-]{0,39}',value):raise ValueError('Invalid dataset identifier')
    return 'public' if value=='TISSUE-LEGACY' else 'ds_'+hashlib.sha256(value.encode()).hexdigest()[:32]


def provision_schema(c,dataset_id):
    """Clone structure, local FK/functions/triggers/views, and units only. Never copy business rows.
    All object identifiers are server-generated or from the fixed migration-owned allowlist.
    This is additive DDL; no DROP/TRUNCATE and no legacy row UPDATE.
    """
    schema=schema_for(dataset_id)
    if schema=='public':return
    previous_path=c.exec_driver_sql('SHOW search_path').scalar_one()
    c.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    c.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", pg_catalog')
    for table in CORE_TABLES:
        c.exec_driver_sql(f'CREATE TABLE "{schema}"."{table}" (LIKE public."{table}" INCLUDING ALL EXCLUDING CONSTRAINTS)')
    # CHECKs and FKs are explicitly re-bound to the local schema; unique/index/exclusion/identity are copied by LIKE.
    constraints=c.execute(text("""SELECT t.relname,k.conname,pg_get_constraintdef(k.oid) AS definition
      FROM pg_constraint k JOIN pg_class t ON t.oid=k.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
      WHERE n.nspname='public' AND t.relname=ANY(:tables) AND k.contype IN ('c','f') ORDER BY t.relname,k.conname"""),{'tables':list(CORE_TABLES)}).mappings().all()
    for row in constraints:
        if row['conname'] in {f'ck_{table}_dataset_scope' for table in ROOT_TABLES}:continue
        definition=row['definition'].replace('public.',f'"{schema}".').replace(f'"{schema}".dataset','public.dataset')
        name=row['conname'].replace('"','""')
        c.exec_driver_sql(f'ALTER TABLE "{schema}"."{row["relname"]}" ADD CONSTRAINT "{name}" {definition}')
    for table in ROOT_TABLES:
        c.exec_driver_sql(f'ALTER TABLE "{schema}"."{table}" ALTER COLUMN dataset_id SET DEFAULT \'{dataset_id}\'')
        c.exec_driver_sql(f'ALTER TABLE "{schema}"."{table}" ADD CONSTRAINT ck_{table}_dataset_scope CHECK (dataset_id=\'{dataset_id}\')')
    functions=c.execute(text("""SELECT p.proname,pg_get_functiondef(p.oid) AS definition FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.prorettype='trigger'::regtype ORDER BY p.proname""")).mappings().all()
    for row in functions:
        c.execute(text(row['definition'].replace('public.',f'"{schema}".')))
        name=row['proname'].replace('"','""')
        c.exec_driver_sql(f'ALTER FUNCTION "{schema}"."{name}"() SET search_path TO "{schema}",pg_catalog')
    triggers=c.execute(text("""SELECT pg_get_triggerdef(g.oid) AS definition FROM pg_trigger g JOIN pg_class t ON t.oid=g.tgrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='public' AND t.relname=ANY(:tables) AND NOT g.tgisinternal ORDER BY g.tgname"""),{'tables':list(CORE_TABLES)}).mappings().all()
    for row in triggers:c.exec_driver_sql(row['definition'].replace('public.',f'"{schema}".'))
    view=c.execute(text("SELECT pg_get_viewdef('public.v_forecast_input_monthly_demand'::regclass,true)")).scalar_one()
    c.exec_driver_sql(f'CREATE VIEW "{schema}".v_forecast_input_monthly_demand AS '+view.replace('public.',f'"{schema}".'))
    c.exec_driver_sql(f'INSERT INTO "{schema}".unit SELECT * FROM public.unit')
    c.execute(text("SELECT set_config('search_path',:path,true)"),{'path':previous_path})
