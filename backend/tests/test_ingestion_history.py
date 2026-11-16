"""Service and HTTP regression with a test-only transactional repository, never PostgreSQL evidence."""
import copy
from contextlib import contextmanager
import hashlib
import json
from uuid import uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from app.api.batches import get_service
from app.api.datasets import dataset_context
from app.api.ingest_history import get_history_service
from app.batches.repository import RepositoryError
from app.batches.service import BatchService
from app.errors import ApiError
from app.ingest.history import TransformationService, verify_evidence
from app.ingest.transformation import digest, transform
from app.main import app
from contracts.interfaces.ingestion import SalesTransformPolicy
from tests.fakes import FakeTx, InMemoryBatchRepository

DATASET = 'CHUNGPAMO-2027'


def sales(count=2):
    rows = ['주문日,製品,数量,単位,状態,取引,行']
    for index in range(count):
        rows.append(f'{2020 + index // 12}-{index % 12 + 1:02}-01,P1,0.1,팩,정상,O{index},1')
    return [('sales.csv', ('\n'.join(rows) + '\n').encode())]


def policy(**changes):
    return SalesTransformPolicy(dataset_id=DATASET, user_confirmed=True, columns={
        'order_date': '주문日', 'product_id': '製品', 'quantity': '数量', 'unit': '単位',
        'status': '状態', 'order_id': '取引', 'line_id': '行'}, **changes)


class HistoryTx(FakeTx):
    def __init__(self, repo):
        super().__init__(repo)
        self.repo = repo

    def lock_input(self, key):
        pass  # Does not model PostgreSQL lock scheduling.

    def find_transformation(self, key):
        return next((row for row in self.repo.state.transformations.values() if row['input_digest'] == key), None)

    def get_transformation(self, id):
        return self.repo.state.transformations.get(id)

    def list_transformations(self, limit, offset):
        rows = list(self.repo.state.transformations.values())
        return [{**{k: v for k, v in record.items() if k != 'manifest'},
            'created_by': record['manifest']['created_by'], 'engine_version': record['manifest']['engine_version'],
            'batch_status': self.get_batch(record['batch_id']).status} for record in rows[offset:offset + limit]], len(rows)

    def transformation_sources(self, id):
        return self.repo.state.transformation_sources[id]

    def transformation_for_batch(self, batch_id):
        row = next((row for row in self.repo.state.transformations.values() if row['batch_id'] == batch_id), None)
        return (row, self.transformation_sources(row['transformation_id'])) if row else None

    def insert_transformation(self, record, files):
        self.repo.state.transformations[record['transformation_id']] = copy.deepcopy(record)
        if self.repo.fail_history:
            raise RepositoryError('private database content')
        self.repo.state.transformation_sources[record['transformation_id']] = list(files)


class HistoryMemoryRepository(InMemoryBatchRepository):
    def __init__(self, dataset_id=DATASET):
        super().__init__(products={'P1': 'Synthetic product'})
        self.dataset_id = dataset_id
        self.state.transformations, self.state.transformation_sources = {}, {}
        self.fail_history = False

    @contextmanager
    def transaction(self):
        with super().transaction():
            yield HistoryTx(self)


@pytest.fixture
def repo():
    return HistoryMemoryRepository()


def stage(repo, count=2, master=False):
    from app.ingest.profiling import ScopedMaster
    from app.ingest.validation import MasterData
    master_data = ScopedMaster(repo.dataset_id, MasterData({row.product_id: row for row in FakeTx(repo).list_known_products()})) if master else None
    preview = transform(sales(count), policy(), master_data)
    return TransformationService(repo).create(sales(count), policy(), preview.result_digest, 'Generated synthetic test', 'TEST-REVIEWER', master)


def test_full_result_over_500_rows_is_stored_and_paged_and_original_bytes_survive(repo):
    detail, reused = stage(repo, count=620)
    assert not reused and detail.persisted and not detail.auto_approve
    assert detail.batch_status == 'READY_FOR_APPROVAL' and len(repo.state.demand) == 0
    assert detail.preview.total == 620 and len(detail.preview.records) == 500
    service = TransformationService(repo)
    assert len(service.get(detail.transformation_id, offset=500).preview.records) == 120
    assert service.get(detail.transformation_id, offset=900).preview.records == []
    stored = repo.state.transformations[detail.transformation_id]
    assert len(stored['manifest']['result']['records']) == 620
    assert repo.state.transformation_sources[detail.transformation_id] == sales(620)
    assert repo.state.files[detail.batch_id].count(b'\n') == 621
    assert hashlib.sha256(repo.state.files[detail.batch_id]).hexdigest() == detail.output_sha256
    metadata = service.list()['items'][0]
    assert 'preview' not in metadata and 'content' not in json.dumps(metadata, default=str)


def test_existing_approval_gate_and_immutable_evidence_link(repo):
    detail, _ = stage(repo)
    snapshot = copy.deepcopy(repo.state.transformations)
    svc = BatchService(repo)
    batch = svc.get_batch(detail.batch_id)
    with pytest.raises(ApiError) as e:
        svc.approve(batch.batch_id, approved_by='TEST-REVIEWER', expected_result_digest=detail.result_digest)
    assert e.value.code == 'RESULT_CHANGED' and not repo.state.demand
    svc.approve(batch.batch_id, approved_by='TEST-REVIEWER', expected_result_digest=batch.result_digest)
    assert len(repo.state.demand) == 2
    assert TransformationService(repo).get(detail.transformation_id).batch_status == 'APPROVED'
    assert repo.state.transformations == snapshot
    with pytest.raises(ApiError):
        svc.approve(batch.batch_id, approved_by='TEST-REVIEWER', expected_result_digest=batch.result_digest)


def test_multiple_sources_preserve_cancelled_and_separate_returns_without_netting(repo):
    files = sales(1)
    second = '주문日,製品,数量,単位,状態,取引,行\n2020-01-01,P1,9,팩,취소,C1,1\n2020-01-01,P1,-2,팩,반품,R1,1\n'
    files.append(('other.csv', second.encode()))
    preview = transform(files, policy())
    detail, _ = TransformationService(repo).create(files, policy(), preview.result_digest, 'Synthetic partition probe', 'TEST-REVIEWER')
    restored = TransformationService(repo).get(detail.transformation_id)
    assert len(restored.preview.sources) == 2
    assert restored.preview.counts['cancelled_excluded'] == restored.preview.counts['returns_separate'] == 1
    assert restored.preview.records[0].demand_qty == '0.1'
    assert restored.preview.returns[0].return_qty == '2'
    assert repo.state.files[detail.batch_id].splitlines()[-1] == b'P1,2020-01,0.1,EA'


def test_transaction_failure_rolls_back_batch_source_history_and_no_secret_leaks(repo):
    repo.fail_history = True
    with pytest.raises(ApiError) as e:
        stage(repo)
    assert e.value.code == 'PERSISTENCE_ERROR'
    assert 'private' not in str(e.value.body())
    assert not repo.state.batches and not repo.state.files and not repo.state.transformations


def test_repeated_input_is_idempotent_and_preserves_first_review_identity(repo):
    a, reused_a = stage(repo)
    b, reused_b = stage(repo)
    assert not reused_a and reused_b and a.transformation_id == b.transformation_id
    assert len(repo.state.batches) == len(repo.state.transformations) == 1


@pytest.mark.parametrize('kind', ['unconfirmed', 'wrong_digest', 'bad_rows', 'empty_normal', 'cross_dataset'])
def test_rejected_staging_never_writes(repo, kind):
    files, recipe = sales(), policy()
    if kind == 'unconfirmed':
        recipe = recipe.model_copy(update={'user_confirmed': False})
    if kind == 'cross_dataset':
        recipe = recipe.model_copy(update={'dataset_id': 'TISSUE-LEGACY'})
    if kind in ('bad_rows', 'empty_normal'):
        files = [(name, content.replace('정상'.encode(), ('알수없음' if kind == 'bad_rows' else '취소').encode())) for name, content in files]
    expected = '0' * 64 if kind == 'wrong_digest' else transform(files, recipe).result_digest
    with pytest.raises(ApiError):
        TransformationService(repo).create(files, recipe, expected, 'Synthetic test', 'TEST-REVIEWER')
    assert not repo.state.batches and not repo.state.transformations


@pytest.mark.parametrize('tamper', ['source', 'manifest', 'result_with_new_manifest_hash', 'batch_bytes'])
def test_evidence_tampering_blocks_read_or_approval(repo, tamper):
    detail, _ = stage(repo)
    record = repo.state.transformations[detail.transformation_id]
    if tamper == 'source':
        repo.state.transformation_sources[detail.transformation_id] = [('sales.csv', b'corrupted')]
    elif tamper == 'manifest':
        record['manifest']['result']['records'][0]['demand_qty'] = '900'
    elif tamper == 'result_with_new_manifest_hash':
        record['manifest']['result']['records'][0]['demand_qty'] = '900'
        record['manifest_digest'] = digest(record['manifest'])
    else:
        repo.state.files[detail.batch_id] = b'wrong bytes'
    with pytest.raises(ApiError):
        batch = BatchService(repo).get_batch(detail.batch_id)
        BatchService(repo).approve(batch.batch_id, approved_by='TEST-REVIEWER', expected_result_digest=batch.result_digest)
    assert not repo.state.demand


def test_preserved_master_snapshot_replays_after_current_master_changes(repo):
    detail, _ = stage(repo, master=True)
    repo.state.products.clear()
    assert TransformationService(repo).get(detail.transformation_id).preview.master_digest
    batch = BatchService(repo).get_batch(detail.batch_id)
    with pytest.raises(ApiError):
        BatchService(repo).approve(batch.batch_id, approved_by='TEST-REVIEWER', expected_result_digest=batch.result_digest)
    assert not repo.state.demand


def test_linked_batch_cannot_reinterpret_columns_but_same_settings_can_revalidate(repo):
    detail, _ = stage(repo)
    svc = BatchService(repo)
    batch = svc.get_batch(detail.batch_id)
    with pytest.raises(ApiError) as e:
        svc.revalidate(batch.batch_id, expected_version=batch.version,
                       column_overrides={'product_id': 'B'}, default_unit=None, sheet=None)
    assert e.value.code == 'TRANSFORM_BLOCKED'
    updated = svc.revalidate(batch.batch_id, expected_version=batch.version, column_overrides={}, default_unit=None, sheet=None)
    assert updated.version == batch.version + 1


def test_api_disabled_persistence_is_not_faked():
    client = TestClient(app)
    assert client.get('/ingest/transformations').status_code == 501
    assert client.get('/ingest/transformations/' + str(uuid4())).status_code == 501
    assert client.post('/ingest/transformations', files=[('files', sales()[0])], data={
        'policy': policy().model_dump_json(), 'expected_result_digest': '0' * 64,
        'created_by': 'TEST-REVIEWER', 'source_note': 'Synthetic'}).status_code == 501


def test_http_dataset_isolation_and_preview_digest_then_explicit_batch_approval():
    repositories = {DATASET: HistoryMemoryRepository(), 'TISSUE-LEGACY': HistoryMemoryRepository('TISSUE-LEGACY')}
    def history(dataset_id: str = Depends(dataset_context)):
        return TransformationService(repositories[dataset_id])
    def batches(dataset_id: str = Depends(dataset_context)):
        return BatchService(repositories[dataset_id])
    app.dependency_overrides[get_history_service] = history
    app.dependency_overrides[get_service] = batches
    try:
        client = TestClient(app)
        params = {'dataset_id': DATASET}
        preview = client.post('/ingest/transform-preview', params=params, files=[('files', sales()[0])],
            data={'policy': policy().model_dump_json()}).json()
        data = {'policy': policy().model_dump_json(), 'expected_result_digest': preview['result_digest'],
                'created_by': 'TEST-REVIEWER', 'source_note': 'Synthetic test'}
        response = client.post('/ingest/transformations', params=params, files=[('files', sales()[0])], data=data)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body['persisted'] and not body['preview']['persisted'] and not body['auto_approve']
        assert client.post('/ingest/transformations', params=params, files=[('files', sales()[0])], data=data).status_code == 200
        assert client.get('/ingest/transformations/' + body['transformation_id']).status_code == 404
        assert client.get('/ingest/transformations').json()['total'] == 0
        assert client.get('/ingest/transformations', params=params).json()['total'] == 1
        assert client.get('/ingest/transformations/' + body['transformation_id'], params=params).status_code == 200
        assert client.get('/demand/monthly', params=params).json()['total'] == 0
        batch = client.get('/batches/' + body['batch_id'], params=params).json()
        response = client.post('/batches/' + body['batch_id'] + '/approve', params=params,
            json={'approved_by': 'TEST-REVIEWER', 'expected_result_digest': batch['result_digest']})
        assert response.status_code == 200 and client.get('/demand/monthly', params=params).json()['total'] == 2
        data['policy'] = policy().model_copy(update={'dataset_id': 'TISSUE-LEGACY'}).model_dump_json()
        assert client.post('/ingest/transformations', params=params, files=[('files', sales()[0])], data=data).status_code == 409
    finally:
        app.dependency_overrides.pop(get_history_service, None)
        app.dependency_overrides.pop(get_service, None)
