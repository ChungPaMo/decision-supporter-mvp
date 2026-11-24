"""Paid document experiments accept only regenerated or Git-verified synthetic inputs."""
import argparse
from base64 import b64encode
from collections import Counter
from decimal import Decimal
from hashlib import sha1, sha256
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import runpy
import subprocess
from time import perf_counter

from openpyxl import load_workbook
from PIL import Image, ImageDraw, ImageFont

from evaluate_classifier_xlsx import ROOT, SAMPLES, find_tables, classify_workbook, parse_file
from evaluate_mapping_research import write
from mapping_research_data import canonical, sha
from mapping_research_neural import passages
from mapping_research_phase2 import CATALOG, DATA, synthetic_documents
from mapping_research_remote import (APPROVED_CAP, SHARED_CACHE, VAT, BudgetExceeded, PaidResearch,
                                     ProviderFailure, load_local_key, lock_paid_cache)


OUT = Path('.artifacts/mapping-research/document-intelligence')
PARSE = 'document-parse-260930'
EXTRACT = 'information-extract-261113'
CLASSIFY = 'document-classify-260904'
PRICE = {key:Decimal(value) for key,value in {
    'standard':'.01','enhanced':'.03','auto':'.03','classify':'.004',
    'extract-standard':'.04','extract-enhanced':'.06','ocr':'.0015'}.items()}
TYPES = {'BOM':'BOM or product assembly component breakdown', 'MPS':'master production schedule',
         'MRP':'material requirements or planned procurement schedule', 'RCCP':'rough-cut capacity plan',
         'CRP':'capacity requirements and work center load', 'MES':'shop floor production and quality actuals',
         'ERP':'ERP product, transaction, purchasing, inventory or partner master records',
         'OTHER':'non-manufacturing, unclassifiable or mixed document with no dominant supported type'}
FIXTURE_COMMIT = '61cf597608839b1f8754f7ccbf9266f43b9a4c44'
FLAT = ('product_id','component_id','qty_per')


def text(value):
    return '' if value is None else str(value).strip()


def workbook_panel():
    source = SAMPLES.relative_to(ROOT).as_posix()
    tracked = subprocess.check_output(['git','ls-tree','-r','-z',FIXTURE_COMMIT,'--',source], cwd=ROOT)
    pinned = {line.split(b'\t',1)[1].decode():line.split(b' ')[2].split(b'\t')[0].decode()
              for line in tracked.split(b'\0') if line}

    def verified(path):
        data = path.read_bytes()
        if path.suffix != '.xlsx':
            data = data.replace(b'\r\n',b'\n')
        git_blob = sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
        if pinned[path.relative_to(ROOT).as_posix()] != git_blob:
            raise ValueError('Synthetic fixture differs from the pinned Git blob')
        return data

    labels = json.loads(verified(SAMPLES/'labels.json'))['files']
    verified(SAMPLES/'make_samples.py')
    generator = runpy.run_path(str(SAMPLES/'make_samples.py'))['build']()
    if len(labels) != 200 or [{k:v for k,v in item.items() if k != '_write'} for item in generator] != labels:
        raise ValueError('Synthetic fixture generator and labels disagree')
    candidates = []
    for label, record in zip(labels,generator,strict=True):
        if label['split'] != 'test':
            continue
        data = verified(SAMPLES/'inbox'/label['file'])
        with_book = load_workbook(BytesIO(data))
        with_values = load_workbook(BytesIO(data),data_only=True)
        blocks = record['_write'][0]
        gold = find_tables(with_book.active,blocks)
        visible = [ws for ws in with_values if ws.sheet_state == 'visible' and any(x is not None for row in ws.values for x in row)]
        ws = with_book.active
        features = {label['category'],label['template']}
        flags = {'single_header':all(not t['grouped'] for t in gold),'grouped':any(t['grouped'] for t in gold),
                 'merged':bool(ws.merged_cells.ranges),'title':any(b['kind']=='title' for b in blocks),
                 'blank_row':any(not any(v is not None for v in row) for row in ws.values),
                 'blank_col':any(not any(c.value is not None for c in col) for col in ws.columns),
                 'many_tables':len(gold)>1,'many_sheets':len(visible)>1,
                 'total':any(b.get('total') for b in blocks),
                 'hidden_col':any(d.hidden for d in ws.column_dimensions.values()),
                 'hidden_row':any(d.hidden for d in ws.row_dimensions.values()),
                 'formula':any(c.data_type=='f' for row in ws.rows for c in row)}
        features.update(name for name, present in flags.items() if present)
        tables = []
        for index,t in enumerate(gold):
            header, left, right = t['row'],t['first_col'],t['last_col']
            values = with_values.active
            cells = [[text(values.cell(row,col).value) for col in range(left,right+1)]
                     for row in range(header+1,header+t['body_rows']+1)]
            tabs = [[text(values.cell(row,col).value) for col in range(left,right+1)]
                    for row in range(header-int(t['grouped']),header+1)]
            merges = [str(rng) for rng in ws.merged_cells.ranges if rng.min_row <= header and rng.max_row >= header-int(t['grouped'])
                      and rng.min_col <= right and rng.max_col >= left]
            formula = [c.coordinate for row in ws.iter_rows(min_row=header+1,max_row=header+t['body_rows'],min_col=left,max_col=right)
                       for c in row if c.data_type=='f']
            tables.append({**t,'index':index,'sheet':ws.title,'headers':tabs,'body':cells,'merges':merges,'formula_cells':formula,
                           'formulas_without_cache':sum(values[key].value is None for key in formula)})
        candidates.append({'label':label,'data':data,'sha256':sha256(data).hexdigest(),'tables':tables,
                           'features':features,'visible_pages':len(visible),'dimensions':[ws.max_row,ws.max_column]})
        with_book.close()
        with_values.close()
    flat = [item for item in candidates if item['label']['template']=='bom_structure_table'][:2]
    selected = flat[:]
    covered = set().union(*(row['features'] for row in selected))
    for category in TYPES:
        if category != 'BOM':
            actual = '미분류' if category=='OTHER' else category
            options = [row for row in candidates if row['label']['category']==actual]
            match = max(options,key=lambda row:(len(row['features']-covered),-row['dimensions'][0]))
            selected.append(match)
            covered |= match['features']
    for _ in range(12-len(selected)):
        match = max((row for row in candidates if row not in selected),
                    key=lambda row:(len(row['features']-covered),-row['dimensions'][0]))
        selected.append(match)
        covered |= match['features']
    return selected


def image_pages(matrices):
    normal = ImageFont.truetype('malgun.ttf',20)
    bold = ImageFont.truetype('malgunbd.ttf',20)
    pages = []
    for rows, headers, hidden_rows, hidden_columns, merged in matrices:
        columns = [i for i in range(max(map(len,rows))) if i not in hidden_columns]
        widths = {i:max(95, int(max(normal.getlength(row[i]) if i<len(row) else 0 for row in rows))+27) for i in columns}
        heights = {i:32 for i in range(len(rows)) if i not in hidden_rows}
        page = Image.new('RGB',(max(sum(widths.values())+48,660),sum(heights.values())+48),'white')
        draw = ImageDraw.Draw(page)
        y=24
        for r,row in enumerate(rows):
            if r in hidden_rows:
                continue
            x=24
            for c in columns:
                merge = next((m for m in merged if m.min_row-1<=r<m.max_row and m.min_col-1<=c<m.max_col),None)
                if merge is None or (r==merge.min_row-1 and c==merge.min_col-1):
                    w = widths[c] if merge is None else sum(widths[k] for k in columns if c<=k<merge.max_col)
                    h = heights[r] if merge is None else sum(heights[k] for k in heights if r<=k<merge.max_row)
                    value = row[c] if c < len(row) else ''
                    if value:
                        draw.rectangle((x,y,x+w,y+h),fill='#eaf2fa' if r in headers else None,outline='#9aaabb')
                        draw.text((x+9,y+2),value,fill='#202830',font=bold if r in headers else normal)
                x += widths[c]
            y += heights[r]
        pages.append(page)
    out = BytesIO()
    pages[0].save(out,format='PDF',save_all=True,append_images=pages[1:],resolution=150,
                  creationDate=None,modDate=None,title='Synthetic research worksheet')
    return out.getvalue(),len(pages)


def workbook_pdf(item):
    book = load_workbook(BytesIO(item['data']),data_only=True)
    matrices=[]
    page_sheets=[]
    for ws in book:
        rows = [[text(v) for v in row] for row in ws.values]
        if ws.sheet_state!='visible' or not any(any(row) for row in rows):
            continue
        headers = {t['row']-1-h for t in item['tables'] if t['sheet']==ws.title for h in range(len(t['headers']))}
        hidden_cols = {i-1 for d in ws.column_dimensions.values() if d.hidden for i in range(d.min,d.max+1)}
        matrices.append((rows,headers,{k-1 for k,d in ws.row_dimensions.items() if d.hidden},hidden_cols,ws.merged_cells.ranges))
        page_sheets.append(ws.title)
    book.close()
    data,pages = image_pages(matrices)
    return data,pages,page_sheets


def multipart(data,kind,options):
    boundary = 'upstage-research-'+sha256(data).hexdigest()[:30]
    if boundary.encode() in data:
        raise ValueError('Unexpected multipart boundary collision')
    prefix = f'--{boundary}\r\n'.encode()
    wire = b''.join(prefix+f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k,v in options.items())
    mime = {'xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','pdf':'application/pdf'}[kind]
    return (wire+prefix+f'Content-Disposition: form-data; name="document"; filename="synthetic.{kind}"\r\n'
            f'Content-Type: {mime}\r\n\r\n'.encode()+data+f'\r\n--{boundary}--\r\n'.encode(),
            f'multipart/form-data; boundary={boundary}')


def document_call(client, data, kind, mode, page_limit, schema=None, split=False, *, flat=False, cache_only=False):
    if mode in ('standard','enhanced','auto','ocr'):
        options = {'model':PARSE,'mode':mode,'output_formats':'["html","markdown","text"]',
                   'coordinates':'true','chart_recognition':'false','ocr':'force' if kind=='pdf' else 'auto'}
        if mode=='ocr':
            options={'model':'ocr'}
        wire,mime = multipart(data,kind,options)
        endpoint = '/document-digitization'
    else:
        classify = mode=='classify'
        options = {'model':CLASSIFY if classify else EXTRACT,'split':split,'response_format':{
            'type':'json_schema','json_schema':{'name':'manufacturing_document','schema':schema}}}
        if not classify:
            options.update(mode=mode.removeprefix('extract-'),location=True,
                           location_granularity='element' if flat else 'word')
        message = {'role':'user','content':[{'type':'image_url','image_url':{'url':
                    'data:application/octet-stream;base64,'+b64encode(data).decode()}}]}
        wire,mime = canonical({**options,'messages':[message]}),'application/json'
        endpoint = '/document-classification' if classify else '/information-extraction'

    def measured(body):
        usage = body.get('usage') or {}
        count = usage.get('pages',page_limit if kind=='pdf' else None)
        if type(count) is not int or count < 0 or count > page_limit:
            return None
        if mode=='auto':
            low,high=usage.get('standard',[]),usage.get('enhanced',[])
            if (isinstance(low,list) and isinstance(high,list) and low+high
                    and all(type(page) is int for page in low+high) and sorted(low+high)==list(range(1,count+1))):
                return VAT*(PRICE['standard']*len(low)+PRICE['enhanced']*len(high))
        return VAT*PRICE[mode]*count

    identity = {**options,'mode':mode,'format':kind,'source_sha256':sha256(data).hexdigest(),'max_pages':page_limit}
    if cache_only:
        return client.cached_response(endpoint,identity)
    return client.request(endpoint,identity,wire,mime,VAT*PRICE[mode]*page_limit,measured)


class HTMLTables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables=[]
        self.table=None
        self.row=None
        self.cell=None
        self.depth=0

    def handle_starttag(self,tag,attrs):
        if tag=='table':
            self.depth+=1
            if self.depth==1:
                self.table=[]
        if self.depth!=1:
            return
        if tag=='tr':
            self.row=[]
        if tag in ('td','th') and self.row is not None:
            self.cell=[tag,'',dict(attrs)]
        if tag=='br' and self.cell is not None:
            self.cell[1]+=' '

    def handle_data(self,data):
        if self.depth==1 and self.cell is not None:
            self.cell[1]+=data

    def handle_endtag(self,tag):
        if self.depth==1 and tag in ('td','th') and self.cell is not None:
            self.row.append(self.cell)
            self.cell=None
        if self.depth==1 and tag=='tr' and self.row is not None:
            self.table.append(self.row)
            self.row=None
        if tag=='table' and self.depth:
            if self.depth==1 and self.table:
                self.tables.append(self.table)
            self.depth-=1


def expanded(rows):
    cells={}
    spans=0
    header_depth=0
    for ri,row in enumerate(rows):
        if ri==header_depth and row and all(tag=='th' for tag,_,_ in row):
            header_depth+=1
        col=0
        for _,value,attrs in row:
            while (ri,col) in cells:
                col+=1
            def span(key):
                raw=attrs.get(key,'1')
                return min(100,max(1,int(raw))) if raw and raw.isdecimal() else 1
            height,width=span('rowspan'),span('colspan')
            spans+=height*width>1
            for y in range(ri,ri+height):
                for x in range(col,col+width):
                    cells[y,x]=text(value) if (y,x)==(ri,col) else ''
            col+=width
    if not cells:
        return [],[],0
    columns=max(c for _,c in cells)+1
    grid=[[cells.get((r,c),'') for c in range(columns)] for r in range(max(r for r,_ in cells)+1)]
    k=max(1,header_depth)
    return grid[:k],grid[k:],spans


def parse_tables(response):
    tables=[]
    elements=response.get('elements') or []
    for element in elements:
        content=element.get('content') or {}
        if element.get('category')=='table':
            parser=HTMLTables()
            parser.feed(content.get('html') or '')
            for grid in parser.tables:
                headers,body,merges=expanded(grid)
                tables.append({'headers':headers,'body':body,'merges':merges,'page':element.get('page'),
                               'has_coordinates':bool(element.get('coordinates'))})
    if not elements:
        parser=HTMLTables()
        parser.feed((response.get('content') or {}).get('html',''))
        for grid in parser.tables:
            headers,body,merges=expanded(grid)
            tables.append({'headers':headers,'body':body,'merges':merges,'page':None,'has_coordinates':False})
    return tables


def normalized(value):
    return ' '.join(value.casefold().split())


def matching(gold, predicted):
    def names(table):
        return {normalized(cell) for row in table['headers'] for cell in row if cell}
    matches=[]
    used=set()
    for src in gold:
        actual=names(src)
        ranking=[(len(actual & names(dst))/max(len(actual | names(dst)),1), i) for i,dst in enumerate(predicted) if i not in used]
        overlap,index=max(ranking,default=(0,-1))
        if overlap>=.5:
            matches.append((src,predicted[index]))
            used.add(index)
    return matches


def structure_score(gold,predicted):
    stat=Counter(gold_tables=len(gold),predicted_tables=len(predicted),exact_table_count=(len(gold)==len(predicted)))
    stat['gold_value_cells']=sum(bool(v) for t in gold for row in t['body'] for v in row)
    stat['gold_uncached_formulas']=sum(t.get('formulas_without_cache',0) for t in gold)
    aligned=matching(gold,predicted)
    stat['values_in_unmatched_tables']=stat['gold_value_cells']-sum(bool(v) for source,_ in aligned for row in source['body'] for v in row)
    for source,found in aligned:
        stat['matched_tables']+=1
        stat['exact_header']+=source['headers'] and [[normalized(v) for v in row] for row in source['headers']]==[[normalized(v) for v in row] for row in found['headers']]
        stat['header_depth_exact']+=len(source['headers'])==len(found['headers'])
        stat['header_merge_count_exact']+=len(source['merges'])==found['merges']
        stat['row_count_exact']+=len(source['body'])==len(found['body'])
        stat['column_count_exact']+=len(source['headers'][-1])==len(found['headers'][-1])
        stat['unexpected_body_rows']+=max(0,len(found['body'])-len(source['body']))
        stat['missing_body_rows']+=max(0,len(source['body'])-len(found['body']))
        for r,row in enumerate(source['body']):
            for c,value in enumerate(row):
                if not value:
                    continue
                answer=found['body'][r][c] if r<len(found['body']) and c<len(found['body'][r]) else ''
                stat['value_exact']+=value==answer
                stat['unrecovered_value_cells']+=not bool(answer)
                try:
                    number=Decimal(value)
                except ArithmeticError:
                    pass
                else:
                    if number.is_finite():
                        stat['numeric_cells_in_matched_tables']+=1
                        stat['numeric_display_exact']+=value==answer
                        try:
                            stat['numeric_value_exact']+=number==Decimal(answer)
                        except ArithmeticError:
                            pass
                if len(value)>=10 and value[4:5]=='-' and value[7:8]=='-':
                    stat['date_cells_in_matched_tables']+=1
                    stat['date_display_exact']+=value==answer
                if value.casefold() in {'ea','kg','g','box','m','pcs','ton','m2'}:
                    stat['unit_cells_in_matched_tables']+=1
                    stat['unit_display_exact']+=value==answer
    return dict(stat)


def local_tables(item):
    parsed=parse_file(item['label']['file'],item['data'])
    return [{'headers':([[text(h.group) for h in s.header]] if len(s.header_rows)>1 else [])
                       + [[text(h.name) for h in s.header]],
             'body':[[text(c.value) for c in row.cells] for row in s.rows], 'merges':0,'sheet':s.name,
             'header_rows':s.header_rows} for s in parsed.sheets if s.header_rows and s.header]


def baseline_document(item):
    book=load_workbook(BytesIO(item['data']),data_only=True)
    guess=classify_workbook([(ws.title, [[text(v) for v in row] for row in ws.iter_rows(min_row=1,max_row=60,max_col=60,values_only=True)])
                              for ws in book.worksheets[:20]])
    book.close()
    return {'category':guess.category,'review':guess.needs_review}


def extraction_fixtures():
    docs,_=synthetic_documents(DATA,'calibration')
    result={}
    for entity in CATALOG:
        options=[doc for doc in docs if doc['entity']==entity and doc['document_type']==entity]
        doc=max(options,key=lambda doc:sum(col['expected'] is not None for col in doc['columns']))
        inputs=[col for col in doc['columns']]
        rows=[[col['header'] for col in inputs]] + [list(row) for row in zip(*[col['values'][:6] for col in inputs],strict=True)]
        data,pages=image_pages([([[doc['title']],*rows],{1},set(),set(),[])])
        descriptions=passages(entity,'confusion')
        keys=[field for field,rule in CATALOG[entity].items() if rule['kind'].endswith('code')]
        values=[field for field in CATALOG[entity] if field not in keys]
        parts={name:{'type':'object','additionalProperties':False,'properties':{
               field:{'type':'string','description':descriptions[field]+' Copy the value as displayed. Empty string when absent.'}
               for field in fields},'required':fields} for name,fields in [('keys',keys),('values',values)] if fields}
        schema={'type':'object','additionalProperties':False,'properties':{'rows':{'type':'array','items':{
                'type':'object','additionalProperties':False,'properties':parts,'required':list(parts)}}},'required':['rows']}
        expected=[{col['expected']:value for col,value in zip(inputs,row,strict=True) if col['expected']} for row in rows[1:]]
        result[entity]={'bytes':data,'pages':pages,'id':doc['id'],'schema':schema,'answers':expected,'source_rows':rows}
    return result


def extraction_score(response,fixture):
    message=response['choices'][0]['message']
    parsed=json.loads(message['content'])
    if not isinstance(parsed,dict) or set(parsed)!={'rows'} or not isinstance(parsed['rows'],list):
        raise ValueError('Extraction wrapper mismatch')
    schema=fixture['schema']['properties']['rows']['items']['properties']
    actual=[]
    for row in parsed['rows']:
        if not isinstance(row,dict) or set(row)!=set(schema):
            raise ValueError('Nested object mismatch')
        flat={}
        if fixture.get('flat'):
            if not all(isinstance(v,str) for v in row.values()):
                raise ValueError('Invalid field values')
            flat.update(row)
        else:
            for key,fields in row.items():
                if not isinstance(fields,dict) or set(fields)!=set(schema[key]['properties']) or not all(isinstance(v,str) for v in fields.values()):
                    raise ValueError('Missing or invalid extraction fields')
                flat.update(fields)
        actual.append(flat)
    expected=fixture['answers']
    stats=Counter(source_rows=len(expected),extracted_rows=len(actual),missing_rows=max(len(expected)-len(actual),0),
                  extra_rows=max(len(actual)-len(expected),0), expected_cells=sum(bool(v) for r in expected for v in r.values()))
    for index,right in enumerate(actual):
        left=expected[index] if index<len(expected) else {}
        stats['exact_values']+=sum(bool(v) and v==right.get(k) for k,v in left.items())
        stats['wrong_values']+=sum(bool(v) and bool(left.get(k)) and v!=left[k] for k,v in right.items())
        stats['filled_absent_field']+=sum(bool(v) and not left.get(k) for k,v in right.items())
        stats['missing_expected_values']+=sum(bool(v) and not right.get(k) for k,v in left.items())
        stats['exact_rows']+=bool(left) and {k:v for k,v in left.items() if v}=={k:v for k,v in right.items() if v}
    stats['missing_expected_values']+=sum(bool(v) for row in expected[len(actual):] for v in row.values())
    return {'counts':dict(stats), 'location_tool_names':[call['function']['name'] for call in message.get('tool_calls') or []]}


def flat_schema(fixture):
    elements=fixture['schema']['properties']['rows']['items']['properties']
    fields={field:rule for item in elements.values() for field,rule in item['properties'].items()}
    schema={'type':'object','properties':{'rows':{'type':'array','items':{'type':'object','properties':fields}}}}
    return {**fixture,'schema':schema,'flat':True}


def safe_call(call,score):
    tick=perf_counter()
    try:
        response=call()
    except BudgetExceeded:
        return {'status':'NOT_RUN_BUDGET'}
    except ProviderFailure as exc:
        return {'status':'FAILED_PROVIDER','http_status':exc.status,'error_category':exc.category}
    try:
        result=score(response)
    except (KeyError,ValueError,IndexError,TypeError,AttributeError):
        return {'status':'FAILED_CONTRACT','usage':response.get('usage')}
    return {'status':'MEASURED','model':response.get('model'),'usage':response.get('usage'),
            'read_or_request_ms':(perf_counter()-tick)*1000,**result}


def classification_score(response):
    value=response['choices'][0]['message']['content']
    if not isinstance(value,str) or value.strip().strip('"') not in TYPES:
        raise ValueError('Unrecognized class')
    return {'category':value.strip().strip('"')}


def document_experiment(args,client,panel,extraction):
    category_schema={'type':'string','oneOf':[{'const':k,'description':v} for k,v in TYPES.items()]}
    results={}
    if args.category:
        category='미분류' if args.category=='OTHER' else args.category
        panel=[item for item in panel if item['label']['category']==category]
    for mode in args.modes:
        observations=[]
        if mode.startswith('extract-'):
            for entity,fixture in list(extraction.items())[:args.limit]:
                if args.flat_extraction:
                    fixture=flat_schema(fixture)
                scored=safe_call(lambda:document_call(client,fixture['bytes'],'pdf',mode,fixture['pages'],fixture['schema'],
                                                     flat=args.flat_extraction),
                                 lambda response:extraction_score(response,fixture))
                observations.append({'entity':entity,**scored})
        else:
            for item in panel[:args.limit]:
                kind='xlsx' if args.native else 'pdf'
                data,pages=(item['data'],100) if args.native else (item['pdf'],item['pages'])

                def parsed_struct(response):
                    tables=parse_tables(response)
                    return {'counts':structure_score(item['tables'],tables),'tables':tables,
                            'title_elements':sum(e.get('category')=='heading1' for e in response.get('elements',[])),
                            'markdown_present':bool((response.get('content') or {}).get('markdown'))}

                scorer=classification_score if mode=='classify' else parsed_struct
                scored=safe_call(lambda:document_call(client,data,kind,mode,pages,category_schema),scorer)
                observations.append({'file':item['label']['file'],'truth':item['label']['category'],'reserved_pages':pages,**scored})
                if scored.get('http_status') in (401,403):
                    break
        results[mode]=observations
        write(args.output,{'kind':'xlsx' if args.native else 'pdf','modes':results,'shared_cost_usd':str(client.spent)})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run'))
    parser.add_argument('--modes',nargs='+',choices=list(PRICE),default=['standard'])
    parser.add_argument('--native',action='store_true')
    parser.add_argument('--flat-extraction',action='store_true')
    parser.add_argument('--limit',type=int,choices=range(1,13),default=12)
    parser.add_argument('--category',choices=tuple(TYPES))
    parser.add_argument('--output',type=Path,default=OUT/'results.json')
    parser.add_argument('--approved-paid-api',action='store_true')
    parser.add_argument('--max-usd',type=Decimal,default=Decimal(4))
    args=parser.parse_args()
    panel=workbook_panel()
    for item in panel:
        item['pdf'],item['pages'],item['page_sheets']=workbook_pdf(item)
    extraction=extraction_fixtures()
    def frozen_baseline(item):
        counts=structure_score(item['tables'],local_tables(item))
        # These two diagnostics were added after the panel was frozen.
        return {k:v for k,v in counts.items() if k not in ('numeric_value_exact','values_in_unmatched_tables')}

    gold={'documents':[{**{k:v for k,v in item.items() if k not in {'data','pdf','features'}},'features':sorted(item['features']),
                        'pdf_sha256':sha256(item['pdf']).hexdigest(),'baseline':baseline_document(item),
                        'base_structure':frozen_baseline(item)} for item in panel],
          'extraction':{key:{**{k:v for k,v in item.items() if k!='bytes'},'pdf_sha256':sha256(item['bytes']).hexdigest()}
                        for key,item in extraction.items()}}
    path=OUT/'gold.json'
    if args.action=='prepare':
        write(path,{**gold,'sha256':sha(gold)})
        category='미분류' if args.category=='OTHER' else args.category
        selected=[item for item in panel if category is None or item['label']['category']==category][:args.limit]
        pages=sum(item['pages'] for item in selected)
        reserved=sum(PRICE[mode]*(sum(r['pages'] for r in list(extraction.values())[:args.limit]) if mode.startswith('extract-')
                     else len(selected)*100 if args.native else pages) for mode in args.modes)*VAT
        print(json.dumps({'panel':len(panel),'pdf_pages':pages,'gold_sha256':sha(gold),'planned_with_vat':str(reserved)}))
        return
    if json.loads(path.read_text(encoding='utf-8')) != {**gold,'sha256':sha(gold)}:
        raise ValueError('Panel sources, rendering or frozen gold differ')
    if not args.approved_paid_api or not args.max_usd.is_finite() or not 0<args.max_usd<=APPROVED_CAP or not load_local_key():
        parser.error('Paid research requires authorization, shared cap within USD 5 and configured local key')
    with lock_paid_cache(SHARED_CACHE):
        document_experiment(args,PaidResearch(SHARED_CACHE,args.max_usd,args.approved_paid_api),panel,extraction)


if __name__=='__main__':
    main()
