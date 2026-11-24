"""Post-freeze attribution at one fixed confidence and one fixed margin."""
import argparse
from collections import Counter
import json
from pathlib import Path

from evaluate_mapping_phase6 import DATA, METHODS, OUT, PHASE5, calculate, setup
from evaluate_mapping_research import write
from mapping_phase6_data import read_panel
from mapping_phase6_rank import build_frames
from mapping_phase6_risk import make_predictions, risk_counts
from mapping_research_data import sha
from threadpoolctl import threadpool_limits


def fixed_ablation(args):
    frozen = json.loads((args.output / 'frozen-policy.json').read_bytes())
    if frozen['sha256'] != sha({key: value for key, value in frozen.items() if key != 'sha256'}):
        raise ValueError('Frozen policy digest mismatch')
    lexicon, generator, _, aliases, scorer, provenance = setup(args)
    if provenance != frozen['provenance']:
        raise ValueError('Ablation requires the original frozen ranking code and training data')
    cutoff, margin = (frozen['winner'][key] for key in ('threshold', 'margin'))
    report = {}
    for split in ('selection', 'holdout'):
        docs, digest = read_panel(args.output, split)
        frames = build_frames(docs, lexicon, generator, aliases)
        methods, _ = calculate(frames, scorer, METHODS)
        rows = {}
        for name, proposals in methods.items():
            decisions = [make_predictions(item, cutoff, margin) for item in proposals]
            mistakes = Counter()
            for doc, answers in zip(docs, decisions, strict=True):
                for col, row in zip(doc['columns'], answers, strict=True):
                    reference, prediction = col['expected'], row['prediction']
                    if prediction and reference != prediction:
                        mistakes[f'{reference or col["scenario"]}->{prediction}'] += 1
            rows[name] = {**risk_counts(docs, decisions), 'wrong_types': dict(mistakes),
                          'routed_columns': sum(proposal.routed for proposal in proposals)}
        report[split] = {'data_sha': digest, 'methods': rows}
    return {'frozen_policy_sha': frozen['sha256'], 'threshold': cutoff, 'margin': margin, **report}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--data', type=Path, default=DATA)
    parser.add_argument('--phase5', type=Path, default=PHASE5 / 'verified')
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        write(args.output / 'fixed-ablation.json', fixed_ablation(args))
