"""Actual PostgreSQL/API regression; ONLY the authorized disposable DB fixture.
All data comes from committed synthetic fixtures or a fresh temporary generator run.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import json
import runpy
from uuid import UUID,uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.main import app
from app.config import Settings
from app.batches.service import BatchService
from app.batches.sql_repository import SqlBatchRepository
from app.datasets import get_dataset_engine
from app.dataset_schema_v1 import schema_for
from app.integrations.planning import SqlPlanningSourceProvider
from app.plans.repository import PlanRepository,digest
from app.plans.service import what_if_snapshot
from app.plans.exports import formal_export
from app.errors import ApiError
from contracts.interfaces.planning import PlanCommand,PlanningInput,PlanningOutput
from scripts.verify_synthetic_contracts import FILES
from scripts.verify_test_db import assert_destructive_engine,DATABASE,ROLE

ROOT=Path(__file__).resolve().parents[2]


@contextmanager
def seeded_api(test_engine,tmp_path_factory,*,seed_legacy):
    from app import db
    from app.api import batches,forecasts,datasets,plan_executions
    from app.integrations import planning
    target=tmp_path_factory.mktemp('regression-synthetic')/'data'
    module=runpy.run_path(str(ROOT/'modules/planning_engine/synthetic/generate.py'),run_name='db_test_generator')
    module['main'].__globals__['OUT']=target;module['main']()
    settings=Settings(_env_file=None,persistence='postgres',database_url=test_engine.url.render_as_string(hide_password=False))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(db,'get_engine',lambda:test_engine)
        for m in (batches,forecasts,datasets,plan_executions,planning):patch.setattr(m,'get_settings',lambda:settings)
        client=TestClient(app)
        def upload(dataset,entity,file):
            r=client.post('/batches',params={'dataset_id':dataset},files={'file':(file.name,file.read_bytes())},
                data={'entity':entity,'source_type':'SYNTHETIC','source_note':'Fresh isolated regression synthetic fixture'})
            assert r.status_code==201,r.json();b=r.json();assert b['status']=='READY_FOR_APPROVAL',b
            r=client.post('/batches/'+b['batch_id']+'/approve',params={'dataset_id':dataset},json={'approved_by':'TEST-REVIEWER','expected_result_digest':b['result_digest']})
            assert r.status_code==200,r.json()
        if seed_legacy:
            for entity,file in [('product','tissue_products.csv'),('material','tissue_materials.csv'),('bom','tissue_bom.csv'),
                ('inventory','tissue_inventory.csv'),('monthly_demand','tissue_demand.csv'),
                ('capacity','tissue_capacity/capacity_upload.xlsx'),('routing','tissue_capacity/routing_upload.xlsx')]:
                upload('TISSUE-LEGACY',entity,ROOT/'contracts/examples'/file)
        for filename,entity in FILES:upload('CHUNGPAMO-2027',entity,target/'upload'/filename)
        yield client,test_engine


@pytest.fixture(scope='module')
def api(test_engine,tmp_path_factory):
    assert_destructive_engine(test_engine)
    try:
        with seeded_api(test_engine,tmp_path_factory,seed_legacy=True) as connection:
            yield connection
    finally:
        assert_destructive_engine(test_engine)
        with test_engine.begin() as c:
            assert tuple(c.execute(text('SELECT current_database(),current_user')).one())==(DATABASE,ROLE)
            for schema in ('public',schema_for('CHUNGPAMO-2027')):
                c.execute(text(f'TRUNCATE "{schema}".forecast_run,"{schema}".import_batch CASCADE'))


@pytest.mark.parametrize('dataset,products,resources,demand',[('TISSUE-LEGACY',1,2,24),('CHUNGPAMO-2027',9,6,498)])
def test_actual_dataset_api_forecast_and_input(api,dataset,products,resources,demand):
    client,engine=api;p={'dataset_id':dataset}
    assert client.get('/products',params=p).json()['total']==products
    assert client.get('/products',params={**p,'limit':1,'offset':products}).json()['items']==[]
    assert client.get('/demand/monthly',params=p).json()['total']==demand
    r=client.post('/forecasts',params=p,json={'trained_until':'2026-12-31','horizon_months':3})
    assert r.status_code==201,r.json();execution=r.json()['execution']
    reused=client.post('/forecasts',params=p,json={'trained_until':'2026-12-31','horizon_months':3})
    assert reused.status_code==200 and reused.json()['reused']
    assert execution['input_digest']!=execution['dataset_input_digest']
    ids=[r['product_id'] for r in client.get('/products',params=p).json()['items']]
    snapshot=SqlPlanningSourceProvider(get_dataset_engine(dataset)).load(PlanCommand(dataset_id=dataset,forecast_execution_id=execution['execution_id'],product_ids=ids,target_month='2027-01',horizon_months=1,as_of_date='2026-12-31'))
    assert snapshot.dataset_id==dataset and len(snapshot.capacity_snapshot.resources)==resources
    preview=client.post('/plans',params=p,json=snapshot.command.model_dump(mode='json'))
    assert preview.status_code in (200,422) and preview.json()['persisted'] is False,preview.json()
    other='CHUNGPAMO-2027' if dataset=='TISSUE-LEGACY' else 'TISSUE-LEGACY'
    assert client.get('/forecasts/'+execution['execution_id'],params={'dataset_id':other}).status_code==404


def test_actual_plan_preview_and_storage_on_regression_db(api,monkeypatch,record_property):
    client,engine=api
    with engine.connect() as c:
        revision=c.execute(text('SELECT version_num FROM public.alembic_version')).scalar_one()
    ledger_connected=revision=='0010'
    dataset='CHUNGPAMO-2027'
    params={'dataset_id':dataset}
    forecast=client.post('/forecasts',params=params,json={'trained_until':'2026-12-31','horizon_months':3})
    assert forecast.status_code in (200,201),forecast.json()
    command={'dataset_id':dataset,'forecast_execution_id':forecast.json()['execution']['execution_id'],
             'product_ids':[row['product_id'] for row in client.get('/products',params=params).json()['items']],
             'target_month':'2027-01','horizon_months':3,'as_of_date':'2026-12-31'}
    history=client.get('/plan-executions',params=params).json()['total']
    inputs=client.post('/planning-inputs/preview',params=params,json=command)
    assert inputs.status_code==200 and inputs.json()['engine_available'],inputs.json()
    assert inputs.json()['missing_inputs']==([] if ledger_connected else ['RECEIPT_SOURCE_UNAVAILABLE'])
    preview=client.post('/plans',params=params,json=command)
    assert preview.status_code==200 and preview.json()['persisted'] is False,preview.json()
    assert preview.json()['input_digest']==inputs.json()['input_digest']
    assert client.get('/plan-executions',params=params).json()['total']==history
    created=client.post('/plan-executions',params=params,json=command)
    assert created.status_code==201,created.json()
    parent=created.json()['execution']
    assert parent['data_origin']=='REAL_ENGINE' and parent['input_digest']==preview.json()['input_digest']
    assert parent['result_snapshot']==preview.json()['result']
    assert parent['result_digest']==digest(preview.json()['result'])
    assert parent['input_snapshot']['scheduled_receipts']==([] if ledger_connected else None)
    plan_types={'BASELINE','STABLE','COST_SAVING'}
    assert {p['plan_type'] for p in parent['result_snapshot']['plans']}==plan_types
    retry=client.post('/plan-executions',params=params,json=command)
    assert retry.status_code==200 and retry.json()=={'execution':parent,'reused':True}
    child_command={**command,'scenario':'WHAT_IF','base_plan_execution_id':parent['execution_id'],
                   'overrides':{'overtime_hours_limit.SAW1.2027-02':'80'}}
    what_if=client.post('/plans/what-if',params=params,json=child_command)
    assert what_if.status_code==200 and what_if.json()['persisted'] is False,what_if.json()
    assert client.get('/plan-executions',params=params).json()['total']==history+1
    child=client.post('/plan-executions',params=params,json=child_command)
    assert child.status_code==201,child.json()
    detail=child.json()['execution']
    assert detail['base_plan_execution_id']==parent['execution_id']
    assert detail['input_digest']==what_if.json()['input_digest']
    assert detail['input_snapshot']['base_plan_snapshot']['input_digest']==parent['input_digest']
    assert detail['input_snapshot']['base_plan_snapshot']['result_digest']==parent['result_digest']
    assert detail['result_snapshot']==what_if.json()['result']
    assert detail['result_digest']==digest(what_if.json()['result'])
    assert {p['plan_type'] for p in detail['result_snapshot']['plans']}==plan_types
    for key in ('forecast_rows','approved_inputs','capacity_snapshot','routing_snapshot','scheduled_receipts'):
        assert detail['input_snapshot'][key]==parent['input_snapshot'][key]
    child_retry=client.post('/plan-executions',params=params,json=child_command)
    assert child_retry.status_code==200 and child_retry.json()=={'execution':detail,'reused':True}
    path='/plan-executions/'+parent['execution_id']
    assert client.get(path,params=params).json()==parent
    assert client.get('/plan-executions/'+detail['execution_id'],params=params).json()==detail
    assert client.get(path,params={'dataset_id':'TISSUE-LEGACY'}).status_code==404
    foreign_params={'dataset_id':'TISSUE-LEGACY'}
    foreign={**child_command,**foreign_params}
    for target in ('/plans/what-if','/plan-executions'):
        blocked=client.post(target,params=foreign_params,json=foreign)
        assert blocked.status_code==404 and blocked.json()['detail']['code']=='PLAN_NOT_FOUND'

    # Inspect the same stored input with the real core. The public DTO carries stockout
    # reasons, but uses a nonnegative value for the affected safety-stock evaluation.
    from engine.adapter import to_internal
    from engine.planning_core import calculate_plans
    from what_if.core import apply_overrides
    sql_input=to_internal(PlanningInput.model_validate(parent['input_snapshot']))
    assert not sql_input.invalid and not sql_input.unsupported
    changed,errors=apply_overrides(sql_input.data,child_command['overrides'])
    assert not errors
    stable_base=calculate_plans(sql_input.data)['STABLE']
    stable_child=calculate_plans(changed)['STABLE']
    stockout=lambda result: sum(sum(values) for values in result.stockout.values())
    for stored,computed in ((parent,stable_base),(detail,stable_child)):
        rows=next(p['production'] for p in stored['result_snapshot']['plans'] if p['plan_type']=='STABLE')
        assert {(r['product_id'],r['period']):Decimal(r['production_qty']) for r in rows}=={
            (p,month):q for p,values in computed.production.items()
            for month,q in zip(computed.months,values,strict=True)}
    assert stockout(stable_child)<stockout(stable_base)
    record_property('stable_stockout_ea',f'{stockout(stable_base)} -> {stockout(stable_child)}')
    production=lambda result: sum(sum(values) for values in result.production.values())
    record_property('stable_production_ea',f'{production(stable_base)} -> {production(stable_child)}')

    approve=client.post(path+'/decisions',params=params,json={
        'plan_id':parent['result_snapshot']['plans'][0]['plan_id'],'action':'APPROVE',
        'actor_id':'TEST-REVIEWER','reason':'Approval remains disabled',
        'expected_version':parent['version'],'expected_input_digest':parent['input_digest']})
    assert approve.status_code==501 and approve.json()['detail']['code']=='PLAN_APPROVAL_DISABLED'

    tables=('plan_execution','plan_candidate','plan_constraint_evaluation','plan_material_requirement',
            'plan_execution_input','plan_review','plan_decision')
    def counts():
        with get_dataset_engine(dataset).connect() as connection:
            return {table:connection.execute(text(f'SELECT count(*) FROM {table}')).scalar_one() for table in tables}
    before_failure=counts()
    original_save=PlanRepository.save
    def fail_after_insert(connection,*args,**kwargs):
        original_save(connection,*args,**kwargs)
        connection.execute(text('SELECT 1 / 0'))
    with monkeypatch.context() as patch:
        patch.setattr(PlanRepository,'save',staticmethod(fail_after_insert))
        failed=client.post('/plan-executions',params=params,json={
            **child_command,'overrides':{'overtime_hours_limit.SAW1.2027-02':'79'}})
    assert failed.status_code==500 and failed.json()['detail']['code']=='PERSISTENCE_ERROR'
    assert counts()==before_failure
    assert client.get('/plan-executions',params=params).json()['total']==history+2
    assert client.get(path,params=params).json()==parent


def test_actual_cross_refs_rollback_unknown_and_archived(api):
    client,engine=api
    r=client.post('/batches',params={'dataset_id':'TISSUE-LEGACY'},files={'file':('cross.csv',b'capacity_id,resource_id,period,regular_hours,unit,time_basis,availability_basis\nCROSS,RW1,2027-01,1,h,MACHINE_HOUR,NET\n')},
        data={'entity':'capacity','source_type':'SYNTHETIC','source_note':'Synthetic rejected cross reference'})
    assert r.status_code==201 and r.json()['status']=='HAS_ERRORS';b=r.json()
    assert client.post('/batches/'+b['batch_id']+'/approve',json={'approved_by':'TEST-REVIEWER','expected_result_digest':b['result_digest']}).status_code==409
    assert client.get('/batches/'+b['batch_id'],params={'dataset_id':'CHUNGPAMO-2027'}).status_code==404
    assert client.get('/products',params={'dataset_id':'UNKNOWN'}).status_code==404
    with engine.begin() as c:
        c.execute(text("INSERT INTO public.dataset(dataset_id,dataset_name,description,source_type,status,schema_name) VALUES('ARCHIVED-TEST','Synthetic','Regression only','SYNTHETIC','ARCHIVED',:s)"),{'s':schema_for('ARCHIVED-TEST')})
    assert client.get('/products',params={'dataset_id':'ARCHIVED-TEST'}).status_code==409


def test_plan_dedup_lineage_concurrent_review_and_audit(api):
    client,engine=api;dataset='CHUNGPAMO-2027';p={'dataset_id':dataset}
    # This test also runs independently of the preceding parameterized forecast tests.
    forecast=client.post('/forecasts',params=p,json={'trained_until':'2026-12-31','horizon_months':3})
    assert forecast.status_code in (200,201),forecast.json()
    fid=forecast.json()['execution']['execution_id']
    snapshot=SqlPlanningSourceProvider(get_dataset_engine(dataset)).load(PlanCommand(dataset_id=dataset,forecast_execution_id=fid,product_ids=['CP-N3-3030'],target_month='2027-01',horizon_months=1,as_of_date='2026-12-31'))
    result=PlanningOutput.model_validate(json.loads((ROOT/'contracts/examples/integration/planning_output.json').read_text(encoding='utf-8'))['payload'])
    for plan in result.plans:
        for row in plan.production:row.product_id='CP-N3-3030'
    scoped=get_dataset_engine(dataset)
    with scoped.begin() as c:parent=PlanRepository.save(c,snapshot,result,{'test_double':True},'a'*64,origin='TEST_DOUBLE')
    assert client.get('/plan-executions/'+str(parent.execution_id),params=p).status_code==404
    assert client.get('/plan-executions/'+str(parent.execution_id)+'/export.xlsx',params=p).status_code==404
    with pytest.raises(ApiError):formal_export(parent)
    def duplicate():
        try:
            with scoped.begin() as c:PlanRepository.save(c,snapshot,result,{'test_double':True},'b'*64,origin='TEST_DOUBLE')
            return 'stored'
        except IntegrityError as e:return e.orig.sqlstate
    with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(lambda _:duplicate(),range(2)))
    assert sorted(out)==['23505','stored']
    child_cmd=PlanCommand(**{**snapshot.command.model_dump(),'scenario':'WHAT_IF','base_plan_execution_id':parent.execution_id,'overrides':{'demand_multiplier.CP-N3-3030':'100'}})
    child_input=what_if_snapshot(parent,child_cmd,allow_test=True)
    with scoped.begin() as c:child=PlanRepository.save(c,child_input,result,{'test_double':True},'c'*64,origin='TEST_DOUBLE')
    assert child.base_plan_execution_id==parent.execution_id
    with pytest.raises(ApiError):what_if_snapshot(parent,child_cmd.model_copy(update={'dataset_id':'TISSUE-LEGACY'}),allow_test=True)
    def review():
        try:
            with scoped.begin() as c:
                c.execute(text("""INSERT INTO plan_decision(decision_id,execution_id,plan_id,action,status_before,status_after,review_version,actor_id,auth_verified,reason,input_digest)
                    VALUES(:d,:e,:p,'REVIEW','DRAFT','REVIEW',1,'TEST-REVIEWER',false,'TEST-DOUBLE-ONLY',:h)"""),{'d':uuid4(),'e':parent.execution_id,'p':parent.result_snapshot.plans[0].plan_id,'h':parent.input_digest})
            return 'reviewed'
        except IntegrityError as e:return e.orig.sqlstate
    with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(lambda _:review(),range(2)))
    assert sorted(out)==['23514','reviewed']
    with pytest.raises(IntegrityError):
        with scoped.begin() as c:c.execute(text("UPDATE plan_decision SET reason='overwrite' WHERE execution_id=:e"),{'e':parent.execution_id})
    with scoped.connect() as c:
        stored=PlanRepository.detail(c,parent.execution_id,include_test=True)
        assert stored.version==2 and len(stored.decisions)==1
        assert stored.input_snapshot==snapshot
