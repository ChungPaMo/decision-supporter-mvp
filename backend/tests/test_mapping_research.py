"""Offline research guards. No optional model/runtime dependencies required."""
import copy
from decimal import Decimal
from pathlib import Path
import sys

import numpy as np
import pytest


SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
try:
    from evaluate_mapping_research import calibrate, decisions, metrics
    from mapping_research_classical import MappingMemory, MemoryKey
    from mapping_research_data import audit, build, load_frozen, sha
    from mapping_research_features import abstain, allowed_shape, inventory_votes, stats
    from mapping_research_neural import cached_vectors
    from mapping_research_remote import FIXED_SPLITS, PaidResearch, approved_bundle, chat_request, parse_mapping, plan_remote
finally:
    sys.path.remove(str(SCRIPTS))


@pytest.fixture(scope='module')
def frozen(tmp_path_factory):
    directory = tmp_path_factory.mktemp('mapping-splits')
    manifest = build(directory,write_csv=True)
    return directory, manifest


def test_fixed_synthetic_data_reaches_split_targets_and_rejects_tampering(frozen):
    directory, manifest = frozen
    assert manifest['splits']['train']['columns'] >= 5000
    assert manifest['splits']['final']['documents'] >= 100
    for split, minimum in [('calibration',300),('final',500)]:
        assert manifest['splits'][split]['columns'] >= minimum
        docs, digest = load_frozen(directory,split)
        assert digest == FIXED_SPLITS[split] and docs
    path = directory / 'final.json'
    previous = path.read_bytes()
    try:
        path.write_bytes(previous.replace(b'"direct"',b'"tampered"',1))
        with pytest.raises(ValueError, match='digest mismatch'):
            load_frozen(directory,'final')
    finally:
        path.write_bytes(previous)
    csv = directory / 'csv' / 'final' / (docs[0]['id'] + '.csv')
    original = csv.read_bytes()
    try:
        csv.write_bytes(original + b'changed')
        with pytest.raises(ValueError,match='CSV digest mismatch'):
            load_frozen(directory,'final')
    finally:
        csv.write_bytes(original)


def test_split_audit_does_not_allow_a_relabelled_duplicate(frozen):
    directory, manifest = frozen
    first = load_frozen(directory,'train')[0][0]
    copy_ = {**first,'family':'separate-id','id':'new-name'}
    with pytest.raises(ValueError, match='Cross-split'):
        audit({split:{'scope':manifest['scope'],'split':split,'documents':[item]} for split,item in (
            ('train',first),('final',copy_))})


def test_mask_detects_type_conflict_and_relationship_is_only_evidence():
    assert not allowed_shape('number', stats(['$1,024','₩40']))
    assert allowed_shape('date', stats(['2027-01-10','2027-12-11']))
    columns = [{'values':['12']*10}, {'values':['4']*10}, {'values':['8']*10}]
    assert inventory_votes(columns)[0,0] == 1
    noisy = copy.deepcopy(columns)
    noisy[2]['values'] = ['90']*10
    assert not inventory_votes(noisy).any()
    assert not inventory_votes([{'values':['12']},{'values':['4']},{'values':['8']}]).any()


def test_assignment_keeps_one_to_one_and_individual_hold_dummies():
    scores = np.asarray([[.90,.20],[.89,.88],[.30,.12],[.99,.98]])
    allowed = np.asarray([[1,1],[1,1],[1,1],[0,0]],dtype=bool)
    assert abstain(scores,allowed,.70,0,'independent')[0] == [0,0,None,None]
    assert abstain(scores,allowed,.70,0,'greedy')[0] == [0,None,None,None]
    assert abstain(scores,allowed,.70,0,'hungarian')[0] == [0,1,None,None]
    with pytest.raises(ValueError,match='finite'):
        abstain(scores * np.nan,allowed,.7,0)


def test_threshold_counts_real_holds_and_does_not_pick_empty_coverage():
    scores = [np.array([[.9,.31],[.21,.2]])]
    record = {'fields':('product_id','product_name'),'allowed':np.ones((2,2),dtype=bool)}
    policy = calibrate(scores,[record],[np.array([[1,0],[0,0]],dtype=bool)])
    predicted = decisions(scores[0],record,policy)
    doc = {'id':'demo','family':'test','entity':'product','columns':[
        {'header':'key','expected':'product_id','scenario':'direct'}, {'header':'misc','expected':None,'scenario':'unknown'}]}
    measured = metrics([doc],[predicted])
    assert measured['correct'] == measured['negative_hold'] == 1
    assert measured['wrong'] == 0 and measured['precision'] == 1


def test_memory_scope_and_revocation_are_independent():
    memory = MappingMemory()
    key = MemoryKey('SYNTH-A','product','v1',('saleitemreference','displaylabel'))
    memory.approve(key,['product_id','product_name'])
    changed = MemoryKey('SYNTH-A','product','v1',('saleitemreferencee','displaylabel'))
    assert memory.lookup(changed) is None and memory.lookup(changed,True) == ('product_id','product_name')
    assert memory.lookup(MemoryKey('SYNTH-B','product','v1',key.headers),True) is None
    assert memory.lookup(MemoryKey('SYNTH-A','product','v2',key.headers),True) is None
    with pytest.raises(ValueError):
        memory.approve(key,['unknown','product_name'])
    memory.withdraw(key)
    assert memory.lookup(changed,True) is None


def test_network_export_uses_pinned_synthetic_inputs_without_answers(frozen):
    directory, _ = frozen
    bundle = approved_bundle(directory,'calibration','table')
    assert bundle['sha256'] == sha({k:v for k,v in bundle.items() if k != 'sha256'})
    assert all(set(item) == {'id','input'} for doc in bundle['requests'] for item in doc['columns'])
    assert all(not ({'expected','scenario','document_type','csv_sha256'} & item.keys()) for item in bundle['requests'])
    request, allowed = chat_request(bundle,bundle['requests'][0],'solar-mini4-260922')
    assert request['response_format']['type'] == 'json_schema'
    assert parse_mapping({'mapping':[{'id':key,'field':'HOLD'} for key in allowed]},allowed) == {key:None for key in allowed}
    assert plan_remote(bundle,'solar-mini4-260922')['status'] == 'NOT_RUN'
    with pytest.raises(ValueError,match='split'):
        approved_bundle(directory,'final','column',{'data_sha256':'fake'})


@pytest.mark.parametrize('mapping', [
    [{'id':'0','field':'invalid'}], [{'id':'wrong','field':'HOLD'}],
    [{'id':'0','field':'product_id'},{'id':'1','field':'product_id'}],
    [{'id':'0','field':'HOLD'},{'id':'0','field':'HOLD'}],
])
def test_remote_output_cannot_force_unsupported_incomplete_or_duplicate_mapping(mapping):
    with pytest.raises(ValueError):
        parse_mapping({'mapping':mapping},{'0':{'product_id'},'1':{'product_id'}})


def test_cost_gate_does_not_read_key_or_send_without_approval(monkeypatch, tmp_path):
    monkeypatch.delenv('UPSTAGE_API_KEY',raising=False)
    with pytest.raises(ValueError,match='Explicit paid'):
        PaidResearch(tmp_path,Decimal('1'),False)
    monkeypatch.setenv('UPSTAGE_API_KEY','SYNTHETIC-TEST')
    client = PaidResearch(tmp_path,Decimal('.00000001'),True)
    monkeypatch.setattr(client.opener,'open',lambda *args,**kwargs:pytest.fail('No budget means no network'))
    with pytest.raises(ValueError,match='budget'):
        client.call('/embeddings',{'model':'solar-embedding-2-query','input':['SYNTHETIC']},(Decimal('1'),Decimal(0)))


def test_vector_cache_refreshes_on_configuration_and_distinguishes_encoder_failure(tmp_path):
    class Encoder:
        revision, runtime, bytes = 'test-v1','unit-test',1
        attempts = 0
        def embed(self, texts, query):
            self.attempts += 1
            if texts == ['fail']:
                raise ValueError('Synthetic model failure')
            return [[1,0] for _ in texts]

    model = Encoder()
    first, _ = cached_vectors(model,['sample','sample'],query=True,cache=tmp_path,batch=4)
    again, run = cached_vectors(model,['sample','sample'],query=True,cache=tmp_path,batch=4)
    assert model.attempts == 1 and run['cached_batches'] == 1 and np.array_equal(first,again)
    model.revision = 'test-v2'
    cached_vectors(model,['sample'],query=True,cache=tmp_path,batch=4)
    with pytest.raises(ValueError,match='Synthetic model failure'):
        cached_vectors(model,['fail'],query=True,cache=tmp_path,batch=4)
    assert model.attempts == 3
