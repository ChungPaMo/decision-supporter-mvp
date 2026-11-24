"""Non-DB tests for the offline paper benchmark."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

SCRIPTS = str(Path(__file__).resolve().parents[2] / 'scripts')
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from mapping_phase5_local import prepare_local
from mapping_phase6_contract import build_request, parse_response
from mapping_phase6_data import panel, validate
from mapping_phase6_rank import (LearnedAliases, Proposal, budgeted_evidence, candidate_mask, contrast, listwise,
                                 reconcile, typed_state)
from mapping_phase6_risk import conformal_calibrate, conformal_measure, group_threshold, make_predictions
from mapping_research_features import CATALOG, Lexicon


def toy_frame():
    doc = {'entity': 'inventory', 'title': '재고', 'columns': [
        {'header': '예약 차감 후 가용 수량', 'values': ['12', '13']},
        {'header': '창고 예약 물량', 'values': ['2', '3']},
    ]}
    item = prepare_local(doc, Lexicon(CATALOG))
    m = len(item.fields)
    raw = np.zeros((2, m))
    all_allowed = np.ones_like(raw, dtype=bool)
    j = item.fields.index('available_qty')
    k = item.fields.index('allocated_qty')
    raw[:, k] = .20
    cues = np.array([contrast(item, i) for i in range(2)])
    return SimpleNamespace(item=item, raw=raw, cues=cues, semantic=all_allowed, ready=all_allowed.copy(),
                           candidates=np.argsort(-raw, axis=1, kind='stable')), j, k


def test_direction_of_inventory_evidence_survives_shared_reservation_term():
    frame, available, allocated = toy_frame()
    assert frame.cues[0, available] == 1 and frame.cues[0, allocated] < 0
    assert frame.cues[1, allocated] == 1 and frame.cues[1, available] < 0
    assert candidate_mask(frame, 1)[0, allocated]
    assert candidate_mask(frame, 'expand')[0, available]


def test_ambiguous_and_unready_pairs_are_distinct():
    frame, available, allocated = toy_frame()
    frame.ready[0, available] = False
    frame.semantic[0, allocated] = False
    assert typed_state(frame, 0, available, .90) == 'TRANSFORM_REQUIRED'
    assert typed_state(frame, 0, allocated, .90) == 'NON_MATCH'
    assert typed_state(frame, 0, available, .20) == 'HOLD'
    assert typed_state(frame, 1, allocated, .90) == 'MATCH'


def test_listwise_contains_a_private_hold_and_does_not_reuse_pinned_field():
    values = np.array([[.95, .1], [.91, .2], [.2, .29]])
    assigned = listwise([(0,), (0, 1), (1,)], values, values, [0, 0, 1], [1, 2])
    assert assigned == [0, None, None]
    assert reconcile([0, 0, None], values) == [None, None, None]


def test_rank_controls_keep_registered_readiness_in_final_top3():
    p = Proposal(('direct', 'transform'), np.array([[1, 0]]), ((0,),), (1,), (.99,),
                 (0,), (.98,), (.1,), ('MATCH',), 0)
    assert make_predictions(p, .9, .0) == [{'prediction': 'direct', 'rank': ['transform', 'direct'],
                                             'top3': ['direct'], 'ranking': ['transform', 'direct']}]
    assert make_predictions(p, .99, .0)[0]['prediction'] is None


def test_strict_contract_can_hold_partial_duplicate_or_truncated_result():
    frame, available, allocated = toy_frame()
    frame.ready[1, available] = False
    pairs = {'1:0': (0, available), '1:1': (0, allocated), '2:0': (1, available)}
    def response(value, finish='stop'):
        return {'choices': [{'finish_reason': finish, 'message': {'content': json.dumps(value)}}]}
    conflict = response({'1:0': 'MATCH', '1:1': 'MATCH', '2:0': 'MATCH'})
    assert parse_response(frame, pairs, conflict) == ({}, {'MULTIPLE_MATCHES_ONE_SOURCE': 1, 'LOCAL_HARD_CONSTRAINT': 1}, None)
    safe, warnings, _ = parse_response(frame, pairs, response({'1:0': 'MATCH'}))
    assert safe == {'0': 'available_qty'} and warnings == {'MISSING_ID': 2}
    assert parse_response(frame, pairs, response({'1:0': 'MATCH'}, 'length'))[2] == 'OUTPUT_LIMIT'
    assert parse_response(frame, pairs, response({'1:0': 'MATCH'}), {'44': 'available_qty'})[0] == {'44': 'available_qty'}


def test_packing_bounds_and_offline_wire_contains_no_instance_samples():
    frame, available, allocated = toy_frame()
    packed = budgeted_evidence(frame, 0, (allocated, available), limit=70)
    assert packed['bytes'] <= 70 and packed['bytes'] == sum(len(x.encode()) for x in packed['evidence'])
    assert budgeted_evidence(frame, 0, (allocated,), limit=0)['evidence'] == []
    pairs, wire, meta = build_request(frame, 'solar-mini4-260922')
    assert len(pairs) == 6 and meta['wire_bytes'] > 0
    visible = json.loads(wire['messages'][1]['content'])
    assert 'values' not in visible['columns'][0]
    assert 'expected' not in json.dumps(visible)


def test_train_alias_requires_independent_families_and_no_contradiction():
    docs = [{'entity': 'inventory', 'family': str(i), 'columns': [
        {'header': 'free after hold', 'expected': 'available_qty'},
        {'header': 'ambivalent reserve tag', 'expected': ('allocated_qty' if i % 2 else 'available_qty')},
    ]} for i in range(4)]
    index = LearnedAliases(docs)
    assert index.entries == {('inventory', 'available_qty'): ('freeafterhold',)}


def test_conformal_group_correction_has_sample_size_floor():
    p = Proposal(('quantity',), np.array([[0]]), ((0,),), (0,), (.91,), (0,), (.91,), (.2,), ('MATCH',), 0)
    docs = [{'family': str(i), 'columns': [{'expected': 'quantity'}]} for i in range(4)]
    assert group_threshold(docs, [p] * 4, .0, .01)['selected'] is None
    assert group_threshold(docs, [p] * 4, .0, .20)['selected']['adjusted'] == .20
    q = conformal_calibrate(docs, [p] * 4, alpha=.10)
    assert q == 1 and conformal_measure(docs, [p] * 4, q)['direct_singletons'] == 0


def test_holdout_has_separate_semantic_and_ready_truth_and_distinct_vocab():
    train, known = validate(panel('development'))
    test, held = validate(panel('holdout'))
    assert train['documents'] == 70 and test['documents'] == 200
    assert test['sha256'] == 'da519e42f1ea5669693c22746e025bc0d24c2ee96c31e0173ef0d517b6d59ad0'
    assert test['states']['TRANSFORM_REQUIRED'] == 25 and not known & held
