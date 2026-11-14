"""Registration draft only. No new upload entity, approval or DB migration."""
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import Field, model_validator
from .base import Code, Month, DecimalValue, StrictModel

TimeBasis = Literal['ELAPSED', 'PERSON_HOUR', 'MACHINE_HOUR']


class Resource(StrictModel):
    resource_id: Code
    resource_name: str
    kind: Literal['WORKCENTER', 'LABOR_POOL', 'EQUIPMENT', 'EQUIPMENT_POOL']
    time_basis: TimeBasis
    parallel_units: int = Field(ge=1)


class QuantityLimit(StrictModel):
    capacity_id: Code
    product_id: Code
    period: Month
    limit_qty: DecimalValue
    unit: Code
    accounting_point: Literal['FINISHED_OUTPUT', 'OPERATION_OUTPUT']
    operation_id: Code | None = None

    @model_validator(mode='after')
    def operation_required(self):
        if self.accounting_point == 'OPERATION_OUTPUT' and self.operation_id is None:
            raise ValueError('Operation output requires operation_id')
        return self


class HoursBudget(StrictModel):
    capacity_id: Code
    resource_id: Code
    period: Month
    regular_hours: DecimalValue
    overtime_hours_limit: DecimalValue | None = None
    unit: Literal['h', 'min']
    time_basis: TimeBasis
    availability_basis: Literal['GROSS', 'NET']
    calendar_ref: Code | None = None


class RoutingStep(StrictModel):
    routing_id: Code
    routing_version: Code
    step_id: Code
    product_id: Code
    operation_id: Code
    resource_id: Code
    predecessor_step_ids: list[Code]
    reference_qty: DecimalValue
    quantity_unit: Code
    run_time: DecimalValue
    time_unit: Literal['h', 'min']
    time_basis: TimeBasis
    concurrent_units: int | None = Field(default=None, ge=1)
    setup_time: DecimalValue | None = None
    setup_policy_ref: Code | None = None
    alternative_group_ref: Code | None = None
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode='after')
    def explicit_usage(self):
        if Decimal(self.reference_qty) <= 0 or Decimal(self.run_time) <= 0:
            raise ValueError('Reference quantity and run time must be positive')
        if self.time_basis == 'ELAPSED' and self.concurrent_units is None:
            raise ValueError('Elapsed usage requires explicit concurrent_units')
        if self.time_basis != 'ELAPSED' and self.concurrent_units is not None:
            raise ValueError('Already aggregated time must not multiply concurrent_units again')
        if self.setup_time is not None and self.setup_policy_ref is None:
            raise ValueError('Setup requires an explicit policy reference, including explicit zero setup')
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValueError('Inverted routing validity')
        return self


class CapacityRegistrationDraft(StrictModel):
    contract_version: Literal['capacity-registration-0.1-draft'] = 'capacity-registration-0.1-draft'
    resources: list[Resource]
    quantity_limits: list[QuantityLimit]
    hours_budgets: list[HoursBudget]
    routing_steps: list[RoutingStep]
    unresolved_policy_refs: list[Code] = Field(default_factory=list)

    @model_validator(mode='after')
    def references_and_cycles(self):
        def unique(rows, key):
            keys = [key(r) for r in rows]
            if len(keys) != len(set(keys)): raise ValueError('Duplicate logical row key')
        unique(self.resources, lambda r: r.resource_id)
        unique(self.quantity_limits, lambda r: (r.capacity_id, r.period))
        unique(self.hours_budgets, lambda r: (r.capacity_id, r.period))
        unique(self.routing_steps, lambda r: (r.routing_id, r.routing_version, r.step_id))
        resources = {r.resource_id: r for r in self.resources}
        steps = {(r.routing_id, r.routing_version, r.step_id): r for r in self.routing_steps}
        routing_products = {}
        for budget in self.hours_budgets:
            if budget.resource_id not in resources or budget.time_basis != resources[budget.resource_id].time_basis:
                raise ValueError('Budget resource or time basis mismatch')
        for step in self.routing_steps:
            key = (step.routing_id, step.routing_version)
            if key in routing_products and routing_products[key] != step.product_id:
                raise ValueError('A routing version must belong to one product')
            routing_products[key] = step.product_id
            if step.resource_id not in resources: raise ValueError('Unknown routing resource')
            if step.time_basis != 'ELAPSED' and step.time_basis != resources[step.resource_id].time_basis:
                raise ValueError('Routing time basis mismatch')
            if any((step.routing_id, step.routing_version, p) not in steps for p in step.predecessor_step_ids):
                raise ValueError('Unknown predecessor in this routing')
        visiting, done = set(), set()
        def visit(key):
            if key in visiting: raise ValueError('Routing cycle')
            if key in done: return
            visiting.add(key)
            for predecessor in steps[key].predecessor_step_ids: visit((key[0], key[1], predecessor))
            visiting.remove(key); done.add(key)
        for key in steps: visit(key)
        return self

    def check_approved_products(self, product_ids: set[str]):
        references = {r.product_id for r in self.quantity_limits} | {r.product_id for r in self.routing_steps}
        if references - product_ids: raise ValueError('Unapproved product reference')
