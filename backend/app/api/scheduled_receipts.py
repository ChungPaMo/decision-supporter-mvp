from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.datasets import dataset_context
from app.batches.receipt_reader import read_receipt_page
from app.config import get_settings
from app.errors import ApiError, ErrorCode, ERROR_RESPONSES
from contracts.interfaces.base import Code
from contracts.interfaces.receipts import ReceiptLedgerPage, ReceiptState


router = APIRouter(tags=['scheduled-receipts'])


@router.get('/scheduled-receipts', response_model=ReceiptLedgerPage,
            responses={status: ERROR_RESPONSES[status] for status in (404, 409, 422, 500, 501, 503)},
            summary='List the latest approved receipt revisions at the business effective date')
def list_scheduled_receipts(
    dataset_id: Annotated[str, Depends(dataset_context)],
    as_of_date: Annotated[date, Query(description='Inclusive business effective date')],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    po_id: Annotated[Code | None, Query()] = None,
    material_id: Annotated[Code | None, Query()] = None,
    state: Annotated[ReceiptState | None, Query()] = None,
) -> ReceiptLedgerPage:
    if get_settings().persistence != 'postgres':
        raise ApiError(501, ErrorCode.PERSISTENCE_DISABLED, 'Receipt ledger persistence is disabled.')
    return read_receipt_page(
        dataset_id, as_of_date=as_of_date, po_id=po_id, material_id=material_id, state=state,
        limit=limit, offset=offset,
    )
