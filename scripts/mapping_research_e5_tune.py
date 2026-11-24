"""Train the final E5 encoder LayerNorm affine tensors on CPU and export a patched ONNX model."""
import argparse
from collections import defaultdict
import gc
from pathlib import Path
import shutil
from time import perf_counter

import numpy as np

from evaluate_mapping_embeddings import E5_FILES, E5_REVISION, OnnxEncoder, file_sha, normalized
from evaluate_mapping_research import calibrate, decisions, make_targets, peak_rss_mib, write
from mapping_research_data import load_frozen, sha
from mapping_research_features import CATALOG, Lexicon, prepare, train_prototypes
from mapping_research_neural import passages, queries
from mapping_research_phase2 import DATA, OUT, panel_indices, scored


def affine_names(model, tensor):
    graph=model.graph
    initial={v.name:v for v in graph.initializer}
    producers={output:node for node in graph.node for output in node.output}
    node=producers[tensor]
    if node.op_type=='LayerNormalization':
        gain,bias=node.input[1:3]
    else:
        if node.op_type!='Add':
            raise ValueError('E5 output does not terminate in an affine LayerNorm')
        bias,=set(node.input)&set(initial)
        multiplication=producers[next(name for name in node.input if name!=bias)]
        if multiplication.op_type!='Mul':
            raise ValueError('E5 output does not terminate in an affine LayerNorm')
        gain,=set(multiplication.input)&set(initial)
    if any(sum(name in node.input for node in graph.node)!=1 for name in (gain,bias)):
        raise ValueError('LayerNorm parameters have additional consumers')
    return initial[gain],initial[bias]


def raw_mean(encoder,texts,query):
    out=[]
    prefix='query: ' if query else 'passage: '
    for i in range(0,len(texts),24):
        tokens=encoder.tokenizer.encode_batch([prefix+x for x in texts[i:i+24]])
        mask=np.array([t.attention_mask for t in tokens],dtype=np.int64)
        cols={'input_ids':[t.ids for t in tokens],'token_type_ids':[t.type_ids for t in tokens],'attention_mask':mask}
        hidden=encoder.session.run([encoder.hidden],{name:np.asarray(cols[name],dtype=np.int64) for name in encoder.inputs})[0]
        out.extend((hidden * mask[:,:,None]).sum(axis=1) / mask.sum(axis=1,keepdims=True))
    return np.asarray(out,dtype=np.float64)


def build_bank(encoder):
    bank={}
    for entity in CATALOG:
        passages_=passages(entity,'full')
        fields=list(CATALOG[entity])+['HOLD']
        encoded=normalized(raw_mean(encoder,[passages_[f] for f in fields],False))
        bank[entity]=(fields,encoded)
    return bank


def encode(encoder,documents):
    texts=[query for doc in documents for query in queries(doc,'header')]
    unique=list(dict.fromkeys(texts))
    lookup=dict(zip(unique,raw_mean(encoder,unique,True),strict=True))
    return [np.asarray([lookup[t] for t in queries(doc,'header')]) for doc in documents]


def gradients(x, y, weights, bias, bank, temperature=.12):
    vectors=x*weights+bias
    norm=np.linalg.norm(vectors,axis=1,keepdims=True)
    z=vectors/norm
    logits=z@bank.T / temperature
    logits-=logits.max(axis=1,keepdims=True)
    probs=np.exp(logits)
    probs/=probs.sum(axis=1,keepdims=True)
    row=np.arange(len(x))
    loss=-np.log(probs[row,y]).sum()
    probs[row,y]-=1
    dz=probs @ bank / temperature
    deriv=(dz-z*(dz*z).sum(axis=1,keepdims=True))/norm
    return loss,(deriv*x).sum(axis=0),deriv.sum(axis=0)


def fit(documents,pooled,gain,bias,bank):
    groups=defaultdict(list)
    labels=defaultdict(list)
    for doc,vectors in zip(documents,pooled,strict=True):
        entity=doc['entity']
        targets=bank[entity][0]
        for col,raw in zip(doc['columns'],vectors,strict=True):
            labels[entity].append(targets.index(col['expected'] or 'HOLD'))
            groups[entity].append((raw-bias)/gain)
    x={k:np.asarray(v) for k,v in groups.items()}
    y={k:np.asarray(v) for k,v in labels.items()}
    weights,offset=gain.copy(),bias.copy()
    size=sum(map(len,y.values()))
    losses=[]
    for _ in range(61):
        loss, dw, db = 0,np.zeros_like(weights,dtype=float),np.zeros_like(offset,dtype=float)
        for entity,array in x.items():
            l,w,b=gradients(array,y[entity],weights,offset,bank[entity][1])
            loss+=l
            dw+=w
            db+=b
        losses.append(loss/size)
        weights-=.005*(dw/size+.03*(weights-gain))
        offset-=.005*(db/size+.03*(offset-bias))
    return weights.astype(gain.dtype),offset.astype(bias.dtype),size,losses


def matrices(docs, pooled, bank, params):
    gain,bias,weights,offset=params
    result=[]
    for doc,vectors in zip(docs,pooled,strict=True):
        targets=bank[doc['entity']][1]
        vec=normalized(((vectors-bias)/gain)*weights+offset)
        result.append(vec@(targets[:-1]-targets[-1]).T)
    return result


def evaluate(args):
    import onnx
    from onnx import numpy_helper

    started=perf_counter()
    train,train_sha=load_frozen(DATA,'train')
    cal,cal_sha=load_frozen(DATA,'calibration')
    enc=OnnxEncoder(args.model,'e5',args.threads)
    proto=onnx.load(args.model/'model.onnx')
    gain_tensor,bias_tensor=affine_names(proto,enc.hidden)
    gain,bias=[numpy_helper.to_array(t).copy() for t in (gain_tensor,bias_tensor)]
    if gain.ndim!=1 or bias.shape!=gain.shape or np.any(np.abs(gain)<1e-6):
        raise ValueError('Unsupported final E5 LayerNorm dimensions')
    parameters=sum(np.prod(v.dims,dtype=np.int64) for v in proto.graph.initializer if v.data_type==onnx.TensorProto.FLOAT)
    bank=build_bank(enc)
    pilot=[train[i] for i in panel_indices(train,40)]
    train_pooled=encode(enc,pilot)
    tick=perf_counter()
    gain_after,bias_after,size,losses=fit(pilot,train_pooled,gain,bias,bank)
    fit_seconds=perf_counter()-tick
    if np.array_equal(gain,gain_after) or np.array_equal(bias,bias_after):
        raise ValueError('Training did not change both original encoder tensors')
    weights_directory=args.output.parent/'e5-layernorm-model'
    weights_directory.mkdir(parents=True,exist_ok=True)
    for tensor,values in ((gain_tensor,gain_after),(bias_tensor,bias_after)):
        tensor.CopyFrom(numpy_helper.from_array(values,name=tensor.name))
    onnx.save(proto,weights_directory/'model.onnx')
    shutil.copyfile(args.model/'tokenizer.json',weights_directory/'tokenizer.json')
    del proto
    lexicon,prototypes=Lexicon(CATALOG),train_prototypes(train)
    calibrated=[prepare(d,lexicon,prototypes) for d in cal]
    targets=make_targets(cal,calibrated)
    specs={'before':(gain,bias,gain,bias),'after':(gain,bias,gain_after,bias_after)}
    cal_pooled=encode(enc,cal)
    policies={name:calibrate(matrices(cal,cal_pooled,bank,params),calibrated,targets) for name,params in specs.items()}
    frozen={'train_sha256':train_sha,'calibration_sha256':cal_sha,'policies':policies,'pilot_documents':[d['id'] for d in pilot]}
    write(args.output.with_name(args.output.stem+'-policy.json'),{**frozen,'sha256':sha(frozen)})
    docs,digest=load_frozen(DATA,'final')
    prepared=[prepare(d,lexicon,prototypes) for d in docs]
    pooled=encode(enc,docs)
    control_text=list(queries(docs[0],'header'))
    raw_reference=raw_mean(enc,control_text,True)
    ref=((raw_reference-bias)/gain)*gain_after+bias_after
    del enc
    gc.collect()
    checks={name:file_sha(weights_directory/name) for name in E5_FILES}
    tuned=OnnxEncoder(weights_directory,'e5',args.threads,artifact_identity=(checks,E5_REVISION+'-layernorm'))
    observed=raw_mean(tuned,control_text,True)
    discrepancy=float(np.max(np.abs(ref-observed)))
    if discrepancy>2e-5:
        raise ValueError('Exported model differs from trained E5 affine calculation')
    result={name:scored(docs,[decisions(m,r,policies[name]) for m,r in zip(matrices(docs,pooled,bank,params),prepared,strict=True)])
            for name,params in specs.items()}
    write(args.output,{'metrics':result,'final_sha256':digest,'trained_parameters':int(gain.size+bias.size),
          'onnx_fp32_parameters':int(parameters),'tensor_names':[gain_tensor.name,bias_tensor.name],
          'pilot_documents':len(pilot),'pilot_columns':size,'fit_seconds':fit_seconds,'initial_loss':losses[0],'last_loss':losses[-1],
          'export_max_delta':discrepancy,'sha256_before':E5_FILES['model.onnx'],'sha256_after':checks['model.onnx'],
          'peak_python_mib':peak_rss_mib(),'elapsed_seconds':perf_counter()-started})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=OUT/'e5-layernorm.json')
    parser.add_argument('--threads',type=int,default=3)
    evaluate(parser.parse_args())
