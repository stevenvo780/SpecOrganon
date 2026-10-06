#!/usr/bin/env python3
"""Offline CLI checks; no fixtures or third-party dependencies."""
import itertools
import json
import random
import subprocess
import sys

PROGRAM = '/input/delivery/range_audit.py'
COMMAND = [sys.executable, '-I', '-B', '-c',
           'import runpy; runpy.run_path(' + repr(PROGRAM) + ", run_name='__main__')"]
ERROR = b'range-audit: invalid input\n'
checks = 0


def require(condition, label):
    if not condition:
        raise AssertionError(label)


def invoke(raw):
    result = subprocess.run(COMMAND, input=raw, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=10)
    return result.returncode, result.stdout, result.stderr


def encode(intervals):
    return json.dumps({'intervals': intervals}, separators=(',', ':')).encode('utf-8')


def shape(result):
    require(type(result) is dict, 'result must be object')
    require(set(result) == {'merged', 'covered', 'span', 'gaps'}, 'result keys')
    require(type(result['covered']) is int, 'covered integer type')
    for name in ('merged', 'gaps'):
        require(type(result[name]) is list, name + ' list type')
        for pair in result[name]:
            require(type(pair) is list and len(pair) == 2, name + ' pair shape')
            require(all(type(x) is int for x in pair), name + ' endpoint types')
    span = result['span']
    require(span is None or (type(span) is list and len(span) == 2
            and all(type(x) is int for x in span)), 'span shape')


def valid(raw, expected, label):
    global checks
    code, out, err = invoke(raw)
    require(code == 0, label + ': exit')
    require(err == b'', label + ': stderr')
    require((not expected and out == b'') or
            (bool(expected) and out.endswith(b'\n')), label + ': final newline')
    lines = out.split(b'\n')[:-1] if out else []
    require(len(lines) == len(expected), label + ': line count')
    for line, wanted in zip(lines, expected):
        require(bool(line), label + ': empty output line')
        def unique(pairs):
            obj = {}
            for key, value in pairs:
                require(key not in obj, label + ': duplicate output key')
                obj[key] = value
            return obj
        def constant(value):
            raise AssertionError(label + ': nonstandard output constant')
        actual = json.loads(line.decode('utf-8'), object_pairs_hook=unique,
                            parse_constant=constant)
        shape(actual)
        require(actual == wanted, label + ': semantic output')
    checks += 1


def invalid(raw, label):
    global checks
    code, out, err = invoke(raw)
    require(code == 2, label + ': exit')
    require(out == b'', label + ': stdout atomicity')
    require(err == ERROR, label + ': exact stderr')
    checks += 1


def oracle(intervals):
    # Independent small-domain oracle: enumerate covered unit cells, then
    # recover their consecutive components without sorting input intervals.
    cells = set()
    for start, end in intervals:
        cells.update(range(start, end))
    merged = []
    for cell in sorted(cells):
        if merged and merged[-1][1] == cell:
            merged[-1][1] = cell + 1
        else:
            merged.append([cell, cell + 1])
    return {'merged': merged, 'covered': len(cells),
            'span': [min(cells), max(cells) + 1] if cells else None,
            'gaps': [[a[1], b[0]] for a, b in zip(merged, merged[1:])]}


def run():
    empty = {'merged': [], 'covered': 0, 'span': None, 'gaps': []}
    examples = [
        ([[1, 3], [3, 7], [10, 12]],
         {'merged': [[1, 7], [10, 12]], 'covered': 8,
          'span': [1, 12], 'gaps': [[7, 10]]}),
        ([[4, 8], [1, 2], [2, 6], [4, 8]],
         {'merged': [[1, 8]], 'covered': 7, 'span': [1, 8], 'gaps': []}),
        ([], empty),
        ([[-5, -2], [0, 1]],
         {'merged': [[-5, -2], [0, 1]], 'covered': 4,
          'span': [-5, 1], 'gaps': [[-2, 0]]})]
    for index, (pairs, expected) in enumerate(examples):
        valid(encode(pairs) + b'\n', [expected], 'public example ' + str(index))
    valid(b'', [], 'zero-byte input')
    valid(encode([]), [empty], 'unterminated last line')
    valid(b' \t{"intervals":[]} \r\n', [empty], 'JSON whitespace CRLF')
    valid(b'{"interv\\u0061ls":[]}\n', [empty], 'escaped valid key')
    valid(b'{"intervals":[[-0,1]]}\n', [oracle([[0, 1]])], 'negative zero')
    valid(b'\r\n'.join(encode(p) for p, _ in examples) + b'\r\n',
          [v for _, v in examples], 'multi-request CRLF')
    valid(b'\n'.join(encode(p) for p, _ in examples),
          [v for _, v in examples], 'multi-request LF no final newline')

    limit = 10**12
    boundary_pairs = [[limit - 1, limit], [-limit, -limit + 1]]
    boundary_result = {'merged': [[-limit, -limit + 1], [limit - 1, limit]],
                       'covered': 2, 'span': [-limit, limit],
                       'gaps': [[-limit + 1, limit - 1]]}
    valid(encode(boundary_pairs), [boundary_result], 'inclusive endpoint bounds')
    valid(encode([[-limit, limit]]),
          [{'merged': [[-limit, limit]], 'covered': 2 * limit,
            'span': [-limit, limit], 'gaps': []}], 'large exact coverage')
    many = [[i, i + 1] for i in reversed(range(2000))]
    valid(encode(many), [{'merged': [[0, 2000]], 'covered': 2000,
                         'span': [0, 2000], 'gaps': []}], '2000 intervals')
    invalid(encode(many + [[0, 1]]), '2001 intervals')
    base = encode([])
    exact = base + b' ' * (131072 - len(base) - 1) + b'\n'
    require(len(exact) == 131072, 'boundary fixture byte length')
    valid(exact, [empty], '131072 bytes')
    invalid(exact + b' ', '131073 bytes')

    structural = [None, True, False, 0, 1.5, 'intervals', [], {},
                  {'intervals': [], 'extra': 0}]
    structural += [{'intervals': x} for x in (None, True, 0, {}, 'x')]
    structural += [{'intervals': [x]} for x in
                   (None, {}, 'x', 1, [], [1], [1, 2, 3])]
    structural += [{'intervals': [[x, 2]]} for x in
                   (True, False, 1.0, '1', None, [], {})]
    structural += [{'intervals': [[0, x]]} for x in
                   (True, False, 2.0, '2', None, [], {})]
    structural += [{'intervals': [[1, 1]]}, {'intervals': [[2, 1]]},
                   {'intervals': [[-limit - 1, 0]]},
                   {'intervals': [[0, limit + 1]]}]
    for index, obj in enumerate(structural):
        invalid(json.dumps(obj).encode('utf-8'), 'schema case ' + str(index))

    malformed = [b'\n', b'\r\n', b' ', b'\t', b'\n' + base,
                 base + b'\n\n', base + b'\n \n', base + b'\n\n' + base,
                 b'\xff', b'\xc0\xaf', b'\xe2\x82', b'\xed\xa0\x80',
                 b'\xef\xbb\xbf' + base,
                 b'{"intervals":[],"intervals":[]}',
                 b'{"intervals":[],"interv\\u0061ls":[]}',
                 b'{"intervals":[],"x":{"a":1,"a":2}}',
                 b'{"intervals":[[NaN,2]]}', b'{"intervals":[[0,Infinity]]}',
                 b'{"intervals":[[-Infinity,2]]}',
                 b'{"intervals":[[1e0,2]]}', b'{"intervals":[[0,1e999]]}',
                 b'{"intervals":[[01,2]]}', b'{"intervals":[[+1,2]]}',
                 b'{"intervals":[]', b'{"intervals":[],}',
                 b"{'intervals':[]}", base + b' {}', base + b'\r' + base,
                 b'{"intervals":[[0,' + b'9' * 6000 + b']]}',
                 b'{"intervals":' + b'[' * 1800 + b']' * 1800 + b'}',
                 b'\xc2\xa0' + base]
    for index, raw in enumerate(malformed):
        invalid(raw, 'parsing case ' + str(index))
    invalid(encode([[1, 2]]) + b'\n' + b'{"intervals":[[2,2]]}\n',
            'valid then invalid atomicity')
    invalid(b'{}\n' + encode([[1, 2]]) + b'\n', 'invalid then valid atomicity')
    invalid(encode([[1, 2]]) + b'\n\xff\n', 'late UTF-8 error atomicity')

    pairs = [[a, b] for a in range(-2, 3) for b in range(a + 1, 4)]
    cases = [[]] + [[p] for p in pairs]
    cases += [[a, b] for a, b in itertools.product(pairs, repeat=2)]
    rng = random.Random(20261006)
    for _ in range(200):
        batch = []
        for _ in range(rng.randrange(31)):
            a = rng.randrange(-12, 12)
            batch.append([a, rng.randrange(a + 1, 13)])
        cases.append(batch)
        cases.append(list(reversed(batch)))
        cases.append(batch + batch)
    # Bound every property batch, keeping input comfortably below 131072 bytes.
    for offset in range(0, len(cases), 100):
        chunk = cases[offset:offset + 100]
        raw = b'\n'.join(encode(p) for p in chunk) + b'\n'
        require(len(raw) <= 131072, 'property fixture input bound')
        valid(raw, [oracle(p) for p in chunk], 'oracle batch ' + str(offset))
    return len(cases)


def main():
    try:
        requests = run()
    except Exception as exc:
        # Deliberately bounded diagnostics; never print captured stdin/stdout.
        print(json.dumps({'status': 'fail', 'checks_completed': checks,
                          'error_type': type(exc).__name__,
                          'detail': str(exc)[:500]}, separators=(',', ':')))
        return 1
    print(json.dumps({'status': 'pass', 'checks_completed': checks,
                      'oracle_requests': requests}, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
