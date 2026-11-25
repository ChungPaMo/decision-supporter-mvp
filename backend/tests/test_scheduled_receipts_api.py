"""Exercise the HTTP and reader contracts with a scoped SQL connection double."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy.exc import OperationalError, ProgrammingError, TimeoutError

from app.api import scheduled_receipts
from app.batches import receipt_reader
from app.errors import ApiError, ErrorCode
from app.main import app
from contracts.interfaces.receipts import ReceiptLedgerPage


PATH = '/scheduled-receipts'
DATASET = 'CHUNGPAMO-2027'
LEGACY = 'TISSUE-LEGACY'
BASE_QUERY = {'dataset_id': DATASET, 'as_of_date': '2027-01-05'}


def row(po_id, revision=1, *, dataset_id=DATASET, effective=1, received='0.000000',
        status='OPEN', material_id='MR-N3', batch_status='APPROVED', source_sheet='CSV'):
    return dict(
        dataset_id=dataset_id, receipt_key=po_id, po_id=po_id, po_line_id=None, revision=revision,
        material_id=material_id, unit='KG', ordered_qty='99999999999999.999999', received_qty=received,
        ledger_status=status, expected_date=date(2027, 5, 1), effective_date=date(2027, 1, effective),
        batch_status=batch_status, batch_id=UUID(int=revision), filename='synthetic-receipts.csv',
        source_sha256='a' * 64, result_digest='b' * 64, approved_at=datetime(2027, 1, 8, tzinfo=timezone.utc),
        source_sheet=source_sheet, source_row_no=revision + 1, source_row_sha256='c' * 64,
    )


class SqlSnapshot:
    """Assert SQL structure and binds, then simulate the result in the selected scope."""

    def __init__(self, dataset_id, rows, revision, present):
        self.dataset_id = dataset_id
        self.rows = rows
        self.revision = revision
        self.present = present
        self.calls = []
        self.failure = None
        self.closed = False

    def connect(self):
        return self

    @contextmanager
    def execution_options(self, *, isolation_level):
        assert isolation_level == 'REPEATABLE READ'
        try:
            yield self
        finally:
            self.closed = True

    def execute(self, statement, params=None):
        sql = ' '.join(str(statement).split())
        self.calls.append(sql)
        assert self.calls[0] == 'SET TRANSACTION READ ONLY'
        if sql == 'SET TRANSACTION READ ONLY':
            return None
        if 'to_regclass' in sql:
            return SimpleNamespace(scalar_one=lambda: self.present)
        if 'public.alembic_version' in sql:
            return SimpleNamespace(scalar_one=lambda: self.revision)
        if self.failure:
            raise self.failure

        latest, after_latest = sql.split('), with_state AS (')
        assert 'SELECT DISTINCT ON (r.receipt_key)' in latest
        assert 'b.dataset_id = r.dataset_id' in latest and 'WHERE r.dataset_id = :dataset_id' in latest
        assert "b.entity = 'scheduled_receipt' AND b.status = 'APPROVED' AND b.blocking_error_count = 0" in latest
        assert 'b.approved_at IS NOT NULL AND b.result_digest IS NOT NULL' in latest
        assert 'r.effective_date <= :as_of ORDER BY r.receipt_key, r.revision DESC' in latest
        assert "WHEN ledger_status = 'CANCELLED' THEN 'CANCELLED'" in after_latest
        assert "WHEN received_qty = ordered_qty THEN 'COMPLETED'" in after_latest
        assert "WHEN received_qty > 0 THEN 'PARTIALLY_RECEIVED'" in after_latest
        for key in ('po_id', 'material_id', 'state'):
            assert f':{key}' not in latest and f'{key} = :{key}' in after_latest
        assert params['dataset_id'] == self.dataset_id
        assert isinstance(params['as_of'], date)

        current = {}
        for record in sorted(self.rows, key=lambda item: item['revision']):
            if (record['dataset_id'] == self.dataset_id and record['batch_status'] == 'APPROVED'
                    and record['effective_date'] <= params['as_of']):
                current[record['receipt_key']] = record
        filtered = []
        for key in sorted(current):
            item = current[key].copy()
            item.pop('batch_status')
            ordered, received = Decimal(item['ordered_qty']), Decimal(item['received_qty'])
            state = 'CANCELLED' if item['ledger_status'] == 'CANCELLED' else (
                'COMPLETED' if received == ordered else 'PARTIALLY_RECEIVED' if received else 'OPEN'
            )
            item['state'] = state
            item['open_qty'] = '0' if state in ('CANCELLED', 'COMPLETED') else format(ordered - received, 'f')
            if all(params[k] is None or item[k] == params[k] for k in ('po_id', 'material_id', 'state')):
                filtered.append(item)
        if sql.endswith('SELECT count(*) FROM filtered'):
            assert 'limit' not in params and 'offset' not in params
            return SimpleNamespace(scalar_one=lambda: len(filtered))
        assert sql.endswith('FROM filtered ORDER BY receipt_key LIMIT :limit OFFSET :offset')
        assert "THEN '0' ELSE (ordered_qty - received_qty)::text END AS open_qty" in sql
        return SimpleNamespace(mappings=lambda: filtered[params['offset']:params['offset'] + params['limit']])


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setattr(scheduled_receipts, 'get_settings', lambda: SimpleNamespace(persistence='postgres'))
    snapshots = []

    def setup(rows=(), *, revision='0010', present=True):
        def resolve(dataset_id):
            snapshot = SqlSnapshot(dataset_id, rows, revision, present)
            snapshots.append(snapshot)
            return snapshot

        monkeypatch.setattr(receipt_reader, 'get_dataset_engine', resolve)

    with TestClient(app) as client:
        yield client, setup, snapshots


def get(client, **query):
    response = client.get(PATH, params=BASE_QUERY | query)
    assert response.status_code == 200, response.json()
    TypeAdapter(ReceiptLedgerPage).validate_python(response.json())
    return response.json()


def test_inclusive_date_latest_approved_revision_and_source(http):
    client, setup, snapshots = http
    setup([
        row('PO-A', 1), row('PO-A', 2, effective=5, received='0.000001', source_sheet='입고'),
        row('PO-A', 3, effective=5, batch_status='READY_FOR_APPROVAL'),
        row('PO-A', 4, effective=6, status='CANCELLED'),
        row('PO-FUTURE', effective=6), row('PO-UNAPPROVED', batch_status='REJECTED'),
    ])
    result = get(client, state='PARTIALLY_RECEIVED', po_id='PO-A', material_id='MR-N3')
    assert result['total'] == 1 and result['source_state'] == 'AVAILABLE'
    item, = result['items']
    assert item['revision'] == 2 and item['effective_date'] == '2027-01-05'
    assert item['open_qty'] == '99999999999999.999998'
    assert item['state'] == 'PARTIALLY_RECEIVED' and item['ledger_status'] == 'OPEN'
    assert item['source'] == {
        'batch_id': str(UUID(int=2)), 'filename': 'synthetic-receipts.csv',
        'source_sha256': 'a' * 64, 'result_digest': 'b' * 64, 'approved_at': '2027-01-08T00:00:00Z',
        'source_sheet': '입고', 'source_row_no': 3, 'source_row_sha256': 'c' * 64,
    }
    assert snapshots[-1].closed and len(snapshots[-1].calls) == 5
    assert [i['receipt_key'] for i in get(client)['items']] == ['PO-A']
    assert get(client, as_of_date='2027-01-04')['items'][0]['revision'] == 1


def test_latest_revision_precedes_state_filters_and_terminal_balances(http):
    client, setup, _ = http
    setup([
        row('PO-C'), row('PO-C', 2, received='2.000000', status='CANCELLED'),
        row('PO-D', received='99999999999999.999999'), row('PO-O'),
    ])
    assert [i['po_id'] for i in get(client, state='OPEN')['items']] == ['PO-O']
    for state, po_id, ledger_status in [('CANCELLED', 'PO-C', 'CANCELLED'), ('COMPLETED', 'PO-D', 'OPEN')]:
        item, = get(client, state=state)['items']
        assert (item['po_id'], item['ledger_status'], item['open_qty']) == (po_id, ledger_status, '0')
    assert get(client, po_id='PO-C', state='OPEN')['total'] == 0
    assert get(client, material_id='MR-OTHER')['items'] == []


def test_scope_and_stable_pagination(http):
    client, setup, snapshots = http
    line = row('PO-A') | {'receipt_key': 'PO-A--01', 'po_line_id': '01'}
    setup([row('PO-C'), line, row('PO-B'), row('PO-B', 2, dataset_id=LEGACY)])
    page = get(client, limit=1, offset=0)
    assert page['total'] == 3 and page['limit'] == 1 and page['offset'] == 0
    assert page['items'][0]['receipt_key'] == 'PO-A--01' and page['items'][0]['po_line_id'] == '01'
    assert get(client, limit=1, offset=1)['items'][0]['revision'] == 1
    beyond = get(client, limit=1, offset=9)
    assert beyond['items'] == [] and beyond['total'] == 3
    assert len(snapshots[-1].calls) == 4  # Only the count query is needed beyond the last row.
    legacy = client.get(PATH, params={'as_of_date': BASE_QUERY['as_of_date']}).json()
    assert legacy['dataset_id'] == LEGACY and legacy['total'] == 1 and legacy['items'][0]['revision'] == 2
    assert [connection.dataset_id for connection in snapshots] == [DATASET, DATASET, DATASET, LEGACY]


def test_empty_and_unavailable(http):
    client, setup, snapshots = http
    setup()
    assert get(client) == dict(BASE_QUERY, source_state='AVAILABLE', reason_code=None,
                               items=[], total=0, limit=50, offset=0)
    setup(revision='0009', present=False)
    assert get(client) == dict(BASE_QUERY, source_state='UNAVAILABLE', reason_code='RECEIPT_SOURCE_UNAVAILABLE',
                               items=None, total=None, limit=50, offset=0)
    assert len(snapshots[-1].calls) == 3


@pytest.mark.parametrize('query', [
    {}, {'as_of_date': '2027-02-30'}, {'state': 'DONE'}, {'limit': 101}, {'offset': -1},
    {'po_id': '!'}, {'dataset_id': 'unknown-lowercase'},
])
def test_invalid_query_is_rejected_before_storage(http, monkeypatch, query):
    client, _, _ = http
    read = Mock()
    monkeypatch.setattr(scheduled_receipts, 'read_receipt_page', read)
    params = BASE_QUERY | query if query else {}
    response = client.get(PATH, params=params)
    assert response.status_code == 422
    read.assert_not_called()


def test_persistence_disabled_skips_storage(monkeypatch):
    monkeypatch.setattr(scheduled_receipts, 'get_settings', lambda: SimpleNamespace(persistence='disabled'))
    read = Mock()
    monkeypatch.setattr(scheduled_receipts, 'read_receipt_page', read)
    with TestClient(app) as client:
        response = client.get(PATH, params=BASE_QUERY)
    assert response.status_code == 501 and response.json()['detail']['code'] == 'PERSISTENCE_DISABLED'
    read.assert_not_called()


@pytest.mark.parametrize('failure, status, code', [
    (OperationalError('SELECT', {}, OSError('private-driver-detail')), 503, ErrorCode.DB_UNAVAILABLE),
    (TimeoutError('private-driver-detail'), 503, ErrorCode.DB_UNAVAILABLE),
    (ProgrammingError('SELECT', {}, ValueError('private-driver-detail')), 500, ErrorCode.PERSISTENCE_ERROR),
    (ApiError(404, ErrorCode.DATASET_NOT_FOUND, 'Dataset not found'), 404, ErrorCode.DATASET_NOT_FOUND),
    (ApiError(409, ErrorCode.DATASET_INACTIVE, 'Dataset inactive'), 409, ErrorCode.DATASET_INACTIVE),
])
def test_storage_failures_are_not_empty_pages(http, monkeypatch, failure, status, code):
    client, _, _ = http
    connection = SqlSnapshot(DATASET, [], '0010', True)
    connection.failure = failure
    resolve = Mock(return_value=connection) if isinstance(failure, ProgrammingError) else Mock(side_effect=failure)
    monkeypatch.setattr(receipt_reader, 'get_dataset_engine', resolve)
    response = client.get(PATH, params=BASE_QUERY)
    assert response.status_code == status and response.json()['detail']['code'] == code
    assert 'private-driver-detail' not in response.text and 'items' not in response.json()
    resolve.assert_called_once_with(DATASET)


def test_mismatched_schema_is_not_unavailable(http):
    client, setup, _ = http
    setup(revision='0010', present=False)
    response = client.get(PATH, params=BASE_QUERY)
    assert response.status_code == 500 and response.json()['detail']['code'] == 'PERSISTENCE_ERROR'


def test_openapi_describes_the_query_and_discriminated_response(http):
    client, _, _ = http
    operation = client.get('/openapi.json').json()['paths'][PATH]['get']
    params = {parameter['name']: parameter for parameter in operation['parameters']}
    assert set(params) == {'dataset_id', 'as_of_date', 'limit', 'offset', 'po_id', 'material_id', 'state'}
    assert params['as_of_date']['required'] and params['as_of_date']['schema']['format'] == 'date'
    assert params['dataset_id']['schema']['default'] == LEGACY
    responses = operation['responses']
    schema = responses['200']['content']['application/json']['schema']
    assert schema['discriminator']['propertyName'] == 'source_state'
    assert set(schema['discriminator']['mapping']) == {'AVAILABLE', 'UNAVAILABLE'}
    assert set(responses) == {'200', '404', '409', '422', '500', '501', '503'}
