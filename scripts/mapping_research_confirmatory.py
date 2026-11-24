"""Build an independent local-only manufacturing panel and compare frozen decision policies."""
import argparse
from collections import Counter
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import random
from time import perf_counter

import numpy as np

from evaluate_mapping_research import (baseline_decisions, calibrate, decisions, fit_model, make_targets,
                                       metrics, peak_rss_mib, timing, write)
from mapping_research_data import csv_bytes, load_frozen, norm, sha
from mapping_research_features import CATALOG, Lexicon, prepare, train_prototypes
from mapping_research_phase2 import DATA, RESULTS
from mapping_research_hybrid import read_scores


OUTPUT = Path('.artifacts/mapping-research/phase2/confirmatory')
SEED = 614051
TERMS = {
    'product_id':'납품 시 사용하는 사내 분류 번호','product_name':'판매 라벨 인쇄 문구','product_type':'출하 관리 품종',
    'material_id':'수입검사 장부의 소재 식별자','material_name':'창고 라벨의 소재 호칭','base_unit':'자재 계수 기준',
    'unit':'원장에 표시된 계수 기호','safety_stock_qty':'최소 안전 보유량','bom_id':'배합등록 문서 식별표시',
    'bom_version':'원부자재 명세 판본','status':'명세 검토 현황','is_active':'현재 배합 적용 표시',
    'valid_from':'구성 개시 기준 날짜','valid_to':'구성 폐기 기준 날짜','base_qty':'표준 제조 배치','line_no':'전개 순번',
    'component_type':'투입 원료 분류','component_id':'구성재의 관리 키','qty_per':'기준 산출에 들어가는 자재 수량',
    'scrap_rate':'공정 감모 몫','item_type':'실사 분류','item_id':'실사 카드 대상 코드','as_of_date':'실사 기준일',
    'on_hand_qty':'출고 약정 포함 실사 합계','allocated_qty':'확정 출고분 자리 확보','available_qty':'현장 자유 사용 가능 잔량',
    'period':'납기 계획 월회계 구간','demand_qty':'수요 계획 승인 물량'}
DISTRACTORS = {'customer':'수하처 정산용 등록키','purchase':'입하 예정 구매 발주량','returns':'반품 검수 확정 개수',
               'money':'비용 계산 기준단가','unknown':'참고 계수','note':'순회 점검 의견'}


def fabricate_values(kind, field, rng, size, serial):
    if kind.endswith('_code'):
        prefix={'product_code':'CPM-P','material_code':'CPM-M','stock_code':'CPM-M','generic_code':'CPM-R'}[kind]
        return [f'{prefix}-{serial:02}-{j//2+40:04}' for j in range(size)]
    if kind in ('month','date'):
        start=date(2029,4,1)
        days=[start+timedelta(days=j*7+serial) for j in range(size)]
        return [d.strftime('%Y-%m' if kind=='month' else '%Y-%m-%d') for d in days]
    if kind in ('unit','version','bool','category','status','name'):
        options={'unit':('kg','m','EA','BOX'), 'version':('Rev-04','Rev-05'), 'bool':('TRUE','FALSE'),
                 'category':('원료','반제품','제품'), 'status':('APPROVED','HOLD'),
                 'name':('저온 원료 B','표준 배합용 15','검수품-나','포장 A 규격')}[kind]
        return [options[rng.randrange(len(options))] for _ in range(size)]
    if kind=='ratio':
        return [str(round(rng.expovariate(100),5)) for _ in range(size)]
    return [str(j+1 if field=='line_no' else round(50*rng.lognormvariate(1.3,.7),2)) for j in range(size)]


def create_documents():
    rng=random.Random(SEED)
    docs=[]
    for typ,fields in CATALOG.items():
        for n in range(20):
            family=n%5
            size=rng.randrange(5,15)
            forced=[f for f,spec in fields.items() if spec['required']]
            optional=[f for f in fields if f not in forced]
            selected=forced+rng.sample(optional,min(3,len(optional)))
            if family==4:
                selected.pop(0)
            columns=[]
            for f in selected:
                aliases=(f, f.replace('_',' '), TERMS[f], '현장 인계 / '+TERMS[f], '집계기준·'+TERMS[f])
                columns.append({'header':aliases[family],'expected':f,'scenario':'direct',
                                'values':fabricate_values(fields[f]['kind'],f,rng,size,n)})
            for role in rng.sample(list(DISTRACTORS),3):
                kind={'customer':'generic_code','money':'number','note':'name'}.get(role,'number')
                columns.append({'header':DISTRACTORS[role],'expected':None,'scenario':role,
                                'values':fabricate_values(kind,role,rng,size,n)})
            rng.shuffle(columns)
            if n==17:
                entity=next(f for f in CATALOG if f!=typ)
                columns=[{**c,'expected':None,'scenario':'wrong_route'} for c in columns]
            else:
                entity=typ
            doc={'id':f'confirm-{typ}-{n:02}', 'family':f'confirm-{typ}-{family}','entity':entity,'document_type':typ,
                 'title':f'{typ} · 현장 이관 확인서 {family+1}', 'columns':columns}
            doc['csv_sha256']=sha256(csv_bytes(doc)).hexdigest()
            docs.append(doc)
    return docs


def draft(out):
    payload={'scope':'LOCAL_ONLY_CONFIRMATORY_V1','seed':SEED,'documents':create_documents()}
    digest=sha(payload)
    write(out/'panel.json',{**payload,'sha256':digest})
    return digest


def locked_panel(out):
    raw=read_scores(out/'panel.json')
    if raw['scope']!='LOCAL_ONLY_CONFIRMATORY_V1' or raw['documents']!=create_documents():
        raise ValueError('The independent holdout no longer matches its generator')
    docs=raw['documents']
    if len(docs)!=100 or len({d['csv_sha256'] for d in docs})!=100:
        raise ValueError('Invalid external-template partition')
    return docs,sha(raw)


def cpu_reference(data=DATA, results=RESULTS):
    train,_=load_frozen(data,'train')
    lexicon, prototypes = Lexicon(CATALOG),train_prototypes(train)
    records=[prepare(doc,lexicon,prototypes) for doc in train]
    predict,seconds,_,_=fit_model('lightgbm','business',records,make_targets(train,records),threads=2)
    policy=read_scores(results/'frozen-policies.json')['policies']['lightgbm-business']
    return lexicon,prototypes,predict,policy,seconds


def ranker_fit(records, targets):
    from lightgbm import LGBMRanker

    inputs, gold = [], []
    for record,target in zip(records,targets,strict=True):
        for features,labels in zip(record['features'],target,strict=True):
            if labels.any():
                inputs.append(features)
                gold.append(labels)
    model=LGBMRanker(n_estimators=100,num_leaves=15,max_depth=6,learning_rate=.06,n_jobs=2,verbosity=-1,random_state=23)
    tick=perf_counter()
    model.fit(np.concatenate(inputs),np.concatenate(gold).astype(int),group=[len(x) for x in inputs])

    def predict(record):
        f=record['features']
        return model.booster_.predict(f.reshape(-1,f.shape[-1]),num_threads=2).reshape(f.shape[:2])
    return predict,perf_counter()-tick


def layered(record, model, mode):
    if mode=='binary':
        return model
    source=record['exact'] if mode=='exact_then_binary' else record['rapid']
    new=list(model)
    used=set()
    for i,override in enumerate(source):
        if override and record['allowed'][i,record['fields'].index(override[0])] and override[0] not in used:
            new[i]={'prediction':override[0],'top3':override,'ranking':None}
            used.add(override[0])
    for i,row in enumerate(model):
        if new[i] is row and row['prediction'] in used:
            new[i]={'prediction':None,'top3':[],'ranking':None}
    return new


def evaluate(out):
    docs,digest=locked_panel(out)
    lexicon,prototypes,binary,policy,binary_s=cpu_reference()
    train,train_sha=load_frozen(DATA,'train')
    cal,cal_sha=load_frozen(DATA,'calibration')
    known_headers={norm(col['header']) for doc in train+cal for col in doc['columns']}
    known_files={doc['csv_sha256'] for doc in train+cal}
    if known_files & {doc['csv_sha256'] for doc in docs}:
        raise ValueError('Holdout duplicate in development data')
    train_records=[prepare(doc,lexicon,prototypes) for doc in train]
    cal_records=[prepare(doc,lexicon,prototypes) for doc in cal]
    ranker,rank_s=ranker_fit(train_records,make_targets(train,train_records))
    rank_policy=calibrate([ranker(x) for x in cal_records],cal_records,make_targets(cal,cal_records))
    frozen={'train_sha256':train_sha,'calibration_sha256':cal_sha,'confirmatory_sha256':digest,
            'binary':policy,'ranker':rank_policy,'modes':['local_only','exact_then_binary','rapid_then_binary']}
    write(out/'policy.json',{**frozen,'sha256':sha(frozen)})
    records=[prepare(doc,lexicon,prototypes) for doc in docs]
    counters={}
    for name in ('exact','rapid','binary','ranker','exact_then_binary','rapid_then_binary'):
        rows,elapsed=[],[]
        for record in records:
            tick=perf_counter()
            if name in ('exact','rapid'):
                pred=baseline_decisions(record,name)
            elif name=='ranker':
                pred=decisions(ranker(record),record,rank_policy)
            else:
                pred=layered(record,decisions(binary(record),record,policy),name)
            rows.append(pred)
            elapsed.append((perf_counter()-tick)*1000 + (record['elapsed_ms'] if name not in ('exact','rapid') else record[name+'_ms']))
        value=metrics(docs,rows)
        value.pop('case_counts')
        counters[name]={'metrics':value,'document_ms':timing(elapsed)}
    write(out/'results.json',{'panel_sha256':digest,'header_overlap_with_train_cal':sum(norm(c['header']) in known_headers for d in docs for c in d['columns']),
          'learning_seconds':{'binary':binary_s,'ranker':rank_s},'peak_mib':peak_rss_mib(),'methods':counters,
          'family_counts':dict(Counter(d['family'] for d in docs))})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','evaluate'))
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args()
    if args.action=='prepare':
        print(draft(args.output))
    else:
        evaluate(args.output)


if __name__=='__main__':
    main()
