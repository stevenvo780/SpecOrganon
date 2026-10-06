import json
import random
import subprocess
import unittest

PYTHON = '/opt/specorganon/venv/bin/python'
PROGRAM = '/input/delivery/range_audit.py'
ERROR = b'range-audit: invalid input\n'


def encode(intervals):
    return json.dumps({'intervals': intervals}, separators=(',', ':')).encode('utf-8')


def result(merged, covered, span, gaps):
    return dict(merged=merged, covered=covered, span=span, gaps=gaps)


def same(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(same(a, b) for a, b in zip(actual, expected))
    return actual == expected


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate output key')
        obj[key] = value
    return obj


def no_constant(value):
    raise ValueError('non-JSON output constant')


def cell_oracle(intervals):
    cells = {x for start, end in intervals for x in range(start, end)}
    if not cells:
        return result([], 0, None, [])
    low, high = min(cells), max(cells) + 1
    runs, holes = [], []
    begin = low
    occupied = True
    for x in range(low + 1, high + 1):
        next_occupied = x in cells
        if next_occupied != occupied:
            (runs if occupied else holes).append([begin, x])
            begin, occupied = x, next_occupied
    return result(runs, len(cells), [low, high], holes)


class ContractTests(unittest.TestCase):
    def check(self, name, raw, expected=None):
        proc = subprocess.run([PYTHON, PROGRAM], input=raw, capture_output=True, timeout=10)
        valid = expected is not None
        expected_code = 0 if valid else 2
        expected_error = b'' if valid else ERROR
        decoded = None
        shape_ok = not proc.stdout
        if valid:
            try:
                rows = proc.stdout.decode('utf-8', errors='strict').split('\n')
                if not proc.stdout:
                    rows = []
                elif rows[-1] == '':
                    rows.pop()
                else:
                    raise ValueError('missing final newline')
                decoded = [json.loads(row, object_pairs_hook=unique_object, parse_constant=no_constant) for row in rows]
                shape_ok = same(decoded, expected)
            except (ValueError, RecursionError):
                shape_ok = False
        matches = proc.returncode == expected_code and proc.stderr == expected_error and shape_ok
        print(json.dumps({'case': name, 'input_hex': raw.hex(), 'expected_objects': expected, 'expected_code': expected_code, 'expected_stderr_hex': expected_error.hex(), 'stdout_hex': proc.stdout.hex(), 'stderr_hex': proc.stderr.hex(), 'returncode': proc.returncode, 'discordant': not matches}, separators=(',', ':')), flush=True)
        self.assertTrue(matches, name)

    def test_public_controls_and_batches(self):
        examples = [
            ([[1, 3], [3, 7], [10, 12]], result([[1, 7], [10, 12]], 8, [1, 12], [[7, 10]])),
            ([[4, 8], [1, 2], [2, 6], [4, 8]], result([[1, 8]], 7, [1, 8], [])),
            ([], result([], 0, None, [])),
            ([[-5, -2], [0, 1]], result([[-5, -2], [0, 1]], 4, [-5, 1], [[-2, 0]])),
        ]
        for i, (intervals, expected) in enumerate(examples):
            with self.subTest(example=i):
                self.check('public-' + str(i), encode(intervals) + b'\n', [expected])
        self.check('empty-stdin', b'', [])
        self.check('batch-lf', b'\n'.join(encode(a) for a, _ in examples) + b'\n', [e for _, e in examples])
        self.check('batch-crlf', b'\r\n'.join(encode(a) for a, _ in examples) + b'\r\n', [e for _, e in examples])
        self.check('no-final-newline', encode(examples[0][0]), [examples[0][1]])
        self.check('json-whitespace', b' \t{"intervals":[]} \t\n', [examples[2][1]])
        self.check('negative-zero', b'{"intervals":[[-0,1]]}', [result([[0, 1]], 1, [0, 1], [])])

    def test_small_independent_oracle(self):
        cases = [[], [[-4, 4], [-2, 2]], [[2, 3], [0, 1]], [[0, 1], [1, 2], [2, 3]], [[-2, 0], [-2, 0], [0, 2]]]
        rng = random.Random(731)
        endpoints = list(range(-8, 9))
        for _ in range(80):
            pairs = []
            for _ in range(rng.randrange(21)):
                a, b = sorted(rng.sample(endpoints, 2))
                pairs.append([a, b])
            cases.append(pairs)
        for i, intervals in enumerate(cases):
            expected = cell_oracle(intervals)
            for label, variant in [('original', intervals), ('reversed', list(reversed(intervals))), ('duplicates', intervals + intervals)]:
                with self.subTest(case=i, variant=label):
                    self.check('cells-' + str(i) + '-' + label, encode(variant), [expected])

    def test_admitted_limits(self):
        limit = 10**12
        self.check('endpoint-limits', encode([[-limit, -limit + 1], [limit - 1, limit]]), [result([[-limit, -limit + 1], [limit - 1, limit]], 2, [-limit, limit], [[-limit + 1, limit - 1]])])
        self.check('exact-large-covered', encode([[-limit, limit]]), [result([[-limit, limit]], 2 * limit, [-limit, limit], [])])
        self.check('2000-pairs', encode([[i * 2, i * 2 + 1] for i in range(2000)]), [result([[i * 2, i * 2 + 1] for i in range(2000)], 2000, [0, 3999], [[i * 2 + 1, i * 2 + 2] for i in range(1999)])])
        self.check('2000-duplicates', encode([[0, 1]] * 2000), [result([[0, 1]], 1, [0, 1], [])])
        base = encode([])
        exact = b' ' * (131072 - len(base)) + base
        self.check('131072-bytes', exact, [result([], 0, None, [])])
        self.check('131073-bytes', b' ' + exact)

    def test_rejections_and_atomicity(self):
        invalid = [
            b'\n', b' ', b'\r\n', b'{', b'{"intervals":[]',
            b'{"intervals":[]} trailing', b'{"intervals":[],}',
            b'{"intervals":[]} {"intervals":[]}', b'[]', b'null', b'1', b'"x"',
            b'{}', b'{"intervals":[],"extra":0}',
            b'{"intervals":[],"intervals":[]}',
            b'{"intervals":[],"inter\\u0076als":[]}',
            b'{"intervals":{}}', b'{"intervals":null}', b'{"intervals":"x"}',
            b'{"intervals":[[0.0,1]]}', b'{"intervals":[[0,1e0]]}',
            b'{"intervals":[[false,1]]}', b'{"intervals":[[0,true]]}',
            b'{"intervals":[["0",1]]}', b'{"intervals":[[null,1]]}',
            b'{"intervals":[[0,NaN]]}', b'{"intervals":[[0,Infinity]]}',
            b'{"intervals":[[-Infinity,1]]}', b'{"intervals":[[0,0]]}',
            b'{"intervals":[[2,1]]}', b'{"intervals":[[]]}',
            b'{"intervals":[[0]]}', b'{"intervals":[[0,1,2]]}',
            b'{"intervals":[0]}', b'{"intervals":[{"x":0,"x":1}]}',
            b'{"intervals":[[0,01]]}', b'{"intervals":[[0,+1]]}',
            b'\xff', b'\xc0\xaf', b'\xef\xbb\xbf{"intervals":[]}',
            b'{"intervals":[]}\n\n', b'{"intervals":[]}\n \n',
            encode([[-10**12 - 1, 0]]), encode([[0, 10**12 + 1]]),
            encode([[0, 1]] * 2001),
            b'{"intervals":[[' + b'9' * 5000 + b',1]]}',
            b'{"intervals":' + b'[' * 1500 + b']' * 1500 + b'}',
        ]
        valid = encode([[1, 2]])
        for i, raw in enumerate(invalid):
            for label, batch in [('alone', raw), ('late', valid + b'\n' + raw), ('early', raw + b'\n' + valid)]:
                with self.subTest(case=i, position=label):
                    self.check('invalid-' + str(i) + '-' + label, batch)


if __name__ == '__main__':
    unittest.main()
