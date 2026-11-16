"""Non-destructive SYNTHETIC seed via actual API; dedicated development DB only.
No migration/reset is performed. Existing records must match this seed exactly.
Run from repository root: .venv/Scripts/python scripts/seed_tissue_capacity.py
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'modules/planning_engine'), str(ROOT)]


def verify_target():
    from app.config import get_settings
    from sqlalchemy.engine import make_url
    from sqlalchemy import create_engine, text
    u = get_settings().database_url
    v = make_url(u)
    if (v.host,v.port,v.database,v.username)!=('127.0.0.1',55433,'chungpamo','chungpamo_app'):
        raise RuntimeError('STOP unexpected development DB target')
    result = subprocess.run(['docker','inspect','chungpamo-monorepo-db'],check=True,capture_output=True,text=True)
    d = json.loads(result.stdout)[0]
    assert d['Config']['Labels']['com.docker.compose.project']=='chungpamo-monorepo'
    assert d['HostConfig']['PortBindings']['5432/tcp']==[{'HostIp':'127.0.0.1','HostPort':'55433'}]
    assert {m['Name'] for m in d['Mounts'] if m['Type']=='volume'}=={'chungpamo-monorepo-pgdata'}
    assert set(d['NetworkSettings']['Networks'])=={'chungpamo-monorepo-net'}
    e = create_engine(u)
    with e.connect() as c:
        actual = c.execute(text('SELECT current_database(),current_user')).one()
        assert tuple(actual)==('chungpamo','chungpamo_app')
        assert c.execute(text('SELECT version_num FROM alembic_version')).scalar() in ('0006','0007','0008','0009')
    return e


def seed():
    e = verify_target()
    os.environ['PERSISTENCE']='postgres'
    from fastapi.testclient import TestClient
    from app.main import app
    from sqlalchemy import text
    client = TestClient(app)
    expected = [('product','tissue_products.csv'),('material','tissue_materials.csv'),('bom','tissue_bom.csv'),
                ('inventory','tissue_inventory.csv'),('monthly_demand','tissue_demand.csv'),
                ('capacity','tissue_capacity/capacity_upload.xlsx'),('routing','tissue_capacity/routing_upload.xlsx')]
    # Preflight every entity before the first write, not only when its turn arrives.
    with e.connect() as c:
        for entity,path in expected:
            digest=hashlib.sha256((ROOT/'contracts/examples'/path).read_bytes()).hexdigest()
            existing=c.execute(text("SELECT source_type,source_sha256 FROM import_batch WHERE entity=:e AND status<>'REJECTED'"),{'e':entity}).mappings().all()
            if any(r['source_type']!='SYNTHETIC' or r['source_sha256']!=digest for r in existing):
                raise RuntimeError('STOP conflicting existing data before seed: '+entity)
    reports=[]
    for entity,path in expected:
        file = ROOT/'contracts/examples'/path
        data = file.read_bytes();sha=hashlib.sha256(data).hexdigest()
        with e.connect() as c:
            matches=c.execute(text("SELECT batch_id,status,source_type,source_sha256 FROM import_batch WHERE entity=:e AND status<>'REJECTED'"),{'e':entity}).mappings().all()
        # Seed is intended for a fresh dedicated development DB. Never silently merge business data.
        if any(r['source_type']!='SYNTHETIC' or r['source_sha256']!=sha for r in matches):
            raise RuntimeError('STOP existing entity data differs from the integration seed: '+entity)
        if matches:
            r=client.get('/batches/'+str(matches[0]['batch_id']))
        else:
            r=client.post('/batches',files={'file':(file.name,data)},data={'entity':entity,'source_type':'SYNTHETIC',
                'source_note':'TISSUE-CAPACITY-BASE-01; fixed synthetic integration literals, not measured company data', 'created_by':'SEED-INTEGRATION'})
        if r.status_code not in (200,201): raise RuntimeError(f'{entity} upload failed: {r.status_code} {r.json()}')
        b=r.json()
        if b['status']=='READY_FOR_APPROVAL':
            r=client.post('/batches/'+b['batch_id']+'/approve',json={'approved_by':'REVIEWER-INTEGRATION','expected_result_digest':b['result_digest']})
            if r.status_code!=200: raise RuntimeError(f'{entity} approval failed: {r.status_code} {r.json()}')
            b=r.json()
        if b['status']!='APPROVED': raise RuntimeError(f'{entity} is {b["status"]}: {b.get("validation")}')
        reports.append({k:b[k] for k in ('batch_id','entity','status','version','approved_record_count','result_digest')})
    for path in ('/capacity','/routings'):
        r=client.get(path);assert r.status_code==200
        print(path, 'approved rows',r.json()['total'])
    print(json.dumps(reports,indent=2))
    e.dispose()
    return reports


if __name__=='__main__': seed()
