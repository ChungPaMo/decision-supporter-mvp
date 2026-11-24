"""Run fixed-split Solar and Embedding 2 experiments against Phase 1 CPU scores."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from pathlib import Path

import numpy as np

from evaluate_mapping_research import baseline_decisions, calibrate, decisions, make_targets, metrics, write
from mapping_research_data import canonical, load_frozen, sha
from mapping_research_features import CATALOG, Lexicon, prepare, train_prototypes
from mapping_research_hybrid import as_matrices, read_scores
from mapping_research_neural import passages, queries
from mapping_research_remote import (APPROVED_CAP, CHAT, EMBED, SHARED_CACHE, VAT, BudgetExceeded,
                                     PaidResearch, ProviderFailure, chat_request, embedded, expected_cost,
                                     load_local_key, lock_paid_cache, parse_mapping, synthetic_documents)


DATA = Path('.artifacts/mapping-research/data')
RESULTS = Path('.artifacts/mapping-research/results')
OUT = Path('.artifacts/mapping-research/phase2')
MODEL_BY_SIZE = dict(zip(('mini', 'pro'), CHAT, strict=True))
EMBED_MODES = ('header', 'dtype-values', 'full', 'business', 'confusion')


def input_bundle(doc, *, business=False):
    mode = 'confusion' if business else 'full'
    columns = [{'id':str(i), 'input':text} for i,text in enumerate(queries(doc,mode))]
    return {'catalog':{doc['entity']:passages(doc['entity'],mode)}}, columns


def payload_for(doc, model, indexes, *, business=False, single=False, permitted=None, previous=None):
    bundle, columns = input_bundle(doc, business=business)
    selected = [columns[i] for i in indexes]
    item = {'entity':doc['entity'], 'columns':selected}
    if permitted is not None:
        item['permitted'] = permitted
    payload, expected = chat_request(bundle,item,model)
    submitted = json.loads(payload['messages'][1]['content'])
    if not single:
        submitted['title'] = doc['title']
        submitted['aligned_sample_rows'] = list(zip(*[col['values'][:3] for col in doc['columns']]))
        submitted['column_order'] = [col['id'] for col in columns]
        submitted['headers_in_sample_order'] = [col['header'] for col in doc['columns']]
    if previous:
        submitted['existing_review_candidates'] = previous
        payload['messages'][0]['content'] += ' Do not reuse fields in existing_review_candidates on new columns.'
    payload['messages'][1]['content'] = canonical(submitted).decode()
    payload['reasoning_effort'] = 'none'
    payload['max_tokens'] = 128 + 40 * len(selected)
    return payload, expected


def recommend(client, payload, expected):
    try:
        response = client.call('/chat/completions', payload, CHAT[payload['model']])
    except BudgetExceeded:
        return {}, 'NOT_RUN_BUDGET'
    except ProviderFailure as exc:
        return {}, f'FAILED_PROVIDER_{exc.status or "NO_STATUS"}'
    try:
        choice = response['choices'][0]
        if choice['finish_reason'] != 'stop':
            return {}, f'FAILED_FINISH_{choice["finish_reason"]}'
        return parse_mapping(json.loads(choice['message']['content']),expected), None
    except (TypeError, KeyError, IndexError, ValueError):
        return {}, 'FAILED_CONTRACT'


def cpu_inputs(data, results, split):
    train, _ = load_frozen(data,'train')
    docs, digest = synthetic_documents(data,split)
    lexicon, prototypes = Lexicon(CATALOG), train_prototypes(train)
    records = [prepare(doc,lexicon,prototypes) for doc in docs]
    scores = as_matrices(read_scores(results/'cpu-selected-scores.json'),split,digest,records)
    policy = read_scores(results/'frozen-policies.json')['policies']['lightgbm-business']
    cpu = [decisions(matrix,row,policy) for matrix,row in zip(scores,records,strict=True)]
    return docs,digest,records,scores,cpu


def panel_indices(docs, per_entity):
    counts = dict.fromkeys(CATALOG,0)
    indexes = []
    for j, doc in enumerate(docs):
        entity = doc['entity']
        if counts[entity] < per_entity:
            indexes.append(j)
            counts[entity] += 1
    return indexes


def chat_jobs(docs, records, scores, cpu, ids, model, mode, candidate_scores=None, columns_per_doc=None):
    for j in ids:
        doc, record = docs[j], records[j]
        count = len(doc['columns'])
        if columns_per_doc is not None:
            count = min(count,columns_per_doc)
        fallback = mode in ('hold','hold-column')
        indexes = [i for i in range(count) if not fallback or cpu[j][i]['prediction'] is None]
        if mode in ('column','shortlist','hold-column','embed-shortlist'):
            matrix = candidate_scores[j] if candidate_scores is not None else scores[j]
            for i in indexes:
                allowed = None
                if mode in ('shortlist','embed-shortlist'):
                    indexes_by_score = np.argsort(-matrix[i],kind='stable')
                    allowed = [record['fields'][k] for k in indexes_by_score if record['allowed'][i,k]][:3]
                    if not allowed:
                        continue
                yield j, payload_for(doc,model,[i],business=mode!='column',single=True,permitted=allowed)
        elif indexes:
            previous = ({str(i):row['prediction'] for i,row in enumerate(cpu[j]) if row['prediction']}
                        if fallback else None)
            yield j, payload_for(doc,model,indexes,business=mode in ('business','hold'),previous=previous)


def scored(docs, predictions):
    result = metrics(docs,predictions)
    result.pop('case_counts',None)
    return result


def chat_experiment(args,client):
    docs,digest,records,scores,cpu = cpu_inputs(args.data,args.results,args.split)
    ids = panel_indices(docs,args.per_entity) if args.per_entity else list(range(len(docs)))
    model = MODEL_BY_SIZE[args.model]
    candidate = None
    if args.mode=='embed-shortlist':
        bundle=read_scores(args.embed_scores)
        keys=bundle.get(args.split+'_documents')
        if keys is None:
            candidate=as_matrices(bundle,args.split,digest,records)
        else:
            if keys != [docs[j]['id'] for j in ids]:
                raise ValueError('Embedding subset does not match selected chat documents')
            candidate=dict(zip(ids,as_matrices(bundle,args.split,digest,[records[j] for j in ids]),strict=True))
    jobs = list(chat_jobs(docs,records,scores,cpu,ids,model,args.mode,candidate,args.columns_per_doc))
    write(args.output.with_name(args.output.stem+'-plan.json'),{'split_sha256':digest,'model':model,'mode':args.mode,
          'documents':[docs[j]['id'] for j in ids],'request_hashes':[sha(payload) for _,(payload,_) in jobs],
          'estimated_max_usd_with_vat':str(VAT * sum(expected_cost(p,CHAT[model]) for _,(p,_) in jobs))})
    if args.plan:
        return

    def run(job):
        j,(payload,expected) = job
        return j,sha(payload),recommend(client,payload,expected)

    by_document, failures, attempted = {}, {}, 0
    remaining = iter(jobs)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        while batch := [job for _, job in zip(range(args.workers),remaining)]:
            terminal = False
            for j, request_sha, (rows,error) in pool.map(run,batch):
                attempted += 1
                if error:
                    failures[request_sha] = error
                    terminal |= error in ('FAILED_PROVIDER_401','FAILED_PROVIDER_403','NOT_RUN_BUDGET')
                by_document.setdefault(j,{}).update(rows)
            if terminal:
                break

    predictions, violations = [], 0
    fallback = args.mode in ('hold','hold-column')
    for j in ids:
        record = records[j]
        used = {p['prediction'] for p in cpu[j] if fallback and p['prediction']}
        row = []
        for i in range(len(docs[j]['columns'])):
            previous = cpu[j][i]['prediction'] if fallback else None
            field = by_document.get(j,{}).get(str(i))
            if field and (field in used or not record['allowed'][i,record['fields'].index(field)]):
                field = None
                violations += 1
            if field:
                used.add(field)
            if previous:
                row.append(cpu[j][i])
            else:
                row.append({'prediction':field,'top3':[field] if field else [],'ranking':None})
        predictions.append(row)
    selected = [{**docs[j],'columns':docs[j]['columns'][:args.columns_per_doc]} for j in ids]
    baseline = scored(selected,[cpu[j][:args.columns_per_doc] for j in ids])
    observed = scored(selected,[r[:args.columns_per_doc] for r in predictions])
    write(args.output,{'split':args.split,'split_sha256':digest,'model':model,'mode':args.mode,
                       'planned_requests':len(jobs),'attempted_or_cached':attempted,
                       'failed_requests':failures,'rejected_after_model':violations,
                       'lightgbm':baseline,'rapidfuzz':scored(selected,[baseline_decisions(records[j],'rapid')[:args.columns_per_doc] for j in ids]),
                       'metrics':observed,'decisions':{docs[j]['id']:r for j,r in zip(ids,predictions,strict=True)},
                       'shared_cost_usd':str(client.spent)})


def embedding_experiment(args,client):
    score_bundle = {'name':'upstage-embedding-'+args.mode}
    for split in ('calibration','final'):
        docs,digest,records,_,_ = cpu_inputs(args.data,args.results,split)
        if args.per_entity:
            panel = panel_indices(docs,args.per_entity)
            docs,records = [docs[i] for i in panel],[records[i] for i in panel]
            score_bundle[split+'_documents'] = [doc['id'] for doc in docs]
        descriptions = {entity:passages(entity,args.mode) for entity in CATALOG}
        if args.mode == 'header':
            descriptions = {entity:{field:field.replace('_',' ') if field != 'HOLD' else text
                                    for field,text in fields.items()} for entity,fields in descriptions.items()}
        references = list(dict.fromkeys(text for fields in descriptions.values() for text in fields.values()))
        if args.mode=='dtype-values':
            prepared_text = [[q+'\nSamples: '+', '.join(col['values'][:3])
                              for q,col in zip(queries(doc,'dtype'),doc['columns'],strict=True)] for doc in docs]
        else:
            prepared_text = [list(queries(doc,args.mode)) for doc in docs]
        unique = list(dict.fromkeys(text for col in prepared_text for text in col))
        if split == 'calibration':
            bank = dict(zip(references,embedded(client,references,EMBED[1]),strict=True))
        vectors = dict(zip(unique,embedded(client,unique,EMBED[0]),strict=True))
        matrices = []
        for doc,record,columns in zip(docs,records,prepared_text,strict=True):
            fields = descriptions[doc['entity']]
            hold = bank[fields['HOLD']]
            targets = np.array([bank[fields[f]]-hold for f in record['fields']])
            matrices.append(np.array([vectors[text] for text in columns]) @ targets.T)
        score_bundle[split+'_sha256'] = digest
        score_bundle[split] = [matrix.tolist() for matrix in matrices]
        if split == 'calibration':
            policy = calibrate(matrices,records,make_targets(docs,records))
            frozen = {'calibration_sha256':digest, 'policy':policy,'mode':args.mode}
            write(args.output.with_name(args.output.stem+'-policy.json'),{**frozen,'sha256':sha(frozen)})
    write(args.output.with_name(args.output.stem+'-scores.json'),{**score_bundle,'sha256':sha(score_bundle)})
    rows = [decisions(matrix,record,policy) for matrix,record in zip(matrices,records,strict=True)]
    write(args.output,{'model':list(EMBED),'mode':args.mode,'final_sha256':digest,
                       'documents':[doc['id'] for doc in docs], 'metrics':scored(docs,rows),
                       'shared_cost_usd':str(client.spent)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('chat','embed'))
    parser.add_argument('--data',type=Path,default=DATA)
    parser.add_argument('--results',type=Path,default=RESULTS)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--split',choices=('calibration','final'),default='final')
    parser.add_argument('--mode',required=True)
    parser.add_argument('--model',choices=tuple(MODEL_BY_SIZE),default='mini')
    parser.add_argument('--per-entity',type=int,default=0)
    parser.add_argument('--columns-per-doc',type=int,choices=range(1,6))
    parser.add_argument('--workers',type=int,choices=range(1,5),default=4)
    parser.add_argument('--plan',action='store_true')
    parser.add_argument('--embed-scores',type=Path)
    parser.add_argument('--max-usd',type=Decimal,default=Decimal(4))
    parser.add_argument('--approved-paid-api',action='store_true')
    args = parser.parse_args()
    valid = ('table','business','hold','column','shortlist','hold-column','embed-shortlist') if args.action=='chat' else EMBED_MODES
    if args.mode not in valid or (args.mode=='embed-shortlist' and not args.embed_scores):
        parser.error('The experiment mode requires compatible arguments')
    if args.columns_per_doc and args.mode not in ('column','shortlist','embed-shortlist'):
        parser.error('Column caps apply to column or shortlist comparisons only')
    if args.plan:
        if args.action!='chat':
            parser.error('Use the remote plan command for an offline embedding estimate')
        chat_experiment(args,None)
        return
    if not args.approved_paid_api or not args.max_usd.is_finite() or not 0 < args.max_usd <= APPROVED_CAP:
        parser.error(f'Paid research requires explicit authorization within USD {APPROVED_CAP}')
    if not load_local_key():
        parser.error('Local key is unavailable')
    with lock_paid_cache(SHARED_CACHE):
        client = PaidResearch(SHARED_CACHE,args.max_usd,args.approved_paid_api)
        (chat_experiment if args.action=='chat' else embedding_experiment)(args,client)


if __name__=='__main__':
    main()
