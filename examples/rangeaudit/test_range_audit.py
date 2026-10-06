"""Prospective public contract controls; execution supplies observations."""
import itertools
import json
import subprocess
import unittest

PYTHON = '/opt/specorganon/venv/bin/python'
PROGRAM = '/input/delivery/range_audit.py'
LIMIT = 131072
ENDPOINT = 10**12


def request(intervals):
    return json.dumps({'intervals': intervals}, separators=(',', ':')).encode('utf-8')


def expected(merged, covered, span, gaps):
    return {'merged': merged, 'covered': covered, 'span': span, 'gaps': gaps}


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate output key')
        obj[key] = value
    return obj


def reject_constant(value):
    raise ValueError('non-JSON output constant')


class RangeAuditContract(unittest.TestCase):
    def run_batch(self, raw):
        return subprocess.run([PYTHON, PROGRAM], input=raw,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=10, check=False)

    def assert_exact_types(self, value):
        if isinstance(value, dict):
            for child in value.values():
                self.assert_exact_types(child)
        elif isinstance(value, list):
            for child in value:
                self.assert_exact_types(child)
        elif value is not None:
            self.assertIs(type(value), int)

    def valid(self, raw, outputs):
        result = self.run_batch(raw)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b'')
        if not outputs:
            self.assertEqual(result.stdout, b'')
            return
        self.assertTrue(result.stdout.endswith(b'\n'))
        lines = result.stdout[:-1].split(b'\n')
        self.assertEqual(len(lines), len(outputs))
        for line, wanted in zip(lines, outputs):
            self.assertTrue(line)
            actual = json.loads(line.decode('utf-8'),
                                object_pairs_hook=unique_object,
                                parse_constant=reject_constant)
            self.assertIs(type(actual), dict)
            self.assertEqual(set(actual), {'merged', 'covered', 'span', 'gaps'})
            self.assert_exact_types(actual)
            self.assertEqual(actual, wanted)

    def invalid(self, raw):
        result = self.run_batch(raw)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b'')
        self.assertEqual(result.stderr, b'range-audit: invalid input\n')

    def test_public_contract_controls(self):
        controls = [
            ([[1, 3], [3, 7], [10, 12]],
             expected([[1, 7], [10, 12]], 8, [1, 12], [[7, 10]])),
            ([[4, 8], [1, 2], [2, 6], [4, 8]],
             expected([[1, 8]], 7, [1, 8], [])),
            ([], expected([], 0, None, [])),
            ([[-5, -2], [0, 1]],
             expected([[-5, -2], [0, 1]], 4, [-5, 1], [[-2, 0]])),
        ]
        for intervals, wanted in controls:
            with self.subTest(intervals=intervals):
                self.valid(request(intervals) + b'\n', [wanted])
        self.valid(b'\n'.join(request(x) for x, _ in controls),
                   [y for _, y in controls])

    def test_empty_and_line_terminations(self):
        empty = expected([], 0, None, [])
        self.valid(b'', [])
        self.valid(request([]), [empty])
        self.valid(b'  {"intervals": []} \t\r\n', [empty])
        self.valid(request([]) + b'\n' + request([]) + b'\n', [empty, empty])

    def test_nested_overlapping_and_disjoint(self):
        intervals = [[8, 10], [1, 9], [2, 3], [-9, -7], [-5, -2], [-2, 1]]
        self.valid(request(intervals), [expected(
            [[-9, -7], [-5, 10]], 17, [-9, 10], [[-7, -5]])])

    def test_endpoint_and_interval_limits(self):
        intervals = [[-ENDPOINT, ENDPOINT]]
        self.valid(request(intervals), [expected(
            intervals, 2 * ENDPOINT, [-ENDPOINT, ENDPOINT], [])])
        intervals = [[0, 1]] * 2000
        self.valid(request(intervals), [expected([[0, 1]], 1, [0, 1], [])])
        intervals = [[3 * i, 3 * i + 1] for i in range(2000)]
        wanted = expected(intervals, 2000, [0, 5998],
                          [[3 * i + 1, 3 * i + 3] for i in range(1999)])
        self.valid(request(list(reversed(intervals))), [wanted])
        self.invalid(request([[0, 1]] * 2001))
        for pair in [[-ENDPOINT - 1, 0], [0, ENDPOINT + 1]]:
            with self.subTest(pair=pair):
                self.invalid(request([pair]))

    def test_total_byte_limit(self):
        base = request([])
        wanted = expected([], 0, None, [])
        self.valid(base + b' ' * (LIMIT - len(base)), [wanted])
        self.valid(base + b' ' * (LIMIT - len(base) - 1) + b'\n', [wanted])
        self.invalid(base + b' ' * (LIMIT + 1 - len(base)))
        self.invalid(base + b'\n' + b' ' * LIMIT)

    def test_invalid_json_encoding_and_structure(self):
        cases = [
            b'\n', b' ', b'\t\r\n', b'\r',
            b'{', b'{"intervals":[]', b'{"intervals":[],}',
            b'{"intervals":[]} trailing', b'{"intervals":[]}{}',
            b'{"intervals":[]\x00}', b'\xff',
            b'{"intervals":[]}\xff', b'\xef\xbb\xbf{"intervals":[]}',
            b'{}', b'[]', b'null', b'1', b'true', b'"text"',
            b'{"intervals":[],"extra":0}',
            b'{"intervals":[],"intervals":[]}',
            b'{"intervals":[],"interv\\u0061ls":[]}',
            b'{"intervals":null}', b'{"intervals":{}}',
            b'{"intervals":"[]"}', b'{"intervals":true}',
            b'{"intervals":[null]}', b'{"intervals":[{}]}',
            b'{"intervals":[[1]]}', b'{"intervals":[[1,2,3]]}',
            b'{"intervals":[[true,2]]}', b'{"intervals":[[0,false]]}',
            b'{"intervals":[[1.0,2]]}', b'{"intervals":[[0,2.0]]}',
            b'{"intervals":[[1e0,2]]}', b'{"intervals":[["1",2]]}',
            b'{"intervals":[[null,2]]}', b'{"intervals":[[0,[]]]}',
            b'{"intervals":[[1,1]]}', b'{"intervals":[[2,1]]}',
            b'{"intervals":[[NaN,2]]}', b'{"intervals":[[0,Infinity]]}',
            b'{"intervals":[[-Infinity,2]]}',
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                self.invalid(raw)

    def test_atomic_rejection(self):
        good = request([[1, 3]])
        bad_cases = [b'{}', b'\xff', b'', request([[2, 1]]),
                     request([[0, 1]] * 2001)]
        for bad in bad_cases:
            with self.subTest(bad=bad[:80]):
                self.invalid(good + b'\n' + bad + b'\n')
                self.invalid(bad + b'\n' + good + b'\n')
        self.invalid(good + b'\n\n')
        self.invalid(good + b'\n \n' + good)

    def test_fixed_small_integer_corpus(self):
        # Independent oracle: enumerate covered unit cells, then their runs.
        # The corpus and expectations depend only on fixed integer inputs.
        pairs = list(itertools.combinations(range(-2, 3), 2))
        corpus = [list(combo) for size in range(4)
                  for combo in itertools.combinations_with_replacement(pairs, size)]
        outputs = []
        for intervals in corpus:
            cells = sorted({x for start, end in intervals for x in range(start, end)})
            starts = [x for x in cells if x - 1 not in cells]
            ends = [x + 1 for x in cells if x + 1 not in cells]
            merged = [list(pair) for pair in zip(starts, ends)]
            gaps = [[end, start] for end, start in zip(ends[:-1], starts[1:])]
            span = [cells[0], cells[-1] + 1] if cells else None
            outputs.append(expected(merged, len(cells), span, gaps))
        raw = b'\n'.join(request(list(reversed(x))) for x in corpus) + b'\n'
        self.assertLessEqual(len(raw), LIMIT)
        self.valid(raw, outputs)


if __name__ == '__main__':
    unittest.main()
