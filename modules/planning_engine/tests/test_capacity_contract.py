import copy
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from contracts.interfaces.capacity import CapacityRegistrationDraft

ROOT = Path(__file__).resolve().parents[3] / 'contracts/examples/integration'


def sample(): return json.loads((ROOT / 'capacity_registration.json').read_text())['payload']


def test_independent_quantity_machine_and_person_hour_limits_are_preserved():
    data = CapacityRegistrationDraft.model_validate(sample())
    assert data.quantity_limits[0].limit_qty == '10500'
    assert [r.time_basis for r in data.hours_budgets] == ['MACHINE_HOUR', 'PERSON_HOUR']
    assert data.routing_steps[0].reference_qty == '60'
    data.check_approved_products({'TP-10R'})
    with pytest.raises(ValueError): data.check_approved_products({'OTHER'})


@pytest.mark.parametrize('error', ['duplicate', 'unknown_resource', 'basis', 'cycle', 'zero_rate', 'setup', 'elapsed'])
def test_structural_errors_are_rejected_without_any_calculation(error):
    data = copy.deepcopy(sample())
    if error == 'duplicate': data['quantity_limits'] *= 2
    if error == 'unknown_resource': data['routing_steps'][0]['resource_id'] = 'UNKNOWN'
    if error == 'basis': data['hours_budgets'][0]['time_basis'] = 'PERSON_HOUR'
    if error == 'cycle': data['routing_steps'][0]['predecessor_step_ids'] = ['PACK']
    if error == 'zero_rate': data['routing_steps'][0]['run_time'] = '0'
    if error == 'setup': data['routing_steps'][0]['setup_time'] = '0'
    if error == 'elapsed': data['routing_steps'][0]['time_basis'] = 'ELAPSED'
    with pytest.raises(ValidationError): CapacityRegistrationDraft.model_validate(data)
