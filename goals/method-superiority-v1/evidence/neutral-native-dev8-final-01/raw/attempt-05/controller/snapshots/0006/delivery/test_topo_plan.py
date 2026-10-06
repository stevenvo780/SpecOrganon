#!/usr/bin/env python3
"""Fixed offline battery; expectations are independent of implementation output."""
import copy
import itertools
import json
from pathlib import Path
import runpy
import subprocess
import sys

PROGRAM = str(Path(__file__).resolve().parent / 'topo_plan.py')
ARGV = [sys.executable, '-I', '-B', '-c',
        'import runpy; runpy.run_path(' + repr(PROGRAM) + ", run_name='__main__')"]
ERROR = b'topo-plan: invalid input\n'
COUNTS = {'cli_batches': 0, 'graph_cases': 0, 'assertions': 0}


def require(condition, label):
    COUNTS['assertions'] += 1
    if not condition:
        raise AssertionError(label)


def encode(request):
    return json.dumps(request, separators=(',', ':')).encode('utf-8')


def run_cli(raw):
    COUNTS['cli_batches'] += 1
    return subprocess.run(ARGV, input=raw, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=15, check=False)


def valid(raw, expected, label):
    result = run_cli(raw)
    require(result.returncode == 0, label + ': exit')
    require(result.stderr == b'', label + ': stderr')
    lines = result.stdout.split(b'\n')
    require(lines[-1] == b'', label + ': final newline')
    lines.pop()
    require(len(lines) == len(expected), label + ': response count')
    actual = [json.loads(line) for line in lines]
    require(actual == expected, label + ': complete response objects')


def invalid(raw, label):
    result = run_cli(raw)
    require(result.returncode == 2, label + ': exit')
    require(result.stdout == b'', label + ': atomic stdout')
    require(result.stderr == ERROR, label + ': exact stderr')


def oracle(nodes, edges):
    parents = {node: set() for node in nodes}
    for source, target in edges:
        parents[target].add(source)
    order = None
    for candidate in itertools.permutations(sorted(nodes)):
        positions = {node: index for index, node in enumerate(candidate)}
        if all(positions[source] < positions[target] for source, target in edges):
            order = list(candidate)
            break
    if order is None:
        return None
    remaining = set(nodes)
    layers = []
    while remaining:
        current = sorted(node for node in remaining
                         if parents[node].isdisjoint(remaining))
        require(bool(current), 'oracle progress')
        layers.append(current)
        remaining.difference_update(current)
    return {'order': order, 'layers': layers,
            'roots': layers[0][:] if layers else []}


def exercise():
    namespace = runpy.run_path(PROGRAM)
    plan = namespace['plan']
    invalid_type = namespace['InvalidInput']
    empty = {'nodes': [], 'edges': []}
    empty_output = {'order': [], 'layers': [], 'roots': []}
    examples = [
        ({'nodes': ['z', 'b', 'a'], 'edges': [['a', 'b']]},
         {'order': ['a', 'b', 'z'], 'layers': [['a', 'z'], ['b']],
          'roots': ['a', 'z']}),
        ({'nodes': ['c', 'a', 'b'],
          'edges': [['a', 'c'], ['b', 'c'], ['a', 'c']]},
         {'order': ['a', 'b', 'c'], 'layers': [['a', 'b'], ['c']],
          'roots': ['a', 'b']}),
        (empty, empty_output)]
    valid(b'', [], 'empty stream')
    for index, (request, expected) in enumerate(examples):
        valid(encode(request) + b'\n', [expected], 'public example ' + str(index))
    batch = b'\n'.join(encode(request) for request, _ in examples)
    outputs = [expected for _, expected in examples]
    valid(batch, outputs, 'unterminated final request')
    valid(batch.replace(b'\n', b'\r\n') + b'\r\n', outputs, 'CRLF batch')
    valid(b' \t' + encode(empty) + b' \t\r\n', [empty_output], 'JSON whitespace')
    valid(b'{"no\\u0064es":[],"edges":[]}\n', [empty_output], 'escaped field name')

    bad = [
        ('blank', b'\n'), ('whitespace line', b' \t\r\n'),
        ('extra blank line', encode(empty) + b'\n\n'),
        ('malformed', b'{'), ('trailing data', encode(empty) + b' true'),
        ('two objects on one line', encode(empty) + encode(empty)),
        ('trailing comma', b'{"nodes":[],"edges":[],}'),
        ('invalid UTF-8', b'\xff'),
        ('UTF-8 BOM', b'\xef\xbb\xbf' + encode(empty)),
        ('duplicate key', b'{"nodes":[],"nodes":[],"edges":[]}'),
        ('escaped duplicate key', b'{"nodes":[],"no\\u0064es":[],"edges":[]}'),
        ('nested duplicate key', b'{"nodes":[{"x":1,"x":2}],"edges":[]}'),
        ('NaN', b'{"nodes":NaN,"edges":[]}'),
        ('Infinity', b'{"nodes":[],"edges":Infinity}'),
        ('negative Infinity', b'{"nodes":[],"edges":-Infinity}'),
        ('numeric overflow', b'{"nodes":[1e999],"edges":[]}'),
        ('deep invalid JSON value', b'[' * 1500 + b'0' + b']' * 1500),
        ('raw control character', b'{"nodes":["a\x00"],"edges":[]}')]
    wrong_requests = [
        None, [], True, 4, 'request', {}, {'nodes': []}, {'edges': []},
        {'nodes': [], 'edges': [], 'extra': 0},
        {'nodes': None, 'edges': []}, {'nodes': {}, 'edges': []},
        {'nodes': 'a', 'edges': []}, {'nodes': [], 'edges': None},
        {'nodes': [], 'edges': {}}, {'nodes': [], 'edges': 'edge'}]
    for node in ['', 'A', '_a', '0a', 'a-b', 'a b', 'a\n', 'é',
                 'a' * 17, '\ud800', 1, True, None, [], {}]:
        wrong_requests.append({'nodes': [node], 'edges': []})
    wrong_requests.append({'nodes': ['a', 'a'], 'edges': []})
    for edge in [[], ['a'], ['a', 'b', 'a'], 'ab', None, {},
                 [1, 'b'], ['a', True], [[], 'b'], ['a', {}],
                 ['unknown', 'b'], ['a', 'unknown'], ['a', 'a']]:
        wrong_requests.append({'nodes': ['a', 'b'], 'edges': [edge]})
    wrong_requests.extend([
        {'nodes': ['a', 'b'], 'edges': [['a', 'b'], ['b', 'a']]},
        {'nodes': ['a', 'b', 'c', 'z'],
         'edges': [['a', 'b'], ['b', 'c'], ['c', 'a']]},
        {'nodes': [], 'edges': [['a', 'b']]}])
    bad.extend(('invalid structure ' + str(index), encode(request))
               for index, request in enumerate(wrong_requests))
    prefix = encode(examples[0][0]) + b'\n'
    for label, raw in bad:
        invalid(raw, label)
        invalid(prefix + raw, 'valid prefix then ' + label)
    invalid(encode(empty) + b'\n\n' + encode(empty), 'blank middle request')
    invalid(encode(empty) + b'\n{\n' + encode(empty), 'invalid middle request')

    names = ['n' + str(index).zfill(3) for index in range(120)]
    large_edges = [[names[i], names[j]] for i in range(120)
                   for j in range(i + 1, 120)][:2000]
    large = {'nodes': names[::-1], 'edges': large_edges}
    # For this graph the first nodes form a chain through every node.
    # Derive its expected rounds by the independent predecessor-set rule;
    # its lexicographic order is names because all edges point forward.
    remaining = set(names)
    parents = {node: set() for node in names}
    for source, target in large_edges:
        parents[target].add(source)
    large_layers = []
    while remaining:
        current = sorted(node for node in remaining
                         if parents[node].isdisjoint(remaining))
        require(bool(current), 'large reference progress')
        large_layers.append(current)
        remaining.difference_update(current)
    large_expected = {'order': names, 'layers': large_layers,
                      'roots': large_layers[0]}
    valid(encode(large), [large_expected], '120 nodes and 2000 distinct edges')
    invalid(encode({'nodes': names + ['overflow'], 'edges': []}), '121 nodes')
    repeated = {'nodes': ['a', 'b'], 'edges': [['a', 'b']] * 2000}
    repeated_expected = {'order': ['a', 'b'], 'layers': [['a'], ['b']],
                         'roots': ['a']}
    valid(encode(repeated), [repeated_expected], '2000 duplicate entries')
    repeated['edges'].append(['a', 'b'])
    invalid(encode(repeated), '2001 duplicate entries')
    large['edges'].append([names[-2], names[-1]])
    invalid(encode(large), '2001 edge entries')
    name_request = {'nodes': ['a' * 16, 'a0_'], 'edges': []}
    valid(encode(name_request), [oracle(name_request['nodes'], [])], 'valid name bounds')
    base = encode(empty)
    exact = base + b' ' * (131072 - len(base))
    valid(exact, [empty_output], 'exact byte limit')
    invalid(exact + b' ', 'over byte limit')
    valid(base + b' ' * (131071 - len(base)) + b'\n',
          [empty_output], 'exact byte limit with newline')

    # Exhaust every loop-free directed graph on up to four named nodes.
    # The permutation oracle does not use Kahn's algorithm or production helpers.
    pending = []
    expected_pending = []
    for size in range(5):
        nodes = list('abcd'[:size])
        possible = [(source, target) for source in nodes for target in nodes
                    if source != target]
        for mask in range(1 << len(possible)):
            edges = [list(edge) for index, edge in enumerate(possible)
                     if mask & (1 << index)]
            if edges and mask % 17 == 0:
                edges.append(edges[0][:])
            request = {'nodes': nodes[::-1], 'edges': edges[::-1]}
            original = copy.deepcopy(request)
            expected = oracle(nodes, edges)
            COUNTS['graph_cases'] += 1
            label = 'graph size=' + str(size) + ' mask=' + str(mask)
            if expected is None:
                try:
                    plan(request)
                except invalid_type:
                    pass
                else:
                    require(False, label + ': cycle rejection')
            else:
                require(plan(request) == expected, label + ': independent oracle')
                pending.append(encode(request))
                expected_pending.append(expected)
                if len(pending) == 200:
                    valid(b'\n'.join(pending) + b'\n', expected_pending,
                          'exhaustive valid graph batch')
                    pending = []
                    expected_pending = []
            require(request == original, label + ': unchanged input graph')
    if pending:
        valid(b'\n'.join(pending) + b'\n', expected_pending,
              'final exhaustive valid graph batch')
    require(COUNTS['graph_cases'] == 4166, 'exhaustive graph case count')


if __name__ == '__main__':
    try:
        exercise()
    except AssertionError as error:
        sys.stderr.write(json.dumps({'status': 'failed', 'check': str(error),
                                     'counts': COUNTS}, sort_keys=True) + '\n')
        raise SystemExit(1)
    print(json.dumps({'status': 'passed', 'counts': COUNTS}, sort_keys=True))
