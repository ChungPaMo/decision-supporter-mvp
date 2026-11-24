"""Development DB verification using PostgreSQL-enforced READ ONLY connections only.
Never calls upload, approve, forecast creation or migration/reset functions.
"""
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import sys
from uuid import UUID
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'modules/planning_engine'),str(ROOT)]


def fingerprint(engine):
    from sqlalchemy import text
    from app.dataset_schema_v2 import CORE_TABLES,schema_for
    result={}
    with engine.connect() as c:
        assert c.execute(text('SHOW transaction_read_only')).scalar()=='on'
        for scope in ('TISSUE-LEGACY','CHUNGPAMO-2027'):
            schema=schema_for(scope)
            tables=list(CORE_TABLES)+(['dataset','alembic_version'] if schema=='public' else [])
            for table in tables:
                rows=c.execute(text(f'SELECT row_to_json(t) FROM "{schema}"."{table}" t')).scalars().all()
                body='\n'.join(sorted(json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(',',':')) for r in rows))
                result[scope+'/'+table]={'count':len(rows),'sha256':hashlib.sha256(body.encode()).hexdigest()}
    return result


def main():
    from scripts.postgresql_preservation import compare, development_url, snapshot as development_snapshot
    from sqlalchemy import create_engine
    from fastapi.testclient import TestClient
    from app.api import batches, forecasts, plan_executions
    from app.config import Settings
    from app.integrations import planning
    from app.main import app
    from app.datasets import get_dataset_engine
    from app.integrations.planning import SqlPlanningSourceProvider
    from app.batches.sql_repository import SqlBatchTx
    from app.batches.capacity import preview
    from app.ingest.pipeline import run_preview
    from app.ingest.validation import MasterData
    from app.errors import ApiError
    from contracts.interfaces.planning import PlanCommand
    before=development_snapshot()
    assert before['revision']=='0009'
    readonly=create_engine(development_url(),connect_args={'connect_timeout':3,'options':'-c default_transaction_read_only=on'},pool_pre_ping=True)
    settings=Settings(_env_file=None,persistence='postgres',database_url=development_url().render_as_string(hide_password=False))
    checks=[];plans={};client=TestClient(app)
    def ok(name):checks.append(name)
    from app import db
    with patch.object(db,'get_engine',lambda:readonly), patch.object(batches,'get_settings',lambda:settings), \
            patch.object(forecasts,'get_settings',lambda:settings), patch.object(planning,'get_settings',lambda:settings), \
            patch.object(plan_executions,'get_settings',lambda:settings):
        expected={'TISSUE-LEGACY':{'/products':1,'/materials':3,'/boms':1,'/inventory':4,'/demand/monthly':24,'/capacity':5,'/routings':1,'/batches':7},
                  'CHUNGPAMO-2027':{'/products':9,'/materials':9,'/boms':9,'/inventory':18,'/demand/monthly':498,'/capacity':27,'/routings':27,'/batches':9}}
        for dataset,paths in expected.items():
            for path,total in paths.items():
                params={'dataset_id':dataset,'limit':1}
                response=client.get(path,params=params);assert response.status_code==200,(path,response.json())
                page=response.json();assert page['total']==total and len(page['items'])==1,(path,page)
                empty=client.get(path,params={**params,'offset':total}).json()
                assert empty['total']==total and empty['items']==[]
            ok(dataset+': all eight query APIs and total/offset isolated')
        assert client.get('/products').json()['total']==1
        assert client.get('/products',params={'dataset_id':'UNKNOWN'}).status_code==404
        assert client.get('/products',params={'dataset_id':'../public'}).status_code==422
        ok('omission is legacy-only; unknown and invalid datasets rejected')
        executions={}
        for dataset in expected:
            page=client.get('/forecasts',params={'dataset_id':dataset}).json();assert page['total']==1
            execution=client.get('/forecasts/'+page['items'][0]['execution_id'],params={'dataset_id':dataset}).json()
            assert execution['dataset_id']==dataset
            assert execution['input_digest']!=execution['dataset_input_digest']
            assert execution['result']['run']['input_digest']==execution['input_digest']
            ids={r['batch_id'] for r in execution['input_batches']}
            batch_rows=client.get('/batches',params={'dataset_id':dataset,'limit':200}).json()['items']
            assert ids<={b['batch_id'] for b in batch_rows if b['status']=='APPROVED' and b['entity']=='monthly_demand'}
            executions[dataset]=execution
            horizon=3 if dataset=='CHUNGPAMO-2027' else 1
            command=PlanCommand(dataset_id=dataset,forecast_execution_id=UUID(execution['execution_id']),product_ids=sorted(r['product_id'] for r in client.get('/products',params={'dataset_id':dataset}).json()['items']),target_month='2027-01',horizon_months=horizon,as_of_date='2026-12-31')
            body = command.model_dump(mode='json')
            report = client.post('/planning-inputs/preview', params={'dataset_id':dataset}, json=body)
            diagnostics = report.json()
            if report.status_code == 409 and diagnostics['detail']['code'] == 'PLAN_INPUT_UNAVAILABLE':
                plans[dataset] = {'horizon_months': horizon, 'input_blocker': diagnostics['detail']}
            else:
                assert report.status_code == 200 and diagnostics['engine_available'], report.status_code
                snapshot=SqlPlanningSourceProvider(get_dataset_engine(dataset)).load(command)
                assert snapshot.dataset_id==dataset
                assert {s.batch_id for s in snapshot.approved_inputs.sources}<={UUID(b['batch_id']) for b in batch_rows}
                assert all(r.product_id in command.product_ids for r in snapshot.forecast_rows)
                assert planning.snapshot_digest(snapshot) == diagnostics['input_digest']
                preview = client.post('/plans', params={'dataset_id':dataset}, json=body)
                outcome = preview.json().get('result')
                assert preview.status_code in (200, 422) and outcome is not None, preview.status_code
                assert preview.json()['persisted'] is False and preview.json()['input_digest'] == diagnostics['input_digest']
                plans[dataset] = {'inputs':diagnostics['inputs'], 'missing_inputs':diagnostics['missing_inputs'],
                    'diagnostic_warnings':diagnostics['warning_codes'], 'input_digest':diagnostics['input_digest'],
                    'horizon_months':horizon, 'status':outcome['status'], 'errors':outcome['errors'],
                    'warnings':outcome['warnings'], 'unverified':outcome['unverified'],
                    'constraint_findings':[row for row in outcome['constraint_evaluations'] if row['status']!='SATISFIED'],
                    'version_evidence':[issue for issue in outcome['evidence'] if issue['code'].endswith('VERSION_SELECTED')],
                    'candidates':[{k:row[k] for k in ('plan_type','feasibility','unverified')} for row in outcome['plans']]}
            assert client.get('/plan-executions',params={'dataset_id':dataset}).status_code==200
            unknown='00000000-0000-0000-0000-000000000000'
            assert client.get('/plan-executions/'+unknown,params={'dataset_id':dataset}).status_code==404
            assert client.get('/plan-executions/not-a-uuid',params={'dataset_id':dataset}).status_code==422
            assert client.get('/plan-executions/'+unknown+'/export.xlsx',params={'dataset_id':dataset}).status_code==404
            ok(dataset+': read-only input diagnostics, optional engine preview, history query and missing execution checks')
        for source,target in [('TISSUE-LEGACY','CHUNGPAMO-2027'),('CHUNGPAMO-2027','TISSUE-LEGACY')]:
            foreign=executions[source]['execution_id']
            assert client.get('/forecasts/'+foreign,params={'dataset_id':target}).status_code==404
            try:SqlPlanningSourceProvider(get_dataset_engine(target)).load(PlanCommand(dataset_id=target,forecast_execution_id=UUID(foreign),product_ids=['TP-10R'],target_month='2027-01',horizon_months=1,as_of_date='2026-12-31'))
            except ApiError as exc:assert exc.status==404
            else:raise AssertionError('Foreign forecast accepted')
        ok('forecast UUID cross-access rejected in both API and actual SQL provider')
        with get_dataset_engine('CHUNGPAMO-2027').connect() as c:
            tx=SqlBatchTx(c);master=MasterData({p.product_id:p for p in tx.list_known_products()},{m.material_id:m for m in tx.list_known_materials()},tx.list_known_boms())
            data=b'bom_id,product_id,bom_version,status,is_active,valid_from,base_qty,line_no,component_type,component_id,qty_per,unit,scrap_rate\nPROBE,TP-10R,V1,APPROVED,Y,2026-01-01,1,1,MATERIAL,MR-N3,1,kg,0\n'
            result=run_preview('cross.csv',data,'bom',master=master)
            assert result.status=='HAS_ERRORS'
        with get_dataset_engine('TISSUE-LEGACY').connect() as c:
            data=b'resource_id,reference_qty,quantity_unit,run_time,time_unit,time_basis,routing_id,routing_version,step_id,product_id,operation_id,predecessor_step_ids,valid_from\nRW1,1,EA,1,h,MACHINE_HOUR,PROBE,V1,PACK,TP-10R,PACK,[],2026-01-01\n'
            assert preview(SqlBatchTx(c),'cross.csv',data,'routing',{},None).status=='HAS_ERRORS'
        ok('real scoped master validators reject legacy product in CP BOM and CP resource in legacy routing; no staging writes')
    after=development_snapshot();compare(before,after);assert before['objects']==after['objects']
    artifact=ROOT/'.artifacts/readonly_dataset_api.json';artifact.parent.mkdir(exist_ok=True)
    artifact.write_text(json.dumps({'passed':len(checks),'failed':0,'checks':checks,'planning':plans,'before':before,'after':after},indent=2,default=str),encoding='utf-8')
    readonly.dispose()
    print(json.dumps({'passed':len(checks),'failed':0,'checks':checks,'development_data_unchanged':True},indent=2))


if __name__=='__main__':main()
