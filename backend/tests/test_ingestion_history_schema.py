"""No database connections: migration scope and provisioning order checks."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.dataset_schema_v2 import CORE_TABLES, ROOT_TABLES, history_ddl, provision_schema, schema_for


def test_online_migration_includes_archived_datasets_without_touching_business_rows():
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/0009_ingestion_history.py'
    spec = importlib.util.spec_from_file_location('history_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    c = Mock()
    c.execute.return_value.mappings.return_value.all.return_value = [
        {'dataset_id': dataset, 'schema_name': schema_for(dataset)} for dataset in ('TISSUE-LEGACY', 'CHUNGPAMO-2027', 'ARCHIVED-DEMO')]
    module.op = SimpleNamespace(get_context=lambda: SimpleNamespace(as_sql=False), get_bind=lambda: c)
    module.upgrade()
    statements = [str(call.args[0]) for call in c.execute.call_args_list]
    assert 'status' not in statements[1]  # Archived schemas must also evolve.
    ddl = statements[2:]
    assert len(ddl) == 3 and all('CREATE TABLE' in sql for sql in ddl)
    assert all('DROP ' not in sql and 'TRUNCATE ' not in sql and 'UPDATE import_batch SET' not in sql for sql in statements)
    assert 'DEFAULT \'ARCHIVED-DEMO\'' in ddl[-1]
    with pytest.raises(RuntimeError):
        module.downgrade()


def test_schema_checks_hash_sources_and_keeps_batch_and_manifest_immutable():
    sql = history_ddl('CHUNGPAMO-2027')
    assert '__SCHEMA__' not in sql and '__DATASET__' not in sql
    assert f'REFERENCES "{schema_for("CHUNGPAMO-2027")}".import_batch' in sql
    assert "sha256 = encode(sha256(content), 'hex')" in sql
    assert 'DEFERRABLE INITIALLY DEFERRED' in sql and 'source manifest mismatch' in sql
    assert 'trg_ingestion_batch_settings' in sql and "NEW.column_overrides<>'{}'::jsonb" in sql
    assert 'forbid_change()' in sql and 'public.dataset' in sql
    with pytest.raises(ValueError):
        history_ddl("BAD';DROP SCHEMA public")


def test_new_dataset_clones_all_tables_before_compiling_history_trigger_functions():
    class Connection:
        def __init__(self):
            self.statements = []
        def exec_driver_sql(self, sql):
            self.statements.append(sql)
            return SimpleNamespace(scalar_one=lambda: 'public')
        def execute(self, sql, params=None):
            self.statements.append(str(sql))
            functions = [{'proname': 'ingestion_evidence_guard', 'definition': 'CREATE FUNCTION public.ingestion_evidence_guard() RETURNS trigger AS $$ BEGIN RETURN NEW; END $$ LANGUAGE plpgsql'}]
            rows = functions if 'pg_get_functiondef' in str(sql) else []
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows), scalar_one=lambda: 'SELECT 1')
    c = Connection()
    provision_schema(c, 'NEW-SYNTHETIC')
    creates = [i for i, sql in enumerate(c.statements) if 'CREATE TABLE' in sql]
    functions = [i for i, sql in enumerate(c.statements) if sql.startswith('CREATE FUNCTION')]
    assert len(creates) == len(CORE_TABLES) and max(creates) < min(functions)
    assert 'ingestion_transformation' in ROOT_TABLES
    assert 'set_config' in c.statements[-1]
