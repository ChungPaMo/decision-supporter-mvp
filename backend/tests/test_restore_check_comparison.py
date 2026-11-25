from dataclasses import replace

import pytest

from scripts.restore_check_comparison import CheckAttributes, equivalent_array_cast


NAME = 'public.import_batch.ck_batch_entity'
ORIGINAL = "CHECK (((entity)::text = ANY ((ARRAY['a'::character varying, 'b'::character varying])::text[])))"
RESTORED = "CHECK (((entity)::text = ANY (ARRAY[('a'::character varying)::text, ('b'::character varying)::text])))"
ATTRIBUTES = CheckAttributes('character varying(30)', 'pg_catalog.default', False, True, True, False, 0, False)


def test_only_observed_array_cast_rewrite_matches():
    assert equivalent_array_cast(NAME, ORIGINAL, RESTORED, ATTRIBUTES, ATTRIBUTES)
    assert not equivalent_array_cast('other_schema.import_batch.ck_batch_entity', ORIGINAL, RESTORED, ATTRIBUTES, ATTRIBUTES)


@pytest.mark.parametrize('replacement', [
    RESTORED.replace("'b'", "'c'"),
    RESTORED.replace(", ('b'::character varying)::text", ""),
    RESTORED.replace("])", ", ('c'::character varying)::text])"),
    RESTORED.replace("'a'", "'temp'").replace("'b'", "'a'").replace("'temp'", "'b'"),
    RESTORED.replace('character varying', 'varchar(1)'),
    RESTORED.replace('entity', 'status'),
    RESTORED.replace('= ANY', '<> ALL'),
    RESTORED[:-1] + ' OR entity IS NULL)',
    RESTORED + ' NO INHERIT',
])
def test_sql_changes_are_refused(replacement):
    assert not equivalent_array_cast(NAME, ORIGINAL, replacement, ATTRIBUTES, ATTRIBUTES)


@pytest.mark.parametrize('changes', [
    {'validated': False}, {'nullable': True}, {'local': False}, {'no_inherit': True},
    {'inheritance_count': 1}, {'has_parent': True}, {'column_type': 'character varying(31)'}, {'collation': 'C'},
])
def test_catalog_changes_are_refused(changes):
    assert not equivalent_array_cast(NAME, ORIGINAL, RESTORED, ATTRIBUTES, replace(ATTRIBUTES, **changes))
