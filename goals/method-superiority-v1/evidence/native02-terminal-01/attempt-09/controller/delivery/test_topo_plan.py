"""Corpus contractual fijado antes de ejecutar; sin dependencias externas."""
import itertools
import json
import subprocess
import sys

PYTHON = '/opt/specorganon/venv/bin/python'
PROGRAM = '/input/delivery/topo_plan.py'
ERROR = b'topo-plan: invalid input\n'


def encode(value):
    return json.dumps(value, separators=(',', ':')).encode('utf-8') + b'\n'


def oracle(nodes, edges):
    edges = set(map(tuple, edges))
    orders = []
    for order in itertools.permutations(sorted(nodes)):
        positions = {node: index for index, node in enumerate(order)}
        if all(positions[a] < positions[b] for a, b in edges):
            orders.append(order)
    if not orders:
        return None
    remaining = set(nodes)
    layers = []
    while remaining:
        current = sorted(node for node in remaining
                         if not any(b == node and a in remaining for a, b in edges))
        if not current:
            return None
        layers.append(current)
        remaining.difference_update(current)
    return {'order': list(min(orders)), 'layers': layers,
            'roots': layers[0] if layers else []}


def corpus():
    cases = []

    def add(name, raw, expected=None):
        cases.append((name, raw, expected))

    def graph(name, nodes, edges, expected):
        add(name, encode({'nodes': nodes, 'edges': edges}), [expected])

    empty = {'order': [], 'layers': [], 'roots': []}
    first = {'order': ['a', 'b', 'z'], 'layers': [['a', 'z'], ['b']],
             'roots': ['a', 'z']}
    second = {'order': ['a', 'b', 'c'], 'layers': [['a', 'b'], ['c']],
              'roots': ['a', 'b']}
    graph('example-1', ['z', 'b', 'a'], [['a', 'b']], first)
    graph('example-2', ['c', 'a', 'b'], [['a', 'c'], ['b', 'c'], ['a', 'c']], second)
    graph('example-3', [], [], empty)
    add('empty-stdin', b'', [])
    one = encode({'nodes': ['z', 'b', 'a'], 'edges': [['a', 'b']]})
    zero = encode({'nodes': [], 'edges': []})
    add('valid-batch', one + zero, [first, empty])
    add('no-final-newline', one[:-1], [first])
    add('crlf', one[:-1] + b'\r\n', [first])
    add('json-whitespace', b' \t' + zero[:-1] + b' \t\n', [empty])

    nodes = ['c', 'a', 'b']
    possible = [(a, b) for a in sorted(nodes) for b in sorted(nodes) if a != b]
    for mask in range(1 << len(possible)):
        edges = [list(edge) for bit, edge in enumerate(possible) if mask & (1 << bit)]
        expected = oracle(nodes, edges)
        raw = encode({'nodes': nodes, 'edges': edges})
        add('graph-%02d' % mask, raw, None if expected is None else [expected])

    for count in (119, 120, 121):
        names = ['n%03d' % index for index in range(count)]
        expected = {'order': names, 'layers': [names], 'roots': names}
        add('nodes-%d' % count, encode({'nodes': names, 'edges': []}),
            [expected] if count <= 120 else None)
    chain = ['n%03d' % index for index in range(120)]
    graph('chain-120', list(reversed(chain)),
          [[chain[i], chain[i + 1]] for i in range(119)],
          {'order': chain, 'layers': [[node] for node in chain], 'roots': [chain[0]]})
    pair = {'order': ['a', 'b'], 'layers': [['a'], ['b']], 'roots': ['a']}
    for count in (1999, 2000, 2001):
        add('edges-%d' % count,
            encode({'nodes': ['b', 'a'], 'edges': [['a', 'b']] * count}),
            [pair] if count <= 2000 else None)
    for size in (131071, 131072, 131073):
        raw = zero[:-1] + b' ' * (size - len(zero)) + b'\n'
        add('bytes-%d' % size, raw, [empty] if size <= 131072 else None)
    name = 'a' + '0' * 15
    graph('name-16', [name], [], {'order': [name], 'layers': [[name]], 'roots': [name]})
    graph('name-underscore', ['a_0'], [],
          {'order': ['a_0'], 'layers': [['a_0']], 'roots': ['a_0']})

    invalid_objects = [
        [], None, True, 1, 'graph', {}, {'nodes': []}, {'edges': []},
        {'nodes': [], 'edges': [], 'extra': 0},
        {'nodes': None, 'edges': []}, {'nodes': {}, 'edges': []},
        {'nodes': 'a', 'edges': []}, {'nodes': ['a'], 'edges': None},
        {'nodes': ['a'], 'edges': {}}, {'nodes': ['a'], 'edges': 'a'},
        {'nodes': ['a', 'a'], 'edges': []},
        {'nodes': [1], 'edges': []}, {'nodes': [True], 'edges': []},
        {'nodes': [None], 'edges': []}, {'nodes': [[]], 'edges': []},
        {'nodes': [{}], 'edges': []},
    ]
    for bad_name in ('', 'A', '0a', 'a-b', 'a b', 'a\n', 'é', 'a' * 17):
        invalid_objects.append({'nodes': [bad_name], 'edges': []})
    for edge in ([], ['a'], ['a', 'b', 'a'], 'ab', None, {},
                 [1, 'b'], ['a', True], [[], 'b'], ['a', {}],
                 ['a', 'unknown'], ['unknown', 'b'], ['a', 'a']):
        invalid_objects.append({'nodes': ['a', 'b'], 'edges': [edge]})
    invalid_objects.append({'nodes': ['a', 'b', 'c'],
                            'edges': [['a', 'b'], ['b', 'c'], ['c', 'a']]})
    for index, obj in enumerate(invalid_objects):
        add('structure-%02d' % index, encode(obj))

    invalid_raw = [
        b'\n', b' \t\n', b'\r\n', b'{', b'{} trailing\n',
        b'{"nodes":[],"edges":[],}\n', b'{"nodes":[],"edges":[]}{}\n',
        b'{"nodes":[],"nodes":[],"edges":[]}\n',
        b'{"nodes":[],"edges":[],"edges":[]}\n',
        b'{"nodes":[],"edges":[],"nested":{"x":1,"x":2}}\n',
        b'{"nodes":[NaN],"edges":[]}\n',
        b'{"nodes":[],"edges":Infinity}\n',
        b'{"nodes":[],"edges":-Infinity}\n',
        b'{"nodes":["\xff"],"edges":[]}\n',
        b'\xef\xbb\xbf' + zero,
        b'{"nodes":["\\ud800"],"edges":[]}\n',
        b'[' * 1500 + b'0' + b']' * 1500 + b'\n',
    ]
    for index, raw in enumerate(invalid_raw):
        add('syntax-%02d' % index, raw)
    add('atomic-invalid-last', one + b'{\n')
    add('atomic-invalid-first', b'{\n' + one)
    add('atomic-invalid-middle', zero + b'\n' + one)
    add('extra-blank-line', zero + b'\n')
    add('late-cycle', one + encode({'nodes': ['a', 'b'],
                                   'edges': [['a', 'b'], ['b', 'a']]}))
    return cases


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate output key')
        result[key] = value
    return result


def no_constant(value):
    raise ValueError('nonfinite output')


def matches(actual, expected):
    if expected is None:
        return actual.returncode == 2 and actual.stdout == b'' and actual.stderr == ERROR
    if actual.returncode != 0 or actual.stderr != b'':
        return False
    if not expected:
        return actual.stdout == b''
    if not actual.stdout.endswith(b'\n'):
        return False
    lines = actual.stdout[:-1].decode('utf-8').split('\n')
    if len(lines) != len(expected):
        return False
    decoded = [json.loads(line, object_pairs_hook=unique_pairs,
                          parse_constant=no_constant) for line in lines]
    return decoded == expected


def main():
    cases = corpus()
    records = []
    discrepancies = []
    for name, raw, expected in cases:
        try:
            actual = subprocess.run([PYTHON, PROGRAM], input=raw,
                                    capture_output=True, timeout=5)
            records.append({'id': name, 'input': raw, 'expected': expected,
                            'stdout': actual.stdout, 'stderr': actual.stderr,
                            'exit': actual.returncode})
            try:
                correct = matches(actual, expected)
            except (ValueError, TypeError, RecursionError):
                correct = False
            if not correct:
                discrepancies.append(name)
        except (OSError, subprocess.TimeoutExpired) as error:
            records.append({'id': name, 'input': raw, 'expected': expected,
                            'execution_error': type(error).__name__})
            discrepancies.append(name)
    print(json.dumps({'cases': len(records), 'discrepancies': discrepancies},
                     separators=(',', ':')))
    return 1 if discrepancies else 0


if __name__ == '__main__':
    sys.exit(main())
