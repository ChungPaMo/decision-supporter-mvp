"""New assistance APIs against existing approved development masters, enforced READ ONLY.

Creates/compares ignored fingerprints only. Never uploads, approves or resets DB data.
"""
from pathlib import Path
from unittest.mock import patch
import argparse
import csv
import io
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]


def main():
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from app.main import app
    from app import db
    from app.api import batches
    from app.config import Settings
    from contracts.interfaces.ingestion import SalesTransformPolicy
    from scripts.seed_tissue_capacity import verify_target
    from scripts.verify_readonly_dataset_api import fingerprint
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-baseline', action='store_true')
    args = parser.parse_args()
    base = verify_target()
    readonly = create_engine(base.url, connect_args={'options': '-c default_transaction_read_only=on', 'connect_timeout': 3})
    base.dispose()
    artifact = ROOT / '.artifacts/ingestion_development_fingerprints.json'
    before = fingerprint(readonly)
    original = before
    if args.check_baseline:
        original = json.loads(artifact.read_text(encoding='utf-8'))['before']
        assert original == before, 'Development contents changed since pre-regression verification'
    elif artifact.exists():
        raise RuntimeError('Existing verification evidence preserved; use --check-baseline or inspect privately')
    settings = Settings(_env_file=None, persistence='postgres', database_url=readonly.url.render_as_string(hide_password=False))
    checks = []
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['주문일자', '제품코드', '수량', '단위', '구분', '주문번호', '행번호'])
    writer.writerow(['2026-01-02', 'CP-N3-3030', '1', '팩', '정상', 'READONLY-PROBE', '1'])
    raw = stream.getvalue().encode()
    with patch.object(db, 'get_engine', lambda: readonly), patch.object(batches, 'get_settings', lambda: settings):
        client = TestClient(app)
        for dataset, match in [('CHUNGPAMO-2027', 1), ('TISSUE-LEGACY', 0)]:
            params = {'dataset_id': dataset}
            profile = client.post('/ingest/profile', params=params,
                files={'file': ('synthetic.csv', b'product_id,quantity\nCP-N3-3030,1\n')}, data={'use_approved_master': 'true'})
            assert profile.status_code == 200, profile.json()
            assert profile.json()['sheets'][0]['columns'][0]['known_product_match_ratio'] == match
            assert profile.json()['master_scope'] == dataset
            policy = SalesTransformPolicy(dataset_id=dataset)
            preview = client.post('/ingest/transform-preview', params=params, files=[('files', ('synthetic.csv', raw))],
                data={'policy': policy.model_dump_json(), 'use_approved_master': 'true'})
            assert preview.status_code == 200, preview.json()
            assert preview.json()['status'] == ('POLICY_REVIEW_REQUIRED' if match else 'HAS_ERRORS')
            assert not preview.json()['persisted'] and not preview.json()['auto_approve']
            checks.append(dataset + ': measured approved-master scope and no persistence before confirmation')
    after = fingerprint(readonly)
    assert before == after == original
    artifact.parent.mkdir(exist_ok=True)
    artifact.write_text(json.dumps({'before': original, 'after': after, 'checks': checks}, indent=2), encoding='utf-8')
    readonly.dispose()
    print('2 scoped assistance API groups passed; 56/56 development table fingerprints unchanged; READ ONLY enforced.')


if __name__ == '__main__':
    main()
