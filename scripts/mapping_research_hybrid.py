"""Compare already measured candidate generators with a measured cross-encoder."""
import argparse
import json
from pathlib import Path

import numpy as np

from evaluate_mapping_research import calibrate, decisions, make_targets, metrics, write
from mapping_research_data import load_frozen, sha
from mapping_research_features import CATALOG, Lexicon, prepare, train_prototypes
from mapping_research_neural import shortlist


def read_scores(path):
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.pop('sha256') != sha(payload):
        raise ValueError('Score artifact checksum mismatch')
    return payload


def as_matrices(bundle, split, digest, prepared):
    if bundle[split + '_sha256'] != digest:
        raise ValueError('Score split checksum mismatch')
    matrices = [np.asarray(raw) for raw in bundle[split]]
    if any(m.shape != row['allowed'].shape or not np.all(np.isfinite(m)) for m,row in zip(matrices,prepared,strict=True)):
        raise ValueError('Scores do not align with split, columns or catalog')
    return matrices


def candidate_export(prepared, matrices, digest, output):
    allow = {}
    for record, block in zip(prepared,matrices,strict=True):
        order = np.argsort(-np.where(record['allowed'],block,-1e6),axis=1,kind='stable')
        for i,row in enumerate(order):
            allow[f'{record["id"]}:{i}'] = [record['fields'][j] for j in row if record['allowed'][i,j] and block[i,j]>-1e5][:3]
    write(output, {'data_sha256':digest,'candidates':allow})


def compare(data, output, generators):
    train, _ = load_frozen(data,'train')
    calibration, cal_sha = load_frozen(data,'calibration')
    lexicon, prototypes = Lexicon(CATALOG), train_prototypes(train)
    cal = [prepare(doc,lexicon,prototypes) for doc in calibration]
    expected = make_targets(calibration,cal)
    reranker = read_scores(output / 'minilm-scores.json')
    bank = [read_scores(path) for path in generators]
    minilm = as_matrices(reranker,'calibration',cal_sha,cal)

    def rank(bundle, prepared, cross_scores, split, digest):
        candidate = as_matrices(bundle,split,digest,prepared)
        return shortlist(cross_scores,prepared,'external',candidate)

    policies = {x['name']:calibrate(rank(x,cal,minilm,'calibration',cal_sha),cal,expected) for x in bank}
    frozen = {'calibration_sha256':cal_sha,'policies':policies,'top_k':3}
    write(output/'hybrids-frozen.json',{**frozen,'sha256':sha(frozen)})
    final, final_sha = load_frozen(data,'final')
    prepared = [prepare(doc,lexicon,prototypes) for doc in final]
    cross_scores = as_matrices(reranker,'final',final_sha,prepared)
    results = {}
    for bundle in bank:
        name = bundle['name']
        raw = rank(bundle,prepared,cross_scores,'final',final_sha)
        rows = [decisions(matrix,{**source,'allowed':source['allowed'] & (matrix > -1e5)},policies[name])
                for matrix,source in zip(raw,prepared,strict=True)]
        scores = metrics(final,rows)
        scores.pop('case_counts')
        results[name + '+minilm'] = scores
        candidate_export(prepared,as_matrices(bundle,'final',final_sha,prepared),final_sha,output/(name+'-final-shortlist.json'))
    write(output/'hybrids-results.json',{'final_sha256':final_sha,'models':results})


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('generators',nargs='+',type=Path)
    parser.add_argument('--data',type=Path,default=Path('.artifacts/mapping-research/data'))
    parser.add_argument('--output',type=Path,default=Path('.artifacts/mapping-research/results'))
    args=parser.parse_args()
    compare(args.data,args.output,args.generators)
