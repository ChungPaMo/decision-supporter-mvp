"""Authorized disposable DB runner. Never derives a test URL from development credentials."""
from pathlib import Path
import os
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]


def main(args=None):
    from dotenv import dotenv_values
    from scripts.verify_test_db import authorize_reset
    config=dotenv_values(ROOT/'.env.regression.local')
    if not config.get('TEST_DATABASE_URL'):raise RuntimeError('Explicit ignored regression configuration required')
    # Do not turn user approval on automatically. Set the documented token only after approval.
    os.environ['TEST_DATABASE_URL']=config['TEST_DATABASE_URL']
    authorize_reset()
    import pytest
    return pytest.main(args or ['-q','--tb=short','--junitxml=.artifacts/db_regression_final.xml'])


if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
