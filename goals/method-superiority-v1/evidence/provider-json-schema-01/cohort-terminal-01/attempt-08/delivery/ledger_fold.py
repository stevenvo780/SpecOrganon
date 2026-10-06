"""Consolidate strictly validated NDJSON batches from standard input."""

import json
import re
import sys


MAX_BYTES = 131072
ACCOUNT = re.compile(r'[a-z][a-z0-9_]{0,31}', re.ASCII)


def invalid(*args):
    raise ValueError('invalid input')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            invalid()
        result[key] = value
    return result


def consolidate(line):
    request = json.loads(
        line, object_pairs_hook=unique_object, parse_constant=invalid
    )
    if type(request) is not dict or set(request) != {'entries'}:
        invalid()
    entries = request['entries']
    if type(entries) is not list or len(entries) > 2000:
        invalid()
    balances = {}
    total = 0
    for entry in entries:
        if type(entry) is not dict or set(entry) != {'account', 'delta'}:
            invalid()
        account = entry['account']
        delta = entry['delta']
        if type(account) is not str or ACCOUNT.fullmatch(account) is None:
            invalid()
        if type(delta) is not int or abs(delta) > 10**12:
            invalid()
        balances[account] = balances.get(account, 0) + delta
        total += delta
    return {
        'balances': balances,
        'total': total,
        'count': len(entries),
        'zero_accounts': sorted(
            account for account, balance in balances.items() if balance == 0
        ),
    }


def prepare(raw):
    if len(raw) > MAX_BYTES:
        invalid()
    text = raw.decode('utf-8', errors='strict')
    if not text:
        return ''
    lines = text.split('\n')
    if lines[-1] == '':
        lines.pop()
    output = []
    for line in lines:
        if not line.strip():
            invalid()
        result = consolidate(line)
        output.append(json.dumps(result, separators=(',', ':')) + '\n')
    return ''.join(output)


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        output = prepare(raw)
    except (ValueError, UnicodeError, RecursionError):
        sys.stderr.write('ledger-fold: invalid input\n')
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
