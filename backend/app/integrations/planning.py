"""Read-only approved snapshot provider and pure-module adapter. No plan writes."""
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

from app.batches.sql_repository import SqlBatchTx
from app.config import get_settings
from app.errors import ApiError, ErrorCode
from app.forecast.runs import ForecastRuns
from app.batches.capacity import planning_snapshot
from app.integrations.planning_validation import (
    forecast_scope, horizon_bounds, input_conflict, input_coverage, validate_input, validate_overrides, validate_pair,
)
from app.integrations.planning_receipts import ReceiptLedgerReader, open_receipts
from contracts.interfaces.modules import PlanCommand, PlanningInput, PlanningOutput, PlanningReply
from contracts.interfaces.planning import ApprovedSource, PlanningInputDiagnostics
from contracts.interfaces.dataset import LEGACY_DATASET


class PlanningSourceProvider(Protocol):
    def load(self, command: PlanCommand) -> PlanningInput: ...


def _encode(value):
    if isinstance(value, Decimal): return format(value, 'f')
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, UUID): return str(value)
    raise TypeError('Unsupported snapshot value')


def _json(value):
    return json.dumps(value, default=_encode, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _all_pages(fetch):
    result, offset = [], 0
    while True:
        rows, total = fetch(200, offset)
        result.extend(rows); offset += len(rows)
        if offset >= total: return result
        if not rows: raise ApiError(500, ErrorCode.PERSISTENCE_ERROR, '승인 입력 스냅샷 조회가 완료되지 않았습니다.')


class SqlPlanningSourceProvider:
    def __init__(self, database, receipt_reader: ReceiptLedgerReader | None = None):
        self.database = database
        self.receipt_reader = receipt_reader

    def load(self, command: PlanCommand) -> PlanningInput:
        if command.dataset_id != getattr(self.database, 'dataset_id', LEGACY_DATASET):
            raise ApiError(409,ErrorCode.DATASET_MISMATCH,'Plan request and database dataset do not match.')
        if command.scenario == 'WHAT_IF':
            from app.plans.service import load_what_if
            snapshot = load_what_if(self.database, command)
            validate_input(command, snapshot)
            return snapshot
        try:
            with self.database.connect().execution_options(isolation_level='REPEATABLE READ') as c:
                c.execute(text('SET TRANSACTION READ ONLY'))
                execution = ForecastRuns._detail(c, command.forecast_execution_id)
                if execution.dataset_id != command.dataset_id:
                    raise ApiError(404, ErrorCode.FORECAST_NOT_FOUND, '예측 실행 이력을 찾을 수 없습니다.')
                if execution.status not in ('OK', 'PARTIAL') or execution.result is None:
                    raise ApiError(409, ErrorCode.PLAN_INPUT_UNAVAILABLE, '성공한 저장 예측 결과를 선택하세요.')
                tx = SqlBatchTx(c)
                products = _all_pages(lambda l, o: tx.list_products(None, None, l, o))
                materials = _all_pages(lambda l, o: tx.list_materials(None, None, l, o))
                boms = _all_pages(lambda l, o: tx.list_boms(None, None, True, l, o))
                inventory = _all_pages(lambda l, o: tx.list_inventory(None, None, None, l, o))
                first, last = horizon_bounds(command)
                # Preserve candidates across month boundaries; choosing versions/latest stock is engine policy.
                boms = [b for b in boms if b.header.valid_from <= last and (b.header.valid_to is None or b.header.valid_to >= first)]
                inventory = [r for r in inventory if r.as_of_date <= command.as_of_date]
                master = {r.product_id: r for r in products}
                required = forecast_scope(command)
                selected = [r for r in execution.result.forecasts if (r.product_id, r.target_month) in required]
                if set(command.product_ids) - set(master):
                    raise input_conflict('PRODUCT_COVERAGE')
                if {(r.product_id, r.target_month) for r in selected} != required or len(selected) != len(required):
                    raise input_conflict('FORECAST_PRODUCT_MONTH_COVERAGE')
                capacity, routing, capacity_ids, missing = planning_snapshot(c, command)
                ids = {r.batch_id for r in [*products, *materials, *boms, *inventory]} | capacity_ids
                receipt_rows = self.receipt_reader(c, command.dataset_id) if self.receipt_reader else None
                receipts = None
                receipt_ids = set()
                if receipt_rows is not None:
                    receipts = open_receipts(receipt_rows, command, {row.material_id: row.base_unit for row in materials})
                    receipt_ids = {row.batch_id for row in receipt_rows}
                    ids |= {row.batch_id for row in receipts}
                else:
                    missing.append('RECEIPT_SOURCE_UNAVAILABLE')
                forecast_ids = {row.batch_id for row in execution.input_batches}
                if not forecast_ids or len(forecast_ids) != len(execution.input_batches):
                    raise input_conflict('FORECAST_SOURCE_MISMATCH')
                all_ids = ids | forecast_ids | receipt_ids
                sources = c.execute(text("""SELECT batch_id,version AS batch_version,entity,source_sha256,result_digest,approved_at
FROM import_batch WHERE batch_id=ANY(CAST(:ids AS uuid[])) AND dataset_id=:dataset_id
AND status='APPROVED' AND blocking_error_count=0 ORDER BY batch_id"""), {
                    'ids': sorted(all_ids), 'dataset_id': command.dataset_id,
                }).mappings().all()
                approved = {row['batch_id']: ApprovedSource.model_validate(row) for row in sources}
                if approved.keys() != all_ids:
                    raise input_conflict('APPROVED_SOURCE_MISMATCH')
                if any(approved[id].entity != 'scheduled_receipt' or not approved[id].result_digest for id in receipt_ids):
                    raise input_conflict('RECEIPT_SOURCE_MISMATCH')
                for source in execution.input_batches:
                    current = approved[source.batch_id]
                    if (current.entity != 'monthly_demand'
                            or current.model_dump(exclude={'entity'}) != source.model_dump()):
                        raise input_conflict('FORECAST_SOURCE_MISMATCH')
                # Keep LEGACY plan snapshots compatible while checking forecast provenance for every dataset.
                source_ids = ids if command.dataset_id == LEGACY_DATASET else ids | forecast_ids
                if any(not any(b.header.product_id == pid for b in boms) for pid in command.product_ids): missing.append('BOM_COVERAGE')
                if any(not any(r.item_type == 'PRODUCT' and r.item_id == pid for r in inventory) for pid in command.product_ids): missing.append('INVENTORY_COVERAGE')
                snapshot = PlanningInput.model_validate(json.loads(_json({
                    'dataset_id': command.dataset_id,
                    'command': command.model_dump(mode='json'), 'forecast_input_digest': execution.input_digest,
                    'forecast_model_version': getattr(execution, 'quantile_model_version', None),
                    'forecast_runtime_identity': getattr(execution, 'runtime_identity', {}),
                    'forecast_rows': [{'product_id': r.product_id, 'target_month': r.target_month, 'p50': r.p50,
                                       'p80': r.p80, 'p90': r.p90, 'unit': master[r.product_id].base_unit} for r in selected],
                    'approved_inputs': {'products': [asdict(r) for r in products], 'materials': [asdict(r) for r in materials],
                                        'boms': [asdict(r) for r in boms], 'inventory': [asdict(r) for r in inventory],
                                        'sources': [approved[id].model_dump(mode='json') for id in sorted(source_ids)]}, 'missing_inputs': missing,
                    'capacity_snapshot': capacity, 'routing_snapshot': routing,
                    'scheduled_receipts': None if receipts is None else [row.model_dump(mode='json') for row in receipts],
                })))
                validate_input(command, snapshot)
                return snapshot
        except ValidationError:
            raise input_conflict('STORED_INPUT_INVALID') from None
        except (OperationalError, InterfaceError):
            raise ApiError(503, ErrorCode.DB_UNAVAILABLE, '계획 입력 저장소에 연결할 수 없습니다.') from None
        except DBAPIError:
            raise ApiError(500, ErrorCode.PERSISTENCE_ERROR, '계획 입력 스냅샷 조회에 실패했습니다.') from None


def get_source_provider(dataset_id='TISSUE-LEGACY') -> PlanningSourceProvider:
    if get_settings().persistence != 'postgres':
        raise ApiError(501, ErrorCode.PERSISTENCE_DISABLED, '승인 계획 입력 조회가 비활성화되어 있습니다.')
    from app.datasets import get_dataset_engine
    return SqlPlanningSourceProvider(get_dataset_engine(dataset_id))


def snapshot_digest(snapshot: PlanningInput) -> str:
    return 'sha256:' + hashlib.sha256(_json(snapshot.model_dump(mode='json')).encode()).hexdigest()


def preview_inputs(command: PlanCommand) -> PlanningInputDiagnostics:
    try:
        provider = get_source_provider() if command.dataset_id == LEGACY_DATASET else get_source_provider(command.dataset_id)
        snapshot = PlanningInput.model_validate(provider.load(command))
        validate_input(command, snapshot)
    except ApiError:
        raise
    except ValidationError:
        raise input_conflict('STORED_INPUT_INVALID') from None
    except Exception:
        raise ApiError(500, ErrorCode.MODULE_ERROR, '계획 입력 진단 자료를 구성할 수 없습니다.') from None

    try:
        from engine import planning
        engine_available = bool(planning.AVAILABLE)
    except ImportError:
        engine_available = False

    inputs, missing, warnings = input_coverage(snapshot)
    needs_review = missing or any(code != 'POLICY_NOT_CONFIRMED' for code in warnings)
    return PlanningInputDiagnostics(
        dataset_id=command.dataset_id, forecast_execution_id=command.forecast_execution_id,
        target_month=command.target_month, as_of_date=command.as_of_date,
        horizon_months=command.horizon_months, scope='SINGLE_MONTH' if command.horizon_months == 1 else 'MULTI_MONTH',
        status='NEEDS_REVIEW' if needs_review else 'INPUTS_PRESENT',
        inputs={kind: {'row_count': count, 'ready': ready} for kind, (count, ready) in inputs.items()},
        missing_inputs=missing, warning_codes=warnings, approved_sources=snapshot.approved_inputs.sources,
        forecast_input_digest=snapshot.forecast_input_digest, input_digest=snapshot_digest(snapshot),
        engine_available=engine_available,
    )


def execute(command: PlanCommand, provider_factory=get_source_provider) -> PlanningReply:
    validate_overrides(command)
    try:
        from engine import planning
        if not planning.AVAILABLE:
            raise NotImplementedError
    except (ImportError, NotImplementedError):
        raise ApiError(501, ErrorCode.MODULE_NOT_IMPLEMENTED, '생산계획 계산 모듈은 아직 구현되지 않았습니다.') from None
    try:
        snapshot = PlanningInput.model_validate(provider_factory().load(command))
    except ApiError:
        raise
    except Exception:
        raise ApiError(500, ErrorCode.MODULE_ERROR, '계획 입력 스냅샷 구성 또는 계약 검증에 실패했습니다.') from None
    return run_snapshot(command, snapshot)


def run_snapshot(command: PlanCommand, snapshot: PlanningInput) -> PlanningReply:
    from engine import planning
    # Prevent a provider mismatch and module mutation from changing the authoritative command/provenance.
    validate_input(command, snapshot)
    if command.scenario == 'WHAT_IF':
        validate_overrides(command, snapshot)
        base = snapshot.base_plan_snapshot or {}
        if (base.get('execution_id') != str(command.base_plan_execution_id)
                or base.get('forecast_execution_id') != str(command.forecast_execution_id)):
            raise ApiError(409, ErrorCode.PLAN_INPUT_UNAVAILABLE, '저장된 기준 계획과 예측 실행의 연결을 확인하세요.')
    digest = snapshot_digest(snapshot)
    try:
        raw = planning.run(snapshot.model_copy(deep=True))
        result = PlanningOutput.model_validate(raw.model_dump() if isinstance(raw, PlanningOutput) else raw)
        validate_pair(snapshot, result)
        if (command.scenario == 'WHAT_IF' and result.status in ('OK', 'PARTIAL')
                and {plan.plan_type for plan in result.plans} != {'BASELINE', 'STABLE', 'COST_SAVING'}):
            raise ValueError('What-if must recalculate all three plan types')
        return PlanningReply(forecast_execution_id=command.forecast_execution_id, input_digest=digest, result=result)
    except NotImplementedError:
        raise ApiError(501, ErrorCode.MODULE_NOT_IMPLEMENTED, '요청한 계획 계산은 아직 지원되지 않습니다.') from None
    except Exception:
        raise ApiError(500, ErrorCode.MODULE_ERROR, '계획 모듈 실행 또는 출력 계약 검증에 실패했습니다.') from None
