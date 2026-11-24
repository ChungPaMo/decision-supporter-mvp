from collections import Counter
from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
import json
import sys

import numpy as np
import pytest

from app.ingest.parsing import Cell
from app.ingest.validation import parse_period
import evaluate_mapping_phase9 as runner
import mapping_research_remote as remote
from mapping_phase9 import MINI, PRO, assignment
from mapping_phase9_data import manifest, panels
from mapping_phase9_variants import bidirectional, cascade, generator_verifier
from mapping_phase7_llm import Study
from mapping_research_data import sha


def test_synthetic_panels_are_deterministic_and_family_isolated():
    splits = panels()
    pins = manifest(splits)
    assert pins == manifest(panels())
    assert [part['documents'] for part in pins.values()] == [50, 50, 200]
    assert [part['families'] for part in pins.values()] == [25, 25, 50]
    assert set(pins['selection']['entities'].values()) == {10}
    assert pins['holdout']['states']['TRANSFORM_REQUIRED'] > 0
    assert {col['scenario'] for doc in splits['selection'] for col in doc['columns']} >= {
        'novel', 'standard', 'representation', 'ambiguous_numeric', 'open_orders', 'inbound', 'returns', 'money'}
    for docs in splits.values():
        for doc in docs:
            assert all((c['expected'] is None and c['semantic'] is not None)
                       for c in doc['columns'] if c['state'] == 'TRANSFORM_REQUIRED')
            for col in doc['columns']:
                if col['semantic'] == 'period':
                    _, error = parse_period(Cell(col['values'][0], 'text'))
                    assert bool(error) == (col['state'] == 'TRANSFORM_REQUIRED')


def test_global_assignment_preserves_locks_filters_shape_and_abstains_on_ties():
    frame = SimpleNamespace(item=SimpleNamespace(fields=['base_qty', 'qty_per', 'line_no']),
                            ready=np.array([[True, True, True], [True, True, True], [True, True, False]]))
    scores = {('0', 'qty_per'): .96, ('0', 'base_qty'): .71, ('1', 'qty_per'): .95,
              ('2', 'line_no'): .99, ('2', 'base_qty'): .85}
    assert assignment(frame, scores) == {}
    assert assignment(frame, scores, {'1': 'qty_per', '2': 'line_no'}) == {'1': 'qty_per', '2': 'line_no'}
    scores[('1', 'qty_per')] = .90
    assert assignment(frame, scores) == {'0': 'qty_per'}


def test_exact_plan_approval_rejects_wrong_hash_and_budget():
    data = {'scope': 'PHASE9_A_SYNTHETIC_SELECTION_ONLY', 'maximum_usd': '0.40', 'calls_max': 150}
    plan = {**data, 'approval_sha256': sha(data)}
    approval = {'approval_sha256': sha(data), 'maximum_usd': '0.40'}
    assert runner.validate_approval(plan, approval) == Decimal('.40')
    for value in ('0.39', '1.01', 'Infinity'):
        with pytest.raises(ValueError):
            runner.validate_approval(plan, {**approval, 'maximum_usd': value})
    with pytest.raises(ValueError):
        runner.validate_approval({**plan, 'calls_max': 151}, approval)


def test_phase9_limit_increases_only_on_shared_ledger(tmp_path, monkeypatch):
    shared = tmp_path / 'shared'
    shared.mkdir()
    before = b'{"cost_delta_usd":"9.92067637","state":"RESERVED","request_sha256":"historical"}\n'
    (shared / 'billing.jsonl').write_bytes(before)
    monkeypatch.setattr(remote, 'SHARED_CACHE', shared)
    monkeypatch.setenv('UPSTAGE_API_KEY', 'local-test-fixture')
    client = remote.PaidResearch(shared, Decimal('20'), approved=True, phase9=True)
    assert client.spent == Decimal('9.92067637')
    assert client.audit.read_bytes() == before
    for directory, limit, flag in [(shared, '20', False), (shared, '20.01', True),
                                    (tmp_path / 'separate', '20', True)]:
        with pytest.raises(ValueError):
            remote.PaidResearch(directory, Decimal(limit), approved=True, phase9=flag)


def test_plan_contains_only_bound_request_hashes_not_payloads(monkeypatch):
    docs = [{'id': 'synthetic-test', 'csv_sha256': '1' * 64}]
    ledger = {'locked_usd': '9.92067637', 'ledger_sha256': '2' * 64}

    def synthetic_steps(doc, frame, previous, send):
        for model, stage in [(MINI, 'direct'), (PRO, 'direct'), (MINI, 'verify')]:
            send(SimpleNamespace(name=stage, wire={'model': model, 'max_tokens': 32,
                                                   'messages': [{'content': 'synthetic payload ' + stage}]}))

    monkeypatch.setattr(runner, 'document_eval', synthetic_steps)
    plan = runner.build_plan(docs, [None], [None], {'selection': {'sha256': '3' * 64}}, '4' * 64, ledger)
    assert Counter(row['model'] for row in plan['requests']) == {MINI: 2, PRO: 1}
    assert 'synthetic payload' not in json.dumps(plan)
    assert len({row['wire_sha256'] for row in plan['requests']}) == 3
    assert Decimal(plan['maximum_usd']) == sum(Decimal(row['reserve_usd']) for row in plan['requests'])


def test_paid_action_requires_separate_approval_before_preparing_requests(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['evaluate_mapping_phase9', 'run'])
    monkeypatch.setattr(runner, 'selection', lambda: pytest.fail('approval file is required before planning'))
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2


def test_changed_shared_ledger_fails_before_loading_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'lock_paid_cache', lambda _: nullcontext())
    monkeypatch.setattr(runner, 'settlement', lambda _: {'ledger_sha256': 'changed-ledger'})
    monkeypatch.setattr(runner, 'load_local_key', lambda: pytest.fail('changed ledger cannot open paid transport'))
    with pytest.raises(ValueError, match='ledger changed'):
        runner.execute({'ledger_sha256': 'original-ledger', 'requests': []}, [], [], [], {}, {}, tmp_path)


@pytest.fixture
def pair(monkeypatch):
    fields = ('qty_per', 'scrap_rate')
    frame = SimpleNamespace(item=SimpleNamespace(fields=fields), raw=np.array([[.9, .1], [.2, .8]]),
                            ready=np.array([[True, True], [True, False]]),
                            semantic=np.full((2, 2), True))
    doc = {'entity': 'bom', 'title': 'Synthetic BOM', 'columns': [{'header': 'input'}] * 2}
    monkeypatch.setattr(Study, 'observe', lambda self, rows, pools, context: list(rows))
    return doc, frame


def mock_reply(values):
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(values)}}]}


def test_bidirectional_agreement_alone_does_not_pass(pair):
    sources = {
        'forward': {'0': 'qty_per', '1': 'scrap_rate'},
        'fields': {'qty_per': '0', 'scrap_rate': '1'},
        'verify': {'0_0': 'NON_MATCH', '1_0': 'TRANSFORM_REQUIRED'},
    }
    result = bidirectional(*pair, lambda s: mock_reply(sources[s.name]))
    assert result.proposals['agreement'] == sources['forward']
    assert not result.direct
    assert result.transforms == {'1': 'scrap_rate'}


def test_blind_verification_and_selective_cascade(pair):
    stages = []

    def call(stage):
        stages.append((stage.name, stage.wire['model']))
        return mock_reply({'0': 'qty_per', '1': 'HOLD'})

    result = generator_verifier(*pair, call, MINI, PRO, blind=True)
    assert result.direct == {'0': 'qty_per'}
    assert stages == [('generate', MINI), ('blind-verify', PRO)]
    stages.clear()

    def hold(stage):
        stages.append((stage.name, stage.wire['model']))
        return mock_reply({'1': 'HOLD'})

    result = cascade(*pair, hold, locked={'0': 'qty_per'})
    # A low-confidence HOLD cannot erase a locked mapping, regardless of fallback.
    assert result.direct == {'0': 'qty_per'}
    assert stages[0] == ('mini', MINI)
    assert all(name != 'pro-fallback' or model == PRO for name, model in stages)
