"""Immutable stdlib battery; all fixtures and oracle logic are embedded."""
import json
import random
import subprocess
import sys

PROGRAM = '/input/delivery/ledger_fold.py'
ARGV = [sys.executable, '-I', '-B', '-c',
        'import runpy; runpy.run_path(' + repr(PROGRAM) + ", run_name='__main__')"]
ERROR = b'ledger-fold: invalid input\n'
CHECKS = 0
CURRENT = 'initialization'


def require(condition, detail):
    if not condition:
        raise AssertionError(detail)


def unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate output key')
        obj[key] = value
    return obj


def run(label, data):
    global CURRENT
    CURRENT = label
    return subprocess.run(ARGV, input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=5, check=False)


def valid(label, data, expected):
    global CHECKS
    result = run(label, data)
    require(result.returncode == 0, 'valid exit status')
    require(result.stderr == b'', 'valid stderr')
    if not expected:
        require(result.stdout == b'', 'empty batch output')
    else:
        require(result.stdout.endswith(b'\n'), 'output final newline')
        lines = result.stdout.split(b'\n')
        require(lines[-1] == b'' and len(lines) == len(expected) + 1,
                'output line count')
        for line, wanted in zip(lines[:-1], expected):
            actual = json.loads(line.decode('utf-8'), object_pairs_hook=unique)
            require(type(actual) is dict and set(actual) ==
                    {'balances', 'total', 'count', 'zero_accounts'}, 'output schema')
            require(type(actual['balances']) is dict, 'balances type')
            require(all(type(k) is str and type(v) is int
                        for k, v in actual['balances'].items()), 'balance types')
            require(type(actual['total']) is int and type(actual['count']) is int,
                    'total/count types')
            require(type(actual['zero_accounts']) is list and
                    all(type(a) is str for a in actual['zero_accounts']),
                    'zero_accounts type')
            require(actual == wanted, 'output value')
    CHECKS += 1


def invalid(label, data):
    global CHECKS
    result = run(label, data)
    require(result.returncode == 2, 'invalid exit status')
    require(result.stdout == b'', 'invalid stdout atomicity')
    require(result.stderr == ERROR, 'invalid diagnostic')
    CHECKS += 1


def encode(request):
    return json.dumps(request, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def oracle(entries):
    accounts = sorted({entry['account'] for entry in entries})
    balances = {account: sum(entry['delta'] for entry in entries
                            if entry['account'] == account) for account in accounts}
    return {'balances': balances, 'total': sum(balances.values()),
            'count': len(entries),
            'zero_accounts': [account for account in accounts if balances[account] == 0]}


def request_case(label, entries):
    valid(label, encode({'entries': entries}) + b'\n', [oracle(entries)])


def battery():
    empty = {'balances': {}, 'total': 0, 'count': 0, 'zero_accounts': []}
    line = b'{"entries":[]}'
    valid('empty stdin', b'', [])
    valid('empty entries', line + b'\n', [empty])
    valid('optional final newline', line, [empty])
    valid('CRLF batch', line + b'\r\n' + line + b'\r\n', [empty, empty])
    valid('JSON whitespace', b' \t{ "entries" : [ ] }\t\r\n', [empty])
    valid('multiple requests without terminal newline', line + b'\n' + line,
          [empty, empty])
    valid('many requests', (line + b'\n') * 100, [empty] * 100)
    request_case('public cancellation', [
        {'account': 'cash', 'delta': 7}, {'account': 'cash', 'delta': -7},
        {'account': 'bank', 'delta': 3}])
    request_case('unbounded accumulated sum', [
        {'account': 'a', 'delta': 10**12}, {'account': 'a', 'delta': 10**12}])
    request_case('negative accumulated sum', [
        {'account': 'a', 'delta': -10**12}, {'account': 'a', 'delta': -10**12}])
    request_case('zero retention sorting and duplicates', [
        {'account': 'z', 'delta': 0}, {'account': 'a', 'delta': 4},
        {'account': 'a', 'delta': -4}, {'account': 'm', 'delta': 0},
        {'account': 'b', 'delta': -1}, {'account': 'b', 'delta': -1}])
    for account in ['a', 'a' * 32, 'a0_', 'z9_' + '0' * 29]:
        request_case('valid account ' + account, [{'account': account, 'delta': 0}])
    for delta in [-10**12, -1, 0, 1, 10**12]:
        request_case('valid delta ' + str(delta), [{'account': 'a', 'delta': delta}])
    valid('escaped ASCII keys and account',
          b'{"entr\\u0069es":[{"account":"\\u0061","delta":-0}]}\n',
          [{'balances': {'a': 0}, 'total': 0, 'count': 1, 'zero_accounts': ['a']}])
    entries = [{'account': 'a', 'delta': 10**12}] * 2000
    request_case('2000 entries', entries)
    invalid('2001 entries', encode({'entries': entries + [entries[0]]}))
    valid('byte limit exact', line + b' ' * (131072 - len(line)), [empty])
    valid('byte limit exact including newline',
          line + b' ' * (131071 - len(line)) + b'\n', [empty])
    invalid('byte limit plus one', line + b' ' * (131073 - len(line)))
    invalid('oversized multirequest batch', (line + b'\n') * 10000)

    bad = [
        ('newline only', b'\n'), ('space only', b' '), ('CR only', b'\r'),
        ('leading blank', b'\n' + line),
        ('internal blank', line + b'\n\n' + line),
        ('trailing blank', line + b'\n\n'),
        ('whitespace request', line + b'\n \t\r\n'),
        ('malformed', b'{'), ('trailing comma', b'{"entries":[],}'),
        ('comment', b'{"entries":[]} // comment'),
        ('concatenated objects', line + line),
        ('UTF8 BOM', b'\xef\xbb\xbf' + line),
        ('invalid UTF8 leading', b'\xff' + line),
        ('invalid UTF8 trailing', line + b'\x80'),
        ('invalid UTF8 account', b'{"entries":[{"account":"\xff","delta":0}]}'),
        ('overlong UTF8', b'\xc0\xaf'),
        ('truncated UTF8', b'\xe2\x82'),
        ('UTF8 surrogate', b'\xed\xa0\x80'),
        ('duplicate top key', b'{"entries":[],"entries":[]}'),
        ('escaped duplicate key', b'{"entries":[],"entr\\u0069es":[]}'),
        ('duplicate account', b'{"entries":[{"account":"a","account":"b","delta":0}]}'),
        ('duplicate delta', b'{"entries":[{"account":"a","delta":0,"delta":1}]}'),
        ('nested duplicate', b'{"entries":[{"account":{"x":1,"x":2},"delta":0}]}'),
        ('extra nested duplicate', b'{"entries":[],"extra":{"x":1,"x":2}}'),
        ('deep nesting', b'{"entries":' + b'[' * 1500 + b']' * 1500 + b'}'),
        ('huge integer', b'{"entries":[{"account":"a","delta":' + b'9' * 5000 + b'}]}'),
    ]
    for value in [None, True, 1, 1.0, 'x', [], {}, {'entries': [], 'extra': 0}]:
        bad.append(('top schema ' + repr(value), encode(value)))
    for value in [None, True, 0, 'x', {}]:
        bad.append(('entries type ' + repr(value), encode({'entries': value})))
    for value in [None, True, 0, 'x', [], {}, {'account': 'a'}, {'delta': 0},
                  {'account': 'a', 'delta': 0, 'extra': 1}]:
        bad.append(('entry schema ' + repr(value), encode({'entries': [value]})))
    for account in ['', 'a' * 33, 'A', 'aB', '1a', '_a', 'a-b', 'a.b',
                    'a b', 'a\n', 'é', 'aé', 'а', 'a\x00', None, True, 1, [], {}]:
        bad.append(('bad account ' + repr(account),
                    encode({'entries': [{'account': account, 'delta': 0}]})))
    for delta in [10**12 + 1, -10**12 - 1, True, False, 0.0, 1.0,
                  '1', None, [], {}]:
        bad.append(('bad delta ' + repr(delta),
                    encode({'entries': [{'account': 'a', 'delta': delta}]})))
    for token in [b'1e0', b'1E12', b'-0.0', b'NaN', b'Infinity', b'-Infinity',
                  b'1e999', b'01', b'+1']:
        bad.append(('bad number ' + token.decode('ascii'),
                    b'{"entries":[{"account":"a","delta":' + token + b'}]}'))
    for token in [b'NaN', b'Infinity', b'-Infinity']:
        bad.append(('top nonfinite ' + token.decode('ascii'), token))
    for label, data in bad:
        invalid(label, data)
    for label, data in bad:
        if b'\n' not in data and len(data) < 1000:
            invalid('atomic sandwich ' + label, line + b'\n' + data + b'\n' + line + b'\n')
    invalid('late UTF8 failure', line + b'\n\xff\n')
    invalid('late oversized input', line + b'\n' + line + b' ' * 131072)

    rng = random.Random(92741)
    accounts = ['a', 'b', 'cash', 'bank', 'a0_', 'z', 'a' * 32]
    for batch_index in range(20):
        requests = []
        expected = []
        for _ in range(1 + batch_index % 5):
            entries = [{'account': rng.choice(accounts),
                        'delta': rng.choice([-10**12, 10**12, 0, rng.randint(-9999, 9999)])}
                       for _ in range(rng.randrange(100))]
            requests.append(encode({'entries': entries}))
            expected.append(oracle(entries))
        data = b'\n'.join(requests) + (b'\n' if batch_index % 2 else b'')
        valid('generated batch ' + str(batch_index), data, expected)


def main():
    try:
        battery()
    except Exception as exc:
        print(json.dumps({'status': 'fail', 'completed_checks': CHECKS,
                          'case': CURRENT, 'error_type': type(exc).__name__,
                          'detail': str(exc) if isinstance(exc, AssertionError)
                          else 'harness or decoding exception'}, separators=(',', ':')))
        return 1
    print(json.dumps({'status': 'pass', 'completed_checks': CHECKS}, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
