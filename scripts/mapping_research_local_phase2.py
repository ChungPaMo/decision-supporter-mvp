"""Small one-model-at-a-time CPU panels for dedicated rerankers and local chat."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
from time import perf_counter, sleep
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

import numpy as np

from evaluate_mapping_embeddings import file_sha
from evaluate_mapping_research import calibrate, decisions, make_targets, peak_rss_mib, timing, write
from mapping_research_data import canonical, sha
from mapping_research_hybrid import as_matrices, read_scores
from mapping_research_neural import CrossEncoder, passages, queries
from mapping_research_phase2 import DATA, OUT, RESULTS, cpu_inputs, panel_indices, payload_for, scored
from mapping_research_remote import parse_mapping


QWEN3_REVISION = '23749fefcc72300e3a2ad315e1317431b06b590a'


@contextmanager
def local_server(executable, weights, log_path, threads, flags):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}'
    opener=build_opener(ProxyHandler({}))
    log_path.parent.mkdir(parents=True,exist_ok=True)
    with log_path.open('w',encoding='utf-8') as stream:
        args=[str(executable),'--model',str(weights),'--host','127.0.0.1','--port',str(port),'--alias','local-research',
              '--threads',str(threads),'--parallel','1','--n-gpu-layers','0','--no-webui',*flags]
        process=subprocess.Popen(args,stdout=stream,stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            until=perf_counter()+70
            while process.poll() is None and perf_counter()<until:
                try:
                    with opener.open(url+'/health',timeout=1):
                        break
                except (URLError,TimeoutError):
                    sleep(.2)
            else:
                raise RuntimeError('Local llama.cpp worker could not start')

            def call(path,payload):
                request=Request(url+path,data=canonical(payload),headers={'Content-Type':'application/json'})
                with opener.open(request,timeout=65) as reply:
                    return json.load(reply)

            yield call
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


def identity(args):
    weights=args.model if args.model.is_file() else args.model/'model.onnx'
    path=weights.with_name('revision.txt')
    revision=path.read_text('ascii').strip() if path.is_file() else QWEN3_REVISION
    if len(revision)!=40:
        raise ValueError('Local model revision missing')
    return {'revision':revision,'weight_sha256':file_sha(weights),'weight_bytes':weights.stat().st_size}


def chat(args):
    docs,digest,_,_,_=cpu_inputs(DATA,RESULTS,'final')
    docs=[docs[i] for i in panel_indices(docs,1)]
    setup={**identity(args),'data_sha256':digest,'document_ids':[d['id'] for d in docs],'context':4096,'reasoning_effort':'none'}
    results={}
    tick=perf_counter()
    with local_server(args.llama,args.model,args.output.with_suffix('.log'),args.threads,
                      ['--ctx-size','4096','--jinja','--reasoning-budget','0']) as call:
        startup=perf_counter()-tick
        for mode in ('column','table'):
            rows,elapsed,states=[],[],[]
            for doc in docs:
                indexes=[0] if mode=='column' else list(range(len(doc['columns'])))
                payload,expected=payload_for(doc,'local-research',indexes,single=mode=='column')
                schema=payload['response_format']['json_schema']['schema']
                schema['properties']['mapping'].update(minItems=len(indexes),maxItems=len(indexes))
                payload['response_format']={'type':'json_schema','schema':schema}
                payload['chat_template_kwargs']={'enable_thinking':False}
                payload['seed']=24
                best={}
                started=perf_counter()
                try:
                    response=call('/v1/chat/completions',payload)
                    choice=response['choices'][0]
                    status=choice['finish_reason']
                    if status=='stop':
                        best=parse_mapping(json.loads(choice['message']['content']),expected)
                    states.append({'id':doc['id'],'status':status,'usage':response.get('usage')})
                except (ValueError,KeyError,TypeError,IndexError,TimeoutError,URLError) as exc:
                    states.append({'id':doc['id'],'status':type(exc).__name__,'http_status':getattr(exc,'code',None)})
                elapsed.append((perf_counter()-started)*1000)
                rows.append([{'prediction':best.get(str(i)),'top3':[best[str(i)]] if best.get(str(i)) else [],
                              'ranking':None} for i in indexes])
            metric_docs=[{**d,'columns':d['columns'][:1]} if mode=='column' else d for d in docs]
            results[mode]={'requests':states,'timing_ms':timing(elapsed),'metrics':scored(metric_docs,rows)}
            write(args.output,{'identity':setup,'startup_seconds':startup,'elapsed_seconds':perf_counter()-tick,'modes':results})


def rerank_panel(split):
    docs,digest,records,cpu,_=cpu_inputs(DATA,RESULTS,split)
    indices=panel_indices(docs,1)
    cached={k:as_matrices(read_scores(RESULTS/filename),split,digest,records) for k,filename in
            [('mMiniLM','minilm-scores.json'),('BGE','bge-q4-scores.json'),('Qwen','qwen-scores.json')]}
    panel_docs=[{**docs[i],'columns':docs[i]['columns'][:4]} for i in indices]
    panel_data=[{**records[i],'allowed':records[i]['allowed'][:4]} for i in indices]
    scores={'LightGBM':[cpu[i][:4] for i in indices],**{k:[a[i][:4] for i in indices] for k,a in cached.items()}}
    return panel_docs,digest,panel_data,scores


def pair_scores(args, call, docs, records):
    mode=args.action
    if mode=='bge-reranker':
        def calculate(pairs):
            return np.concatenate([call.predict(pairs[i:i+12]) for i in range(0,len(pairs),12)])
    else:
        def calculate(pairs):
            options=[p[1] for p in pairs]
            data=call('/v1/rerank',{'query':pairs[0][0],'documents':options,'top_n':len(options)})
            ordered=sorted(data['results'],key=lambda r:r['index'])
            if [item['index'] for item in ordered]!=list(range(len(pairs))):
                raise ValueError('Incomplete llama.cpp reranker output')
            return np.asarray([item['relevance_score'] for item in ordered])
    values,elapsed=[],[]
    for doc,record in zip(docs,records,strict=True):
        describes=passages(doc['entity'],'confusion')
        fields=[*record['fields'],'HOLD']
        raw=[]
        for search in queries(doc,'full'):
            started=perf_counter()
            scores=calculate([(search,describes[f]) for f in fields])
            if not np.all(np.isfinite(scores)):
                raise ValueError('Non-finite reranker scores')
            raw.append(scores[:-1]-scores[-1])
            elapsed.append((perf_counter()-started)*1000)
        values.append(np.asarray(raw))
    return values,elapsed


def restrict(raw, candidates, record):
    mask=np.zeros_like(record['allowed'])
    for i,order in enumerate(np.argsort(-np.where(record['allowed'],candidates,-1e6),axis=1,kind='stable')):
        mask[i,order[:3]]=True
    allowed=record['allowed'] & mask
    return np.where(allowed,raw,-1e6),{**record,'allowed':allowed}


def rerank(args,call,setup):
    measurements={}
    policies={}
    for split in ('calibration','final'):
        docs,digest,records,reference=rerank_panel(split)
        setup[split]=[d['id'] for d in docs]
        setup[split+'_sha256']=digest
        cache=args.output.with_name(args.output.stem+'-'+split+'-scores.json')
        frozen={**setup,'split':split,'columns':[len(d['columns']) for d in docs]}
        if cache.exists():
            observed=read_scores(cache)
            if observed['setup']!=frozen:
                raise ValueError('Cached reranker configuration mismatch')
            raw,elapsed=[np.asarray(row) for row in observed['scores']],observed['elapsed']
        else:
            raw,elapsed=pair_scores(args,call,docs,records)
            observed={'setup':frozen,'scores':[row.tolist() for row in raw],'elapsed':elapsed}
            write(cache,{**observed,'sha256':sha(observed)})
        recipes={'all':(raw,records),'mMiniLM':(reference['mMiniLM'],records)}
        for name in ('LightGBM','BGE' if args.action=='bge-reranker' else 'Qwen'):
            blocks,profiles=zip(*(restrict(scores,candidate,record) for scores,candidate,record in
                                  zip(raw,reference[name],records,strict=True)),strict=True)
            recipes[name+'-top3']=(blocks,profiles)
        if split=='calibration':
            for name,(scores,profiles) in recipes.items():
                policies[name]=calibrate(scores,profiles,make_targets(docs,profiles))
            write(args.output.with_name(args.output.stem+'-policy.json'),{'setup':setup,'policies':policies})
        else:
            for name,(scores,profiles) in recipes.items():
                measurements[name]=scored(docs,[decisions(m,r,policies[name]) for m,r in zip(scores,profiles,strict=True)])
            write(args.output,{'setup':setup,'results':measurements,'column_ms':timing(elapsed),'peak_python_mib':peak_rss_mib()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('chat','bge-reranker','qwen-reranker'))
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--llama',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--threads',type=int,default=4)
    args=parser.parse_args()
    if args.action=='chat':
        chat(args)
    elif args.action=='bge-reranker':
        rerank(args,CrossEncoder(args.model,args.threads),identity(args))
    else:
        with local_server(args.llama,args.model,args.output.with_suffix('.log'),args.threads,
                          ['--ctx-size','4096','--embedding','--reranking','--pooling','rank']) as call:
            rerank(args,call,identity(args))


if __name__=='__main__':
    main()
