"""Refuse accidental legacy DB resets before any Docker inspection or DB access."""
import pytest
from scripts.verify_test_db import authorize_reset, TOKEN


def test_reset_needs_separate_approval(monkeypatch):
    monkeypatch.delenv('CHUNGPAMO_ALLOW_TEST_DB_RESET', raising=False)
    with pytest.raises(RuntimeError, match='Separate user approval'):
        authorize_reset('postgresql+psycopg://chungpamo_app:unused@127.0.0.1:55433/chungpamo_test')


def test_reset_rejects_existing_server_and_other_projects_before_connecting(monkeypatch):
    monkeypatch.setenv('CHUNGPAMO_ALLOW_TEST_DB_RESET', TOKEN)
    for target in ('postgresql+psycopg://chungpamo_app:unused@127.0.0.1:55432/chungpamo_test',
                   'postgresql+psycopg://chungpamo_app:unused@127.0.0.1:55433/sisicallcall',
                   'postgresql+psycopg://postgres:unused@127.0.0.1:55433/chungpamo_test'):
        with pytest.raises(RuntimeError, match='outside dedicated'):
            authorize_reset(target)
