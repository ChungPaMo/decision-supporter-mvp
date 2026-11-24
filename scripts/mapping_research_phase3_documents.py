"""Compare document models and re-read candidate XLSX ranges from pinned synthetic originals."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from evaluate_mapping_research import write
from mapping_research_data import sha
from mapping_research_document import (FLAT, TYPES, baseline_document, classification_score, document_call,
                                       normalized, parse_tables, safe_call, structure_score, text,
                                       workbook_panel, workbook_pdf)
from mapping_research_document_pipeline import research_doc
from mapping_research_features import CATALOG, Lexicon, prepare
from mapping_research_hybrid import read_scores
from mapping_research_neural import passages
from mapping_research_phase3 import OUT, RECIPES, build_request, collision_guard, run_job
from mapping_research_remote import APPROVED_CAP, PaidResearch, SHARED_CACHE, load_local_key, lock_paid_cache


FIXED_OUTPUT = OUT / 'documents'
PARSE_MODES = ('standard','enhanced','auto')
EXTRACT_MODES = ('extract-standard','extract-enhanced')
BODY_STOP = {'합계','총계','소계','비고','주석','작성','결재','sum','total','subtotal','note','notes'}


def normalized_row(row):
    return tuple(normalized(text(x)) for x in row)


def sheet_hits(sheets, headers):
    signature=[normalized_row(row) for row in headers]
    if not signature or not signature[-1] or not all(signature[-1]) or len(set(signature[-1]))!=len(signature[-1]):
        return []
    width=len(signature[-1])
    if any(len(row)!=width for row in signature):
        return []
    hits=[]
    for ws in sheets:
        if ws.sheet_state!='visible':
            continue
        physical=[normalized_row(row) for row in ws.values]
        for i in range(len(signature)-1,len(physical)):
            for j in range(len(physical[i])-width+1):
                if all(physical[i-len(signature)+1+h][j:j+width]==row for h,row in enumerate(signature)):
                    hits.append((ws,i+1,j+1))
    return hits


def trace_table(sheets,table,source_sha):
    headers=table['headers']
    hits=sheet_hits(sheets,headers)
    if len(hits)!=1:
        return {'status':'HOLD_AMBIGUOUS_HEADER' if hits else 'HOLD_NO_EXACT_HEADER','matches':len(hits)}
    ws,header,left=hits[0]
    right=left+len(headers[-1])-1
    result={'sheet':ws.title,'header_row':header,'header_depth':len(headers),'first_col':left,'last_col':right,
            'source_sha256':source_sha,'header_cells':[ws.cell(header,i).coordinate for i in range(left,right+1)]}
    raw_headers=[ws.cell(header,i).value for i in range(left,right+1)]
    if any(isinstance(value,(int,float,Decimal,date)) for value in raw_headers):
        return {**result,'status':'HOLD_DATA_LIKE_HEADER'}
    expected_signature=normalized_row(headers[-1])
    body=[]
    row_ids=[]
    for rownum in range(header+1,ws.max_row+1):
        row=tuple(ws.cell(rownum,i).value for i in range(left,right+1))
        signature=normalized_row(row)
        populated=[v for v in signature if v]
        if len(populated)<max(2,(len(signature)+1)//2) or signature==expected_signature:
            break
        if any(populated[0]==p or populated[0].startswith(p+':') for p in BODY_STOP):
            break
        body.append(list(map(text,row)))
        row_ids.append({'row':rownum,'cells':[ws.cell(rownum,c).coordinate for c in range(left,right+1)]})
    # A provider fragment can suggest a header but cannot justify the full range.
    if not body or len(body)!=len(table['body']):
        return {**result,'status':'HOLD_RANGE_DISAGREEMENT','original_candidate_rows':len(body),'provider_rows':len(table['body'])}
    return {**result,'status':'LOCATED','data_start_row':header+1,'data_end_row':header+len(body),
            'headers':list(map(text,raw_headers)),'body':body,'row_ids':row_ids}


def score_traces(item,tables):
    book=load_workbook(BytesIO(item['data']),data_only=True)
    try:
        probes=[trace_table(book.worksheets,table,item['sha256']) for table in tables]
    finally:
        book.close()
    expected={(t['sheet'],t['row'],t['first_col'],t['last_col'],t['row']+len(t['body'])) for t in item['tables']}
    observed={(r['sheet'],r['header_row'],r['first_col'],r['last_col'],r['data_end_row'])
              for r in probes if r['status']=='LOCATED'}
    # Several provider fragments for one physical range are counted once.
    return {'gold_ranges':len(expected),'unique_exact_ranges':len(expected & observed),
            'wrong_ranges':len(observed-expected),'trace_states':dict(Counter(p['status'] for p in probes)),'traces':probes}


def pinned_panel():
    panel=workbook_panel(include_complex=True)
    for item in panel:
        item['pdf'],item['pages'],item['page_sheets']=workbook_pdf(item)
    return panel


def manifest(panel):
    return {'scope':'GIT_PINNED_SYNTHETIC_XLSX_AND_DERIVED_PDF_V1','documents':[
        {'file':item['label']['file'],'template':item['label']['template'],'source_sha256':item['sha256'],
         'pdf_sha256':sha256(item['pdf']).hexdigest(),'pages':item['pages'],'structure_sha256':sha(item['tables'])}
        for item in panel]}


def parse_check(item, response):
    tables=parse_tables(response)
    return {'values':structure_score(item['tables'],tables),**score_traces(item,tables)}


def layout_probe(client,panel):
    results={}
    ids=(0,1,2,3,6,7,len(panel)-2,len(panel)-1)
    for mode in PARSE_MODES:
        def probe(i):
            item=panel[i]
            scored=safe_call(lambda:document_call(client,item['data'],'xlsx',mode,100),lambda r:parse_check(item,r))
            return {'index':i,'file':item['label']['file'],**scored}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results[mode]=list(pool.map(probe,ids))
    return results


def classify_ocr_probe(client,panel):
    schema={'type':'string','oneOf':[{'const':k,'description':v} for k,v in TYPES.items()]}
    def classify(i):
        item=panel[i]
        result=safe_call(lambda:document_call(client,item['data'],'xlsx','classify',100,schema),classification_score)
        return {'index':i,'truth':item['label']['category'],'baseline':baseline_document(item),**result}

    def read_ocr(i):
        item=panel[i]
        keys={v for table in item['tables'] for row in table['headers'] for v in row if v}

        def coverage(response):
            raw=response.get('text','')
            if not raw:
                raw=' '.join(str(w.get('text','')) for page in response.get('pages',[]) for w in page.get('words',[]))
            normalized_text=normalized(raw)
            return {'header_terms':len(keys),'terms_found':sum(normalized(k) in normalized_text for k in keys),
                    'response_pages':len(response['pages']) if isinstance(response.get('pages'),list) else None}

        outcome=safe_call(lambda:document_call(client,item['pdf'],'pdf','ocr',item['pages']),coverage)
        return {'index':i,'format':'pdf','rendered_pages':item['pages'],**outcome}
    with ThreadPoolExecutor(max_workers=3) as pool:
        classified=list(pool.map(classify,(0,3,4,7,8,12)))
        ocr=list(pool.map(read_ocr,(0,3,12)))
    return {'classify_xlsx':classified,'ocr_pdf':ocr}


def bom_schema():
    descriptions=passages('bom','confusion')
    fields={name:{'type':'string','description':descriptions[name]+'. Copy supported source text. Use empty string when absent.'}
            for name in CATALOG['bom']}
    return {'type':'object','properties':{'rows':{'type':'array','items':{'type':'object','properties':fields}}}}


def extraction_rows(item, response, *, ground_flat):
    message=response['choices'][0]['message']
    payload=json.loads(message['content'])
    if not isinstance(payload,dict) or set(payload)!={'rows'} or not isinstance(payload['rows'],list):
        raise ValueError('Extraction row wrapper mismatch')
    rows=payload['rows']
    fields=set(CATALOG['bom'])
    if any(not isinstance(r,dict) or set(r)!=fields or not all(isinstance(v,str) for v in r.values()) for r in rows):
        raise ValueError('Extracted rows failed the BOM field contract')
    located=Counter()
    for call in message.get('tool_calls') or []:
        if call['function']['name']=='additional_values':
            details=call['function']['arguments']
            if isinstance(details,str):
                details=json.loads(details)

            def visit(node):
                if isinstance(node,list):
                    for v in node:
                        visit(v)
                elif isinstance(node,dict):
                    if type(node.get('page')) is int and node.get('coordinates'):
                        located['value_locations']+=1
                        located['max_output_location_page']=max(located['max_output_location_page'],node['page'])
                    for v in node.values():
                        if isinstance(v,(list,dict)):
                            visit(v)

            visit(details)
    result={'extracted_rows':len(rows),'location':dict(located)}
    if not ground_flat:
        return {**result,'unsupported_document':True,'nonempty_fields':sum(bool(v) for row in rows for v in row.values())}
    gold=item['tables'][0]
    expected=[dict(zip(FLAT,row,strict=True)) for row in gold['body']]
    key=lambda row:(row['product_id'],row['component_id'])
    lookup=defaultdict(list)
    for pos,row in enumerate(expected):
        lookup[key(row)].append(pos)
    source_positions=Counter(key(row) for row in rows)
    used=set()
    counts=Counter(expected_rows=len(expected),expected_nonempty=sum(bool(v) for row in expected for v in row.values()))
    examples=[]
    for row in rows:
        candidates=lookup.get(key(row),[])
        position=candidates[0] if len(candidates)==1 and source_positions[key(row)]==1 else None
        if position is None:
            counts['unlinked_or_extra_rows']+=1
            counts['unlinked_nonempty_fields']+=sum(bool(v) for v in row.values())
            continue
        used.add(position)
        source=expected[position]
        counts['linked_rows']+=1
        counts['missing_values']+=sum(bool(v) and not row[k] for k,v in source.items())
        counts['exact_values']+=sum(bool(v) and row[k]==v for k,v in source.items())
        counts['unsupported_extra_values']+=sum(bool(v) and not source.get(k) for k,v in row.items())
        counts['exact_rows']+={k:v for k,v in row.items() if v}=={k:v for k,v in source.items() if v}
        if row['qty_per'] and source['qty_per']:
            try:
                same_numeric=Decimal(row['qty_per'])==Decimal(source['qty_per'])
            except InvalidOperation:
                same_numeric=False
            counts['numeric_changed']+=not same_numeric
            counts['numeric_format_only']+=same_numeric and row['qty_per']!=source['qty_per']
        if len(examples)<3:
            raw_row=gold['row']+1+position
            examples.append({'sheet':gold['sheet'],'source_sha256':item['sha256'],'row':raw_row,
                             'cells':[get_column_letter(gold['first_col']+j)+str(raw_row) for j in range(len(FLAT))]})
    counts['unlinked_or_missing_source_rows']=len(expected)-len(used)
    counts['missing_values']+=sum(bool(v) for i,row in enumerate(expected) if i not in used for v in row.values())
    if len(rows)==len(expected):
        ordered_pairs=list(zip(expected,rows,strict=True))
        codes=('product_id','component_id')
        counts['positional_code_values']=sum(bool(src[field]) for src,_ in ordered_pairs for field in codes)
        counts['positional_code_differences']=sum(bool(src[field]) and src[field]!=ref[field]
                                                 for src,ref in ordered_pairs for field in codes)
    result.update(counts=counts,examples=examples,exact_row_count=len(rows)==len(expected))
    return result


def extraction_probe(client,panel,*,native):
    schema=bom_schema()
    parts=[(0,'extract-enhanced','xlsx')] if native else [
        *((i,mode,'pdf') for mode in EXTRACT_MODES for i in (0,1)),
        (12,'extract-enhanced','pdf'),(8,'extract-enhanced','pdf')]
    def extract(part):
        i,mode,fmt=part
        item=panel[i]
        data,pages=(item['data'],100) if fmt=='xlsx' else (item['pdf'],item['pages'])
        if i==12:
            # A complex BOM has no independent normalized row mapping in this corpus.
            def scorer(response):
                observed=extraction_rows(item,response,ground_flat=False)
                observed['unsupported_document']=False
                observed['gold_scope']='structure_only'
                return observed
        else:
            def scorer(response):
                return extraction_rows(item,response,ground_flat=i in (0,1))
        probe=safe_call(lambda:document_call(client,data,fmt,mode,pages,schema,flat=True),scorer)
        return {'index':i,'format':fmt,'mode':mode,'input_limit':pages,**probe}
    with ThreadPoolExecutor(max_workers=1 if native else 3) as pool:
        return list(pool.map(extract,parts))


def document_solar_probe(client,panel,policy):
    results=[]
    recipe=RECIPES[policy]
    lexicon=Lexicon(CATALOG)
    for j in (0,1):
        item=panel[j]
        for fmt in ('xlsx','pdf'):
            data,pages=(item['data'],100) if fmt=='xlsx' else (item['pdf'],item['pages'])
            mode='standard' if fmt=='xlsx' else 'enhanced'
            upstream=safe_call(lambda:document_call(client,data,fmt,mode,pages),lambda r:{'tables':parse_tables(r)})
            tables=upstream.get('tables',[])
            if fmt=='xlsx':
                report=score_traces(item,tables)
                triplets=[r for r in report['traces'] if r['status']=='LOCATED' and len(r['headers'])==len(FLAT)]
                by_range={(r['sheet'],r['header_row'],r['first_col'],r['data_end_row']):r for r in triplets}
                triplets=list(by_range.values())
            else:
                triplets=[{**t,'headers':t['headers'][-1]} for t in tables if t['headers'] and len(t['headers'][-1])==len(FLAT)
                          and all(any(c.isalpha() for c in value) for value in t['headers'][-1])]
            if len(triplets)!=1:
                results.append({'index':j,'format':fmt,'status':'HOLD_NO_UNIQUE_TABLE','correct':0,'wrong':0})
                continue
            first=triplets[0]
            doc=research_doc(item['label']['file'],first.get('sheet','Synthetic BOM'),first['headers'],first['body'])
            all_columns=list(range(len(FLAT)))
            _,key,picks,errors,_=run_job(client,(j,build_request(doc,all_columns,recipe)))
            validated,local_issues=collision_guard(picks,{},prepare(doc,lexicon,{}))
            # The order is independently known only when the source header signature agrees.
            header_matches=normalized_row(first['headers'])==normalized_row(item['tables'][0]['headers'][-1])
            correct=sum(header_matches and v==FLAT[int(k)] for k,v in validated.items())
            results.append({'index':j,'format':fmt,'status':'MEASURED','correct':correct,'wrong':len(validated)-correct,
                            'upstream_value_rows':len(first['body']),'source_range_verified':fmt=='xlsx' and header_matches,
                            'errors':dict(errors),'local_rejections':dict(local_issues),'request_sha256':key})
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('freeze','run'))
    parser.add_argument('--parts',nargs='+',choices=('layout','classify-ocr','extract-pdf','extract-xlsx','solar'),default=['layout'])
    parser.add_argument('--approved-paid-api',action='store_true')
    parser.add_argument('--max-usd',type=Decimal,default=APPROVED_CAP)
    args=parser.parse_args()
    panel=pinned_panel()
    approved=manifest(panel)
    path=FIXED_OUTPUT/'manifest.json'
    if args.action=='freeze':
        write(path,{**approved,'sha256':sha(approved)})
        print(json.dumps({'documents':len(panel),'manifest_sha256':sha(approved)}))
        return
    if read_scores(path)!=approved:
        parser.error('Current documents do not match the frozen synthetic manifest')
    if not args.approved_paid_api or not args.max_usd.is_finite() or not 0<args.max_usd<=APPROVED_CAP or not load_local_key():
        parser.error('Explicit approval, configured local key and shared maximum cost are required')
    with lock_paid_cache(SHARED_CACHE):
        client=PaidResearch(SHARED_CACHE,args.max_usd,True)
        priority=('layout','extract-pdf','solar','extract-xlsx','classify-ocr')
        for part in (part for part in priority if part in args.parts):
            if part=='layout':
                data=layout_probe(client,panel)
            elif part=='classify-ocr':
                data=classify_ocr_probe(client,panel)
            elif part.startswith('extract-'):
                data=extraction_probe(client,panel,native=part=='extract-xlsx')
            else:
                policy=read_scores(OUT/'policy.json')['selected']
                data=document_solar_probe(client,panel,policy)
            write(FIXED_OUTPUT/f'{part}.json',{'data':data,'manifest_sha256':sha(approved),'cost_or_reserve_usd':str(client.spent)})


if __name__=='__main__':
    main()
