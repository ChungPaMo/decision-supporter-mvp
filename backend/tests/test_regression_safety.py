"""No DB calls: reject wrong URL/role/approval before Docker or SQL access."""
from types import SimpleNamespace
import pytest
from sqlalchemy.engine import make_url
from scripts import verify_test_db as guard

VALID='postgresql+psycopg://chungpamo_regression_runner:UNRELATED-TEST-SECRET@127.0.0.1:55433/chungpamo_regression'


@pytest.mark.parametrize('target',[
    VALID.replace('/chungpamo_regression','/chungpamo'),
    VALID.replace('/chungpamo_regression','/chungpamo_test'),
    VALID.replace('55433','55432'),VALID.replace('127.0.0.1','localhost'),
    VALID.replace('chungpamo_regression_runner','chungpamo_app'),
    VALID.replace('chungpamo_regression_runner','postgres'),
    VALID+'?options=-csearch_path%3Dpublic',VALID.replace(':UNRELATED-TEST-SECRET',''),
])
def test_wrong_destructive_target_is_rejected_before_docker(monkeypatch,target):
    monkeypatch.setenv('CHUNGPAMO_ALLOW_TEST_DB_RESET',guard.TOKEN)
    def forbidden(*args,**kwargs):raise AssertionError('No Docker/SQL permitted for invalid target')
    monkeypatch.setattr(guard.subprocess,'check_output',forbidden)
    monkeypatch.setattr(guard,'create_engine',forbidden)
    with pytest.raises(RuntimeError):guard.authorize_reset(target)


def test_no_implicit_development_url_conversion(monkeypatch):
    monkeypatch.delenv('TEST_DATABASE_URL',raising=False)
    monkeypatch.setenv('DATABASE_URL',VALID.replace('/chungpamo_regression','/chungpamo'))
    with pytest.raises(RuntimeError,match='Explicit TEST_DATABASE_URL'):guard.validate_test_url()


def test_approval_is_exact_and_credentials_must_differ(monkeypatch):
    monkeypatch.setenv('CHUNGPAMO_ALLOW_TEST_DB_RESET','chungpamo_test@127.0.0.1:55433')
    with pytest.raises(RuntimeError,match='Separate user approval'):guard.assert_destructive_engine(SimpleNamespace(url=make_url(VALID)))
    monkeypatch.setattr('dotenv.dotenv_values',lambda path:{'DATABASE_URL':VALID})
    with pytest.raises(RuntimeError,match='credentials cannot be reused'):guard.validate_test_url(VALID)


def test_explicit_separate_target_is_not_rewritten(monkeypatch):
    monkeypatch.setattr('dotenv.dotenv_values',lambda path:{'DATABASE_URL':VALID.replace('UNRELATED-TEST-SECRET','DEVELOPMENT-ONLY-SECRET')})
    assert guard.validate_test_url(VALID).database==guard.DATABASE
