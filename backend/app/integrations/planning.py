"""Read-only approved snapshot provider and pure-module adapter. No plan writes."""
import calendar
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

from app.batches.sql_repository import SqlBatchTx
from app.config import get_settings
from app.errors import ApiError, ErrorCode
from app.forecast.runs import ForecastRuns
from contracts.interfaces.modules import PlanCommand, PlanningInput, PlanningOutput, PlanningReply


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
    def __init__(self, database): self.database = database

    def load(self, command: PlanCommand) -> PlanningInput:
        if command.scenario == 'WHAT_IF':
            raise ApiError(501, ErrorCode.PLAN_HISTORY_NOT_IMPLEMENTED,
                           '기준 계획 저장·조회가 아직 없어 What-if 실행에 연결할 수 없습니다.')
        try:
            with self.database.connect().execution_options(isolation_level='REPEATABLE READ') as c:
                c.execute(text('SET TRANSACTION READ ONLY'))
                execution = ForecastRuns._detail(c, command.forecast_execution_id)
                if execution.status not in ('OK', 'PARTIAL') or execution.result is None:
                    raise ApiError(409, ErrorCode.PLAN_INPUT_UNAVAILABLE, '성공한 저장 예측 결과를 선택하세요.')
                tx = SqlBatchTx(c)
                products = _all_pages(lambda l, o: tx.list_products(None, None, l, o))
                materials = _all_pages(lambda l, o: tx.list_materials(None, None, l, o))
                boms = _all_pages(lambda l, o: tx.list_boms(None, None, True, l, o))
                inventory = _all_pages(lambda l, o: tx.list_inventory(None, None, None, l, o))
                year, month = map(int, command.target_month.split('-'))
                first, last = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
                # Preserve candidates across month boundaries; choosing versions/latest stock is engine policy.
                boms = [b for b in boms if b.header.valid_from <= last and (b.header.valid_to is None or b.header.valid_to >= first)]
                inventory = [r for r in inventory if r.as_of_date <= command.as_of_date]
                master = {r.product_id: r for r in products}
                selected = [r for r in execution.result.forecasts if r.product_id in command.product_ids and r.target_month == command.target_month]
                if set(command.product_ids) - set(master):
                    raise ApiError(409, ErrorCode.PLAN_INPUT_UNAVAILABLE, '승인된 제품 범위를 확인하세요.')
                if {r.product_id for r in selected} != set(command.product_ids):
                    raise ApiError(409, ErrorCode.PLAN_INPUT_UNAVAILABLE, '선택 제품·월의 예측이 누락됐습니다. 제외 제품을 0 수요로 처리하지 않습니다.')
                ids = {r.batch_id for r in [*products, *materials, *boms, *inventory]}
                sources = c.execute(text("""SELECT batch_id,version AS batch_version,entity,source_sha256,result_digest,approved_at
FROM import_batch WHERE batch_id=ANY(CAST(:ids AS uuid[])) AND status='APPROVED' AND blocking_error_count=0"""), {'ids': list(ids)}).mappings().all()
                if {r['batch_id'] for r in sources} != ids:
                    raise ApiError(409, ErrorCode.PLAN_INPUT_UNAVAILABLE, '승인 출처 스냅샷이 일치하지 않습니다.')
                missing = ['CAPACITY_NOT_REGISTERED', 'ROUTING_NOT_REGISTERED', 'POLICY_NOT_CONFIRMED']
                if any(not any(b.header.product_id == pid for b in boms) for pid in command.product_ids): missing.append('BOM_COVERAGE')
                if any(not any(r.item_type == 'PRODUCT' and r.item_id == pid for r in inventory) for pid in command.product_ids): missing.append('INVENTORY_COVERAGE')
                return PlanningInput.model_validate(json.loads(_json({
                    'command': command.model_dump(mode='json'), 'forecast_input_digest': execution.input_digest,
                    'forecast_model_version': getattr(execution, 'quantile_model_version', None),
                    'forecast_runtime_identity': getattr(execution, 'runtime_identity', {}),
                    'forecast_rows': [{'product_id': r.product_id, 'target_month': r.target_month, 'p50': r.p50,
                                       'p80': r.p80, 'p90': r.p90, 'unit': master[r.product_id].base_unit} for r in selected],
                    'approved_inputs': {'products': [asdict(r) for r in products], 'materials': [asdict(r) for r in materials],
                                        'boms': [asdict(r) for r in boms], 'inventory': [asdict(r) for r in inventory],
                                        'sources': [dict(r) for r in sources]}, 'missing_inputs': missing,
                })))
        except (OperationalError, InterfaceError):
            raise ApiError(503, ErrorCode.DB_UNAVAILABLE, '계획 입력 저장소에 연결할 수 없습니다.') from None
        except DBAPIError:
            raise ApiError(500, ErrorCode.PERSISTENCE_ERROR, '계획 입력 스냅샷 조회에 실패했습니다.') from None


def get_source_provider() -> PlanningSourceProvider:
    if get_settings().persistence != 'postgres':
        raise ApiError(501, ErrorCode.PERSISTENCE_DISABLED, '승인 계획 입력 조회가 비활성화되어 있습니다.')
    from app.db import get_engine
    return SqlPlanningSourceProvider(get_engine())


def execute(command: PlanCommand, provider_factory=get_source_provider) -> PlanningReply:
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
    # Prevent a provider mismatch and module mutation from changing the authoritative command/provenance.
    if snapshot.command != command:
        raise ApiError(500, ErrorCode.MODULE_ERROR, '계획 입력 명령이 스냅샷과 일치하지 않습니다.')
    if command.scenario == 'WHAT_IF':
        base = snapshot.base_plan_snapshot or {}
        if (base.get('execution_id') != str(command.base_plan_execution_id)
                or base.get('forecast_execution_id') != str(command.forecast_execution_id)):
            raise ApiError(409, ErrorCode.PLAN_INPUT_UNAVAILABLE, '저장된 기준 계획과 예측 실행의 연결을 확인하세요.')
    digest = 'sha256:' + hashlib.sha256(_json(snapshot.model_dump(mode='json')).encode()).hexdigest()
    try:
        result = PlanningOutput.model_validate(planning.run(snapshot.model_copy(deep=True)))
        units = {r.product_id: r.unit for r in snapshot.forecast_rows}
        for plan in result.plans:
            if any(r.product_id not in command.product_ids or r.period != command.target_month for r in plan.production):
                raise ValueError('Output outside requested scope')
            if any(r.unit != units.get(r.product_id) for r in plan.production):
                raise ValueError('Output unit differs from the approved product unit')
            if result.status == 'OK' and {r.product_id for r in plan.production} != set(command.product_ids):
                raise ValueError('OK cannot silently omit requested products')
            if snapshot.missing_inputs and plan.feasibility == 'FEASIBLE':
                raise ValueError('Missing source data cannot be reported as verified')
        return PlanningReply(forecast_execution_id=command.forecast_execution_id, input_digest=digest, result=result)
    except NotImplementedError:
        raise ApiError(501, ErrorCode.MODULE_NOT_IMPLEMENTED, '요청한 계획 계산은 아직 지원되지 않습니다.') from None
    except Exception:
        raise ApiError(500, ErrorCode.MODULE_ERROR, '계획 모듈 실행 또는 출력 계약 검증에 실패했습니다.') from None
