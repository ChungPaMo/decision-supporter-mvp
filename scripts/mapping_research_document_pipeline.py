"""Compare cached Parse layouts and the local XLSX path on labeled flat BOM columns."""
import argparse
from collections import Counter
from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from evaluate_mapping_research import baseline_decisions, decisions, write
from mapping_research_confirmatory import cpu_reference
from mapping_research_document import (FLAT, OUT, baseline_document, document_call, local_tables,
                                       normalized, parse_tables, text, workbook_panel)
from mapping_research_features import prepare
from mapping_research_hybrid import read_scores
from mapping_research_phase2 import MODEL_BY_SIZE, payload_for, recommend
from mapping_research_remote import APPROVED_CAP, SHARED_CACHE, PaidResearch, load_local_key, lock_paid_cache


def unique_origin(tables, header):
    """Link an ordered header signature to a single XLSX header on any visible sheet."""
    search = tuple(normalized(v) for v in header)
    if not search or not all(search) or len(set(search))!=len(search):
        return None
    locations = []
    for ws in tables:
        for row in ws.iter_rows():
            values = [normalized(text(c.value)) for c in row]
            for i in range(len(values)-len(search)+1):
                if tuple(values[i:i+len(search)])==search:
                    locations.append((ws.title,row[i].row,i+1))
    return locations[0] if len(locations)==1 else None


def research_doc(fileid, title, header, rows):
    return {'id':fileid,'family':'existing-xlsx-flat-bom','entity':'bom','document_type':'bom','title':title,
            'columns':[{'header':value,'values':[row[index] if index<len(row) else '' for row in rows]}
                       for index,value in enumerate(header)]}


def count_recommendations(picks, roles):
    return {'gold_columns':len(FLAT),'correct':sum(p['prediction']==roles.get(i) and p['prediction'] is not None for i,p in enumerate(picks)),
            'top3':sum(roles.get(i) in p['top3'] for i,p in enumerate(picks)),
            'wrong':sum(p['prediction'] is not None and p['prediction']!=roles.get(i) for i,p in enumerate(picks)),
            'all_three':sum(p['prediction']==roles.get(i) and p['prediction'] is not None for i,p in enumerate(picks))==len(FLAT)}


def score_tables(item, tables, model, *, rapid=False, solar=None):
    result={'gold_columns':len(FLAT),'correct':0,'top3':0,'wrong':0,'all_three':False}
    if not tables or not tables[0]['headers'] or not tables[0]['body']:
        return result
    table=tables[0]
    labels=table['headers'][-1]
    run_labels=[value or f'Unnamed column {index}' for index,value in enumerate(labels,1)]
    book=load_workbook(BytesIO(item['data']),data_only=True)
    visible=[ws for ws in book if ws.sheet_state=='visible']
    origin=unique_origin(visible,labels)
    local=table.get('header_rows')
    if local:
        origin=(table['sheet'],local[-1],1)
    if origin:
        sheet,row,first_col=origin
        ref={'source_sha256':item['sha256'],'sheet':sheet,'row':row,
             'header_cells':[get_column_letter(first_col+i)+str(row) for i in range(len(labels))]}
    else:
        ref=None
    expected=item['tables'][0]
    if origin and (origin[0],origin[1])==(expected['sheet'],expected['row']):
        roles={position-origin[2]:role for position,role in enumerate(FLAT,expected['first_col'])}
    else:
        roles={}
    lexicon,prototypes,predict,policy,_=model
    source=research_doc(item['label']['file'],origin[0] if origin else '',run_labels,table['body'])
    record=prepare(source,lexicon,prototypes)
    error=None
    if solar:
        if len(run_labels)>30:
            return {**result,'status':'NOT_RUN_COLUMN_LIMIT'}
        payload,fields=payload_for(source,MODEL_BY_SIZE['mini'],list(range(len(run_labels))),business=True)
        picks_,error=recommend(solar,payload,fields)
        picks=[{'prediction':picks_.get(str(i)),'top3':[picks_[str(i)]] if picks_.get(str(i)) else []} for i in range(len(run_labels))]
    else:
        picks=baseline_decisions(record,'rapid') if rapid else decisions(predict(record),record,policy)
    book.close()
    return {**count_recommendations(picks,roles),'source_headers':ref,'provider_has_page_coordinates':table.get('has_coordinates'),
            'input_field_count':len(run_labels),'status':error or 'MEASURED'}


def evaluate(gold_path, parsed_path, output, solar=None):
    panel=workbook_panel()
    entries=read_scores(gold_path)['documents']
    if [(d['label']['file'],d['sha256']) for d in entries] != [(d['label']['file'],d['sha256']) for d in panel]:
        raise ValueError('Document panel hash mismatch')
    parsed=json.loads(parsed_path.read_text(encoding='utf-8'))
    model=cpu_reference()
    results={}
    for item in panel[:2]:
        name=item['label']['file']
        if item['label']['template']!='bom_structure_table':
            raise ValueError('Missing independent mapping labels')
        original=local_tables(item)
        raw=[t for t in original if t['sheet']==item['tables'][0]['sheet']]
        gold=item['tables'][0]
        explicit={'headers':gold['headers'],'body':gold['body']}
        methods={'xlsx-default+rapid':score_tables(item,raw,model,rapid=True),
                 'xlsx-default+lightgbm':score_tables(item,raw,model),
                 'xlsx-verified-range+rapid':score_tables(item,[explicit],model,rapid=True),
                 'xlsx-verified-range+lightgbm':score_tables(item,[explicit],model)}
        for mode,docs in parsed['modes'].items():
            reply=next((d for d in docs if d.get('file')==name and d['status']=='MEASURED'),None)
            if reply and 'tables' in reply:
                methods[f'parse-{mode}+lightgbm']=score_tables(item,reply['tables'],model)
        if solar:
            if baseline_document(item)['category']=='BOM':
                methods['xlsx-default+solar']=score_tables(item,raw,model,solar=solar)
            for mode in ('standard','enhanced'):
                reply=document_call(solar,item['data'],'xlsx',mode,100,cache_only=True)
                if reply is not None:
                    methods[f'parse-{mode}+solar']=score_tables(item,parse_tables(reply),model,solar=solar)
        results[name]=methods
    counts=Counter()
    for methods in results.values():
        for name,value in methods.items():
            counts[name]+=value['all_three']
    write(output,{'files':results,'complete_bom_recommendations':dict(counts),
                  'important':'All-three comparison covers the independently known flat BOM roles only. No persistence or approval.'})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gold',type=Path,default=OUT/'gold.json')
    parser.add_argument('--parsed',type=Path,default=OUT/'native-panel.json')
    parser.add_argument('--output',type=Path,default=OUT/'pipelines.json')
    parser.add_argument('--approved-paid-api',action='store_true')
    parser.add_argument('--max-usd',type=Decimal,default=Decimal('4'))
    args=parser.parse_args()
    if args.approved_paid_api:
        if not args.max_usd.is_finite() or not 0<args.max_usd<=APPROVED_CAP or not load_local_key():
            parser.error('Paid research requires a local key and a cap within the approved USD 5')
        with lock_paid_cache(SHARED_CACHE):
            evaluate(args.gold,args.parsed,args.output,PaidResearch(SHARED_CACHE,args.max_usd,True))
    else:
        evaluate(args.gold,args.parsed,args.output)
