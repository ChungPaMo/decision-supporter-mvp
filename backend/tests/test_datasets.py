"""Dataset routing contracts; no real DB and no owner algorithm changes."""
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from app.main import app
from app.api.datasets import dataset_context,get_repository
from app.api.batches import get_service
from app.datasets import DatasetEngine,check_id,schema_for,get_dataset_engine
from app.batches.service import BatchService
from app.errors import ApiError,ErrorCode
from tests.fakes import InMemoryBatchRepository
from contracts.interfaces.planning import PlanCommand,PlanningInput


@pytest.mark.parametrize('bad',['','public','../public','OTHER;SET','a'*41,'A"B'])
def test_untrusted_schema_names_never_enter_sql(bad):
    with pytest.raises(ApiError):schema_for(bad)


def test_connection_scope_is_transaction_local_and_options_precede_statements():
    events=[]
    class Connection:
        def execution_options(self,**opts):events.append(('options',opts));return self
        def exec_driver_sql(self,q):events.append(q)
        def close(self):events.append('closed')
    class Engine:
        def connect(self):return Connection()
    scoped=DatasetEngine(Engine(),'CHUNGPAMO-2027',schema_for('CHUNGPAMO-2027'))
    with scoped.connect().execution_options(isolation_level='REPEATABLE READ'):pass
    assert events[0][0]=='options'
    assert events[1].endswith(', pg_catalog') and 'public' not in events[1]
    assert events[-1]=='closed'
    with pytest.raises(ValueError):DatasetEngine(Engine(),'CHUNGPAMO-2027','public')


def test_unknown_and_archived_datasets_do_not_fallback(monkeypatch):
    from app import db
    row={'dataset_id':'CHUNGPAMO-2027','schema_name':schema_for('CHUNGPAMO-2027'),'status':'ARCHIVED'}
    class C:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,*args):return SimpleNamespace(mappings=lambda:SimpleNamespace(first=lambda:row))
    monkeypatch.setattr(db,'get_engine',lambda:SimpleNamespace(connect=lambda:C()))
    with pytest.raises(ApiError) as e:get_dataset_engine('CHUNGPAMO-2027')
    assert e.value.code==ErrorCode.DATASET_INACTIVE
    row=None
    with pytest.raises(ApiError) as e:get_dataset_engine('CHUNGPAMO-2027')
    assert e.value.code==ErrorCode.DATASET_NOT_FOUND


def test_two_memory_datasets_same_codes_refs_and_page_totals():
    repositories={d:InMemoryBatchRepository() for d in ('TISSUE-LEGACY','CHUNGPAMO-2027')}
    for d,repo in repositories.items():repo.dataset_id=d
    def scoped(dataset_id:str=Depends(dataset_context)):
        if dataset_id not in repositories:raise ApiError(404,ErrorCode.DATASET_NOT_FOUND,'No dataset')
        return BatchService(repositories[dataset_id])
    app.dependency_overrides[get_service]=scoped
    try:
        client=TestClient(app)
        data=b'product_id,product_name,base_unit,product_type,safety_stock_qty\nSAME,Synthetic,EA,FINISHED,0\n'
        ids={}
        for d in repositories:
            r=client.post('/batches',params={'dataset_id':d},files={'file':('p.csv',data)},data={'entity':'product','source_type':'SYNTHETIC','source_note':'Dataset contract test'})
            b=r.json();assert r.status_code==201 and b['dataset_id']==d
            ids[d]=b['batch_id']
            r=client.post('/batches/'+b['batch_id']+'/approve',params={'dataset_id':d},json={'approved_by':'TEST-REVIEWER','expected_result_digest':b['result_digest']})
            assert r.status_code==200
            duplicate=client.post('/batches',params={'dataset_id':d},files={'file':('p.csv',data)},data={'entity':'product'})
            assert duplicate.status_code==409
            info = duplicate.json()['detail']['details']
            assert info['dataset_id'] == d and info['batch_id'] == b['batch_id']
            assert info['source_sha256'] == b['file']['sha256']
        assert client.get('/products').json()['total']==1 # Compatibility defaults to legacy ONLY.
        for d in repositories:
            page=client.get('/products',params={'dataset_id':d,'limit':1,'offset':0}).json()
            assert page['total']==1 and page['items'][0]['product_id']=='SAME'
            assert client.get('/products',params={'dataset_id':d,'offset':1}).json()['items']==[]
        assert client.get('/batches/'+ids['TISSUE-LEGACY'],params={'dataset_id':'CHUNGPAMO-2027'}).status_code==404
        assert client.post('/batches/'+ids['TISSUE-LEGACY']+'/approve',params={'dataset_id':'CHUNGPAMO-2027'},json={'approved_by':'TEST-REVIEWER','expected_result_digest':'0'*64}).status_code==404
        assert client.get('/products',params={'dataset_id':'UNKNOWN'}).status_code==404
    finally:app.dependency_overrides.pop(get_service,None)


def test_plan_context_and_what_if_dataset_cannot_be_changed():
    from app.integrations.planning_validation import validate_pair
    from app.plans.service import what_if_snapshot
    from app.api.integrations import scoped_command
    from app.integrations.planning import SqlPlanningSourceProvider
    command=PlanCommand(dataset_id='CHUNGPAMO-2027',forecast_execution_id=UUID(int=1),product_ids=['SAME'],target_month='2027-01',as_of_date='2026-12-31')
    with pytest.raises(ApiError):scoped_command(command,'TISSUE-LEGACY')
    with pytest.raises(ApiError):SqlPlanningSourceProvider(SimpleNamespace(dataset_id='TISSUE-LEGACY')).load(command)
    base=SimpleNamespace(dataset_id='TISSUE-LEGACY',data_origin='REAL_ENGINE',input_snapshot=SimpleNamespace(command=command))
    with pytest.raises(ApiError) as e:what_if_snapshot(base,command)
    assert e.value.code==ErrorCode.DATASET_MISMATCH


def test_dataset_changes_plan_digest_without_touching_engine_algorithm():
    from app.plans.repository import digest
    from app.forecast.runs_schemas import ForecastExecutionSummary
    a={'dataset_id':'TISSUE-LEGACY','value':'1'};b={**a,'dataset_id':'CHUNGPAMO-2027'}
    assert digest(a)!=digest(b)
    # Computed scope digest distinguishes identical engine digests without changing the engine contract.
    a=ForecastExecutionSummary.model_construct(dataset_id='TISSUE-LEGACY',input_digest='sha256:'+'a'*64)
    b=ForecastExecutionSummary.model_construct(dataset_id='CHUNGPAMO-2027',input_digest='sha256:'+'a'*64)
    assert a.dataset_input_digest!=b.dataset_input_digest


def test_form_dataset_cannot_silently_override_legacy_query_default():
    app.dependency_overrides[get_service]=lambda:BatchService(InMemoryBatchRepository())
    try:
        r=TestClient(app).post('/batches',files={'file':('p.csv',b'product_id,product_name,base_unit\nP,Synthetic,EA\n')},
                              data={'entity':'product','dataset_id':'CHUNGPAMO-2027'})
        assert r.status_code==409 and r.json()['detail']['code']=='DATASET_MISMATCH'
    finally:app.dependency_overrides.pop(get_service,None)
