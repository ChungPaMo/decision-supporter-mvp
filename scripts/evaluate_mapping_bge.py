"""Compare RapidFuzz and local BGE-M3 on the fixed synthetic mapping cases only."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
from statistics import median, quantiles
from time import perf_counter
from unittest.mock import patch

from evaluate_mapping_recommendations import CASES, ROOT, candidates, parsed_case, recommendation
from app.ingest.mapping import ENTITY_FIELDS


GOLD_SHA = '7df6ea18a15c2f08cbd81a7e2ada9ad98e0248def9da8bdaaa08cf1be45ffd67'
MODEL_REVISION = '5617a9f61b028005a4858fdac845db406aefb181'
FILE_SHA = {
    'Constant_7_attr__value': 'cdf16f72c5d07b36484056e601ed9687f78477e5d85cee85a34f2406b7fb5906',
    'model.onnx': 'f84251230831afb359ab26d9fd37d5936d4d9bb5d1d5410e66442f630f24435b',
    'model.onnx_data': '1eebfb28493f67bba03ce0ef64bfdc7fc5a3bd9d7493f818bb1d78cd798416b4',
    'tokenizer.json': '6710678b12670bc442b99edc952c4d996ae309a7020c1fa0096dd245c2faf790',
}
MIN_COSINE = 0.60  # Fixed before evaluation; no threshold tuning on the 48 cases.


class DenseIndex:
    """The research dense path, CLS + L2 normalization, using BAAI's local ONNX export."""

    def __init__(self, directory: Path):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.np = np
        self.tokenizer = Tokenizer.from_file(str(directory / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=64)
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id('<pad>'), pad_token='<pad>')
        settings = ort.SessionOptions()
        settings.intra_op_num_threads = 4
        settings.inter_op_num_threads = 1
        settings.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        self.session = ort.InferenceSession(str(directory / 'model.onnx'), settings,
                                            providers=['CPUExecutionProvider'])
        self.inputs = [item.name for item in self.session.get_inputs()]
        self.hidden = next(item.name for item in self.session.get_outputs() if len(item.shape) == 3)
        # Use the same field vocabulary as RapidFuzz, with original spelling for the tokenizer.
        terms = list(dict.fromkeys(term for fields in ENTITY_FIELDS.values() for field, spec in fields.items()
                                  for term in (field, *spec['strong'], *spec['weak'])))
        self.vectors = np.concatenate([self.encode(terms[i:i + 8]) for i in range(0, len(terms), 8)])
        self.index = {term: index for index, term in enumerate(terms)}
        self.groups = {
            entity: {
                recommendation.VOCABULARY[entity][field]['all']:
                    [self.index[term] for term in (field, *spec['strong'], *spec['weak'])]
                for field, spec in fields.items()
            } for entity, fields in ENTITY_FIELDS.items()
        }

    def encode(self, texts):
        tokens = self.tokenizer.encode_batch(texts)
        columns = {'input_ids': [token.ids for token in tokens], 'attention_mask': [token.attention_mask for token in tokens],
                   'token_type_ids': [token.type_ids for token in tokens]}
        inputs = {name: self.np.asarray(columns[name], dtype=self.np.int64) for name in self.inputs}
        cls = self.session.run([self.hidden], inputs)[0][:, 0]
        return cls / self.np.maximum(self.np.linalg.norm(cls, axis=1, keepdims=True), 1e-12)

    def rank(self, case, parsed):
        scores = self.vectors @ self.encode([case['header']])[0]
        groups = self.groups[case['entity']]

        def dense_similarity(_, aliases):
            return float(scores[groups[aliases]].max())

        with patch.object(recommendation, 'lexical_similarity', dense_similarity), \
                patch.object(recommendation, 'LEXICAL_CUTOFF', MIN_COSINE):
            return candidates(parsed, case['entity'], 'rapidfuzz')


def measure(cases, parsed, rank, repeats):
    rank(cases[0], parsed[0])
    timings = []
    rows = []
    for repeat in range(repeats):
        for case, source in zip(cases, parsed):
            start = perf_counter()
            options = rank(case, source)
            timings.append((perf_counter() - start) * 1000)
            if repeat == 0:
                rows.append({'id': case['id'], 'kind': case['kind'], 'expected': case['expected'],
                             'top3': options, 'top1': options[0] if options else None})
    stats = {
        'top1': sum(row['expected'] is not None and row['top1'] == row['expected'] for row in rows),
        'top3': sum(row['expected'] is not None and row['expected'] in row['top3'] for row in rows),
        'wrong_top1': sum(row['top1'] is not None and row['top1'] != row['expected'] for row in rows),
        'hold': sum(row['top1'] is None for row in rows),
        'null_gold_with_candidates': sum(row['expected'] is None and bool(row['top3']) for row in rows),
        'null_gold_candidate_count': sum(len(row['top3']) for row in rows if row['expected'] is None),
        'median_ms': median(timings),
        'p95_ms': quantiles(timings, n=20, method='inclusive')[-1],
    }
    return {'metrics': stats, 'cases': rows}


def run(directory: Path, repeats: int):
    import psutil
    import rapidfuzz

    for name, expected in FILE_SHA.items():
        with (directory / name).open('rb') as model_file:
            if hashlib.file_digest(model_file, 'sha256').hexdigest() != expected:
                raise ValueError(f'Unexpected BAAI model checksum: {name}')
    gold = CASES.read_bytes()
    if hashlib.sha256(gold).hexdigest() != GOLD_SHA:
        raise ValueError('Expected the fixed synthetic mapping v1 evaluation set')
    cases = json.loads(gold)['cases']
    parsed = [parsed_case(case) for case in cases]
    process = psutil.Process()

    def memory():
        info = process.memory_info()
        return {'rss_mib': info.rss / 2**20,
                'peak_working_set_mib': info.peak_wset / 2**20 if hasattr(info, 'peak_wset') else None}

    def rapid(case, source):
        return candidates(source, case['entity'], 'rapidfuzz')

    baseline = measure(cases, parsed, rapid, repeats)
    baseline['memory'] = memory()
    start = perf_counter()
    index = DenseIndex(directory)
    init_s = perf_counter() - start
    dense = measure(cases, parsed, index.rank, repeats)
    dense['memory'] = memory()

    def backfill(case, source):
        first = rapid(case, source)
        if len(first) == 3:
            return first
        second = index.rank(case, source)
        return (first + [field for field in second if field not in first])[:3]

    hybrid = measure(cases, parsed, backfill, repeats)
    hybrid['memory'] = memory()
    gain = hybrid['metrics']['top3'] - baseline['metrics']['top3']
    eligible = (gain >= 2 and hybrid['metrics']['top1'] >= baseline['metrics']['top1']
                and all(hybrid['metrics'][key] <= baseline['metrics'][key]
                        for key in ('wrong_top1', 'null_gold_with_candidates', 'null_gold_candidate_count')))
    return {'dataset_sha256': GOLD_SHA, 'model': 'BAAI/bge-m3', 'model_revision': MODEL_REVISION,
            'model_sha256': FILE_SHA, 'cases': len(cases), 'positives': sum(c['expected'] is not None for c in cases),
            'python': platform.python_version(), 'rapidfuzz': rapidfuzz.__version__, 'cpu': platform.processor(),
            'runtime': __import__('onnxruntime').__version__, 'tokenizers': __import__('tokenizers').__version__,
            'device': 'CPU, 4 threads, FP32', 'repeats': repeats, 'model_and_alias_index_init_s': init_s,
            'dense_cosine_cutoff': MIN_COSINE, 'passes_candidate_quality_gate': eligible,
            'methods': {'rapidfuzz': baseline, 'bge_m3': dense, 'rapidfuzz_bge_backfill': hybrid}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model_directory', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / '.artifacts/mapping-bge-eval/results.json')
    args = parser.parse_args()
    report = run(args.model_directory.resolve(strict=True), 3)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({**report, 'methods': {key: {k: v for k, v in method.items() if k != 'cases'}
                                           for key, method in report['methods'].items()}}, indent=2))


if __name__ == '__main__':
    main()
