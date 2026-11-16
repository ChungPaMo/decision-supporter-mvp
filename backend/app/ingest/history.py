"""Immutable transformation evidence, staged atomically through the existing batch gate."""
from contextlib import contextmanager
from datetime import datetime, timezone
import csv
import hashlib
import io
from uuid import uuid4

from app.batches.service import BatchService, _check_actor
from app.errors import ApiError, ErrorCode
from app.ingest.parsing import FileError
from app.ingest.profiling import ScopedMaster, master_digest
from app.ingest.transformation import digest, transform_complete
from app.ingest.validation import KnownMaterial, KnownProduct, MasterData
from contracts.interfaces.ingestion import SalesTransformPolicy, TransformReply
from contracts.interfaces.ingestion_history import TransformationDetail

ENGINE_VERSION = 'synthetic-sales-reducer-1.0'


def canonical_csv(result):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(['product_id', 'period', 'demand_qty', 'unit'])
    writer.writerows((r.product_id, r.period, r.demand_qty, r.unit) for r in result.records)
    return stream.getvalue().encode('utf-8')


def reference_snapshot(master):
    if master is None:
        return None
    return {'dataset_id': master.dataset_id,
        'products': {key: row.base_unit for key, row in sorted(master.data.products.items())},
        'materials': {key: row.base_unit for key, row in sorted(master.data.materials.items())}}


def restore_master(snapshot):
    if snapshot is None:
        return None
    return ScopedMaster(snapshot['dataset_id'], MasterData(
        {key: KnownProduct(key, '', unit) for key, unit in snapshot['products'].items()},
        {key: KnownMaterial(key, '', unit) for key, unit in snapshot['materials'].items()}))


class BoundBatchRepository:
    """Share one transaction; the inner BatchService never commits independently."""
    def __init__(self, tx, dataset_id):
        self.tx, self.dataset_id = tx, dataset_id

    @contextmanager
    def transaction(self):
        yield self.tx


class TransformationService:
    def __init__(self, repo):
        self.repo = repo

    @contextmanager
    def _tx(self):
        # Use the same sanitized repository error contract as existing batch endpoints.
        with BatchService(self.repo)._tx() as tx:
            yield tx

    def create(self, files, policy, expected_result_digest, source_note, created_by, use_approved_master=False):
        actor = _check_actor(created_by, '변환 검토자')
        if not source_note or not source_note.strip() or len(source_note) > 1000:
            raise ApiError(422, ErrorCode.SOURCE_NOTE_REQUIRED, 'Bounded synthetic source description is required.')
        if policy.dataset_id != self.repo.dataset_id:
            raise ApiError(409, ErrorCode.DATASET_MISMATCH, 'Policy and selected dataset disagree.')
        if not policy.user_confirmed:
            raise ApiError(409, ErrorCode.TRANSFORM_BLOCKED, 'Confirm the synthetic transformation policy before staging.')
        if any(not name or len(name) > 200 or '/' in name or '\\' in name
               or any(ord(char) < 32 for char in name) for name, _ in files):
            raise ApiError(422, ErrorCode.REQUEST_INVALID, 'Bounded plain source filenames are required.')
        with self._tx() as tx:
            master = ScopedMaster(self.repo.dataset_id, MasterData(
                {row.product_id: row for row in tx.list_known_products()},
                {row.material_id: row for row in tx.list_known_materials()})) if use_approved_master else None
            try:
                result = transform_complete(files, policy, master)
            except FileError as exc:
                raise ApiError(exc.http_status, ErrorCode(exc.code), exc.message) from None
            if result.result_digest != expected_result_digest:
                raise ApiError(409, ErrorCode.RESULT_CHANGED, 'Source, policy or master changed; review a fresh preview.')
            if result.status != 'TRANSFORMED_PREVIEW' or not result.records:
                raise ApiError(409, ErrorCode.TRANSFORM_BLOCKED, 'Errors or empty demand block transformation staging.')
            # Serialize competing submissions before either inserts its batch.
            tx.lock_input(result.input_digest)
            existing = tx.find_transformation(result.input_digest)
            if existing is not None:
                verify_evidence(existing, tx.transformation_sources(existing['transformation_id']))
                return self._detail(tx, existing), True
            output = canonical_csv(result)
            transformation_id = uuid4()
            batch = BatchService(BoundBatchRepository(tx, self.repo.dataset_id)).create_batch(
                'transformed_monthly_demand.csv', output, entity='monthly_demand', source_type='SYNTHETIC',
                source_note=source_note.strip(), created_by=actor)
            manifest = {'contract_version': 'ingestion-history-0.1', 'engine_version': ENGINE_VERSION,
                'transformation_id': str(transformation_id), 'dataset_id': self.repo.dataset_id,
                'batch_id': str(batch.batch_id), 'created_by': actor, 'source_note': source_note.strip(),
                'output_sha256': hashlib.sha256(output).hexdigest(), 'master_snapshot': reference_snapshot(master),
                'result': result.model_dump(mode='json')}
            record = {'transformation_id': transformation_id, 'dataset_id': self.repo.dataset_id,
                'batch_id': batch.batch_id, 'created_at': datetime.now(timezone.utc),
                'input_digest': result.input_digest, 'result_digest': result.result_digest,
                'policy_digest': result.policy_digest, 'output_sha256': manifest['output_sha256'],
                'manifest_digest': digest(manifest), 'manifest': manifest}
            tx.insert_transformation(record, files)
            return self._detail(tx, record), False

    def get(self, transformation_id, offset=0, limit=500):
        with self._tx() as tx:
            record = tx.get_transformation(transformation_id)
            if record is None:
                raise ApiError(404, ErrorCode.TRANSFORM_NOT_FOUND, 'Transformation not found in the selected dataset.')
            verify_evidence(record, tx.transformation_sources(transformation_id))
            return self._detail(tx, record, offset, limit)

    def list(self, limit=50, offset=0):
        with self._tx() as tx:
            records, total = tx.list_transformations(limit, offset)
            # Lists carry metadata only, never the full record snapshots/raw bytes.
            return {'items': records, 'total': total, 'limit': limit, 'offset': offset}

    @staticmethod
    def _detail(tx, record, offset=0, limit=500):
        if digest(record['manifest']) != record['manifest_digest']:
            raise ApiError(500, ErrorCode.PERSISTENCE_ERROR, 'Transformation manifest digest mismatch.')
        result = TransformReply.model_validate(record['manifest']['result'])
        preview = result.model_copy(update={'offset': offset, 'limit': limit,
            'records': result.records[offset:offset + limit], 'returns': result.returns[offset:offset + limit]})
        batch = tx.get_batch(record['batch_id'])
        if batch is None or batch.dataset_id != record['dataset_id'] or batch.source_sha256 != record['output_sha256']:
            raise ApiError(500, ErrorCode.PERSISTENCE_ERROR, 'Transformation batch evidence is inconsistent.')
        return TransformationDetail(**{k: v for k, v in record.items() if k != 'manifest'},
            created_by=record['manifest']['created_by'], engine_version=record['manifest']['engine_version'],
            batch_status=batch.status, preview=preview)


def verify_evidence(record, files):
    """Verify immutable stored bytes and every complete result, independent of response pages."""
    try:
        manifest = record['manifest']
        require(manifest['engine_version'] == ENGINE_VERSION)
        require(manifest['contract_version'] == 'ingestion-history-0.1')
        result = TransformReply.model_validate(manifest['result'])
        require(digest(manifest) == record['manifest_digest'])
        require(manifest['dataset_id'] == result.dataset_id == record['dataset_id'])
        require(manifest['batch_id'] == str(record['batch_id']))
        require(manifest['transformation_id'] == str(record['transformation_id']))
        require(result.policy_digest == record['policy_digest'])
        require(result.input_digest == record['input_digest'] and result.result_digest == record['result_digest'])
        require(result.total == len(result.records) and result.returns_total == len(result.returns))
        require(len(files) == len(result.sources))
        for index, ((name, content), source) in enumerate(zip(files, result.sources)):
            require(source.source_index == index and source.filename == name)
            require(hashlib.sha256(content).hexdigest() == source.sha256)
        output = canonical_csv(result)
        require(hashlib.sha256(output).hexdigest() == manifest['output_sha256'] == record['output_sha256'])
        master = restore_master(manifest['master_snapshot'])
        require(master_digest(master) == result.master_digest)
        # Recompute using the preserved reference snapshot, never today's mutable master.
        replay = transform_complete(files, SalesTransformPolicy.model_validate(result.policy), master)
        require(replay.model_dump() == result.model_dump())
    except (KeyError, ValueError, TypeError, AttributeError, FileError):
        raise ApiError(500, ErrorCode.PERSISTENCE_ERROR, 'Stored transformation integrity verification failed.') from None


def require(condition):
    if not condition:
        raise ValueError('Invalid evidence')
