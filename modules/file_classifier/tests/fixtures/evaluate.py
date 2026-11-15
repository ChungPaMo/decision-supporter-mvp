"""시험셋으로 분류기를 채점한다. 저장소 루트에서:

    python -X utf8 modules/file_classifier/tests/fixtures/evaluate.py [--failures]

결과 분류
    correct   기대한 entity 를 추천했거나, 보류가 정답인 사례를 보류함 (hold_ok 사례의 보류 포함)
    wrong     오분류: 틀린 entity 를 추천했거나, 보류해야 할 사례에 추천함
    missed    추천이 정답인데 보류함 (hold_ok 가 아닌 사례)
"""
import collections
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / 'modules' / 'file_classifier' / 'src')]

from contracts.interfaces.modules import ClassificationInput  # noqa: E402
from file_classifier import classify  # noqa: E402

CASES = pathlib.Path(__file__).parent / 'cases.json'


def judge(case, output):
    e = case['expected']
    if output.recommended_entity is None:
        return 'correct' if e['must_hold'] or e['hold_ok'] else 'missed'
    return 'correct' if output.recommended_entity == e['expected_entity'] else 'wrong'


def run():
    rows = []
    for case in json.loads(CASES.read_text(encoding='utf-8'))['cases']:
        request = ClassificationInput(**case['payload'])
        start = time.perf_counter()
        output = classify(request)
        elapsed = (time.perf_counter() - start) * 1000
        e = case['expected']
        guided = None if not e['guidance_entity'] else e['guidance_entity'] in [c.entity for c in output.candidates]
        rows.append({'case': case, 'output': output, 'outcome': judge(case, output), 'ms': elapsed, 'guided': guided,
                     'held_when_ok': output.recommended_entity is None and e['hold_ok']})
    return rows


def summarize(rows):
    n = len(rows)
    count = collections.Counter(r['outcome'] for r in rows)
    need = [r for r in rows if not r['case']['expected']['must_hold']]
    guided = [r['guided'] for r in rows if r['guided'] is not None]
    times = sorted(r['ms'] for r in rows)
    return {'n': n, 'correct': count['correct'], 'wrong': count['wrong'], 'missed': count['missed'],
            'accuracy': count['correct'] / n if n else 0.0, 'misclassification_rate': count['wrong'] / n if n else 0.0,
            'hold_rate': sum(r['output'].hold for r in rows) / n if n else 0.0,
            'recommend_recall': sum(r['output'].recommended_entity == r['case']['expected']['expected_entity'] for r in need) / len(need) if need else 0.0,
            'guidance_hits': f'{sum(guided)}/{len(guided)}', 'ms_median': times[n // 2] if n else 0.0, 'ms_max': times[-1] if n else 0.0}


if __name__ == '__main__':
    results = run()
    for title, subset in [('all', results), ('dev', [r for r in results if r['case']['split'] == 'dev']),
                          ('test', [r for r in results if r['case']['split'] == 'test'])]:
        print(title, json.dumps(summarize(subset), ensure_ascii=False))
    print('--- by group')
    for group in sorted({r['case']['group'] for r in results}):
        s = summarize([r for r in results if r['case']['group'] == group])
        print(f"{group:18s} n={s['n']:3d} correct={s['correct']:3d} wrong={s['wrong']} missed={s['missed']} hold_rate={s['hold_rate']:.0%} recall={s['recommend_recall']:.0%}")
    print('--- by sample rows (추천이 정답인 사례)')
    for label, pick in [('0', lambda k: k == 0), ('1+', lambda k: k > 0)]:
        sub = [r for r in results if not r['case']['expected']['must_hold']
               and pick(sum(len(x['sample_rows']) for x in r['case']['payload']['sheets']))]
        s = summarize(sub)
        print(f"rows {label:2s} n={s['n']} recall={s['recommend_recall']:.1%} wrong={s['wrong']} held_when_ok={sum(r['held_when_ok'] for r in sub)}")
    if '--failures' in sys.argv:
        for r in results:
            if r['outcome'] != 'correct' or r['guided'] is False or r['held_when_ok']:
                c, o = r['case'], r['output']
                print(f"\n{r['outcome']} {c['case_id']} {c['variant']} expected={c['expected']} got={o.recommended_entity} hold={o.hold}")
                print('   ', [s['columns'][:10] for s in c['payload']['sheets']][:2])
                print('   ', o.reasons[:2])
