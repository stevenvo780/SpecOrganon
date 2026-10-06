import json
import subprocess
import unittest

PYTHON = '/opt/specorganon/venv/bin/python'
PROGRAM = '/input/delivery/ledger_fold.py'
EMPTY = {'balances': {}, 'total': 0, 'count': 0, 'zero_accounts': []}
VALID = b'{"entries":[]}\n'


def encode(entries):
    return json.dumps({'entries': entries}, separators=(',', ':')).encode('utf-8')


def movement(account, delta):
    return {'account': account, 'delta': delta}


class LedgerFoldContract(unittest.TestCase):
    def invoke(self, raw):
        return subprocess.run([PYTHON, PROGRAM], input=raw, capture_output=True, timeout=10)

    def valid(self, raw, expected):
        p = self.invoke(raw)
        detail = repr((raw, p.returncode, p.stdout, p.stderr))
        self.assertEqual(p.returncode, 0, detail)
        self.assertEqual(p.stderr, b'', detail)
        if not expected:
            self.assertEqual(p.stdout, b'', detail)
            return
        self.assertTrue(p.stdout.endswith(b'\n'), detail)
        lines = p.stdout[:-1].split(b'\n')
        self.assertEqual(len(lines), len(expected), detail)
        def unique(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise AssertionError('duplicate output key: ' + key)
                obj[key] = value
            return obj
        for line, wanted in zip(lines, expected):
            obj = json.loads(line.decode('utf-8'), object_pairs_hook=unique)
            self.assertEqual(obj, wanted, detail)
            self.assertIs(type(obj['total']), int, detail)
            self.assertIs(type(obj['count']), int, detail)
            self.assertIs(type(obj['balances']), dict, detail)
            self.assertIs(type(obj['zero_accounts']), list, detail)
            for value in obj['balances'].values():
                self.assertIs(type(value), int, detail)

    def invalid(self, raw):
        p = self.invoke(raw)
        self.assertEqual((p.returncode, p.stdout, p.stderr),
                         (2, b'', b'ledger-fold: invalid input\n'),
                         repr((raw, p.returncode, p.stdout, p.stderr)))

    def test_valid_cases(self):
        long_account = 'a' + '0' * 31
        cases = [
            ('empty stdin', b'', []),
            ('empty entries', VALID, [EMPTY]),
            ('no final newline', VALID[:-1], [EMPTY]),
            ('multiple lines', VALID * 2, [EMPTY, EMPTY]),
            ('crlf', b'{"entries":[]}\r\n', [EMPTY]),
            ('whitespace', b' \t{"entries": []}\t \n', [EMPTY]),
            ('example cancellation', encode([movement('cash', 7), movement('cash', -7), movement('bank', 3)]) + b'\n',
             [{'balances': {'cash': 0, 'bank': 3}, 'total': 3, 'count': 3, 'zero_accounts': ['cash']}]),
            ('unbounded sum', encode([movement('a', 10**12)] * 2),
             [{'balances': {'a': 2 * 10**12}, 'total': 2 * 10**12, 'count': 2, 'zero_accounts': []}]),
            ('negative sum', encode([movement('a', -10**12)] * 2),
             [{'balances': {'a': -2 * 10**12}, 'total': -2 * 10**12, 'count': 2, 'zero_accounts': []}]),
            ('zero order and duplicates', encode([movement('z', 0), movement('b', 2), movement('a', -3), movement('b', -2), movement('a', 3), movement('z', 0)]),
             [{'balances': {'z': 0, 'b': 0, 'a': 0}, 'total': 0, 'count': 6, 'zero_accounts': ['a', 'b', 'z']}]),
            ('account boundaries', encode([movement('a', 1), movement(long_account, -1), movement('a_0', 0)]),
             [{'balances': {'a': 1, long_account: -1, 'a_0': 0}, 'total': 0, 'count': 3, 'zero_accounts': ['a_0']}]),
            ('exact integer beyond float precision', encode([movement('a', 10**12)] * 2000),
             [{'balances': {'a': 2000 * 10**12}, 'total': 2000 * 10**12, 'count': 2000, 'zero_accounts': []}]),
            ('byte limit', VALID[:-1] + b' ' * (131072 - len(VALID)) + b'\n', [EMPTY]),
        ]
        for name, raw, expected in cases:
            with self.subTest(case=name):
                self.valid(raw, expected)

    def test_invalid_cases_and_atomicity(self):
        cases = [
            ('blank', b'\n'), ('spaces', b' \t\r\n'),
            ('extra blank line', VALID + b'\n'),
            ('malformed', b'{'), ('trailing data', b'{"entries":[]}x'),
            ('two objects on line', VALID[:-1] * 2),
            ('trailing comma', b'{"entries":[],}'),
            ('root list', b'[]'), ('root null', b'null'),
            ('missing entries', b'{}'), ('extra field', b'{"entries":[],"x":0}'),
            ('entries null', b'{"entries":null}'),
            ('entries object', b'{"entries":{}}'),
            ('entries string', b'{"entries":""}'),
            ('entry scalar', b'{"entries":[1]}'),
            ('entry array', b'{"entries":[[]]}'),
            ('entry missing account', b'{"entries":[{"delta":0}]}'),
            ('entry missing delta', b'{"entries":[{"account":"a"}]}'),
            ('entry extra field', b'{"entries":[{"account":"a","delta":0,"x":0}]}'),
            ('duplicate root', b'{"entries":[],"entries":[]}'),
            ('duplicate account', b'{"entries":[{"account":"a","account":"b","delta":1}]}'),
            ('duplicate delta', b'{"entries":[{"account":"a","delta":1,"delta":2}]}'),
            ('escaped duplicate key', b'{"entries":[],"\u0065ntries":[]}'),
            ('duplicate deeper object', b'{"entries":[{"account":"a","delta":{"x":1,"x":2}}]}'),
            ('invalid utf8', VALID + b'\xff'),
            ('truncated utf8', b'{"entries":[]}\xc3'),
            ('bom', b'\xef\xbb\xbf' + VALID),
            ('too many entries', encode([movement('a', 0)] * 2001)),
            ('too many bytes', VALID[:-1] + b' ' * (131073 - len(VALID)) + b'\n'),
        ]
        for account in ['', 'A', '_a', '0a', 'a-b', 'a b', 'a\n', 'a' * 33, 'é', '\ud800', 1, True, None, [], {}]:
            cases.append(('account ' + repr(account), encode([movement(account, 0)])))
        for delta in [10**12 + 1, -10**12 - 1, True, False, 0.0, 1.5, '1', None, [], {}]:
            cases.append(('delta ' + repr(delta), encode([movement('a', delta)])))
        for token in [b'NaN', b'Infinity', b'-Infinity', b'1e999', b'1.0', b'1e0']:
            cases.append(('numeric token ' + repr(token), b'{"entries":[{"account":"a","delta":' + token + b'}]}'))
        for name, raw in cases:
            for prefix in [b'', VALID]:
                with self.subTest(case=name, valid_prefix=bool(prefix)):
                    self.invalid(prefix + raw)

    def test_valid_invalid_valid_batch(self):
        self.invalid(VALID + b'{"entries":[{"account":"a","delta":true}]}\n' + VALID)


if __name__ == '__main__':
    unittest.main(verbosity=2)
