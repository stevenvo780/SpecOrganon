import json
import subprocess
import unittest

PYTHON = '/opt/specorganon/venv/bin/python'
PROGRAM = '/input/delivery/range_audit.py'
ERROR = b'range-audit: invalid input\n'
EMPTY = {'merged': [], 'covered': 0, 'span': None, 'gaps': []}


def request(intervals):
    return json.dumps({'intervals': intervals}, separators=(',', ':')).encode('utf-8')


def reject_number(value):
    raise ValueError('noninteger output number')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate output key')
        result[key] = value
    return result


class RangeAuditContract(unittest.TestCase):
    def invoke(self, payload):
        return subprocess.run([PYTHON, PROGRAM], input=payload,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=5, check=False)

    def assert_exact_types(self, value):
        if isinstance(value, dict):
            for key, child in value.items():
                self.assertIs(type(key), str)
                self.assert_exact_types(child)
        elif isinstance(value, list):
            for child in value:
                self.assert_exact_types(child)
        elif value is not None:
            self.assertIs(type(value), int)

    def valid(self, payload, expected):
        proc = self.invoke(payload)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, b'')
        if not expected:
            self.assertEqual(proc.stdout, b'')
            return
        self.assertTrue(proc.stdout.endswith(b'\n'))
        lines = proc.stdout[:-1].split(b'\n')
        self.assertEqual(len(lines), len(expected))
        for line, wanted in zip(lines, expected):
            actual = json.loads(line.decode('utf-8', errors='strict'),
                                parse_float=reject_number,
                                parse_constant=reject_number,
                                object_pairs_hook=unique_object)
            self.assertIs(type(actual), dict)
            self.assertEqual(set(actual), {'merged', 'covered', 'span', 'gaps'})
            self.assert_exact_types(actual)
            self.assertEqual(actual, wanted)

    def invalid(self, payload):
        proc = self.invoke(payload)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, b'')
        self.assertEqual(proc.stderr, ERROR)

    def test_valid_contract_cases(self):
        cases = [
            ([[1, 3], [3, 7], [10, 12]],
             {'merged': [[1, 7], [10, 12]], 'covered': 8,
              'span': [1, 12], 'gaps': [[7, 10]]}),
            ([[4, 8], [1, 2], [2, 6], [4, 8]],
             {'merged': [[1, 8]], 'covered': 7, 'span': [1, 8], 'gaps': []}),
            ([], EMPTY),
            ([[-5, -2], [0, 1]],
             {'merged': [[-5, -2], [0, 1]], 'covered': 4,
              'span': [-5, 1], 'gaps': [[-2, 0]]}),
            ([[10, 12], [4, 5], [0, 1]],
             {'merged': [[0, 1], [4, 5], [10, 12]], 'covered': 4,
              'span': [0, 12], 'gaps': [[1, 4], [5, 10]]}),
            ([[2, 3], [1, 10], [4, 9], [1, 10]],
             {'merged': [[1, 10]], 'covered': 9, 'span': [1, 10], 'gaps': []}),
            ([[0, 2], [-2, 0], [2, 4]],
             {'merged': [[-2, 4]], 'covered': 6, 'span': [-2, 4], 'gaps': []}),
            ([[-10**12, 10**12]],
             {'merged': [[-10**12, 10**12]], 'covered': 2 * 10**12,
              'span': [-10**12, 10**12], 'gaps': []}),
            ([[-10**12, -10**12 + 1], [10**12 - 1, 10**12]],
             {'merged': [[-10**12, -10**12 + 1], [10**12 - 1, 10**12]],
              'covered': 2, 'span': [-10**12, 10**12],
              'gaps': [[-10**12 + 1, 10**12 - 1]]}),
            ([[1, 2]] * 2000,
             {'merged': [[1, 2]], 'covered': 1, 'span': [1, 2], 'gaps': []})
        ]
        self.valid(b'', [])
        for index, (intervals, wanted) in enumerate(cases):
            for ending in (b'', b'\n'):
                with self.subTest(case=index, ending=ending):
                    self.valid(request(intervals) + ending, [wanted])
        self.valid(b'\n'.join(request(intervals) for intervals, _ in cases) + b'\n',
                   [wanted for _, wanted in cases])
        self.valid(b' \t{"intervals":[]} \r\n', [EMPTY])
        self.valid(b'{"interv\\u0061ls":[]}\n', [EMPTY])
        base = request([])
        for ending in (b'', b'\n'):
            payload = base + b' ' * (131072 - len(base) - len(ending)) + ending
            self.assertEqual(len(payload), 131072)
            self.valid(payload, [EMPTY])

    def test_invalid_contract_cases(self):
        cases = [
            b'\n', b' ', b'\t\n', b'\r\n', b'\n\n',
            b'{', b'{"intervals":[]', b'{"intervals":[],}',
            b'{"intervals":[]} garbage', b'{"intervals":[]}{"intervals":[]}',
            b'{}', b'[]', b'null', b'true', b'1', b'"text"',
            b'{"intervals":[],"extra":0}',
            b'{"intervals":[],"intervals":[]}',
            b'{"intervals":[],"interv\\u0061ls":[]}',
            b'{"intervals":[{"x":1,"x":2}]}',
            b'{"intervals":null}', b'{"intervals":{}}',
            b'{"intervals":true}', b'{"intervals":"pairs"}',
            b'{"intervals":[1]}', b'{"intervals":[null]}',
            b'{"intervals":[{}]}', b'{"intervals":[[]]}',
            b'{"intervals":[[1]]}', b'{"intervals":[[1,2,3]]}',
            b'{"intervals":[[true,2]]}', b'{"intervals":[[0,false]]}',
            b'{"intervals":[[1.0,2]]}', b'{"intervals":[[1,2.0]]}',
            b'{"intervals":[[1e0,2]]}', b'{"intervals":[["1",2]]}',
            b'{"intervals":[[1,null]]}', b'{"intervals":[[[],2]]}',
            b'{"intervals":[[NaN,2]]}', b'{"intervals":[[1,Infinity]]}',
            b'{"intervals":[[-Infinity,2]]}',
            request([[1, 1]]), request([[2, 1]]),
            request([[-10**12 - 1, 0]]), request([[0, 10**12 + 1]]),
            request([[10**12 + 1, 10**12 + 2]]),
            request([[-10**12 - 2, -10**12 - 1]]),
            request([[1, 2]] * 2001),
            b'\xff', b'{"intervals":[]}\n\xc3',
            b'\xef\xbb\xbf{"intervals":[]}',
            b'{"intervals":[]}\n\n',
            b'{"intervals":[]}\n \n',
            b'{"intervals":[]}\r{"intervals":[]}',
            request([]) + b' ' * (131073 - len(request([]))),
            b' ' * 131073
        ]
        for index, payload in enumerate(cases):
            with self.subTest(case=index):
                self.invalid(payload)
        good = request([[1, 3]])
        bad_cases = [b'{"intervals":[[2,1]]}', b'{', b' ',
                     b'{"intervals":[],"intervals":[]}', b'\xff']
        for bad in bad_cases:
            with self.subTest(atomic=bad):
                self.invalid(good + b'\n' + bad + b'\n')
                self.invalid(bad + b'\n' + good + b'\n')
                self.invalid(good + b'\n' + good + b'\n' + bad)


if __name__ == '__main__':
    unittest.main()
