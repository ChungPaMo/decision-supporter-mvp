"""Small, preregistered local Qwen chat panel. Uses a loopback-only llama-server."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
from time import perf_counter, sleep
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from evaluate_mapping_embeddings import file_sha
from evaluate_mapping_research import metrics, timing, write
from mapping_research_data import canonical, load_frozen, sha
from mapping_research_features import CATALOG, Lexicon, prepare, train_prototypes
from mapping_research_remote import approved_bundle, chat_request, parse_mapping


REVISION = '23749fefcc72300e3a2ad315e1317431b06b590a'


def evaluate(args):
    final, digest = load_frozen(args.data, 'final')
    # Two fixed worksheets per entity selected by lexical document ID, without model scores.
    panel = [doc for entity in CATALOG for doc in sorted(final, key=lambda d: d['id']) if doc['id'].startswith('final-' + entity + '-') and doc['id'].endswith(('-000','-001'))]
    frozen = {'final_sha256':digest, 'documents': [doc['id'] for doc in panel],
              'modes': ['column', 'table', 'rapid-shortlist'], 'revision':REVISION,
              'weights_sha256':file_sha(args.model), 'seed':24}
    write(args.output / 'local-qwen-frozen.json', {**frozen, 'sha256':sha(frozen)})
    train, _ = load_frozen(args.data,'train')
    lexicon, prototypes = Lexicon(CATALOG), train_prototypes(train)
    panel_by_id = {doc['id']:doc for doc in panel}
    sources = {doc['id']:prepare(doc,lexicon,prototypes) for doc in panel}
    with socket.socket() as check:
        check.bind(('127.0.0.1',0))
        port = check.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    local = build_opener(ProxyHandler({}))
    started = perf_counter()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / 'local-qwen-server.log').open('w',encoding='utf-8') as log:
        process = subprocess.Popen([str(args.llama), '--model', str(args.model), '--alias', 'local-qwen3', '--host', '127.0.0.1',
            '--port', str(port), '--n-gpu-layers','0','--threads',str(args.threads),'--parallel','1','--ctx-size','3072','--jinja','--no-webui'],
            stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            deadline = perf_counter() + 60
            while perf_counter() < deadline and process.poll() is None:
                try:
                    with local.open(url + '/health',timeout=1):
                        break
                except (URLError, TimeoutError):
                    sleep(.15)
            else:
                raise RuntimeError('CPU local chat server did not start. See private runtime log.')
            initialized = perf_counter() - started
            results = {}
            for mode in frozen['modes']:
                bundle = approved_bundle(args.data,'final','table' if mode=='table' else 'column')
                resolved, failures, sizes, latencies, usage = {}, [], [], [], []
                for raw in bundle['requests']:
                    doc_id, _, index = raw['id'].partition(':')
                    if doc_id not in panel_by_id or (mode != 'table' and index != '0'):
                        continue
                    item = dict(raw)
                    if mode == 'rapid-shortlist':
                        item['permitted'] = sources[doc_id]['rapid'][0]
                        if not item['permitted']:
                            resolved[raw['id']] = None
                            continue
                    payload, allowed = chat_request(bundle,item,'local-qwen3')
                    payload['chat_template_kwargs'] = {'enable_thinking':False}
                    payload['seed'] = frozen['seed']
                    request = Request(url+'/v1/chat/completions', data=canonical(payload), headers={'Content-Type':'application/json'})
                    tick = perf_counter()
                    try:
                        with local.open(request,timeout=35) as response:
                            body = json.load(response)
                        mapping = parse_mapping(json.loads(body['choices'][0]['message']['content']),allowed)
                        for key, field in mapping.items():
                            resolved[f'{doc_id}:{key}'] = field
                        usage.append(body.get('usage',{}))
                    except (URLError, TimeoutError, TypeError, ValueError, KeyError, IndexError) as exc:
                        failures.append({'id':raw['id'],'type':type(exc).__name__,'http_status':getattr(exc,'code',None)})
                    sizes.append(len(allowed))
                    latencies.append((perf_counter()-tick)*1000)
                documents = [{**doc,'columns':doc['columns'] if mode=='table' else doc['columns'][:1]} for doc in panel]
                rows = [[{'prediction':resolved.get(f'{doc["id"]}:{i}'), 'ranking':None,
                          'top3':[resolved[f'{doc["id"]}:{i}']] if resolved.get(f'{doc["id"]}:{i}') else []}
                         for i in range(len(doc['columns']))] for doc in documents]
                scored = metrics(documents,rows)
                scored.pop('case_counts')
                results[mode] = {'status':('NOT_RUN' if not sizes else 'MEASURED' if len(failures)<len(sizes) else 'FAILED'),
                    'successful_requests':len(sizes)-len(failures),'request_failures':failures,'request_count':len(sizes),
                    'results':scored if len(failures)<len(sizes) or not sizes else None,
                    'latency_per_request':timing(latencies) if latencies else None, 'usage':usage}
                write(args.output / 'local-qwen-results.json', {'setup':frozen,'weight_bytes':args.model.stat().st_size,
                    'startup_seconds':initialized,'seconds':perf_counter()-started,'models':results})
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--llama', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=Path('.artifacts/mapping-research/data'))
    parser.add_argument('--output', type=Path, default=Path('.artifacts/mapping-research/results'))
    parser.add_argument('--threads', type=int, default=2)
    evaluate(parser.parse_args())
