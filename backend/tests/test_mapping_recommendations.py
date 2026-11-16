"""Small regression for review-only fuzzy retrieval, qualifiers and offline evaluation."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app.ingest.mapping import ENTITY_FIELDS, map_sheet, norm_header
from app.ingest.profiling import parse_analysis_file
from app.ingest.recommendation import recommend
from app.main import app

ROOT = Path(__file__).resolve().parents[2]


def test_rapidfuzz_suggests_typos_without_applying_them_and_override_still_wins():
    parsed = parse_analysis_file('p.csv', b'product_id,period,demnad_qty,unit\nP1,2026-01,12,EA\n')
    baseline = map_sheet(parsed.sheets[0])
    reply = recommend(parsed, 'monthly_demand', 'TISSUE-LEGACY')
    sheet = reply.sheets[0]
    assert sheet.existing_mapping == {field: row.col for field, row in baseline.fields.items()}
    assert sheet.status == 'HOLD' and 'demand_qty' not in sheet.existing_mapping
    candidate = sheet.suggestions[2].suggestions[0]
    assert candidate.target_field == 'demand_qty' and candidate.requires_review
    assert candidate.method == 'LEXICAL_SIMILARITY'
    assert any('RAPIDFUZZ_RATIO=' in item and 'NOT_CONFIDENCE' in item for item in candidate.evidence)
    assert not reply.persisted and not reply.auto_approve and reply.approval_required
    reviewed = recommend(parsed, 'monthly_demand', 'TISSUE-LEGACY', overrides={'demand_qty': 'C'}).sheets[0]
    assert reviewed.status == 'MAPPED'
    assert reviewed.existing_mapping['demand_qty'] == 3
    assert reviewed.suggestions[2].suggestions[0].method == 'USER_OVERRIDE'


@pytest.mark.parametrize('header,field', [
    ('수요량（반품）', 'demand_qty'), ('demand_qty[cancelled]', 'demand_qty'),
    ('수요월(출고 기준)', 'period'), ('product_id(material)', 'product_id'),
])
def test_semantic_qualifiers_are_not_lost_even_when_exact_mapper_ignores_annotations(header, field):
    parsed = parse_analysis_file('p.csv', f'{header},unrelated_note\n12,Synthetic\n'.encode())
    original = map_sheet(parsed.sheets[0], entity='monthly_demand')
    reply = recommend(parsed, 'monthly_demand', 'TISSUE-LEGACY').sheets[0]
    assert reply.existing_mapping == {name: item.col for name, item in original.fields.items()}
    assert reply.suggestions[0].suggestions == []
    assert reply.status == 'HOLD'
    assert 'PROFILE_CONTRADICTION:' + field in reply.holds


def test_legitimate_unit_annotation_and_exact_mapping_do_not_regress():
    data = b'product_id,period,demand_qty(EA),unit\nP1,2026-01,12,EA\n'
    parsed = parse_analysis_file('p.csv', data)
    reply = recommend(parsed, 'monthly_demand', 'TISSUE-LEGACY').sheets[0]
    assert reply.status == 'MAPPED' and reply.existing_mapping['demand_qty'] == 3
    assert reply.suggestions[2].suggestions[0].method == 'STANDARD_EXACT'


def test_http_review_only_behavior_preserves_source_and_history_is_not_created():
    import hashlib
    data = b'product_id,period,demnad_qty,unit\nP1,2026-01,12,EA\n'
    client = TestClient(app)
    reply = client.post('/ingest/mapping-suggestions', files={'file': ('p.csv', data)}).json()
    assert reply['source_sha256'] == hashlib.sha256(data).hexdigest()
    assert reply['sheets'][0]['status'] == 'HOLD' and not reply['persisted'] and not reply['auto_approve']
    assert 'batch_id' not in reply and 'transformation_id' not in reply
    # Existing persistence-disabled gate remains authoritative; recommendation creates no storage mode.
    assert client.get('/ingest/transformations').status_code == 501


def test_fixed_small_eval_is_not_generated_from_aliases_and_reports_bge_separately():
    from scripts.evaluate_mapping_recommendations import run
    data = json.loads((ROOT / 'contracts/examples/mapping_recommendation_cases_v1.json').read_text(encoding='utf-8'))
    assert len(data['cases']) == 48 and len({row['id'] for row in data['cases']}) == 48
    for case in data['cases']:
        if case['kind'] not in ('variant', 'new_expression'):
            continue
        aliases = {norm_header(alias) for spec in ENTITY_FIELDS[case['entity']].values()
                   for alias in spec['strong'] + spec['weak']}
        assert norm_header(case['header']) not in aliases
    report = run(repeats=1)
    saved = json.loads((ROOT / 'docs/MAPPING_RECOMMENDATION_RESULTS_20261116.json').read_text(encoding='utf-8'))
    assert report['dataset_sha256'] == saved['dataset_sha256']
    methods = report['methods']
    assert methods['rapidfuzz']['top3_recall'] >= methods['exact_alias']['top3_recall']
    assert methods['rapidfuzz']['top3_recall'] == methods['sequence']['top3_recall']
    assert methods['rapidfuzz']['wrong_recommendation_count'] > 0  # Do not silently hide false proposals.
    assert 'bge' not in methods  # Historical results do not share this evaluation's denominator.
    research = json.loads((ROOT / 'contracts/examples/mapping_bge_research_excerpt.json').read_text(encoding='utf-8'))
    assert research['hold_rate'] is None and research['ranking_test']['n'] != len(data['cases'])
