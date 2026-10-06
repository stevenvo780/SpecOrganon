#!/usr/bin/env python3
"""Fixed, self-contained CLI battery; no external fixtures or test configuration."""
import json
import random
import subprocess
import sys

PROGRAM = '/input/delivery/range_audit.py'
LAUNCH = 'import runpy; runpy.run_path(' + repr(PROGRAM) + ', run_name="__main__")'
ERROR = b'range-audit: invalid input\n'
checks = 0


def require(condition, label):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(label)


def invoke(raw):
    return subprocess.run([sys.executable, '-I', '-B', '-c', LAUNCH],
                          input=raw, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=10, check=False)


def encode(intervals):
    return json.dumps({'intervals': intervals}, separators=(',', ':')).encode('utf-8')


def exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(exact(actual[k], expected[k]) for k in expected)
    if type(expected) is list:
        return len(actual) == len(expected) and all(exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate output key')
        result[key] = value
    return result


def no_constant(value):
    raise ValueError('nonstandard output constant')


def valid(raw, expected, label):
    result = invoke(raw)
    require(result.returncode == 0, label + ': exit')
    require(result.stderr == b'', label + ': stderr')
    if not expected:
        require(result.stdout == b'', label + ': empty output')
        return
    require(result.stdout.endswith(b'\n'), label + ': final newline')
    lines = result.stdout[:-1].split(b'\n')
    require(len(lines) == len(expected), label + ': output count')
    for index, (line, wanted) in enumerate(zip(lines, expected)):
        try:
            actual = json.loads(line.decode('utf-8', errors='strict'),
                                object_pairs_hook=unique, parse_constant=no_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise AssertionError(label + ': malformed output at ' + str(index)) from None
        require(exact(actual, wanted), label + ': semantic result at ' + str(index))


def invalid(raw, label):
    result = invoke(raw)
    require(result.returncode == 2, label + ': exit')
    require(result.stdout == b'', label + ': atomic stdout')
    require(result.stderr == ERROR, label + ': exact stderr')


def cells_oracle(intervals):
    cells = set()
    for start, end in intervals:
        cells.update(range(start, end))
    runs = []
    for cell in sorted(cells):
        if cell - 1 not in cells:
            runs.append([cell, cell + 1])
        else:
            runs[-1][1] = cell + 1
    return {'merged': runs, 'covered': len(cells),
            'span': [min(cells), max(cells) + 1] if cells else None,
            'gaps': [[runs[i][1], runs[i + 1][0]] for i in range(len(runs) - 1)]}


def battery():
    examples = [
        ([[1, 3], [3, 7], [10, 12]],
         {'merged': [[1, 7], [10, 12]], 'covered': 8, 'span': [1, 12], 'gaps': [[7, 10]]}),
        ([[4, 8], [1, 2], [2, 6], [4, 8]],
         {'merged': [[1, 8]], 'covered': 7, 'span': [1, 8], 'gaps': []}),
        ([], {'merged': [], 'covered': 0, 'span': None, 'gaps': []}),
        ([[-5, -2], [0, 1]],
         {'merged': [[-5, -2], [0, 1]], 'covered': 4, 'span': [-5, 1], 'gaps': [[-2, 0]]}),
    ]
    for index, (intervals, expected) in enumerate(examples):
        valid(encode(intervals) + b'\n', [expected], 'example ' + str(index))
    valid(b'', [], 'empty stdin')
    valid(b'\n'.join(encode(pairs) for pairs, _ in examples),
          [expected for _, expected in examples], 'batch without terminal newline')
    valid(b'\r\n'.join(encode(pairs) for pairs, _ in examples) + b'\r\n',
          [expected for _, expected in examples], 'CRLF batch')
    valid(b' \t{"intervals":[]} \t\r\n', [examples[2][1]], 'JSON whitespace')
    valid(b'{"interv\\u0061ls":[[-0,1]]}',
          [{'merged': [[0, 1]], 'covered': 1, 'span': [0, 1], 'gaps': []}], 'escaped key and negative zero')

    rng = random.Random(7621)
    small = [[], [[-4, 4], [-2, 2], [-4, 4]],
             [[3, 4], [-3, -1], [-1, 0], [0, 3]], [[-4, -3], [3, 4]]]
    for _ in range(250):
        pairs = []
        for _ in range(rng.randrange(31)):
            start, end = sorted(rng.sample(range(-12, 13), 2))
            pairs.append([start, end])
        if pairs:
            pairs.extend(pairs[:rng.randrange(min(5, len(pairs)) + 1)])
        rng.shuffle(pairs)
        small.append(pairs)
    valid(b'\n'.join(encode(pairs) for pairs in small) + b'\n',
          [cells_oracle(pairs) for pairs in small], 'finite cell oracle')

    bound = 10**12
    valid(encode([[-bound, bound]]),
          [{'merged': [[-bound, bound]], 'covered': 2 * bound,
            'span': [-bound, bound], 'gaps': []}], 'endpoint inclusive bounds')
    separated = [[2 * i, 2 * i + 1] for i in range(2000)]
    valid(encode(list(reversed(separated))),
          [{'merged': separated, 'covered': 2000, 'span': [0, 3999],
            'gaps': [[2 * i + 1, 2 * i + 2] for i in range(1999)]}], '2000 separated pairs')
    valid(encode([[0, 1]] * 2000),
          [{'merged': [[0, 1]], 'covered': 1, 'span': [0, 1], 'gaps': []}], '2000 duplicate pairs')
    invalid(encode([[0, 1]] * 2001), '2001 pairs')

    base = encode([])
    exact_size = base + b' ' * (131072 - len(base))
    require(len(exact_size) == 131072, 'size fixture length')
    valid(exact_size, [examples[2][1]], 'inclusive byte bound')
    invalid(exact_size + b' ', 'exceeded byte bound')
    unit = base + b'\n'
    count, remainder = divmod(131072, len(unit))
    many = unit * (count - 1) + base + b' ' * remainder + b'\n'
    require(len(many) == 131072, 'many-request fixture length')
    valid(many, [examples[2][1]] * count, 'many requests at byte bound')

    bad_objects = [None, True, 0, 'request', [], {}, {'intervals': [], 'extra': 1},
                   {'intervals': None}, {'intervals': {}}, {'intervals': 'pairs'},
                   {'intervals': True}]
    bad_pairs = [None, {}, 'pair', 3, [], [0], [0, 1, 2],
                 [False, 1], [0, True], [0.0, 1], [0, 1.0],
                 ['0', 1], [0, '1'], [None, 1], [0, None],
                 [[], 1], [0, {}], [0, 0], [2, 1],
                 [-bound - 1, 0], [0, bound + 1],
                 [bound, bound + 1], [-bound - 1, -bound]]
    bad_objects.extend({'intervals': [pair]} for pair in bad_pairs)
    bad = [json.dumps(obj, separators=(',', ':')).encode('utf-8') for obj in bad_objects]
    bad.extend([
        b'{"intervals":[],"intervals":[]}',
        b'{"intervals":[],"interv\\u0061ls":[]}',
        b'{"intervals":[],"x":{"a":1,"a":2}}',
        b'{"intervals":[[NaN,1]]}', b'{"intervals":[[0,Infinity]]}',
        b'{"intervals":[[-Infinity,0]]}', b'{"intervals":[[0,1e0]]}',
        b'{"intervals":[[00,1]]}', b'{"intervals":[[+0,1]]}',
        b'{"intervals":[],}', b'{"intervals":[]', b'{"intervals":[]} {}',
        b'{"intervals":[]}#comment', b'{"intervals":[]}\x00',
        b'{"intervals":[]}\xff', b'{"intervals":[]}\xc0\xaf',
        b'{"intervals":[]}\xe2\x82', b'{"intervals":[]}\xed\xa0\x80',
        b'\xef\xbb\xbf{"intervals":[]}', b'\x00{\x00}',
        b'\n', b' \t\r', b'\r\n', b'\n{"intervals":[]}',
        b'{"intervals":[]}\n\n', b'{"intervals":[]}\n \t\n',
        b'{"intervals":[]}\v', b'{"intervals":[]}\f',
        '{"intervals":[]}\u00a0'.encode('utf-8'),
        b'{"intervals":[' + b'[' * 1500 + b'0' + b']' * 1500 + b']}',
        b'{"intervals":[[' + b'9' * 5000 + b',1]]}',
    ])
    good_line = base + b'\n'
    for index, raw in enumerate(bad):
        label = 'rejection ' + str(index)
        invalid(raw, label)
        invalid(good_line + raw, label + ' after valid')
        invalid(raw + b'\n' + base, label + ' before valid')


if __name__ == '__main__':
    try:
        battery()
    except Exception as error:
        # Controlled diagnostics avoid dumping potentially large child streams.
        # Every check failure exits nonzero; neither failures nor timeouts are ignored.
        if isinstance(error, AssertionError):
            detail = str(error)
        else:
            detail = type(error).__name__
        print(json.dumps({'status': 'fail', 'checks_completed': checks, 'detail': detail}))
        raise SystemExit(1)
    print(json.dumps({'status': 'pass', 'checks_completed': checks}))
