"""Public development oracles independent of generated tests, never holdout F."""
import hashlib
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys


def exact(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(exact(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    return a == b


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate output key')
        result[key] = value
    return result


def ledger_oracle(entries):
    # Group first, then sum; independently of a streaming accumulator.
    names = sorted({e['account'] for e in entries})
    balances = {name: sum(e['delta'] for e in entries if e['account'] == name) for name in names}
    return {'balances': balances, 'total': sum(balances.values()), 'count': len(entries),
            'zero_accounts': [name for name in names if balances[name] == 0]}


def topo_oracle(request):
    nodes, edges = sorted(request['nodes']), {tuple(e) for e in request['edges']}
    # Exhaustive lexicographic permutation search, not the product's Kahn queue.
    order = next(list(p) for p in itertools.permutations(nodes)
                 if all(p.index(a) < p.index(b) for a, b in edges))
    # Layers via longest predecessor path, independently of removing rounds.
    depth = {n: 0 for n in nodes}
    for n in order:
        parents = [a for a, b in edges if b == n]
        depth[n] = max((depth[a] + 1 for a in parents), default=0)
    layers = [[n for n in nodes if depth[n] == i] for i in range(max(depth.values(), default=-1) + 1)]
    return {'order': order, 'layers': layers, 'roots': layers[0] if layers else []}


def corpus(task):
    rows = []
    def valid(name, requests, expected=None):
        raw = b''.join((json.dumps(r, separators=(',', ':')) + '\n').encode() for r in requests)
        oracle = ledger_oracle if task == 'ledgerfold' else topo_oracle
        outcomes = ([oracle(r['entries']) for r in requests] if task == 'ledgerfold'
                    else [oracle(r) for r in requests]) if expected is None else expected
        rows.append((name, raw, outcomes))

    valid('empty-input', [])
    rng = random.Random(2026100601)
    if task == 'ledgerfold':
        empty = {'entries': []}
        samples = [empty, {'entries': [{'account': 'cash', 'delta': 7}, {'account': 'cash', 'delta': -7},
                                     {'account': 'bank', 'delta': 3}]},
                   {'entries': [{'account': 'a', 'delta': 10**12}] * 2},
                   {'entries': [{'account': 'z_' + '0' * 30, 'delta': -10**12},
                                {'account': 'a', 'delta': 0}]}]
        valid('public-examples-and-boundaries', samples)
        for i in range(60):
            requests = []
            for _ in range(rng.randrange(1, 5)):
                entries = [{'account': rng.choice(['a', 'b', 'cash', 'cost_1', 'x']),
                            'delta': rng.randrange(-100, 101)} for _ in range(rng.randrange(31))]
                requests.append({'entries': entries})
            valid('group-sum-' + str(i), requests)
        valid('entry-limit-exact', [{'entries': [{'account': 'a', 'delta': 10**12}] * 2000}])
        bad = [b'{}\n', b'[]\n', b'{"entries":null}\n', b'{"entries":[],"extra":0}\n',
               b'{"entries":[],"entries":[]}\n', b'{"entries":[null]}\n',
               b'{"entries":[{"account":"a","delta":1,"delta":2}]}\n']
        for account in ['', '1a', 'A', 'a-b', 'á', 'a' * 33, True, 1, None]:
            bad.append((json.dumps({'entries': [{'account': account, 'delta': 1}]}) + '\n').encode())
        for delta in [True, False, 1.0, '1', None, 10**12 + 1, -10**12 - 1]:
            bad.append((json.dumps({'entries': [{'account': 'a', 'delta': delta}]}) + '\n').encode())
        bad.extend([b'{"entries":[{"account":"a"}]}\n',
                    b'{"entries":[{"account":"a","delta":1,"other":0}]}\n',
                    b'{"entries":[{"account":"a","delta":NaN}]}\n',
                    b'{"entries":[{"account":"a","delta":Infinity}]}\n',
                    (json.dumps({'entries': [{'account': 'a', 'delta': 1}] * 2001}) + '\n').encode()])
        # JSON Unicode escapes may encode a valid ASCII name.
        rows.append(('escaped-ascii-account', b'{"entries":[{"account":"\\u0061","delta":0}]}\n',
                     [{'balances': {'a': 0}, 'total': 0, 'count': 1, 'zero_accounts': ['a']}]))
    elif task == 'topoplan':
        empty = {'nodes': [], 'edges': []}
        examples = [empty, {'nodes': ['z', 'b', 'a'], 'edges': [['a', 'b']]},
                    {'nodes': ['c', 'a', 'b'], 'edges': [['a', 'c'], ['b', 'c'], ['a', 'c']]}]
        valid('order-is-not-layers-concatenated', examples)
        for i in range(60):
            names = list('abcdefg')[:rng.randrange(1, 8)]
            rng.shuffle(names)
            edges = [[a, b] for ai, a in enumerate(names) for b in names[ai+1:] if rng.random() < .35]
            shuffled = names[:]; rng.shuffle(shuffled)
            valid('permutation-oracle-' + str(i), [{'nodes': shuffled, 'edges': edges + edges[:2]}])
        names = ['n' + str(i).zfill(3) for i in range(120)]
        valid('node-limit-exact', [{'nodes': names[::-1], 'edges': []}],
              [{'order': names, 'layers': [names], 'roots': names}])
        valid('edge-limit-duplicate-exact', [{'nodes': ['a', 'b'], 'edges': [['a', 'b']] * 2000}])
        valid('max-name', [{'nodes': ['a' * 16], 'edges': []}])
        bad = [b'{}\n', b'[]\n', b'{"nodes":null,"edges":[]}\n',
               b'{"nodes":[],"edges":null}\n', b'{"nodes":[],"edges":[],"extra":0}\n',
               b'{"nodes":[],"nodes":[],"edges":[]}\n']
        for nodes, edges in [(['a', 'a'], []), (['a'], [['a', 'a']]),
                             (['a', 'b'], [['a', 'b'], ['b', 'a']]),
                             (['a', 'b', 'c'], [['a', 'b'], ['b', 'c'], ['c', 'a']]),
                             (['a'], [['a', 'b']]), (['a'], [[True, 'a']]),
                             (['a'], [['a']]), (['a'], [['a', 'a', 'a']]),
                             (['a'], [None]), (['a', 'b'], [['a', 'b']] * 2001),
                             (['n' + str(i) for i in range(121)], [])]:
            bad.append((json.dumps({'nodes': nodes, 'edges': edges}) + '\n').encode())
        for name in ['', '1a', 'A', 'a-b', 'á', 'a' * 17, True, 1, None]:
            bad.append((json.dumps({'nodes': [name], 'edges': []}) + '\n').encode())
        bad.extend([b'{"nodes":[NaN],"edges":[]}\n', b'{"nodes":[Infinity],"edges":[]}\n'])
    else:
        raise ValueError('unknown public development task')

    base = (json.dumps(empty, separators=(',', ':')) + '\n').encode()
    expected_empty = ledger_oracle([]) if task == 'ledgerfold' else topo_oracle(empty)
    rows.append(('byte-limit-exact', b' ' * (131072 - len(base)) + base, [expected_empty]))
    bad.extend([b'\n', b' \n', b'\xff\n', b'{', b' ' * (131073 - len(base)) + base])
    for i, raw in enumerate(bad):
        rows.append(('invalid-' + str(i), raw, None))
    for i, raw in enumerate([b'\n', b'{}\n', b'\xff\n']):
        rows.append(('atomic-after-valid-' + str(i), base + raw, None))
        rows.append(('atomic-before-valid-' + str(i), raw + base, None))
    return rows


def main(task):
    filename, error = {'ledgerfold': ('ledger_fold.py', b'ledger-fold: invalid input\n'),
                       'topoplan': ('topo_plan.py', b'topo-plan: invalid input\n')}[task]
    target = Path(__file__).with_name(filename)
    records = []
    for name, raw, expected in corpus(task):
        try:
            p = subprocess.run([sys.executable, '-E', '-s', '-S', '-B', str(target)],
                               input=raw, capture_output=True, timeout=4)
            if expected is None:
                passed = p.returncode == 2 and p.stdout == b'' and p.stderr == error
            else:
                observed = [json.loads(line, object_pairs_hook=unique,
                                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
                            for line in p.stdout.decode('utf-8').splitlines()]
                passed = p.returncode == 0 and p.stderr == b'' and exact(observed, expected)
                passed = passed and (p.stdout == b'' if not expected else p.stdout.endswith(b'\n'))
            record = {'name': name, 'passed': passed, 'exit_code': p.returncode,
                      'stdout_sha256': hashlib.sha256(p.stdout).hexdigest(),
                      'stderr_sha256': hashlib.sha256(p.stderr).hexdigest()}
        except (subprocess.TimeoutExpired, ValueError, UnicodeError) as exc:
            record = {'name': name, 'passed': False, 'error': type(exc).__name__}
        record['input_sha256'] = hashlib.sha256(raw).hexdigest()
        records.append(record)
    failed = [r for r in records if not r['passed']]
    print(json.dumps({'classification': 'independent public development checks; not reserved or blinded',
                      'task': task, 'cases': len(records), 'passed': sum(r['passed'] for r in records),
                      'failed': failed, 'observations_sha256': hashlib.sha256(
                          json.dumps(records, sort_keys=True).encode()).hexdigest()}))
    return int(bool(failed))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
