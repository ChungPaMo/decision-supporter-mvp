import pytest
from pydantic import ValidationError
from contracts.interfaces.modules import PlanCommand


def test_what_if_requires_saved_base_and_explicit_scenario():
    request = {'forecast_execution_id': '00000000-0000-4000-8000-000000000001',
               'product_ids': ['TP-10R'], 'target_month': '2027-01', 'as_of_date': '2026-12-31'}
    with pytest.raises(ValidationError): PlanCommand(**request, scenario='WHAT_IF')
    with pytest.raises(ValidationError): PlanCommand(**request, overrides={'production_qty': '8500'})
