"""Replay pinned Solar concept responses using local files and MockTransport only."""
import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from math import isclose
from pathlib import Path

import httpx

from mapping_research_confirmatory import OUTPUT as CONFIRM_DIR, locked_panel
from mapping_research_data import csv_bytes, load_frozen, sha
from mapping_research_features import CATALOG, Lexicon, prepare, train_prototypes
from mapping_research_phase3 import CONFIRM_SHA, DATA, OUT, Corpus, decode_response, make_jobs, request_key, scored, summary
from mapping_research_remote import SHARED_CACHE, billing_summary, synthetic_documents

from app.api.ingest_ai import review_mapping_file
from app.config import Settings
from app.integrations.upstage import UpstageClient
from contracts.mapping_review import strict_json


DATASET = 'PHASE4-CACHED-REPLAY'


class ReplayMeter:
    """Only usable with the local MockTransport in this script."""

    def reserve(self, request):
        return True

    def complete(self, request, usage, outcome):
        pass


def load_panel(split, data, confirm):
    if split == 'confirmatory':
        docs, digest = locked_panel(confirm)
        if digest != CONFIRM_SHA:
            raise ValueError('Confirmatory input SHA changed')
    else:
        docs, digest = synthetic_documents(data, split)
    train, _ = load_frozen(data, 'train')
    lexicon, prototypes = Lexicon(CATALOG), train_prototypes(train)
    return Corpus(docs, digest, [prepare(doc, lexicon, prototypes) for doc in docs], {})


def adapt_ids(body):
    # Phase 3 cached IDs start at zero. The API uses original 1-based CSV column coordinates.
    adjusted = deepcopy(body)
    try:
        message = adjusted['choices'][0]['message']
        values = strict_json(message['content'])
        if isinstance(values, dict):
            message['content'] = json.dumps({
                str(int(key) + 1) if key.isascii() and key.isdecimal() and len(key) <= 6 else key: value
                for key, value in values.items()}, ensure_ascii=False)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, RecursionError):
        pass
    return adjusted


def predictions(rows):
    return [{'prediction': field, 'top3': [field] if field else [], 'ranking': None} for field in rows]


def headline(metrics):
    keys = ('n', 'eligible', 'correct', 'wrong', 'hold', 'all_columns_correct')
    return {key: metrics[key] for key in keys}


def evaluate(split, data, confirm, cache, results):
    panel = load_panel(split, data, confirm)
    indexes = range(len(panel.docs))
    jobs = list(make_jobs(panel, indexes, 'concept', None))
    expected = strict_json((results / f'{split}-results.json').read_bytes())
    if expected['data_sha256'] != panel.digest:
        raise ValueError(f'{split} Phase 3 result SHA changed')
    files = [csv_bytes(doc) for doc in panel.docs]
    digests = [sha256(content).hexdigest() for content in files]
    if any(digest != doc['csv_sha256'] for digest, doc in zip(digests, panel.docs, strict=True)):
        raise ValueError(f'{split} synthetic CSV failed its digest check')
    settings = Settings(_env_file=None, upstage_api_enabled=True, ai_mapping_enabled=True, ai_external_data_allowed=True,
        upstage_api_key='offline-replay-fixture', ai_mapping_strategy='concept', ai_mapping_prompt_version='mapping-v1',
        ai_mapping_knowledge_version='manufacturing-v1', ai_mapping_model='solar-mini4-260922', ai_mapping_max_columns=64,
        ai_external_synthetic_sources={DATASET: set(digests)})
    observations, backend = [], []
    statuses, issues, counts = Counter(), Counter(), Counter()
    for index, (endpoint, wire, allowed, vocabulary, keyed) in jobs:
        key = request_key(endpoint, wire)
        entry = strict_json((cache / f'{key}.json').read_bytes())
        body = entry['body']
        if entry['request_sha256'] != key or entry['body_sha256'] != sha(body):
            raise ValueError(f'{split} cache integrity failed')
        picks, errors = decode_response(body, endpoint, allowed, vocabulary, keyed)
        observations.append((index, key, picks, errors, False))
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=adapt_ids(body)))
        client = UpstageClient(settings, ReplayMeter(), transport=transport)
        result = review_mapping_file(settings, client, DATASET, 'fixture.csv', files[index], None,
                                     panel.docs[index]['entity'], {}, True)
        combined = []
        statuses[result.status] += 1
        for column in result.columns:
            combined.append(column.target_field)
            if column.hold_reason:
                issues[column.hold_reason] += 1
        if len(combined) != len(panel.docs[index]['columns']):
            raise ValueError(f'{split} backend did not preserve all columns')
        counts['reviewable_ai_columns'] += sum(column.validation == 'REVIEWABLE' for column in result.columns)
        counts['preserved_local_columns'] += sum(column.validation == 'PRESERVED' for column in result.columns)
        backend.append(predictions(combined))
    replay = summary(panel, indexes, 'concept', jobs, observations, [])
    original = expected['methods']['concept']
    for key in ('strict', 'verified_partial'):
        measured, recorded = replay[key]['metrics'], original[key]['metrics']
        # Macro averages can differ at floating-point rounding precision across hash seeds.
        if (measured.keys() != recorded.keys() or replay[key]['local_rejections'] != original[key]['local_rejections']
                or any(not (isclose(value, recorded[field], abs_tol=1e-12, rel_tol=0.0) if isinstance(value, float)
                            else value == recorded[field]) for field, value in measured.items())):
            raise ValueError(f'{split} Phase 3 metrics differ under shared verifier: {key}')
    for key in ('contract_affected_documents', 'errors', 'attempted_or_cached'):
        if replay[key] != original[key]:
            raise ValueError(f'{split} Phase 3 results differ under shared verifier: {key}')
    return {'documents': len(panel.docs), 'cache_verified': len(observations),
            'phase3_strict': headline(replay['strict']['metrics']),
            'phase3_partial': headline(replay['verified_partial']['metrics']),
            'backend_protected_local_plus_reviewable': headline(scored(panel.docs, backend)),
            'backend_statuses': statuses, 'backend_columns': counts, 'backend_hold_or_conflict_reasons': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=DATA)
    parser.add_argument('--confirmatory', type=Path, default=CONFIRM_DIR)
    parser.add_argument('--cache', type=Path, default=SHARED_CACHE)
    parser.add_argument('--results', type=Path, default=OUT)
    args = parser.parse_args()
    audit = args.cache / 'billing.jsonl'
    before = sha256(audit.read_bytes()).hexdigest()
    measurements = {split: evaluate(split, args.data, args.confirmatory, args.cache, args.results)
                    for split in ('final', 'confirmatory')}
    billing = billing_summary(args.cache)
    if before != sha256(audit.read_bytes()).hexdigest():
        raise ValueError('Research ledger changed during local replay')
    print(json.dumps({'panels': measurements, 'research_ledger_intact': True, 'provider_http_calls': 0,
                      'historical_requests': billing['calls'], 'historical_usd': billing['cost_or_reserve_usd']},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
