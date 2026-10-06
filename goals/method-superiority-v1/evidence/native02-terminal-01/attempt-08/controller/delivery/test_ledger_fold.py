import json
import subprocess
import sys

PROGRAM = '/input/delivery/ledger_fold.py'
ERROR = b'ledger-fold: invalid input\n'
CASES = []


def wire(obj):
    return json.dumps(obj, separators=(',', ':')).encode('ascii')


def request(entries):
    return wire({'entries': entries})


def movement(account, delta):
    return {'account': account, 'delta': delta}


def expected(balances, total, count, zeros):
    return {'balances': balances, 'total': total, 'count': count,
            'zero_accounts': zeros}


def valid(name, raw, outputs):
    CASES.append((name, raw, outputs))


def invalid(name, raw):
    CASES.append((name, raw, None))


EMPTY = request([])
ZERO = expected({}, 0, 0, [])
valid('empty-input', b'', [])
valid('example-empty', EMPTY + b'\n', [ZERO])
valid('example-cancellation', request([movement('cash', 7),
      movement('cash', -7), movement('bank', 3)]) + b'\n',
      [expected({'cash': 0, 'bank': 3}, 3, 3, ['cash'])])
valid('example-large-sum', request([movement('a', 10**12)] * 2),
      [expected({'a': 2 * 10**12}, 2 * 10**12, 2, [])])
valid('negative-large-sum', request([movement('a', -10**12)] * 2),
      [expected({'a': -2 * 10**12}, -2 * 10**12, 2, [])])
valid('zero-order-and-duplicates', request([movement('z', 0),
      movement('a', -4), movement('a', 4), movement('m', -3)]),
      [expected({'z': 0, 'a': 0, 'm': -3}, -3, 4, ['a', 'z'])])
valid('multiple-requests', EMPTY + b'\n' + request([movement('a', 2)])
      + b'\n', [ZERO, expected({'a': 2}, 2, 1, [])])
valid('whitespace-crlf', b' \t' + EMPTY + b' \r\n', [ZERO])
valid('entry-key-order', b'{"entries":[{"delta":1,"account":"a"}]}',
      [expected({'a': 1}, 1, 1, [])])
valid('escaped-ascii-account', b'{"entries":[{"account":"\\u0061","delta":-0}]}',
      [expected({'a': 0}, 0, 1, ['a'])])
ACCOUNT32 = 'a' + '0_' * 15 + 'z'
valid('account-length-32', request([movement(ACCOUNT32, 1)]),
      [expected({ACCOUNT32: 1}, 1, 1, [])])
valid('entries-2000', request([movement('a', 10**12)] * 2000),
      [expected({'a': 2000 * 10**12}, 2000 * 10**12, 2000, [])])
valid('bytes-131072', EMPTY + b' ' * (131072 - len(EMPTY)), [ZERO])
valid('bytes-131072-newline', EMPTY + b' ' * (131071 - len(EMPTY))
      + b'\n', [ZERO])

BAD = [
    ('blank', b'\n'), ('whitespace-only', b' \t\n'),
    ('extra-blank-line', EMPTY + b'\n\n'),
    ('utf8', b'\xff'), ('utf8-truncated', b'\xc3'),
    ('bom', b'\xef\xbb\xbf' + EMPTY),
    ('malformed', b'{'), ('trailing-json', EMPTY + b'{}'),
    ('trailing-comma', b'{"entries":[],}'),
    ('duplicate-root', b'{"entries":[],"entries":[]}'),
    ('duplicate-entry', b'{"entries":[{"account":"a","delta":1,"delta":2}]}'),
    ('duplicate-escaped-key', b'{"entries":[],"\\u0065ntries":[]}'),
    ('nested-duplicate', b'{"entries":[{"account":{"x":1,"x":2},"delta":1}]}'),
    ('extra-root', wire({'entries': [], 'extra': 0})),
    ('missing-root', b'{}'), ('root-list', b'[]'),
    ('root-null', b'null'), ('root-bool', b'true'),
    ('entries-null', wire({'entries': None})),
    ('entries-object', wire({'entries': {}})),
    ('entries-string', wire({'entries': ''})),
    ('entry-null', request([None])), ('entry-list', request([[]])),
    ('entry-number', request([1])), ('entry-missing', request([{}])),
    ('missing-delta', request([{'account': 'a'}])),
    ('missing-account', request([{'delta': 1}])),
    ('extra-entry', request([{'account': 'a', 'delta': 1, 'x': 0}])),
    ('entries-2001', request([movement('a', 0)] * 2001)),
    ('bytes-131073', EMPTY + b' ' * (131073 - len(EMPTY))),
    ('bytes-multirequest-over', EMPTY + b'\n' + EMPTY
        + b' ' * (131073 - 2 * len(EMPTY) - 1))
]
for index, account in enumerate(['', 'A', '_a', '0a', 'a-b', 'a b',
                                 'a\n', 'é', 'a' * 33, 1, True, None]):
    BAD.append(('account-' + str(index), request([movement(account, 1)])))
for index, delta in enumerate([True, False, 1.0, 0.0, '1', None, [], {},
                               10**12 + 1, -10**12 - 1]):
    BAD.append(('delta-' + str(index), request([movement('a', delta)])))
for token in [b'NaN', b'Infinity', b'-Infinity', b'1e0', b'1e999']:
    BAD.append(('numeric-' + token.decode('ascii'),
                b'{"entries":[{"account":"a","delta":' + token + b'}]}'))
for name, raw in BAD:
    invalid(name, raw)
    invalid('late-' + name, EMPTY + b'\n' + raw)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False)


def unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate output key')
        obj[key] = value
    return obj


def reject_constant(value):
    raise ValueError('nonfinite output')


def matches(proc, outputs):
    if outputs is None:
        return (proc.returncode == 2 and proc.stdout == b''
                and proc.stderr == ERROR)
    if proc.returncode != 0 or proc.stderr != b'':
        return False
    if not outputs:
        return proc.stdout == b''
    if not proc.stdout.endswith(b'\n'):
        return False
    lines = proc.stdout[:-1].split(b'\n')
    if len(lines) != len(outputs):
        return False
    actual = [json.loads(line.decode('utf-8'), object_pairs_hook=unique,
                         parse_constant=reject_constant) for line in lines]
    return all(canonical(a) == canonical(e) for a, e in zip(actual, outputs))


def main():
    executed = 0
    for name, raw, outputs in CASES:
        try:
            proc = subprocess.run([sys.executable, PROGRAM], input=raw,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=5, check=False)
            executed += 1
            conforming = matches(proc, outputs)
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError,
                RecursionError, OverflowError):
            print('FAIL ' + name + ' execution-or-output-error')
            return 1
        if not conforming:
            print('FAIL ' + name + ' contract-mismatch')
            return 1
    print('conforming_batches=' + str(executed) + '/' + str(len(CASES)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
