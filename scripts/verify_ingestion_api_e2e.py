"""Run the official-data TestClient journey and handoff checks; never connect to a DB."""
from pathlib import Path
import os
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    (root / '.artifacts').mkdir(exist_ok=True)
    result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'pytest', '--no-db', '-q', '--tb=short',
        'backend/tests/test_ingestion_api_e2e.py', 'backend/tests/test_ingestion_sales_generated.py',
        'backend/tests/test_ingestion_ui_contract.py', '--junitxml=.artifacts/ingestion-api-e2e.xml'],
        cwd=root, env={**os.environ, 'PERSISTENCE': 'disabled'})
    print('TEST-DOUBLE-ONLY: .artifacts/ingestion_api_e2e.json; no SQL or database approval evidence.')
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
