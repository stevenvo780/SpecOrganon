"""Index deterministic public inputs without executing a generated delivery.

These existing public checker modules are trusted operator code, not authored
products. Compile the exact read bytes; invoke only their corpus generators.
No native calls, Docker commands or test products are executed here.
"""
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).absolute().parents[1]
    base = root / 'goals/method-superiority-v1/development'
    tasks = {}
    for name in ('rangeaudit', 'ledgerfold', 'topoplan'):
        path = base / ('check_rangeaudit_public.py' if name == 'rangeaudit' else 'check_cohort_public.py')
        raw = path.read_bytes(); namespace = {'__name__': 'public_corpus_index_only', '__file__': str(path)}
        exec(compile(raw, str(path), 'exec'), namespace)
        cases = namespace['cases']() if name == 'rangeaudit' else namespace['corpus'](name)
        identity = ({'classification': 'independent public development checks; not reserved method comparison',
                     'oracle': 'integer-cell occupancy for small intervals; explicit public boundary expectations'}
                    if name == 'rangeaudit' else
                    {'classification': 'independent public development checks; not reserved or blinded', 'task': name})
        tasks[name] = {'checker': str(path.relative_to(root)), 'checker_sha256': hashlib.sha256(raw).hexdigest(),
                       'checker_args': [] if name == 'rangeaudit' else [name], 'identity': identity,
                       'cases': [{'name': case, 'input_sha256': hashlib.sha256(data).hexdigest()}
                                 for case, data, _ in cases]}
    raw = (json.dumps({'schema': 1, 'tasks': tasks}, indent=2) + '\n').encode()
    path = base / 'neutral-public-v1/case-index.json'
    if path.exists() and path.read_bytes() != raw:
        raise ValueError('existing public index differs; use a new version instead of replacing it')
    if not path.exists(): path.write_bytes(raw)
    print(json.dumps({'case_index_sha256': hashlib.sha256(raw).hexdigest(),
                      'tasks': {name: len(item['cases']) for name, item in tasks.items()}, 'model_calls': 0}))


if __name__ == '__main__': main()
