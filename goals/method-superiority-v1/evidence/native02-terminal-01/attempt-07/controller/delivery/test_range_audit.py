"""Controles públicos de contrato; ejecutar para obtener observaciones reales."""
import itertools
import json
import subprocess
import sys

PYTHON = '/opt/specorganon/venv/bin/python'
PROGRAM = '/input/delivery/range_audit.py'
LIMIT = 131072
ERROR = b'range-audit: invalid input\n'


def encode(intervals):
    return json.dumps({'intervals': intervals}, separators=(',', ':')).encode()


def oracle(intervals):
    events = {}
    for start, end in intervals:
        events[start] = events.get(start, 0) + 1
        events[end] = events.get(end, 0) - 1
    active = 0
    merged = []
    for point in sorted(events):
        following = active + events[point]
        if active == 0 and following > 0:
            start = point
        if active > 0 and following == 0:
            merged.append([start, point])
        active = following
    return {'merged': merged,
            'covered': sum(b - a for a, b in merged),
            'span': [merged[0][0], merged[-1][1]] if merged else None,
            'gaps': [[merged[i][1], merged[i + 1][0]]
                     for i in range(len(merged) - 1)]}


def same(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return (actual.keys() == expected.keys()
                and all(same(actual[k], expected[k]) for k in expected))
    if isinstance(expected, list):
        return (len(actual) == len(expected)
                and all(same(a, b) for a, b in zip(actual, expected)))
    return actual == expected


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate output key')
        result[key] = value
    return result


def constant(value):
    raise ValueError('invalid output constant')


def cases():
    fixed = []

    def valid(name, requests, raw=None):
        if raw is None:
            raw = b''.join(encode(request) + b'\n' for request in requests)
        fixed.append((name, raw, [oracle(r) for r in requests]))

    def invalid(name, raw):
        fixed.append((name, raw, None))

    examples = [
        ([[1, 3], [3, 7], [10, 12]],
         {'merged': [[1, 7], [10, 12]], 'covered': 8,
          'span': [1, 12], 'gaps': [[7, 10]]}),
        ([[4, 8], [1, 2], [2, 6], [4, 8]],
         {'merged': [[1, 8]], 'covered': 7, 'span': [1, 8], 'gaps': []}),
        ([], {'merged': [], 'covered': 0, 'span': None, 'gaps': []}),
        ([[-5, -2], [0, 1]],
         {'merged': [[-5, -2], [0, 1]], 'covered': 4,
          'span': [-5, 1], 'gaps': [[-2, 0]]})]
    for index, (intervals, expected) in enumerate(examples):
        if not same(oracle(intervals), expected):
            raise ValueError('oracle fixture mismatch')
        fixed.append(('example-%d' % index, encode(intervals) + b'\n', [expected]))
    valid('empty-stdin', [])
    valid('multi-request', [entry[0] for entry in examples])
    valid('eof', [[[2, 9]]], encode([[2, 9]]))
    valid('crlf', [[]], b'{"intervals":[]}\r\n')
    valid('json-whitespace', [[]], b' \t{"intervals":[]} \t\n')
    valid('endpoint-limits', [[[-10**12, 10**12]]])
    valid('separated-limits', [[[-10**12, -10**12 + 1], [10**12 - 1, 10**12]]])
    valid('2000-pairs', [[[i * 2, i * 2 + 1] for i in range(1999, -1, -1)]])
    valid('2000-duplicates', [[[0, 1]] * 2000])
    base = encode([])
    valid('byte-limit', [[]], base + b' ' * (LIMIT - len(base)))
    valid('byte-limit-newline', [[]], base + b' ' * (LIMIT - len(base) - 1) + b'\n')
    invalid('byte-over-limit', base + b' ' * (LIMIT + 1 - len(base)))
    invalid('2001-pairs', encode([[0, 1]] * 2001))
    pool = [[-3, -1], [-1, 2], [0, 1], [2, 4], [5, 7]]
    for size in range(4):
        for index, combo in enumerate(itertools.combinations_with_replacement(pool, size)):
            valid('sweep-%d-%d' % (size, index), [list(reversed(combo))])
    bad = [
        b'\n', b' \t', b'\r\n', b'{', b'null', b'[]', b'1', b'"x"',
        b'{}', b'{"intervals":[],"extra":0}',
        b'{"intervals":[],"intervals":[]}',
        b'{"intervals":[],"extra":{"x":1,"x":2}}',
        b'{"intervals":null}', b'{"intervals":{}}', b'{"intervals":"x"}',
        b'{"intervals":[null]}', b'{"intervals":[{}]}',
        b'{"intervals":[1]}', b'{"intervals":[[]]}',
        b'{"intervals":[[0]]}', b'{"intervals":[[0,1,2]]}',
        b'{"intervals":[[true,2]]}', b'{"intervals":[[0,false]]}',
        b'{"intervals":[[0.0,1]]}', b'{"intervals":[[0,1.0]]}',
        b'{"intervals":[[0,1e0]]}', b'{"intervals":[["0",1]]}',
        b'{"intervals":[[null,1]]}', b'{"intervals":[[0,0]]}',
        b'{"intervals":[[2,1]]}', encode([[-10**12 - 1, 0]]),
        encode([[0, 10**12 + 1]]), b'{"intervals":[[NaN,1]]}',
        b'{"intervals":[[0,Infinity]]}', b'{"intervals":[[-Infinity,1]]}',
        b'{"intervals":[],}', b'{"intervals":[]} trailing',
        b'{"intervals":[]} {"intervals":[]}',
        b'{"intervals":[]}\n\n', b'\n{"intervals":[]}',
        b'{"intervals":[]}\n \n', b'\xff',
        b'{"intervals":[]}\n\xc3\x28',
        b'\xef\xbb\xbf{"intervals":[]}', b'{"intervals":[]}\x00',
        b'{"intervals":[]}\x0b{"intervals":[]}',
        b'{"intervals":[[01,2]]}',
        b'{"intervals":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}']
    for index, raw in enumerate(bad):
        invalid('invalid-%d' % index, raw)
    good = encode([[1, 2]]) + b'\n'
    for index, raw in enumerate([b'{"intervals":[[0,0]]}', b'\xff', b'{', b' ']):
        invalid('atomic-after-%d' % index, good + raw + b'\n')
        invalid('atomic-before-%d' % index, raw + b'\n' + good)
    return fixed


def check(raw, expected):
    completed = subprocess.run([PYTHON, PROGRAM], input=raw,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=10)
    if expected is None:
        if completed.returncode != 2:
            return 'exit'
        if completed.stdout != b'':
            return 'atomic-stdout'
        if completed.stderr != ERROR:
            return 'stderr'
        return None
    if completed.returncode != 0:
        return 'exit'
    if completed.stderr != b'':
        return 'stderr'
    if not expected:
        return None if completed.stdout == b'' else 'empty-stdout'
    if not completed.stdout.endswith(b'\n'):
        return 'newline'
    try:
        lines = completed.stdout.decode('utf-8').split('\n')[:-1]
        if len(lines) != len(expected):
            return 'line-count'
        actual = [json.loads(line, object_pairs_hook=unique,
                             parse_constant=constant) for line in lines]
    except (ValueError, RecursionError):
        return 'output-json'
    return None if same(actual, expected) else 'object-or-integer'


def main():
    try:
        fixed = cases()
    except Exception:
        print('test setup error', file=sys.stderr)
        return 1
    disagreements = 0
    for name, raw, expected in fixed:
        try:
            issue = check(raw, expected)
        except subprocess.TimeoutExpired:
            issue = 'timeout'
        except Exception:
            issue = 'runner-error'
        if issue:
            disagreements += 1
            print('disagreement %s %s' % (name, issue))
    print('contract batches=%d concordant=%d disagreements=%d' %
          (len(fixed), len(fixed) - disagreements, disagreements))
    return 1 if disagreements else 0


if __name__ == '__main__':
    sys.exit(main())
