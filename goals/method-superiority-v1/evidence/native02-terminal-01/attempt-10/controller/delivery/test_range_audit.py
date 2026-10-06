"""Controles públicos de contrato; expectativas independientes del programa."""
import itertools
import json
import subprocess
import sys

PYTHON = '/opt/specorganon/venv/bin/python'
PROGRAM = '/input/delivery/range_audit.py'
cases = 0
failures = []


def encode(intervals):
    return json.dumps({'intervals': intervals}, separators=(',', ':')).encode()


def unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate output key')
        obj[key] = value
    return obj


def exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            exact(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def check(name, raw, expected=None):
    global cases
    cases += 1
    try:
        run = subprocess.run([PYTHON, PROGRAM], input=raw,
                             capture_output=True, timeout=10)
        if expected is None:
            ok = (run.returncode == 2 and run.stdout == b'' and
                  run.stderr == b'range-audit: invalid input\n')
        else:
            ok = run.returncode == 0 and run.stderr == b''
            if expected:
                ok = ok and run.stdout.endswith(b'\n')
                lines = run.stdout.split(b'\n')[:-1]
                ok = ok and len(lines) == len(expected)
                if ok:
                    values = [json.loads(line.decode('utf-8'),
                                         object_pairs_hook=unique)
                              for line in lines]
                    ok = exact(values, expected)
            else:
                ok = ok and run.stdout == b''
        if not ok:
            failures.append(name)
    except Exception as exc:
        failures.append(name + ':' + type(exc).__name__)


def cells(intervals):
    # Independent finite-domain oracle: occupied integer unit cells.
    occupied = sorted({x for a, b in intervals for x in range(a, b)})
    runs = []
    for _, group in itertools.groupby(enumerate(occupied),
                                      lambda pair: pair[1] - pair[0]):
        block = [value for _, value in group]
        runs.append([block[0], block[-1] + 1])
    holes = []
    if occupied:
        missing = sorted(set(range(occupied[0], occupied[-1] + 1))
                         - set(occupied))
        for _, group in itertools.groupby(enumerate(missing),
                                          lambda pair: pair[1] - pair[0]):
            block = [value for _, value in group]
            holes.append([block[0], block[-1] + 1])
    return {'merged': runs, 'covered': len(occupied),
            'span': [occupied[0], occupied[-1] + 1] if occupied else None,
            'gaps': holes}


def main():
    examples = [
        ([[1, 3], [3, 7], [10, 12]],
         {'merged': [[1, 7], [10, 12]], 'covered': 8,
          'span': [1, 12], 'gaps': [[7, 10]]}),
        ([[4, 8], [1, 2], [2, 6], [4, 8]],
         {'merged': [[1, 8]], 'covered': 7, 'span': [1, 8], 'gaps': []}),
        ([], {'merged': [], 'covered': 0, 'span': None, 'gaps': []}),
        ([[-5, -2], [0, 1]],
         {'merged': [[-5, -2], [0, 1]], 'covered': 4,
          'span': [-5, 1], 'gaps': [[-2, 0]]}),
    ]
    for i, (intervals, expected) in enumerate(examples):
        check('example-' + str(i), encode(intervals) + b'\n', [expected])
    check('empty-stdin', b'', [])
    check('multiple', b'\n'.join(encode(x) for x, _ in examples) + b'\n',
          [y for _, y in examples])
    check('no-final-newline', encode(examples[0][0]), [examples[0][1]])
    check('crlf', encode([]) + b'\r\n', [cells([])])
    check('json-whitespace', b' \t{"intervals":[]}\r \n', [cells([])])
    geometries = [[], [[-3, 3]], [[-3, 3], [-1, 1]],
                  [[-4, -2], [-2, 0], [1, 4]],
                  [[-4, 0], [-2, 2], [1, 4]],
                  [[2, 4], [-3, -1], [2, 4], [0, 1]]]
    for i, intervals in enumerate(geometries):
        for j, variant in enumerate((intervals, intervals[::-1],
                                     intervals + intervals)):
            check('geometry-%d-%d' % (i, j), encode(variant), [cells(intervals)])
    pairs = [[-2, -1], [-1, 1], [0, 2], [2, 3]]
    for i, permutation in enumerate(itertools.permutations(pairs)):
        check('permutation-' + str(i), encode(list(permutation)), [cells(pairs)])
    for mask in range(32):
        intervals = [[i - 2, i - 1] for i in range(5) if mask & (1 << i)]
        check('cells-' + str(mask), encode(intervals), [cells(intervals)])
    limit = 10**12
    check('endpoint-limits', encode([[-limit, limit]]),
          [{'merged': [[-limit, limit]], 'covered': 2 * limit,
            'span': [-limit, limit], 'gaps': []}])
    check('large-separated', encode([[limit - 1, limit], [-limit, -limit + 1]]),
          [{'merged': [[-limit, -limit + 1], [limit - 1, limit]],
            'covered': 2, 'span': [-limit, limit],
            'gaps': [[-limit + 1, limit - 1]]}])
    check('2000-pairs', encode([[0, 1]] * 2000), [cells([[0, 1]])])
    check('2001-pairs', encode([[0, 1]] * 2001))
    small = encode([])
    check('131072-bytes', small + b' ' * (131072 - len(small)), [cells([])])
    check('131073-bytes', small + b' ' * (131073 - len(small)))
    invalid = [
        b'\n', b' \t\n', b'{', b'{"intervals":[]} trailing',
        b'{"intervals":[],}', b'{"intervals":[]} {"intervals":[]}',
        b'{}', b'[]', b'null', b'1', b'"intervals"', b'true',
        b'{"intervals":[],"extra":0}',
        b'{"intervals":[],"intervals":[]}',
        b'{"intervals":[],"interv\\u0061ls":[]}',
        b'{"intervals":{"x":1,"x":2}}',
        b'{"intervals":null}', b'{"intervals":{}}',
        b'{"intervals":"[]"}', b'{"intervals":true}',
        b'{"intervals":[[NaN,1]]}',
        b'{"intervals":[[0,Infinity]]}',
        b'{"intervals":[[-Infinity,0]]}',
        b'\xff', b'\xc3', b'\xc0\xaf',
        b'\xef\xbb\xbf{"intervals":[]}',
        small + b'\n\n', small + b'\n \t\n', small + b'\n\xff',
    ]
    bad_pairs = [None, {}, 1, 'pair', [], [0], [0, 1, 2],
                 [True, 2], [0, False], [0.0, 1], [0, 1.0],
                 ['0', 1], [None, 1], [[0], 1], [0, {}],
                 [0, 0], [1, 0], [-limit - 1, 0], [0, limit + 1]]
    invalid.extend(encode([pair]) for pair in bad_pairs)
    for i, raw in enumerate(invalid):
        check('invalid-' + str(i), raw)
    valid = encode([[1, 2]])
    bad = b'{"intervals":[[2,1]]}'
    for position in range(3):
        batch = [valid, valid, valid]
        batch[position] = bad
        check('atomic-' + str(position), b'\n'.join(batch) + b'\n')
    check('deep-json', b'{"intervals":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}')
    check('huge-integer', b'{"intervals":[[0,' + b'9' * 5000 + b']]}')
    print('cases=%d discrepancies=%d' % (cases, len(failures)))
    for name in failures:
        print('FAIL ' + name)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
