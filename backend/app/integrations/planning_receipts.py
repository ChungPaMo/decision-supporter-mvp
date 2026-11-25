"""Approved receipt supply, read in the planning transaction."""
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.batches.receipts import LATEST_APPROVED_RECEIPTS, installed
from app.integrations.planning_validation import input_conflict
from contracts.interfaces.base import Code, DecimalValue, StrictModel
from contracts.interfaces.dataset import DatasetId
from contracts.interfaces.planning import PlanCommand, ScheduledReceipt


class ReceiptLedgerRow(StrictModel):
    dataset_id: DatasetId
    batch_id: UUID
    po_id: Code
    material_id: Code
    ordered_qty: DecimalValue
    received_qty: DecimalValue
    unit: Code
    expected_date: date
    supplier_id: Code | None = None
    status: Literal['OPEN', 'CANCELLED']


class ReceiptLedgerReader(Protocol):
    def __call__(self, connection: Connection, dataset_id: str) -> list[ReceiptLedgerRow]: ...


def read_approved_receipts(connection: Connection, command: PlanCommand) -> list[ReceiptLedgerRow] | None:
    if not installed(connection):
        return None
    rows = connection.execute(text('''
        SELECT DISTINCT ON (r.receipt_key) r.receipt_key AS po_id, r.dataset_id, r.batch_id, r.material_id,
            r.ordered_qty::text AS ordered_qty, r.received_qty::text AS received_qty, r.unit,
            r.expected_date, r.supplier_id, r.status
    ''' + LATEST_APPROVED_RECEIPTS), {
        'dataset_id': command.dataset_id, 'as_of': command.as_of_date,
    }).mappings().all()
    return [ReceiptLedgerRow.model_validate(row) for row in rows]


def open_receipts(rows: list[ReceiptLedgerRow], command: PlanCommand,
                  material_units: dict[str, str]) -> list[ScheduledReceipt]:
    """Validate one current ledger row per PO and project its outstanding balance."""
    seen = set()
    receipts = []
    for row in sorted(rows, key=lambda item: item.po_id):
        if row.dataset_id != command.dataset_id:
            raise input_conflict('RECEIPT_DATASET_MISMATCH')
        if row.po_id in seen:
            raise input_conflict('RECEIPT_DUPLICATE_PO')
        seen.add(row.po_id)
        if material_units.get(row.material_id) != row.unit:
            raise input_conflict('RECEIPT_MATERIAL_OR_UNIT_MISMATCH')
        ordered, received = Decimal(row.ordered_qty), Decimal(row.received_qty)
        if ordered <= 0 or received > ordered:
            raise input_conflict('RECEIPT_BALANCE_INVALID')
        if row.status == 'CANCELLED' or received == ordered:
            continue
        receipt = ScheduledReceipt(po_id=row.po_id, material_id=row.material_id,
                                   open_qty=format(ordered - received, 'f'), unit=row.unit,
                                   expected_date=row.expected_date, supplier_id=row.supplier_id, batch_id=row.batch_id)
        if receipt.period(command) is not None:
            receipts.append(receipt)
    return receipts
