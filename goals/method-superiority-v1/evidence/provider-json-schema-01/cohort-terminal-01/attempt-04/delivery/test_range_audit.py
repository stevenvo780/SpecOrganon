import json
import random
import subprocess
import unittest

PYTHON = '/opt/specorganon/venv/bin/python'
PROGRAM = '/input/delivery/range_audit.py'
LIMIT = 131072
EDGE = 10 ** 12
ERROR = b'range-audit: invalid input\n'


def request(intervals):
    return json.dumps({'intervals': intervals}, separators=(',', ':')).encode('utf-8')


def oracle(intervals):
    # Independently mark elementary segments between distinct endpoints.
    points = sorted({value for pair in intervals for value in pair})
    runs = []
    for left, right in zip(points, points[1:]):
        if any(start <= left and right <= end for start, end in intervals):
            if runs and runs[-1][1] == left:
                runs[-1][1] = right
            else:
                runs.append([left, right])
    return {'merged': runs,
            'covered': sum(right - left for left, right in runs),
            'span': [points[0], points[-1]] if points else None,
            'gaps': [[a[1], b[0]] for a, b in zip(runs, runs[1:])]}


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate output key')
        obj[key] = value
    return obj


def reject_constant(value):
    raise ValueError('nonstandard output constant')


class RangeAuditTests(unittest.TestCase):
    def invoke(self, raw):
        return subprocess.run([PYTHON, PROGRAM], input=raw,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=10, check=False)

    def assert_exact(self, actual, expected):
        self.assertIs(type(actual), type(expected))
        if isinstance(expected, dict):
            self.assertEqual(set(actual), set(expected))
            for key in expected:
                self.assert_exact(actual[key], expected[key])
        elif isinstance(expected, list):
            self.assertEqual(len(actual), len(expected))
            for left, right in zip(actual, expected):
                self.assert_exact(left, right)
        else:
            self.assertEqual(actual, expected)

    def valid(self, raw, expected):
        proc = self.invoke(raw)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, b'')
        if not expected:
            self.assertEqual(proc.stdout, b'')
            return
        self.assertTrue(proc.stdout.endswith(b'\n'))
        lines = proc.stdout[:-1].split(b'\n')
        self.assertEqual(len(lines), len(expected))
        for line, wanted in zip(lines, expected):
            actual = json.loads(line.decode('utf-8'),
                                object_pairs_hook=unique_object,
                                parse_constant=reject_constant)
            self.assert_exact(actual, wanted)

    def invalid(self, raw):
        proc = self.invoke(raw)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, b'')
        self.assertEqual(proc.stderr, ERROR)

    def test_public_contract_controls(self):
        cases = [
            ([[1, 3], [3, 7], [10, 12]],
             {'merged': [[1, 7], [10, 12]], 'covered': 8,
              'span': [1, 12], 'gaps': [[7, 10]]}),
            ([[4, 8], [1, 2], [2, 6], [4, 8]],
             {'merged': [[1, 8]], 'covered': 7,
              'span': [1, 8], 'gaps': []}),
            ([], {'merged': [], 'covered': 0, 'span': None, 'gaps': []}),
            ([[-5, -2], [0, 1]],
             {'merged': [[-5, -2], [0, 1]], 'covered': 4,
              'span': [-5, 1], 'gaps': [[-2, 0]]})]
        for intervals, expected in cases:
            for suffix in (b'', b'\n'):
                with self.subTest(intervals=intervals, suffix=suffix):
                    self.valid(request(intervals) + suffix, [expected])
        self.valid(b'\n'.join(request(i) for i, _ in cases) + b'\n',
                   [expected for _, expected in cases])

    def test_empty_input_and_legal_whitespace(self):
        self.valid(b'', [])
        empty = oracle([])
        self.valid(b'  { "intervals" : [] } \r\n', [empty])
        self.valid(b'{"intervals":[]}\n{"intervals":[]}', [empty, empty])
        self.valid(b'{"interv\\u0061ls":[]}', [empty])

    def test_normalization_and_exact_extremes(self):
        cases = [
            [[8, 10], [1, 4], [2, 3], [4, 8], [1, 4]],
            [[5, 6], [-8, -4], [-3, 0], [0, 2]],
            [[-EDGE, EDGE]],
            [[EDGE - 1, EDGE], [-EDGE, -EDGE + 1]],
            [[-EDGE, -1], [-1, 0], [0, EDGE]],
            [[-0, 1]],
            [[1, 2]] * 2000]
        for intervals in cases:
            with self.subTest(intervals=intervals[:8], count=len(intervals)):
                self.valid(request(intervals), [oracle(intervals)])

    def test_seeded_segment_oracle(self):
        rng = random.Random(617)
        cases = []
        for _ in range(40):
            intervals = []
            for _ in range(rng.randrange(0, 30)):
                left, right = sorted(rng.sample(range(-30, 31), 2))
                intervals.append([left, right])
            if intervals:
                intervals += intervals[:3]
            rng.shuffle(intervals)
            cases.append(intervals)
        self.valid(b'\n'.join(request(i) for i in cases) + b'\n',
                   [oracle(i) for i in cases])

    def test_byte_limit(self):
        base = request([])
        exact = base + b' ' * (LIMIT - len(base) - 1) + b'\n'
        self.assertEqual(len(exact), LIMIT)
        self.valid(exact, [oracle([])])
        self.invalid(exact + b' ')
        # A valid prefix must not be emitted when the entire batch is oversized.
        self.invalid(base + b'\n' + exact)

    def test_invalid_inputs_and_atomic_batches(self):
        malformed = [
            b'\n', b' ', b'\t\r\n', b'{"intervals":[]}\n\n',
            b'\n{"intervals":[]}', b'{', b'{"intervals":[]',
            b'{"intervals":[],}', b'{"intervals":[]} trailing',
            b'{"intervals":[]}{"intervals":[]}', b'\xff',
            b'{"intervals":[]}\n\xc3', b'\xef\xbb\xbf{"intervals":[]}',
            b'{"intervals":[],"intervals":[]}',
            b'{"intervals":[],"interv\\u0061ls":[]}',
            b'{"intervals":[],"extra":{"x":1,"x":2}}',
            b'{"intervals":NaN}', b'{"intervals":[[0,Infinity]]}',
            b'{"intervals":[[-Infinity,1]]}',
            b'{"intervals":[[0,01]]}', b'{"intervals":[[0,1e309]]}',
            b'{"intervals":[[0,1]]}\x00']
        invalid_objects = [
            None, True, 1, [], 'text', {}, {'extra': []},
            {'intervals': [], 'extra': 0},
            {'intervals': None}, {'intervals': {}}, {'intervals': '[]'},
            {'intervals': [None]}, {'intervals': [{}]},
            {'intervals': ['01']}, {'intervals': [[]]},
            {'intervals': [[0]]}, {'intervals': [[0, 1, 2]]},
            {'intervals': [[True, 2]]}, {'intervals': [[0, False]]},
            {'intervals': [[0.0, 1]]}, {'intervals': [[0, 1.0]]},
            {'intervals': [['0', 1]]}, {'intervals': [[0, None]]},
            {'intervals': [[[0], 1]]}, {'intervals': [[0, {}]]},
            {'intervals': [[1, 1]]}, {'intervals': [[2, 1]]},
            {'intervals': [[-EDGE - 1, 0]]},
            {'intervals': [[0, EDGE + 1]]},
            {'intervals': [[EDGE + 1, EDGE + 2]]},
            {'intervals': [[-EDGE - 2, -EDGE - 1]]},
            {'intervals': [[0, 1]] * 2001}]
        malformed += [json.dumps(obj, separators=(',', ':')).encode('utf-8')
                      for obj in invalid_objects]
        good = request([[1, 3]])
        for index, raw in enumerate(malformed):
            with self.subTest(case=index, placement='alone'):
                self.invalid(raw)
            with self.subTest(case=index, placement='after_valid'):
                self.invalid(good + b'\n' + raw)
            with self.subTest(case=index, placement='before_valid'):
                self.invalid(raw + b'\n' + good)


if __name__ == '__main__':
    unittest.main()
