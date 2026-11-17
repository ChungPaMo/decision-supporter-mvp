"""Existing development DB additive upgrade, ONLY after separate user approval.

Requires unchanged preflight fingerprints and verified private backup. Never resets,
downgrades, restores or retries automatically. Token is not a substitute for consent.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]
APPROVAL = '0009@127.0.0.1:55433/chungpamo'


def main():
    if os.environ.get('CHUNGPAMO_ALLOW_DEV_MIGRATION') != APPROVAL:
        raise RuntimeError('Separate user approval for development 0009 is required')
    from scripts.postgresql_preservation import OUT, compare, development_url, snapshot
    before = json.loads((OUT / 'development-before.json').read_text(encoding='utf-8'))
    current = json.loads(json.dumps(snapshot(), default=str))
    compare(before, current)
    assert current['revision'] == '0008'
    metadata = json.loads((OUT / 'backup-metadata.json').read_text(encoding='utf-8'))
    backup = OUT / 'chungpamo-before-0009.dump'
    assert metadata['toc_validated'] and backup.stat().st_size == metadata['bytes']
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == metadata['sha256']
    with backup.open('rb') as stream:
        listing = subprocess.run(['docker', 'exec', '-i', 'chungpamo-monorepo-db', 'pg_restore', '--list'], stdin=stream, capture_output=True)
    assert listing.returncode == 0
    # Only the existing migration is applied; credentials travel through env, not argv/log.
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', '0009'], cwd=ROOT / 'backend',
        env={**os.environ, 'DATABASE_URL': development_url().render_as_string(hide_password=False)}, capture_output=True)
    (OUT / '0009-apply.log').write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('0009 failed; private log preserved. No reset/downgrade/automatic restore attempted.')
    after = json.loads(json.dumps(snapshot(), default=str))
    compare(before, after, allow_0009=True)
    (OUT / 'development-after.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
    print('Applied 0009. Existing rows/registry/DB objects/Docker identity unchanged; four new history tables empty.')


if __name__ == '__main__':
    main()
