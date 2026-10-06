#!/usr/bin/env python3
"""Fixed stdlib CLI battery; fixtures and independent oracle are inline."""
import json
from pathlib import Path
import random
import subprocess
import sys

PROGRAM = str(Path(__file__).resolve().with_name('ledger_fold.py'))
ARGV = [sys.executable, '-I', '-B', '-c',
        'import runpy; runpy.run_path(' + repr(PROGRAM) + ', run_name="__main__")']
ERROR = b'ledger-fold: invalid input\n'
CHECKS = 0
CURRENT = 'initialization'


class CheckFailure(Exception):
    pass


def require(condition, detail):
    if not condition:
        raise CheckFailure(detail)


def invoke(data, label):
    global CURRENT, CHECKS
    CURRENT = label
    CHECKS += 1
    return subprocess.run(ARGV, input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=5, check=False)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CheckFailure('duplicate output key')
        result[key] = value
    return result


def reject_constant(value):
    raise CheckFailure('nonfinite output')


def identical(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return (actual.keys() == expected.keys()
                and all(identical(actual[k], expected[k]) for k in expected))
    if type(expected) is list:
        return (len(actual) == len(expected)
                and all(identical(a, b) for a, b in zip(actual, expected)))
    return actual == expected


def oracle(entries):
    names = sorted({entry['account'] for entry in entries})
    balances = {name: sum(entry['delta'] for entry in entries
                          if entry['account'] == name) for name in names}
    return {'balances': balances,
            'total': sum(entry['delta'] for entry in entries),
            'count': len(entries),
            'zero_accounts': [name for name in names if balances[name] == 0]}


def encoded(entries):
    return json.dumps({'entries': entries}, separators=(',', ':')).encode('utf-8')


def valid(data, expected, label):
    result = invoke(data, label)
    require(result.returncode == 0, 'valid exit status')
    require(result.stderr == b'', 'valid stderr')
    if not expected:
        require(result.stdout == b'', 'empty batch output')
        return
    require(result.stdout.endswith(b'\n'), 'output terminal newline')
    lines = result.stdout[:-1].split(b'\n')
    require(len(lines) == len(expected), 'output line count')
    actual = [json.loads(line.decode('utf-8'), object_pairs_hook=unique_object,
                         parse_constant=reject_constant) for line in lines]
    require(identical(actual, expected), 'output shape, types, or values')


def invalid(data, label):
    result = invoke(data, label)
    require(result.returncode == 2, 'invalid exit status')
    require(result.stdout == b'', 'invalid batch leaked output')
    require(result.stderr == ERROR, 'invalid diagnostic')


def run():
    valid(b'', [], 'empty stdin')
    empty = oracle([])
    valid(b'{"entries":[]}', [empty], 'no final newline')
    valid(b'{"entries":[]}\n', [empty], 'final newline')
    valid(b' \t{"entries":[]}\r\n{"entries":[]}\r\n',
          [empty, empty], 'CRLF and JSON whitespace')
    examples = [
        [{'account': 'cash', 'delta': 7}, {'account': 'cash', 'delta': -7},
         {'account': 'bank', 'delta': 3}],
        [],
        [{'account': 'a', 'delta': 10**12}, {'account': 'a', 'delta': 10**12}],
    ]
    valid(b'\n'.join(encoded(e) for e in examples) + b'\n',
          [oracle(e) for e in examples], 'public examples batch')
    entries = [{'account': 'z', 'delta': 0}, {'account': 'a', 'delta': -4},
               {'account': 'a', 'delta': 4}, {'account': 'm', 'delta': -10**12},
               {'account': 'm', 'delta': -10**12},
               {'account': 'b0_' + 'x'*28, 'delta': 10**12}]
    valid(encoded(entries), [oracle(entries)], 'sorted zeros and signed sums')
    valid(b'{"entr\u0069es":[{"account":"\u0061","delta":-0}]}',
          [oracle([{'account': 'a', 'delta': 0}])], 'escaped valid names and negative zero')
    maximum = [{'account': 'a', 'delta': 10**12} for _ in range(2000)]
    valid(encoded(maximum), [oracle(maximum)], '2000 entries and large sum')
    distinct = [{'account': 'a' + str(i), 'delta': (i % 3) - 1}
                for i in range(2000)]
    valid(encoded(distinct), [oracle(distinct)], '2000 distinct accounts')
    base = b'{"entries":[]}'
    exact = base + b' ' * (131072 - len(base))
    valid(exact, [empty], 'exact byte cap')
    valid(exact[:-1] + b'\n', [empty], 'exact byte cap including newline')
    invalid(exact + b' ', 'byte cap plus one')
    invalid(exact + b' ' * 8192, 'byte overflow sentinel')
    invalid(encoded(maximum + [{'account': 'a', 'delta': 0}]), '2001 entries')

    bad = [
        ('blank', b''), ('whitespace', b' \t\r'),
        ('consecutive newlines', b'\n'), ('null root', b'null'),
        ('array root', b'[]'), ('string root', b'"x"'),
        ('integer root', b'1'), ('boolean root', b'true'),
        ('missing entries', b'{}'), ('extra root field', b'{"entries":[],"x":0}'),
        ('null entries', b'{"entries":null}'),
        ('object entries', b'{"entries":{}}'),
        ('string entries', b'{"entries":"x"}'),
        ('boolean entries', b'{"entries":false}'),
        ('duplicate root', b'{"entries":[],"entries":[]}'),
        ('escaped duplicate root', b'{"entries":[],"\u0065ntries":[]}'),
        ('duplicate account', b'{"entries":[{"account":"a","account":"b","delta":1}]}'),
        ('duplicate delta', b'{"entries":[{"account":"a","delta":1,"delta":2}]}'),
        ('escaped duplicate delta', b'{"entries":[{"account":"a","delta":1,"\u0064elta":2}]}'),
        ('deep duplicate', b'{"entries":[{"account":"a","delta":{"x":{"k":0,"k":1}}}]}'),
        ('extra entry field', b'{"entries":[{"account":"a","delta":0,"x":0}]}'),
        ('missing account', b'{"entries":[{"delta":0}]}'),
        ('missing delta', b'{"entries":[{"account":"a"}]}'),
        ('null entry', b'{"entries":[null]}'),
        ('array entry', b'{"entries":[[]]}'),
        ('scalar entry', b'{"entries":[1]}'),
        ('truncated JSON', b'{"entries":['),
        ('trailing comma', b'{"entries":[],}'),
        ('two roots on one line', b'{"entries":[]} {"entries":[]}'),
        ('comment', b'{"entries":[]} // comment'),
        ('leading zero', b'{"entries":[{"account":"a","delta":01}]}'),
        ('plus sign', b'{"entries":[{"account":"a","delta":+1}]}'),
        ('invalid escape', b'{"entries":[{"account":"\\q","delta":0}]}'),
        ('literal control', b'{"entries":[{"account":"a\t","delta":0}]}'),
        ('invalid UTF8', b'{"entries":[]}\xff'),
        ('overlong UTF8', b'{"entries":[]}\xc0\xaf'),
        ('truncated UTF8', b'{"entries":[]}\xe2\x82'),
        ('UTF8 surrogate', b'{"entries":[]}\xed\xa0\x80'),
        ('BOM', b'\xef\xbb\xbf{"entries":[]}'),
        ('unicode line separator', '{"entries":[]}\u2028{"entries":[]}'.encode('utf-8')),
        ('deep nesting', b'{"entries":' + b'['*3000 + b']'*3000 + b'}'),
        ('huge integer', b'{"entries":[{"account":"a","delta":' + b'9'*5000 + b'}]}'),
    ]
    for constant in ('NaN', 'Infinity', '-Infinity'):
        bad.append(('constant ' + constant,
                    ('{"entries":[{"account":"a","delta":' + constant + '}]}').encode()))
    for token in ('true', 'false', 'null', '"1"', '[]', '{}', '1.0',
                  '1e0', '1e9999', '-0.0', '1000000000001', '-1000000000001'):
        bad.append(('delta ' + token,
                    ('{"entries":[{"account":"a","delta":' + token + '}]}').encode()))
    for index, account in enumerate(('', 'A', '0a', '_a', 'a-b', 'a b',
                                     'a\n', 'a'*33, 'é', 'aé', 'a\x00',
                                     '\ud800', None, 1, True, [], {})):
        bad.append(('account type or pattern ' + str(index),
                    encoded([{'account': account, 'delta': 0}])))
    prefix = b'{"entries":[{"account":"prefix","delta":9}]}\n'
    for label, data in bad:
        # Empty standalone stdin is valid; an empty request line is not.
        standalone = b'\n' if data == b'' else data
        invalid(standalone, label)
        invalid(prefix + standalone, 'atomic prefix: ' + label)
    invalid(prefix + b'\n{"entries":[]}\n', 'blank between valid requests')
    invalid(prefix + b'{"entries":[]}\n\n', 'extra terminal blank line')

    rng = random.Random(1701)
    requests = []
    names = ['a', 'a0', 'a_', 'bank', 'cash', 'z', 'x'*32]
    deltas = [-10**12, -7, -1, 0, 1, 7, 10**12]
    for _ in range(60):
        requests.append([{'account': rng.choice(names), 'delta': rng.choice(deltas)}
                         for _ in range(rng.randrange(100))])
    payload = b'\n'.join(encoded(e) for e in requests)
    require(len(payload) <= 131072, 'generated fixture byte bound')
    valid(payload, [oracle(e) for e in requests], 'seeded aggregation batch')
    reordered = [list(reversed(e)) for e in requests]
    valid(b'\n'.join(encoded(e) for e in reordered) + b'\n',
          [oracle(e) for e in requests], 'movement order invariance')


def main():
    try:
        run()
    except Exception as error:
        # Stop at the first failure, retain nonzero status, and avoid dumping
        # potentially large subprocess streams into the host evidence stream.
        detail = str(error) if isinstance(error, CheckFailure) else type(error).__name__
        print(json.dumps({'status': 'fail', 'checks_started': CHECKS,
                          'case': CURRENT, 'detail': detail}, separators=(',', ':')))
        return 1
    print(json.dumps({'status': 'pass', 'checks': CHECKS}, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
