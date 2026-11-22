"""Boundary for a future approved receipt ledger, read in the planning transaction."""
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy.engine import Connection

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
