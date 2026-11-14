"""Registration policy and wire contracts; no module algorithm or DB access."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from decimal import Decimal
import pytest
from app.batches import capacity as service
from contracts.interfaces.capacity import CapacityRegistrationDraft

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture
def sample():
    return json.loads((ROOT/'contracts/examples/tissue_capacity/baseline.json').read_text(encoding='utf-8'))['payload']


def test_concurrent_requirements_are_one_step_not_two_operations(sample):
    d=CapacityRegistrationDraft(**sample)
    assert len(d.routing_steps)==1
    s=d.routing_steps[0]
    assert s.resource_id=='M1' and s.time_basis=='MACHINE_HOUR'
    assert s.resource_requirements[0].resource_id=='L1'
    assert Decimal(s.resource_requirements[0].run_time)/Decimal(s.resource_requirements[0].reference_qty)==Decimal('0.018')
    assert d.hours_budgets[1].regular_hours=='170' and d.resources[1].parallel_units==2


@pytest.mark.parametrize('problem',['missing','unknown','unit','period','time','duplicate_resource','duplicate_month','cycle','setup','overlap','unapproved_product'])
def test_registration_rejects_invalid_data(sample,monkeypatch,problem):
    data=copy.deepcopy(sample)
    if problem=='missing': del data['resources'][0]['resource_id']
    if problem=='unknown': data['routing_steps'][0]['resource_id']='UNKNOWN'
    if problem=='unit': data['quantity_limits'][0]['unit']='KG'
    if problem=='period': data['quantity_limits'][0]['period']='2027-13'
    if problem=='time': data['hours_budgets'][0]['unit']='day'
    if problem=='duplicate_resource': data['resources'].append(data['resources'][0])
    if problem=='duplicate_month': data['hours_budgets'].append({**data['hours_budgets'][0],'capacity_id':'H-OTHER'})
    if problem=='cycle': data['routing_steps'][0]['predecessor_step_ids']=['PACK']
    if problem=='setup': data['routing_steps'][0].update(setup_time='1',setup_policy_ref='UNKNOWN')
    if problem=='overlap': data['routing_steps'].append({**data['routing_steps'][0],'routing_version':'V2'})
    if problem=='unapproved_product': data['routing_steps'][0]['product_id']='UNAPPROVED'
    monkeypatch.setattr(service,'approved_rows',lambda c,s: [{'payload':r} for r in data['resources']] if s=='resources' and problem in ('setup','overlap') else [])
    tx=SimpleNamespace(c=None,list_known_products=lambda:[SimpleNamespace(product_id='TP-10R',base_unit='EA')])
    rows=[(s,p) for s in service.MODELS for p in data[s]]
    # Validate structural cases through the draft, then service-only reference policies separately.
    with pytest.raises(ValueError):
        d=CapacityRegistrationDraft(**data)
        d.check_approved_products({'TP-10R'})
        if problem in ('unit','duplicate_month','setup','overlap'):
            routing = problem in ('setup','overlap')
            rows=[(s,p) for s,p in rows if (s=='routing_steps')==routing]
            service.validate_rows(tx,'routing' if routing else 'capacity',rows)


def test_null_overtime_is_preserved(sample):
    sample['hours_budgets'][0]['overtime_hours_limit']=None
    assert CapacityRegistrationDraft(**sample).hours_budgets[0].overtime_hours_limit is None


def test_file_headers_hold_then_explicit_mapping(monkeypatch):
    from app.batches.capacity import preview
    monkeypatch.setattr(service,'approved_rows',lambda c,s: [])
    tx=SimpleNamespace(c=None,list_known_products=lambda:[])
    data=b'code,resource_name,kind,time_basis,parallel_units\nNEW,synthetic,EQUIPMENT,MACHINE_HOUR,1\n'
    assert preview(tx,'resources.csv',data,'capacity',{},None).status=='MAPPING_HOLD'
    result=preview(tx,'resources.csv',data,'capacity',{'resource_id':'code'},None)
    assert result.status=='READY_FOR_APPROVAL'


def test_snapshot_excludes_other_month_and_preserves_midmonth_versions(sample,monkeypatch):
    from contracts.interfaces.planning import PlanCommand
    from uuid import UUID
    rows={s:[{'payload':p,'batch_id':UUID(int=2)} for p in sample[s]] for s in service.MODELS}
    rows['routing_steps'][0]['payload']['valid_to']='2027-01-15'
    rows['routing_steps'].append({'batch_id':UUID(int=3),'payload':{**sample['routing_steps'][0],'routing_version':'V2','valid_from':'2027-01-16','valid_to':None}})
    rows['hours_budgets'].append({'batch_id':UUID(int=4),'payload':{**sample['hours_budgets'][0],'period':'2027-02','capacity_id':'NEXT'}})
    monkeypatch.setattr(service,'approved_rows',lambda c,s:rows[s])
    cmd=PlanCommand(forecast_execution_id=UUID(int=1),product_ids=['TP-10R'],target_month='2027-01',as_of_date='2026-12-31')
    capacity,routing,ids,missing=service.planning_snapshot(None,cmd)
    assert len(routing['routing_steps'])==2
    assert len(capacity['hours_budgets'])==2 and UUID(int=4) not in ids
    assert 'ROUTING_VERSION_POLICY_REQUIRED' in missing
