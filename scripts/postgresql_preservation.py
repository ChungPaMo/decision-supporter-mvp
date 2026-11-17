"""Read-only development DB evidence/backup. No reset, restore or migration command.

All evidence is private under .artifacts; credentials are never emitted.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]
OUT = ROOT / '.artifacts/postgresql-ingestion-20261117'


def docker_identity():
    item = json.loads(subprocess.check_output(['docker', 'inspect', 'chungpamo-monorepo-db'], encoding='utf-8'))[0]
    assert item['Config']['Labels']['com.docker.compose.project'] == 'chungpamo-monorepo'
    assert item['State']['Health']['Status'] == 'healthy'
    assert item['HostConfig']['PortBindings']['5432/tcp'] == [{'HostIp': '127.0.0.1', 'HostPort': '55433'}]
    assert {m['Name'] for m in item['Mounts'] if m['Type'] == 'volume'} == {'chungpamo-monorepo-pgdata'}
    assert set(item['NetworkSettings']['Networks']) == {'chungpamo-monorepo-net'}
    return {'container_id': item['Id'], 'project': 'chungpamo-monorepo', 'image': item['Config']['Image'],
            'volume': 'chungpamo-monorepo-pgdata', 'network': 'chungpamo-monorepo-net', 'port': 55433}


def development_url():
    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url
    url = make_url(dotenv_values(ROOT / '.env')['DATABASE_URL'])
    assert (url.drivername, url.host, url.port, url.database, url.username) == (
        'postgresql+psycopg', '127.0.0.1', 55433, 'chungpamo', 'chungpamo_app')
    assert not url.query
    return url


def snapshot():
    from sqlalchemy import create_engine, text
    from app.dataset_schema_v1 import schema_for
    identity = docker_identity()
    engine = create_engine(development_url(), connect_args={'options': '-c default_transaction_read_only=on', 'connect_timeout': 3})
    tables, summaries = {}, {}
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
            assert tuple(c.execute(text('SELECT current_database(),current_user')).one()) == ('chungpamo', 'chungpamo_app')
            assert c.execute(text('SHOW transaction_read_only')).scalar() == 'on'
            revision = c.execute(text('SELECT version_num FROM public.alembic_version')).scalar_one()
            datasets = [dict(r) for r in c.execute(text('SELECT * FROM public.dataset ORDER BY dataset_id')).mappings()]
            for row in datasets:
                schema = row['schema_name']
                assert schema == schema_for(row['dataset_id'])
                names = c.execute(text('SELECT tablename FROM pg_tables WHERE schemaname=:s ORDER BY tablename'), {'s': schema}).scalars()
                for name in names:
                    rows = c.execute(text(f'SELECT row_to_json(t)::text FROM "{schema}"."{name}" t')).scalars().all()
                    # Hash PostgreSQL's text directly: no JSON-float conversion of NUMERIC values.
                    encoded = '\n'.join(sorted(rows))
                    tables[schema + '.' + name] = {'rows': len(rows), 'sha256': hashlib.sha256(encoded.encode()).hexdigest()}
                summaries[row['dataset_id']] = {
                    'batches': [dict(r) for r in c.execute(text(f'SELECT entity,status,count(*) AS n FROM "{schema}".import_batch GROUP BY entity,status ORDER BY entity,status')).mappings()],
                    'forecast_runs': c.execute(text(f'SELECT count(*) FROM "{schema}".forecast_run')).scalar_one()}
            objects = {}
            queries = [
                ('function', "SELECT n.nspname||'.'||p.oid::regprocedure::text AS name,pg_get_functiondef(p.oid) AS definition FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=ANY(:schemas) AND p.prokind='f'"),
                ('trigger', "SELECT n.nspname||'.'||t.relname||'.'||g.tgname AS name,pg_get_triggerdef(g.oid) AS definition FROM pg_trigger g JOIN pg_class t ON t.oid=g.tgrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname=ANY(:schemas) AND NOT g.tgisinternal"),
                ('constraint', "SELECT n.nspname||'.'||t.relname||'.'||k.conname AS name,pg_get_constraintdef(k.oid) AS definition FROM pg_constraint k JOIN pg_class t ON t.oid=k.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname=ANY(:schemas)"),
                ('view', "SELECT schemaname||'.'||viewname AS name,definition FROM pg_views WHERE schemaname=ANY(:schemas)")]
            for kind, query in queries:
                for row in c.execute(text(query), {'schemas': [r['schema_name'] for r in datasets]}).mappings():
                    objects[kind + ':' + row['name']] = hashlib.sha256(row['definition'].encode()).hexdigest()
            return {'docker': identity, 'revision': revision, 'datasets': datasets, 'tables': tables, 'objects': objects, 'summary': summaries}
    finally:
        engine.dispose()


def compare(before, after, allow_0009=False):
    assert before['docker'] == after['docker'], 'Docker resource identity changed'
    assert before['datasets'] == after['datasets'], 'Dataset registry changed'
    assert before['summary'] == after['summary'], 'Approved batches/forecast history changed'
    for table, evidence in before['tables'].items():
        if allow_0009 and table == 'public.alembic_version':
            continue
        assert after['tables'].get(table) == evidence, 'Existing table data changed: ' + table
    for name, sha in before['objects'].items():
        assert after['objects'].get(name) == sha, 'Existing DB object changed: ' + name
    if allow_0009:
        assert before['revision'] == '0008' and after['revision'] == '0009'
        new = set(after['tables']) - set(before['tables'])
        assert new == {r['schema_name'] + '.' + t for r in after['datasets'] for t in ('ingestion_transformation', 'ingestion_transform_source')}
        assert all(after['tables'][t]['rows'] == 0 for t in new)
    else:
        assert before['revision'] == after['revision'] and before['tables'] == after['tables']


def backup():
    from dotenv import dotenv_values
    state = snapshot()
    assert state['revision'] == '0008', 'Backup preparation expects the inspected pre-upgrade revision'
    destination = OUT / 'chungpamo-before-0009.dump'
    if destination.exists():
        raise RuntimeError('Existing backup preserved; refusing overwrite')
    admin = dotenv_values(ROOT / '.env').get('POSTGRES_ADMIN_USER', 'chungpamo_admin')
    OUT.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as output:
        result = subprocess.run(['docker', 'exec', 'chungpamo-monorepo-db', 'pg_dump', '--no-password', '-U', admin, '-d', 'chungpamo', '-Fc'], stdout=output, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError('Read-only backup failed; partial private artifact preserved')
    with destination.open('rb') as stream:
        listing = subprocess.run(['docker', 'exec', '-i', 'chungpamo-monorepo-db', 'pg_restore', '--list'], stdin=stream, capture_output=True)
    assert listing.returncode == 0 and listing.stdout
    (OUT / 'backup-toc.txt').write_bytes(listing.stdout)
    metadata = {'bytes': destination.stat().st_size, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                'format': 'pg_dump custom', 'toc_validated': True, 'restore_rehearsal': False}
    (OUT / 'backup-metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    compare(state, snapshot())
    print(json.dumps(metadata))


def verify_api():
    """GET only, with PostgreSQL-enforced READ ONLY on every application connection."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from app.main import app
    from app import db
    from app.api import batches, forecasts, ingest_history
    from app.config import Settings
    before = snapshot()
    assert before['revision'] == '0009'
    engine = create_engine(development_url(), connect_args={'options': '-c default_transaction_read_only=on'})
    settings = Settings(_env_file=None, persistence='postgres', database_url=development_url().render_as_string(hide_password=False))
    checked = 0
    try:
        with patch.object(db, 'get_engine', lambda: engine), patch.object(batches, 'get_settings', lambda: settings), \
             patch.object(forecasts, 'get_settings', lambda: settings), patch.object(ingest_history, 'get_settings', lambda: settings):
            client = TestClient(app)
            for dataset in before['datasets']:
                params = {'dataset_id': dataset['dataset_id']}
                schema = dataset['schema_name']
                endpoints = {'/products': 'product', '/materials': 'material', '/boms': 'bom_header',
                    '/inventory': 'inventory', '/demand/monthly': 'monthly_demand', '/routings': 'production_routing_step',
                    '/batches': 'import_batch', '/forecasts': 'forecast_run', '/ingest/transformations': 'ingestion_transformation'}
                for path, table in endpoints.items():
                    response = client.get(path, params=params)
                    assert response.status_code == 200, (path, response.status_code)
                    assert response.json()['total'] == before['tables'][schema + '.' + table]['rows'], path
                    checked += 1
                response = client.get('/capacity', params=params)
                assert response.status_code == 200
                expected = sum(before['tables'][schema + '.' + t]['rows'] for t in
                    ('production_resource', 'production_quantity_limit', 'production_hours_budget'))
                assert response.json()['total'] == expected
                checked += 1
                missing = client.get('/ingest/transformations/00000000-0000-0000-0000-000000000000', params=params)
                assert missing.status_code == 404
                checked += 1
                executions = client.get('/forecasts', params=params).json()['items']
                for row in executions:
                    assert client.get('/forecasts/' + row['execution_id'], params=params).status_code == 200
                    checked += 1
        compare(before, snapshot())
        result = {'get_checks_passed': checked, 'postgresql_read_only': True, 'tables_unchanged': len(before['tables'])}
        (OUT / 'development-api-readonly.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['before', 'compare', 'backup', 'api'])
    parser.add_argument('--allow-0009', action='store_true', help='Comparison only; never permission to migrate')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = OUT / 'development-before.json'
    if args.action == 'api':
        verify_api()
        return
    if args.action == 'backup':
        backup()
        return
    current = snapshot()
    if args.action == 'before':
        with baseline.open('x', encoding='utf-8') as stream:
            json.dump(current, stream, indent=2, default=str)
    else:
        previous = json.loads(baseline.read_text(encoding='utf-8'))
        # Registry timestamps use stable ISO serialization in persisted snapshots.
        current = json.loads(json.dumps(current, default=str))
        compare(previous, current, args.allow_0009)
        (OUT / 'development-after.json').write_text(json.dumps(current, indent=2), encoding='utf-8')
    print(json.dumps({'revision': current['revision'], 'tables': len(current['tables']), 'summary': current['summary']}, default=str))


if __name__ == '__main__':
    main()
