"""Offline API/service contract validation of Lee's generated data.

Uses an explicitly isolated in-memory repository. No Docker, SQL or DB approval.
Production parsers/validators/digest gates run unchanged; CAPA persistence is a
test double only. Generated source CSVs are read-only and remain Git-ignored.
"""
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from types import SimpleNamespace
import csv
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'modules/planning_engine'),str(ROOT)]
FILES=[('01_products.csv','product'),('02_materials.csv','material'),('03_bom.csv','bom'),
       ('04_inventory.csv','inventory'),('05_monthly_demand.csv','monthly_demand'),
       ('06_capacity_resources.csv','capacity'),('07_capacity_quantity_limits.csv','capacity'),
       ('08_capacity_hours_budgets.csv','capacity'),('09_routing_steps.csv','routing')]


def verify(folder=None):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.batches import get_service
    from app.batches.service import BatchService
    from app.batches import capacity
    from tests.fakes import InMemoryBatchRepository,FakeTx
    from contracts.interfaces.capacity import CapacityRegistrationDraft
    folder=Path(folder) if folder else ROOT/'modules/planning_engine/synthetic/data'
    class Repository(InMemoryBatchRepository):
        def __init__(self):
            super().__init__()
            self.state.capacity={s:[] for s in capacity.MODELS}
        @contextmanager
        def transaction(self):
            with super().transaction() as tx:
                tx.c=tx
                yield tx
    repo=Repository();svc=BatchService(repo);client=TestClient(app)
    def approved(tx,section):return tx.s.capacity[section]
    def persist_double(tx,bid,actor,records):
        capacity.validate_rows(tx,tx.get_batch(bid).entity,[(r.section,r.payload) for r in records])
        tx.mark_approved(bid,actor,len(records))
        for row in records:tx.s.capacity[row.section].append({'payload':row.payload,'batch_id':bid})
        return len(records)
    previous=app.dependency_overrides.get(get_service)
    app.dependency_overrides[get_service]=lambda:svc
    report={'scope':'OFFLINE / TEST-DOUBLE-ONLY / NO DATABASE WRITE','normal':[],'errors':[]}
    try:
        with patch.object(capacity,'approved_rows',approved),patch.object(capacity,'commit',persist_double):
            for name,entity in FILES:
                path=folder/'upload'/name;data=path.read_bytes()
                rows=list(csv.DictReader(data.decode('utf-8-sig').splitlines()))
                upload=client.post('/batches',files={'file':(name,data)},data={'entity':entity,'source_type':'SYNTHETIC',
                    'source_note':'CP-PAPER integration contract verification, generated synthetic data; offline double only','created_by':'SYNTHETIC-TEST'})
                body=upload.json()
                item={'file':name,'entity':entity,'rows':len(rows),'sha256':hashlib.sha256(data).hexdigest(),
                      'headers':list(rows[0]) if rows else [],'utf8_bom':data.startswith(b'\xef\xbb\xbf'),
                      'http_status':upload.status_code,'status':body.get('status'),'errors':body.get('blocking_error_count'),
                      'issues':[i for s in (body.get('validation') or {}).get('sheets',[]) for i in s['issues']],
                      'holds':[h for s in (body.get('validation') or {}).get('sheets',[]) for h in s['holds']]}
                if upload.status_code==201 and body['status']=='READY_FOR_APPROVAL':
                    response=client.post('/batches/'+body['batch_id']+'/approve',json={'approved_by':'OFFLINE-REVIEWER','expected_result_digest':body['result_digest']})
                    item['double_approval_http']=response.status_code;item['double_status']=response.json().get('status')
                    item['double_record_count']=response.json().get('approved_record_count')
                    duplicate=client.post('/batches',files={'file':(name,data)},data={'entity':entity,'source_type':'SYNTHETIC','source_note':'Same generated synthetic file'})
                    item['duplicate_http']=duplicate.status_code
                report['normal'].append(item)
            error_entities={'bom_unknown_material.csv':'bom','demand_bad_period_format.csv':'monthly_demand',
                'demand_duplicate_period.csv':'monthly_demand','demand_missing_qty.csv':'monthly_demand',
                'inventory_negative_qty.csv':'inventory','products_unknown_unit.csv':'product'}
            for name,entity in error_entities.items():
                data=(folder/'errors'/name).read_bytes()
                # Fresh isolated repository, with only approved master facts from the valid run.
                # Avoid a preexisting key making an otherwise valid error fixture fail accidentally.
                fresh=InMemoryBatchRepository();fresh.state.products=repo.state.products.copy();fresh.state.materials=repo.state.materials.copy()
                app.dependency_overrides[get_service]=lambda r=fresh:BatchService(r)
                response=client.post('/batches',files={'file':(name,data)},data={'entity':entity,'source_type':'SYNTHETIC','source_note':'Synthetic negative contract fixture'})
                body=response.json();issues=[i for s in (body.get('validation') or {}).get('sheets',[]) for i in s['issues']]
                report['errors'].append({'file':name,'http_status':response.status_code,'status':body.get('status'),
                    'blocking_errors':body.get('blocking_error_count'),'issues':issues})
            app.dependency_overrides[get_service]=lambda:svc
            dirty=folder/'errors/sales_orders_dirty_sample.csv'
            response=client.post('/ingest/preview',files={'file':(dirty.name,dirty.read_bytes())},data={'entity':'monthly_demand'})
            report['dirty_sales']={'http_status':response.status_code,'status':response.json().get('status'),
                                  'supported_as_monthly_demand':False,'note':'Requires a separate transaction cleaning/aggregation pipeline.'}
            # Pure typed snapshot of the NEW scenario alone; not a stored forecast or SQL PlanningInput.
            draft=CapacityRegistrationDraft(**{s:[r['payload'] for r in repo.state.capacity[s]] for s in capacity.MODELS})
            draft.check_approved_products(set(repo.state.products))
            report['capacity_dto']={'resources':len(draft.resources),'limits':len(draft.quantity_limits),
                'budgets':len(draft.hours_budgets),'steps':len(draft.routing_steps),
                'shared_saw_products':sorted({s.product_id for s in draft.routing_steps if s.resource_id=='SAW1'}),
                'concurrent_labor_steps':sum(any(r.resource_id=='LB1' and r.time_basis=='PERSON_HOUR' for r in s.resource_requirements) for s in draft.routing_steps),
                'periods':sorted({b.period for b in draft.hours_budgets}),
                'inventory_dates':sorted({str(row.as_of_date) for row,_ in repo.state.inventory.values()})}
            report['counts_in_memory']={k:len(getattr(repo.state,k)) for k in ('products','materials','boms','inventory','demand')}
            report['normal_contract_passes']=sum(r.get('double_status')=='APPROVED' and r.get('duplicate_http')==409 and r.get('errors')==0 for r in report['normal'])
    finally:
        if previous is None:app.dependency_overrides.pop(get_service,None)
        else:app.dependency_overrides[get_service]=previous
    return report


if __name__=='__main__':
    report=verify();artifact=ROOT/'.artifacts/synthetic_validation.json';artifact.parent.mkdir(exist_ok=True)
    artifact.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(report['normal_contract_passes']!=len(FILES))
