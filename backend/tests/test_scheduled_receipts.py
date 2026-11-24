from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID

import pytest
from openpyxl import Workbook
from sqlalchemy.exc import OperationalError

from app.batches import receipts
from app.dataset_schema_v3 import receipt_count_definition, receipt_ddl
from app.errors import ApiError, ErrorCode
from app.integrations.planning import run_snapshot
from app.integrations.planning_receipts import open_receipts, read_approved_receipts
from app.plans.repository import digest
from app.plans.service import what_if_snapshot
from contracts.interfaces.planning import PlanCommand
from contracts.interfaces.receipts import ReceiptRevisionInput
from tests.test_db_scheduled_receipts import receipt
from tests.test_real_planning_integration import official


SCOPE = 'CHUNGPAMO-2027'


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def mappings(self):
        return self

    def all(self):
        return self.value


def preview_tx(current=()):
    def execute(statement, params=None):
        sql = str(statement)
        if 'to_regclass' in sql:
            return Result(True)
        if 'alembic' in sql:
            return Result('0010')
        assert 'b.dataset_id = r.dataset_id' in sql and params['dataset_id'] == SCOPE
        return Result(list(current))
    return SimpleNamespace(c=SimpleNamespace(execute=execute),
                           list_known_materials=lambda: [SimpleNamespace(material_id='MR-N3', base_unit='kg')])


def preview(tx, data):
    return receipts.preview(tx, SCOPE, 'receipt.csv', data, None, None, None)


def test_receipt_template_and_source_row_digest():
    a = preview(preview_tx(), receipt())
    b = preview(preview_tx(), receipt())
    records = a.sheets[0].records
    assert a.status == 'READY_FOR_APPROVAL' and records == b.sheets[0].records
    assert records[0].location.row == 2 and len(records[0].source_row_sha256) == 64
    assert records[0].ordered_qty == '10000' and records[0].unit == 'kg' and records[0].receipt_key == 'PO-2701-001'
    assert ReceiptRevisionInput.model_validate(records[0].model_dump(exclude={'location', 'source_row_sha256'})
                                               | {'po_line_id': '02'}).receipt_key == 'PO-2701-001--02'
    assert preview(preview_tx(), receipt().replace(b'ordered_qty', b'amount')).status == 'MAPPING_HOLD'


@pytest.mark.parametrize(('filename', 'source_sheet'), [('receipt.csv', 'CSV'), ('receipt.xlsx', 'January')])
def test_receipt_approval_stores_nonempty_source_sheet_without_rewriting_digest(filename, source_sheet):
    data = receipt()
    if filename.endswith('.xlsx'):
        workbook = Workbook()
        workbook.active.title = source_sheet
        for line in data.decode().splitlines():
            workbook.active.append(line.split(','))
        with BytesIO() as stream:
            workbook.save(stream)
            data = stream.getvalue()
        workbook.close()
    staged = receipts.preview(preview_tx(), SCOPE, filename, data, None, None, None)
    record, = staged.sheets[0].records
    original_location = record.location.model_dump()
    original_digest = record.source_row_sha256
    tx = preview_tx()
    execute = tx.c.execute
    inserts, approvals = [], []

    def capture(statement, params):
        if 'INSERT INTO scheduled_receipt_revision' in str(statement):
            inserts.append(params)
        elif 'pg_advisory_xact_lock' not in str(statement):
            return execute(statement, params)

    tx.c.execute = capture
    tx.get_batch = lambda _: SimpleNamespace(dataset_id=SCOPE)
    tx.mark_approved = lambda *args: approvals.append(args)
    batch_id = UUID(int=1)
    assert receipts.commit(tx, batch_id, 'TEST-REVIEWER', [record]) == 1
    assert approvals == [(batch_id, 'TEST-REVIEWER', 1)]
    inserted, = inserts
    assert (inserted['source_sheet'], inserted['source_row_no'], inserted['source_row_sha256']) == (
        source_sheet, original_location['row'], original_digest)
    assert record.location.model_dump() == original_location and record.source_row_sha256 == original_digest


@pytest.mark.parametrize(('data', 'code'), [
    (receipt(received=10001), 'RECEIPT_ROW_INVALID'),
    (receipt(unit='EA'), 'RECEIPT_MATERIAL_OR_UNIT_MISMATCH'),
    (receipt(material='MISSING'), 'RECEIPT_MATERIAL_OR_UNIT_MISMATCH'),
    (receipt(revision=2), 'RECEIPT_INITIAL_REVISION_INVALID'),
    (receipt(status='CANCELLED'), 'RECEIPT_INITIAL_REVISION_INVALID'),
    (receipt().replace(b'2027-01-20', b'2027-02-30'), 'RECEIPT_ROW_INVALID'),
    (receipt() + receipt().splitlines(keepends=True)[1], 'RECEIPT_DUPLICATE_PO'),
])
def test_receipt_invalid_rows_never_ready(data, code):
    result = preview(preview_tx(), data)
    assert result.status == 'HAS_ERRORS' and result.sheets[0].valid_records == 0
    assert {i.code for i in result.sheets[0].issues} == {code}


def test_cancelled_history_and_stale_concurrent_approval(monkeypatch):
    current = dict(receipt_key='PO-2701-001', po_id='PO-2701-001', po_line_id=None, revision=1, status='CANCELLED',
                   effective_date=date(2026, 12, 31), received_qty=Decimal('1'), ordered_qty=Decimal('10000'),
                   material_id='MR-N3', unit='kg')
    assert preview(preview_tx([current]), receipt(revision=2, received=1)).status == 'HAS_ERRORS'
    valid = preview(preview_tx(), receipt()).sheets[0].records
    events = []
    tx = SimpleNamespace(get_batch=lambda _: SimpleNamespace(dataset_id=SCOPE),
                         c=SimpleNamespace(execute=lambda sql, params: events.append((str(sql), params))),
                         mark_approved=lambda *a: pytest.fail('A stale receipt cannot be approved'))

    def stale(*args):
        assert len(events) == 1 and 'pg_advisory_xact_lock' in events[0][0]
        return [(valid[0], 'RECEIPT_REVISION_INVALID')]
    monkeypatch.setattr(receipts, '_issues', stale)
    with pytest.raises(ApiError) as exc:
        receipts.commit(tx, UUID(int=1), 'TEST-REVIEWER', valid)
    assert exc.value.status == 409 and exc.value.code is ErrorCode.RESULT_CHANGED


def test_reader_distinguishes_unavailable_empty_and_database_failure(official):
    command = official.command
    disconnected = SimpleNamespace(execute=lambda sql, *p: Result('0009' if 'alembic' in str(sql) else False))
    assert read_approved_receipts(disconnected, command) is None
    corrupt = SimpleNamespace(execute=lambda sql, *p: Result('0010' if 'alembic' in str(sql) else False))
    with pytest.raises(ApiError) as exc:
        read_approved_receipts(corrupt, command)
    assert exc.value.code is ErrorCode.PERSISTENCE_ERROR

    def execute(sql, params=None):
        sql = str(sql)
        if 'to_regclass' in sql:
            return Result(True)
        if 'alembic' in sql:
            return Result('0010')
        assert params == {'dataset_id': SCOPE, 'as_of': command.as_of_date}
        assert "b.status = 'APPROVED'" in sql and 'b.dataset_id = r.dataset_id' in sql
        assert 'AND r.effective_date <= :as_of' in sql and 'ORDER BY r.receipt_key, r.revision DESC' in sql
        assert "r.status != 'CANCELLED'" not in sql
        return Result([])
    assert read_approved_receipts(SimpleNamespace(execute=execute), command) == []

    def broken(*args):
        raise OperationalError('select receipt', {}, OSError())
    with pytest.raises(OperationalError):
        read_approved_receipts(SimpleNamespace(execute=broken), command)


def test_official_receipt_reader_projection_and_parent_overrides(official):
    row = official.scheduled_receipts[0]
    result = {**row.model_dump(exclude={'open_qty'}), 'dataset_id': SCOPE, 'ordered_qty': '10000',
              'received_qty': '0', 'status': 'OPEN'}
    def execute(sql, *_):
        sql = str(sql)
        if 'to_regclass' in sql:
            return Result(True)
        if 'alembic' in sql:
            return Result('0010')
        return Result([result])
    connection = SimpleNamespace(execute=execute)
    ledger = read_approved_receipts(connection, official.command)
    sources = {r.material_id: r.base_unit for r in official.approved_inputs.materials}
    open_list = open_receipts(ledger, official.command, sources)
    connected = official.model_copy(update={'scheduled_receipts': open_list})
    disconnected = official.model_copy(update={'scheduled_receipts': None})

    def january(plans):
        return {r.plan_id: (Decimal(r.available_qty), Decimal(r.shortage_qty)) for r in plans.material_requirements
                if (r.material_id, r.period) == ('MR-N3','2027-01')}

    old = run_snapshot(disconnected.command, disconnected)
    base = run_snapshot(connected.command, connected)
    assert january(old.result) == {p: (82100, Decimal(q)) for p, q in
                                  [('BASELINE', '4028.4006'), ('STABLE', '7135.1947'), ('COST_SAVING', '1827.2391')]}
    assert january(base.result) == {p: (92100, 0) for p in january(old.result)}
    assert [r.code for r in old.result.unverified] == ['RECEIPT_SOURCE_UNAVAILABLE'] and not base.result.unverified
    assert [p.feasibility for p in base.result.plans] == [p.feasibility for p in old.result.plans]
    execution_id = UUID(int=99)
    parent = SimpleNamespace(input_snapshot=connected, execution_id=execution_id, status='COMPLETED', data_origin='REAL_ENGINE',
                             dataset_id=SCOPE, forecast_execution_id=connected.command.forecast_execution_id,
                             input_digest=base.input_digest, result_snapshot=base.result,
                             result_digest=digest(base.result.model_dump(mode='json')))
    for qty, available in [('4000', 86100), ('0', 82100)]:
        command = PlanCommand.model_validate({**connected.command.model_dump(), 'scenario':'WHAT_IF',
                                               'base_plan_execution_id':execution_id, 'overrides':{f'receipt_qty.{row.po_id}':qty}})
        reply = run_snapshot(command, what_if_snapshot(parent, command))
        assert all(amt == available for amt, _ in january(reply.result).values())
    assert parent.input_snapshot.scheduled_receipts == open_list and ledger[0].ordered_qty == '10000'


def test_migration_approval_trigger_extends_existing_definition_without_replacing_old_branches():
    old = "IF NEW.entity = 'inventory' THEN\n    SELECT 1 INTO n;\n  END IF;\n  IF n IS DISTINCT FROM NEW.approved_record_count::bigint THEN"
    updated = receipt_count_definition(old)
    assert receipt_count_definition(updated) == updated
    assert "NEW.entity = 'inventory'" in updated and "NEW.entity = 'scheduled_receipt'" in updated
    with pytest.raises(RuntimeError):
        receipt_count_definition('Unexpected catalog function')
    ddl = receipt_ddl(SCOPE)
    assert 'BEFORE UPDATE OR DELETE' in ddl and "CHECK(dataset_id='CHUNGPAMO-2027')" in ddl
    assert 'approved_at=now()' in ddl and "previous.status='CANCELLED'" in ddl
