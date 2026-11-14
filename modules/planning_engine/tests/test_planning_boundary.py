import pytest
from pydantic import ValidationError
from contracts.interfaces.modules import PlanCommand


def test_handoff_fixtures_are_typed_but_not_calculation_evidence():
    import json
    from pathlib import Path
    from contracts.interfaces.modules import PlanningInput, PlanningOutput
    root = Path(__file__).resolve().parents[3] / 'contracts/examples/integration'
    source = PlanningInput.model_validate(json.loads((root / 'planning_input.json').read_text())['payload'])
    result = PlanningOutput.model_validate(json.loads((root / 'planning_output.json').read_text())['payload'])
    assert result.module_version == 'TEST-DOUBLE-ONLY'
    assert all(p.feasibility == 'UNVERIFIED' for p in result.plans)
    assert PlanningInput.model_validate(source.model_dump(mode='json')) == source
    bad = source.model_dump(mode='json')
    bad['forecast_rows'][0]['p90'] = '1'
    with pytest.raises(ValidationError): PlanningInput.model_validate(bad)


def test_what_if_requires_saved_base_and_explicit_scenario():
    request = {'forecast_execution_id': '00000000-0000-4000-8000-000000000001',
               'product_ids': ['TP-10R'], 'target_month': '2027-01', 'as_of_date': '2026-12-31'}
    with pytest.raises(ValidationError): PlanCommand(**request, scenario='WHAT_IF')
    with pytest.raises(ValidationError): PlanCommand(**request, overrides={'production_qty': '8500'})
