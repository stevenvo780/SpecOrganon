import json
import random
import subprocess
import sys

PYTHON = '/opt/specorganon/venv/bin/python'
PROGRAM = '/input/delivery/ledger_fold.py'
ERROR = b'ledger-fold: invalid input\n'
cases = []


def encode(obj):
    return json.dumps(obj, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def oracle(entries):
    names = sorted({e['account'] for e in entries})
    balances = {a: sum(e['delta'] for e in entries if e['account'] == a)
                for a in names}
    return {'balances': balances,
            'total': sum(e['delta'] for e in entries),
            'count': len(entries),
            'zero_accounts': [a for a in names if balances[a] == 0]}


def valid(name, requests, raw=None):
    if raw is None:
        raw = b''.join(encode({'entries': e}) + b'\n' for e in requests)
    cases.append((name, raw, [oracle(e) for e in requests]))


def invalid(name, raw):
    cases.append((name, raw, None))
    prefix = encode({'entries': [{'account': 'cash', 'delta': 7}]}) + b'\n'
    cases.append((name + '_late', prefix + raw, None))


examples = [
    [{'account': 'cash', 'delta': 7}, {'account': 'cash', 'delta': -7},
     {'account': 'bank', 'delta': 3}],
    [],
    [{'account': 'a', 'delta': 10**12}, {'account': 'a', 'delta': 10**12}],
]
for i, entries in enumerate(examples):
    valid('example_' + str(i), [entries])
valid('empty_stdin', [], b'')
valid('multiple', examples)
valid('no_final_newline', [examples[0]], encode({'entries': examples[0]}))
valid('crlf', examples, b'\r\n'.join(encode({'entries': e}) for e in examples) + b'\r\n')
valid('json_whitespace', [[]], b' \t { "entries" : [] } \t\r\n')
valid('zero_order', [[{'account': a, 'delta': d} for a, d in
                     [('z', 0), ('a', -9), ('z', 4), ('a', 9),
                      ('z', -4), ('middle', 0), ('negative', -3)]]])
valid('account_bounds', [[{'account': 'a', 'delta': -10**12},
                         {'account': 'a' + '9_' * 15 + 'z', 'delta': 10**12}]])
valid('negative_sum', [[{'account': 'a', 'delta': -10**12}] * 3])
valid('2000_entries', [[{'account': 'a', 'delta': 10**12}] * 2000])
base = encode({'entries': []})
valid('131072_bytes', [[]], base + b' ' * (131072 - len(base)))
valid('escaped_account', [[{'account': 'a', 'delta': 0}]],
      b'{"entries":[{"account":"\u0061","delta":-0}]}\n')

rng = random.Random(614)
for i in range(12):
    entries = [{'account': rng.choice(['cash', 'a_1', 'z', 'bank']),
                'delta': rng.choice([-10**12, -7, 0, 5, 10**12])}
               for _ in range(10 + i * 3)]
    valid('generated_' + str(i), [entries, list(reversed(entries)), []])

bad_raw = [
    ('blank', b'\n'), ('spaces', b' \t\n'),
    ('extra_blank', base + b'\n\n'),
    ('malformed', b'{"entries":['),
    ('trailing_json', base + b' true'),
    ('trailing_comma', b'{"entries":[],}'),
    ('duplicate_top', b'{"entries":[],"entries":[]}'),
    ('duplicate_escaped', b'{"entries":[],"\u0065ntries":[]}'),
    ('duplicate_account', b'{"entries":[{"account":"a","account":"b","delta":1}]}'),
    ('duplicate_delta', b'{"entries":[{"account":"a","delta":1,"delta":2}]}'),
    ('nan', b'{"entries":[{"account":"a","delta":NaN}]}'),
    ('inf', b'{"entries":[{"account":"a","delta":Infinity}]}'),
    ('negative_inf', b'{"entries":[{"account":"a","delta":-Infinity}]}'),
    ('invalid_utf8', b'{"entries":[]}\n\xff'),
    ('utf8_account', '{"entries":[{"account":"é","delta":1}]}'.encode('utf-8')),
    ('exponent', b'{"entries":[{"account":"a","delta":1e0}]}'),
    ('131073_bytes', base + b' ' * (131073 - len(base))),
]
for name, raw in bad_raw:
    invalid(name, raw)

bad_objects = [
    ('top_list', []), ('top_null', None), ('top_number', 1),
    ('top_bool', True), ('top_string', 'entries'),
    ('missing_entries', {}), ('extra_top', {'entries': [], 'extra': 0}),
    ('entries_null', {'entries': None}),
    ('entries_object', {'entries': {}}),
    ('entries_string', {'entries': ''}),
    ('entries_bool', {'entries': False}),
    ('2001_entries', {'entries': [{'account': 'a', 'delta': 0}] * 2001}),
]
for name, obj in bad_objects:
    invalid(name, encode(obj))
for i, entry in enumerate([None, [], 'a', 1, True, {},
                           {'account': 'a'}, {'delta': 1},
                           {'account': 'a', 'delta': 1, 'extra': 0}]):
    invalid('entry_' + str(i), encode({'entries': [entry]}))
for i, account in enumerate(['', 'A', '1a', '_a', 'a-b', 'a.b',
                             'a' * 33, 'a\n', 'a ', 'é', '\ud800',
                             1, True, None, [], {}]):
    invalid('account_' + str(i), encode({'entries': [{'account': account, 'delta': 1}]}))
for i, delta in enumerate([True, False, 1.0, 0.5, '1', None, [], {},
                           10**12 + 1, -10**12 - 1]):
    invalid('delta_' + str(i), encode({'entries': [{'account': 'a', 'delta': delta}]}))


def unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate output key')
        obj[key] = value
    return obj


def nonfinite(value):
    raise ValueError('nonfinite output')


def output_matches(raw, expected):
    if not expected:
        return raw == b''
    if not raw.endswith(b'\n'):
        return False
    lines = raw[:-1].split(b'\n')
    if len(lines) != len(expected):
        return False
    try:
        actual = [json.loads(line.decode('utf-8'), object_pairs_hook=unique,
                             parse_constant=nonfinite) for line in lines]
        # Canonical JSON distinguishes integers from bool and float values.
        return json.dumps(actual, sort_keys=True, separators=(',', ':')) == \
            json.dumps(expected, sort_keys=True, separators=(',', ':'))
    except (ValueError, UnicodeError, RecursionError):
        return False


def main():
    discrepancies = []
    for index, (name, raw, expected) in enumerate(cases):
        mask = 0
        try:
            run = subprocess.run([PYTHON, PROGRAM], input=raw,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=5, check=False,
                                 env={'PYTHONIOENCODING': 'utf-8', 'PYTHONHASHSEED': '0'})
            if run.returncode != (2 if expected is None else 0):
                mask |= 1
            if run.stderr != (ERROR if expected is None else b''):
                mask |= 2
            if expected is None:
                if run.stdout != b'':
                    mask |= 4
            elif not output_matches(run.stdout, expected):
                mask |= 4
        except (OSError, subprocess.TimeoutExpired):
            mask |= 8
        if mask:
            discrepancies.append([index, mask])
    # Every case has a stable zero-based index in the construction order above.
    # Masks: 1 exit, 2 stderr, 4 stdout, 8 execution unavailable/timeout.
    # One record per discrepant case; no captured product streams are echoed.
    print(json.dumps({'attempted': len(cases), 'discrepancies': discrepancies},
                     separators=(',', ':')))
    return 1 if discrepancies else 0


if __name__ == '__main__':
    sys.exit(main())
