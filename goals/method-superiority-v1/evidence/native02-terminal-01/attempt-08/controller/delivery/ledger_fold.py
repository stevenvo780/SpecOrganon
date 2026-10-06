#!/usr/bin/env python3
"""Consolidación entera de lotes NDJSON con validación atómica."""
import json
import re
import sys

MAX_BYTES = 131072
ACCOUNT = re.compile(r'[a-z][a-z0-9_]{0,31}')


def invalid():
    raise ValueError('invalid input')


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            invalid()
        obj[key] = value
    return obj


def reject_constant(value):
    invalid()


def consolidate(line):
    request = json.loads(line, object_pairs_hook=unique_object,
                         parse_constant=reject_constant)
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
        account, delta = entry['account'], entry['delta']
        if type(account) is not str or ACCOUNT.fullmatch(account) is None:
            invalid()
        if type(delta) is not int or abs(delta) > 10**12:
            invalid()
        balances[account] = balances.get(account, 0) + delta
        total += delta
    return {'balances': balances, 'total': total, 'count': len(entries),
            'zero_accounts': sorted(a for a, b in balances.items() if b == 0)}


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
        result = consolidate(line)
        output.append(json.dumps(result, separators=(',', ':'),
                                 ensure_ascii=True) + '\n')
    return ''.join(output)


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        output = prepare(raw)
    except (ValueError, TypeError, RecursionError, OverflowError):
        sys.stderr.write('ledger-fold: invalid input\n')
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
