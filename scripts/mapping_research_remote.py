"""Prepare and score Upstage comparisons. Network calls require explicit paid-run arguments."""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from decimal import Decimal
import json
import os
from pathlib import Path
import re
from threading import Lock
from time import perf_counter, sleep
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import numpy as np

from evaluate_mapping_research import calibrate, decisions, metrics, timing, write
from contracts.mapping_review import SYSTEM, mapping_schema, solar_chat_payload
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
ROOT = Path(__file__).resolve().parents[1]
SHARED_CACHE = ROOT / '.artifacts/mapping-research/upstage'
APPROVED_CAP = Decimal('10')
PHASE9_APPROVED_CAP = Decimal('20')
VAT = Decimal('1.10')


def load_local_key(root=ROOT):
    path = root / '.env.upstage.local'
    if not path.is_file():
        return False
    matches = [match.group(1).strip() for line in path.read_text(encoding='utf-8-sig').splitlines()
               if (match := re.fullmatch(r'\s*(?:export\s+)?UPSTAGE_API_KEY\s*=\s*(.*?)\s*', line))]
    if len(matches) != 1:
        return False
    value = matches[0]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    if not value or any(c.isspace() for c in value):
        return False
    os.environ['UPSTAGE_API_KEY'] = value
    return True


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
    expected = {col['id']:set(fields) for col in columns}
    schema = mapping_schema(expected,{**{field:field for field in fields},'HOLD':None},keyed=False)
    content = canonical({'concepts': concepts, 'columns': columns}).decode('utf-8')
    return solar_chat_payload(model, SYSTEM, content, schema, max(64, 32 * len(columns))), expected


def expected_cost(payload, rates):
    byte_bound = len(canonical(payload)) + 512
    return (rates[0] * byte_bound + rates[1] * payload.get('max_tokens', payload.get('max_output_tokens', 0))) / MILLION


class RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class BudgetExceeded(ValueError):
    pass


class ProviderFailure(ValueError):
    def __init__(self, status, category=None):
        super().__init__('Upstage request failed. Reservation retained.')
        self.status = status
        self.category = category


def provider_error_category(error):
    if not isinstance(error, HTTPError) or error.code not in (400, 422):
        return None
    try:
        data = json.loads(error.read(4096))
    except (OSError, ValueError):
        return None
    reply = data.get('error') if isinstance(data, dict) else None
    description = (str((reply or data)).lower())
    for category, needles in {
        'SCHEMA': ('schema','additionalproperties'), 'LOCATION': ('location_granularity','word_coordinates'),
        'MEDIA': ('unsupported file','file type','invalid document','image_url','base64'),
        'MODEL': ('model name','unsupported model','model not found'),
    }.items():
        if any(needle in description for needle in needles):
            return category
    return 'REQUEST_REJECTED'


class PaidResearch:
    def __init__(self, cache, cap, approved, *, phase9=False):
        maximum = PHASE9_APPROVED_CAP if phase9 else APPROVED_CAP
        if not approved or not cap.is_finite() or not 0 < cap <= maximum:
            raise ValueError(f'Explicit paid authorization and a limit within the approved USD {maximum} are required')
        if phase9 and cache.resolve() != SHARED_CACHE.resolve():
            raise ValueError('Phase 9 paid authorization is limited to the shared research ledger')
        self.key = os.environ.get('UPSTAGE_API_KEY')
        if not self.key:
            raise ValueError('UPSTAGE_API_KEY must be set locally')
        self.cap, self.cache, self.spent = cap, cache, Decimal(0)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.opener = build_opener(RejectRedirect())
        self.audit = self.cache / 'billing.jsonl'
        self.lock = Lock()
        self.requested = set()
        self.next_by_model = {}
        if self.audit.exists():
            for line in self.audit.read_text(encoding='utf-8').splitlines():
                item = json.loads(line)
                self.spent += Decimal(item.get('cost_delta_usd', '0'))
                if item['state'] == 'RESERVED':
                    self.requested.add(item['request_sha256'])
        if not self.spent.is_finite() or self.spent < 0:
            raise ValueError('Invalid shared budget ledger')

    def record(self, item):
        with self.audit.open('ab') as stream:
            stream.write(canonical(item) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())

    def call(self, endpoint, payload, rates):
        def measured(body):
            usage = body.get('usage') or {}
            inputs = usage.get('prompt_tokens', usage.get('input_tokens'))
            outputs = usage.get('completion_tokens', usage.get('output_tokens', 0))
            if type(inputs) is int and type(outputs) is int and min(inputs, outputs) >= 0:
                return VAT * (rates[0] * inputs + rates[1] * outputs) / MILLION
            return None

        return self.request(endpoint, payload, canonical(payload), 'application/json',
                            VAT * expected_cost(payload, rates), measured)

    def cached_response(self, endpoint, identity):
        key = sha({'endpoint':endpoint, 'payload':identity, 'priced_at':PRICE_DATE})
        path = self.cache / (key + '.json')
        if not path.exists():
            return None
        prior = json.loads(path.read_text(encoding='utf-8'))
        if prior['request_sha256'] != key or prior['body_sha256'] != sha(prior['body']):
            raise ValueError('Cached result digest mismatch')
        return prior['body']

    def request(self, endpoint, identity, wire, content_type, reserve, measured):
        if endpoint not in {'/chat/completions', '/responses', '/embeddings', '/document-digitization',
                            '/document-classification', '/information-extraction'}:
            raise ValueError('Unsupported Upstage research endpoint')
        key = sha({'endpoint':endpoint, 'payload':identity, 'priced_at':PRICE_DATE})
        path = self.cache / (key + '.json')
        meta = {'request_sha256':key, 'endpoint':endpoint, 'model':identity['model'], 'mode':identity.get('mode'),
                'format':identity.get('format'), 'max_pages':identity.get('max_pages')}
        with self.lock:
            prior = self.cached_response(endpoint,identity)
            if prior is not None:
                return prior
            if key in self.requested:
                raise ProviderFailure(None)
            if not reserve.is_finite() or reserve < 0 or self.spent + reserve > self.cap:
                raise BudgetExceeded('Research budget would be exceeded')
            self.record({**meta, 'state':'RESERVED', 'cost_delta_usd':str(reserve)})
            self.spent += reserve
            self.requested.add(key)
            model = identity['model']
            send_at = max(perf_counter(), self.next_by_model.get(model, 0))
            self.next_by_model[model] = send_at + .70
        sleep(max(0, send_at - perf_counter()))
        request = Request(ENDPOINT + endpoint, data=wire, method='POST',
                          headers={'Content-Type':content_type,'Authorization':'Bearer ' + self.key})
        clock = perf_counter()
        try:
            with self.opener.open(request, timeout=60) as response:
                body = json.load(response)
            if not isinstance(body, dict):
                raise ValueError('Unexpected provider object')
        except (HTTPError, URLError, OSError, ValueError) as exc:
            status = getattr(exc, 'code', None)
            category = provider_error_category(exc)
            with self.lock:
                self.record({**meta, 'state':'FAILED', 'error':type(exc).__name__, 'status':status,
                             'category':category, 'ms':(perf_counter()-clock)*1000})
            raise ProviderFailure(status,category) from None
        actual = measured(body)
        delta = actual - reserve if actual is not None else Decimal(0)
        with self.lock:
            self.record({**meta, 'state':'RECEIVED', 'usage':body.get('usage'),
                         'cost_delta_usd':str(delta), 'calculated_cost_usd':str(actual) if actual is not None else None,
                         'ms':(perf_counter()-clock)*1000})
            self.spent += delta
            write(path, {'request_sha256':key,'body_sha256':sha(body),'body':body})
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


def billing_summary(cache):
    path=cache/'billing.jsonl'
    entries=[json.loads(line) for line in path.read_text('utf-8').splitlines()] if path.exists() else []
    groups=defaultdict(list)
    for row in entries:
        groups[(row.get('model') or 'legacy',row.get('mode') or 'default')].append(row)
    grouped=[]
    for (model,mode),rows in sorted(groups.items()):
        statuses=Counter(row['state'] for row in rows)
        received=[row for row in rows if row['state']=='RECEIVED']
        usage=[row.get('usage') or {} for row in received]
        cost=sum((Decimal(row.get('cost_delta_usd','0')) for row in rows),Decimal(0))
        measured=sum((Decimal(row['calculated_cost_usd']) for row in received if row.get('calculated_cost_usd') is not None),Decimal(0))
        grouped.append({'model':model,'mode':mode,'http_requests':statuses['RESERVED'],'responses':statuses['RECEIVED'],
                        'failed_requests':statuses['FAILED'],'prompt_tokens':sum(u.get('prompt_tokens',u.get('input_tokens')) or 0 for u in usage),
                        'completion_tokens':sum(u.get('completion_tokens',u.get('output_tokens')) or 0 for u in usage),
                        'reported_pages':sum(u.get('pages') or 0 for u in usage),
                        'latency':timing([r['ms'] for r in rows if 'ms' in r]) if statuses['RECEIVED']+statuses['FAILED'] else None,
                        'usage_calculated_usd':str(measured),'cost_or_reserve_usd':str(cost)})
    spent=sum((Decimal(row['cost_or_reserve_usd']) for row in grouped),Decimal(0))
    return {'calls':sum(row['http_requests'] for row in grouped),'models':grouped,'cost_or_reserve_usd':str(spent),
            'remaining_approved_budget_usd':str(APPROVED_CAP-spent)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('export','plan','run','score','audit'))
    parser.add_argument('--data', type=Path, default=Path('.artifacts/mapping-research/data'))
    parser.add_argument('--split', choices=tuple(FIXED_SPLITS), default='calibration')
    parser.add_argument('--mode', choices=('column','table','business','embed'), default='column')
    parser.add_argument('--model', choices=tuple(CHAT), default='solar-mini4-260922')
    parser.add_argument('--shortlist', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--calibration', type=Path)
    parser.add_argument('--cache', type=Path, default=SHARED_CACHE)
    parser.add_argument('--approved-paid-api', action='store_true')
    parser.add_argument('--max-usd', type=Decimal, default=Decimal(0))
    args = parser.parse_args()
    if args.action == 'audit':
        write(args.output,billing_summary(args.cache))
        return
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
        if not args.approved_paid_api or not args.max_usd.is_finite() or not 0 < args.max_usd <= APPROVED_CAP:
            parser.error(f'Paid execution requires explicit authorization and a cap within USD {APPROVED_CAP}')
        if args.cache.resolve() != SHARED_CACHE.resolve():
            parser.error('Paid execution requires the shared research cache and ledger')
        if not load_local_key():
            parser.error('Local key is unavailable')
        with lock_paid_cache(args.cache):
            run_remote(bundle,args.model,PaidResearch(args.cache,args.max_usd,args.approved_paid_api),args.output)


if __name__ == '__main__':
    main()
