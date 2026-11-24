"""CPU neural experiments using the existing pinned encoders and an ONNX cross-encoder."""
import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from evaluate_mapping_embeddings import OnnxEncoder, QwenEncoder, REJECT, file_sha, normalized
from evaluate_mapping_research import calibrate, decisions, make_targets, metrics, peak_rss_mib, timing, write
from mapping_research_data import load_frozen, sha
from mapping_research_features import CATALOG, Lexicon, prepare, stats, train_prototypes


MODES = ('header', 'dtype', 'sample', 'profile', 'neighbors', 'full', 'business', 'confusion')


def queries(doc, mode):
    columns = doc['columns']
    for i, col in enumerate(columns):
        header = col['header']
        text = [f'Column: {header}']
        if mode in ('dtype','profile','full','business','confusion'):
            vector = stats(col['values'])
            kinds = ['numeric', 'code', 'date', 'month', 'unit']
            indexes = (0, 3, 4, 5, 6)
            text.append('Type: ' + ', '.join(kind for kind, index in zip(kinds, indexes) if vector[index] >= .8))
            if mode != 'dtype':
                text.append(f'Profile: numeric={vector[0]:.2f}, distinct={vector[11]:.2f}, missing={vector[7]:.2f}')
        if mode in ('sample','full','business','confusion'):
            text.append('Samples: ' + ', '.join(value for value in col['values'][:3] if value))
        if mode in ('neighbors','full','business','confusion'):
            text.append('Neighbors: ' + ', '.join(columns[j]['header'] for j in range(max(0, i-2), min(len(columns), i+3)) if j != i))
            text.append(f'Table: {doc["title"]}')
        yield '\n'.join(text)


def passages(entity, mode):
    from mapping_research_features import BUSINESS_WORDS, CONFLICTS

    fields = CATALOG[entity]
    result = {}
    for field, row in fields.items():
        text = row['description']
        if mode in ('business', 'confusion'):
            text += f' | standard datatype: {row["kind"]} | concept: {BUSINESS_WORDS.get(field, field)}'
        if mode == 'confusion' and field in CONFLICTS:
            text += f' | exclude: {CONFLICTS[field]}'
        result[field] = text
    result['HOLD'] = 'Unknown column, ambiguous, out-of-schema, or requires transformation. ' + ' '.join(REJECT.values())
    return result


def cached_vectors(encoder, texts, *, query, cache, batch):
    """Cache input/revision/settings together, deduping texts before inference."""
    unique = list(dict.fromkeys(texts))
    rows, elapsed, seen = [], [], 0
    for i in range(0, len(unique), batch):
        block = unique[i:i+batch]
        digest = sha({'encoder':encoder.revision, 'runtime':encoder.runtime, 'bytes':encoder.bytes, 'query':query, 'batch':batch, 'texts':block})
        path = cache / (digest + '.npz')
        if path.exists():
            with np.load(path, allow_pickle=False) as archived:
                vectors, original_ms = archived['vectors'], float(archived['ms'])
            if vectors.shape[0] != len(block) or not np.all(np.isfinite(vectors)):
                raise ValueError('Invalid cached vector block')
            seen += 1
        else:
            clock = perf_counter()
            vectors = np.asarray(encoder.embed(block, query=query), dtype=np.float32)
            original_ms = (perf_counter() - clock) * 1000
            with path.with_suffix('.tmp').open('wb') as stream:
                np.savez(stream, vectors=vectors, ms=original_ms)
            path.with_suffix('.tmp').replace(path)
        rows.extend(vectors)
        elapsed.extend([original_ms / len(block)] * len(block))
    lookups = dict(zip(unique, rows, strict=True))
    return np.asarray([lookups[text] for text in texts]), {**timing(elapsed), 'unique':len(unique), 'cached_batches':seen}


def embed_set(encoder, documents, mode, cache, batch):
    texts = [text for doc in documents for text in queries(doc, mode)]
    source, measured = cached_vectors(encoder, texts, query=True, cache=cache, batch=batch)
    keys = {entity:list(passages(entity, mode).values()) for entity in CATALOG}
    bank, _ = cached_vectors(encoder, [t for v in keys.values() for t in v], query=False, cache=cache, batch=batch)
    grouped, start = {}, 0
    for entity, items in keys.items():
        grouped[entity] = bank[start:start + len(items)]
        start += len(items)
    source_by_doc, cursor = [], 0
    for doc in documents:
        limit = cursor + len(doc['columns'])
        source_by_doc.append(source[cursor:limit])
        cursor = limit
    return source_by_doc, grouped, measured


def embed_scores(sources, catalog, documents, projection=None):
    def transform(x):
        return normalized(x @ projection) if projection is not None else x
    targets = {entity: transform(vectors) for entity, vectors in catalog.items()}
    response = []
    for values, doc in zip(sources, documents, strict=True):
        scores = transform(values) @ targets[doc['entity']].T
        response.append(scores[:, :-1] - scores[:, -1:])
    return response


def train_projection(embeddings, bank, documents):
    """Learn a regularized alignment layer over the frozen encoder. No encoder weights change."""
    started = perf_counter()
    samples, targets = [], []
    for doc, rows in zip(documents, embeddings, strict=True):
        in_scope = list(CATALOG[doc['entity']]) + [None]
        for col, vector in zip(doc['columns'], rows, strict=True):
            samples.append(vector)
            targets.append(bank[doc['entity']][in_scope.index(col['expected'])])
    x, y = np.asarray(samples, dtype=np.float64), np.asarray(targets, dtype=np.float64)
    norm_eye = np.eye(x.shape[1]) * 25
    matrix = np.linalg.solve(x.T @ x + norm_eye, x.T @ y + norm_eye)
    return matrix, {'parameters':matrix.size, 'fit_seconds':perf_counter() - started, 'rows':len(x),
                    'weight_bytes':matrix.nbytes, 'training_mse':float(np.mean((x @ matrix - y)**2))}


def learn_pairs(spaces, prepared, documents, *, hybrid):
    from sklearn.linear_model import LogisticRegression
    features = lambda score, row: np.concatenate((score[:, :, None], row['features']), axis=2) if hybrid else score[:, :, None]
    x = np.concatenate([features(score, row).reshape(score.size, -1) for score, row in zip(spaces, prepared, strict=True)])
    y = np.concatenate([row.ravel() for row in make_targets(documents, prepared)])
    clock = perf_counter()
    model = LogisticRegression(max_iter=350, random_state=24, class_weight='balanced').fit(x, y)
    elapsed = perf_counter() - clock
    return lambda scores, data: [model.predict_proba(features(score, row).reshape(score.size, -1))[:,1].reshape(score.shape)
                                 for score, row in zip(scores, data, strict=True)], elapsed


class CrossEncoder:
    def __init__(self, directory, threads):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.revision = (directory / 'revision.txt').read_text(encoding='ascii').strip()
        if len(self.revision) != 40:
            raise ValueError('Expected pinned model revision')
        model, tokenizer = directory / 'model.onnx', directory / 'tokenizer.json'
        self.identity = {'revision':self.revision, 'weight_sha256':file_sha(model), 'tokenizer_sha256':file_sha(tokenizer),
                         'weight_bytes':model.stat().st_size, 'ort':ort.__version__, 'threads':threads}
        self.tokenizer = Tokenizer.from_file(str(tokenizer))
        self.tokenizer.enable_truncation(max_length=128)
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id('<pad>'), pad_token='<pad>')
        settings = ort.SessionOptions()
        settings.intra_op_num_threads, settings.inter_op_num_threads = threads, 1
        self.session = ort.InferenceSession(str(model), settings, providers=['CPUExecutionProvider'])
        self.inputs = [item.name for item in self.session.get_inputs()]

    def predict(self, pairs):
        encoded = self.tokenizer.encode_batch(pairs)
        inputs = {key: np.array([getattr(item, attr) for item in encoded], dtype=np.int64) for key, attr in
                  (('input_ids','ids'), ('attention_mask','attention_mask'), ('token_type_ids','type_ids')) if key in self.inputs}
        logits = self.session.run(None, inputs)[0].reshape(-1)
        if len(logits) != len(pairs) or not np.all(np.isfinite(logits)):
            raise ValueError('Unexpected reranker logits')
        return logits


def rerank_set(encoder, documents, cache, batch):
    run, durations = [], []
    for doc in documents:
        texts = list(queries(doc, 'full'))
        targets = list(passages(doc['entity'], 'full').values())
        pairs = [(query, target) for query in texts for target in targets]
        key = sha({'identity':encoder.identity, 'pairs':pairs, 'batch':batch})
        cached = cache / (key + '.npz')
        if cached.exists():
            with np.load(cached, allow_pickle=False) as saved:
                values, elapsed = saved['scores'], float(saved['ms'])
        else:
            start = perf_counter()
            values = np.concatenate([encoder.predict(pairs[i:i+batch]) for i in range(0, len(pairs), batch)])
            elapsed = (perf_counter() - start) * 1000
            with cached.with_suffix('.tmp').open('wb') as stream:
                np.savez(stream, scores=values, ms=elapsed)
            cached.with_suffix('.tmp').replace(cached)
        matrix = values.reshape(len(texts), len(targets))
        run.append(matrix[:, :-1] - matrix[:, -1:])
        durations.append(elapsed)
    return run, timing(durations)


def shortlist(scores, preparation, method, external=None):
    selected = []
    for i, (matrix, raw) in enumerate(zip(scores, preparation, strict=True)):
        output = np.full(matrix.shape, -1e6)
        if method == 'rapid':
            for row, fields in enumerate(raw['rapid']):
                for column in fields:
                    j = raw['fields'].index(column)
                    output[row, j] = matrix[row, j]
        else:
            ix = np.argsort(-external[i], axis=1, kind='stable')[:, :3]
            output[np.arange(len(output))[:, None], ix] = matrix[np.arange(len(output))[:, None], ix]
        selected.append(output)
    return selected


def evaluate(args):
    start = perf_counter()
    train, train_sha = load_frozen(args.data, 'train')
    cal, cal_sha = load_frozen(args.data, 'calibration')
    manifest = json.loads((args.data / 'manifest.json').read_text(encoding='utf-8'))
    lexicon, prototypes = Lexicon(CATALOG), train_prototypes(train)
    cal_data = [prepare(doc, lexicon, prototypes) for doc in cal]
    gold = make_targets(cal, cal_data)
    cache = args.output / ('cache-' + args.model_id)
    cache.mkdir(parents=True, exist_ok=True)
    tick = perf_counter()
    if args.model_id == 'minilm':
        encoder = CrossEncoder(args.model, args.threads)
        identity = encoder.identity
    elif args.model_id == 'qwen':
        encoder = QwenEncoder(args.model, args.llama, args.threads, cache / 'llama-server.log')
        identity = {'revision':encoder.revision,'runtime':encoder.runtime,'weight_bytes':encoder.bytes}
    elif args.model_id == 'bge-q4':
        revision = (args.model / 'revision.txt').read_text(encoding='ascii').strip()
        checks = {filename:file_sha(args.model / filename) for filename in ('model.onnx','tokenizer.json')}
        encoder = OnnxEncoder(args.model, 'bge', args.threads, artifact_identity=(checks,revision))
        identity = {'revision':encoder.revision, 'runtime':encoder.runtime, 'weight_bytes':encoder.bytes, 'files':checks}
    else:
        encoder = OnnxEncoder(args.model, args.model_id, args.threads)
        identity = {'revision':encoder.revision,'runtime':encoder.runtime,'weight_bytes':encoder.bytes}
    init_elapsed = perf_counter() - tick
    cal_scores, final_models, train_info = {}, {}, {}

    def add(name, scores, predictor):
        cal_scores[name] = scores
        final_models[name] = predictor

    def dense(docs, mode, projection=None):
        sources, bank, times = embed_set(encoder, docs, mode, cache, args.batch)
        return embed_scores(sources, bank, docs, projection), times

    try:
        if args.model_id == 'minilm':
            scores, _ = rerank_set(encoder, cal, cache, args.batch)
            add('minilm-full-pairs+hold', scores, lambda docs, data: rerank_set(encoder, docs, cache, args.batch))
            def limited(docs, data):
                raw, times = rerank_set(encoder, docs, cache, args.batch)
                return shortlist(raw, data, 'rapid'), times
            add('rapid+minilm', shortlist(scores, cal_data, 'rapid'), limited)
        else:
            for mode in args.modes:
                scores, _ = dense(cal, mode)
                add(args.model_id + '-' + mode, scores, lambda docs, data, mode=mode: dense(docs, mode))
            if args.model_id == 'e5' and 'header' in args.modes:
                # All train rows use cached header vectors. Additional contexts never leak across splits.
                train_source, train_bank, _ = embed_set(encoder, train, 'header', cache, args.batch)
                projection, info = train_projection(train_source, train_bank, train)
                projection_file = args.output / 'e5-projection.npy'
                np.save(projection_file, projection, allow_pickle=False)
                train_info['e5-projection'] = {**info, 'sha256':file_sha(projection_file), 'train_sha256':train_sha}
                scores = embed_scores(train_source, train_bank, train)
                projected_train = embed_scores(train_source, train_bank, train, projection)
                projected_calibration, _ = dense(cal, 'header', projection)
                add('e5-projection', projected_calibration, lambda docs, data: dense(docs, 'header', projection))
                feature_data = [prepare(doc, lexicon, prototypes) for doc in train]
                for config in ('e5-pair-head', 'e5-hybrid-head', 'e5-projection-head'):
                    projected = config == 'e5-projection-head'
                    model, seconds = learn_pairs(projected_train if projected else scores, feature_data, train,
                                                 hybrid=config != 'e5-pair-head')
                    train_info[config] = {'fit_seconds':seconds, 'train_sha256':train_sha}
                    def scored(docs, data, model=model, projection=projection if projected else None):
                        raw, times = dense(docs, 'header', projection)
                        return model(raw, data), times
                    add(config, model(projected_calibration if projected else cal_scores['e5-header'], cal_data), scored)
        policies = {name:calibrate(scores, cal_data, gold) for name, scores in cal_scores.items()}
        final_sha = manifest['splits']['final']['sha256']
        fixed = {'calibration_sha256':cal_sha, 'final_sha256':final_sha, 'identity':identity, 'policies':policies}
        write(args.output / (args.model_id + '-frozen.json'), {**fixed, 'sha256':sha(fixed)})
        final, observed = load_frozen(args.data, 'final')
        assert final_sha == observed
        final_data = [prepare(doc, lexicon, prototypes) for doc in final]
        results = {}
        for name, model in final_models.items():
            scores, times = model(final, final_data)
            rows = [decisions(matrix, {**source, 'allowed':source['allowed'] & (matrix > -1e5)}, policies[name])
                    for matrix, source in zip(scores, final_data, strict=True)]
            values = metrics(final, rows)
            values.pop('case_counts')
            results[name] = {**values, 'inference_ms':times, 'status':'MEASURED'}
            export_mode = 'full' if 'full' in args.modes else 'header'
            if name in ('minilm-full-pairs+hold', args.model_id + '-' + export_mode):
                score_data = {'name':name, 'calibration_sha256':cal_sha, 'final_sha256':final_sha,
                              'calibration':[matrix.tolist() for matrix in cal_scores[name]], 'final':[matrix.tolist() for matrix in scores]}
                write(args.output / (args.model_id + '-scores.json'), {**score_data,'sha256':sha(score_data)})
            write(args.output / (args.model_id + '-results.json'), {'models':results, 'identity':identity,
                'training':train_info, 'startup_seconds':init_elapsed, 'peak_process_mib':peak_rss_mib(),
                'elapsed_seconds':perf_counter() - start, 'final_sha256':final_sha})
    finally:
        if args.model_id == 'qwen':
            encoder.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model_id', choices=('e5','bge','bge-q4','qwen','minilm'))
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--llama', type=Path)
    parser.add_argument('--data', type=Path, default=Path('.artifacts/mapping-research/data'))
    parser.add_argument('--output', type=Path, default=Path('.artifacts/mapping-research/results'))
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--batch', type=int, default=8)
    parser.add_argument('--modes', nargs='+', choices=MODES, default=MODES)
    args = parser.parse_args()
    try:
        evaluate(args)
    except (RuntimeError, ValueError, OSError, ImportError) as exc:
        write(args.output / (args.model_id + '-failure.json'), {'status':'FAILED','error':type(exc).__name__,'message':str(exc)[:320]})
        raise
