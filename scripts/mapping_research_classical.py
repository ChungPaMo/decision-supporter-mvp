"""Valentine benchmark and an isolated mapping-memory simulation."""
import argparse
from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from evaluate_mapping_research import baseline_decisions, calibrate, decisions, make_targets, metrics, peak_rss_mib, timing, write
from mapping_research_data import load_frozen, norm, sha
from mapping_research_features import CATALOG, Lexicon, prepare, train_prototypes


def representative_tables(train):
    import pandas as pd
    samples = {entity: {} for entity in CATALOG}
    for doc in train:
        for col in doc['columns']:
            field = col['expected']
            if field is not None and field not in samples[doc['entity']]:
                samples[doc['entity']][field] = [item for item in col['values'] if item][:12]
    return {entity: pd.DataFrame({field: pd.Series(data) for field, data in fields.items()})
            for entity, fields in samples.items()}


def valentine_matrix(doc, reference, matcher):
    import pandas as pd
    from valentine import valentine_match

    labels = [col['header'] for col in doc['columns']]
    unique = [label if labels.count(label) == 1 else f'{label} [{i}]' for i, label in enumerate(labels)]
    frame = pd.DataFrame({key: col['values'] for key, col in zip(unique, doc['columns'], strict=True)})
    matches = valentine_match([frame, reference], matcher, df_names=['input', 'reference'])
    fields = list(CATALOG[doc['entity']])
    matrix = np.full((len(unique), len(fields)), -1e6)
    for pair, score in matches.items():
        left_table, left_col, right_table, right_col = pair
        if left_table == 'input' and right_table == 'reference':
            matrix[unique.index(left_col), fields.index(right_col)] = float(score)
        elif right_table == 'input' and left_table == 'reference':
            matrix[unique.index(right_col), fields.index(left_col)] = float(score)
    return matrix


def classical(directory, output):
    from valentine.algorithms import Coma, Cupid, DistributionBased, JaccardDistanceMatcher, SimilarityFlooding
    from valentine.algorithms.jaccard_distance import StringDistanceFunction

    started = perf_counter()
    train, _ = load_frozen(directory, 'train')
    calibration, calibration_sha = load_frozen(directory, 'calibration')
    schemas = representative_tables(train)
    lexicon, prototypes = Lexicon(CATALOG), train_prototypes(train)
    cal_inputs = [prepare(doc, lexicon, prototypes) for doc in calibration]
    cal_targets = make_targets(calibration, cal_inputs)
    options = {
        'coma-schema': lambda: Coma(delta=1.0),
        'coma-instances': lambda: Coma(delta=1.0, use_instances=True),
        'cupid': lambda: Cupid(process_num=1),
        'similarity-flooding': SimilarityFlooding,
        'distribution': lambda: DistributionBased(quantiles=32, process_num=1),
        'jaccard-exact': lambda: JaccardDistanceMatcher(threshold_dist=1.0, distance_fun=StringDistanceFunction.Levenshtein),
    }
    policies, results = {}, {}
    for name, factory in options.items():
        try:
            scores = [valentine_matrix(doc, schemas[doc['entity']], factory()) for doc in calibration]
            policies[name] = calibrate(scores, cal_inputs, cal_targets)
        except Exception as exc:
            results[name] = {'status':'FAILED', 'error':type(exc).__name__, 'message':str(exc)[:200]}
    freeze = {'calibration_sha256':calibration_sha, 'policies':policies, 'valentine':version('valentine')}
    write(output / 'classical-frozen.json', {**freeze, 'sha256':sha(freeze)})
    final, final_sha = load_frozen(directory, 'final')
    prepared = [prepare(doc, lexicon, prototypes) for doc in final]
    for name, policy in policies.items():
        try:
            rows, latency = [], []
            for doc, source in zip(final, prepared, strict=True):
                tick = perf_counter()
                scores = valentine_matrix(doc, schemas[doc['entity']], options[name]())
                available = {**source, 'allowed': source['allowed'] & (scores > -1e5)}
                rows.append(decisions(scores, available, policy))
                latency.append((perf_counter() - tick) * 1000)
            result = metrics(final, rows)
            result.pop('case_counts')
            modes = {False:{'possible':0,'correct':0}, True:{'possible':0,'correct':0}}
            for doc, predictions in zip(final,rows,strict=True):
                reference = schemas[doc['entity']]
                for column, row in zip(doc['columns'],predictions,strict=True):
                    target = column['expected']
                    if target is None:
                        continue
                    overlap = bool(set(column['values']) & set(reference[target].dropna()))
                    modes[overlap]['possible'] += 1
                    modes[overlap]['correct'] += row['prediction'] == target
            results[name] = {'status':'MEASURED', **result, **timing(latency), 'value_overlap':{
                             'overlap':modes[True],'no_overlap':modes[False]}}
        except Exception as exc:
            results[name] = {'status':'FAILED', 'error':type(exc).__name__, 'message':str(exc)[:200]}
        write(output / 'classical-results.json', {'sha256':final_sha, 'models':results, 'seconds':perf_counter() - started,
                                                'peak_process_mib':peak_rss_mib()})
    return results


def nltk_local_only(resource, **_):
    from nltk.data import find
    category = 'tokenizers' if resource == 'punkt_tab' else 'corpora'
    for location in (f'{category}/{resource}', f'{category}/{resource}.zip'):
        try:
            find(location)
            return True
        except LookupError:
            pass
    return False


@dataclass(frozen=True)
class MemoryKey:
    dataset_id: str
    entity: str
    version: str
    headers: tuple[str, ...]


class MappingMemory:
    def __init__(self):
        self.confirmed = {}

    def approve(self, key, mapping):
        used = [field for field in mapping if field is not None]
        if (len(mapping) != len(key.headers) or len(set(key.headers)) != len(key.headers)
                or len(set(used)) != len(used) or any(field not in CATALOG[key.entity] for field in used)):
            raise ValueError('Invalid or ambiguous confirmed mapping')
        self.confirmed[key] = tuple(mapping)

    def withdraw(self, key):
        self.confirmed.pop(key, None)

    def lookup(self, key, similar=False):
        if key in self.confirmed:
            return self.confirmed[key]
        if not similar:
            return None
        candidates = []
        for prior, mapping in self.confirmed.items():
            if (prior.dataset_id, prior.entity, prior.version) != (key.dataset_id, key.entity, key.version) or len(prior.headers) != len(key.headers):
                continue
            agreements = [SequenceMatcher(None, a, b, autojunk=False).ratio() for a, b in zip(prior.headers, key.headers, strict=True)]
            if min(agreements) >= .88 and sum(a < 1 for a in agreements) == 1:
                candidates.append(mapping)
        return candidates[0] if len(candidates) == 1 else None


def memory(directory, output):
    train, _ = load_frozen(directory, 'train')
    lexicon, prototypes = Lexicon(CATALOG), train_prototypes(train)
    documents, modes = [], {name: [] for name in ('rapid','exact-memory','similar-memory','hybrid')}
    scenarios = ('repeat', 'format_edit', 'layout_change', 'other_dataset', 'revoked', 'version_change', 'bad_memory', 'unconfirmed')
    valid = [doc for doc in train if len({norm(c['header']) for c in doc['columns']}) == len(doc['columns'])
             and sum(col['expected'] is not None for col in doc['columns']) >= 2]
    for i, scenario in enumerate(scenarios * 10):
        original = valid[i * 9]
        prior = MemoryKey('COMPANY-A', original['entity'], 'v1', tuple(norm(col['header']) for col in original['columns']))
        history = MappingMemory()
        known = [col['expected'] for col in original['columns']]
        if scenario == 'bad_memory':
            first, second = [j for j, target in enumerate(known) if target is not None][:2]
            known[first], known[second] = known[second], known[first]
        if scenario != 'unconfirmed':
            history.approve(prior, known)
        if scenario == 'revoked':
            history.withdraw(prior)
        current = deepcopy(original)
        current['id'] += '-repeat'
        current['family'] = scenario
        for col in current['columns']:
            col['values'] = col['values'][1:] + col['values'][:1]
        if scenario == 'format_edit':
            col = max(current['columns'], key=lambda item: len(item['header']))
            col['header'] += col['header'][-1]
        if scenario == 'layout_change':
            current['columns'].reverse()
        if scenario == 'other_dataset':
            column = next(col for col in current['columns'] if col['expected'] is not None)
            column.update(expected=None, scenario='other_dataset_role', values=['$54']*len(column['values']))
        scope, generation = ('COMPANY-B' if scenario == 'other_dataset' else 'COMPANY-A'), ('v2' if scenario == 'version_change' else 'v1')
        key = MemoryKey(scope, current['entity'], generation, tuple(norm(col['header']) for col in current['columns']))
        source = prepare(current, lexicon, prototypes)
        base = baseline_decisions(source, 'rapid')
        modes['rapid'].append(base)
        documents.append(current)
        for method, similar in (('exact-memory', False), ('similar-memory', True), ('hybrid', True)):
            cached = history.lookup(key, similar=similar)
            rows = deepcopy(base)
            if cached is not None:
                for j, field in enumerate(cached):
                    allowed = field is None or source['allowed'][j, source['fields'].index(field)]
                    if method == 'hybrid' and (not allowed or (base[j]['prediction'] and base[j]['prediction'] != field)):
                        continue
                    rows[j].update(prediction=field, top3=[field] if field else [])
            modes[method].append(rows)
    results = {name:metrics(documents, predicted) for name, predicted in modes.items()}
    for result in results.values():
        result.pop('case_counts')
    write(output / 'memory-results.json', {'synthetic_only':True, 'models':results})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('method', choices=('valentine','memory'))
    parser.add_argument('--data', type=Path, default=Path('.artifacts/mapping-research/data'))
    parser.add_argument('--output', type=Path, default=Path('.artifacts/mapping-research/results'))
    args = parser.parse_args()
    if args.method == 'valentine':
        with patch('nltk.download', nltk_local_only):
            classical(args.data, args.output)
    else:
        memory(args.data, args.output)
