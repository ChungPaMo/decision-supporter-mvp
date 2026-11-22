"""Dedicated development DB only. Probes always rollback; --approve explicitly seeds the new dataset.
No DROP/TRUNCATE, existing business-row UPDATE or source-file rewrite.
"""
from contextlib import contextmanager
from pathlib import Path
import argparse
import hashlib
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from seed_tissue_capacity import verify_target,ROOT
from verify_synthetic_contracts import FILES,verify


def isolation_probes(base):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from fastapi import Depends
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.batches import get_service
    from app.api.datasets import dataset_context
    from app.datasets import schema_for,CORE_TABLES,get_dataset_engine
    from app.batches.service import BatchService
    from app.batches.sql_repository import SqlBatchRepository
    from app.integrations.planning import SqlPlanningSourceProvider
    from contracts.interfaces.planning import PlanCommand
    from app.errors import ApiError
    target='CHUNGPAMO-2027';schema=schema_for(target);checks=[]
    with base.connect() as c:
        outer=c.begin()
        before=c.execute(text(f'SELECT count(*) FROM "{schema}".import_batch')).scalar()
        class Bound:
            def __init__(self,id):self.dataset_id=id;self.schema=schema_for(id)
            @contextmanager
            def begin(self):
                with c.begin_nested():
                    c.exec_driver_sql(f'SET LOCAL search_path TO "{self.schema}",pg_catalog')
                    yield c
                    c.execute(text('SET CONSTRAINTS ALL IMMEDIATE'));c.execute(text('SET CONSTRAINTS ALL DEFERRED'))
        def get_probe(dataset_id:str=Depends(dataset_context)):
            if dataset_id not in ('TISSUE-LEGACY',target):raise ValueError('Unexpected test scope')
            return BatchService(SqlBatchRepository(Bound(dataset_id)))
        app.dependency_overrides[get_service]=get_probe
        client=TestClient(app)
        def upload(entity,data):
            return client.post('/batches',params={'dataset_id':target},files={'file':('probe.csv',data)},
                data={'entity':entity,'source_type':'SYNTHETIC','source_note':'Rollback-only cross-dataset probe'})
        def approve(response):
            b=response.json();assert response.status_code==201 and b['status']=='READY_FOR_APPROVAL',b
            r=client.post('/batches/'+b['batch_id']+'/approve',params={'dataset_id':target},json={'approved_by':'PROBE-REVIEWER','expected_result_digest':b['result_digest']})
            assert r.status_code==200,r.json()
            return r.json()
        try:
            # Legacy-only product/resource are not fallback references before a local copy is registered.
            r=upload('monthly_demand',b'product_id,period,demand_qty,unit\nTP-10R,2026-12,5,EA\n')
            assert r.json()['status']=='HAS_ERRORS'
            r=upload('capacity',b'capacity_id,resource_id,period,regular_hours,unit,time_basis,availability_basis\nPROBE-H,M1,2027-01,10,h,MACHINE_HOUR,NET\n')
            assert r.json()['status']=='HAS_ERRORS';checks.append('cross-dataset product/resource references rejected')
            product=approve(upload('product',b'product_id,product_name,base_unit,product_type,safety_stock_qty\nTP-10R,Synthetic duplicate code,EA,FINISHED,0\n'))
            resource=approve(upload('capacity',b'resource_id,resource_name,kind,time_basis,parallel_units\nM1,Synthetic duplicate resource,EQUIPMENT,MACHINE_HOUR,1\n'))
            assert product['dataset_id']==target and resource['dataset_id']==target
            assert c.execute(text('SELECT count(*) FROM public.product WHERE product_id=\'TP-10R\'')).scalar()==1
            assert c.execute(text(f'SELECT count(*) FROM "{schema}".product WHERE product_id=\'TP-10R\'')).scalar()==1
            checks.append('same product/resource IDs coexist with independent PKs and approval roots')
            r=upload('bom',b'bom_id,product_id,bom_version,status,is_active,valid_from,base_qty,line_no,component_type,component_id,qty_per,unit,scrap_rate\nPROBE-B,TP-10R,V1,APPROVED,Y,2026-01-01,1,1,MATERIAL,TP-ROLL,1,EA,0\n')
            assert r.json()['status']=='HAS_ERRORS';checks.append('BOM cannot borrow a material from legacy')
            r=client.get('/batches/'+product['batch_id'],params={'dataset_id':'TISSUE-LEGACY'})
            assert r.status_code==404;checks.append('batch UUID cannot cross dataset detail/approval boundary')
            try:
                with c.begin_nested():
                    c.execute(text(f'UPDATE "{schema}".import_batch SET dataset_id=\'TISSUE-LEGACY\' WHERE batch_id=:id'),{'id':product['batch_id']})
            except IntegrityError:pass
            else:raise AssertionError('dataset root ownership changed')
            checks.append('dataset membership immutable in DB')
            fks=c.execute(text("""SELECT rn.nspname AS referenced_schema,r.relname FROM pg_constraint k JOIN pg_class t ON t.oid=k.conrelid
                JOIN pg_namespace n ON n.oid=t.relnamespace JOIN pg_class r ON r.oid=k.confrelid JOIN pg_namespace rn ON rn.oid=r.relnamespace
                WHERE k.contype='f' AND n.nspname=:schema"""),{'schema':schema}).mappings().all()
            assert fks and all(r['referenced_schema']==schema or (r['referenced_schema']=='public' and r['relname']=='dataset') for r in fks)
            checks.append('all business FKs target local schema; only ownership registry is shared')
        finally:
            app.dependency_overrides.pop(get_service,None);outer.rollback()
    with base.connect() as c:
        assert c.execute(text(f'SELECT count(*) FROM "{schema}".import_batch')).scalar()==before
        forecast=c.execute(text('SELECT execution_id FROM public.forecast_run LIMIT 1')).scalar_one()
    try:
        SqlPlanningSourceProvider(get_dataset_engine(target)).load(PlanCommand(dataset_id=target,forecast_execution_id=forecast,product_ids=['TP-10R'],target_month='2027-01',horizon_months=1,as_of_date='2026-12-31'))
    except ApiError as exc:assert exc.status==404
    else:raise AssertionError('cross-dataset forecast accepted')
    checks.append('foreign dataset forecast UUID rejected; all probes rolled back')
    return checks


def registry_probes(base):
    """Exercise actual dataset creation with additive schema DDL, then rollback everything."""
    from app.main import app
    from app.api.datasets import get_repository
    from app.datasets import DatasetRepository,schema_for
    from fastapi.testclient import TestClient
    from sqlalchemy import text
    with base.connect() as c:
        outer=c.begin()
        class Bound:
            @contextmanager
            def begin(self):
                with c.begin_nested():yield c
            @contextmanager
            def connect(self):yield c
        app.dependency_overrides[get_repository]=lambda:DatasetRepository(Bound())
        try:
            client=TestClient(app)
            body={'dataset_id':'PROBE-DATASET','dataset_name':'Rollback-only synthetic probe','description':'SYNTHETIC dataset API verification'}
            assert client.post('/datasets',json=body).status_code==201
            assert client.get('/datasets/PROBE-DATASET').json()['created_by'] is None
            assert client.post('/datasets',json=body).status_code==409
            assert client.get('/datasets/DOES-NOT-EXIST').status_code==404
            assert client.post('/datasets',json={**body,'dataset_id':'../public'}).status_code==422
        finally:
            app.dependency_overrides.pop(get_repository,None);outer.rollback()
    with base.connect() as c:
        assert c.execute(text('SELECT count(*) FROM public.dataset WHERE dataset_id=\'PROBE-DATASET\'')).scalar()==0
        assert not c.execute(text('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:s)'),{'s':schema_for('PROBE-DATASET')}).scalar()
    return ['dataset create/get/duplicate/unknown/invalid API; schema and registry probes rolled back']


def plan_lineage_probes():
    from app.datasets import get_dataset_engine
    from app.integrations.planning import SqlPlanningSourceProvider
    from app.plans.repository import PlanRepository
    from app.plans.service import what_if_snapshot
    from app.errors import ApiError
    from contracts.interfaces.planning import PlanCommand,PlanningOutput
    from sqlalchemy import text
    target='CHUNGPAMO-2027';engine=get_dataset_engine(target)
    with engine.connect() as c:forecast=c.execute(text('SELECT execution_id FROM forecast_run LIMIT 1')).scalar_one()
    command=PlanCommand(dataset_id=target,forecast_execution_id=forecast,product_ids=['CP-N3-3030'],target_month='2027-01',horizon_months=1,as_of_date='2026-12-31')
    snapshot=SqlPlanningSourceProvider(engine).load(command)
    result=PlanningOutput.model_validate(json.loads((ROOT/'contracts/examples/integration/planning_output.json').read_text(encoding='utf-8'))['payload'])
    for p in result.plans:
        for row in p.production:row.product_id='CP-N3-3030'
    with engine.connect() as c:
        outer=c.get_transaction()
        try:
            parent=PlanRepository.save(c,snapshot,result,{'test_double':True},'7'*64,origin='TEST_DOUBLE')
            new=PlanCommand(**{**command.model_dump(),'scenario':'WHAT_IF','base_plan_execution_id':parent.execution_id,'overrides':{'demand_multiplier.CP-N3-3030':'100'}})
            child_input=what_if_snapshot(parent,new,allow_test=True)
            child=PlanRepository.save(c,child_input,result,{'test_double':True},'8'*64,origin='TEST_DOUBLE')
            c.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
            assert child.dataset_id==parent.dataset_id==target
            assert child.base_plan_execution_id==parent.execution_id
            assert PlanRepository.detail(c,parent.execution_id,include_test=True).input_snapshot==snapshot
            try:what_if_snapshot(parent,new.model_copy(update={'dataset_id':'TISSUE-LEGACY'}),allow_test=True)
            except ApiError as exc:assert exc.status==409
            else:raise AssertionError('Cross-dataset What-if accepted')
            with get_dataset_engine('TISSUE-LEGACY').connect() as legacy:
                try:PlanRepository.detail(legacy,parent.execution_id,include_test=True)
                except ApiError as exc:assert exc.status==404
                else:raise AssertionError('Cross-dataset plan UUID accepted')
        finally:outer.rollback()
    with engine.connect() as c:assert c.execute(text('SELECT count(*) FROM plan_execution')).scalar()==0
    return ['same-dataset stored What-if lineage; foreign dataset plan/child denied; TEST_DOUBLE records rolled back']


def main(approve=False):
    base=verify_target()
    from sqlalchemy import text
    from fastapi.testclient import TestClient
    from app.main import app
    from app.datasets import schema_for,get_dataset_engine,CORE_TABLES
    from app.integrations.planning import SqlPlanningSourceProvider
    from contracts.interfaces.planning import PlanCommand
    with base.connect() as c:assert c.execute(text('SELECT version_num FROM public.alembic_version')).scalar()=='0009'
    offline=verify();assert offline['normal_contract_passes']==9
    checks=registry_probes(base)+isolation_probes(base)
    print('Pre-approval isolation probes:',len(checks),'passed')
    if not approve:return
    target='CHUNGPAMO-2027';client=TestClient(app);params={'dataset_id':target}
    folder=ROOT/'modules/planning_engine/synthetic/data/upload'
    expected={hashlib.sha256((folder/n).read_bytes()).hexdigest() for n,_ in FILES}
    batches=client.get('/batches',params={**params,'limit':200}).json()['items']
    if any(b['source_type']!='SYNTHETIC' or b['file']['sha256'] not in expected for b in batches):raise RuntimeError('Unexpected dataset contents; no seed writes allowed')
    records=[]
    for name,entity in FILES:
        data=(folder/name).read_bytes();sha=hashlib.sha256(data).hexdigest()
        existing=next((b for b in batches if b['file']['sha256']==sha and b['entity']==entity),None)
        r=(client.get('/batches/'+existing['batch_id'],params=params) if existing else
            client.post('/batches',params=params,files={'file':(name,data)},data={'entity':entity,'source_type':'SYNTHETIC',
                'source_note':'CHUNGPAMO-2027; Lee synthetic generator SEED 20261115; generated fictional company data','created_by':'DATASET-INTEGRATION'}))
        assert r.status_code in (200,201),r.json();b=r.json()
        if b['status']=='READY_FOR_APPROVAL':
            r=client.post('/batches/'+b['batch_id']+'/approve',params=params,json={'approved_by':'REVIEWER-INTEGRATION','expected_result_digest':b['result_digest']})
            assert r.status_code==200,r.json();b=r.json()
        assert b['status']=='APPROVED' and b['blocking_error_count']==0,b
        records.append({**{k:b[k] for k in ('batch_id','entity','dataset_id','status','version','approved_record_count','result_digest')},'source_sha256':b['file']['sha256']})
        duplicate=client.post('/batches',params=params,files={'file':(name,data)},data={'entity':entity,'source_type':'SYNTHETIC','source_note':'Duplicate source check'})
        assert duplicate.status_code==409
    legacy=client.get('/products').json();new=client.get('/products',params=params).json()
    assert legacy['total']==1 and legacy['items'][0]['product_id']=='TP-10R'
    assert new['total']==9 and all(p['product_id'].startswith('CP-') for p in new['items'])
    r=client.post('/forecasts',params=params,json={'trained_until':'2026-12-31','horizon_months':3})
    assert r.status_code in (200,201),r.json();execution=r.json()['execution']
    assert execution['dataset_id']==target and execution['status'] in ('OK','PARTIAL')
    id=execution['execution_id'];assert client.get('/forecasts/'+id).status_code==404
    engine=get_dataset_engine(target)
    from uuid import UUID
    snapshot=SqlPlanningSourceProvider(engine).load(PlanCommand(dataset_id=target,forecast_execution_id=UUID(id),product_ids=[p['product_id'] for p in new['items']],target_month='2027-01',horizon_months=1,as_of_date='2026-12-31'))
    assert snapshot.dataset_id==target and snapshot.forecast_input_digest==execution['input_digest']
    assert len(snapshot.approved_inputs.products)==9 and len(snapshot.capacity_snapshot.resources)==6
    assert len(snapshot.routing_snapshot.routing_steps)==27
    assert all(r.resource_id not in ('M1','L1') for r in snapshot.capacity_snapshot.resources)
    checks+=plan_lineage_probes()
    with engine.connect() as c:
        counts={t:c.execute(text('SELECT count(*) FROM '+t)).scalar() for t in CORE_TABLES}
    output={'checks':checks,'batches':records,'counts':counts,'forecast_execution_id':id,
            'dataset_input_digest':execution['dataset_input_digest'],'snapshot':snapshot.model_dump(mode='json')}
    (ROOT/'.artifacts/dataset_integration.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'approved_batches':len(records),'forecast_execution_id':id,'counts':counts},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--approve',action='store_true');args=parser.parse_args();main(args.approve)
