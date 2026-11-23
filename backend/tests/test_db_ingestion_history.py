"""Prepared real PostgreSQL tests. Requires the existing authorized, guarded regression fixture.

--no-db skips these without attempting a connection. In-memory tests are not their substitute.
"""
from contextlib import contextmanager
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
import pytest

from app.batches.service import BatchService
from app.batches.repository import RepositoryError
from app.batches.sql_repository import SqlBatchRepository
from app.dataset_schema_v2 import schema_for
from app.errors import ApiError
from app.ingest.history import TransformationService
from app.ingest.history_repository import SqlTransformationRepository, SqlTransformationTx
from app.ingest.transformation import transform
from contracts.interfaces.xlsx import XlsxTableSelection
from tests.test_ingestion_history import sales, policy
from tests.test_xlsx_transformation_history import bounds, selected_workbook


class RollbackEngine:
    def __init__(self, c, dataset_id):
        self.c, self.dataset_id = c, dataset_id
    @contextmanager
    def begin(self):
        previous = self.c.exec_driver_sql('SHOW search_path').scalar_one()
        with self.c.begin_nested():
            self.c.exec_driver_sql(f'SET LOCAL search_path TO "{schema_for(self.dataset_id)}",pg_catalog')
            yield self.c
            self.c.execute(text("SELECT set_config('search_path',:path,true)"), {'path': previous})


def test_postgres_history_sources_replay_approval_and_cross_dataset_isolation(conn):
    # Entire probe lives in conn's rollback-only outer transaction.
    engine = RollbackEngine(conn, 'CHUNGPAMO-2027')
    batches = BatchService(SqlBatchRepository(engine))
    product = batches.create_batch('p.csv', b'product_id,product_name,base_unit\nP1,Synthetic,EA\n',
        entity='product', source_type='SYNTHETIC', source_note='Synthetic ingestion-history probe')
    batches.approve(product.batch_id, approved_by='TEST-REVIEWER', expected_result_digest=product.result_digest)
    svc = TransformationService(SqlTransformationRepository(engine))
    preview = transform(sales(), policy())
    detail, reused = svc.create(sales(), policy(), preview.result_digest, 'Synthetic history probe', 'TEST-REVIEWER')
    assert not reused and detail.batch_status == 'READY_FOR_APPROVAL'
    conn.exec_driver_sql('SET CONSTRAINTS ALL IMMEDIATE')
    # Check the staged evidence now, then restore the production default. Approval first
    # changes status and inserts rows in the same transaction; its count trigger is deferred.
    conn.exec_driver_sql('SET CONSTRAINTS ALL DEFERRED')
    assert svc.get(detail.transformation_id).output_sha256 == detail.output_sha256
    batch = batches.get_batch(detail.batch_id)
    assert batches.list_approved_demand(None, None, None, 100, 0)[1] == 0
    batches.approve(batch.batch_id, approved_by='TEST-REVIEWER', expected_result_digest=batch.result_digest)
    conn.exec_driver_sql('SET CONSTRAINTS ALL IMMEDIATE')
    conn.exec_driver_sql('SET CONSTRAINTS ALL DEFERRED')
    assert svc.get(detail.transformation_id).batch_status == 'APPROVED'
    assert batches.list_approved_demand(None, None, None, 100, 0)[1] == 2
    other = TransformationService(SqlTransformationRepository(RollbackEngine(conn, 'TISSUE-LEGACY')))
    from app.errors import ApiError
    with pytest.raises(ApiError) as exc:
        other.get(detail.transformation_id)
    assert exc.value.status == 404
    for table in ('ingestion_transformation', 'ingestion_transform_source'):
        with pytest.raises(DBAPIError), conn.begin_nested():
            conn.exec_driver_sql(f'UPDATE "{schema_for(engine.dataset_id)}".{table} SET transformation_id=transformation_id')
    assert svc.create(sales(), policy(), preview.result_digest, 'Synthetic repeat', 'TEST-REVIEWER')[1]


def test_postgres_new_dataset_provisions_history_tables_and_local_foreign_keys(conn):
    from app.datasets import DatasetRepository
    from contracts.interfaces.dataset import DatasetCreate
    @contextmanager
    def begin():
        with conn.begin_nested():
            yield conn
    class Engine:
        def connect(self):
            return begin()
        def begin(self):
            return begin()
    dataset = DatasetRepository(Engine()).create(DatasetCreate(dataset_id='HISTORY-PROBE',
        dataset_name='Synthetic history probe', description='Rollback-only test', source_type='SYNTHETIC'))
    assert dataset.dataset_id == 'HISTORY-PROBE'
    schema = schema_for(dataset.dataset_id)
    assert conn.execute(text('SELECT count(*) FROM pg_tables WHERE schemaname=:s AND tablename IN (:a,:b)'),
        {'s': schema, 'a': 'ingestion_transformation', 'b': 'ingestion_transform_source'}).scalar_one() == 2
    refs = conn.execute(text('''SELECT rn.nspname,r.relname FROM pg_constraint k JOIN pg_class t ON t.oid=k.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace JOIN pg_class r ON r.oid=k.confrelid
        JOIN pg_namespace rn ON rn.oid=r.relnamespace WHERE n.nspname=:s AND k.contype='f' '''), {'s': schema}).all()
    assert all(namespace == schema or (namespace == 'public' and table == 'dataset') for namespace, table in refs)


def test_postgres_selected_xlsx_history_replay_approval_and_rollback(conn, monkeypatch):
    engine = RollbackEngine(conn, 'CHUNGPAMO-2027')
    batches = BatchService(SqlBatchRepository(engine))
    history = TransformationService(SqlTransformationRepository(engine))
    product = batches.create_batch('p.csv', b'product_id,product_name,base_unit\nP1,Synthetic,EA\n',
        entity='product', source_type='SYNTHETIC', source_note='Selected XLSX history regression')
    batches.approve(product.batch_id, approved_by='TEST-REVIEWER', expected_result_digest=product.result_digest)
    files = selected_workbook()
    recipe = policy()

    def stage(sheet, end=6):
        selections = {0: XlsxTableSelection.model_validate(bounds(files, sheet=sheet, data_end_row=end))}
        preview = transform(files, recipe, selections=selections)
        return history.create(files, recipe, preview.result_digest, 'Selected XLSX probe', 'TEST-REVIEWER', selections=selections)

    first, reused = stage('January', 8)
    assert not reused and first.batch_status == 'READY_FOR_APPROVAL'
    conn.exec_driver_sql('SET CONSTRAINTS ALL IMMEDIATE')
    conn.exec_driver_sql('SET CONSTRAINTS ALL DEFERRED')
    assert stage('January', 8)[0].transformation_id == first.transformation_id
    view = history.get(first.transformation_id)
    assert view.preview.sources[0].table_selection.sheet == 'January'
    assert view.preview.sources[0].resolved_columns['quantity'] == 5
    assert [item.row for item in view.preview.records[0].source_locations] == [6, 8]
    assert batches.list_approved_demand(None, None, None, 10, 0)[1] == 0
    batch = batches.get_batch(first.batch_id)
    validated = batches.revalidate(batch.batch_id, expected_version=batch.version, column_overrides={}, default_unit=None, sheet=None)
    batches.approve(batch.batch_id, approved_by='TEST-REVIEWER', expected_result_digest=validated.result_digest)
    conn.exec_driver_sql('SET CONSTRAINTS ALL IMMEDIATE')
    conn.exec_driver_sql('SET CONSTRAINTS ALL DEFERRED')
    assert history.get(first.transformation_id).batch_status == 'APPROVED'
    assert batches.list_approved_demand(None, None, None, 10, 0)[1] == 1
    other = TransformationService(SqlTransformationRepository(RollbackEngine(conn, 'TISSUE-LEGACY')))
    with pytest.raises(ApiError) as exc:
        other.get(first.transformation_id)
    assert exc.value.status == 404

    tables = ('import_batch', 'batch_source_file', 'ingestion_transformation', 'ingestion_transform_source', 'monthly_demand')
    schema = schema_for(engine.dataset_id)

    def counts():
        return [conn.exec_driver_sql(f'SELECT count(*) FROM "{schema}".{table}').scalar_one() for table in tables]

    before = counts()
    original_insert = SqlTransformationTx.insert_transformation

    def fail_after_insert(tx, record, inputs):
        original_insert(tx, record, inputs)
        raise RepositoryError('Injected failure after all history inserts')

    with monkeypatch.context() as patch:
        patch.setattr(SqlTransformationTx, 'insert_transformation', fail_after_insert)
        with pytest.raises(ApiError) as exc:
            stage('February')
        assert exc.value.code == 'PERSISTENCE_ERROR'
    assert counts() == before and history.get(first.transformation_id).manifest_digest == first.manifest_digest
    second, reused = stage('February')
    assert not reused and second.input_digest != first.input_digest
    assert second.preview.sources[0].sha256 == first.preview.sources[0].sha256
    conn.exec_driver_sql('SET CONSTRAINTS ALL IMMEDIATE')
