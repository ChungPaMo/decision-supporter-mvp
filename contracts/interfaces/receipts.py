"""Scheduled receipt registration and approved ledger read contracts."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .base import Code, DecimalValue, StrictModel
from .dataset import DatasetId


ReceiptState = Literal['OPEN', 'PARTIALLY_RECEIVED', 'COMPLETED', 'CANCELLED']
ReceiptLedgerStatus = Literal['OPEN', 'CANCELLED']
Sha256Hex = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class ReceiptRevisionInput(StrictModel):
    po_id: Code
    po_line_id: Code | None = None
    revision: int = Field(ge=1, le=2_147_483_647)
    material_id: Code
    expected_date: date
    effective_date: date
    ordered_qty: DecimalValue
    received_qty: DecimalValue
    unit: Code
    supplier_id: Code | None = None
    status: ReceiptLedgerStatus

    @property
    def receipt_key(self) -> str:
        return self.po_id if self.po_line_id is None else f'{self.po_id}--{self.po_line_id}'

    @model_validator(mode='after')
    def check_revision(self):
        if any('.' in value or '--' in value for value in (self.po_id, self.po_line_id or '')) or len(self.receipt_key) > 40:
            raise ValueError('Invalid purchase order/line identifier for a What-if key')
        ordered, received = Decimal(self.ordered_qty), Decimal(self.received_qty)
        if ordered <= 0 or received > ordered:
            raise ValueError('Outstanding quantity must be derived from a valid order and cumulative receipt')
        return self


class ReceiptLedgerSource(StrictModel):
    batch_id: UUID
    filename: str
    source_sha256: Sha256Hex
    result_digest: Sha256Hex
    approved_at: AwareDatetime
    source_sheet: str = Field(min_length=1)
    source_row_no: int = Field(ge=1)
    source_row_sha256: Sha256Hex


class ReceiptLedgerItem(StrictModel):
    receipt_key: Code
    po_id: Code
    po_line_id: Code | None
    revision: int = Field(ge=1)
    material_id: Code
    unit: Code
    ordered_qty: DecimalValue
    received_qty: DecimalValue
    open_qty: DecimalValue
    ledger_status: ReceiptLedgerStatus
    state: ReceiptState
    expected_date: date
    effective_date: date
    source: ReceiptLedgerSource


class ReceiptLedgerPageBase(StrictModel):
    dataset_id: DatasetId
    as_of_date: date
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class AvailableReceiptLedgerPage(ReceiptLedgerPageBase):
    source_state: Literal['AVAILABLE']
    reason_code: None
    items: list[ReceiptLedgerItem]
    total: int = Field(ge=0)


class UnavailableReceiptLedgerPage(ReceiptLedgerPageBase):
    source_state: Literal['UNAVAILABLE']
    reason_code: Literal['RECEIPT_SOURCE_UNAVAILABLE']
    items: None
    total: None


ReceiptLedgerPage = Annotated[
    AvailableReceiptLedgerPage | UnavailableReceiptLedgerPage, Field(discriminator='source_state')
]
