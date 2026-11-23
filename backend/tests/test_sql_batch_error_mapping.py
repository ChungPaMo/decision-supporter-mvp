"""Verify SQL repository error translation with driver diagnostics, without PostgreSQL I/O."""
from contextlib import contextmanager

from psycopg import errors
from psycopg.pq import DiagnosticField
import pytest
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError

from app.batches.service import BatchService
from app.batches.sql_repository import SqlBatchRepository
from app.datasets import schema_for
from app.errors import ApiError, ErrorCode
from app.ingest.history_repository import SqlTransformationRepository


LEGACY_INDEX = 'uq_batch_live_entity_sha'
DATASET_INDEX = 'import_batch_entity_source_sha256_idx'
DATASET = 'CHUNGPAMO-2027'
DATASET_SCHEMA = schema_for(DATASET)


class FailingTransaction:
    def __init__(self, dataset_id, error):
        self.dataset_id = dataset_id
        self.error = error

    @contextmanager
    def begin(self):
        yield None
        raise self.error


def driver_diagnostics(constraint, *, schema=DATASET_SCHEMA, table='import_batch'):
    return {DiagnosticField.SCHEMA_NAME: schema.encode(), DiagnosticField.TABLE_NAME: table.encode(),
            DiagnosticField.CONSTRAINT_NAME: constraint.encode()}


@pytest.mark.parametrize(('repository', 'dataset_id', 'schema', 'index'), [
    (SqlBatchRepository, 'TISSUE-LEGACY', 'public', LEGACY_INDEX),
    (SqlTransformationRepository, DATASET, DATASET_SCHEMA, DATASET_INDEX),
    (SqlTransformationRepository, 'ANOTHER-SYNTHETIC', schema_for('ANOTHER-SYNTHETIC'), DATASET_INDEX),
])
def test_live_batch_hash_collision_maps_to_duplicate_upload(repository, dataset_id, schema, index):
    original = errors.UniqueViolation('Localized driver message without an index name',
                                      info=driver_diagnostics(index, schema=schema))
    service = BatchService(repository(FailingTransaction(dataset_id, IntegrityError(None, None, original))))

    with pytest.raises(ApiError) as error, service._tx():
        pass

    assert (error.value.status, error.value.code) == (409, ErrorCode.DUPLICATE_UPLOAD)


@pytest.mark.parametrize(('sqlalchemy_error', 'driver_error', 'diagnostics', 'expected'), [
    (IntegrityError, errors.UniqueViolation, driver_diagnostics('import_batch_pkey'),
     (500, ErrorCode.PERSISTENCE_ERROR)),
    (IntegrityError, errors.UniqueViolation, driver_diagnostics(DATASET_INDEX, table='batch_source_file'),
     (500, ErrorCode.PERSISTENCE_ERROR)),
    (IntegrityError, errors.UniqueViolation, driver_diagnostics(LEGACY_INDEX),
     (500, ErrorCode.PERSISTENCE_ERROR)),
    (IntegrityError, errors.UniqueViolation, driver_diagnostics(LEGACY_INDEX, schema='public'),
     (500, ErrorCode.PERSISTENCE_ERROR)),
    (IntegrityError, errors.UniqueViolation, None, (500, ErrorCode.PERSISTENCE_ERROR)),
    (IntegrityError, errors.ForeignKeyViolation, driver_diagnostics(DATASET_INDEX), (500, ErrorCode.PERSISTENCE_ERROR)),
    (IntegrityError, errors.CheckViolation, driver_diagnostics(DATASET_INDEX), (500, ErrorCode.PERSISTENCE_ERROR)),
    (DatabaseError, errors.RaiseException, None, (500, ErrorCode.PERSISTENCE_ERROR)),
    (OperationalError, errors.ConnectionFailure, None, (503, ErrorCode.DB_UNAVAILABLE)),
])
def test_other_sql_failures_keep_existing_api_errors(sqlalchemy_error, driver_error, diagnostics, expected):
    original = driver_error(f'Synthetic message mentions {LEGACY_INDEX}', info=diagnostics)
    service = BatchService(SqlTransformationRepository(
        FailingTransaction(DATASET, sqlalchemy_error(None, None, original))))

    with pytest.raises(ApiError) as error, service._tx():
        pass

    assert (error.value.status, error.value.code) == expected
