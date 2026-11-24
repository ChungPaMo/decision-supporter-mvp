"""Reproducible Upstage comparison on the three specifically approved synthetic splits."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal
from itertools import zip_longest
import json
from pathlib import Path

import numpy as np

from evaluate_mapping_research import baseline_decisions, decisions, timing, write
from contracts.mapping_review import (HOLD_CONCEPTS, KEYED_INSTRUCTION, SOLAR_PREVIEW, concept_vocabulary,
                                      decode_mapping, mapping_schema, solar_responses_payload, validate_mapping)
from mapping_research_confirmatory import OUTPUT as CONFIRM_DIR, cpu_reference, locked_panel
from mapping_research_data import canonical, sha
from mapping_research_features import CATALOG, prepare
from mapping_research_hybrid import read_scores
from mapping_research_neural import passages, queries
from mapping_research_phase2 import DATA, RESULTS, cpu_inputs, panel_indices, payload_for, scored
from mapping_research_remote import (APPROVED_CAP, CHAT, EMBED, FIXED_SPLITS, PRICE_DATE, SHARED_CACHE, VAT,
                                     BudgetExceeded, PaidResearch, ProviderFailure, embedded, expected_cost,
                                     load_local_key, lock_paid_cache)


OUT = Path('.artifacts/mapping-research/phase3')
CONFIRM_SHA = 'ea4a86ed84dcfd12400f46cd11ea87d3f6a266a89040299e611752ea7eba5649'
PREVIEW = SOLAR_PREVIEW
MODELS = {**dict(zip(('mini','pro'), CHAT, strict=True)), 'preview':PREVIEW}
RATES = {**CHAT, PREVIEW:(Decimal('.10'),Decimal('.40'))}
EMBED_RATE = (Decimal('.02'),Decimal(0))
MINI = MODELS['mini']


@dataclass(frozen=True)
class Recipe:
    model: str
    form: str = 'array'
    business: bool = True
    prior: str = ''
    treatment: str = ''


RECIPES = {
    'mini-table':Recipe(MINI,business=False), 'pro-table':Recipe(MODELS['pro'],business=False),
    'mini-business':Recipe(MINI), 'pro-business':Recipe(MODELS['pro']),
    'preview-business':Recipe(PREVIEW), 'keyed':Recipe(MINI,'keyed'), 'groups4':Recipe(MINI,'groups4'),
    'concept':Recipe(MINI,'concept'), 'column':Recipe(MINI,'column',business=False),
    'rapid-verify':Recipe(MINI,'keyed',prior='rapid',treatment='verify'),
    'rapid-hold':Recipe(MINI,'keyed',prior='rapid',treatment='hold'),
    'lightgbm-hold':Recipe(MINI,'keyed',prior='lightgbm',treatment='hold'),
    'lightgbm-verify':Recipe(MINI,'keyed',prior='lightgbm',treatment='verify'),
    'embed-solar':Recipe(MINI,'keyed',treatment='embed'),
}
CORE = ('mini-table','pro-table','mini-business','pro-business','preview-business')


@dataclass
class Corpus:
    docs: list
    digest: str
    records: list
    baselines: dict


def corpus(split, data=DATA, results=RESULTS, confirm=CONFIRM_DIR):
    if split == 'confirmatory':
        docs,digest = locked_panel(confirm)
        if digest != CONFIRM_SHA:
            raise ValueError('Independent research input does not match the approved Confirmatory SHA')
        lexicon,prototypes,predict,policy,_ = cpu_reference(data,results)
        records = [prepare(doc,lexicon,prototypes) for doc in docs]
        lightgbm = [decisions(predict(r),r,policy) for r in records]
    else:
        docs,digest,records,_,lightgbm = cpu_inputs(data,results,split)
    exact = [baseline_decisions(record,'exact') for record in records]
    rapid = [baseline_decisions(record,'rapid') for record in records]
    return Corpus(docs,digest,records,{'exact':exact,'rapid':rapid,'lightgbm':lightgbm})


def source_prior(panel, j, method):
    if method == 'lightgbm':
        baseline=panel.baselines[method][j]
    else:
        baseline=[e if e['prediction'] else r for e,r in zip(panel.baselines['exact'][j],panel.baselines['rapid'][j],strict=True)]
    picks={str(i):row['prediction'] for i,row in enumerate(baseline) if row['prediction']}
    unique=Counter(picks.values())
    return {key:field for key,field in picks.items() if unique[field]==1}


def build_request(doc, indexes, recipe, prior=None, candidates=None):
    locked = (prior or {}) if recipe.treatment == 'hold' else None
    wire,allowed=payload_for(doc,recipe.model,indexes,business=recipe.business,single=recipe.form=='column',previous=locked)
    vocab = {field:field for field in CATALOG[doc['entity']]} | {'HOLD':None}
    keyed = recipe.form in ('keyed','concept')
    if keyed:
        vocabulary=json.loads(wire['messages'][1]['content'])
        if recipe.form=='concept':
            vocab=concept_vocabulary(CATALOG[doc['entity']])
            vocabulary['concepts']={key:(vocabulary['concepts'][field] if field else HOLD_CONCEPTS[key])
                                    for key,field in vocab.items()}
        if recipe.treatment=='verify':
            vocabulary['proposed_fields_to_check']=prior or {}
            wire['messages'][0]['content']+=' Check the proposed fields independently and correct them or return HOLD if unsupported.'
        if candidates is not None:
            for key in allowed:
                allowed[key]=set(candidates.get(key,[]))
        wire['response_format']['json_schema']['schema']=mapping_schema(allowed,vocab,keyed=True)
        wire['messages'][0]['content']+=KEYED_INSTRUCTION
        wire['messages'][1]['content']=canonical(vocabulary).decode('utf-8')
    endpoint='/responses' if recipe.model==PREVIEW else '/chat/completions'
    return endpoint,solar_responses_payload(wire) if endpoint=='/responses' else wire,allowed,vocab,keyed

def decode_response(body,endpoint,allowed,vocab,keyed):
    result=decode_mapping(body,endpoint,allowed,vocab,keyed=keyed)
    return result.values,result.issues


def collision_guard(proposals, locked, record):
    def check(key, field):
        if not record['allowed'][int(key),record['fields'].index(field)]:
            return 'LOCAL_COMPATIBILITY'
        return None
    safe,rejected=validate_mapping(proposals,locked,check)
    return safe,Counter('DUPLICATE_TARGET' if reason=='EXISTING_MAPPING_CONFLICT' else reason
                        for reason in rejected.values())


def make_jobs(panel, indexes, name, embed_candidates):
    recipe=RECIPES[name]
    for j in indexes:
        prior=source_prior(panel,j,recipe.prior) if recipe.prior else {}
        n=len(panel.docs[j]['columns'])
        columns=[i for i in range(n) if recipe.treatment!='hold' or str(i) not in prior]
        group_size={'groups4':4,'column':1}.get(recipe.form,n)
        candidates=embed_candidates[j] if recipe.treatment=='embed' and embed_candidates is not None else None
        active=Recipe(recipe.model) if recipe.prior and not prior else recipe
        for start in range(0,len(columns),group_size):
            selected=columns[start:start+group_size]
            yield j,build_request(panel.docs[j],selected,active,prior,candidates)


def request_key(endpoint,payload):
    return sha({'endpoint':endpoint,'payload':payload,'priced_at':PRICE_DATE})


def run_job(client, job):
    j,(endpoint,payload,allowed,vocab,keyed)=job
    key=request_key(endpoint,payload)
    try:
        body=client.call(endpoint,payload,RATES[payload['model']])
    except BudgetExceeded:
        return j,key,{},Counter(NOT_RUN_BUDGET=1),True
    except ProviderFailure as exc:
        return j,key,{},Counter({f'PROVIDER_{exc.status or "NO_STATUS"}':1}),exc.status in (401,403,429)
    rows,issues=decode_response(body,endpoint,allowed,vocab,keyed)
    return j,key,rows,issues,False


def row_result(mapping,n):
    return [{'prediction':mapping.get(str(i)), 'top3':[mapping[str(i)]] if mapping.get(str(i)) else [],
             'ranking':None} for i in range(n)]


def summary(panel,indexes,name,jobs,observations,ledger):
    recipe=RECIPES[name]
    repairs,strict=defaultdict(dict),defaultdict(dict)
    errors=Counter()
    invalid=set()
    keys=set()
    for j,key,row,issues,_ in observations:
        keys.add(key)
        repairs[j].update(row)
        errors.update(issues)
        targets=Counter(f for f in row.values() if f)
        duplicates=sum(v for v in targets.values() if v>1)
        if duplicates:
            errors['DUPLICATE_TARGET_IN_RESPONSE']+=duplicates
        if issues or duplicates:
            invalid.add(j)
        else:
            strict[j].update(row)
    docs=[panel.docs[j] for j in indexes]
    measured={}
    for mode,values in (('strict',strict),('verified_partial',repairs)):
        picks=[]
        rejected=Counter()
        for j in indexes:
            prior=source_prior(panel,j,recipe.prior) if recipe.treatment=='hold' else {}
            safe,issues=collision_guard(values[j] if mode!='strict' or j not in invalid else {},prior,panel.records[j])
            rejected.update(issues)
            picks.append(row_result(safe,len(panel.docs[j]['columns'])))
        measured[mode]={'metrics':scored(docs,picks),'local_rejections':dict(rejected)}
    records=[entry for entry in ledger if entry['request_sha256'] in keys]
    seconds=[row['ms'] for row in records if 'ms' in row]
    spent=sum((Decimal(row.get('cost_delta_usd','0')) for row in records),Decimal(0))
    return {'documents':len(docs),'planned_requests':len(jobs),'attempted_or_cached':len(observations),
            'unattempted_requests':len(jobs)-len(observations),
            'contract_affected_documents':len(invalid),'errors':dict(errors),'cost_or_reserve_usd':str(spent),
            'request_ms':timing(seconds) if seconds else None, **measured}


def evaluate_recipes(client,panel,indexes,names,split,out,embed_candidates=None,workers=8):
    jobs={name:list(make_jobs(panel,indexes,name,embed_candidates)) for name in names}
    plans={name:{'requests':len(items),'upper_usd':str(VAT*sum(expected_cost(payload,RATES[payload['model']])
                                                            for _,(_,payload,*_) in items))} for name,items in jobs.items()}
    write(out/f'{split}-plan.json',{'data_sha256':panel.digest,'documents':[panel.docs[j]['id'] for j in indexes],'methods':plans})
    if client is None:
        return
    consumers=defaultdict(list)
    unique={}
    for group in zip_longest(*(jobs[name] for name in names)):
        for name,job in zip(names,group,strict=True):
            if job is None:
                continue
            endpoint,payload,*_=job[1]
            key=request_key(endpoint,payload)
            consumers[key].append((name,job[0]))
            unique.setdefault(key,job)
    observations=defaultdict(list)
    blocked=set()
    all_jobs=iter(unique.items())
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while batch := [item for _,item in zip(range(workers),all_jobs)]:
            futures={pool.submit(run_job,client,job):key for key,job in batch
                     if any(name not in blocked for name,_ in consumers[key])}
            for future in as_completed(futures):
                result=future.result()
                for name,j in consumers[futures[future]]:
                    observations[name].append((j,*result[1:]))
                    if result[-1]:
                        blocked.add(name)
    ledger=[json.loads(line) for line in client.audit.read_text('utf-8').splitlines()] if client.audit.exists() else []
    results={name:summary(panel,indexes,name,items,observations[name],ledger) for name,items in jobs.items()}
    baselines={name:scored([panel.docs[j] for j in indexes],[rows[j] for j in indexes]) for name,rows in panel.baselines.items()}
    write(out/f'{split}-results.json',{'data_sha256':panel.digest,'methods':results,'baselines':baselines,
                                      'shared_cost_usd':str(client.spent)})
    return results


def embed_shortlists(client, panel, target):
    descriptions={entity:passages(entity,'full') for entity in CATALOG}
    reference=list(dict.fromkeys(v for fields in descriptions.values() for v in fields.values()))
    document_texts=[list(queries(doc,'full')) for doc in panel.docs]
    texts=list(dict.fromkeys(v for row in document_texts for v in row))
    bank=dict(zip(reference,embedded(client,reference,EMBED[1]),strict=True))
    vectors=dict(zip(texts,embedded(client,texts,EMBED[0]),strict=True))
    result=[]
    for doc,texts,record in zip(panel.docs,document_texts,panel.records,strict=True):
        fields=record['fields']
        pool=np.array([bank[descriptions[doc['entity']][field]] for field in fields])
        scores=np.array([vectors[text] for text in texts]) @ pool.T
        ranks=np.argsort(-np.where(record['allowed'],scores,-1e6),axis=1,kind='stable')
        result.append({str(i):[fields[j] for j in order[:3] if record['allowed'][i,j]] for i,order in enumerate(ranks)})
    public={'data_sha256':panel.digest,'candidates':result}
    write(target,{**public,'sha256':sha(public)})
    return result


def select_policy(results):
    choices=('mini-business','keyed','groups4','concept')
    def rank(name):
        stats=results[name]['verified_partial']['metrics']
        return (stats['precision'] is not None and stats['precision']>=.95,
                stats['correct']-2*stats['wrong'], -stats['wrong'])
    return max(choices,key=rank)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('plan','calibrate','evaluate'))
    parser.add_argument('--output',type=Path,default=OUT)
    parser.add_argument('--split',choices=('calibration','final','confirmatory'),default='final')
    parser.add_argument('--methods',nargs='+',choices=tuple(RECIPES))
    parser.add_argument('--per-entity',type=int,choices=range(1,6),help='Limit supplementary evaluations to a fixed balanced panel')
    parser.add_argument('--workers',type=int,choices=range(1,13),default=8)
    parser.add_argument('--approved-paid-api',action='store_true')
    parser.add_argument('--max-usd',type=Decimal,default=Decimal('10'))
    args=parser.parse_args()
    split='calibration' if args.action=='calibrate' else args.split
    panel=corpus(split)
    names=args.methods or CORE
    indexes=panel_indices(panel.docs,args.per_entity) if args.per_entity else list(range(len(panel.docs)))
    frozen_path=(args.output if args.action=='calibrate' else OUT)/'policy.json'
    if args.action=='calibrate':
        names=(*CORE,'keyed','groups4','concept','column','rapid-verify','rapid-hold','lightgbm-hold','lightgbm-verify','embed-solar')
        indexes=panel_indices(panel.docs,2)
    if args.action=='evaluate':
        frozen=read_scores(frozen_path)
        if frozen['calibration_sha256']!=FIXED_SPLITS['calibration'] or args.split=='calibration':
            parser.error('Evaluation requires the frozen Calibration policy and a held-out split')
        names=args.methods or tuple(dict.fromkeys((*CORE,frozen['selected'],'rapid-verify','rapid-hold','lightgbm-hold')))
    if args.action=='plan':
        evaluate_recipes(None,panel,indexes,names,split,args.output)
        return
    if not args.approved_paid_api or not args.max_usd.is_finite() or not 0<args.max_usd<=APPROVED_CAP or not load_local_key():
        parser.error('Paid research requires approval, a local key and the shared hard cap')
    with lock_paid_cache(SHARED_CACHE):
        client=PaidResearch(SHARED_CACHE,args.max_usd,True)
        candidates=None
        if 'embed-solar' in names:
            candidate_file=args.output/f'{split}-embedding.json'
            try:
                if candidate_file.exists():
                    bundle=read_scores(candidate_file)
                    if bundle['data_sha256']!=panel.digest:
                        raise ValueError('Mismatched embedding candidates')
                    candidates=bundle['candidates']
                else:
                    candidates=embed_shortlists(client,panel,candidate_file)
            except (BudgetExceeded,ProviderFailure) as exc:
                write(args.output/f'{split}-embedding-unavailable.json',{'status':type(exc).__name__})
                names=tuple(name for name in names if name!='embed-solar')
        results=evaluate_recipes(client,panel,indexes,names,split,args.output,candidates,args.workers)
    if args.action=='calibrate':
        policy={'calibration_sha256':panel.digest,'document_ids':[panel.docs[j]['id'] for j in indexes],
                'selected':select_policy(results),'results_sha256':sha(results),'guard':'verified_partial'}
        write(frozen_path,{**policy,'sha256':sha(policy)})


if __name__=='__main__':
    main()
