"""Read the latest approved receipt revisions in one scoped database snapshot."""
from datetime import date

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError, TimeoutError

from app.batches.receipts import LATEST_APPROVED_RECEIPTS, installed
from app.datasets import get_dataset_engine, scope_error
from app.errors import ApiError, ErrorCode
from contracts.interfaces.receipts import (
    AvailableReceiptLedgerPage, ReceiptLedgerItem, ReceiptLedgerPage, ReceiptLedgerSource,
    ReceiptState, UnavailableReceiptLedgerPage,
)


# Keep both queries on the same filtered relation. Filtering first could resurrect
# an earlier OPEN revision when the latest approved revision is CANCELLED.
FILTERED_RECEIPTS = """
    WITH latest AS (
        SELECT DISTINCT ON (r.receipt_key)
            r.dataset_id, r.receipt_key, r.po_id, r.po_line_id, r.revision, r.material_id, r.unit,
            r.ordered_qty, r.received_qty, r.status AS ledger_status, r.expected_date, r.effective_date,
            r.batch_id, b.source_name AS filename, b.source_sha256, b.result_digest, b.approved_at,
            r.source_sheet, r.source_row_no, r.source_row_sha256
""" + LATEST_APPROVED_RECEIPTS + """
    ), with_state AS (
        SELECT latest.*,
            CASE WHEN ledger_status = 'CANCELLED' THEN 'CANCELLED'
                 WHEN received_qty = ordered_qty THEN 'COMPLETED'
                 WHEN received_qty > 0 THEN 'PARTIALLY_RECEIVED'
                 ELSE 'OPEN' END AS state
        FROM latest
    ), filtered AS (
        SELECT * FROM with_state
        WHERE (CAST(:po_id AS text) IS NULL OR po_id = :po_id)
          AND (CAST(:material_id AS text) IS NULL OR material_id = :material_id)
          AND (CAST(:state AS text) IS NULL OR state = :state)
    )
"""
COUNT_RECEIPTS = text(FILTERED_RECEIPTS + 'SELECT count(*) FROM filtered')
PAGE_RECEIPTS = text(FILTERED_RECEIPTS + """
    SELECT dataset_id, receipt_key, po_id, po_line_id, revision, material_id, unit,
        ordered_qty::text AS ordered_qty, received_qty::text AS received_qty,
        CASE WHEN state IN ('CANCELLED', 'COMPLETED') THEN '0'
             ELSE (ordered_qty - received_qty)::text END AS open_qty,
        ledger_status, state, expected_date, effective_date,
        batch_id, filename, source_sha256, result_digest, approved_at, source_sheet, source_row_no, source_row_sha256
    FROM filtered ORDER BY receipt_key LIMIT :limit OFFSET :offset
""")


def read_receipt_page(
    dataset_id: str, *, as_of_date: date, po_id: str | None, material_id: str | None,
    state: ReceiptState | None, limit: int, offset: int,
) -> ReceiptLedgerPage:
    page = dict(dataset_id=dataset_id, as_of_date=as_of_date, limit=limit, offset=offset)
    params = dict(dataset_id=dataset_id, as_of=as_of_date, po_id=po_id, material_id=material_id, state=state)
    try:
        database = get_dataset_engine(dataset_id)
        with database.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
            connection.execute(text('SET TRANSACTION READ ONLY'))
            if not installed(connection):
                return UnavailableReceiptLedgerPage(
                    **page, source_state='UNAVAILABLE', reason_code='RECEIPT_SOURCE_UNAVAILABLE', items=None, total=None,
                )
            total = connection.execute(COUNT_RECEIPTS, params).scalar_one()
            items = []
            if offset < total:
                rows = connection.execute(PAGE_RECEIPTS, {**params, 'limit': limit, 'offset': offset}).mappings()
                for row in rows:
                    fields = dict(row)
                    if fields.pop('dataset_id') != dataset_id:
                        raise ValueError('Receipt ledger dataset mismatch')
                    source = {name: fields.pop(name) for name in ReceiptLedgerSource.model_fields}
                    items.append(ReceiptLedgerItem.model_validate({**fields, 'source': source}))
            return AvailableReceiptLedgerPage(**page, source_state='AVAILABLE', reason_code=None, items=items, total=total)
    except DBAPIError as exc:
        raise scope_error(exc) from None
    except TimeoutError:
        raise ApiError(503, ErrorCode.DB_UNAVAILABLE, 'Receipt ledger storage is unavailable.') from None
    except (SQLAlchemyError, ValueError, KeyError):
        raise ApiError(500, ErrorCode.PERSISTENCE_ERROR, 'Receipt ledger storage is inconsistent.') from None
