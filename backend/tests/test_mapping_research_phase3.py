from decimal import Decimal
import json
from pathlib import Path
import random
import sys

import numpy as np
import pytest


SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0,str(SCRIPTS))

from mapping_research_data import make_document
from mapping_research_phase3 import PREVIEW, RECIPES, build_request, collision_guard, decode_response
from mapping_research_remote import APPROVED_CAP, expected_cost


def chat(raw, finish='stop'):
    return {'choices':[{'finish_reason':finish,'message':{'content':raw}}]}


def test_partial_mapping_rejects_every_duplicate_id_and_keeps_only_independent_valid_columns():
    allowed={'0':{'a','b'},'1':{'a','b'},'2':{'a','b'},'3':{'a','b'}}
    vocab={'a':'a','b':'b','HOLD':None}
    raw=json.dumps({'mapping':[{'id':'0','field':'b'},{'id':'0','field':'a'},
                               {'id':'1','field':'a'},{'id':'2','field':'unsupported'},
                               {'id':'9','field':'a'}]})
    rows,issues=decode_response(chat(raw),'/chat/completions',allowed,vocab,False)
    assert rows=={'1':'a'}
    assert dict(issues)=={'DUPLICATE_ID':2,'MISSING_ID':1,'INVALID_FIELD':1,'EXTRA_ID':1}
    assert decode_response(chat(raw,'length'),'/chat/completions',allowed,vocab,False)==({}, {'OUTPUT_LIMIT':1})
    assert decode_response(chat('{"0":"a","0":"b"}'),'/chat/completions',allowed,vocab,True)==({}, {'DUPLICATE_JSON_KEY':1})


def test_cross_group_duplicate_targets_and_locked_fields_do_not_survive():
    profile={'allowed':np.asarray([[True,True,True],[True,False,True],[True,True,True],[True,True,True]]),
             'fields':['a','b','c']}
    safe,issues=collision_guard({'0':'a','1':'b','2':'a','3':'c'},{'4':'c'},profile)
    assert safe=={'4':'c'}
    assert dict(issues)=={'DUPLICATE_TARGET':3,'LOCAL_COMPATIBILITY':1}


def test_preview_request_only_contains_reviewable_synthetic_values():
    doc=make_document('calibration','bom',2,random.Random(7))
    endpoint,payload,allowed,vocab,keyed=build_request(doc,[0,1],RECIPES['preview-business'])
    assert endpoint=='/responses' and payload['model']==PREVIEW and payload['store'] is False
    assert payload['text']['format']['strict'] is True
    user_context=json.loads(payload['input'])
    assert set(user_context)=={'concepts','columns','title','aligned_sample_rows','column_order','headers_in_sample_order'}
    assert all(set(row)=={'id','input'} for row in user_context['columns'])
    assert 'expected' not in user_context and 'document_type' not in user_context
    assert expected_cost(payload,(Decimal('0'),Decimal('1')))==Decimal(payload['max_output_tokens'])/Decimal('1000000')
    assert APPROVED_CAP==Decimal(10)


def test_keyed_schema_can_restrict_each_column_independently():
    doc=make_document('calibration','bom',2,random.Random(7))
    endpoint,payload,allowed,vocab,keyed=build_request(doc,[0,1],RECIPES['embed-solar'],
                                                     candidates={'0':['product_id'],'1':['component_id']})
    assert keyed and allowed=={'0':{'product_id'},'1':{'component_id'}}
    assert set(payload['response_format']['json_schema']['schema']['properties']['1']['enum'])=={'component_id','HOLD'}
    result,issues=decode_response(chat('{"0":"component_id","1":"HOLD"}'),endpoint,allowed,vocab,keyed)
    assert result=={'1':None} and issues=={'INVALID_FIELD':1}


def test_trace_uses_original_cells_and_holds_fragments_and_duplicate_sheet_heads():
    pytest.importorskip('PIL')
    from openpyxl import Workbook
    from mapping_research_phase3_documents import trace_table

    book=Workbook()
    ws=book.active
    ws.append(['Meta'])
    ws.append([None,'Code','Qty'])
    ws.append([None,'001',12])
    ws.append([None,'002',19])
    ws.append([None,'Total',31])
    source={'headers':[['Code','Qty']],'body':[['1','12.00'],['2','190']]}
    located=trace_table(book.worksheets,source,'source-sha')
    assert located['status']=='LOCATED'
    assert located['body']==[['001','12'],['002','19']]
    assert located['row_ids'][1]=={'row':4,'cells':['B4','C4']}
    assert located['source_sha256']=='source-sha' and located['data_end_row']==4
    assert trace_table(book.worksheets,{**source,'body':source['body'][:1]},'sha')['status']=='HOLD_RANGE_DISAGREEMENT'
    fragment={'headers':[['001','12']],'body':[['002','19'],['Total','31']]}
    assert trace_table(book.worksheets,fragment,'sha')['status']=='HOLD_DATA_LIKE_HEADER'
    book.copy_worksheet(ws)
    assert trace_table(book.worksheets,source,'sha')['status']=='HOLD_AMBIGUOUS_HEADER'
