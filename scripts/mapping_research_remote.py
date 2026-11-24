"""Prepare and score Upstage comparisons. Network calls require explicit paid-run arguments."""
import argparse
from contextlib import contextmanager
from decimal import Decimal
import json
import os
from pathlib import Path
from time import perf_counter, sleep
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import numpy as np

from evaluate_mapping_research import calibrate, decisions, metrics, write
from mapping_research_data import SCOPE, canonical, load_frozen, sha
from mapping_research_features import CATALOG, Lexicon, prepare, train_prototypes
from mapping_research_neural import passages, queries


FIXED_SPLITS = {
    'calibration':'0ca04d71d809704a006bbdba237c79c3f56e92a01786939e79fd306b6a9fecee',
    'final':'0609378f9e16a6ded396998f028d96f39ccae37c0a0bc2694442c2d3f8761850',
}
CHAT = {'solar-mini4-260922': (Decimal('.10'), Decimal('.40')), 'solar-pro4-260806': (Decimal('.30'), Decimal('1.20'))}
EMBED = ('solar-embedding-2-query', 'solar-embedding-2-passage')
ENDPOINT = 'https://api.upstage.ai/v1'
MILLION = Decimal(1_000_000)
PRICE_DATE = '2026-11-24'


@contextmanager
def lock_paid_cache(directory):
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / 'active-paid-run.lock'
    with lock.open('x', encoding='utf-8') as stream:
        stream.write(str(os.getpid()))
    try:
        yield
    finally:
        lock.unlink()


def synthetic_documents(directory, split):
    docs, digest = load_frozen(directory, split)
    if digest != FIXED_SPLITS[split]:
        raise ValueError('External comparison only accepts the pinned synthetic research split')
    return docs, digest


def approved_bundle(directory, split, mode, shortlist=None):
    docs, digest = synthetic_documents(directory, split)
    if shortlist is not None and shortlist.get('data_sha256') != digest:
        raise ValueError('Candidate file does not match the synthetic split')
    catalog, requests = {entity:passages(entity, 'confusion' if mode == 'business' else 'full') for entity in CATALOG}, []
    for doc in docs:
        inputs = list(queries(doc, 'full'))
        if mode in ('table','business'):
            requests.append({'id':doc['id'], 'entity':doc['entity'],
                             'columns':[{'id':str(i), 'input':text} for i,text in enumerate(inputs)]})
        else:
            for i, text in enumerate(inputs):
                key = f'{doc["id"]}:{i}'
                permitted = list(CATALOG[doc['entity']]) if shortlist is None else shortlist['candidates'].get(key, [])
                if (len(set(permitted)) != len(permitted) or any(field not in CATALOG[doc['entity']] for field in permitted)):
                    raise ValueError('Unsupported shortlist field')
                requests.append({'id':key, 'entity':doc['entity'], 'input':text, 'permitted':permitted})
    body = {'scope':SCOPE, 'split':split, 'data_sha256':digest, 'mode':mode, 'catalog':catalog, 'requests':requests}
    return {**body, 'sha256':sha(body)}


def parse_mapping(array, expected):
    if not isinstance(array, dict) or set(array) != {'mapping'} or not isinstance(array['mapping'], list):
        raise ValueError('Invalid mapping wrapper')
    resolved, assigned = {}, set()
    for row in array['mapping']:
        if not isinstance(row, dict) or set(row) != {'id','field'}:
            raise ValueError('Unexpected mapping item')
        identifier, field = row['id'], row['field']
        if not isinstance(identifier, str) or not isinstance(field, str) or identifier not in expected or identifier in resolved:
            raise ValueError('Unexpected or duplicate response ID')
        if field != 'HOLD' and (field not in expected[identifier] or field in assigned):
            raise ValueError('Unsupported or duplicate target field')
        resolved[identifier] = None if field == 'HOLD' else field
        if field != 'HOLD':
            assigned.add(field)
    if set(resolved) != set(expected):
        raise ValueError('Incomplete mapping response')
    return resolved


def chat_request(bundle, item, model):
    vocabulary = bundle['catalog'][item['entity']]
    columns = item.get('columns', [{'id':'0', 'input':item.get('input')}])
    fields = item.get('permitted', list(CATALOG[item['entity']]))
    concepts = {field:vocabulary[field] for field in [*fields,'HOLD']}
    schema = {'type':'object', 'required':['mapping'], 'additionalProperties':False, 'properties':{
        'mapping':{'type':'array','items':{'type':'object', 'required':['id','field'], 'additionalProperties':False,
            'properties':{'id':{'type':'string','enum':[col['id'] for col in columns]},
                          'field':{'type':'string','enum':[*fields,'HOLD']}}}}}}
    instruction = ('Identify each synthetic column business meaning. Use only allowed fields. Use HOLD if ambiguous, incompatible, '
                   'unrelated, or needing aggregation or transformation. Never repeat a target field. Return every column ID.')
    return {'model':model, 'temperature':0, 'max_tokens':max(64, 32 * len(columns)), 'messages':[
        {'role':'system','content':instruction},{'role':'user','content':canonical({'concepts':concepts,'columns':columns}).decode('utf-8')}],
        'response_format':{'type':'json_schema','json_schema':{'name':'mapping_result','strict':True,'schema':schema}}}, {
        col['id']:set(fields) for col in columns}


def expected_cost(payload, rates):
    byte_bound = len(canonical(payload)) + 512
    return (rates[0] * byte_bound + rates[1] * payload.get('max_tokens', 0)) / MILLION


class RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class PaidResearch:
    def __init__(self, cache, cap, approved):
        if not approved or not cap.is_finite() or cap <= 0:
            raise ValueError('Explicit paid authorization and a positive USD limit are required')
        self.key = os.environ.get('UPSTAGE_API_KEY')
        if not self.key:
            raise ValueError('UPSTAGE_API_KEY must be set locally')
        self.cap, self.cache, self.spent = cap, cache, Decimal(0)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.opener = build_opener(RejectRedirect())
        self.audit = self.cache / 'billing.jsonl'
        if self.audit.exists():
            for line in self.audit.read_text(encoding='utf-8').splitlines():
                item = json.loads(line)
                self.spent += Decimal(item.get('cost_delta_usd', '0'))

    def record(self, item):
        with self.audit.open('ab') as stream:
            stream.write(canonical(item) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())

    def call(self, endpoint, payload, rates):
        key = sha({'endpoint':endpoint, 'payload':payload, 'priced_at':PRICE_DATE})
        path = self.cache / (key + '.json')
        if path.exists():
            prior = json.loads(path.read_text(encoding='utf-8'))
            if prior['request_sha256'] != key or prior['body_sha256'] != sha(prior['body']):
                raise ValueError('Cached result digest mismatch')
            return prior['body']
        reserve = expected_cost(payload, rates)
        if self.spent + reserve > self.cap:
            raise ValueError('Research budget would be exceeded')
        request = Request(ENDPOINT + endpoint, data=canonical(payload), method='POST',
                          headers={'Content-Type':'application/json','Authorization':'Bearer ' + self.key})
        clock = perf_counter()
        self.record({'request_sha256':key, 'state':'RESERVED', 'cost_delta_usd':str(reserve)})
        self.spent += reserve
        try:
            with self.opener.open(request, timeout=45) as response:
                body = json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            self.record({'request_sha256':key, 'state':'FAILED', 'error':type(exc).__name__,
                         'status':getattr(exc, 'code', None), 'ms':(perf_counter()-clock)*1000})
            raise ValueError('Upstage request failed. Reservation retained and no automatic retry sent.') from None
        usage = body.get('usage', {})
        inputs, outputs = usage.get('prompt_tokens'), usage.get('completion_tokens', 0)
        actual = (rates[0] * inputs + rates[1] * outputs) / MILLION if type(inputs) is int and type(outputs) is int and min(inputs,outputs) >= 0 else reserve
        self.record({'request_sha256':key, 'state':'RECEIVED', 'usage':usage, 'cost_delta_usd':str(actual-reserve),
                     'reported_cost_available':actual != reserve or type(inputs) is int, 'ms':(perf_counter()-clock)*1000})
        self.spent += actual - reserve
        write(path, {'request_sha256':key,'body_sha256':sha(body),'body':body})
        sleep(.7)  # Solar Embedding 2 documents 100 RPM per model.
        return body


def embedding_requests(bundle):
    query = [row['input'] for row in bundle['requests']]
    passages_ = list(dict.fromkeys(text for title in bundle['catalog'].values() for text in title.values()))
    return query, passages_


def embedded(client, texts, model):
    vectors = []
    for i in range(0, len(texts), 50):
        block = texts[i:i+50]
        message = client.call('/embeddings', {'model':model,'input':block}, (Decimal('.02'), Decimal(0)))
        rows = sorted(message['data'], key=lambda row:row['index'])
        if [row['index'] for row in rows] != list(range(len(block))):
            raise ValueError('Unexpected embedding results')
        matrix = np.asarray([row['embedding'] for row in rows], dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if matrix.shape != (len(block), 1024) or np.any(~np.isfinite(matrix)) or np.any(norms == 0):
            raise ValueError('Invalid embeddings')
        vectors.extend(matrix / norms)
    return vectors


def plan_remote(bundle, model):
    if bundle['mode'] == 'embed':
        groups = embedding_requests(bundle)
        payloads = [{'model':m,'input':rows[i:i+50]} for m,rows in zip(EMBED,groups,strict=True) for i in range(0,len(rows),50)]
        rates = (Decimal('.02'),Decimal(0))
    else:
        payloads = [chat_request(bundle,row,model)[0] for row in bundle['requests']]
        rates = CHAT[model]
    return {'status':'NOT_RUN','requests':len(payloads),'input_token_upper_estimate':sum(len(canonical(p))+512 for p in payloads),
            'output_token_max':sum(p.get('max_tokens',0) for p in payloads),
            'estimated_budget_usd':str(sum(expected_cost(p,rates) for p in payloads)), 'price_date':PRICE_DATE}


def run_remote(bundle, model, client, output):
    if bundle['mode'] == 'embed':
        source, reference = embedding_requests(bundle)
        vectors = embedded(client, source, EMBED[0])
        bank = dict(zip(reference, embedded(client, reference, EMBED[1]), strict=True))
        rows = {}
        for query, row in zip(vectors, bundle['requests'], strict=True):
            catalog = bundle['catalog'][row['entity']]
            hold = query @ bank[catalog['HOLD']]
            rows[row['id']] = {field:float(query @ bank[catalog[field]] - hold) for field in CATALOG[row['entity']]}
    else:
        rows = {}
        errors = {}
        for item in bundle['requests']:
            payload, expected = chat_request(bundle,item,model)
            try:
                body = client.call('/chat/completions', payload, CHAT[model])
                response = parse_mapping(json.loads(body['choices'][0]['message']['content']), expected)
            except (ValueError, IndexError, KeyError, TypeError) as exc:
                errors[item['id']] = type(exc).__name__
                if str(exc).startswith(('Research budget', 'Upstage request')):
                    raise
                continue
            for key, field in response.items():
                identifier = f'{item["id"]}:{key}' if 'columns' in item else item['id']
                rows[identifier] = field
    result = {'bundle_sha256':bundle['sha256'],'mode':bundle['mode'],'split':bundle['split'],'data_sha256':bundle['data_sha256'],
              'cost_used_or_reserved_usd':str(client.spent),'rows':rows, 'errors':{} if bundle['mode']=='embed' else errors}
    write(output, {**result, 'sha256':sha(result)})


def score_remote(data, result_path, bundle_path, calibration_path, output):
    result = json.loads(result_path.read_text(encoding='utf-8'))
    bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
    if (result.pop('sha256') != sha(result) or bundle.pop('sha256') != sha(bundle)
            or result['bundle_sha256'] != sha(bundle)
            or any(result[k] != bundle[k] for k in ('mode','split','data_sha256'))):
        raise ValueError('Result and exact label-free request bundle do not match')
    docs, digest = synthetic_documents(data, result['split'])
    if digest != result['data_sha256']:
        raise ValueError('Result digest does not match the frozen split')
    if result['mode'] == 'embed':
        from evaluate_mapping_research import make_targets
        train, _ = load_frozen(data,'train')
        lexicon, prototypes = Lexicon(CATALOG), train_prototypes(train)
        prepared = [prepare(doc,lexicon,prototypes) for doc in docs]
        def matrices(pointers, answers):
            return [np.array([[answers[f'{row["id"]}:{i}'][field] for field in row['fields']]
                              for i in range(len(row['allowed']))]) for row in pointers]
        raw = matrices(prepared,result['rows'])
        if result['split'] == 'calibration':
            policy = calibrate(raw,prepared,make_targets(docs,prepared))
            frozen = {'data_sha256':digest,'pipeline':'upstage-embedding-2','policy':policy}
            write(output, {**frozen,'sha256':sha(frozen)})
            return
        frozen = json.loads(calibration_path.read_text(encoding='utf-8'))
        if frozen.pop('sha256') != sha(frozen) or frozen['data_sha256'] != FIXED_SPLITS['calibration']:
            raise ValueError('External embedding policy must be frozen on calibration')
        rows = [decisions(score,record,frozen['policy']) for score,record in zip(raw,prepared,strict=True)]
    else:
        def pick(doc, i):
            field = result['rows'].get(f'{doc["id"]}:{i}')
            if field is not None and field not in CATALOG[doc['entity']]:
                raise ValueError('Invalid result field')
            return {'prediction':field,'top3':[field] if field else [],'ranking':None}
        rows = [[pick(doc,i) for i,_ in enumerate(doc['columns'])] for doc in docs]
    stats = metrics(docs,rows)
    stats.pop('case_counts')
    write(output, {'metrics':stats,'failed_requests':len(result['errors']),'actual_or_reserved_usd':result['cost_used_or_reserved_usd']})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('export','plan','run','score'))
    parser.add_argument('--data', type=Path, default=Path('.artifacts/mapping-research/data'))
    parser.add_argument('--split', choices=tuple(FIXED_SPLITS), default='calibration')
    parser.add_argument('--mode', choices=('column','table','business','embed'), default='column')
    parser.add_argument('--model', choices=tuple(CHAT), default='solar-mini4-260922')
    parser.add_argument('--shortlist', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--calibration', type=Path)
    parser.add_argument('--cache', type=Path, default=Path('.artifacts/mapping-research/upstage'))
    parser.add_argument('--approved-paid-api', action='store_true')
    parser.add_argument('--max-usd', type=Decimal, default=Decimal(0))
    args = parser.parse_args()
    if args.action == 'score':
        if not args.input or not args.bundle or (args.mode == 'embed' and args.split == 'final' and not args.calibration):
            parser.error('Score requires --input and --bundle, plus --calibration for final embedding')
        score_remote(args.data,args.input,args.bundle,args.calibration,args.output)
        return
    if args.mode != 'column' and args.shortlist:
        parser.error('Shortlists are only applicable to column chat requests')
    shortlist = json.loads(args.shortlist.read_text(encoding='utf-8')) if args.shortlist else None
    bundle = approved_bundle(args.data,args.split,args.mode,shortlist)
    if args.action == 'export':
        write(args.output,bundle)
    elif args.action == 'plan':
        write(args.output,plan_remote(bundle,args.model))
    else:
        if not args.approved_paid_api or not args.max_usd.is_finite() or args.max_usd <= 0:
            parser.error('Paid execution requires explicit authorization and a positive USD limit')
        with lock_paid_cache(args.cache):
            run_remote(bundle,args.model,PaidResearch(args.cache,args.max_usd,args.approved_paid_api),args.output)


if __name__ == '__main__':
    main()
