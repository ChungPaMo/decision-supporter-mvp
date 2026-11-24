from decimal import Decimal
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError

import pytest


SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0,str(SCRIPTS))

from mapping_research_confirmatory import create_documents, draft, locked_panel
from mapping_research_data import make_document
from mapping_research_phase2 import payload_for
from mapping_research_remote import (BudgetExceeded, PaidResearch, ProviderFailure, load_local_key,
                                     lock_paid_cache)


def test_local_key_parser_only_loads_one_assignment(monkeypatch,tmp_path):
    monkeypatch.setenv('UPSTAGE_API_KEY','test-local-fixture')
    path=tmp_path/'.env.upstage.local'
    path.write_text('# comment\nOTHER=harmless\nUPSTAGE_API_KEY="tester-fixture"\n',encoding='utf-8')
    assert load_local_key(tmp_path) is True
    assert os.environ['UPSTAGE_API_KEY']=='tester-fixture'
    with path.open('a',encoding='utf-8') as stream:
        stream.write('UPSTAGE_API_KEY=duplicate\n')
    assert load_local_key(tmp_path) is False


def test_unified_ledger_persists_cached_cost_across_endpoints(monkeypatch,tmp_path):
    monkeypatch.setenv('UPSTAGE_API_KEY','test-local-fixture')
    with lock_paid_cache(tmp_path):
        with pytest.raises(FileExistsError), lock_paid_cache(tmp_path):
            pytest.fail('A second process must not open an active ledger')
        client=PaidResearch(tmp_path,Decimal('1'),True)
        monkeypatch.setattr(client.opener,'open',lambda *a,**k:BytesIO(b'{"usage":{"pages":3}}'))
        request_args=('/document-digitization',{'model':'document-parse-test','format':'xlsx'}, b'body','test',
                      Decimal('.75'),lambda body:Decimal('.1')*body['usage']['pages'])
        assert client.request(*request_args)['usage']['pages']==3
    assert PaidResearch(tmp_path,Decimal('1'),True).spent==Decimal('.3')
    with lock_paid_cache(tmp_path):
        next_client=PaidResearch(tmp_path,Decimal('1'),True)
        monkeypatch.setattr(next_client.opener,'open',lambda *a,**k:pytest.fail('Cache must not call the provider'))
        assert next_client.request(*request_args)['usage']['pages']==3
        with pytest.raises(BudgetExceeded):
            next_client.request('/embeddings',{'model':'synthetic-embedding'},b'{}','application/json',Decimal('.71'),lambda _:None)
    rows=[json.loads(line) for line in (tmp_path/'billing.jsonl').read_text('utf-8').splitlines()]
    assert [row['state'] for row in rows]==['RESERVED','RECEIVED']


def test_failed_paid_call_reserves_cost_and_does_not_retry(monkeypatch,tmp_path):
    monkeypatch.setenv('UPSTAGE_API_KEY','test-local-fixture')
    with lock_paid_cache(tmp_path):
        client=PaidResearch(tmp_path,Decimal('1'),True)
        attempts=[]

        def reject(*args,**kwargs):
            attempts.append(1)
            raise HTTPError(None,400,'Bad Request',None,BytesIO(b'{"error":{"message":"invalid schema"}}'))

        monkeypatch.setattr(client.opener,'open',reject)
        params=('/information-extraction',{'model':'synthetic-extract'},b'{}','application/json',Decimal('.8'),lambda _:None)
        with pytest.raises(ProviderFailure) as failure:
            client.request(*params)
        assert failure.value.category=='SCHEMA'
        with pytest.raises(ProviderFailure):
            client.request(*params)
        assert len(attempts)==1
        assert client.spent==Decimal('.8')


def test_solar_rows_and_candidate_doc_do_not_expose_labels():
    import random

    doc=make_document('calibration','bom',3,random.Random(77))
    payload,expected=payload_for(doc,'solar-mini4-260922',[0,2],business=True,permitted=['bom_id'])
    body=json.loads(payload['messages'][1]['content'])
    assert list(expected)==['0','2']
    assert set(body['concepts'])=={'bom_id','HOLD'}
    assert 'aligned_sample_rows' in body
    assert all(set(item)=={'id','input'} for item in body['columns'])
    assert not {'expected','scenario','document_type','entity','family'} & set(body)


def test_independent_split_is_reproducible_and_local_only(tmp_path):
    first=draft(tmp_path)
    docs,digest=locked_panel(tmp_path)
    assert first==digest and docs==create_documents()
    assert len({d['family'] for d in docs})==25
    assert any(c['scenario']=='wrong_route' for d in docs for c in d['columns'])


def test_html_spans_and_extract_contract_are_separate():
    pytest.importorskip('PIL')
    from mapping_research_document import expanded, extraction_score, flat_schema, HTMLTables, structure_score

    parser=HTMLTables()
    parser.feed('<table><tr><th colspan="2">Key</th></tr><tr><th>Code</th><th>Qty</th></tr>'
                '<tr><td>001</td><td>1.30</td></tr></table>')
    header,body,merges=expanded(parser.tables[0])
    assert header==[['Key',''],['Code','Qty']] and merges==1
    found={'headers':header,'body':body,'merges':1}
    gold={'headers':header,'body':[['001','1.3']],'merges':['A1:B1']}
    result=structure_score([gold],[found])
    assert result['value_exact']==1 and result['numeric_display_exact']==1 and result['numeric_value_exact']==2
    fixture={'answers':[{'product_id':'001'}],'schema':{'properties':{'rows':{'items':{'properties':{
        'keys':{'properties':{'product_id':{'type':'string'}}}}}}}}}
    received={'choices':[{'message':{'content':'{"rows":[{"product_id":"001"},{"product_id":"002"}]}'}}]}
    counts=extraction_score(received,flat_schema(fixture))['counts']
    assert counts['exact_rows']==1 and counts['extra_rows']==1


def test_unique_xlsx_origin_refuses_repeated_signature():
    pytest.importorskip('PIL')
    from openpyxl import Workbook
    from mapping_research_document_pipeline import unique_origin

    ws=Workbook().active
    ws.append(['title'])
    ws.append([None,'code','qty'])
    assert unique_origin([ws],['code','qty'])==(ws.title,2,2)
    ws.append([None,'code','qty'])
    assert unique_origin([ws],['code','qty']) is None
