from collections import Counter
from decimal import Decimal
import json
from types import SimpleNamespace

import numpy as np
import pytest

from evaluate_mapping_phase7 import MAX_BYTES, MODELS, MeteredTransport, approval_plan, recipes_for
from mapping_phase7_data import manifest, panel
from mapping_phase7_llm import HOLD, Stage, Study, dimension_evidence
from mapping_phase7_optimizer import OptimizerTransport, diagnostics
from mapping_research_remote import BudgetExceeded


def response(values, finish='stop'):
    return {'choices': [{'finish_reason': finish, 'message': {'content': json.dumps(values)}}]}


@pytest.fixture
def tiny():
    fields = ('base_qty', 'qty_per', 'scrap_rate', 'line_no')
    headers = [{'header': 'Quantity input drawn', 'values': ['2', '4']},
               {'header': 'Rejected input percent', 'values': ['3%', '5%']}]
    doc = {'entity': 'bom', 'title': 'BOM', 'columns': headers}
    frame = SimpleNamespace(item=SimpleNamespace(fields=fields, relations=np.zeros((2, 4))),
                            candidates=np.array([[0, 1, 3, 2], [0, 1, 3, 2]]),
                            raw=np.array([[.84, .65, .2, .3], [.8, .7, .5, .6]]),
                            ready=np.array([[True]*4, [True, True, False, True]]),
                            semantic=np.ones((2, 4), dtype=bool))
    return doc, frame


def test_matchmaker_recovers_candidate_outside_top_three_and_merges_correctly(tiny):
    doc, frame = tiny
    calls = []

    def mock(stage):
        calls.append(stage)
        if stage.name == 'calibrate':
            return response({'0_0': 'HIGH', '1_0': 'HIGH'})
        return response({'0': 'qty_per', '1': 'scrap_rate'})

    result = Study(doc, frame, 'fixture', mock).run('matchmaker')
    assert [x.name for x in calls] == ['independent', 'refine', 'calibrate']
    assert 'scrap_rate' in calls[1].allowed['1']
    assert result.direct == {'0': 'qty_per'}
    assert result.transforms == {'1': 'scrap_rate'}


def test_order_consensus_holds_when_two_permutations_disagree(tiny):
    doc, frame = tiny
    calls = []

    def mock(stage):
        calls.append(stage)
        return response({'0': stage.allowed['0'][0], '1': HOLD})

    result = Study(doc, frame, 'fixture', mock).run('mag-permute')
    assert calls[0].allowed['0'][:3] == calls[1].allowed['0'][-2::-1]
    assert not result.direct
    assert result.rejected['PERMUTATION_DISAGREEMENT'] == 1


def test_provider_response_invalid_and_duplicate_targets_are_safe(tiny):
    doc, frame = tiny
    duplicate = Study(doc, frame, 'fixture', lambda _: response({'0': 'qty_per', '1': 'qty_per'})).run('direct')
    assert not duplicate.direct and duplicate.issues['DUPLICATE_TARGET'] == 2
    unfinished = Study(doc, frame, 'fixture', lambda _: response({'0': 'qty_per'}, 'length')).run('mag-list')
    assert not unfinished.direct and unfinished.issues['OUTPUT_LIMIT'] == 1


def test_hold_recovery_does_not_replace_confirmed_result(tiny, monkeypatch):
    doc, frame = tiny
    monkeypatch.setattr(Study, 'verify_choices', lambda self, choices, context: (choices, {}))
    result = Study(doc, frame, 'fixture', lambda _: response({'1': 'qty_per'})).run(
        'hold-recovery', {'0': 'qty_per'})
    assert result.direct == {'0': 'qty_per'}
    assert result.rejected['EXISTING_MAPPING_CONFLICT'] == 1


def test_typed_ablation_only_refines_disagreement(tiny):
    doc, frame = tiny

    def mock(stage):
        if stage.name == 'typed':
            return response({'0_0': 'MATCH', '0_1': 'NON_MATCH', '0_2': 'NON_MATCH',
                             '1_0': 'NON_MATCH', '1_1': 'MATCH', '1_2': 'NON_MATCH'})
        assert set(stage.allowed) == {'1'}
        # A less suitable refinement is vetoed by its independent typed decision.
        return response({'1': 'base_qty'})

    result = Study(doc, frame, 'fixture', mock).run('jev-selective')
    assert result.direct == {'0': 'base_qty'}
    assert result.stage_calls == Counter({'typed': 1, 'list-refine': 1})


def test_independent_generator_and_scale_evidence():
    docs, digest = panel()
    assert panel()[1] == digest
    stats = manifest(docs, digest, [])
    assert stats['documents'] == 60 and stats['families'] == 20
    assert stats['states']['TRANSFORM_REQUIRED'] == 4
    assert dimension_evidence(['3%', '0.04', '400 KRW', '10']) == {
        'percent_share': .25, 'fraction_share': .25, 'currency_share': .25, 'integer_share': .25}
    with pytest.raises(ValueError, match='already occurs'):
        manifest(docs, digest, docs[:1])


def test_smoke_cost_and_transport_upper_bound_reject_before_call():
    record = {'wire_bytes': 1000, 'output_tokens': 60, 'reserve_usd': '.0005', 'wire_sha256': 'example'}
    preview = {f'{model}/{recipe}': [record, record] for model in MODELS for recipe in recipes_for('smoke')}
    ceiling = approval_plan([{'csv_sha256': 'first'}, {'csv_sha256': 'second'}], 'fixed', 'smoke', preview)['budget']
    assert ceiling['calls_max'] == 30
    assert Decimal(ceiling['maximum_usd']) <= Decimal('.09317692')
    client = SimpleNamespace()
    transport = MeteredTransport(MODELS[0], client, 1)
    with pytest.raises(BudgetExceeded):
        transport(Stage('direct', {'model': MODELS[0], 'max_tokens': 256, 'messages': 'a' * MAX_BYTES}, {}))
    assert transport.remaining == 1
    exact = MeteredTransport(MODELS[0], client, 1, ('approved-fingerprint',))
    with pytest.raises(ValueError, match='outside the approved exact'):
        exact(Stage('direct', {'model': MODELS[0], 'max_tokens': 64}, {}))
    assert exact.remaining == 1


def test_optimizer_metrics_and_solar_gateway():
    ex = SimpleNamespace(source='{"fields":["scrap_rate","qty_per"]}',
                         output='{"0":"scrap_rate","1":"HOLD","2":"qty_per","3":"qty_per"}')
    _, issue = diagnostics(ex, '{"0":"HOLD","1":"scrap_rate","2":"scrap_rate","3":"wrong","9":"HOLD"}')
    assert issue == {'FORMAT': 2, 'DUPLICATE': 2, 'OVER_HOLD': 1, 'FALSE_RECOMMENDATION': 1, 'WRONG_ROLE': 1}
    with pytest.raises(ValueError, match='shared research ledger'):
        OptimizerTransport(lambda _: None, MODELS[0], 3)
