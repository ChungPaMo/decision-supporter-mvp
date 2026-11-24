"""Offline manufacturing-column retrieval benchmark. Models and raw runs stay out of Git."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import socket
from statistics import median, quantiles
import subprocess
from time import perf_counter, sleep
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from evaluate_mapping_recommendations import CASES, ROOT, candidates, parsed_case
from contracts.mapping_knowledge import DESCRIPTIONS, REJECT
from app.ingest.mapping import ENTITY_FIELDS
from app.ingest.profiling import parse_analysis_file, profile
from app.ingest.recommendation import compatible


HOLDOUT = ROOT / 'contracts/examples/mapping_semantic_holdout_v1.json'
MIN_MARGIN = 0.02  # Fixed across the retrievers before inspecting the holdout.
MODES = ('header', 'profile', 'full')
KEY_FOCUS = ('demand', 'returns', 'production', 'purchase')
E5_REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
QWEN_REVISION = '370f27d7550e0def9b39c1f16d3fbaa13aa67728'
E5_FILES = {'model.onnx': 'ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665',
            'tokenizer.json': '0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39'}
QWEN_SHA = '06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439'


def read_cases(path, legacy):
    raw = path.read_bytes().replace(b'\r\n', b'\n')
    payload = json.loads(raw)
    if not legacy and payload.get('scope') != 'SYNTHETIC_ONLY':
        raise ValueError('The evaluation accepts only the synthetic research split.')
    rows = payload['cases']
    if len({item['id'] for item in rows}) != len(rows):
        raise ValueError('Duplicate case IDs')
    for row in rows:
        if row['expected'] is not None and row['expected'] not in ENTITY_FIELDS[row['entity']]:
            raise ValueError(f"Unknown reference field in {row['id']}")
        if not legacy and (len(row['samples']) > 3 or len(row['neighbors']) > 4):
            raise ValueError('Keep context bounded to synthetic examples and neighboring headers')
    return rows, hashlib.sha256(raw).hexdigest()


def parse_holdout(case):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow([case['header'], *case['neighbors']])
    for sample in case['samples']:
        writer.writerow([sample, *[''] * len(case['neighbors'])])
    return parse_analysis_file('synthetic.csv', stream.getvalue().encode())


def query_text(case, mode):
    parts = [f"컬럼명: {case['header']}"]
    if mode != 'header':
        parts.extend((f"자료형: {case['dtype']}", '합성 샘플 값: ' + ', '.join(case['samples'])))
    if mode == 'full':
        parts.extend(('주변 열: ' + ', '.join(case['neighbors']), f"문서 종류: {case['document']}"))
    return '\n'.join(parts)


def build_inputs(splits):
    catalogs = {entity: {**{field: f'{field}: {DESCRIPTIONS[field]}' for field in fields},
                         **{f'hold:{name}': text for name, text in REJECT.items()}}
                for entity, fields in ENTITY_FIELDS.items()}
    queries = {name: {mode: [{'id': case['id'], 'entity': case['entity'], 'text': query_text(case, mode)} for case in rows]
                      for mode in (('header',) if name == 'legacy48' else MODES)}
               for name, (rows, _) in splits.items()}
    return {'version':'manufacturing-column-retrieval-v1', 'catalogs':catalogs, 'queries':queries,
            'split_sha256':{key: value[1] for key, value in splits.items()}}


def choose(scores, case, parsed):
    """Order supported candidates independently from the first ranked reject role."""
    entity = case['entity']
    column = profile(parsed, 'TISSUE-LEGACY').sheets[0].columns[0]
    allowed = {field for field in ENTITY_FIELDS[entity] if compatible(field, case['header'], column)[0]}
    if any(not -1.00001 <= value <= 1.00001 for value in scores.values()):
        raise ValueError('Cosine values must be finite and normalized')
    ranked = sorted(scores, key=lambda key: (-scores[key], key))
    raw = [key for key in ranked if key in allowed][:3]
    if not ranked or ranked[0] not in allowed:
        return [], raw, ranked[0] if ranked else None, 'reject_or_incompatible'
    if len(ranked) > 1 and scores[ranked[0]] - scores[ranked[1]] < MIN_MARGIN:
        return [], raw, ranked[0], 'small_margin'
    return raw, raw, ranked[0], None


def summarize(rows):
    positives = [row for row in rows if row['expected'] is not None]
    negatives = [row for row in rows if row['expected'] is None]
    rate = lambda numerator, denominator: round(numerator / denominator, 6) if denominator else None
    top1 = sum(row['top1'] == row['expected'] for row in positives)
    top3 = sum(row['expected'] in row['top3'] for row in positives)
    covered = sum(row['top1'] is not None for row in positives)
    wrong = sum(row['top1'] is not None and row['top1'] != row['expected'] for row in rows)
    hold = sum(row['top1'] is None for row in rows)
    return {'n':len(rows), 'positive':len(positives), 'negative':len(negatives), 'top1':top1, 'top3':top3,
            'top1_accuracy':rate(top1,len(positives)), 'top3_accuracy':rate(top3,len(positives)),
            'wrong_top1':wrong, 'wrong_top1_rate':rate(wrong,len(rows)), 'hold':hold, 'hold_rate':rate(hold,len(rows)),
            'positive_coverage':covered, 'positive_coverage_rate':rate(covered,len(positives)),
            'null_cases_with_recommendation':sum(row['top1'] is not None for row in negatives),
            'raw_top3_recall_count':sum(row['expected'] in row['raw_top3'] for row in positives)}


def file_sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_files(directory, checksums):
    if any(file_sha(directory / name) != sha for name, sha in checksums.items()):
        raise ValueError('Model data does not match the pinned maintainer files')
    return sum((directory / name).stat().st_size for name in checksums)


def normalized(vectors):
    import numpy as np
    values = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if not np.isfinite(values).all() or np.any(norms <= 1e-12):
        raise ValueError('Invalid embedding vectors')
    return values / norms


class OnnxEncoder:
    def __init__(self, directory, method, threads, *, artifact_identity=None):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        if artifact_identity is not None:
            checksums, self.revision = artifact_identity
        elif method == 'bge':
            from evaluate_mapping_bge import FILE_SHA, MODEL_REVISION
            checksums, self.revision = FILE_SHA, MODEL_REVISION
        else:
            checksums, self.revision = E5_FILES, E5_REVISION
        self.bytes = verify_files(directory, checksums)
        self.tokenizer = Tokenizer.from_file(str(directory / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=128)
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id('<pad>'), pad_token='<pad>')
        settings = ort.SessionOptions()
        settings.intra_op_num_threads = threads
        settings.inter_op_num_threads = 1
        settings.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        self.session = ort.InferenceSession(str(directory / 'model.onnx'), settings, providers=['CPUExecutionProvider'])
        self.inputs = [item.name for item in self.session.get_inputs()]
        self.hidden = next(item.name for item in self.session.get_outputs() if len(item.shape) == 3)
        self.method = method
        self.runtime = f'onnxruntime {ort.__version__}'

    def embed(self, texts, query):
        import numpy as np
        if self.method == 'e5':
            prefix = 'query: ' if query else 'passage: '
            texts = [prefix + text for text in texts]
        tokens = self.tokenizer.encode_batch(texts)
        mask = np.asarray([token.attention_mask for token in tokens], dtype=np.int64)
        columns = {'input_ids': [token.ids for token in tokens], 'attention_mask': mask,
                   'token_type_ids': [token.type_ids for token in tokens]}
        hidden = self.session.run([self.hidden], {key: np.asarray(columns[key], dtype=np.int64) for key in self.inputs})[0]
        values = hidden[:, 0] if self.method == 'bge' else (hidden * mask[:, :, None]).sum(1) / mask.sum(1)[:, None]
        return normalized(values)


class QwenEncoder:
    def __init__(self, model, executable, threads, log):
        if file_sha(model) != QWEN_SHA:
            raise ValueError('Qwen GGUF does not match official Q8_0')
        self.bytes = model.stat().st_size
        self.revision = QWEN_REVISION
        self.runtime = subprocess.check_output([str(executable), '--version'], stderr=subprocess.STDOUT, text=True).splitlines()[0]
        self.opener = build_opener(ProxyHandler({}))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        self.log = log.open('w', encoding='utf-8')
        self.process = subprocess.Popen([str(executable), '--model', str(model), '--host', '127.0.0.1', '--port', str(port),
            '--embeddings', '--pooling', 'last', '--n-gpu-layers', '0', '--threads', str(threads), '--threads-batch', str(threads),
            '--parallel', '1', '--ctx-size', '2048', '--batch-size', '1024', '--ubatch-size', '1024', '--no-webui'],
            stdout=self.log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            deadline = perf_counter() + 40
            while self.process.poll() is None and perf_counter() < deadline:
                try:
                    with self.opener.open(self.url + '/health', timeout=1) as result:
                        if result.status == 200:
                            return
                except URLError:
                    sleep(.2)
            raise RuntimeError('Local llama-server did not start; see the experiment log')
        except BaseException:
            self.close()
            raise

    def embed(self, texts, query):
        if query:
            texts = ['Instruct: Retrieve the standard manufacturing column role for this Korean tabular column.\nQuery: ' + text
                     for text in texts]
        request = Request(self.url + '/v1/embeddings', data=json.dumps({'input':texts}).encode(),
                          headers={'Content-Type':'application/json'})
        with self.opener.open(request, timeout=60) as response:
            rows = json.load(response)['data']
        if len(rows) != len(texts):
            raise ValueError('Unexpected embedding count')
        return normalized([item['embedding'] for item in sorted(rows,key=lambda item: item['index'])])

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=10)
        self.log.close()


def measure(split, mode, inputs, cases, parsed, rank, timed):
    samples, rows = [], []
    for query, case, source in zip(inputs['queries'][split][mode], cases, parsed):
        start = perf_counter()
        top, raw, raw_top1, reason = rank(split, mode, query, case, source)
        samples.append((perf_counter() - start) * 1000)
        rows.append({'id':case['id'], 'header':case['header'], 'entity':case['entity'], 'focus':case.get('focus',case.get('kind')),
                     'expected':case['expected'], 'top1':top[0] if top else None, 'top3':top, 'raw_top3':raw,
                     'raw_top1':raw_top1, 'hold_reason':reason})
    result = {'metrics':summarize(rows), 'focus':{kind:summarize([row for row in rows if row['focus'] == kind]) for kind in KEY_FOCUS},
              'cases':rows}
    if timed:
        result['median_ms'] = median(samples)
        result['p95_ms'] = quantiles(samples, n=20, method='inclusive')[-1]
    return result


def run(args, inputs, splits, provider=None, score_file=None):
    import psutil
    process = psutil.Process()
    model = None
    start = perf_counter()
    if provider is not None:
        import numpy as np
        texts = list(dict.fromkeys(text for fields in inputs['catalogs'].values() for text in fields.values()))
        vectors = np.concatenate([provider.embed(texts[i:i+8], query=False) for i in range(0,len(texts),8)])
        index = dict(zip(texts,vectors))
        catalog = {entity:(list(fields),np.stack([index[text] for text in fields.values()]))
                   for entity,fields in inputs['catalogs'].items()}
        model = {'revision':provider.revision, 'bytes':provider.bytes, 'runtime':provider.runtime}

        def rank(split, mode, query, case, source):
            keys, vectors = catalog[case['entity']]
            scores = vectors @ provider.embed([query['text']], query=True)[0]
            return choose(dict(zip(keys,map(float,scores))),case,source)
    elif score_file is not None:
        def rank(split, mode, query, case, source):
            scores = score_file['scores'][split][mode][case['id']]
            if set(scores) != set(inputs['catalogs'][case['entity']]):
                raise ValueError(f"Incomplete candidate score set for {case['id']}")
            return choose(scores,case,source)
    else:
        def rank(split, mode, query, case, source):
            top = candidates(source,case['entity'],'rapidfuzz')
            return top, top, top[0] if top else None, 'production_hold' if not top else None

    results = {}
    prep_s = perf_counter() - start
    for name,(cases,_) in splits.items():
        parsed = [(parsed_case if name == 'legacy48' else parse_holdout)(case) for case in cases]
        results[name] = {}
        for mode, queries in inputs['queries'][name].items():
            if provider is None and score_file is None and mode != 'header':
                continue
            rank(name,mode,queries[0],cases[0],parsed[0])  # Warm query before timed requests.
            results[name][mode] = measure(name, mode, inputs, cases, parsed, rank, score_file is None)
    processes = [process]
    if isinstance(provider,QwenEncoder):
        processes.append(psutil.Process(provider.process.pid))
    peak = [getattr(item.memory_info(),'peak_wset',None) for item in processes]
    return {'method':args.method, 'split_sha256':inputs['split_sha256'], 'minimum_margin':MIN_MARGIN, 'model':model,
        'python':platform.python_version(), 'device':'CPU', 'threads':args.threads, 'catalog_prepare_s':prep_s,
        'peak_working_set_mib_upper_bound':sum(peak)/2**20 if None not in peak else None, 'results':results}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--method',choices=('rapidfuzz','bge','e5','qwen','score-file'),default='rapidfuzz')
    parser.add_argument('--model',type=Path)
    parser.add_argument('--llama-server',type=Path)
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--scores',type=Path)
    parser.add_argument('--export-inputs',type=Path)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    splits = {'legacy48':read_cases(CASES,True), 'heldout':read_cases(HOLDOUT,False)}
    inputs = build_inputs(splits)
    bundle_sha = hashlib.sha256(json.dumps(inputs, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if args.export_inputs:
        dump(args.export_inputs, {**inputs,'bundle_sha256':bundle_sha})
        if not args.output:
            return
    if not args.output or args.threads < 1:
        parser.error('Use --output and a positive --threads value for evaluation')
    if args.method in ('bge', 'e5', 'qwen') and not args.model:
        parser.error('--model is required for a local embedding method')
    if args.method == 'qwen' and not args.llama_server:
        parser.error('--llama-server is required for Qwen')
    if args.method == 'score-file' and not args.scores:
        parser.error('--scores is required for score-file')
    provider, scores = None, None
    started = perf_counter()
    if args.method in ('bge','e5'):
        provider = OnnxEncoder(args.model.resolve(strict=True),args.method,args.threads)
    elif args.method == 'qwen':
        args.output.parent.mkdir(parents=True,exist_ok=True)
        provider = QwenEncoder(args.model.resolve(strict=True),args.llama_server.resolve(strict=True),args.threads,
                               args.output.with_suffix('.llama.log'))
    elif args.method == 'score-file':
        scores = json.loads(args.scores.read_text(encoding='utf-8'))
        if scores['bundle_sha256'] != bundle_sha:
            raise ValueError('External scores were not generated for this frozen input bundle')
    init_s = perf_counter() - started
    try:
        report = {**run(args, inputs, splits, provider, scores),'model_init_and_checksum_s':init_s,'bundle_sha256':bundle_sha}
        dump(args.output, report)
        print(json.dumps({key:{mode:{'metrics':data['metrics'], 'median_ms':data.get('median_ms')}
                                   for mode,data in modes.items()} for key,modes in report['results'].items()},ensure_ascii=False))
    finally:
        if isinstance(provider,QwenEncoder):
            provider.close()


if __name__ == '__main__':
    main()
