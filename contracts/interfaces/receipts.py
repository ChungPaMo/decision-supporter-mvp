"""Input record for the scheduled receipt entity in the existing batch approval flow."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .base import Code, DecimalValue, StrictModel


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
    status: Literal['OPEN', 'CANCELLED']

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
