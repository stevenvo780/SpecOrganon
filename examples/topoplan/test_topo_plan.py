#!/usr/bin/env python3
"""Corpus contractual prefijado; ejecución por subprocess, sin importar el producto."""
import itertools
import json
import subprocess
import sys

PYTHON = '/opt/specorganon/venv/bin/python'
PROGRAM = '/input/delivery/topo_plan.py'
LIMIT = 131072
ERROR = b'topo-plan: invalid input\n'


def encode(obj):
    return json.dumps(obj, separators=(',', ':')).encode('ascii') + b'\n'


def oracle(nodes, edges):
    edges = set(map(tuple, edges))
    orders = [p for p in itertools.permutations(sorted(nodes))
              if all(p.index(a) < p.index(b) for a, b in edges)]
    if not orders:
        return None
    order = list(min(orders))
    remaining = set(nodes)
    layers = []
    while remaining:
        ready = sorted(n for n in remaining
                       if not any(b == n and a in remaining for a, b in edges))
        if not ready:
            raise ValueError('oracle cycle')
        layers.append(ready)
        remaining.difference_update(ready)
    return {'order': order, 'layers': layers,
            'roots': layers[0] if layers else []}


def corpus():
    cases = []

    def valid(label, raw, expected):
        cases.append((label, raw, expected))

    def invalid(label, raw):
        cases.append((label, raw, None))

    examples = [
        ({'nodes': ['z', 'b', 'a'], 'edges': [['a', 'b']]},
         {'order': ['a', 'b', 'z'], 'layers': [['a', 'z'], ['b']], 'roots': ['a', 'z']}),
        ({'nodes': ['c', 'a', 'b'], 'edges': [['a', 'c'], ['b', 'c'], ['a', 'c']]},
         {'order': ['a', 'b', 'c'], 'layers': [['a', 'b'], ['c']], 'roots': ['a', 'b']}),
        ({'nodes': [], 'edges': []}, {'order': [], 'layers': [], 'roots': []})
    ]
    for i, (request, expected) in enumerate(examples):
        valid('example-' + str(i), encode(request), [expected])
    valid('empty-stream', b'', [])
    empty = encode(examples[2][0])
    empty_expected = examples[2][1]
    valid('no-final-newline', empty[:-1], [empty_expected])
    valid('crlf', empty[:-1] + b'\r\n', [empty_expected])
    valid('surrounding-space', b' \t' + empty[:-1] + b' \t\n', [empty_expected])

    # Enumerate every directed edge subset on every node subset.
    # Cyclic candidates are excluded by the permutation oracle, not the product.
    chunk = bytearray()
    expected_chunk = []
    chunk_number = 0
    for count in range(5):
        for nodes_tuple in itertools.combinations('abcd', count):
            nodes = list(nodes_tuple)
            possible = list(itertools.permutations(nodes, 2))
            for mask in range(1 << len(possible)):
                edges = [list(e) for i, e in enumerate(possible) if mask & (1 << i)]
                expected = oracle(nodes, edges)
                if expected is None:
                    continue
                variants = [(nodes, edges), (nodes[::-1], edges[::-1]),
                            (nodes[::-1], edges[::-1] + edges)]
                for ns, es in variants:
                    raw = encode({'nodes': ns, 'edges': es})
                    if len(chunk) + len(raw) > 60000:
                        valid('dag-chunk-' + str(chunk_number), bytes(chunk), expected_chunk)
                        chunk_number += 1
                        chunk = bytearray()
                        expected_chunk = []
                    chunk.extend(raw)
                    expected_chunk.append(expected)
    if chunk:
        valid('dag-chunk-' + str(chunk_number), bytes(chunk), expected_chunk)

    names = ['n%03d' % i for i in range(120)]
    chain = [[names[i], names[i + 1]] for i in range(119)]
    chain_expected = {'order': names, 'layers': [[n] for n in names], 'roots': names[:1]}
    valid('120-node-chain', encode({'nodes': names[::-1], 'edges': chain[::-1]}), [chain_expected])
    valid('120-roots', encode({'nodes': names[::-1], 'edges': []}),
          [{'order': names, 'layers': [names], 'roots': names}])
    pair = {'nodes': ['a', 'b'], 'edges': [['a', 'b']] * 2000}
    valid('2000-edges', encode(pair), [oracle(['a', 'b'], [['a', 'b']])])
    accepted_names = ['a', 'a0_', 'z' * 16]
    valid('name-boundaries', encode({'nodes': accepted_names[::-1], 'edges': []}),
          [oracle(accepted_names, [])])
    exact = empty[:-1] + b' ' * (LIMIT - len(empty)) + b'\n'
    valid('byte-limit-minus-one', exact[:-2] + b'\n', [empty_expected])
    valid('byte-limit', exact, [empty_expected])
    invalid('byte-limit-plus-one', exact[:-1] + b' \n')

    bad_objects = [
        None, [], True, 1, 'x', {}, {'nodes': []}, {'edges': []},
        {'nodes': [], 'edges': [], 'extra': 0},
        {'nodes': None, 'edges': []}, {'nodes': {}, 'edges': []},
        {'nodes': 'a', 'edges': []}, {'nodes': [], 'edges': None},
        {'nodes': [], 'edges': {}}, {'nodes': [], 'edges': 'x'},
        {'nodes': names + ['extra'], 'edges': []},
        {'nodes': ['a', 'b'], 'edges': [['a', 'b']] * 2001},
        {'nodes': ['a', 'a'], 'edges': []},
        {'nodes': ['a'], 'edges': [['a', 'a']]},
        {'nodes': ['a'], 'edges': [['a', 'b']]},
        {'nodes': ['a', 'b'], 'edges': [['a', 'b'], ['b', 'a']]},
        {'nodes': ['a', 'b', 'c', 'z'], 'edges': [['a', 'b'], ['b', 'c'], ['c', 'a']]}
    ]
    for name in ['', 'A', '0a', '_a', 'a-b', 'a b', 'a\n', 'a' * 17, 'á', 1, True, None, [], {}]:
        bad_objects.append({'nodes': [name], 'edges': []})
    for edge in [[], ['a'], ['a', 'b', 'a'], 'ab', {}, None, 1,
                 [1, 'b'], ['a', None], [[], 'b'], ['a', {}]]:
        bad_objects.append({'nodes': ['a', 'b'], 'edges': [edge]})
    malformed = [
        b'\n', b' \t\n', b'\r\n', b'{\n', empty + b'\n',
        b'{"nodes":[],"edges":[],}\n',
        b'{"nodes":[],"edges":[]} {}\n',
        b'{"nodes":[],"nodes":[],"edges":[]}\n',
        b'{"nodes":[],"edges":[],"edges":[]}\n',
        b'{"nodes":[],"edges":[],"n\\u006fdes":[]}\n',
        b'{"nodes":[{"x":1,"x":2}],"edges":[]}\n',
        b'{"nodes":[NaN],"edges":[]}\n',
        b'{"nodes":[Infinity],"edges":[]}\n',
        b'{"nodes":[-Infinity],"edges":[]}\n',
        b'{"nodes":[1e999],"edges":[]}\n',
        b'{"nodes":["\\ud800"],"edges":[]}\n',
        b'\xff\n', b'\xc0\xaf\n', b'\xe2\x82', b'\xef\xbb\xbf' + empty,
        b'{"nodes":["a\x00"],"edges":[]}\n'
    ]
    bad_inputs = [encode(obj) for obj in bad_objects] + malformed
    for i, raw in enumerate(bad_inputs):
        label = 'reject-' + str(i)
        invalid(label, raw)
        separator = b'' if raw.endswith(b'\n') else b'\n'
        invalid(label + '-first', raw + separator + empty + empty)
        invalid(label + '-middle', empty + raw + separator + empty)
        invalid(label + '-last', empty + empty + raw)
    return tuple(cases)


def check(case):
    label, raw, expected = case
    try:
        proc = subprocess.run([PYTHON, PROGRAM], input=raw,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=20, check=False)
    except subprocess.TimeoutExpired:
        return 'timeout'
    if expected is None:
        return None if (proc.returncode, proc.stdout, proc.stderr) == (2, b'', ERROR) else 'rejection'
    if proc.returncode != 0 or proc.stderr:
        return 'termination'
    if not expected:
        return None if proc.stdout == b'' else 'empty-output'
    lines = proc.stdout.split(b'\n')
    if lines[-1] != b'' or len(lines) != len(expected) + 1:
        return 'framing'
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate output key')
                result[key] = value
            return result
        actual = [json.loads(line.decode('utf-8'), object_pairs_hook=unique)
                  for line in lines[:-1]]
    except (ValueError, UnicodeError):
        return 'output-json'
    return None if actual == expected else 'plans'


def main():
    try:
        cases = corpus()  # Freeze all inputs and expectations before any product execution.
        for index, case in enumerate(cases):
            issue = check(case)
            if issue:
                print('FAIL batch=%d label=%s check=%s' % (index, case[0], issue))
                return 1
        print('OK conforming_batches=%d total_batches=%d' % (len(cases), len(cases)))
        return 0
    except Exception as exc:
        # Bounded diagnostic; never echo potentially large streams or traceback.
        print('ERROR harness=' + type(exc).__name__[:60])
        return 1


if __name__ == '__main__':
    sys.exit(main())
