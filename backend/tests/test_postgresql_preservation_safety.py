"""No DB access: migration approval and immutable pre/post evidence checks."""
from copy import deepcopy
import pytest
from scripts.postgresql_preservation import compare


def baseline():
    return {'docker': {'container_id': 'isolated'}, 'datasets': [{'schema_name': 'public'}, {'schema_name': 'ds_test'}],
            'summary': {'approved': 16, 'forecasts': 2}, 'revision': '0008',
            'tables': {'public.product': {'rows': 1, 'sha256': 'original'}, 'public.alembic_version': {'rows': 1, 'sha256': 'v8'}},
            'objects': {'trigger:approval_gate': 'original'}}


def test_development_migration_refuses_before_sql_without_separate_consent(monkeypatch):
    from scripts.apply_ingestion_0009 import main
    monkeypatch.delenv('CHUNGPAMO_ALLOW_DEV_MIGRATION', raising=False)
    def forbidden():
        raise AssertionError('No DB access before the consent guard')
    monkeypatch.setattr('scripts.postgresql_preservation.snapshot', forbidden)
    with pytest.raises(RuntimeError, match='Separate user approval'):
        main()


@pytest.mark.parametrize('part', ['docker', 'datasets', 'summary', 'revision', 'tables', 'objects'])
def test_existing_evidence_changes_are_rejected(part):
    before = baseline(); after = deepcopy(before)
    if part == 'docker': after[part]['container_id'] = 'other-project'
    elif part == 'datasets': after[part][0]['schema_name'] = 'foreign'
    elif part == 'summary': after[part]['approved'] = 15
    elif part == 'revision': after[part] = '0009'
    elif part == 'tables': after[part]['public.product']['sha256'] = 'changed'
    else: del after[part]['trigger:approval_gate']
    with pytest.raises(AssertionError):
        compare(before, after)


def test_additive_0009_comparison_allows_only_empty_history_tables_and_revision():
    before = baseline(); after = deepcopy(before)
    after['revision'] = '0009'
    after['tables']['public.alembic_version']['sha256'] = 'v9'
    for schema in ('public', 'ds_test'):
        for name in ('ingestion_transformation', 'ingestion_transform_source'):
            after['tables'][schema + '.' + name] = {'rows': 0, 'sha256': 'empty'}
    compare(before, after, allow_0009=True)
    after['tables']['ds_test.ingestion_transform_source']['rows'] = 1
    with pytest.raises(AssertionError):
        compare(before, after, allow_0009=True)
